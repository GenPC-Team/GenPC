#!/usr/bin/env python3
"""Batch the isolated Waymo sparse-ray registration over retained samples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_waymo_sparse_ray_registration import run_case
from src.pointcloud_io import jsonable


def _sheet(records: dict[str, dict], output: Path) -> None:
    cell, label = 420, 54
    board = Image.new("RGB", (2 * cell, len(records) * (cell + label)), "white")
    draw = ImageDraw.Draw(board)
    for row, (sample, record) in enumerate(records.items()):
        folder = Path(record["outputs"]["registered_prior"]).parent
        y = row * (cell + label)
        draw.text((8, y + 8), sample, fill="black")
        columns = (
            ("sparse dense-bridge candidate", "refined_saved_view.png"),
            ("selected no-GT posterior", "selected_saved_view.png"),
        )
        for column, (title, name) in enumerate(columns):
            draw.text((column * cell + 8, y + 28), title, fill="black")
            image = Image.open(folder / name).convert("RGB")
            image.thumbnail((cell, cell))
            x = column * cell + (cell - image.width) // 2
            board.paste(image, (x, y + label + (cell - image.height) // 2))
    output.parent.mkdir(parents=True, exist_ok=True)
    board.save(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mainline-root", type=Path, required=True)
    parser.add_argument("--bridge-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    bridge_infos = sorted(args.bridge_root.glob(
        "registration/*/bridge/two_camera_pixal_moge_info.json"
    ))
    if not bridge_infos:
        raise FileNotFoundError("no bridge inputs found")
    records = {}
    for info in bridge_infos:
        sample = info.parents[1].name
        prior = args.mainline_root / "inputs" / "pixal" / sample / "pixal3d_sampled_100k.ply"
        mainline_candidate = args.mainline_root / "final" / sample / "complete_100k.ply"
        records[sample] = run_case(
            info,
            prior,
            args.output_root / sample,
            mainline_candidate_path=(
                mainline_candidate if mainline_candidate.is_file() else None
            ),
        )
    contact_sheet = args.output_root / "sparse_candidate_vs_selected.png"
    _sheet(records, contact_sheet)
    summary = {
        "method": "waymo_camera_ray_gauge_sparse_partial_to_dense_moge_registration",
        "mainline_modified": False,
        "ground_truth_cd_emd_used": False,
        "samples": records,
    }
    (args.output_root / "batch_manifest.json").write_text(
        json.dumps(jsonable(summary), indent=2), encoding="utf-8",
    )
    print(json.dumps({
        "output_root": str(args.output_root.resolve()),
        "samples": len(records),
        "contact_sheet": str(contact_sheet.resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
