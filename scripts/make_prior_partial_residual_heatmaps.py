#!/usr/bin/env python3
"""Render per-view residual heatmaps from a registered prior to a partial scan.

The figures are diagnostics only: they use no ground truth and do not alter the
registration or posterior.  A partial point is paired with its closest point on
the registered complete prior in 3-D.  For each saved camera, the pair residual
combines image-plane displacement and depth disagreement and is drawn at the
prior (source) location.  All views share one robust colour scale.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import cKDTree


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.multiview_partial_evidence import load_manifest_projectors
from src.multiview_proximal_tto import _visible_ids
from src.pointcloud_io import load_points


def _robust_extent(points: np.ndarray) -> float:
    lower, upper = np.quantile(points, (0.01, 0.99), axis=0)
    return max(float(np.linalg.norm(upper - lower)), 1e-9)


def _view_record(prior, partial, projector, resolution: int, diagonal: float):
    prior_uv, prior_depth = projector.project(prior)
    partial_uv, partial_depth = projector.project(partial)
    prior_visible = _visible_ids(prior, projector)
    partial_visible = _visible_ids(partial, projector)
    prior_visibility = np.zeros(len(prior), dtype=bool)
    prior_visibility[prior_visible] = True
    partial_visibility = np.zeros(len(partial), dtype=bool)
    partial_visibility[partial_visible] = True

    distance_3d, source_ids = cKDTree(prior).query(partial, k=1, workers=-1)
    source_ids = np.asarray(source_ids, dtype=np.int64)
    valid = partial_visibility & prior_visibility[source_ids]
    valid &= np.isfinite(partial_uv).all(axis=1)
    valid &= np.isfinite(prior_uv[source_ids]).all(axis=1)
    valid &= partial_depth > 0.0
    valid &= prior_depth[source_ids] > 0.0
    valid_ids = np.flatnonzero(valid)

    pixel = np.linalg.norm(
        partial_uv[valid_ids] - prior_uv[source_ids[valid_ids]], axis=1,
    ) / max(float(resolution), 1.0)
    depth = np.abs(
        partial_depth[valid_ids] - prior_depth[source_ids[valid_ids]],
    ) / diagonal
    geometry = distance_3d[valid_ids] / diagonal
    # Pixel/depth terms make the residual camera-specific; the small 3-D term
    # keeps nearly collinear depth mismatches visible.
    residual = np.sqrt(pixel * pixel + depth * depth + 0.25 * geometry * geometry)

    # Several partial samples can vote for one carrier point.  Retain the
    # strongest positive discrepancy so thin structures remain visible.
    source = source_ids[valid_ids]
    order = np.argsort(residual)
    unique_source, reverse = np.unique(source[order], return_index=True)
    selected = order[reverse]
    # np.unique above returns the first in ascending residual order; replace it
    # with a deterministic maximum aggregation.
    maximum = np.zeros(len(unique_source), dtype=np.float64)
    np.maximum.at(maximum, np.searchsorted(unique_source, source), residual)
    return {
        "prior_uv": prior_uv,
        "prior_visible": prior_visible,
        "partial_uv": partial_uv,
        "partial_visible": partial_visible,
        "source_ids": unique_source,
        "residual": maximum,
        "valid_pairs": int(len(valid_ids)),
    }


def _save_panel(record, path: Path, resolution: int, vmax: float) -> None:
    fig, axis = plt.subplots(figsize=(4.0, 4.0), facecolor="#050608")
    axis.set_facecolor("#050608")
    uv = record["prior_uv"]
    visible = record["prior_visible"]
    axis.scatter(
        uv[visible, 0], uv[visible, 1], s=0.75, c="#252A31",
        linewidths=0, alpha=0.72, rasterized=True, zorder=1,
    )
    source_ids = record["source_ids"]
    residual = record["residual"]
    axis.scatter(
        uv[source_ids, 0], uv[source_ids, 1], s=2.2, c=residual,
        cmap="turbo", vmin=0.0, vmax=vmax, linewidths=0,
        alpha=0.98, rasterized=True, zorder=3,
    )
    partial_uv = record["partial_uv"]
    partial_visible = record["partial_visible"]
    axis.scatter(
        partial_uv[partial_visible, 0], partial_uv[partial_visible, 1],
        s=0.42, facecolors="none", edgecolors="#BDEFFF",
        linewidths=0.18, alpha=0.22, rasterized=True, zorder=2,
    )
    axis.set_xlim(0, resolution)
    axis.set_ylim(resolution, 0)
    axis.set_aspect("equal")
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_visible(False)
    fig.subplots_adjust(0, 0, 1, 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".png"), dpi=500, facecolor="#050608", pad_inches=0)
    fig.savefig(path.with_suffix(".pdf"), facecolor="#050608", pad_inches=0)
    plt.close(fig)


def _save_colorbar(path: Path, vmax: float) -> None:
    fig, axis = plt.subplots(figsize=(4.0, 0.32), facecolor="#050608")
    fig.subplots_adjust(left=0.03, right=0.97, top=0.78, bottom=0.42)
    norm = mpl.colors.Normalize(vmin=0.0, vmax=vmax)
    bar = mpl.colorbar.ColorbarBase(axis, cmap="turbo", norm=norm, orientation="horizontal")
    bar.set_ticks((0.0, vmax))
    bar.set_ticklabels(("low", "high"))
    bar.ax.tick_params(colors="white", labelsize=9, length=0, pad=2)
    bar.outline.set_visible(False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".png"), dpi=500, facecolor="#050608", pad_inches=0.02)
    fig.savefig(path.with_suffix(".pdf"), facecolor="#050608", pad_inches=0.02)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=512)
    args = parser.parse_args()

    prior = load_points(args.prior)
    partial = load_points(args.partial)
    projectors = load_manifest_projectors(args.manifest, resolution=args.resolution)
    if len(projectors) != 4:
        raise ValueError("expected exactly four saved diagnostic cameras")
    diagonal = _robust_extent(partial)
    records = [
        _view_record(prior, partial, projector, args.resolution, diagonal)
        for projector in projectors
    ]
    all_residuals = np.concatenate([record["residual"] for record in records])
    vmax = max(float(np.quantile(all_residuals, 0.98)), 1e-6)
    output = args.output_dir.resolve()
    for name, record in zip(("front", "side", "back", "right"), records):
        _save_panel(record, output / f"fox_residual_{name}", args.resolution, vmax)
    _save_colorbar(output / "fox_residual_shared_colorbar", vmax)
    print(output)
    print(f"shared_vmax={vmax:.8f}")
    print("valid_pairs=" + ",".join(str(record["valid_pairs"]) for record in records))


if __name__ == "__main__":
    main()
