"""Build dense KITTI car/pedestrian partials and ScanSalon partial/GT pairs."""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from math import ceil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path("/data/dataset/PointCloudCompletion")
KITTI_SOURCE = Path("/data/dataset/3D_Object_Detection/KITTI/Detection/training")
VERTEX = re.compile(rb"element vertex (\d+)\r?\n")


def vertex_count(path: Path) -> int:
    with path.open("rb") as handle:
        if handle.readline().strip() != b"ply":
            raise ValueError(f"Not a PLY file: {path}")
        for _ in range(100):
            line = handle.readline()
            match = VERTEX.fullmatch(line)
            if match:
                return int(match.group(1))
            if not line or line.strip() == b"end_header":
                break
    raise ValueError(f"Missing vertex count: {path}")


def copy_verified(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if source.stat().st_size != target.stat().st_size or source.read_bytes() != target.read_bytes():
            raise ValueError(f"Existing file differs from source: {target}")
        return
    shutil.copy2(source, target)
    if source.stat().st_size != target.stat().st_size:
        raise IOError(f"Copy size mismatch: {target}")


def write_manifest(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def materialize_scansalon(source: Path, output: Path, top_k: int) -> None:
    partial_root, gt_root = source / "partials", source / "gts"
    if not partial_root.is_dir() or not gt_root.is_dir():
        raise FileNotFoundError(f"Missing ScanSalon partials/gts: {source}")
    rows: list[dict[str, object]] = []
    categories = sorted(path.name for path in partial_root.iterdir() if path.is_dir())
    for category in categories:
        candidates = []
        for partial in (partial_root / category).glob("*.ply"):
            gt = gt_root / category / partial.name
            if gt.is_file():
                candidates.append((vertex_count(partial), partial, gt))
        candidates.sort(key=lambda item: (-item[0], item[1].name))
        if len(candidates) < top_k:
            raise ValueError(f"Only {len(candidates)} pairs in {category}, need {top_k}")
        for count, partial, gt in candidates[:top_k]:
            name = f"{category}_{partial.stem}.ply"
            copy_verified(partial, output / "partial" / name)
            copy_verified(gt, output / "gt" / name)
            rows.append({"category": category, "sample": name, "partial_points": count,
                         "gt_points": vertex_count(gt),
                         "source_partial": str(partial), "source_gt": str(gt)})
    write_manifest(output / "selection.csv", rows,
                   ["category", "sample", "partial_points", "gt_points", "source_partial", "source_gt"])
    print(f"ScanSalon: {len(rows)} partial/GT pairs across {len(categories)} categories")


def calibration_matrix(path: Path, key: str, shape: tuple[int, int]) -> np.ndarray:
    for line in path.read_text().splitlines():
        if line.startswith(f"{key}:"):
            return np.asarray([float(value) for value in line.split(":", 1)[1].split()],
                              dtype=np.float32).reshape(shape)
    raise ValueError(f"Missing {key} in {path}")


def extract_kitti_frame(label_path: Path, source: Path) -> list[tuple[str, str, int, np.ndarray, str]]:
    labels = [line.split() for line in label_path.read_text().splitlines()]
    labels = [label for label in labels if label and label[0] in {"Car", "Pedestrian"}]
    if not labels:
        return []
    frame = label_path.stem
    velo_path = source / "velodyne" / f"{frame}.bin"
    calib_path = source / "calib" / f"{frame}.txt"
    if not velo_path.is_file() or not calib_path.is_file():
        raise FileNotFoundError(f"Missing KITTI LiDAR/calibration for {frame}")
    lidar = np.fromfile(velo_path, dtype="<f4").reshape(-1, 4)[:, :3]
    transform = calibration_matrix(calib_path, "Tr_velo_to_cam", (3, 4))
    rect = calibration_matrix(calib_path, "R0_rect", (3, 3))
    camera = (lidar @ transform[:, :3].T + transform[:, 3]) @ rect.T
    results = []
    ordinal = {"Car": 0, "Pedestrian": 0}
    for label in labels:
        category = label[0].lower()
        index = ordinal[label[0]]
        ordinal[label[0]] += 1
        height, width, length = map(float, label[8:11])
        location = np.asarray([float(v) for v in label[11:14]], dtype=np.float32)
        yaw = float(label[14])
        radius = np.hypot(width, length) / 2
        nearby = ((camera[:, 1] >= location[1] - height) &
                  (camera[:, 1] <= location[1]) &
                  (np.abs(camera[:, 0] - location[0]) <= radius) &
                  (np.abs(camera[:, 2] - location[2]) <= radius))
        if not np.any(nearby):
            continue
        relative = camera[nearby] - location
        cos_yaw, sin_yaw = np.cos(yaw), np.sin(yaw)
        local = np.column_stack((cos_yaw * relative[:, 0] - sin_yaw * relative[:, 2],
                                 relative[:, 1],
                                 sin_yaw * relative[:, 0] + cos_yaw * relative[:, 2]))
        inside = ((np.abs(local[:, 0]) <= width / 2) &
                  (local[:, 1] >= -height) & (local[:, 1] <= 0) &
                  (np.abs(local[:, 2]) <= length / 2))
        points = local[inside].astype("<f4", copy=True)
        if len(points):
            results.append((category, f"frame_{frame}_{category}_{index}.ply",
                            len(points), points, frame))
    return results


def write_xyz_ply(path: Path, points: np.ndarray) -> None:
    header = ("ply\nformat binary_little_endian 1.0\n"
              f"element vertex {len(points)}\n"
              "property float x\nproperty float y\nproperty float z\nend_header\n")
    with path.open("wb") as handle:
        handle.write(header.encode("ascii"))
        points.tofile(handle)


def materialize_kitti_shard(
    source: Path, output: Path, top_k: int, shard_index: int, shard_count: int
) -> None:
    label_root = source / "label_2"
    if not label_root.is_dir():
        raise FileNotFoundError(label_root)
    shard_root = output / ".selection_work" / f"shard_{shard_index:02d}"
    manifest = shard_root / "selection.csv"
    if manifest.is_file():
        rows = list(csv.DictReader(manifest.open()))
        if len(rows) == 2 * top_k and all((shard_root / row["sample"]).is_file() for row in rows):
            print(f"KITTI shard {shard_index + 1}/{shard_count}: already complete", flush=True)
            return
        raise ValueError(f"Incomplete KITTI shard manifest: {manifest}")
    selected: dict[str, list[tuple[str, str, int, np.ndarray, str]]] = {"car": [], "pedestrian": []}
    all_labels = sorted(label_root.glob("*.txt"))
    shard_size = ceil(len(all_labels) / shard_count)
    labels = all_labels[shard_index * shard_size:(shard_index + 1) * shard_size]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for frame_index, result in enumerate(pool.map(lambda path: extract_kitti_frame(path, source), labels), 1):
            for sample in result:
                category = sample[0]
                candidates = selected[category]
                candidates.append(sample)
                candidates.sort(key=lambda item: (-item[2], item[1]))
                del candidates[top_k:]
            if frame_index % 500 == 0:
                print(f"KITTI shard {shard_index + 1}/{shard_count}: {frame_index}/{len(labels)} frames", flush=True)
    shard_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for category, samples in selected.items():
        if len(samples) < top_k:
            raise ValueError(f"Only {len(samples)} nonempty KITTI {category} scans, need {top_k}")
        for _, name, count, points, frame in samples:
            write_xyz_ply(shard_root / name, points)
            rows.append({"category": category, "sample": name, "partial_points": count,
                         "source_lidar": str(source / "velodyne" / f"{frame}.bin"),
                         "source_label": str(source / "label_2" / f"{frame}.txt"),
                         "source_calibration": str(source / "calib" / f"{frame}.txt")})
    write_manifest(manifest, rows, ["category", "sample", "partial_points", "source_lidar",
                                    "source_label", "source_calibration"])
    print(f"KITTI shard {shard_index + 1}/{shard_count}: complete", flush=True)


def merge_kitti_shards(output: Path, top_k: int, shard_count: int) -> None:
    work_root = output / ".selection_work"
    candidates: dict[str, list[tuple[dict[str, str], Path]]] = {"car": [], "pedestrian": []}
    for shard_index in range(shard_count):
        shard_root = work_root / f"shard_{shard_index:02d}"
        manifest = shard_root / "selection.csv"
        if not manifest.is_file():
            raise FileNotFoundError(manifest)
        for row in csv.DictReader(manifest.open()):
            source_ply = shard_root / row["sample"]
            if vertex_count(source_ply) != int(row["partial_points"]):
                raise ValueError(f"Incorrect shard point count: {source_ply}")
            candidates[row["category"]].append((row, source_ply))
    partial_root = output / "partial"
    partial_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    for category, samples in candidates.items():
        samples.sort(key=lambda item: (-int(item[0]["partial_points"]), item[0]["sample"]))
        if len(samples) < top_k:
            raise ValueError(f"Only {len(samples)} KITTI {category} candidates")
        for row, source_ply in samples[:top_k]:
            target = partial_root / category / row["sample"]
            if target.is_file() and target.read_bytes() != source_ply.read_bytes():
                target.unlink()
            copy_verified(source_ply, target)
            rows.append(row)
    expected = {Path(row["category"]) / row["sample"] for row in rows}
    for old in partial_root.rglob("*.ply"):
        if old.relative_to(partial_root) not in expected:
            old.unlink()
    write_manifest(output / "selection.csv", rows,
                   ["category", "sample", "partial_points", "source_lidar",
                    "source_label", "source_calibration"])
    (output / "gt").mkdir(parents=True, exist_ok=True)
    (output / "gt" / ".gitkeep").touch(exist_ok=True)
    shutil.rmtree(work_root)
    print(f"KITTI: {len(rows)} dense partials across car/pedestrian; no matched GT")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--kitti-source", type=Path, default=KITTI_SOURCE)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--dataset", choices=("all", "kitti", "scansalon"), default="all")
    parser.add_argument("--kitti-shards", type=int, default=5)
    parser.add_argument("--kitti-shard", type=int,
                        help="Process only this zero-based KITTI shard; merge in a later call")
    parser.add_argument("--kitti-merge-only", action="store_true")
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be positive")
    if args.kitti_shards < 1:
        parser.error("--kitti-shards must be positive")
    if args.kitti_shard is not None and not 0 <= args.kitti_shard < args.kitti_shards:
        parser.error("--kitti-shard is outside the shard range")
    if args.kitti_shard is not None and args.kitti_merge_only:
        parser.error("--kitti-shard and --kitti-merge-only cannot be combined")
    if args.dataset in ("all", "scansalon"):
        materialize_scansalon(args.source_root / "ScanSalon", args.data_root / "scannet", args.top_k)
    if args.dataset in ("all", "kitti"):
        output = args.data_root / "kitti"
        if not args.kitti_merge_only:
            indexes = range(args.kitti_shards) if args.kitti_shard is None else [args.kitti_shard]
            for index in indexes:
                materialize_kitti_shard(args.kitti_source, output, args.top_k, index, args.kitti_shards)
        if args.kitti_shard is None:
            merge_kitti_shards(output, args.top_k, args.kitti_shards)


if __name__ == "__main__":
    main()
