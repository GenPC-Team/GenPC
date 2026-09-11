#!/usr/bin/env python3
"""Experimental opt-in CLIP view selection for Omni Redwood single scans."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.rank_completion_views_clip import main as rank_view


REDWOOD_LABELS = {
    "01027": "bicycle",
    "01032": "potted plant",
    "01382": "open-top trash container",
    "01833": "sports car",
    "07089": "motorcycle",
    "07155": "freestanding sign",
    "08310": "bench",
    "08719": "sofa",
    "09643": "table",
    "09862": "chair",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    manifest = {
        "method": "geometry_pruned_frozen_clip_explainability_view_selection",
        "ground_truth_used": False,
        "model": str(Path(args.model).resolve()),
        "samples": {},
    }
    for object_id, category in REDWOOD_LABELS.items():
        for partial_index in (0, 1):
            sample = f"{object_id}_partial_{partial_index}"
            partial = (
                args.data_root / object_id / "partial_data" / "single_scan"
                / f"partial_{partial_index}.ply"
            )
            output = args.output_root / sample
            ranking = output / "clip_view_ranking.json"
            if not (args.resume and ranking.is_file()):
                rank_view([
                    "--partial", str(partial),
                    "--category", category,
                    "--output-dir", str(output),
                    "--model", str(args.model),
                    "--device", str(args.device),
                    "--batch-size", str(args.batch_size),
                ])
            record = json.loads(ranking.read_text(encoding="utf-8"))
            manifest["samples"][sample] = {
                "category": category,
                "partial": str(partial.resolve()),
                "output": str(output.resolve()),
                "best": record["best"],
            }
            args.output_root.mkdir(parents=True, exist_ok=True)
            (args.output_root / "clip_batch_manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
            )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
