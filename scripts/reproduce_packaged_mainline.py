#!/usr/bin/env python3
"""Replay registration and posterior inference from a packaged Pixal3D stage."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command: list[str]) -> None:
    print(" ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def _load_package(root: Path) -> dict[str, Any]:
    manifest = root / "manifest.json"
    if not manifest.is_file():
        raise FileNotFoundError(manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("schema") != "compagent.pixal3d_reproduction.v1":
        raise ValueError(f"unsupported package schema: {payload.get('schema')}")
    return payload


def _verify_package(root: Path, payload: dict[str, Any]) -> None:
    failures = []
    for record in payload.get("files", []):
        path = root / str(record["path"])
        if not path.is_file() or _sha256(path) != str(record["sha256"]):
            failures.append(str(path))
    if failures:
        raise RuntimeError(f"package verification failed for {len(failures)} file(s): {failures[:5]}")


def _selected_samples(
    payload: dict[str, Any], dataset: str, requested: list[str] | None,
) -> list[str]:
    available = [
        str(record["sample_id"]) for record in payload["samples"]
        if record["dataset"] == dataset
    ]
    selected = available if requested is None else [str(sample) for sample in requested]
    missing = sorted(set(selected) - set(available))
    if missing:
        raise ValueError(f"samples absent from {dataset} package: {missing}")
    return selected


def _case(
    bundle: Path,
    dataset: str,
    sample: str,
    selected_registration_root: Path,
) -> dict[str, str]:
    dataset_root = bundle / dataset
    reproduced = (
        selected_registration_root / sample / "camera1_amplified_registered_100k.ply"
    )
    reference = (
        dataset_root / "reference_registration" / sample / "final"
        / "camera1_amplified_registered_100k.ply"
    )
    prior = reproduced if reproduced.is_file() else reference
    return {
        "sample_id": sample,
        "prior": str(prior.resolve()),
        "partial": str((dataset_root / "inputs" / "partial" / f"{sample}.ply").resolve()),
        "camera": str((dataset_root / "inputs" / "camera" / sample / "camera.pth").resolve()),
        "semantic": str((dataset_root / "inputs" / "camera" / sample / "img.png").resolve()),
        "multiview_manifest": str(
            (dataset_root / "residuals" / sample / "render" / "render_manifest.json").resolve()
        ),
    }


def _reference_final(bundle: Path, dataset: str, sample: str) -> Path:
    root = bundle / dataset / "reference_result" / sample
    names = (
        "posterior_expert_distilled_100k.ply",
        "posterior_prior_100k.ply",
    )
    for name in names:
        path = root / name
        if path.is_file():
            return path
    raise FileNotFoundError(f"reference posterior missing for {dataset}/{sample}")


def _compare(label: str, candidate: Path, reference: Path) -> dict[str, Any]:
    candidate_hash = _sha256(candidate)
    reference_hash = _sha256(reference)
    result = {
        "stage": label,
        "candidate": str(candidate),
        "reference": str(reference),
        "candidate_sha256": candidate_hash,
        "reference_sha256": reference_hash,
        "byte_identical": candidate_hash == reference_hash,
    }
    print(json.dumps(result, indent=2), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--dataset", choices=("redwood", "custom"), required=True)
    parser.add_argument("--samples", nargs="+")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--stage", choices=("all", "registration", "posterior"), default="all")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--sample-workers", type=int, default=1)
    parser.add_argument("--skip-package-verification", action="store_true")
    args = parser.parse_args()

    bundle = args.bundle_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    payload = _load_package(bundle)
    if not args.skip_package_verification:
        _verify_package(bundle, payload)
    samples = _selected_samples(payload, str(args.dataset), args.samples)
    dataset_root = bundle / str(args.dataset)
    registration_root = output_root / "registration_initial"
    selected_registration_root = output_root / "registration_selected"

    if args.stage in {"all", "registration"}:
        _run([
            sys.executable, str(ROOT / "scripts" / "run_fixed_pixal_moge_registration.py"),
            "--samples", *samples,
            "--pixal-root", str(dataset_root / "inputs" / "pixal"),
            "--camera-root", str(dataset_root / "inputs" / "camera"),
            "--partial-root", str(dataset_root / "inputs" / "partial"),
            "--output-root", str(registration_root),
            "--sample-workers", str(int(args.sample_workers)),
        ])
        for sample in samples:
            _run([
                sys.executable,
                str(ROOT / "scripts" / "run_camera1_amplified_sim3_refine.py"),
                "--partial", str(dataset_root / "inputs" / "partial" / f"{sample}.ply"),
                "--registered-prior", str(
                    registration_root / sample / "final"
                    / "camera1_amplified_registered_100k.ply"
                ),
                "--camera", str(
                    dataset_root / "inputs" / "camera" / sample / "camera.pth"
                ),
                "--semantic", str(
                    dataset_root / "inputs" / "camera" / sample / "img.png"
                ),
                "--output-dir", str(selected_registration_root / sample),
                "--search-points", "32000",
                "--candidate-workers", "2",
                "--levels-json", str(
                    bundle / "configs" / "registration_broad_continuation.json"
                ),
                "--monotonic",
                "--max-passes", "6",
                "--minimum-relative-improvement", "0.025",
                "--device", "cpu",
            ])

    comparisons: list[dict[str, Any]] = []
    for sample in samples:
        candidate = (
            selected_registration_root / sample / "camera1_amplified_registered_100k.ply"
        )
        if candidate.is_file():
            reference = (
                dataset_root / "reference_registration" / sample / "final"
                / "camera1_amplified_registered_100k.ply"
            )
            comparisons.append(_compare(f"registration/{sample}", candidate, reference))

    if args.stage in {"all", "posterior"}:
        generic = [sample for sample in samples if sample != "cartoon_fox"]
        case_manifest = output_root / "posterior_cases.json"
        case_manifest.parent.mkdir(parents=True, exist_ok=True)
        case_manifest.write_text(json.dumps({
            "samples": [
                _case(bundle, str(args.dataset), sample, selected_registration_root)
                for sample in generic
            ]
        }, indent=2) + "\n", encoding="utf-8")
        if generic:
            _run([
                sys.executable, str(ROOT / "scripts" / "run_posterior_adapter_batch.py"),
                "--case-manifest", str(case_manifest),
                "--output-root", str(output_root / "posterior"),
                "--sample-workers", str(int(args.sample_workers)),
                "--device", str(args.device),
                "--output-profile", "lean",
                "--overwrite",
                "--config-json", str(bundle / "configs" / "posterior_mainline.json"),
            ])
        if "cartoon_fox" in samples:
            fox = _case(
                bundle, str(args.dataset), "cartoon_fox", selected_registration_root,
            )
            _run([
                sys.executable,
                str(ROOT / "scripts" / "run_residual_proximal_prior_adaptation.py"),
                "--prior", fox["prior"],
                "--partial", fox["partial"],
                "--camera", fox["camera"],
                "--semantic", fox["semantic"],
                "--multiview-manifest", fox["multiview_manifest"],
                "--proposal-config", str(bundle / "configs" / "residual_proximal_proposal.json"),
                "--proposal-rounds", "6",
                "--output-dir", str(output_root / "posterior" / "cartoon_fox_visual_best"),
                "--device", str(args.device),
            ])
        for sample in samples:
            candidate = (
                output_root / "posterior" / "cartoon_fox_visual_best" / "prior_projection"
                / "posterior_expert_distilled_100k.ply"
                if sample == "cartoon_fox"
                else output_root / "posterior" / sample / "posterior_prior_100k.ply"
            )
            if candidate.is_file():
                comparisons.append(_compare(
                    f"posterior/{sample}", candidate,
                    _reference_final(bundle, str(args.dataset), sample),
                ))

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "reproduction_report.json").write_text(json.dumps({
        "bundle": str(bundle),
        "dataset": str(args.dataset),
        "samples": samples,
        "stage": str(args.stage),
        "all_byte_identical": bool(comparisons) and all(
            bool(record["byte_identical"]) for record in comparisons
        ),
        "comparisons": comparisons,
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
