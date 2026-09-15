#!/usr/bin/env python3
"""Evaluate sparse completions against an adjacent same-track partial scan.

The held-out frame is never used by inference or candidate routing.  It is an
independent positive-surface check for Waymo subsets without complete GT.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pointcloud_io import jsonable, load_points
from src.ray_consistent_registration import apply_transform


def _track_id(path: Path) -> str:
    fields = path.stem.split("_")
    if len(fields) < 4:
        raise ValueError(f"unexpected Waymo object filename: {path.name}")
    return "_".join(fields[3:])


def _cloud(points: np.ndarray) -> o3d.geometry.PointCloud:
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.asarray(points, dtype=np.float64))
    return cloud


def _adjacent_frame_transform(source: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, dict]:
    diagonal = max(float(np.linalg.norm(np.ptp(target, axis=0))), 1e-8)
    initial = np.eye(4, dtype=np.float64)
    initial[:3, 3] = np.median(target, axis=0) - np.median(source, axis=0)
    result = o3d.pipelines.registration.registration_icp(
        _cloud(source),
        _cloud(target),
        .12 * diagonal,
        initial,
        o3d.pipelines.registration.TransformationEstimationPointToPoint(False),
        o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=80),
    )
    return result.transformation, {
        "fitness": float(result.fitness),
        "inlier_rmse": float(result.inlier_rmse),
        "correspondence_threshold": float(.12 * diagonal),
    }


def _one_sided_surface_score(observation: np.ndarray, prediction: np.ndarray) -> dict:
    diagonal = max(float(np.linalg.norm(np.ptp(observation, axis=0))), 1e-8)
    distance = cKDTree(prediction).query(observation, k=1, workers=-1)[0] / diagonal
    return {
        "median": float(np.median(distance)),
        "mean": float(np.mean(distance)),
        "p90": float(np.quantile(distance, .90)),
        "normalization_diagonal": diagonal,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--mainline-root", type=Path, required=True)
    parser.add_argument("--adapter-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    track_files: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(args.data_root.glob("*/*.ply")):
        track_files[_track_id(path)].append(path)
    rows = []
    for sample_dir in sorted(path for path in args.adapter_root.iterdir() if path.is_dir()):
        sample = sample_dir.name
        source_path = args.mainline_root / "inputs" / "partial" / f"{sample}.ply"
        selected_path = sample_dir / "complete_100k.ply"
        baseline_path = args.mainline_root / "final" / sample / "complete_100k.ply"
        if not all(path.is_file() for path in (source_path, selected_path, baseline_path)):
            continue
        source = load_points(source_path)
        for heldout_path in track_files.get(_track_id(source_path), []):
            if heldout_path.stem == sample:
                continue
            heldout = load_points(heldout_path)
            transform, registration = _adjacent_frame_transform(source, heldout)
            scores = {}
            for name, path in (("frozen_mainline", baseline_path), ("selected", selected_path)):
                prediction = apply_transform(load_points(path), transform)
                scores[name] = _one_sided_surface_score(heldout, prediction)
            rows.append({
                "source": sample,
                "heldout": heldout_path.stem,
                "track_id": _track_id(source_path),
                "partial_to_heldout_registration": registration,
                "scores": scores,
            })
    if not rows:
        raise RuntimeError("no adjacent same-track held-out pairs were found")
    aggregate = {
        metric: {
            name: float(np.mean([row["scores"][name][metric] for row in rows]))
            for name in ("frozen_mainline", "selected")
        }
        for metric in ("median", "mean", "p90")
    }
    strict_wins = sum(
        row["scores"]["selected"]["mean"]
        < row["scores"]["frozen_mainline"]["mean"] - 1e-12
        for row in rows
    )
    non_regressions = sum(
        row["scores"]["selected"]["mean"]
        <= row["scores"]["frozen_mainline"]["mean"] + 1e-12
        for row in rows
    )
    result = {
        "method": "adjacent_same_track_partial_holdout",
        "inference_uses_heldout": False,
        "complete_ground_truth_used": False,
        "pair_count": int(len(rows)),
        "aggregate": aggregate,
        "selected_strict_wins": int(strict_wins),
        "selected_non_regressions": int(non_regressions),
        "pairs": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(jsonable(result), indent=2) + "\n", encoding="utf-8")
    print(json.dumps(jsonable(result | {"pairs": f"{len(rows)} records"}), indent=2))


if __name__ == "__main__":
    main()
