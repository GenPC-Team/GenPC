#!/usr/bin/env python3
"""Rasterize Custom partial scans with their saved acquisition cameras.

The source directories contain a partial PLY and camera, but may omit the
depth/UV files needed by the prior agent. This reconstructs those observations
from the partial alone; it never opens the complete mesh or ground truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.mainline_data import load_partial
from src.zbuffer import zbuffer_depth_with_indices


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(source: Path, destination: Path, *, resolution: int) -> dict:
    sample = source.parents[1].name
    partial = source / f"{sample}_partial.ply"
    camera_json = source / "camera.json"
    camera_pth = source / "camera.pth"
    if not all(path.is_file() for path in (partial, camera_json, camera_pth)):
        raise FileNotFoundError(f"{source}: partial PLY and both camera files are required")
    metadata = json.loads(camera_json.read_text(encoding="utf-8"))
    native_size = int(metadata["image_size"])
    intrinsic = np.asarray(metadata["intrinsic"], dtype=np.float64)
    transform = np.asarray(metadata["extrinsic_world_to_camera"], dtype=np.float64)
    if intrinsic.shape != (3, 3) or transform.shape != (4, 4):
        raise ValueError(f"{sample}: invalid saved pinhole camera")
    points, _ = load_partial(partial)
    camera_points = points @ transform[:3, :3].T + transform[:3, 3]
    depth = camera_points[:, 2]
    pixel = np.column_stack((
        intrinsic[0, 0] * camera_points[:, 0] / depth + intrinsic[0, 2],
        intrinsic[1, 1] * camera_points[:, 1] / depth + intrinsic[1, 2],
    ))
    uv = pixel / max(native_size - 1, 1)
    if not np.isfinite(uv).all() or not np.all(depth > 0):
        raise ValueError(f"{sample}: partial contains invalid pinhole projections")
    target_pixel = uv * (resolution - 1)
    rendered, support, _ = zbuffer_depth_with_indices(
        target_pixel, depth, (resolution, resolution), splat_radius=2,
    )
    if int(support.sum()) < 100:
        raise ValueError(f"{sample}: too few positive projected partial pixels")
    positive = rendered[support]
    gray = np.zeros((resolution, resolution), dtype=np.uint8)
    gray[support] = np.rint(
        25 + 204 * (1 - (positive - positive.min()) /
                    max(float(np.ptp(positive)), 1e-8))
    ).astype(np.uint8)
    closed = cv2.morphologyEx(
        support.astype(np.uint8), cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
    ) > 0
    filled = cv2.inpaint(
        gray, (closed & ~support).astype(np.uint8) * 255, 3,
        cv2.INPAINT_NS,
    )
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("camera.pth", "camera.json"):
        shutil.copy2(source / name, destination / name)
    Image.fromarray(gray).save(destination / "raw_depth.png")
    Image.fromarray(filled).save(destination / "depth.png")
    Image.fromarray(closed.astype(np.uint8) * 255).save(destination / "mask.png")
    np.save(destination / "point_uv.npy", uv.astype(np.float32))
    np.save(destination / "viewpoint.npy", np.asarray(metadata["eye"], dtype=np.float32))
    record = {
        "schema": "genpc.custom_saved_camera_depth.v1",
        "sample": sample, "partial": str(partial.resolve()),
        "partial_sha256": _sha256(partial),
        "source_camera": str(camera_pth.resolve()),
        "source_camera_sha256": _sha256(camera_pth),
        "source_camera_json_sha256": _sha256(camera_json),
        "native_camera_resolution": native_size,
        "depth_raster_resolution": resolution,
        "view_selection": False,
        "ground_truth_used": False,
        "projected_partial_points": int(np.isfinite(target_pixel).all(axis=1).sum()),
        "positive_pixels": int(support.sum()),
        "output": str(destination.resolve()),
    }
    (destination / "fixed_camera_preparation.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8",
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data" / "custom")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--samples", nargs="*")
    args = parser.parse_args()
    if args.resolution <= 0:
        parser.error("--resolution must be positive")
    samples = args.samples or sorted(
        path.name for path in args.data_root.iterdir()
        if path.is_dir() and (path / "partial_data" / "single_scan").is_dir()
    )
    records = []
    for sample in samples:
        source = args.data_root / sample / "partial_data" / "single_scan"
        records.append(prepare(
            source, args.output_root / sample, resolution=args.resolution,
        ))
    (args.output_root / "preparation_index.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps({"samples": len(records), "output_root": str(args.output_root.resolve())}))


if __name__ == "__main__":
    main()
