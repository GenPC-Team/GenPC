#!/usr/bin/env python3
"""Render a deformation-priority heatmap on the undeformed complete prior."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.multiview_partial_evidence import load_manifest_projectors
from src.multiview_proximal_tto import _visible_ids
from src.pointcloud_io import load_points


def _robust_diagonal(points: np.ndarray) -> float:
    lower, upper = np.quantile(points, (0.01, 0.99), axis=0)
    return max(float(np.linalg.norm(upper - lower)), 1e-9)


def _render(points, values, projector, output: Path, *, resolution: int, vmax: float) -> None:
    uv, _ = projector.project(points)
    visible = _visible_ids(points, projector)
    fig, axis = plt.subplots(figsize=(4.0, 4.0), facecolor="#030507")
    axis.set_facecolor("#030507")
    # Larger low-alpha underlay gives the sparse carrier a continuous surface
    # appearance while preserving the actual point samples in the foreground.
    axis.scatter(
        uv[visible, 0], uv[visible, 1], s=3.0, c=values[visible],
        cmap="turbo", vmin=0.0, vmax=vmax, linewidths=0,
        alpha=0.30, rasterized=True,
    )
    axis.scatter(
        uv[visible, 0], uv[visible, 1], s=0.95, c=values[visible],
        cmap="turbo", vmin=0.0, vmax=vmax, linewidths=0,
        alpha=1.0, rasterized=True,
    )
    axis.set_xlim(0, resolution)
    axis.set_ylim(resolution, 0)
    axis.set_aspect("equal")
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_visible(False)
    fig.subplots_adjust(0, 0, 1, 1)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output.with_suffix(".png"), dpi=500, facecolor="#030507", pad_inches=0)
    fig.savefig(output.with_suffix(".pdf"), facecolor="#030507", pad_inches=0)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--clip-quantile", type=float, default=0.99)
    args = parser.parse_args()

    before = load_points(args.before)
    after = load_points(args.after)
    partial = load_points(args.partial)
    if before.shape != after.shape:
        raise ValueError("before and after must be the same ordered carrier")
    projectors = load_manifest_projectors(args.manifest, resolution=args.resolution)
    if len(projectors) != 4:
        raise ValueError("expected exactly four saved diagnostic views")

    displacement = np.linalg.norm(after - before, axis=1) / _robust_diagonal(partial)
    vmax = max(float(np.quantile(displacement, args.clip_quantile)), 1e-8)
    output = args.output_dir.resolve()
    for name, projector in zip(("front", "side", "back", "right"), projectors):
        _render(
            before, displacement, projector, output / f"fox_deformation_priority_{name}",
            resolution=args.resolution, vmax=vmax,
        )
    np.save(output / "deformation_magnitude_normalized.npy", displacement)
    (output / "scale.txt").write_text(
        f"normalization=robust_partial_diagonal\nclip_quantile={args.clip_quantile}\n"
        f"vmin=0.0\nvmax={vmax:.10f}\n",
        encoding="utf-8",
    )
    print(output)
    print(f"shared_vmax={vmax:.8f}")


if __name__ == "__main__":
    main()
