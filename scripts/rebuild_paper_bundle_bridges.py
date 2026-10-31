#!/usr/bin/env python3
"""Recompute missing Pixal/MoGe-to-partial bridges from frozen paper inputs.

This does not replace a historical bridge or change the frozen registered,
refined, or fused carriers. GT and offline metrics are never read.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.package_refine_agent_paper import archive, checked_json, sha256, vertex_count, write_json
from src.multiview_diagnostics import estimate_ordered_similarity
from src.pointcloud_io import load_points


def input_paths(sample_dir: Path, sample: str) -> dict[str, Path]:
    return {
        "partial": sample_dir / "00_observation/partial.ply",
        "point_uv": sample_dir / "00_observation/camera_used_by_agent/point_uv.npy",
        "camera": sample_dir / "00_observation/camera_used_by_agent/camera.pth",
        "source_mask": sample_dir / "01_semantic/camera_used_by_agent" /
                       f"{sample}_moge_to_raw_partial_object_mask.png",
        "semantic": sample_dir / "01_semantic/camera_used_by_agent/img.png",
        "pixal_prior": sample_dir / "02_pixal3d/pixal3d_sampled_100k.ply",
        "pixal_input": sample_dir / "02_pixal3d/pixal3d_input.png",
        "pixal_metadata": sample_dir / "02_pixal3d/pixal3d_metadata.json",
        "pixal_moge_cache": sample_dir / "02_pixal3d/pixal_moge_fp16_observation.npz",
        "frozen_prior": sample_dir / "03_registration/camera1_amplified_registered_100k.ply",
    }


def validate_inputs(sample_dir: Path, paths: dict[str, Path]) -> dict[str, dict]:
    original = checked_json(sample_dir / "manifest.json")
    archived = original["files"]
    result = {}
    for name, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        relative = path.relative_to(sample_dir).as_posix()
        if relative not in archived:
            raise ValueError(f"input is not part of the frozen archive: {relative}")
        digest = sha256(path)
        if digest != archived[relative]["sha256"]:
            raise ValueError(f"frozen input checksum changed: {path}")
        result[name] = {"path": relative, "sha256": digest}
    for name in ("pixal_prior", "frozen_prior"):
        if vertex_count(paths[name]) != 100_000:
            raise ValueError(f"not an ordered 100k carrier: {paths[name]}")
    return result


def run_stage(command: list[str], log: Path) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(command, cwd=ROOT, stdout=handle,
                                   stderr=subprocess.STDOUT, text=True)
    if completed.returncode:
        raise RuntimeError(f"stage exited {completed.returncode}; see {log}")


def output_files(stage_root: Path) -> dict[str, dict]:
    return {
        path.relative_to(stage_root).as_posix(): {
            "bytes": path.stat().st_size, "sha256": sha256(path),
        }
        for path in sorted(stage_root.rglob("*")) if path.is_file()
        and path.name != "rebuild_manifest.json"
    }


def rebuild_one(sample_dir: Path, row: dict, rmbg_model: Path) -> dict:
    dataset, sample = row["dataset"], row["sample"]
    if row["historical_registration"] != "declared_historical_input_unavailable":
        raise ValueError(f"{dataset}:{sample} does not have a missing historical bridge")
    paths = input_paths(sample_dir, sample)
    inputs = validate_inputs(sample_dir, paths)
    stage_root = sample_dir / "03_registration/recomputed_initial"
    native, bridge = stage_root / "native", stage_root / "bridge"
    native_args = [
        sys.executable, "scripts/run_pixal_native_moge_registration.py",
        "--prior", str(paths["pixal_prior"]),
        "--pixal-metadata", str(paths["pixal_metadata"]),
        "--pixal-input", str(paths["pixal_input"]),
        "--cached-moge-observation", str(paths["pixal_moge_cache"]),
        "--rmbg-model", str(rmbg_model),
        "--output-dir", str(native), "--device", "cuda", "--fp16",
    ]
    native_files = [native / "pixal_native_moge_points.ply",
                    native / "pixal_native_moge_info.json",
                    native / "pixal_native_moge_registered_100k.ply",
                    native / "pixal_input_object_mask.png"]
    if not all(path.is_file() and path.stat().st_size > 0 for path in native_files):
        run_stage(native_args, native / "stage.log")
    bridge_args = [
        sys.executable, "scripts/run_pixal_moge_two_camera_bridge.py",
        "--partial", str(paths["partial"]),
        "--point-uv", str(paths["point_uv"]),
        "--source-mask", str(paths["source_mask"]),
        "--target-mask", str(native / "pixal_input_object_mask.png"),
        "--native-moge", str(native / "pixal_native_moge_points.ply"),
        "--native-moge-info", str(native / "pixal_native_moge_info.json"),
        "--pixal-prior", str(paths["pixal_prior"]),
        "--partial-camera", str(paths["camera"]),
        "--saved-view-image", str(paths["semantic"]),
        "--output-dir", str(bridge), "--device", "cpu",
    ]
    bridge_files = [bridge / "two_camera_pixal_moge_info.json",
                    bridge / "two_camera_pixal_moge_registered_100k.ply",
                    bridge / "two_camera_pixal_moge_bridge_registered_100k.ply",
                    bridge / "two_camera_pixal_moge_native_moge_to_partial.npy",
                    bridge / "two_camera_pixal_moge_partial_to_native_moge_matches.npy"]
    if not all(path.is_file() and path.stat().st_size > 0 for path in bridge_files):
        run_stage(bridge_args, bridge / "stage.log")
    for path in (native_files[2], bridge_files[1], bridge_files[2]):
        if vertex_count(path) != 100_000:
            raise ValueError(f"recomputed ordered carrier does not have 100k vertices: {path}")
    native_info = checked_json(native_files[1])
    bridge_info = checked_json(bridge_files[0])
    if native_info.get("ground_truth_cd_emd_used") or bridge_info.get("ground_truth_cd_emd_used"):
        raise ValueError("a registration stage unexpectedly declared GT use")
    if not bridge_info["transform_contract"]["proper_sim3"]:
        raise ValueError("MoGe-to-partial bridge is not a proper Sim(3)")
    matches = int(bridge_info["pixel_matches"]["matched_partial_pixels"])
    if matches < 96:
        raise ValueError(f"insufficient positive pixel matches: {matches}")
    bridge_points = load_points(bridge_files[1])
    frozen_points = load_points(paths["frozen_prior"])
    continuation, rmse = estimate_ordered_similarity(bridge_points, frozen_points)
    diagonal = max(float(np.linalg.norm(np.ptp(frozen_points, axis=0))), 1e-8)
    relative_rmse = rmse / diagonal
    if relative_rmse > 1e-5:
        raise ValueError(f"recomputed bridge does not preserve frozen carrier order: {relative_rmse}")
    np.save(stage_root / "recomputed_bridge_to_frozen_prior_sim3.npy", continuation)
    if not np.all(np.isfinite(continuation)):
        raise ValueError("non-finite continuation transform")
    record = {
        "schema": "compagent.recomputed_moge_partial_bridge.v1",
        "dataset": dataset, "sample": sample,
        "status": "recomputed_from_frozen_inputs_not_historical_original",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "historical_registered_prior": checked_json(sample_dir / "manifest.json")
            ["historical_registration"]["declared_registered_prior"],
        "ground_truth_used": False,
        "native_moge_source": "frozen FP16 Pixal-input MoGe cache; input SHA verified by native stage",
        "input_files": inputs,
        "rmbg_model": str(rmbg_model.resolve()),
        "commands": {"native": native_args, "bridge": bridge_args},
        "validation": {
            "matched_partial_pixels": matches,
            "camera1_to_camera2_mask_iou": bridge_info["camera1_to_camera2"]["foreground_iou"],
            "pixel_match_p90_3d_residual": bridge_info["all_match_residual"]["p90"],
            "proper_sim3": True,
            "bridge_to_frozen_registered_relative_rmse": relative_rmse,
            "bridge_to_frozen_registered_transform":
                "recomputed_bridge_to_frozen_prior_sim3.npy",
            "frozen_refine_and_fusion_unchanged": True,
        },
        "output_files": output_files(stage_root),
    }
    write_json(stage_root / "rebuild_manifest.json", record)
    return {
        "dataset": dataset, "sample": sample, "status": "complete",
        "directory": str(stage_root.relative_to(sample_dir.parents[2])),
        "matched_partial_pixels": matches,
        "bridge_to_frozen_registered_relative_rmse": relative_rmse,
        "files": len(record["output_files"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--rmbg-model", type=Path,
                        default=ROOT.parents[1] / "models/RMBG-2.0")
    parser.add_argument("--only", action="append", default=[],
                        help="Optional dataset:sample; repeat to select several cases")
    parser.add_argument("--workers", type=int, default=1,
                        help="Independent samples in parallel; at most two on the 24GB GPU")
    args = parser.parse_args()
    if not 1 <= args.workers <= 2:
        parser.error("--workers must be one or two")
    root = args.bundle.resolve()
    rows = checked_json(root / "index.json")["samples"]
    selected = [row for row in rows if row["historical_registration"] ==
                "declared_historical_input_unavailable"]
    requested = set(args.only)
    if requested:
        known = {f'{row["dataset"]}:{row["sample"]}' for row in selected}
        if requested - known:
            parser.error(f"unknown/mismatched --only: {sorted(requested - known)}")
        selected = [row for row in selected if f'{row["dataset"]}:{row["sample"]}' in requested]
    if not args.rmbg_model.is_dir():
        raise FileNotFoundError(args.rmbg_model)
    model_weight = args.rmbg_model / "model.safetensors"
    if not model_weight.is_file():
        raise FileNotFoundError(model_weight)
    model_digest = sha256(model_weight)
    code_snapshot = root / "code/scripts/rebuild_paper_bundle_bridges.py"
    archive(Path(__file__).resolve(), code_snapshot, required=True)
    index_path = root / "bridge_rebuild_index.json"
    previous = checked_json(index_path) if index_path.is_file() else {"samples": []}
    results = {f'{row["dataset"]}:{row["sample"]}': row for row in previous["samples"]}
    def process(row: dict) -> dict:
        sample_dir = root / row["directory"]
        try:
            return rebuild_one(sample_dir, row, args.rmbg_model)
        except Exception as error:
            return {"dataset": row["dataset"], "sample": row["sample"],
                    "status": "failed", "error": f"{type(error).__name__}: {error}"}

    def record(result: dict) -> None:
        key = f'{result["dataset"]}:{result["sample"]}'
        if result["status"] == "complete":
            print(f'{key}: complete; {result["matched_partial_pixels"]} pixel matches, '
                  f'continuation relRMSE={result["bridge_to_frozen_registered_relative_rmse"]:.2e}',
                  flush=True)
        else:
            print(f'{key}: failed — {result["error"]}', flush=True)
        results[key] = result
        write_json(index_path, {
            "schema": "compagent.recomputed_moge_partial_bridge_index.v1",
            "historical_bridges_recovered": False,
            "ground_truth_used": False,
            "source_script": str(Path(__file__).resolve()),
            "source_script_sha256": sha256(Path(__file__).resolve()),
            "bundle_script": str(code_snapshot.relative_to(root)),
            "rmbg_model_weight": str(model_weight.resolve()),
            "rmbg_model_weight_sha256": model_digest,
            "samples": [results[name] for name in sorted(results)],
        })

    if args.workers == 1:
        for row in selected:
            record(process(row))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process, row): row for row in selected}
            for future in as_completed(futures):
                record(future.result())
    complete = sum(row["status"] == "complete" for row in results.values())
    print(f"recomputed bridges: {complete}/{len(results)} complete", flush=True)
    if any(row["status"] != "complete" for row in results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
