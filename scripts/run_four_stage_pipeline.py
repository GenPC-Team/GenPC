#!/usr/bin/env python3
"""Resume the accepted prior through registration, GPT refinement, and fusion.

Stage 1's Image Gen result must first pass ``run_prior_generation_agent.py
review``. This runner keeps each stage and its exact command in one new run
directory and never opens GT or offline metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _vertices(path: Path) -> int:
    with path.open("rb") as handle:
        header = handle.read(4096).split(b"end_header", 1)[0]
    match = re.search(rb"^element vertex (\d+)$", header, re.MULTILINE)
    if not match:
        raise ValueError(f"invalid PLY header: {path}")
    return int(match.group(1))


def _save(path: Path, state: dict) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _stage(name: str, command: list[str], outputs: list[Path], state: dict,
           state_path: Path, *, dry_run: bool, env: dict[str, str]) -> None:
    prior = state["stages"].get(name)
    runtime_env = {key: env.get(key) for key in
                   ("CUDA_VISIBLE_DEVICES", "ATTN_BACKEND", "SPARSE_ATTN_BACKEND",
                    "PIXAL3D_SOURCE", "PYOPENGL_PLATFORM")}
    if prior and prior["command"] != command:
        raise ValueError(f"{name} command changed; use a new run directory")
    reusable = bool(prior and prior["status"] == "complete"
                    and all(path.is_file() and path.stat().st_size for path in outputs))
    if prior and prior["status"] == "complete" and prior.get("runtime_env") != runtime_env:
        # Reusing completed files performs no GPU computation. Keep their
        # original device provenance while allowing a queue to use another
        # GPU for later stages. Backend/source changes still invalidate reuse.
        previous_env = prior.get("runtime_env")
        changed = {key for key in runtime_env
                   if previous_env is None or previous_env.get(key) != runtime_env[key]}
        if not reusable or changed != {"CUDA_VISIBLE_DEVICES"}:
            raise ValueError(f"{name} runtime environment changed; use a new run directory")
    if reusable:
        for path in outputs:
            if path.suffix == ".ply" and _vertices(path) != 100_000:
                raise ValueError(f"{name} has a non-100k carrier: {path}")
        print(f"[reuse] {name}", flush=True)
        return
    print(f"[run] {name}: {' '.join(command)}", flush=True)
    if dry_run:
        return
    log_path = state_path.parent / f"{name}.log"
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                stderr=subprocess.STDOUT, text=True, check=False)
    complete = result.returncode == 0 and all(path.is_file() and path.stat().st_size for path in outputs)
    if complete:
        complete = all(path.suffix != ".ply" or _vertices(path) == 100_000
                       for path in outputs)
    state["stages"][name] = {
        "status": "complete" if complete else "failed", "command": command,
        "runtime_env": runtime_env,
        "returncode": result.returncode, "log": str(log_path),
        "outputs": [str(path) for path in outputs],
    }
    _save(state_path, state)
    if not complete:
        raise RuntimeError(f"{name} failed; see {log_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--models-root", type=Path, default=ROOT / "models")
    parser.add_argument("--gpt-model", default="gpt-6-astra")
    parser.add_argument("--maximum-rounds", type=int, default=6)
    parser.add_argument("--structural-proposal-config", type=Path,
                        help="Optional saved residual-proximal proposal config")
    local_policy = parser.add_mutually_exclusive_group()
    local_policy.add_argument("--planned-local-motion", action="store_true",
                        help="Experimental GPT region planning with up to three guarded local moves")
    local_policy.add_argument("--coherent-local-motion", action="store_true",
                        help="Enable the reviewed local rigid proposal within refinement")
    parser.add_argument("--residual-registration", action="store_true",
                        help="Experimental bounded differentiable Sim(3) after fixed registration")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stop-after", choices=("diagnostics", "fusion"), default="fusion",
                        help="Stop after fixed registration diagnostics when a separate refinement runner follows.")
    args = parser.parse_args()
    root = args.output_root.resolve()
    model_root = args.models_root.resolve()
    prior_path = root / "prior_agent" / "prior_agent_manifest.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    accepted = prior.get("accepted")
    if not accepted:
        raise ValueError("prior generation agent has not accepted an Image Gen candidate")
    sample = prior["sample"]
    camera = root / "inputs" / "camera" / sample
    pixal = root / "inputs" / "pixal" / sample
    partial = root / "inputs" / "partial" / f"{sample}.ply"
    required = [Path(accepted["source_image"]), camera / "depth.png", camera / "camera.pth",
                camera / "img.png", pixal / "gpt_image.png", partial,
                Path(accepted["prompt_file"])]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    if _sha256(Path(accepted["source_image"])) != accepted["source_sha256"]:
        raise ValueError("accepted Image Gen source changed")
    if _sha256(camera / "img.png") != accepted["installed_sha256"]:
        raise ValueError("installed semantic image changed")
    pixal_input = pixal / "gpt_image.png"
    if "pixal_input_sha256" in accepted:
        if _sha256(pixal_input) != accepted["pixal_input_sha256"]:
            raise ValueError("transparent Pixal input changed after review")
        with Image.open(pixal_input) as image:
            alpha_min, alpha_max = image.getchannel("A").getextrema() if image.mode == "RGBA" else (None, None)
            # RMBG may leave the strongest foreground alpha at 254 rather
            # than 255; transparent background and substantial foreground
            # opacity are the actual Pixal input contract.
            if image.mode != "RGBA" or alpha_min != 0 or alpha_max < 128:
                raise ValueError("Pixal input must be the transparent RMBG RGBA image")
    elif _sha256(pixal_input) != accepted["installed_sha256"]:
        # Retain resume support for the earlier 01184 pilot, which used the
        # RGB semantic input and let Pixal run its own RMBG preprocessing.
        raise ValueError("legacy Pixal input differs from the accepted semantic image")
    fingerprints = {str(path): _sha256(path) for path in required}
    options = {"coherent_local_motion": args.coherent_local_motion,
               "residual_registration": args.residual_registration}
    # Omit the disabled new option to preserve existing single-step resumes.
    if args.planned_local_motion:
        options["planned_local_motion"] = True
    state_path = root / "four_stage_pipeline.json"
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["input_fingerprints"] != fingerprints or state["gpt_model"] != args.gpt_model:
            raise ValueError("pipeline inputs/model changed; use a new output root")
        if state.get("options", {key: False for key in options}) != options:
            raise ValueError("pipeline options changed; use a new output root")
    else:
        state = {"schema": "compagent.four_stage_pipeline.v1", "sample": sample,
                 "ground_truth_used": False, "gpt_model": args.gpt_model,
                 "input_fingerprints": fingerprints, "options": options, "stages": {}}
        if not args.dry_run:
            _save(state_path, state)
    env = os.environ.copy()
    env.setdefault("PIXAL3D_SOURCE", str(model_root / "Pixal3D"))
    env.setdefault("PYOPENGL_PLATFORM", "egl")
    # The local genpc interpreter is invoked directly rather than through
    # ``conda activate``, so conda activation variables are not inherited.
    env["ATTN_BACKEND"] = "sdpa"
    env["SPARSE_ATTN_BACKEND"] = "sdpa"
    python = sys.executable
    source_carrier = pixal / "pixal3d_sampled_100k.ply"
    _stage("pixal3d", [python, str(ROOT / "scripts" / "run_pixal3d_gpt_batch.py"),
           "--input-root", str(root / "inputs" / "pixal"),
           "--output-root", str(root / "inputs" / "pixal"), "--ids", sample,
           "--model", str(model_root / "Pixal3D-weights"),
           "--dino", str(model_root / "dinov3-vitl16-pretrain-lvd1689m"),
           "--moge", str(model_root / "moge-2-vitl"),
           "--rmbg", str(model_root / "RMBG-2.0"),
           "--decimation-target", "120000", "--texture-size", "1024"],
           [pixal / "pixal3d.glb", source_carrier,
            pixal / "pixal3d_metadata.json", pixal / "pixal_moge_fp16_observation.npz"],
           state, state_path, dry_run=args.dry_run, env=env)
    registration = root / "registration" / sample / "final" / "camera1_amplified_registered_100k.ply"
    _stage("registration", [python, str(ROOT / "scripts" / "run_fixed_pixal_moge_registration.py"),
           "--samples", sample, "--pixal-root", str(root / "inputs" / "pixal"),
           "--camera-root", str(root / "inputs" / "camera"),
           "--partial-root", str(root / "inputs" / "partial"),
           "--output-root", str(root / "registration"),
           "--moge-model", str(model_root / "moge-2-vitl" / "model.pt"),
           "--rmbg-model", str(model_root / "RMBG-2.0")], [registration],
           state, state_path, dry_run=args.dry_run, env=env)
    manifest = root / "residuals" / sample / "render" / "render_manifest.json"
    _stage("diagnostics", [python, str(ROOT / "scripts" / "run_multiview_diagnostics.py"),
           "--registered-prior", str(registration), "--partial", str(partial),
           "--camera", str(camera / "camera.pth"),
           "--output-dir", str(root / "residuals" / sample)], [manifest],
           state, state_path, dry_run=args.dry_run, env=env)
    if args.stop_after == "diagnostics":
        print(json.dumps({"sample": sample, "stopped_after": "diagnostics",
                          "registration": str(registration), "diagnostics": str(manifest),
                          "dry_run": args.dry_run}, indent=2), flush=True)
        return
    if args.residual_registration:
        residual_dir = root / "registration" / sample / "differentiable_residual"
        residual = residual_dir / "registered_100k.ply"
        _stage("registration_residual", [
            python, str(ROOT / "scripts" / "probe_differentiable_registration.py"),
            "--prior", str(registration), "--partial", str(partial),
            "--camera", str(camera / "camera.pth"),
            "--multiview-manifest", str(manifest), "--output-dir", str(residual_dir),
            "--device", args.device], [residual, residual_dir / "registration_report.json"],
            state, state_path, dry_run=args.dry_run, env=env)
        registration = residual
        # Keep exactly the same four saved audit cameras across this update.
        # The residual tool writes before/after boards in those cameras;
        # refinement and fusion load the new carrier explicitly.
    refined = root / "refinement" / sample / "agent_selected_posterior_100k.ply"
    refine_command = [python, str(ROOT / "scripts" / "run_agentic_posterior.py"),
                      "--prior", str(registration), "--partial", str(partial),
                      "--camera", str(camera / "camera.pth"),
                      "--semantic", str(camera / "img.png"),
                      "--multiview-manifest", str(manifest),
                      "--config-json", str(ROOT / "configs" / "posterior_mainline.json"),
                      "--output-dir", str(root / "refinement" / sample),
                      "--maximum-rounds", str(args.maximum_rounds),
                      "--decision-backend", "gpt", "--gpt-model", args.gpt_model,
                      "--gpt-provider", "codex", "--device", args.device]
    if args.structural_proposal_config is not None:
        if not args.structural_proposal_config.is_file():
            raise FileNotFoundError(args.structural_proposal_config)
        refine_command.extend(("--structural-proposal-config",
                               str(args.structural_proposal_config.resolve())))
    if args.coherent_local_motion:
        refine_command.append("--coherent-local-motion")
    if args.planned_local_motion:
        refine_command.append("--planned-local-motion")
    _stage("refinement", refine_command,
           [refined, root / "refinement" / sample / "agent_trace.json"],
           state, state_path, dry_run=args.dry_run, env=env)
    fused_dir = root / "fusion" / sample
    fused = fused_dir / "observation_anchored_fused_100k.ply"
    _stage("fusion", [python, str(ROOT / "scripts" / "run_observation_anchored_fusion.py"),
           "--posterior", str(refined), "--partial", str(partial),
           "--multiview-manifest", str(manifest), "--output-dir", str(fused_dir),
           "--mode", "continuous", "--carrier-colors-from", str(source_carrier)],
           [fused, fused_dir / "observation_anchored_fused_100k_pixal_texture.ply",
            fused_dir / "fusion_info.json"], state, state_path, dry_run=args.dry_run, env=env)
    print(json.dumps({"sample": sample, "dry_run": args.dry_run,
                      "final": str(fused) if not args.dry_run else None,
                      "pipeline_manifest": str(state_path)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
