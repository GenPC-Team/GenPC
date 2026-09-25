#!/usr/bin/env python3
"""Carrier-preserving post-deformation density compensation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pointcloud_io import load_points, write_compare, write_points
from src.strain_aware_densification import StrainDensificationConfig, densify_stretched_surface


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--deformed", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--partial", type=Path)
    parser.add_argument("--strain-quantile", type=float, default=.92)
    parser.add_argument("--minimum-stretch", type=float, default=1.80)
    parser.add_argument("--maximum-segment-stretch", type=float, default=1.35)
    parser.add_argument("--maximum-new-point-ratio", type=float, default=.25)
    args = parser.parse_args()
    dense, report = densify_stretched_surface(
        load_points(args.reference), load_points(args.deformed),
        config=StrainDensificationConfig(
            strain_quantile=float(args.strain_quantile),
            minimum_stretch=float(args.minimum_stretch),
            maximum_segment_stretch=float(args.maximum_segment_stretch),
            maximum_new_point_ratio=float(args.maximum_new_point_ratio),
        ),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_points(args.output_dir / "posterior_prior_dense.ply", dense)
    if args.partial is not None:
        write_compare(args.output_dir / "partial_gray_posterior_dense_red.ply", load_points(args.partial), dense)
    (args.output_dir / "densification_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
