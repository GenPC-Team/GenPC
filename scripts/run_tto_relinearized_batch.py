#!/usr/bin/env python3
"""Package and run fixed posterior TTO over retained Redwood/Custom assets.

The source directory is immutable.  For each case this runner first copies its
camera-consistent semantic/Pixal inputs, the selected global registration and
four-view evidence to ``--output-root``; path-bearing JSON files are then made
local to the package.  The copied registered 100k carrier is the input to three rounds
of the class-free residual re-linearization probe.  Execution is deliberately
sequential so a 24 GB GPU sees one PosteriorAdapter process at a time.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "workspace" / "best_redwood_custom_camera1_transport_20260911"
DEFAULT_OUTPUT = ROOT / "workspace" / "tto_relinearized_selected_redwood_custom_20260920"


def _replace_root(value: Any, source: str, destination: str) -> Any:
    if isinstance(value, str):
        return value.replace(source, destination)
    if isinstance(value, list):
        return [_replace_root(item, source, destination) for item in value]
    if isinstance(value, dict):
        return {key: _replace_root(item, source, destination) for key, item in value.items()}
    return value


def _localize_json_paths(package_dataset: Path, source_dataset: Path) -> None:
    source = str(source_dataset.resolve())
    destination = str(package_dataset.resolve())
    for path in package_dataset.rglob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        localized = _replace_root(value, source, destination)
        path.write_text(json.dumps(localized, indent=2) + "\n", encoding="utf-8")


def _registration_root(dataset_root: Path, stage: str) -> Path:
    return dataset_root / f"registration_{stage}"


def _copy_case(
    source_dataset: Path,
    package_dataset: Path,
    sample: str,
    registration_stage: str,
) -> None:
    registration_name = f"registration_{registration_stage}"
    assets = (
        (source_dataset / "inputs" / "camera" / sample, package_dataset / "inputs" / "camera" / sample),
        (source_dataset / "inputs" / "pixal" / sample, package_dataset / "inputs" / "pixal" / sample),
        (
            _registration_root(source_dataset, registration_stage) / sample,
            package_dataset / registration_name / sample,
        ),
        (source_dataset / "residuals" / sample, package_dataset / "residuals" / sample),
    )
    partial_source = source_dataset / "inputs" / "partial" / f"{sample}.ply"
    if not partial_source.is_file():
        raise FileNotFoundError(partial_source)
    for source, destination in assets:
        if not source.is_dir():
            raise FileNotFoundError(source)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    partial_destination = package_dataset / "inputs" / "partial" / partial_source.name
    partial_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(partial_source, partial_destination)
    gt_candidates = (
        source_dataset / "gt" / f"{sample}.ply",
        source_dataset / "gt" / f"{sample}_gt.ply",
    )
    gt_source = next((path for path in gt_candidates if path.is_file()), None)
    if gt_source is not None:
        # Normalize heterogeneous dataset naming inside a standalone package.
        gt_destination = package_dataset / "gt" / f"{sample}.ply"
        gt_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(gt_source, gt_destination)


def _case_paths(
    package_dataset: Path,
    sample: str,
    registration_stage: str,
) -> dict[str, Path]:
    registration_root = _registration_root(package_dataset, registration_stage) / sample
    if registration_stage == "selected":
        prior = registration_root / "camera1_amplified_registered_100k.ply"
    else:
        prior = registration_root / "final" / "camera1_amplified_registered_100k.ply"
    paths = {
        "prior": prior,
        "partial": package_dataset / "inputs" / "partial" / f"{sample}.ply",
        "camera": package_dataset / "inputs" / "camera" / sample / "camera.pth",
        "semantic": package_dataset / "inputs" / "camera" / sample / "img.png",
        "manifest": package_dataset / "residuals" / sample / "render" / "render_manifest.json",
    }
    for name, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"{sample}: missing {name}: {path}")
    return paths


def _samples(source_dataset: Path, registration_stage: str) -> list[str]:
    root = _registration_root(source_dataset, registration_stage)
    result = sorted(path.name for path in root.iterdir() if path.is_dir())
    if not result:
        raise RuntimeError(f"no registration cases under {root}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dataset", choices=("redwood", "custom", "all"), default="all")
    parser.add_argument("--sample", action="append", default=[], help="repeat to restrict to a case")
    parser.add_argument("--outer-rounds", type=int, default=3)
    parser.add_argument("--update-strength", type=float, default=1.0)
    parser.add_argument(
        "--registration-stage",
        choices=("initial", "selected"),
        default="selected",
        help="global carrier to use before residual re-linearization",
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--resume", action="store_true",
        help="retain completed case summaries and run only unfinished cases",
    )
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()) and not (args.overwrite or args.resume):
        raise FileExistsError(
            f"output exists and is non-empty: {output_root}; pass --overwrite or --resume"
        )
    output_root.mkdir(parents=True, exist_ok=True)
    config_source = ROOT / "configs" / "posterior_mainline.json"
    probe_source = ROOT / "scripts" / "probe_iterative_posterior_tto.py"
    shutil.copy2(config_source, output_root / config_source.name)
    shutil.copy2(probe_source, output_root / probe_source.name)

    selected_datasets = ("redwood", "custom") if args.dataset == "all" else (args.dataset,)
    records: list[dict[str, Any]] = []
    for dataset in selected_datasets:
        source_dataset = source_root / dataset
        package_dataset = output_root / dataset
        all_samples = _samples(source_dataset, args.registration_stage)
        selected = [sample for sample in all_samples if not args.sample or sample in set(args.sample)]
        if args.sample and not selected:
            raise ValueError(f"none of {args.sample} are {dataset} samples")
        for sample in selected:
            completed = package_dataset / "tto" / sample / "tto_summary.json"
            if args.resume and completed.is_file():
                print(f"[keep] {dataset}/{sample}", flush=True)
                continue
            print(f"[package] {dataset}/{sample}", flush=True)
            _copy_case(source_dataset, package_dataset, sample, args.registration_stage)
        _localize_json_paths(package_dataset, source_dataset)

        for sample in selected:
            completed = package_dataset / "tto" / sample / "tto_summary.json"
            if args.resume and completed.is_file():
                continue
            paths = _case_paths(package_dataset, sample, args.registration_stage)
            output = package_dataset / "tto" / sample
            if output.exists():
                shutil.rmtree(output)
            command = [
                sys.executable, str(probe_source),
                "--prior", str(paths["prior"]),
                "--partial", str(paths["partial"]),
                "--camera", str(paths["camera"]),
                "--semantic", str(paths["semantic"]),
                "--multiview-manifest", str(paths["manifest"]),
                "--output-dir", str(output),
                "--config-json", str(output_root / config_source.name),
                "--outer-rounds", str(args.outer_rounds),
                "--update-strength", str(args.update_strength),
                "--device", args.device,
            ]
            print(f"[run] {dataset}/{sample}", flush=True)
            subprocess.run(command, check=True)
            summary_path = output / "tto_summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        for sample in selected:
            summary_path = package_dataset / "tto" / sample / "tto_summary.json"
            if not summary_path.is_file():
                continue
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            records.append({
                "dataset": dataset,
                "sample": sample,
                "output": str(summary_path.parent.relative_to(output_root)),
                "best_no_gt_observation_round": summary["best_no_gt_observation_round"],
                "best_no_gt_observation_median": summary["best_no_gt_observation_median"],
            })

    experiment = {
        "method": "fixed_posterior_adapter_test_time_residual_relinearization",
        "strict_zero_shot": True,
        "ground_truth_cd_emd_used": False,
        "source_root": str(source_root),
        "registration_stage": args.registration_stage,
        "config": str((output_root / config_source.name).resolve()),
        "outer_rounds": args.outer_rounds,
        "update_strength": args.update_strength,
        "execution": "sequential_single_gpu",
        "cases": records,
    }
    (output_root / "experiment_manifest.json").write_text(
        json.dumps(experiment, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(experiment, indent=2))


if __name__ == "__main__":
    main()
