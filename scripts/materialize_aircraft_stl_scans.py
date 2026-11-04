"""Make reproducible, first-hit depth scans and complete point clouds from STL.

Each aircraft has one fixed, area-sampled complete cloud and ten depth-camera
partials. The complete cloud is copied under each view's matching basename so
that partial/<id>.ply and gt/<id>.ply form ordinary dataset pairs.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import shutil
from pathlib import Path

import numpy as np
import open3d as o3d
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "aircraft"
TRIANGLE = np.dtype([("normal", "<f4", (3,)),
                     ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
GT_COUNT = 16_384
PARTIAL_COUNT = 2_048
RESOLUTIONS = (768, 1024)
FOV_DEGREES = 50.0
FRAME_FILL = 0.82
GT_SEED = 6145
VIEW_SEED = 7117
VIEWS = ((0.0, 20.0), (45.0, -20.0), (90.0, 20.0),
         (135.0, -20.0), (180.0, 20.0), (225.0, -20.0),
         (270.0, 20.0), (315.0, -20.0), (22.5, 70.0), (202.5, -70.0))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def open_binary_stl(path: Path) -> np.memmap:
    with path.open("rb") as handle:
        header = handle.read(84)
    if len(header) != 84:
        raise ValueError(f"Incomplete STL header: {path}")
    count = int(np.frombuffer(header[80:84], dtype="<u4")[0])
    if count == 0 or path.stat().st_size != 84 + count * TRIANGLE.itemsize:
        raise ValueError(f"Expected binary STL with consistent triangle count: {path}")
    return np.memmap(path, dtype=TRIANGLE, mode="r", offset=84, shape=(count,))


def mesh_bounds(triangles: np.memmap) -> tuple[np.ndarray, np.ndarray]:
    low = np.full(3, np.inf)
    high = np.full(3, -np.inf)
    for start in range(0, len(triangles), 200_000):
        vertices = triangles["vertices"][start:start + 200_000]
        low = np.minimum(low, vertices.min(axis=(0, 1)))
        high = np.maximum(high, vertices.max(axis=(0, 1)))
    if not np.isfinite(low).all() or not np.isfinite(high).all() or np.max(high - low) <= 0:
        raise ValueError("STL has invalid or degenerate bounds")
    return low, high


def sample_complete(triangles: np.memmap, center: np.ndarray, scale: float,
                    seed: int) -> tuple[np.ndarray, int]:
    areas = np.empty(len(triangles), dtype=np.float64)
    for start in range(0, len(triangles), 100_000):
        stop = min(start + 100_000, len(triangles))
        v = triangles["vertices"][start:stop].astype(np.float64)
        areas[start:stop] = np.linalg.norm(np.cross(v[:, 1] - v[:, 0],
                                                    v[:, 2] - v[:, 0]), axis=1) * 0.5
    good = np.isfinite(areas) & (areas > 0)
    total = float(areas[good].sum())
    if total <= 0:
        raise ValueError("STL has no nondegenerate triangles")
    areas[~good] = 0
    cdf = np.cumsum(areas)
    rng = np.random.default_rng(seed)
    face_ids = np.searchsorted(cdf, rng.random(GT_COUNT) * cdf[-1], side="right")
    v = triangles["vertices"][face_ids].astype(np.float64)
    u = np.sqrt(rng.random(GT_COUNT))
    w = rng.random(GT_COUNT)
    points = ((1 - u)[:, None] * v[:, 0] +
              (u * (1 - w))[:, None] * v[:, 1] +
              (u * w)[:, None] * v[:, 2])
    return ((points - center) / scale).astype("<f4"), int((~good).sum())


def raycasting_scene(triangles: np.memmap, center: np.ndarray,
                     scale: float) -> o3d.t.geometry.RaycastingScene:
    vertices = np.ascontiguousarray(triangles["vertices"].reshape(-1, 3))
    vertices -= center.astype(np.float32)
    vertices /= np.float32(scale)
    faces = np.arange(len(vertices), dtype=np.uint32).reshape(-1, 3)
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.core.Tensor(vertices, dtype=o3d.core.Dtype.Float32),
                        o3d.core.Tensor(faces, dtype=o3d.core.Dtype.UInt32))
    return scene


def camera_pose(azimuth: float, elevation: float) -> tuple[np.ndarray, np.ndarray]:
    az, el = math.radians(azimuth), math.radians(elevation)
    eye_direction = np.array([math.cos(el) * math.cos(az),
                              math.cos(el) * math.sin(az), math.sin(el)])
    forward = -eye_direction
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    rotation = np.stack((right, -up, forward))
    return rotation, eye_direction


def fit_distance(bounds: tuple[np.ndarray, np.ndarray], rotation: np.ndarray,
                 focal: float, resolution: int) -> float:
    corners = np.array(list(itertools.product(*zip(*bounds))))
    projected = corners @ rotation.T
    low = max(float(-projected[:, 2].min() + 0.05), 0.1)
    high = max(2 * low, 1.0)
    target_span = FRAME_FILL * (resolution - 1)

    def span(distance: float) -> float:
        pixels = focal * projected[:, :2] / (projected[:, 2, None] + distance)
        return float(np.ptp(pixels, axis=0).max())

    while span(high) > target_span:
        high *= 2
    for _ in range(35):
        mid = (low + high) / 2
        if span(mid) > target_span:
            low = mid
        else:
            high = mid
    return high


def render_partial(scene: o3d.t.geometry.RaycastingScene,
                   bounds: tuple[np.ndarray, np.ndarray],
                   azimuth: float, elevation: float, seed: int,
                   ) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    rotation, eye_direction = camera_pose(azimuth, elevation)
    for resolution in RESOLUTIONS:
        focal = (resolution - 1) / (2 * math.tan(math.radians(FOV_DEGREES) / 2))
        distance = fit_distance(bounds, rotation, focal, resolution)
        eye = eye_direction * distance
        extrinsic = np.eye(4)
        extrinsic[:3, :3] = rotation
        extrinsic[:3, 3] = -rotation @ eye
        intrinsic = np.array([[focal, 0.0, (resolution - 1) / 2],
                              [0.0, focal, (resolution - 1) / 2], [0.0, 0.0, 1.0]])
        rays = scene.create_rays_pinhole(intrinsic, extrinsic, resolution, resolution).numpy()
        t_hit = scene.cast_rays(o3d.core.Tensor(rays))["t_hit"].numpy()
        valid = np.isfinite(t_hit) & (t_hit > 0)
        count = int(valid.sum())
        if count < 8192:
            continue
        ray_flat = rays.reshape(-1, 6)
        t_flat = t_hit.reshape(-1)
        valid_ids = np.flatnonzero(valid.reshape(-1))
        rng = np.random.default_rng(seed)
        candidate_ids = rng.choice(valid_ids, size=min(8192, count), replace=False)
        candidates = (ray_flat[candidate_ids, :3] +
                      ray_flat[candidate_ids, 3:] * t_flat[candidate_ids, None])
        cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(candidates.astype(np.float64)))
        partial = np.asarray(cloud.farthest_point_down_sample(PARTIAL_COUNT).points,
                             dtype="<f4")
        depth = np.zeros_like(t_hit, dtype=np.float32)
        direction_z = np.einsum("ijk,k->ij", rays[..., 3:], rotation[2])
        depth[valid] = t_hit[valid] * direction_z[valid]
        camera = {"azimuth_degrees": azimuth, "elevation_degrees": elevation,
                  "eye": eye.tolist(), "target": [0.0, 0.0, 0.0],
                  "world_up": [0.0, 0.0, 1.0], "fov_degrees": FOV_DEGREES,
                  "frame_fill": FRAME_FILL, "image_size": resolution,
                  "intrinsic": intrinsic.tolist(),
                  "extrinsic_world_to_camera": extrinsic.tolist(),
                  "hit_pixels": count, "candidate_points": len(candidates),
                  "method": "Open3D RaycastingScene pinhole first-hit depth + FPS"}
        return partial, depth, camera
    raise RuntimeError(f"Only {count} ray hits for view {azimuth}, {elevation}")


def write_ply(path: Path, points: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if points.shape != (len(points), 3) or not np.isfinite(points).all():
        raise ValueError(f"Invalid point cloud: {path}")
    with path.open("wb") as handle:
        handle.write(("ply\nformat binary_little_endian 1.0\n"
                      f"element vertex {len(points)}\nproperty float x\n"
                      "property float y\nproperty float z\nend_header\n").encode())
        np.asarray(points, dtype="<f4").tofile(handle)


def write_depth_preview(path: Path, depth: np.ndarray) -> None:
    valid = depth > 0
    image = np.zeros(depth.shape, dtype=np.uint8)
    values = depth[valid]
    if len(values):
        span = max(float(np.ptp(values)), 1e-8)
        image[valid] = np.rint(35 + 220 * (values.max() - values) / span).astype(np.uint8)
    Image.fromarray(image).save(path)


def process_model(path: Path, output: Path, model_index: int) -> dict[str, object]:
    model = path.stem
    model_manifest = output / "metadata" / f"{model}.json"
    if model_manifest.is_file():
        record = json.loads(model_manifest.read_text())
        required = ("partial", "gt", "depth", "depth_png", "preview", "camera")
        if (len(record["views"]) == len(VIEWS) and
            record["source_sha256"] == sha256(path) and
            all(all((output / item[key]).is_file() for key in required) and
                sha256(output / item["partial"]) == item["partial_sha256"] and
                sha256(output / item["gt"]) == item["gt_sha256"]
                for item in record["views"])):
            print(f"{model}: existing 10-view output found", flush=True)
            return record
        raise ValueError(f"Incomplete existing output for {model}")
    triangles = open_binary_stl(path)
    low, high = mesh_bounds(triangles)
    center = (low + high) / 2
    scale = float(np.max(high - low))
    normalized_bounds = ((low - center) / scale, (high - center) / scale)
    gt_seed = GT_SEED + model_index
    gt, degenerate_faces = sample_complete(triangles, center, scale, gt_seed)
    scene = raycasting_scene(triangles, center, scale)
    views = []
    gt_first = None
    for index, (azimuth, elevation) in enumerate(VIEWS):
        name = f"{model}_view{index:02d}.ply"
        partial_path = output / "partial" / name
        gt_path = output / "gt" / name
        depth_path = output / "depth" / f"{model}_view{index:02d}.npz"
        depth_png_path = output / "depth" / f"{model}_view{index:02d}.png"
        preview_path = output / "previews" / f"{model}_view{index:02d}.png"
        camera_path = output / "metadata" / f"{model}_view{index:02d}.json"
        seed = VIEW_SEED + model_index * 100 + index
        partial, depth, camera = render_partial(scene, normalized_bounds, azimuth, elevation, seed)
        write_ply(partial_path, partial)
        if gt_first is None:
            write_ply(gt_path, gt)
            gt_first = gt_path
        else:
            shutil.copy2(gt_first, gt_path)
        depth_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(depth_path, depth=depth)
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        write_depth_preview(preview_path, depth)
        shutil.copy2(preview_path, depth_png_path)
        camera.update({"sample_id": name.removesuffix(".ply"), "seed": seed,
                       "partial_count": PARTIAL_COUNT, "gt_count": GT_COUNT,
                       "noise_sigma": 0.0})
        camera_path.parent.mkdir(parents=True, exist_ok=True)
        camera_path.write_text(json.dumps(camera, indent=2, ensure_ascii=False) + "\n")
        views.append({"sample_id": name.removesuffix(".ply"),
                      "partial": str(partial_path.relative_to(output)),
                      "gt": str(gt_path.relative_to(output)),
                      "depth": str(depth_path.relative_to(output)),
                      "depth_png": str(depth_png_path.relative_to(output)),
                      "preview": str(preview_path.relative_to(output)),
                      "camera": str(camera_path.relative_to(output)),
                      "partial_sha256": sha256(partial_path),
                      "gt_sha256": sha256(gt_path), "hit_pixels": camera["hit_pixels"],
                      "azimuth_degrees": azimuth, "elevation_degrees": elevation,
                      "seed": seed})
        print(f"{model} view {index:02d}: {camera['hit_pixels']} hits -> {PARTIAL_COUNT} points", flush=True)
    record = {"model": model, "source_stl": str(path.relative_to(ROOT)),
              "source_sha256": sha256(path), "triangle_count": len(triangles),
              "degenerate_triangle_count": degenerate_faces,
              "raw_bounds": [low.tolist(), high.tolist()],
              "normalization": "(point - raw_bounds_center) / max_raw_extent",
              "raw_bounds_center": center.tolist(), "raw_max_extent": scale,
              "raw_unit": "UNKNOWN (STL does not declare units)",
              "gt_seed": gt_seed, "views": views}
    model_manifest.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    return record


def update_index(output: Path) -> None:
    records = []
    for path in sorted((output / "metadata").glob("*.json")):
        record = json.loads(path.read_text())
        if "views" in record:
            records.append(record)
    index = {"method": "Open3D first-hit pinhole raycast; 8192 pixel candidates; 2048-point FPS",
             "partial_count": PARTIAL_COUNT, "gt_count": GT_COUNT,
             "model_count": len(records), "pair_count": sum(len(r["views"]) for r in records),
             "models": records}
    archive = ROOT / "data" / "型号飞机模型.rar"
    if archive.is_file():
        index["source_archive"] = str(archive.relative_to(ROOT))
        index["source_archive_sha256"] = sha256(archive)
    (output / "generation_manifest.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n")
    if len(records) == 4 and all(len(r["views"]) == 10 for r in records):
        sheet = Image.new("RGB", (10 * 224, 4 * 260), "white")
        draw = ImageDraw.Draw(sheet)
        for row, record in enumerate(records):
            for col, view in enumerate(record["views"]):
                preview = Image.open(output / view["preview"]).convert("RGB")
                preview.thumbnail((218, 218))
                x, y = col * 224, row * 260
                sheet.paste(preview, (x + (224 - preview.width) // 2, y))
                label = "Y-20" if record["model"] == "运-20" else record["model"]
                draw.text((x + 5, y + 222), f"{label} v{col:02d}", fill="black")
        sheet.save(output / "view_contact_sheet.png")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DATA_ROOT / "source")
    parser.add_argument("--output-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--model", action="append", help="STL stem; repeat for multiple models")
    args = parser.parse_args()
    files = sorted(args.source_root.glob("*.stl"))
    if args.model:
        files = [args.source_root / f"{model}.stl" for model in args.model]
    if not files or not all(path.is_file() for path in files):
        parser.error("No matching STL files")
    source_order = sorted(path.stem for path in args.source_root.glob("*.stl"))
    for path in files:
        process_model(path, args.output_root, source_order.index(path.stem))
    update_index(args.output_root)


if __name__ == "__main__":
    main()
