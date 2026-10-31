#!/usr/bin/env python3
"""Apply the existing continuous four-view fusion after a frozen refine batch.

This wrapper does not change either geometry solver.  It resolves each refined
carrier and its *same-sample* physical observation, then records a resumable
one-to-one input/output manifest.  GT is never opened here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
FUSION = ROOT / "scripts" / "run_observation_anchored_fusion.py"


def _pilot(value: str) -> tuple[str, Path]:
    key, separator, path = value.partition("=")
    if separator != "=" or ":" not in key or not path:
        raise argparse.ArgumentTypeError("expected DATASET:SAMPLE=/absolute/output.ply")
    return key, Path(path)


def _ply_vertices(path: Path) -> int:
    with path.open("rb") as handle:
        header = handle.read(4096).split(b"end_header", 1)[0]
    match = re.search(rb"^element vertex (\d+)$", header, re.MULTILINE)
    if match is None:
        raise ValueError(f"cannot read PLY vertex count: {path}")
    return int(match.group(1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-index", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--pilot", type=_pilot, action="append", default=[],
                        help="Completed excluded GPT pilot DATASET:SAMPLE=PLY")
    parser.add_argument("--only", action="append", default=[],
                        help="Limit to DATASET:SAMPLE; repeat for a focused test")
    args = parser.parse_args()
    pilots = dict(args.pilot)
    only = set(args.only)
    batch = json.loads(args.agent_index.read_text(encoding="utf-8"))
    if batch.get("decision_backend") != "gpt":
        parser.error("this wrapper requires a GPT refine batch index")
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "fusion_batch_index.json"
    records: list[dict] = []
    for row in batch["samples"]:
        key = f"{row['dataset']}:{row['sample']}"
        if only and key not in only:
            continue
        posterior = args.agent_index.parent / row["dataset"] / row["sample"] / "agent_selected_posterior_100k.ply"
        if row["status"] == "excluded_existing_experiment":
            posterior = pilots.get(key, posterior)
        elif not row["status"].startswith("completed"):
            records.append({"sample": key, "status": "missing_refine_result"})
            continue
        partial = Path(row["inputs"]["partial"])
        manifest = Path(row["inputs"]["multiview_manifest"])
        colors = Path(row["source"]) / "inputs" / "pixal" / row["sample"] / "pixal3d_sampled_100k.ply"
        required = (posterior, partial, manifest)
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            records.append({"sample": key, "status": "missing_input", "missing": missing})
            continue
        sample_out = output_root / row["dataset"] / row["sample"]
        final = sample_out / "observation_anchored_fused_100k.ply"
        info_path = sample_out / "fusion_info.json"
        if final.is_file() and info_path.is_file():
            info = json.loads(info_path.read_text(encoding="utf-8"))
            expected_inputs = {"posterior": posterior, "partial": partial,
                               "multiview_manifest": manifest}
            if any(info["inputs"].get(name) != str(path.resolve())
                   for name, path in expected_inputs.items()):
                raise ValueError(f"stale fusion input for {key}: {sample_out}")
            status = "completed_existing"
        else:
            sample_out.mkdir(parents=True, exist_ok=True)
            command = [sys.executable, str(FUSION), "--posterior", str(posterior),
                       "--partial", str(partial), "--multiview-manifest", str(manifest),
                       "--output-dir", str(sample_out), "--mode", "continuous"]
            if colors.is_file():
                command.extend(("--carrier-colors-from", str(colors)))
            result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, check=False)
            (sample_out / "run.log").write_text(result.stdout, encoding="utf-8")
            status = "completed" if result.returncode == 0 and final.is_file() and info_path.is_file() else "failed"
        if status.startswith("completed") and _ply_vertices(final) != 100_000:
            status = "invalid_carrier_size"
        textured = sample_out / "observation_anchored_fused_100k_pixal_texture.ply"
        if status.startswith("completed") and colors.is_file() and (not textured.is_file() or _ply_vertices(textured) != 100_000):
            status = "missing_or_invalid_texture"
        record = {"sample": key, "status": status, "posterior": str(posterior.resolve()),
                  "partial": str(partial.resolve()), "manifest": str(manifest.resolve()),
                  "colors": str(colors.resolve()) if colors.is_file() else None,
                  "fused": str(final.resolve()) if final.is_file() else None,
                  "fused_textured": str(textured.resolve()) if textured.is_file() else None}
        records.append(record)
        report_path.write_text(json.dumps({"method": "post_refine_continuous_four_view_fusion",
                                           "ground_truth_used": False, "records": records}, indent=2) + "\n",
                               encoding="utf-8")
        print(f"[{status}] {key}", flush=True)
    report_path.write_text(json.dumps({"method": "post_refine_continuous_four_view_fusion",
                                       "ground_truth_used": False, "records": records}, indent=2) + "\n",
                           encoding="utf-8")
    if any(not item["status"].startswith("completed") for item in records):
        raise SystemExit("one or more fusion cases did not complete")


if __name__ == "__main__":
    main()
