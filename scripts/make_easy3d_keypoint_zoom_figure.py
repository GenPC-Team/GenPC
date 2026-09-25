#!/usr/bin/env python3
"""Render a keypoint-deformation view and a tail zoom with Easy3D spheres.

The point-cloud layers are rendered by Easy3D using ``PointsDrawable::SPHERE``.
Matplotlib only adds the sparse keypoint glyphs, arrows, and zoom frame.  The
saved diagnostic camera is reused exactly, so projected arrows remain aligned
with the 3-D point rendering.  This utility is for paper visualization only;
it does not alter geometry or use ground truth.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.multiview_partial_evidence import load_manifest_projectors
from src.pointcloud_io import load_points


def _view_record(manifest: dict, name: str) -> tuple[int, dict]:
    for index, item in enumerate(manifest.get("views", [])):
        if str(item.get("name", "")).lower() == name.lower():
            return index, item
    raise ValueError(f"view {name!r} is not present in the render manifest")


def _selected_ids(keypoint_manifest: Path, name: str) -> np.ndarray:
    record = json.loads(keypoint_manifest.read_text(encoding="utf-8"))
    for item in record.get("views", []):
        if str(item.get("name", "")).lower() == name.lower():
            return np.asarray(item.get("selected_carrier_ids", []), dtype=np.int64)
    raise ValueError(f"view {name!r} is not present in the keypoint manifest")


def _render_easy3d(
    renderer: Path,
    cloud: Path,
    output: Path,
    pose: np.ndarray,
    fov_degrees: float,
    resolution: int,
    point_size: float,
) -> None:
    position = pose[:3, 3]
    direction = -pose[:3, 2]
    up = pose[:3, 1]
    command = [
        "xvfb-run", "-a", str(renderer), "--single-rgb-camera",
        str(cloud), str(output), str(float(point_size)),
        str(int(resolution)), str(int(resolution)),
        *(str(float(value)) for value in position),
        *(str(float(value)) for value in direction),
        *(str(float(value)) for value in up),
        str(float(fov_degrees)),
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(command, check=True)


def _inside(points: np.ndarray, width: int, height: int) -> np.ndarray:
    return (
        np.isfinite(points).all(axis=1)
        & (points[:, 0] >= 0.0) & (points[:, 0] < width)
        & (points[:, 1] >= 0.0) & (points[:, 1] < height)
    )


def _annotate(
    image: Image.Image,
    source_uv: np.ndarray,
    target_uv: np.ndarray,
    output: Path,
    *,
    rectangle: tuple[float, float, float, float] | None = None,
) -> None:
    width, height = image.size
    figure = plt.figure(figsize=(width / 200.0, height / 200.0), dpi=200)
    axis = figure.add_axes((0.0, 0.0, 1.0, 1.0))
    axis.imshow(image)
    for source, target in zip(source_uv, target_uv):
        if float(np.linalg.norm(target - source)) < 2.0:
            continue
        axis.annotate(
            "", xy=target, xytext=source,
            arrowprops={
                "arrowstyle": "-|>", "color": "black", "lw": 2.2,
                "mutation_scale": 14, "shrinkA": 8, "shrinkB": 9,
                "connectionstyle": "arc3,rad=0.0",
            },
            zorder=6,
        )
    if len(source_uv):
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
    if rectangle is not None:
        x0, y0, x1, y1 = rectangle
        axis.add_patch(plt.Rectangle(
            (x0, y0), x1 - x0, y1 - y0,
            fill=False, edgecolor="#333333", linewidth=2.4, zorder=9,
        ))
    axis.set_xlim(0, width)
    axis.set_ylim(height, 0)
    axis.set_aspect("equal")
    axis.axis("off")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=200, facecolor="white", pad_inches=0.0)
    plt.close(figure)


def _compose(
    main: Path,
    zoom: Path,
    output: Path,
    rectangle: tuple[float, float, float, float],
) -> None:
    left = Image.open(main).convert("RGB")
    right = Image.open(zoom).convert("RGB")
    gap = 72
    border = 4
    canvas = Image.new("RGB", (left.width + gap + right.width, max(left.height, right.height)), "white")
    canvas.paste(left, (0, 0))
    offset_x = left.width + gap
    offset_y = (canvas.height - right.height) // 2
    canvas.paste(right, (offset_x, offset_y))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle(
        (offset_x, offset_y, offset_x + right.width - 1, offset_y + right.height - 1),
        outline="#333333", width=border,
    )
    _, y0, x1, y1 = rectangle
    connector = "#666666"
    draw.line((x1, y0, offset_x, offset_y), fill=connector, width=3)
    draw.line((x1, y1, offset_x, offset_y + right.height - 1), fill=connector, width=3)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--posterior", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--textured-overlay", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--keypoint-manifest", type=Path, required=True)
    parser.add_argument("--renderer", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--view", default="side")
    parser.add_argument(
        "--target-mode", choices=("partial-evidence", "posterior"),
        default="partial-evidence",
        help=(
            "Draw arrows to nearest partial evidence or to the actual final "
            "position of the same ordered posterior carrier slot."
        ),
    )
    parser.add_argument("--point-size", type=float, default=4.0)
    parser.add_argument(
        "--zoom-point-size", type=float,
        help="Easy3D sphere size for the high-resolution zoom render (defaults to point-size).",
    )
    parser.add_argument("--resolution", type=int, default=1400)
    parser.add_argument("--zoom-scale", type=int, default=2)
    parser.add_argument(
        "--annotations-in-zoom-only", action="store_true",
        help="Show only handles whose source and target both lie in the zoom ROI.",
    )
    parser.add_argument(
        "--zoom-box", type=float, nargs=4, default=(0.50, 0.50, 1.00, 1.00),
        metavar=("X0", "Y0", "X1", "Y1"),
        help="Normalized crop in the saved camera image.",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    view_index, view = _view_record(manifest, args.view)
    pose = np.asarray(view["camera_pose"], dtype=np.float64)
    fov = float(manifest["field_of_view_degrees"])
    ids = _selected_ids(args.keypoint_manifest, args.view)

    reference = load_points(args.reference)
    posterior = load_points(args.posterior)
    partial = load_points(args.partial)
    if reference.shape != posterior.shape:
        raise ValueError("reference and posterior must be ordered carriers")
    if np.any(ids < 0) or np.any(ids >= len(reference)):
        raise ValueError("keypoint id outside the ordered carrier")
    if args.target_mode == "partial-evidence":
        _, partial_indices = cKDTree(partial).query(posterior[ids], k=1, workers=-1)
        targets = partial[np.asarray(partial_indices, dtype=np.int64)]
    else:
        targets = posterior[ids]

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    full_base = output / f"fox_{args.view}_easy3d_base.png"
    high_base = output / f"fox_{args.view}_easy3d_base_{args.zoom_scale}x.png"
    _render_easy3d(
        args.renderer, args.textured_overlay, full_base, pose, fov,
        args.resolution, args.point_size,
    )
    high_resolution = int(args.resolution) * int(args.zoom_scale)
    zoom_point_size = (
        float(args.zoom_point_size)
        if args.zoom_point_size is not None else float(args.point_size)
    )
    _render_easy3d(
        args.renderer, args.textured_overlay, high_base, pose, fov,
        high_resolution, zoom_point_size,
    )

    projectors = load_manifest_projectors(args.manifest, resolution=args.resolution)
    source_uv, source_depth = projectors[view_index].project(reference[ids])
    target_uv, target_depth = projectors[view_index].project(targets)
    valid = (
        (source_depth > 0.0) & (target_depth > 0.0)
        & _inside(source_uv, args.resolution, args.resolution)
        & _inside(target_uv, args.resolution, args.resolution)
    )
    source_uv = source_uv[valid]
    target_uv = target_uv[valid]

    x0, y0, x1, y1 = (float(value) for value in args.zoom_box)
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        raise ValueError("zoom-box must be normalized and ordered inside [0, 1]")
    crop_full = np.asarray([
        x0 * args.resolution, y0 * args.resolution,
        x1 * args.resolution, y1 * args.resolution,
    ])
    roi_valid = (
        (source_uv[:, 0] >= crop_full[0]) & (source_uv[:, 0] < crop_full[2])
        & (source_uv[:, 1] >= crop_full[1]) & (source_uv[:, 1] < crop_full[3])
        & (target_uv[:, 0] >= crop_full[0]) & (target_uv[:, 0] < crop_full[2])
        & (target_uv[:, 1] >= crop_full[1]) & (target_uv[:, 1] < crop_full[3])
    )
    full_source = source_uv[roi_valid] if args.annotations_in_zoom_only else source_uv
    full_target = target_uv[roi_valid] if args.annotations_in_zoom_only else target_uv
    full_annotated = output / f"fox_{args.view}_easy3d_keypoints.png"
    _annotate(
        Image.open(full_base).convert("RGB"), full_source, full_target,
        full_annotated, rectangle=tuple(crop_full.tolist()),
    )

    high = Image.open(high_base).convert("RGB")
    crop_high = np.rint(crop_full * int(args.zoom_scale)).astype(np.int64)
    zoom_image = high.crop(tuple(int(value) for value in crop_high))
    high_source = source_uv * int(args.zoom_scale) - crop_high[:2]
    high_target = target_uv * int(args.zoom_scale) - crop_high[:2]
    zoom_valid = (
        _inside(high_source, zoom_image.width, zoom_image.height)
        & _inside(high_target, zoom_image.width, zoom_image.height)
    )
    zoom_annotated = output / f"fox_{args.view}_tail_zoom_easy3d_keypoints.png"
    _annotate(
        zoom_image, high_source[zoom_valid], high_target[zoom_valid],
        zoom_annotated,
    )

    composite = output / f"fox_{args.view}_tail_zoom_easy3d_keypoints_composite.png"
    _compose(full_annotated, zoom_annotated, composite, tuple(crop_full.tolist()))
    record = {
        "ground_truth_used": False,
        "geometry_changed": False,
        "renderer": str(args.renderer.resolve()),
        "impostor": "Easy3D PointsDrawable::SPHERE",
        "point_size": float(args.point_size),
        "zoom_point_size": zoom_point_size,
        "view": args.view,
        "target_mode": args.target_mode,
        "saved_camera_pose": pose.tolist(),
        "field_of_view_degrees": fov,
        "zoom_box_normalized": [x0, y0, x1, y1],
        "annotations_in_zoom_only": bool(args.annotations_in_zoom_only),
        "full_annotation_count": int(len(full_source)),
        "keypoint_ids": ids[valid].tolist(),
        "zoom_keypoints": int(np.count_nonzero(zoom_valid)),
        "outputs": {
            "full": str(full_annotated.resolve()),
            "zoom": str(zoom_annotated.resolve()),
            "composite": str(composite.resolve()),
        },
    }
    (output / "figure_manifest.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
