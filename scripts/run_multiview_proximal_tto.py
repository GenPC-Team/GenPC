#!/usr/bin/env python3
"""Run multi-view proximal predictor-corrector TTO on ordered carriers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.multiview_partial_evidence import load_manifest_projectors
from src.multiview_partial_correspondence import save_virtual_overlay_board
from src.multiview_proximal_tto import MultiViewProximalTTOConfig, optimize_multiview_proximal_posterior
from src.pointcloud_io import jsonable, load_points, write_compare, write_points


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--predictor", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--multiview-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--outer-rounds", type=int, default=4)
    parser.add_argument("--propagation-spacing-multiplier", type=float, default=7.0)
    parser.add_argument("--propagation-motion-multiplier", type=float, default=1.0)
    parser.add_argument("--maximum-propagation-diagonal-ratio", type=float, default=.012)
    parser.add_argument("--support-residual-quantile", type=float, default=.50)
    args = parser.parse_args()

    reference = load_points(args.reference)
    predictor = load_points(args.predictor)
    partial = load_points(args.partial)
    views = load_manifest_projectors(args.multiview_manifest, resolution=512)
    config = MultiViewProximalTTOConfig(
        outer_rounds=int(args.outer_rounds),
        propagation_spacing_multiplier=float(args.propagation_spacing_multiplier),
        propagation_motion_multiplier=float(args.propagation_motion_multiplier),
        maximum_propagation_diagonal_ratio=float(args.maximum_propagation_diagonal_ratio),
        support_residual_quantile=float(args.support_residual_quantile),
    )
    result, trace = optimize_multiview_proximal_posterior(
        reference, partial, predictor, views, config=config,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_points(args.output_dir / "registered_prior_100k.ply", reference)
    write_points(args.output_dir / "posterior_multiview_tto_100k.ply", result)
    write_compare(args.output_dir / "partial_gray_posterior_multiview_tto_red.ply", partial, result)
    save_virtual_overlay_board(
        args.output_dir / "posterior_multiview_tto_views.png",
        partial, result, frame_points=reference, views=6, resolution=384,
    )
    (args.output_dir / "multiview_tto_report.json").write_text(
        json.dumps(jsonable({
            "inputs": {
                "reference": str(args.reference.resolve()),
                "predictor": str(args.predictor.resolve()),
                "partial": str(args.partial.resolve()),
                "multiview_manifest": str(args.multiview_manifest.resolve()),
            },
            "config": config.__dict__,
            "trace": trace,
        }), indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(jsonable({
        "output_dir": str(args.output_dir.resolve()),
        "rounds": len(trace),
        "accepted_rounds": sum(bool(row.get("accepted")) for row in trace),
        "last": trace[-1] if trace else None,
    }), indent=2))


if __name__ == "__main__":
    main()
