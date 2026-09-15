#!/usr/bin/env python3
"""Render an orbit atlas and export a completion-friendly partial camera.

The original manual/GPT selection remains available.  ``--auto-select`` uses
only category-free partial geometry to rank a deterministic camera lattice,
then writes a Camera-1-compatible camera, depth raster, and audit metadata.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import cv2
import kaolin as kal
import numpy as np
from PIL import Image, ImageDraw
import torch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.depth_prompting import DepthPrompting
from src.mainline_data import load_partial
from src.zbuffer import zbuffer_depth_with_indices


def view_direction(azimuth_degrees: float, elevation_degrees: float) -> np.ndarray:
    azimuth, elevation = map(math.radians, (azimuth_degrees, elevation_degrees))
    return np.asarray((
        math.cos(elevation) * math.cos(azimuth),
        math.sin(elevation),
        math.cos(elevation) * math.sin(azimuth),
    ), dtype=np.float64)


def camera_parameters(points: np.ndarray, azimuth_degrees: float,
                      elevation_degrees: float, fov_degrees: float) -> dict[str, np.ndarray | float]:
    lower, upper = points.min(axis=0), points.max(axis=0)
    target = (lower + upper) * .5
    extent = float(np.linalg.norm(upper - lower))
    distance = max(1.6 * extent, 1e-3)
    direction = view_direction(azimuth_degrees, elevation_degrees)
    eye = target + direction * distance
    forward = target - eye
    forward /= max(float(np.linalg.norm(forward)), 1e-12)
    world_up = np.asarray((0., 1., 0.), dtype=np.float64)
    if abs(float(np.dot(forward, world_up))) > .98:
        world_up = np.asarray((0., 0., 1.), dtype=np.float64)
    right = np.cross(forward, world_up)
    right /= max(float(np.linalg.norm(right)), 1e-12)
    up = np.cross(right, forward)
    up /= max(float(np.linalg.norm(up)), 1e-12)
    return {
        "target": target, "eye": eye, "up": up, "direction": direction,
        "distance": distance, "fov_degrees": float(fov_degrees),
    }


def roll_camera_parameters(parameters: dict[str, np.ndarray | float],
                           roll_degrees: float) -> dict[str, np.ndarray | float]:
    """Roll the physical camera basis so every exported artifact stays aligned."""
    result = dict(parameters)
    forward = np.asarray(parameters["target"], dtype=np.float64) - np.asarray(
        parameters["eye"], dtype=np.float64,
    )
    forward /= max(float(np.linalg.norm(forward)), 1e-12)
    up = np.asarray(parameters["up"], dtype=np.float64)
    right = np.cross(forward, up)
    right /= max(float(np.linalg.norm(right)), 1e-12)
    angle = math.radians(float(roll_degrees))
    rolled_up = math.cos(angle) * up + math.sin(angle) * right
    rolled_up /= max(float(np.linalg.norm(rolled_up)), 1e-12)
    result["up"] = rolled_up
    result["roll_degrees"] = float(roll_degrees) % 360.0
    return result


def make_camera(parameters: dict[str, np.ndarray | float], resolution: int):
    return kal.render.camera.Camera.from_args(
        eye=torch.as_tensor(parameters["eye"], dtype=torch.float32),
        at=torch.as_tensor(parameters["target"], dtype=torch.float32),
        up=torch.as_tensor(parameters["up"], dtype=torch.float32),
        fov=math.radians(float(parameters["fov_degrees"])),
        width=int(resolution), height=int(resolution), device="cpu",
    )


def project(points: np.ndarray, parameters: dict[str, np.ndarray | float], resolution: int):
    camera = make_camera(parameters, resolution)
    with torch.no_grad():
        camera_points = camera.transform(torch.as_tensor(points, dtype=torch.float32)).cpu().numpy()
    xy = camera_points[:, :2]
    center = (xy.min(axis=0) + xy.max(axis=0)) * .5
    scale = max(float(np.ptp(xy, axis=0).max()), 1e-8)
    uv = (xy - center) / scale * .70 + .5
    uv[:, 1] = 1. - uv[:, 1]
    return camera, uv, camera_points[:, 2], center, scale


def render_depth(points: np.ndarray, colors: np.ndarray,
                 parameters: dict[str, np.ndarray | float], resolution: int):
    """Reuse the frozen mainline DepthPrompting sparse-depth raster exactly."""
    _, uv, depth, center, scale = project(points, parameters, resolution)
    pixels = torch.as_tensor(np.clip(uv * float(resolution), 0., float(resolution - 1)), dtype=torch.long)
    pixels = torch.stack((pixels[:, 1], pixels[:, 0]), dim=1)
    # `_rasterise_depth` reads only these three frozen image parameters.  It
    # paints one depth pixel per observation and applies OpenCV inpainting only
    # to the five-by-five local ring around it; empty background stays empty.
    rasterizer = object.__new__(DepthPrompting)
    rasterizer.cfg = SimpleNamespace(res=int(resolution), point_size=1, mask_pixel_rate=3)
    rasterizer.device = torch.device("cpu")
    sparse_depth, hole_mask = rasterizer._rasterise_depth(
        pixels, torch.as_tensor(depth, dtype=torch.float32), torch.as_tensor(colors, dtype=torch.float32)
    )
    raw = (sparse_depth.permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
    inpaint_mask = (hole_mask.permute(1, 2, 0).cpu().numpy()[..., 0] * 255).astype(np.uint8)
    depth_image = cv2.inpaint(raw, inpaint_mask, 2, cv2.INPAINT_NS)
    valid = raw[..., 0] > 0
    local_support = valid | (inpaint_mask > 0)
    return raw, depth_image, valid, local_support, inpaint_mask, uv, depth, center, scale


def atlas_cell(points: np.ndarray, azimuth: float, elevation: float, resolution: int) -> Image.Image:
    """Fast visual-only orbit render; it is never used for final depth export."""
    parameters = camera_parameters(points, azimuth, elevation, 49.1)
    _, uv, depth, _, _ = project(points, parameters, resolution)
    rendered, visible, _ = zbuffer_depth_with_indices(
        uv * float(resolution - 1), depth, (resolution, resolution), splat_radius=1,
    )
    rgb = np.zeros((resolution, resolution, 3), dtype=np.uint8)
    if visible.any():
        values = rendered[visible]
        shade = np.rint(255. * (1. - (values - values.min()) / max(float(np.ptp(values)), 1e-8))).astype(np.uint8)
        rgb[visible] = np.stack((shade, np.minimum(255, shade + 35), 255 - shade // 3), axis=1)
    cell = Image.fromarray(rgb)
    ImageDraw.Draw(cell).rectangle((0, 0, resolution - 1, 20), fill=(0, 0, 0))
    ImageDraw.Draw(cell).text((4, 4), f"az {azimuth:5.1f}  el {elevation:4.1f}", fill=(255, 255, 255))
    return cell


def write_orbit_atlas(points: np.ndarray, output: Path, resolution: int) -> None:
    azimuths = tuple(float(value) for value in range(0, 360, 45))
    elevations = (-20., 10., 35.)
    sheet = Image.new("RGB", (len(azimuths) * resolution, len(elevations) * resolution), color=(0, 0, 0))
    for row, elevation in enumerate(elevations):
        for column, azimuth in enumerate(azimuths):
            sheet.paste(atlas_cell(points, azimuth, elevation, resolution), (column * resolution, row * resolution))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def _normalised_rank(values: np.ndarray) -> np.ndarray:
    """Return stable [0, 1] ranks without dataset- or category-scale constants."""
    values = np.asarray(values, dtype=np.float64)
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=np.float64)
    ranks[order] = np.arange(len(values), dtype=np.float64)
    return ranks / max(len(values) - 1, 1)


def _view_features(points: np.ndarray, azimuth: float, elevation: float,
                   resolution: int, fov_degrees: float) -> dict[str, float]:
    """Measure view informativeness using partial geometry alone.

    The terms deliberately avoid object labels and preferred world axes.  They
    reward visible support, low projection collision, depth ordering, coherent
    projected support and a non-degenerate image footprint.
    """
    parameters = camera_parameters(points, azimuth, elevation, fov_degrees)
    _, uv, point_depth, _, _ = project(points, parameters, resolution)
    pixels = uv * float(resolution - 1)
    rendered, mask, indices = zbuffer_depth_with_indices(
        pixels, point_depth, (resolution, resolution), splat_radius=1,
    )
    visible_ids = np.unique(indices[mask])
    visible_ratio = float(len(visible_ids) / max(len(points), 1))

    # Projection collision is distinct from visibility: it penalises views in
    # which otherwise visible structures collapse onto the same image cells.
    _, point_mask, point_indices = zbuffer_depth_with_indices(
        pixels, point_depth, (resolution, resolution), splat_radius=0,
    )
    collision_free = float(len(np.unique(point_indices[point_mask])) / max(len(points), 1))
    projected_area = float(mask.mean())

    values = rendered[mask]
    if len(values) > 1 and float(np.ptp(values)) > 1e-12:
        histogram, _ = np.histogram(values, bins=16)
        probability = histogram[histogram > 0].astype(np.float64)
        probability /= probability.sum()
        depth_entropy = float(-(probability * np.log(probability)).sum() / np.log(16.0))
        depth_span = float(np.quantile(values, .95) - np.quantile(values, .05))
    else:
        depth_entropy = 0.0
        depth_span = 0.0
    object_extent = max(float(np.linalg.norm(np.ptp(points, axis=0))), 1e-12)
    depth_span /= object_extent

    support = cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8), iterations=1)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(support, connectivity=8)
    foreground_sizes = stats[1:, cv2.CC_STAT_AREA] if count > 1 else np.empty(0)
    connectivity = float(foreground_sizes.max() / max(foreground_sizes.sum(), 1)) if len(foreground_sizes) else 0.0

    centred = pixels[visible_ids] - pixels[visible_ids].mean(axis=0, keepdims=True)
    covariance = centred.T @ centred / max(len(centred), 1)
    eigenvalues = np.linalg.eigvalsh(covariance)
    footprint_balance = float(np.sqrt(max(eigenvalues[0], 0.0) / max(eigenvalues[-1], 1e-12)))
    return {
        "azimuth_degrees": float(azimuth),
        "elevation_degrees": float(elevation),
        "visible_ratio": visible_ratio,
        "collision_free_ratio": collision_free,
        "projected_area": projected_area,
        "depth_entropy": depth_entropy,
        "normalised_depth_span": depth_span,
        "support_connectivity": connectivity,
        "footprint_balance": footprint_balance,
    }


def select_completion_aware_view(points: np.ndarray, *, resolution: int = 160,
                                 fov_degrees: float = 49.1) -> tuple[dict, list[dict]]:
    """Select a category-free view that is informative and perturbation-stable."""
    azimuths = np.arange(0.0, 360.0, 15.0)
    elevations = (-30.0, -15.0, 0.0, 15.0, 30.0)
    records = [
        _view_features(points, float(azimuth), float(elevation), resolution, fov_degrees)
        for elevation in elevations for azimuth in azimuths
    ]
    terms = (
        ("visible_ratio", .26),
        ("collision_free_ratio", .22),
        ("depth_entropy", .16),
        ("normalised_depth_span", .12),
        ("support_connectivity", .12),
        ("projected_area", .07),
        ("footprint_balance", .05),
    )
    base = np.zeros(len(records), dtype=np.float64)
    for name, weight in terms:
        base += weight * _normalised_rank(np.asarray([record[name] for record in records]))

    # A good completion view should survive a small camera perturbation.  The
    # lattice neighbours provide this stability check without new thresholds.
    lookup = {
        (record["azimuth_degrees"], record["elevation_degrees"]): index
        for index, record in enumerate(records)
    }
    stable = np.empty_like(base)
    for index, record in enumerate(records):
        neighbours = []
        for delta_azimuth, delta_elevation in ((-15., 0.), (15., 0.), (0., -15.), (0., 15.)):
            key = ((record["azimuth_degrees"] + delta_azimuth) % 360.,
                   record["elevation_degrees"] + delta_elevation)
            if key in lookup:
                neighbours.append(base[lookup[key]])
        stable[index] = .7 * base[index] + .3 * float(np.mean(neighbours or [base[index]]))
        records[index]["base_score"] = float(base[index])
        records[index]["completion_view_score"] = float(stable[index])
    ranked = sorted(records, key=lambda item: item["completion_view_score"], reverse=True)
    for rank, record in enumerate(ranked, 1):
        record["rank"] = rank
    return ranked[0], ranked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--azimuth-degrees", type=float)
    parser.add_argument("--elevation-degrees", type=float)
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--atlas-resolution", type=int, default=192)
    parser.add_argument("--fov-degrees", type=float, default=49.1)
    parser.add_argument(
        "--roll-degrees", type=float, choices=(0.0, 90.0, 180.0, 270.0), default=0.0,
        help="Discrete in-plane camera roll applied consistently to depth, UV, and camera.pth.",
    )
    parser.add_argument("--render-atlas-only", action="store_true")
    parser.add_argument("--auto-select", action="store_true",
                        help="Select a category-free completion-friendly view from partial geometry.")
    parser.add_argument("--reuse-atlas", action="store_true",
                        help="Reuse an existing visual-review atlas when exporting the selected view.")
    parser.add_argument("--rationale", default="")
    args = parser.parse_args()
    if args.resolution < 32 or args.atlas_resolution < 64:
        raise ValueError("image resolutions are too small")
    explicit = args.azimuth_degrees is not None or args.elevation_degrees is not None
    if sum((bool(args.render_atlas_only), bool(args.auto_select), bool(explicit))) != 1:
        raise ValueError("choose exactly one of --render-atlas-only, --auto-select, or explicit angles")
    if args.azimuth_degrees is None and explicit:
        raise ValueError("both --azimuth-degrees and --elevation-degrees are required")
    if args.azimuth_degrees is not None and args.elevation_degrees is None:
        raise ValueError("both --azimuth-degrees and --elevation-degrees are required")

    partial = args.partial.resolve()
    output = args.output_dir.resolve()
    points, colors = load_partial(partial)
    output.mkdir(parents=True, exist_ok=True)
    atlas = output / "gpt_orbit_atlas.png"
    if args.reuse_atlas:
        if not atlas.is_file():
            raise FileNotFoundError(f"--reuse-atlas requires {atlas}")
    else:
        write_orbit_atlas(points, atlas, int(args.atlas_resolution))
    if args.render_atlas_only:
        print(json.dumps({"partial": str(partial), "atlas": str(atlas), "selection": "pending_gpt_visual_review"}, indent=2))
        return

    ranking = None
    if args.auto_select:
        selected, ranking = select_completion_aware_view(
            points, resolution=min(int(args.atlas_resolution), 192),
            fov_degrees=float(args.fov_degrees),
        )
        args.azimuth_degrees = selected["azimuth_degrees"]
        args.elevation_degrees = selected["elevation_degrees"]
        (output / "completion_view_ranking.json").write_text(
            json.dumps(ranking, indent=2) + "\n", encoding="utf-8",
        )

    parameters = camera_parameters(
        points, float(args.azimuth_degrees), float(args.elevation_degrees),
        float(args.fov_degrees),
    )
    parameters = roll_camera_parameters(parameters, float(args.roll_degrees))
    camera, uv, _, xy_center, xy_scale = project(points, parameters, int(args.resolution))
    raw, depth, valid, local_support, inpaint_mask, _, point_depth, _, _ = render_depth(
        points, colors, parameters, int(args.resolution)
    )
    Image.fromarray(raw).save(output / "raw_depth.png")
    Image.fromarray(depth).save(output / "depth.png")
    Image.fromarray(inpaint_mask).save(output / "mask.png")
    Image.fromarray((local_support * 255).astype(np.uint8)).save(output / "support_mask.png")
    np.save(output / "depth.npy", (depth[..., 0].astype(np.float32) / 255.))
    np.save(output / "camera_point_depth.npy", point_depth.astype(np.float32))
    np.save(output / "point_uv.npy", uv.astype(np.float32))
    np.save(output / "viewpoint.npy", np.asarray(parameters["eye"], dtype=np.float32))
    np.save(output / "target.npy", np.asarray(parameters["target"], dtype=np.float32))
    torch.save(camera, output / "camera.pth")
    record = {
        "partial": str(partial),
        "selection_source": (
            "category-free completion-aware partial geometry score"
            if args.auto_select else
            "GPT-5.6 Terra visual inspection of gpt_orbit_atlas.png; no geometry-score ranking"
        ),
        "rationale": str(args.rationale),
        "azimuth_degrees": float(args.azimuth_degrees) % 360.,
        "elevation_degrees": float(args.elevation_degrees),
        "roll_degrees": float(args.roll_degrees) % 360.0,
        "eye": np.asarray(parameters["eye"]).tolist(),
        "target": np.asarray(parameters["target"]).tolist(),
        "up": np.asarray(parameters["up"]).tolist(),
        "view_direction": np.asarray(parameters["direction"]).tolist(),
        "camera_distance": float(parameters["distance"]),
        "fov_degrees": float(args.fov_degrees),
        "image_size": int(args.resolution),
        "projection_normalization": {"xy_center_camera": xy_center.tolist(), "xy_scale_camera": float(xy_scale), "frame_fill": .70},
        "visible_pixels": int(valid.sum()),
        "local_support_pixels": int(local_support.sum()),
        "inpaint_pixels": int((inpaint_mask > 0).sum()),
        "source_points": int(len(points)),
    }
    (output / "semantic_view_selection.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"atlas": str(atlas), "output": str(output), **record}, indent=2))


if __name__ == "__main__":
    main()
