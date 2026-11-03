#!/usr/bin/env python3
"""Select a depth view, write an Image Gen prompt, and verify saved candidates.

Image generation itself uses Codex's built-in Image Gen tool. ``prepare`` writes
the exact prompt and selected reference image; ``review`` audits a saved result
and either accepts it or writes the next prompt. No Qwen model is loaded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw
import torch
import yaml
from munch import Munch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.depth_prompting import DepthPrompting
from src.depth_semantic_prompt import build_depth_semantic_prompt
from src.mainline_data import load_partial
from src.prior_generation_agent import PriorGenerationAgent, compose_depth_edit_prompt, PROMPT_VERSION

CAMERA_FILES = ("depth.png", "raw_depth.png", "camera.pth", "point_uv.npy", "viewpoint.npy", "mask.png")


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def verify_review_canvas(review_dir: Path, audit: dict) -> tuple[int, int]:
    """Refuse pixelwise review unless all three images share the recorded canvas."""
    mapping = audit.get("canvas_mapping", {})
    expected = tuple(mapping.get("comparison_size", ()))
    if len(expected) != 2 or any(not isinstance(side, int) or side <= 0 for side in expected):
        raise ValueError("layout audit has no valid comparison canvas")
    for name in ("comparison_depth.png", "img.png", "semantic_depth_audit.png"):
        with Image.open(review_dir / name) as image:
            if image.size != expected:
                raise ValueError(f"{name} is {image.size}, expected {expected}; cannot compare contours")
    return expected


def _camera_files(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in CAMERA_FILES:
        source_file = source / name
        if not source_file.is_file():
            raise FileNotFoundError(source_file)
        shutil.copy2(source_file, destination / name)


def _rotated_views(initial: np.ndarray) -> list[np.ndarray]:
    """Fixed nearby alternatives, avoiding category- or GT-dependent search."""
    initial = np.asarray(initial, dtype=np.float64)
    radius = float(np.linalg.norm(initial))
    if radius <= 0:
        raise ValueError("invalid saved viewpoint")
    x, y, z = initial / radius
    candidates = [initial]
    for degrees in (-45.0, 45.0):
        angle = math.radians(degrees)
        candidates.append(radius * np.array([
            math.cos(angle) * x + math.sin(angle) * z,
            y,
            -math.sin(angle) * x + math.cos(angle) * z,
        ]))
    candidates.append(radius * np.array([x, min(y + .35, .95), z]) /
                      np.linalg.norm([x, min(y + .35, .95), z]))
    return candidates


def _board(candidates: Path, ids: list[str], output: Path) -> None:
    board = Image.new("RGB", (1024, 1090), "white")
    draw = ImageDraw.Draw(board)
    for index, view_id in enumerate(ids):
        image = Image.open(candidates / view_id / "depth.png").convert("RGB")
        image = image.resize((512, 512), Image.Resampling.NEAREST)
        x, y = (index % 2) * 512, (index // 2) * 545
        draw.text((x + 12, y + 6), view_id + "  partial depth", fill="black")
        board.paste(image, (x, y + 30))
    board.save(output)


def prepare(args: argparse.Namespace) -> None:
    root = args.output_root.resolve()
    partial = args.partial.resolve()
    if not partial.is_file():
        raise FileNotFoundError(partial)
    agent_dir = root / "prior_agent"
    state_path = agent_dir / "prior_agent_manifest.json"
    if state_path.exists():
        raise FileExistsError(f"prior plan already exists; use its saved prompt: {state_path}")
    agent_dir.mkdir(parents=True, exist_ok=True)
    camera = root / "inputs" / "camera" / args.sample
    base_prompt = build_depth_semantic_prompt(args.object_description,
                                              structural_constraints=tuple(args.constraint))
    if args.camera_source is not None:
        source_camera = args.camera_source.resolve()
        _camera_files(source_camera, camera)
        selected = "fixed_saved_camera"
        board = camera / "depth.png"
        view_candidates = {selected: str(board)}
        result = {"decision": {"view_id": selected,
                               "reason": "Use the supplied saved acquisition camera"},
                  "model": args.model, "provider": "fixed_saved_camera",
                  "prompt_version": PROMPT_VERSION}
        camera_source = {"directory": str(source_camera),
                         "depth_sha256": _hash(source_camera / "depth.png"),
                         "camera_sha256": _hash(source_camera / "camera.pth"),
                         "point_uv_sha256": _hash(source_camera / "point_uv.npy")}
    else:
        if not (camera / "depth.png").is_file():
            command = [sys.executable, str(ROOT / "scripts" / "run_semantic_stage.py"),
                       "--output-root", str(root / "inputs" / "camera"),
                       "--partial-root", str(partial.parent), "--samples", args.sample,
                       "--depth-only"]
            subprocess.run(command, check=True, cwd=ROOT)
        candidates = agent_dir / "candidates"
        view_ids = [f"view_{index:02d}" for index in range(4)]
        _camera_files(camera, candidates / view_ids[0])
        cfg = Munch.fromDict(yaml.safe_load(args.config.read_text(encoding="utf-8")))
        cfg.paths.output_dir = str(candidates)
        cfg.paths.data_dir = str(partial.parent)
        cfg.paths.models_dir = str(args.models_root.resolve())
        editor = DepthPrompting(cfg)
        points, colors = load_partial(partial)
        xyz = torch.from_numpy(points).to(editor.device)
        rgb = torch.from_numpy(colors).to(editor.device)
        initial = np.load(camera / "viewpoint.npy")
        try:
            for view_id, viewpoint in zip(view_ids[1:], _rotated_views(initial)[1:]):
                editor.save_depth_observation(xyz, view_id, rgb,
                                              viewpoint_override=viewpoint.astype(np.float32),
                                              viewpoint_is_source_camera=False)
        finally:
            editor.close()
        board = agent_dir / "candidate_depth_board.png"
        _board(candidates, view_ids, board)
        result = PriorGenerationAgent(args.model).select_view(
            board=board, view_ids=view_ids, object_description=args.object_description,
            base_prompt=base_prompt,
        )
        selected = result["decision"]["view_id"]
        _camera_files(candidates / selected, camera)
        view_candidates = {view_id: str(candidates / view_id / "depth.png")
                           for view_id in view_ids}
        camera_source = None
    decision = result["decision"]
    if "prompt" in decision:
        decision["agent_draft_prompt"] = decision["prompt"]
    decision["prompt"] = compose_depth_edit_prompt(object_description=args.object_description)
    partial_input = root / "inputs" / "partial" / f"{args.sample}.ply"
    partial_input.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(partial, partial_input)
    prompt_file = agent_dir / "round_00_prompt.txt"
    prompt_file.write_text(result["decision"]["prompt"].strip() + "\n", encoding="utf-8")
    state = {
        "schema": "compagent.prior_agent.v1", "sample": args.sample,
        "ground_truth_used": False, "object_description": args.object_description,
        "input_partial": str(partial_input), "input_partial_sha256": _hash(partial_input),
        "view_candidates": view_candidates, "camera_source": camera_source,
        "selected_view": selected, "selected_depth": str(camera / "depth.png"),
        "camera_dir": str(camera), "view_board": str(board),
        "base_prompt": base_prompt, "selection": result,
        "current_prompt_file": str(prompt_file), "reviews": [], "accepted": None,
    }
    _write(state_path, state)
    print(json.dumps({"selected_depth": state["selected_depth"],
                      "imagegen_prompt": str(prompt_file), "manifest": str(state_path)}, indent=2))


def review(args: argparse.Namespace) -> None:
    root = args.output_root.resolve()
    state_path = root / "prior_agent" / "prior_agent_manifest.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state["accepted"] is not None:
        raise ValueError("an accepted image is already frozen in this run")
    candidate = args.candidate.resolve()
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    index = len(state["reviews"])
    if index >= 8:
        raise ValueError("maximum eight Image Gen reviews per run")
    review_dir = root / "prior_agent" / f"round_{index:02d}"
    review_dir.mkdir(parents=True, exist_ok=True)
    candidate_copy = review_dir / "imagegen_candidate.png"
    shutil.copy2(candidate, candidate_copy)
    prompt_path = Path(state["current_prompt_file"])
    command = [sys.executable, str(ROOT / "scripts" / "install_depth_conditioned_semantic.py"),
               "--sample", state["sample"], "--semantic", str(candidate_copy),
               "--depth", state["selected_depth"], "--prompt-file", str(prompt_path),
               "--camera-dir", str(review_dir), "--rmbg-model", str(args.rmbg_model.resolve()),
               "--positive-support-only"]
    audit_run = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    (review_dir / "layout_audit.log").write_text(audit_run.stdout + audit_run.stderr, encoding="utf-8")
    if audit_run.returncode != 0:
        raise RuntimeError(f"semantic layout audit failed: {review_dir / 'layout_audit.log'}")
    audit = json.loads((review_dir / "semantic_install_manifest.json").read_text(encoding="utf-8"))
    comparison_size = verify_review_canvas(review_dir, audit)
    depth_audit_path = review_dir / "ordinal_depth_audit.json"
    depth_command = [sys.executable, str(ROOT / "scripts" / "audit_prior_depth_order.py"),
                     "--depth", str(review_dir / "comparison_depth.png"),
                     "--semantic", str(review_dir / "img.png"),
                     "--rgba", str(review_dir / "img_rmbg.png"),
                     "--moge-model", str(args.moge_model.resolve()),
                     "--output", str(depth_audit_path)]
    depth_run = subprocess.run(depth_command, cwd=ROOT, text=True,
                               capture_output=True, check=False)
    (review_dir / "ordinal_depth_audit.log").write_text(
        depth_run.stdout + depth_run.stderr, encoding="utf-8")
    if depth_run.returncode != 0:
        raise RuntimeError(f"ordinal depth audit failed: {review_dir / 'ordinal_depth_audit.log'}")
    depth_audit = json.loads(depth_audit_path.read_text(encoding="utf-8"))
    result = PriorGenerationAgent(args.model).review(
        depth=review_dir / "comparison_depth.png", candidate=review_dir / "img.png",
        audit_overlay=review_dir / "semantic_depth_audit.png", audit=audit,
        prompt=prompt_path.read_text(encoding="utf-8"),
        object_description=state["object_description"],
        depth_audit=depth_audit,
    )
    decision = result["decision"]
    accepted = bool(audit["passed"] and decision["action"] == "ACCEPT"
                    and decision["pose_and_orientation_match"]
                    and decision["natural_construction"]
                    and decision["visible_structure_match"]
                    and decision["category_identity_match"]
                    and decision["depth_order_match"]
                    and decision["projected_envelope_match"]
                    and decision["functional_form_match"]
                    and decision["complete_object"])
    row = {"candidate": str(candidate_copy), "candidate_sha256": _hash(candidate_copy),
           "prompt_file": str(prompt_path), "layout_audit": str(review_dir / "semantic_install_manifest.json"),
           "comparison_size": list(comparison_size),
           "ordinal_depth_audit": str(depth_audit_path),
           "decision": result, "accepted": accepted}
    state["reviews"].append(row)
    if accepted:
        camera = Path(state["camera_dir"])
        for name in ("img.png", "img_rmbg.png", f"{state['sample']}_moge_to_raw_partial_object_mask.png",
                     "semantic_depth_audit.png", "semantic_install_manifest.json",
                     "ordinal_depth_audit.json"):
            shutil.copy2(review_dir / name, camera / name)
        pixal_input = root / "inputs" / "pixal" / state["sample"]
        pixal_input.mkdir(parents=True, exist_ok=True)
        # Pixal receives the saved transparent RMBG image. Its own fixed
        # preprocessor crops and composites this alpha image, and MoGe later
        # observes that exact preprocessed Pixal input.
        shutil.copy2(review_dir / "img_rmbg.png", pixal_input / "gpt_image.png")
        shutil.copy2(prompt_path, pixal_input / "gpt_depth_completion_prompt.txt")
        state["accepted"] = {
            "source_image": str(candidate_copy), "source_sha256": _hash(candidate_copy),
            "installed_image": str(camera / "img.png"),
            "installed_sha256": _hash(camera / "img.png"),
            "pixal_input": str(pixal_input / "gpt_image.png"),
            "pixal_input_sha256": _hash(pixal_input / "gpt_image.png"),
            "pixal_input_mode": "RGBA_RMBG",
            "prompt_file": str(prompt_path), "review_index": index,
        }
    else:
        next_path = root / "prior_agent" / f"round_{index+1:02d}_prompt.txt"
        revised = compose_depth_edit_prompt(
            object_description=state["object_description"],
            revision_feedback=decision["reason"],
        )
        next_path.write_text(revised + "\n", encoding="utf-8")
        state["current_prompt_file"] = str(next_path)
    _write(state_path, state)
    print(json.dumps({"accepted": accepted, "audit_passed": audit["passed"],
                      "decision": result["decision"],
                      "next_prompt_file": None if accepted else state["current_prompt_file"]},
                     ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--sample", required=True)
    prep.add_argument("--partial", type=Path, required=True)
    prep.add_argument("--object", dest="object_description", required=True)
    prep.add_argument("--constraint", action="append", default=[])
    prep.add_argument("--output-root", type=Path, required=True)
    prep.add_argument("--config", type=Path, default=ROOT / "configs" / "mainline_redwood.yaml")
    prep.add_argument("--models-root", type=Path, default=ROOT / "models")
    prep.add_argument("--camera-source", type=Path,
                      help="Existing saved camera directory; skip view selection")
    prep.add_argument("--model", default="gpt-6-sol")
    rev = commands.add_parser("review")
    rev.add_argument("--candidate", type=Path, required=True)
    rev.add_argument("--output-root", type=Path, required=True)
    rev.add_argument("--rmbg-model", type=Path, default=ROOT / "models" / "RMBG-2.0")
    rev.add_argument("--moge-model", type=Path, default=ROOT / "models" / "moge-2-vitl" / "model.pt")
    rev.add_argument("--model", default="gpt-6-sol")
    args = parser.parse_args()
    (prepare if args.command == "prepare" else review)(args)


if __name__ == "__main__":
    main()
