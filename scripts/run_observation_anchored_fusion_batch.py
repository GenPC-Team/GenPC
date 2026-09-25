#!/usr/bin/env python3
"""Run the fixed observation-anchored fusion over independent samples."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _input_path(root: Path, template: str, sample: str) -> Path:
    return root / template.format(sample=sample)


def _input_with_fallback(root: Path, primary: str, fallback: str | None,
                         sample: str) -> Path:
    path = _input_path(root, primary, sample)
    if path.is_file() or not fallback:
        return path
    candidate = _input_path(root, fallback, sample)
    return candidate if candidate.is_file() else path


def _run_one(root: Path, output_root: Path, final_root: Path, sample: str,
             *, posterior_template: str, partial_template: str,
             manifest_template: str, color_template: str | None,
             posterior_fallback_template: str | None, mode: str) -> dict:
    posterior = _input_with_fallback(
        root, posterior_template, posterior_fallback_template, sample,
    )
    partial = _input_path(root, partial_template, sample)
    manifest = _input_path(root, manifest_template, sample)
    color_source = (
        _input_path(root, color_template, sample) if color_template else None
    )
    required = (posterior, partial, manifest) + (
        (color_source,) if color_source is not None else ()
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"{sample}: missing inputs: {missing}")
    output = output_root / sample
    output.mkdir(parents=True, exist_ok=True)
    log = output / "stage.log"
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_observation_anchored_fusion.py"),
        "--posterior", str(posterior),
        "--partial", str(partial),
        "--multiview-manifest", str(manifest),
        "--output-dir", str(output),
        "--mode", str(mode),
    ]
    if color_source is not None:
        command.extend(("--carrier-colors-from", str(color_source)))
    with log.open("w", encoding="utf-8") as handle:
        result = subprocess.run(
            command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, text=True,
        )
    if result.returncode:
        raise RuntimeError(f"{sample}: fusion failed; see {log}")
    prediction = output / "observation_anchored_fused_100k.ply"
    destination = final_root / sample / "complete_100k.ply"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(prediction, destination)
    textured_prediction = output / "observation_anchored_fused_100k_pixal_texture.ply"
    textured_destination = final_root / sample / "complete_100k_pixal_texture.ply"
    if textured_prediction.is_file():
        shutil.copyfile(textured_prediction, textured_destination)
    info = json.loads((output / "fusion_info.json").read_text(encoding="utf-8"))
    return {
        "sample_id": sample,
        "status": "complete",
        "prediction": str(prediction.resolve()),
        "canonical_final": str(destination.resolve()),
        "canonical_textured_final": (
            str(textured_destination.resolve()) if textured_destination.is_file() else None
        ),
        "fusion": info["fusion"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--final-root", type=Path)
    parser.add_argument("--samples", nargs="+", required=True)
    parser.add_argument("--sample-workers", type=int, default=2)
    parser.add_argument("--mode", choices=("continuous", "exact"), default="continuous")
    parser.add_argument(
        "--posterior-template", default="posterior/{sample}/posterior_prior_100k.ply",
    )
    parser.add_argument(
        "--posterior-fallback-template",
        help="Optional fallback for accepted sample overrides such as Fox visual-best.",
    )
    parser.add_argument("--partial-template", default="inputs/partial/{sample}.ply")
    parser.add_argument(
        "--manifest-template", default="residuals/{sample}/render/render_manifest.json",
    )
    parser.add_argument(
        "--color-template",
        help="Optional ordered carrier RGB source, e.g. inputs/pixal/{sample}/pixal3d_sampled_100k.ply",
    )
    args = parser.parse_args()
    if args.sample_workers < 1:
        parser.error("--sample-workers must be positive")
    root = args.input_root.resolve()
    output_root = (args.output_root or root / "fusion").resolve()
    final_root = (args.final_root or root / "final").resolve()
    records: list[dict] = []
    with ThreadPoolExecutor(max_workers=int(args.sample_workers)) as executor:
        futures = {
            executor.submit(
                _run_one, root, output_root, final_root, str(sample),
                posterior_template=str(args.posterior_template),
                partial_template=str(args.partial_template),
                manifest_template=str(args.manifest_template),
                color_template=(str(args.color_template) if args.color_template else None),
                posterior_fallback_template=(
                    str(args.posterior_fallback_template)
                    if args.posterior_fallback_template else None
                ),
                mode=str(args.mode),
            ): str(sample)
            for sample in args.samples
        }
        for future in as_completed(futures):
            sample = futures[future]
            try:
                record = future.result()
                print(f"[complete] {sample}", flush=True)
            except Exception as error:
                record = {"sample_id": sample, "status": "failed", "error": str(error)}
                print(f"[failed] {sample}: {error}", flush=True)
            records.append(record)
    records.sort(key=lambda item: item["sample_id"])
    manifest = {
        "method": (
            "continuous_multiview_observation_fusion"
            if args.mode == "continuous"
            else "four_view_observation_anchored_carrier_fusion"
        ),
        "ground_truth_used": False,
        "point_concatenation_used": False,
        "input_root": str(root),
        "output_root": str(output_root),
        "final_root": str(final_root),
        "mode": str(args.mode),
        "input_templates": {
            "posterior": str(args.posterior_template),
            "posterior_fallback": (
                str(args.posterior_fallback_template)
                if args.posterior_fallback_template else None
            ),
            "partial": str(args.partial_template),
            "manifest": str(args.manifest_template),
            "colors": str(args.color_template) if args.color_template else None,
        },
        "samples": records,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "batch_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    if any(record["status"] == "failed" for record in records):
        raise SystemExit("one or more fusion samples failed")


if __name__ == "__main__":
    main()
