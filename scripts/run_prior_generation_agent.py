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
import fpsample

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


def _layout_revision(prompt: str, audit: dict, canvas_size: tuple[int, int]) -> str:
    """Ground a retry in the observed support's pixel location, not GT."""
    box = audit.get("depth_bbox_xyxy")
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError("layout audit has no observed depth box")
    width, height = canvas_size
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError("invalid observed depth box")
    percentages = (round(100*x0/width), round(100*y0/height),
                   round(100*x1/width), round(100*y1/height))
    return (prompt.strip() + "\n请重新对齐图1的可见部分：其横向约位于画幅的"
            f"{percentages[0]}%–{percentages[2]}%，纵向约位于"
            f"{percentages[1]}%–{percentages[3]}%。保持可见部件在原画面中的"
            "位置、尺度和相互关系；缺失部位仍自然补全成完整物体。")


def _base_completion_prompt(root: Path) -> str:
    agent_dir = root / "prior_agent"
    enriched = agent_dir / "depth_relation_prompt.txt"
    initial = enriched if enriched.is_file() else agent_dir / "round_00_prompt.txt"
    return initial.read_text(encoding="utf-8").strip()


def _camera_files(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in CAMERA_FILES:
        source_file = source / name
        if not source_file.is_file():
            raise FileNotFoundError(source_file)
        shutil.copy2(source_file, destination / name)
    # Pinhole datasets record the exact raster/intrinsic convention here.
    sidecar = source / "camera.json"
    if sidecar.is_file():
        shutil.copy2(sidecar, destination / sidecar.name)


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


def select_diverse_view_indices(viewpoints: np.ndarray, visible_counts: np.ndarray,
                                *, count: int = 20, minimum_angle_deg: float = 25.0) -> list[int]:
    """Coverage-first spherical selection with a fixed angular separation."""
    views = np.asarray(viewpoints, dtype=np.float64)
    scores = np.asarray(visible_counts)
    if views.ndim != 2 or views.shape[1] != 3 or scores.shape != (len(views),):
        raise ValueError("viewpoint and visible-count shapes differ")
    if count < 1 or not 0 < minimum_angle_deg < 180:
        raise ValueError("invalid view selection settings")
    directions = views / np.linalg.norm(views, axis=1, keepdims=True)
    cosine_limit = math.cos(math.radians(minimum_angle_deg))
    ranking = sorted(range(len(views)), key=lambda index: (-int(scores[index]), index))
    chosen = []
    for index in ranking:
        if all(float(directions[index] @ directions[prior]) <= cosine_limit
               for prior in chosen):
            chosen.append(index)
            if len(chosen) == count:
                return chosen
    raise ValueError(f"only {len(chosen)} views satisfy {minimum_angle_deg}° separation")


def _view_boards(candidates: Path, ids: list[str], counts: dict[str, int],
                 output_dir: Path) -> list[Path]:
    """Five full-resolution candidate panels per board for GPT-6 Astra."""
    output_dir.mkdir(parents=True, exist_ok=True)
    boards = []
    for start in range(0, len(ids), 5):
        batch = ids[start:start + 5]
        board = Image.new("RGB", (1024, 1635), "white")
        draw = ImageDraw.Draw(board)
        for index, view_id in enumerate(batch):
            image = Image.open(candidates / view_id / "depth.png").convert("RGB")
            x, y = (index % 2) * 512, (index // 2) * 545
            draw.text((x + 12, y + 6),
                      f"{view_id}  partial depth  visible points={counts[view_id]}",
                      fill="black")
            board.paste(image.resize((512, 512), Image.Resampling.NEAREST),
                        (x, y + 30))
        path = output_dir / f"candidate_depth_board_{start//5:02d}.png"
        board.save(path)
        boards.append(path)
    return boards


def prepare(args: argparse.Namespace) -> None:
    root = args.output_root.resolve()
    partial = args.partial.resolve()
    if getattr(args, 'world_up', None) is not None and args.camera_source is not None:
        raise ValueError('a fixed saved camera cannot be overridden by world_up')
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
        if (source_camera / "camera.json").is_file():
            camera_source["camera_json_sha256"] = _hash(source_camera / "camera.json")
    else:
        candidates = agent_dir / "candidates"
        cfg = Munch.fromDict(yaml.safe_load(args.config.read_text(encoding="utf-8")))
        if getattr(args, 'world_up', None) is not None:
            cfg.camera_world_up = list(args.world_up)
        cfg.paths.output_dir = str(candidates)
        cfg.paths.data_dir = str(partial.parent)
        cfg.paths.models_dir = str(args.models_root.resolve())
        camera_geometry = {}
        if args.view_candidates == 20:
            editor = DepthPrompting(cfg)
            points, colors = load_partial(partial)
            framing = editor.frame_observed_bounds(points)
            xyz = torch.from_numpy(points).to(editor.device)
            rgb = torch.from_numpy(colors).to(editor.device)
            try:
                viewpoints = editor._fibonacci_viewpoints()
                sample_count = min(int(cfg.downsample_num), len(points))
                sample_ids = fpsample.fps_sampling(points, sample_count).astype(np.int64)
                sample = xyz[torch.as_tensor(sample_ids, dtype=torch.long,
                                             device=editor.device)]
                visible_counts = editor._visible_indices(
                    sample, viewpoints, float(cfg.removal_radius),
                ).sum(dim=1).cpu().numpy()
                chosen_indices = select_diverse_view_indices(
                    viewpoints - np.asarray(framing['target']), visible_counts, count=20,
                    minimum_angle_deg=args.minimum_view_angle,
                )
                view_ids = [f"view_{index:03d}" for index in chosen_indices]
                counts = {view_id: int(visible_counts[index])
                          for view_id, index in zip(view_ids, chosen_indices)}
                for view_id, index in zip(view_ids, chosen_indices):
                    editor.save_depth_observation(
                        xyz, view_id, rgb,
                        viewpoint_override=viewpoints[index],
                        viewpoint_is_source_camera=False,
                    )
                    geometry = {'eye': viewpoints[index].tolist(), **framing}
                    if getattr(args, 'world_up', None) is not None:
                        up = np.asarray(args.world_up, dtype=float)
                        up /= np.linalg.norm(up)
                        direction = viewpoints[index] - np.asarray(framing['target'])
                        geometry['world_up'] = up.tolist()
                        geometry['elevation_degrees'] = float(np.degrees(np.arcsin(np.clip(
                            direction @ up / np.linalg.norm(direction), -1, 1))))
                    camera_geometry[view_id] = geometry
            finally:
                editor.close()
            _write(agent_dir / "view_ranking.json", {
                "method": "fibonacci_visible_point_count_diverse_top20",
                "ground_truth_used": False,
                "fibonacci_view_count": len(viewpoints),
                "scored_partial_points": sample_count,
                "minimum_angle_deg": args.minimum_view_angle,
                "ranked_view_ids": view_ids,
                "visible_counts": counts,
                "all_visible_counts": visible_counts.tolist(),
                "all_viewpoints": viewpoints.tolist(),
                "camera_geometry": camera_geometry,
            })
            board = _view_boards(candidates, view_ids, counts, agent_dir)
        else:
            if not (camera / "depth.png").is_file():
                command = [sys.executable, str(ROOT / "scripts" / "run_semantic_stage.py"),
                           "--output-root", str(root / "inputs" / "camera"),
                           "--partial-root", str(partial.parent), "--samples", args.sample,
                           "--depth-only"]
                subprocess.run(command, check=True, cwd=ROOT)
            view_ids = [f"view_{index:02d}" for index in range(4)]
            _camera_files(camera, candidates / view_ids[0])
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
            camera_geometry=camera_geometry,
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
    if partial != partial_input.resolve():
        shutil.copy2(partial, partial_input)
    prompt_file = agent_dir / "round_00_prompt.txt"
    prompt_file.write_text(result["decision"]["prompt"].strip() + "\n", encoding="utf-8")
    state = {
        "schema": "compagent.prior_agent.v1", "sample": args.sample,
        "ground_truth_used": False, "object_description": args.object_description,
        "input_partial": str(partial_input), "input_partial_sha256": _hash(partial_input),
        "view_candidates": view_candidates, "camera_source": camera_source,
        "selected_view": selected, "selected_depth": str(camera / "depth.png"),
        "camera_dir": str(camera),
        "view_board": [str(path) for path in board] if isinstance(board, list) else str(board),
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
    if index >= 16:
        raise ValueError("maximum sixteen Image Gen reviews per run")
    review_dir = root / "prior_agent" / f"round_{index:02d}"
    review_dir.mkdir(parents=True, exist_ok=True)
    candidate_copy = review_dir / "imagegen_candidate.png"
    shutil.copy2(candidate, candidate_copy)
    prompt_path = Path(state["current_prompt_file"])
    candidate_sha256 = _hash(candidate_copy)
    for past_review in reversed(state["reviews"]):
        if past_review.get("candidate_sha256") == candidate_sha256:
            prompt_path = Path(past_review["prompt_file"])
            break
    else:
        generation_path = root / "generation.json"
        if generation_path.is_file():
            generation = json.loads(generation_path.read_text(encoding="utf-8"))
            if generation.get("semantic_sha256") == candidate_sha256:
                prompt_path = Path(generation["prompt_file"])
    with Image.open(state["selected_depth"]) as saved_depth:
        if saved_depth.width != saved_depth.height:
            raise ValueError("saved depth must have a square camera canvas")
        comparison_resolution = saved_depth.width
    command = [sys.executable, str(ROOT / "scripts" / "install_depth_conditioned_semantic.py"),
               "--sample", state["sample"], "--semantic", str(candidate_copy),
               "--depth", state["selected_depth"], "--prompt-file", str(prompt_path),
               "--camera-dir", str(review_dir), "--rmbg-model", str(args.rmbg_model.resolve()),
               "--resolution", str(comparison_resolution),
               "--minimum-depth-coverage", str(args.minimum_depth_coverage),
               "--positive-support-only"]
    audit_run = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    (review_dir / "layout_audit.log").write_text(audit_run.stdout + audit_run.stderr, encoding="utf-8")
    if audit_run.returncode != 0:
        audit_path = review_dir / "semantic_install_manifest.json"
        if audit_path.is_file():
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            if audit.get("passed") is False and audit.get("verification_mode") == "positive_observed_support":
                with Image.open(state["selected_depth"]) as depth_image:
                    next_prompt = _layout_revision(_base_completion_prompt(root),
                                                   audit, depth_image.size)
                next_path = root / "prior_agent" / f"review_{index:02d}_next_prompt.txt"
                next_path.write_text(next_prompt + "\n", encoding="utf-8")
                state["reviews"].append({
                    "candidate": str(candidate_copy),
                    "candidate_sha256": _hash(candidate_copy),
                    "prompt_file": str(prompt_path),
                    "layout_audit": str(audit_path),
                    "decision": {"action": "REVISE", "reason":
                                 "Observed depth support does not align with the generated foreground"},
                    "accepted": False, "human_candidate_feedback": args.human_feedback,
                })
                state["current_prompt_file"] = str(next_path)
                _write(state_path, state)
                print(json.dumps({"accepted": False, "audit_passed": False,
                                  "next_prompt_file": str(next_path),
                                  "depth_coverage": audit["depth_coverage"]},
                                 ensure_ascii=False, indent=2))
                return
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
        depth_interpretation=state.get("depth_interpretation", {}).get("decision"),
        human_feedback=state.get("depth_interpretation_feedback", ""),
        candidate_feedback=args.human_feedback,
    )
    decision = result["decision"]
    accepted = bool(audit["passed"] and decision["action"] == "ACCEPT"
                    and decision["pose_and_orientation_match"]
                    and decision["image_plane_orientation_match"]
                    and decision["front_rear_axis_match"]
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
           "decision": result, "accepted": accepted,
           "human_candidate_feedback": args.human_feedback}
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
        next_path = root / "prior_agent" / f"review_{index:02d}_next_prompt.txt"
        correction = decision["next_prompt"].strip()
        base = compose_depth_edit_prompt(
            object_description=state["object_description"],
        )
        # After repeated semantic failures, the original interpretation may
        # itself be misleading. Keep the validated depth sentence and latest
        # observed correction, without preserving a conflicting old hint.
        retry_base = base if index >= 2 else _base_completion_prompt(root)
        revised = (correction if correction.startswith(base) else
                   retry_base + "\n请修正上一轮图像的具体问题：" + correction)
        next_path.write_text(revised + "\n", encoding="utf-8")
        state["current_prompt_file"] = str(next_path)
    _write(state_path, state)
    print(json.dumps({"accepted": accepted, "audit_passed": audit["passed"],
                      "decision": result["decision"],
                      "next_prompt_file": None if accepted else state["current_prompt_file"]},
                     ensure_ascii=False, indent=2))


def enrich(args: argparse.Namespace) -> None:
    """Add a grounded depth-order sentence before generating a candidate."""
    root = args.output_root.resolve()
    state_path = root / "prior_agent" / "prior_agent_manifest.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state["reviews"] or state["accepted"] is not None:
        raise ValueError("depth interpretation must precede candidate review")
    camera_context = ""
    camera_json = Path(state["selected_depth"]).with_name("camera.json")
    if camera_json.is_file():
        metadata = json.loads(camera_json.read_text(encoding="utf-8"))
        if all(key in metadata for key in ("eye", "target", "world_up")):
            direction = np.asarray(metadata["eye"], dtype=np.float64) - np.asarray(
                metadata["target"], dtype=np.float64,
            )
            up = np.asarray(metadata["world_up"], dtype=np.float64)
            if direction.shape == (3,) and up.shape == (3,) and np.linalg.norm(direction) > 0 and np.linalg.norm(up) > 0:
                elevation = math.degrees(math.asin(float(np.clip(
                    direction @ up / (np.linalg.norm(direction) * np.linalg.norm(up)),
                    -1.0, 1.0,
                ))))
                side = "above" if elevation > 3 else "below" if elevation < -3 else "near the horizon of"
                camera_context = (f"The saved acquisition camera is {side} the object "
                                  f"relative to its recorded world-up axis "
                                  f"(signed elevation {elevation:.1f} degrees).")
    interpretation_path = root / 'prior_agent' / 'depth_interpretation_raw.json'
    review_context = {}
    source_audit = root / 'source_audit.json'
    if source_audit.exists():
        prior_audit = json.loads(source_audit.read_text())
        audit_decision = prior_audit['decision']
        if (audit_decision['action'] == 'REGENERATE'
                and audit_decision['selected_view'] == state['selected_view']
                and not state.get('view_refresh_provenance')):
            review_context = {key: audit_decision[key] for key in
                              ('depth_landmark_order', 'reason', 'repair_hint', 'uncertainty')}
            review_context['source_audit_sha256'] = _hash(source_audit)
    interpretation_inputs = {'depth_sha256': _hash(Path(state['selected_depth'])),
                             'model': args.model, 'prompt_version': PROMPT_VERSION,
                             'feedback': args.feedback, 'camera_context': camera_context,
                             'same_view_machine_review': review_context,
                             'object_description': state['object_description']}
    cached = json.loads(interpretation_path.read_text()) if interpretation_path.exists() else {}
    if cached.get('inputs') == interpretation_inputs:
        result = cached['result']
    else:
        result = PriorGenerationAgent(args.model).interpret_depth(
            depth=Path(state["selected_depth"]),
            object_description=state["object_description"],
            feedback=args.feedback,
            camera_context=camera_context,
            review_context=review_context,
        )
        _write(interpretation_path, {'inputs': interpretation_inputs, 'result': result})
    hint = result["decision"]["imagegen_hint"].strip()
    count_guard = result["decision"]["count_guard"].strip()
    facing_cue = result["decision"]["facing_visual_cue"].strip()
    if not hint:
        raise ValueError("depth interpretation needs one concise imagegen_hint")
    count_guard_omitted = len(count_guard) > 100
    if count_guard_omitted:
        # The semantic hint already carries the salient part counts. An
        # overlong extra guard adds prose without new evidence.
        count_guard = ""
    framing_hint = ""
    if getattr(args, "include_depth_framing", False):
        with Image.open(state["selected_depth"]) as source_depth:
            gray = np.asarray(source_depth.convert("L"))
        yy, xx = np.nonzero(gray > 0)
        if len(xx) < 100:
            raise ValueError("too few observed pixels for a framing hint")
        height, width = gray.shape
        frame = [round(100 * int(xx.min()) / width),
                 round(100 * int(yy.min()) / height),
                 round(100 * (int(xx.max()) + 1) / width),
                 round(100 * (int(yy.max()) + 1) / height)]
        framing_hint = (f"图1可见部分约位于画幅横向{frame[0]}%–{frame[2]}%、"
                        f"纵向{frame[1]}%–{frame[3]}%；保持其原位置和尺度，"
                        "缺失部分仍自然补全。黑色扫描缺口不是物体上的洞；"
                        "请生成连续自然的表面，不要复制点云颗粒纹理。")
    prompt = compose_depth_edit_prompt(
        object_description=state["object_description"],
        depth_relation_hint=" ".join(part for part in (hint, count_guard, facing_cue,
                                                        framing_hint)
                                     if part),
    )
    base = compose_depth_edit_prompt(object_description=state["object_description"])
    hint_truncated = False
    if len(prompt) - len(base) > 480:
        count_guard = ""
        count_guard_omitted = True
        prompt = compose_depth_edit_prompt(
            object_description=state["object_description"],
            depth_relation_hint=" ".join(part for part in (hint, facing_cue,
                                                            framing_hint) if part),
        )
    if len(prompt) - len(base) > 480:
        # Never cut a semantic direction halfway through a sentence. Ask the
        # same model for a compact expression grounded in the original depth.
        compact_schema = {'type':'object','properties':{'hint':{'type':'string'}},
                          'required':['hint'],'additionalProperties':False}
        compact_payload = {'task':'express_supported_depth_constraints_concisely',
                           'depth_interpretation':result['decision'],
                           'policy':'Write one or two complete Chinese sentences, at most 200 characters. Preserve supported image-plane orientation, near/far order, salient part directions and connections. Omit uncertain identities. Do not repeat the base prompt or canvas framing; do not invent new constraints.'}
        compact = PriorGenerationAgent(args.model)._decide(compact_schema,compact_payload,[Path(state['selected_depth'])])
        _write(root/'prior_agent/depth_hint_compaction.json',{'payload':compact_payload,'result':compact})
        hint = compact['decision']['hint'].strip()
        if not hint:
            raise ValueError('empty compact depth hint')
        prompt = compose_depth_edit_prompt(
            object_description=state["object_description"],
            depth_relation_hint=" ".join(part for part in (hint, framing_hint) if part),
        )
    if len(prompt) - len(base) > 480:
        raise ValueError("depth interpretation hint remains too long")
    prompt_path = root / "prior_agent" / "depth_relation_prompt.txt"
    prompt_path.write_text(prompt + "\n", encoding="utf-8")
    state["depth_interpretation"] = result
    state["depth_interpretation_feedback"] = args.feedback
    state["depth_interpretation_camera_context"] = camera_context
    state["depth_interpretation_framing_hint"] = framing_hint
    state["count_guard_omitted_for_length"] = count_guard_omitted
    state["hint_truncated_for_length"] = hint_truncated
    state["current_prompt_file"] = str(prompt_path)
    _write(state_path, state)
    print(json.dumps({"prompt": str(prompt_path), "depth_interpretation": result},
                     ensure_ascii=False, indent=2))


def reselect(args: argparse.Namespace) -> None:
    """Retry an unknown-camera sample from a different saved no-GT view."""
    root = args.output_root.resolve()
    agent_dir = root / "prior_agent"
    state_path = agent_dir / "prior_agent_manifest.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state["accepted"] is not None or not state["view_candidates"]:
        raise ValueError("reselection requires an unaccepted unknown-camera sample")
    if not args.reason.strip():
        raise ValueError("record the no-GT reason for view reselection")
    excluded = {state["selected_view"], *args.exclude_view}
    excluded.update(row["failed_view"] for row in state.get("selection_history", []))
    view_ids = [view_id for view_id in state["view_candidates"] if view_id not in excluded]
    if not view_ids:
        raise ValueError("no untried saved view remains")
    board = state["view_board"]
    ranking_path = agent_dir / 'view_ranking.json'
    camera_geometry = (json.loads(ranking_path.read_text()).get('camera_geometry', {})
                       if ranking_path.exists() else {})
    result = PriorGenerationAgent(args.model).select_view(
        board=[Path(path) for path in board] if isinstance(board, list) else Path(board),
        view_ids=view_ids, object_description=state["object_description"],
        camera_geometry={key: value for key, value in camera_geometry.items() if key in view_ids},
        previous_attempt_feedback=args.reason.strip(),
    )
    selected = result["decision"]["view_id"]
    history = state.setdefault("selection_history", [])
    history.append({"failed_view": state["selected_view"],
                    "reason": args.reason.strip(), "review_count": len(state["reviews"]),
                    "previous_selection": state["selection"],
                    "new_selection": result})
    archive = agent_dir / 'selection_revisions' / f'attempt_{len(history):02d}'
    archive.mkdir(parents=True, exist_ok=False)
    _write(archive / 'prior_state.json', state)
    shutil.copytree(Path(state['camera_dir']), archive / 'selected_camera')
    _camera_files(Path(state["view_candidates"][selected]).parent,
                  Path(state["camera_dir"]))
    for path in agent_dir.glob("round_[0-9][0-9]"):
        if path.is_dir():
            shutil.move(str(path), str(archive / path.name))
    for path in agent_dir.glob("review_*_next_prompt.txt"):
        shutil.move(str(path), str(archive / path.name))
    for name in ("depth_relation_prompt.txt",):
        if (agent_dir / name).exists():
            shutil.move(str(agent_dir / name), str(archive / name))
    if (agent_dir / 'generations').exists():
        shutil.move(str(agent_dir / 'generations'), str(archive / 'generations'))
    for name in ("semantic.png", "generation.json"):
        if (root / name).exists():
            shutil.move(str(root / name), str(archive / name))
    state["selection"] = result
    state["selected_view"] = selected
    state["reviews"] = []
    state["current_prompt_file"] = str(agent_dir / "round_00_prompt.txt")
    (agent_dir / 'round_00_prompt.txt').write_text(
        compose_depth_edit_prompt(object_description=state['object_description']) + '\n')
    for key in ("depth_interpretation", "depth_interpretation_feedback",
                "depth_interpretation_camera_context", "depth_interpretation_framing_hint",
                "count_guard_omitted_for_length", "hint_truncated_for_length"):
        state.pop(key, None)
    _write(state_path, state)
    coordinate_path = root / 'coordinate_refresh.json'
    if coordinate_path.exists():
        coordinate = json.loads(coordinate_path.read_text())
        coordinate.update(new_view=selected, new_depth_sha256=_hash(Path(state['selected_depth'])))
        _write(coordinate_path, coordinate)
    print(json.dumps({"selected_view": selected, "failed_view": history[-1]["failed_view"],
                      "reason": args.reason, "selected_depth": state["selected_depth"]},
                     ensure_ascii=False))


def refresh_views(args: argparse.Namespace) -> None:
    """Rebuild unaccepted synthetic views from observed bounds, preserving provenance."""
    root = args.output_root.resolve()
    state_path = root / 'prior_agent/prior_agent_manifest.json'
    state = json.loads(state_path.read_text())
    if state.get('accepted') or state.get('camera_source'):
        raise ValueError('refresh requires an unaccepted synthetic-camera prior')
    if not args.reason.strip():
        raise ValueError('a no-GT refresh reason is required')
    camera = Path(state['camera_dir'])
    metadata_path = camera / 'camera.json'
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    revisions = root / 'view_revisions'
    index = len(list(revisions.glob('revision_*'))) + 1
    archive = revisions / f'revision_{index:02d}'
    archive.mkdir(parents=True)
    _write(archive / 'refresh_reason.json', {'reason': args.reason, 'ground_truth_used': False,
           'old_selected_view': state['selected_view'], 'new_rule': 'observed_bounds_fov'})
    for source in (root / 'prior_agent', camera, root / 'semantic.png', root / 'generation.json'):
        if source.exists():
            shutil.move(str(source), str(archive / ('camera' if source == camera else source.name)))
    prepare(argparse.Namespace(output_root=root, partial=Path(state['input_partial']),
        sample=state['sample'], object_description=state['object_description'], constraint=[],
        camera_source=None, world_up=metadata.get('world_up'), config=args.config,
        models_root=args.models_root, model=args.model, view_candidates=20, minimum_view_angle=25.0))
    updated = json.loads(state_path.read_text())
    updated['view_refresh_provenance'] = str(archive / 'refresh_reason.json')
    _write(state_path, updated)
    coordinate_path = root / 'coordinate_refresh.json'
    if coordinate_path.exists():
        coordinate = json.loads(coordinate_path.read_text())
        coordinate.update(new_view=updated['selected_view'],
                          new_depth_sha256=_hash(Path(updated['selected_depth'])))
        _write(coordinate_path, coordinate)


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
    prep.add_argument("--model", default="gpt-6-astra")
    prep.add_argument("--world-up", nargs=3, type=float,
                      help="Declared physical up in input coordinates for synthetic candidate cameras; never infer from GT.")
    prep.add_argument("--view-candidates", type=int, choices=(4, 20), default=4,
                      help="Use 20 diverse high-coverage Fibonacci views for unknown cameras")
    prep.add_argument("--minimum-view-angle", type=float, default=25.0)
    rev = commands.add_parser("review")
    rev.add_argument("--candidate", type=Path, required=True)
    rev.add_argument("--output-root", type=Path, required=True)
    rev.add_argument("--rmbg-model", type=Path, default=ROOT / "models" / "RMBG-2.0")
    rev.add_argument("--moge-model", type=Path, default=ROOT / "models" / "moge-2-vitl" / "model.pt")
    rev.add_argument("--model", default="gpt-6-astra")
    rev.add_argument("--minimum-depth-coverage", type=float, default=0.65,
                     help="Tolerant partial-scan foreground support; semantic review remains required")
    rev.add_argument("--human-feedback", default="",
                     help="Verbatim human observation about this candidate, if any")
    insight = commands.add_parser("enrich")
    insight.add_argument("--output-root", type=Path, required=True)
    insight.add_argument("--feedback", default="")
    insight.add_argument("--model", default="gpt-6-astra")
    insight.add_argument("--include-depth-framing", action="store_true",
                         help="Append approximate observed canvas box from partial depth")
    retry_view = commands.add_parser("reselect")
    retry_view.add_argument("--output-root", type=Path, required=True)
    retry_view.add_argument("--reason", required=True)
    retry_view.add_argument("--exclude-view", action="append", default=[])
    retry_view.add_argument("--model", default="gpt-6-astra")
    refresh = commands.add_parser('refresh-views')
    refresh.add_argument('--output-root', type=Path, required=True)
    refresh.add_argument('--reason', required=True)
    refresh.add_argument('--config', type=Path, default=ROOT / 'configs/mainline_redwood.yaml')
    refresh.add_argument('--models-root', type=Path, default=ROOT / 'models')
    refresh.add_argument('--model', default='gpt-6-astra')
    args = parser.parse_args()
    {"prepare": prepare, "review": review, "enrich": enrich,
     "reselect": reselect, 'refresh-views': refresh_views}[args.command](args)


if __name__ == "__main__":
    main()
