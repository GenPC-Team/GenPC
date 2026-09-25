#!/usr/bin/env python3
"""Render sparse prior-to-partial keypoint motion in saved camera views.

This is a figure-only utility.  It assumes that the reference and posterior
are ordered carriers.  A deformed carrier point is associated with its nearest
partial observation, so arrows start on the registered prior and terminate on
the observed partial surface.  No ground truth or evaluation metric is used.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.multiview_partial_evidence import load_manifest_projectors
from src.pointcloud_io import load_points
from src.zbuffer import zbuffer_depth_with_indices


def _load_colors(path: Path, count: int) -> np.ndarray:
    cloud = o3d.io.read_point_cloud(str(path))
    colors = np.asarray(cloud.colors, dtype=np.float64)
    if len(colors) < count:
        raise ValueError(f"{path} contains {len(colors)} colors, expected at least {count}")
    return np.clip(colors[:count], 0.0, 1.0)


def _render_texture_with_partial(
    points: np.ndarray,
    colors: np.ndarray,
    partial: np.ndarray,
    projector,
) -> np.ndarray:
    uv, depth = projector.project(points)
    _, mask, indices = zbuffer_depth_with_indices(
        uv, depth, projector.image_shape, splat_radius=1,
    )
    image = np.ones((*mask.shape, 3), dtype=np.float64)
    image[mask] = colors[indices[mask]]
    # A light second layer makes the carrier legible without turning it into a
    # dense silhouette; this keeps the point-cloud appearance of the examples.
    image[mask] = 0.90 * image[mask] + 0.10

    partial_uv, partial_depth = projector.project(partial)
    _, partial_mask, _ = zbuffer_depth_with_indices(
        partial_uv, partial_depth, projector.image_shape, splat_radius=0,
    )
    # Blue is reserved for observed partial evidence.  A small amount of the
    # underlying texture remains visible where both clouds overlap.
    partial_blue = np.asarray([0.04, 0.31, 0.92], dtype=np.float64)
    image[partial_mask] = 0.88 * partial_blue + 0.12 * image[partial_mask]
    return image


def _save_view(
    output: Path,
    image: np.ndarray,
    source_uv: np.ndarray,
    target_uv: np.ndarray,
) -> None:
    fig, axis = plt.subplots(figsize=(5.2, 5.2), facecolor="white")
    axis.imshow(image)
    for source, target in zip(source_uv, target_uv):
        delta = target - source
        if float(np.linalg.norm(delta)) < 1.0:
            continue
        axis.annotate(
            "", xy=target, xytext=source,
            arrowprops={
                "arrowstyle": "-|>", "color": "black", "lw": 2.15,
                "mutation_scale": 14, "shrinkA": 8, "shrinkB": 9,
                "connectionstyle": "arc3,rad=0.0",
            },
            zorder=6,
        )
    axis.scatter(
        source_uv[:, 0], source_uv[:, 1], s=115,
        facecolors="#f7f7f7", edgecolors="#343434", linewidths=1.7,
        zorder=7,
    )
    axis.scatter(
        target_uv[:, 0], target_uv[:, 1], s=150,
        facecolors="#f6b2b7", edgecolors="#c75b61", linewidths=1.9,
        zorder=8,
    )
    axis.set_xlim(0, image.shape[1])
    axis.set_ylim(image.shape[0], 0)
    axis.set_aspect("equal")
    axis.axis("off")
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=360, bbox_inches="tight", pad_inches=0.0,
                facecolor="white")
    fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.0,
                facecolor="white")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--posterior", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--textured-carrier", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--keypoint-ids", type=int, nargs="+")
    parser.add_argument("--auto-longest-keypoints", action="store_true")
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--maximum-keypoints-per-view", type=int, default=8)
    parser.add_argument("--minimum-pixel-motion", type=float, default=18.0)
    parser.add_argument("--selection-separation-pixels", type=float, default=34.0)
    parser.add_argument(
        "--candidate-lower-quantile", type=float, nargs=2, action="append",
        metavar=("AXIS", "QUANTILE"),
        help=(
            "Restrict automatic candidates to the union of lower-tail "
            "coordinate quantiles, e.g. '0 0.10' for one geometric extremity."
        ),
    )
    args = parser.parse_args()

    mpl.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    reference = load_points(args.reference)
    posterior = load_points(args.posterior)
    partial = load_points(args.partial)
    if reference.shape != posterior.shape:
        raise ValueError("reference and posterior must be ordered carriers")
    if not args.auto_longest_keypoints and not args.keypoint_ids:
        raise ValueError("provide --keypoint-ids or use --auto-longest-keypoints")
    ids = (
        np.arange(len(reference), dtype=np.int64)
        if args.auto_longest_keypoints
        else np.asarray(args.keypoint_ids, dtype=np.int64)
    )
    candidate_rules = []
    if args.auto_longest_keypoints and args.candidate_lower_quantile:
        candidate_mask = np.zeros(len(reference), dtype=bool)
        for raw_axis, quantile in args.candidate_lower_quantile:
            axis = int(raw_axis)
            if axis not in (0, 1, 2):
                raise ValueError("candidate quantile axis must be 0, 1, or 2")
            if not 0.0 < quantile < 1.0:
                raise ValueError("candidate quantile must lie in (0, 1)")
            threshold = float(np.quantile(reference[:, axis], quantile))
            candidate_mask |= reference[:, axis] <= threshold
            candidate_rules.append({
                "axis": axis,
                "lower_quantile": float(quantile),
                "threshold": threshold,
            })
        ids = np.flatnonzero(candidate_mask)
    if np.any(ids < 0) or np.any(ids >= len(reference)):
        raise ValueError("keypoint id outside the ordered carrier")
    colors = _load_colors(args.textured_carrier, len(reference))
    partial_tree = cKDTree(partial)
    _, partial_indices = partial_tree.query(posterior, k=1, workers=-1)
    partial_targets = partial[np.asarray(partial_indices, dtype=np.int64)]
    projectors = load_manifest_projectors(args.manifest, resolution=args.resolution)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    names = [
        str(item.get("name", f"view_{index + 1}"))
        for index, item in enumerate(manifest["views"])
    ]

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for index, projector in enumerate(projectors[:4]):
        name = names[index] if index < len(names) else f"view_{index + 1}"
        source_uv, source_depth = projector.project(reference[ids])
        target_uv, target_depth = projector.project(partial_targets[ids])
        valid = (
            (source_depth > 0) & (target_depth > 0)
            & (source_uv[:, 0] >= 0) & (source_uv[:, 0] < args.resolution)
            & (source_uv[:, 1] >= 0) & (source_uv[:, 1] < args.resolution)
            & (target_uv[:, 0] >= 0) & (target_uv[:, 0] < args.resolution)
            & (target_uv[:, 1] >= 0) & (target_uv[:, 1] < args.resolution)
        )
        pixel_motion = np.linalg.norm(target_uv - source_uv, axis=1)
        valid &= pixel_motion >= float(args.minimum_pixel_motion)
        valid_ids = np.flatnonzero(valid)
        order = valid_ids[np.argsort(-pixel_motion[valid_ids])]
        selected: list[int] = []
        separation = float(args.selection_separation_pixels)
        for candidate in order:
            if selected:
                chosen = np.asarray(selected, dtype=np.int64)
                source_separation = np.linalg.norm(
                    source_uv[chosen] - source_uv[candidate], axis=1,
                )
                target_separation = np.linalg.norm(
                    target_uv[chosen] - target_uv[candidate], axis=1,
                )
                # Suppress duplicate handles on the same moving structure,
                # while allowing a long structure to contribute another
                # keypoint when its source and endpoint are both separated.
                if np.any((source_separation < separation) | (target_separation < separation)):
                    continue
            selected.append(int(candidate))
            if len(selected) >= int(args.maximum_keypoints_per_view):
                break
        valid_ids = np.asarray(selected, dtype=np.int64)
        path = output / f"keypoint_deformation_{name}.png"
        _save_view(
            path,
            _render_texture_with_partial(reference, colors, partial, projector),
            source_uv[valid_ids], target_uv[valid_ids],
        )
        records.append({
            "name": name,
            "path": str(path.resolve()),
            "visible_keypoints": int(len(valid_ids)),
            "selected_carrier_ids": ids[valid_ids].tolist(),
            "pixel_motion": pixel_motion[valid_ids].tolist(),
        })
    report = {
        "ground_truth_used": False,
        "reference": str(args.reference.resolve()),
        "posterior": str(args.posterior.resolve()),
        "partial": str(args.partial.resolve()),
        "keypoint_selection": (
            "per_view_longest_displacement_with_image_space_suppression"
            if args.auto_longest_keypoints else "explicit_ordered_carrier_ids"
        ),
        "ordered_keypoint_ids": None if args.auto_longest_keypoints else ids.tolist(),
        "candidate_region_rules": candidate_rules,
        "convention": {
            "white_circle": "registered-prior keypoint",
            "pink_circle": "nearest observed partial target",
            "blue_points": "observed partial point cloud",
            "black_arrow": "registered-prior-to-partial displacement",
        },
        "views": records,
    }
    (output / "keypoint_figure_manifest.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
