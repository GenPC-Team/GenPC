#!/usr/bin/env python3
"""Render matching saved-camera projections for refinement review."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.multiview_partial_evidence import load_manifest_projectors
from src.pointcloud_io import load_points
from src.zbuffer import zbuffer_depth_with_indices


def _mask(points: np.ndarray, projector) -> np.ndarray:
    uv, depth = projector.project(points)
    _, mask, _ = zbuffer_depth_with_indices(
        uv, depth, projector.image_shape, splat_radius=1,
    )
    return mask


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--agent", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    partial = load_points(args.partial)
    clouds = {
        "registered": load_points(args.before),
        "fixed_three_rounds": load_points(args.baseline),
        "agent": load_points(args.agent),
    }
    projectors = load_manifest_projectors(args.manifest, resolution=768)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for view_index, projector in enumerate(projectors):
        partial_mask = _mask(partial, projector)
        for name, points in clouds.items():
            prior_mask = _mask(points, projector)
            image = np.full((*projector.image_shape, 3), 255, dtype=np.uint8)
            image[prior_mask] = (226, 56, 54)
            image[partial_mask] = (35, 94, 218)
            image[partial_mask & prior_mask] = (116, 71, 153)
            Image.fromarray(image).save(args.output_dir / f"view_{view_index + 1}_{name}.png")


if __name__ == "__main__":
    main()
