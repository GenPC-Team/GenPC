#!/usr/bin/env python3
"""Fail when a refactored posterior run changes a frozen carrier.

This is intentionally stricter than aggregate CD/EMD: every ordered carrier
slot is compared.  Pointwise equality implies identical downstream metrics,
while also preventing one sample's improvement from hiding another sample's
regression.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from src.pointcloud_io import load_points


def _discover(root: Path, filename: str) -> dict[str, Path]:
    paths = sorted(root.glob(f"*/{filename}"))
    if not paths:
        raise FileNotFoundError(f"No {filename!r} outputs found below {root}")
    return {path.parent.name: path for path in paths}


def compare_runs(
    baseline_root: Path,
    candidate_root: Path,
    *,
    filename: str,
    absolute_tolerance: float,
    samples: list[str] | None = None,
) -> dict:
    baseline = _discover(baseline_root, filename)
    candidate = _discover(candidate_root, filename)
    if samples is not None:
        selected = {str(sample) for sample in samples}
        baseline = {sample: path for sample, path in baseline.items() if sample in selected}
        candidate = {sample: path for sample, path in candidate.items() if sample in selected}
        absent_from_baseline = sorted(selected - set(baseline))
    else:
        absent_from_baseline = []
    missing = sorted(set(baseline) - set(candidate))
    unexpected = sorted(set(candidate) - set(baseline))
    rows = []
    failures = []
    for sample in sorted(set(baseline) & set(candidate)):
        reference = load_points(baseline[sample])
        refactored = load_points(candidate[sample])
        same_count = len(reference) == len(refactored)
        if same_count:
            error = np.linalg.norm(refactored - reference, axis=1)
            maximum = float(error.max(initial=0.0))
            rmse = float(np.sqrt(np.mean(np.square(error))))
        else:
            maximum = float("inf")
            rmse = float("inf")
        passed = bool(same_count and maximum <= float(absolute_tolerance))
        rows.append({
            "sample_id": sample,
            "baseline": str(baseline[sample].resolve()),
            "candidate": str(candidate[sample].resolve()),
            "baseline_points": int(len(reference)),
            "candidate_points": int(len(refactored)),
            "maximum_pointwise_error": maximum,
            "pointwise_rmse": rmse,
            "passed": passed,
        })
        if not passed:
            failures.append(sample)
    return {
        "baseline_root": str(baseline_root.resolve()),
        "candidate_root": str(candidate_root.resolve()),
        "filename": filename,
        "absolute_tolerance": float(absolute_tolerance),
        "missing_samples": missing,
        "absent_from_baseline": absent_from_baseline,
        "unexpected_samples": unexpected,
        "samples": rows,
        "passed": not absent_from_baseline and not missing and not unexpected and not failures,
        "failed_samples": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--filename", default="posterior_prior_100k.ply")
    parser.add_argument("--absolute-tolerance", type=float, default=1e-8)
    parser.add_argument(
        "--samples", nargs="+",
        help="Optional explicit sample set; unrelated baseline subdirectories are ignored.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if float(args.absolute_tolerance) < 0.0:
        parser.error("--absolute-tolerance must be non-negative")
    report = compare_runs(
        args.baseline_root.resolve(),
        args.candidate_root.resolve(),
        filename=str(args.filename),
        absolute_tolerance=float(args.absolute_tolerance),
        samples=args.samples,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for row in report["samples"]:
        state = "pass" if row["passed"] else "FAIL"
        print(
            f"[{state}] {row['sample_id']}: points={row['candidate_points']} "
            f"max={row['maximum_pointwise_error']:.3e} "
            f"rmse={row['pointwise_rmse']:.3e}",
            flush=True,
        )
    if not report["passed"]:
        raise SystemExit(
            "posterior regression failed: "
            f"absent_from_baseline={report['absent_from_baseline']}, "
            f"missing={report['missing_samples']}, "
            f"unexpected={report['unexpected_samples']}, "
            f"changed={report['failed_samples']}"
        )


if __name__ == "__main__":
    main()
