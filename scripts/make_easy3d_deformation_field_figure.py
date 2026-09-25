#!/usr/bin/env python3
"""Render an Easy3D deformation-magnitude map and a local direction field.

The full panel encodes the magnitude of the actual ordered prior-to-posterior
displacement as per-point colour.  The zoom panel overlays spatially uniform,
fixed-length direction glyphs; glyph colour carries magnitude, so a few large
motions cannot dominate the drawing.  Ground truth is never used.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
import numpy as np
from PIL import Image
from plyfile import PlyData, PlyElement
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.multiview_partial_evidence import load_manifest_projectors
from src.multiview_proximal_tto import _median_spacing
from src.pointcloud_io import load_points
from src.zbuffer import zbuffer_depth_with_indices


def _write_rgb(path: Path, points: np.ndarray, rgb: np.ndarray) -> None:
    output = np.empty(
        len(points),
        dtype=[
            ("x", "f4"), ("y", "f4"), ("z", "f4"),
            ("red", "u1"), ("green", "u1"), ("blue", "u1"),
        ],
    )
    output["x"], output["y"], output["z"] = np.asarray(points, np.float32).T
    output["red"], output["green"], output["blue"] = np.asarray(rgb, np.uint8).T
    path.parent.mkdir(parents=True, exist_ok=True)
    PlyData([PlyElement.describe(output, "vertex")], text=False).write(str(path))


def _render(
    renderer: Path,
    cloud: Path,
    output: Path,
    pose: np.ndarray,
    fov: float,
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
        str(float(fov)),
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(command, check=True)


def _view(manifest: dict, name: str) -> tuple[int, dict]:
    for index, item in enumerate(manifest.get("views", [])):
        if str(item.get("name", "")).lower() == name.lower():
            return index, item
    raise ValueError(f"view {name!r} is not present in the render manifest")


def _partial_outline(partial: np.ndarray, projector) -> np.ndarray:
    uv, depth = projector.project(partial)
    _, mask, _ = zbuffer_depth_with_indices(
        uv, depth, projector.image_shape, splat_radius=2,
    )
    mask = ndimage.binary_closing(mask, iterations=2)
    return ndimage.binary_dilation(mask, iterations=1) ^ ndimage.binary_erosion(
        mask, iterations=1,
    )


def _overlay_outline(image: Image.Image, outline: np.ndarray) -> Image.Image:
    array = np.asarray(image.convert("RGB")).copy()
    # Dark royal blue stays distinct from the turbo magnitude palette.
    array[outline] = np.asarray([22, 64, 180], dtype=np.uint8)
    return Image.fromarray(array)


def _field_samples(
    reference: np.ndarray,
    posterior: np.ndarray,
    projector,
    crop: np.ndarray,
    magnitude: np.ndarray,
    *,
    cell: int,
    max_glyphs: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    source, source_depth = projector.project(reference)
    target, target_depth = projector.project(posterior)
    _, visible, indices = zbuffer_depth_with_indices(
        source, source_depth, projector.image_shape, splat_radius=1,
    )
    visible_ids = np.unique(indices[visible])
    valid = np.zeros(len(reference), dtype=bool)
    valid[visible_ids] = True
    x0, y0, x1, y1 = crop
    valid &= (
        (source_depth > 0.0) & (target_depth > 0.0)
        & (source[:, 0] >= x0) & (source[:, 0] < x1)
        & (source[:, 1] >= y0) & (source[:, 1] < y1)
        & (target[:, 0] >= x0) & (target[:, 0] < x1)
        & (target[:, 1] >= y0) & (target[:, 1] < y1)
    )
    motion = np.linalg.norm(target - source, axis=1)
    positive = magnitude[valid & (motion > 2.0)]
    threshold = float(np.quantile(positive, 0.35)) if len(positive) else 0.0
    candidates = np.flatnonzero(valid & (motion > 2.0) & (magnitude >= threshold))
    if not len(candidates):
        return source, target, np.empty(0, dtype=np.int64)
    local = source[candidates] - crop[:2]
    cells = np.floor(local / float(cell)).astype(np.int64)
    key = cells[:, 1] * 10000 + cells[:, 0]
    # One high-magnitude vector per image-space cell.
    order = np.lexsort((-magnitude[candidates], key))
    sorted_key = key[order]
    first = np.r_[True, sorted_key[1:] != sorted_key[:-1]]
    chosen = candidates[order[first]]
    if len(chosen) > int(max_glyphs):
        rank = np.argsort(-magnitude[chosen])[:int(max_glyphs)]
        chosen = chosen[rank]
    return source, target, chosen


def _save_zoom_field(
    image: Image.Image,
    source: np.ndarray,
    target: np.ndarray,
    ids: np.ndarray,
    magnitude: np.ndarray,
    crop: np.ndarray,
    output: Path,
    *,
    cmap,
    norm,
    glyph_length: float,
) -> None:
    width, height = image.size
    figure = plt.figure(figsize=(width / 200.0, height / 200.0), dpi=200)
    axis = figure.add_axes((0.0, 0.0, 1.0, 1.0))
    axis.imshow(image)
    for index in ids:
        start = source[index] - crop[:2]
        delta = target[index] - source[index]
        length = float(np.linalg.norm(delta))
        if length < 1e-8:
            continue
        end = start + delta / length * float(glyph_length)
        color = cmap(norm(magnitude[index]))
        # A restrained black under-stroke keeps arrows legible over all colours.
        axis.add_patch(FancyArrowPatch(
            start, end, arrowstyle="-|>", mutation_scale=10.5,
            linewidth=3.4, color=(0.05, 0.05, 0.05, 0.72), zorder=4,
        ))
        axis.add_patch(FancyArrowPatch(
            start, end, arrowstyle="-|>", mutation_scale=9.2,
            linewidth=1.9, color=color, zorder=5,
        ))
    axis.set_xlim(0, width)
    axis.set_ylim(height, 0)
    axis.set_aspect("equal")
    axis.axis("off")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=200, facecolor="white", pad_inches=0.0)
    plt.close(figure)


def _save_colorbar(output: Path, cmap, norm) -> None:
    figure, axis = plt.subplots(figsize=(5.0, 0.55))
    figure.subplots_adjust(left=.03, right=.97, bottom=.46, top=.88)
    scalar = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    bar = figure.colorbar(scalar, cax=axis, orientation="horizontal")
    bar.set_label(r"Displacement magnitude $\|\Phi(x)-x\| / h$", labelpad=2)
    figure.savefig(output, dpi=300, bbox_inches="tight", pad_inches=.02, facecolor="white")
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--posterior", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--renderer", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--view", default="back")
    parser.add_argument("--point-size", type=float, default=5.0)
    parser.add_argument("--zoom-point-size", type=float, default=10.0)
    parser.add_argument("--resolution", type=int, default=1400)
    parser.add_argument("--zoom-scale", type=int, default=2)
    parser.add_argument("--zoom-box", type=float, nargs=4, default=(.04, .48, .58, .96))
    parser.add_argument("--field-cell", type=int, default=150)
    parser.add_argument("--max-glyphs", type=int, default=30)
    parser.add_argument("--glyph-length", type=float, default=66.0)
    args = parser.parse_args()

    reference = load_points(args.reference)
    posterior = load_points(args.posterior)
    partial = load_points(args.partial)
    if reference.shape != posterior.shape:
        raise ValueError("reference and posterior must be ordered carriers")
    spacing = _median_spacing(reference)
    magnitude = np.linalg.norm(posterior - reference, axis=1) / spacing
    positive = magnitude[magnitude > 0.0]
    vmax = float(np.quantile(positive, .98)) if len(positive) else 1.0
    norm = mpl.colors.Normalize(0.0, max(vmax, 1e-9), clip=True)
    cmap = mpl.colormaps["turbo"]
    rgb = np.rint(cmap(norm(magnitude))[:, :3] * 255.0).astype(np.uint8)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    view_index, view = _view(manifest, args.view)
    pose = np.asarray(view["camera_pose"], dtype=np.float64)
    fov = float(manifest["field_of_view_degrees"])
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    field_ply = output / "registered_prior_deformation_magnitude_rgb.ply"
    _write_rgb(field_ply, reference, rgb)

    full_base = output / "fox_deformation_magnitude_easy3d_base.png"
    _render(
        args.renderer, field_ply, full_base, pose, fov,
        args.resolution, args.point_size,
    )
    full_projector = load_manifest_projectors(args.manifest, resolution=args.resolution)[view_index]
    full_image = _overlay_outline(
        Image.open(full_base), _partial_outline(partial, full_projector),
    )
    full_output = output / "fox_deformation_magnitude_field.png"
    full_image.save(full_output)

    high_resolution = int(args.resolution) * int(args.zoom_scale)
    high_base = output / "fox_deformation_magnitude_easy3d_base_2x.png"
    _render(
        args.renderer, field_ply, high_base, pose, fov,
        high_resolution, args.zoom_point_size,
    )
    high_projector = load_manifest_projectors(
        args.manifest, resolution=high_resolution,
    )[view_index]
    high_image = _overlay_outline(
        Image.open(high_base), _partial_outline(partial, high_projector),
    )
    normalized = np.asarray(args.zoom_box, dtype=np.float64)
    crop = normalized * high_resolution
    crop = np.rint(crop).astype(np.int64)
    crop_image = high_image.crop(tuple(int(value) for value in crop))
    source, target, chosen = _field_samples(
        reference, posterior, high_projector, crop, magnitude,
        cell=int(args.field_cell), max_glyphs=int(args.max_glyphs),
    )
    zoom_output = output / "fox_tail_leg_direction_field.png"
    _save_zoom_field(
        crop_image, source, target, chosen, magnitude, crop, zoom_output,
        cmap=cmap, norm=norm, glyph_length=float(args.glyph_length),
    )
    colorbar = output / "deformation_magnitude_colorbar.png"
    _save_colorbar(colorbar, cmap, norm)

    record = {
        "ground_truth_used": False,
        "reference": str(args.reference.resolve()),
        "posterior": str(args.posterior.resolve()),
        "partial": str(args.partial.resolve()),
        "view": args.view,
        "impostor": "Easy3D PointsDrawable::SPHERE",
        "point_size": float(args.point_size),
        "zoom_point_size": float(args.zoom_point_size),
        "magnitude_units": "median prior spacing",
        "magnitude_vmax_p98": vmax,
        "direction_glyphs": int(len(chosen)),
        "direction_length_encoding": "fixed screen length; colour encodes magnitude",
        "glyph_length_pixels": float(args.glyph_length),
        "outputs": {
            "magnitude_field": str(full_output.resolve()),
            "local_direction_field": str(zoom_output.resolve()),
            "colorbar": str(colorbar.resolve()),
        },
    }
    (output / "figure_manifest.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
