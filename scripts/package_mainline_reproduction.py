#!/usr/bin/env python3
"""Build a self-contained Pixal3D-to-posterior reproduction package.

The package intentionally copies files instead of linking them.  Old workspace
experiments may therefore be removed after the generated checksum manifest has
been verified.  Ground truth and metric-time assets are not packaged because
they are not part of inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "workspace" / "posterior_mainline_generalization_20260923"
DEFAULT_RESULTS = ROOT / "workspace" / "posterior_refactor_regression_20260925"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve(path: str | Path) -> Path:
    value = Path(path).expanduser()
    return (ROOT / value).resolve() if not value.is_absolute() else value.resolve()


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("samples", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError(f"case manifest must contain a samples list: {path}")
    return [dict(record) for record in records]


def _inputs_root(camera_path: Path) -> Path:
    for parent in camera_path.parents:
        if parent.name == "inputs":
            return parent
    raise ValueError(f"camera path is not inside an inputs directory: {camera_path}")


def _copy_file(
    source: Path,
    destination: Path,
    records: list[dict[str, Any]],
    *,
    role: str,
) -> None:
    source = source.resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_hash = _sha256(source)
    if destination.is_file() and _sha256(destination) == source_hash:
        pass
    else:
        shutil.copy2(source, destination)
    destination_hash = _sha256(destination)
    if source_hash != destination_hash:
        raise RuntimeError(f"copy checksum mismatch: {source} -> {destination}")
    records.append({
        "path": str(destination),
        "role": str(role),
        "bytes": int(destination.stat().st_size),
        "sha256": destination_hash,
        "source": str(source),
    })


def _copy_directory_files(
    source_root: Path,
    destination_root: Path,
    records: list[dict[str, Any]],
    *,
    role: str,
) -> None:
    if not source_root.is_dir():
        raise FileNotFoundError(source_root)
    for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
        _copy_file(
            source,
            destination_root / source.relative_to(source_root),
            records,
            role=role,
        )


def _portable_multiview_manifest(source: Path) -> dict[str, Any]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    views = []
    for view in payload.get("views", []):
        views.append({
            key: value for key, value in view.items()
            if key not in {"image", "mask", "depth", "depth_preview"}
        })
    if len(views) != 4 or any("camera_pose" not in view for view in views):
        raise ValueError(f"expected four saved camera poses: {source}")
    keep = (
        "method", "resolution", "field_of_view_degrees", "centre", "radius",
        "front_direction", "up_direction", "view_selection", "ground_truth_used",
    )
    result = {key: payload[key] for key in keep if key in payload}
    result.update({
        "schema": "compagent.portable_multiview_cameras.v1",
        "source_manifest_sha256": _sha256(source),
        "views": views,
    })
    return result


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _git_state() -> dict[str, Any]:
    def command(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=ROOT, check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout.strip()

    return {
        "commit": command("rev-parse", "HEAD"),
        "branch": command("branch", "--show-current"),
        "dirty": bool(command("status", "--porcelain")),
    }


def _result_files(results_root: Path, dataset: str, sample: str) -> dict[str, Path]:
    review = results_root / "review" / dataset / sample
    names = {
        "final_posterior": "01_final_posterior.ply",
        "before_overlay": "02_before_registered_partial_overlay.ply",
        "after_overlay": "03_after_posterior_partial_overlay.ply",
        "camera1_projection": "04_camera1_projection.png",
        "multiview_projection": "05_multiview_projection.png",
        "run_info": "06_run_info.json",
    }
    return {role: (review / name).resolve() for role, name in names.items()}


def _package_sample(
    *,
    dataset: str,
    record: dict[str, Any],
    output_root: Path,
    results_root: Path,
    file_records: list[dict[str, Any]],
) -> dict[str, Any]:
    sample = str(record["sample_id"])
    camera = _resolve(record["camera"])
    partial = _resolve(record["partial"])
    prior = _resolve(record["prior"])
    multiview = _resolve(record["multiview_manifest"])
    inputs_root = _inputs_root(camera)
    camera_source = inputs_root / "camera" / sample
    pixal_source = inputs_root / "pixal" / sample
    sample_root = output_root / dataset

    _copy_directory_files(
        camera_source, sample_root / "inputs" / "camera" / sample,
        file_records, role="camera1_observation",
    )
    _copy_directory_files(
        pixal_source, sample_root / "inputs" / "pixal" / sample,
        file_records, role="pixal3d_prior",
    )
    _copy_file(
        partial, sample_root / "inputs" / "partial" / f"{sample}.ply",
        file_records, role="partial_observation",
    )

    portable_manifest_path = (
        sample_root / "residuals" / sample / "render" / "render_manifest.json"
    )
    _write_json(portable_manifest_path, _portable_multiview_manifest(multiview))
    file_records.append({
        "path": str(portable_manifest_path),
        "role": "portable_multiview_cameras",
        "bytes": int(portable_manifest_path.stat().st_size),
        "sha256": _sha256(portable_manifest_path),
        "source": str(multiview),
    })

    registration_root = sample_root / "reference_registration" / sample / "final"
    _copy_directory_files(
        prior.parent, registration_root, file_records, role="reference_registration",
    )
    result_root = sample_root / "reference_result" / sample
    packaged_results = {}
    for role, source in _result_files(results_root, dataset, sample).items():
        destination = result_root / source.name
        _copy_file(source, destination, file_records, role=f"reference_{role}")
        packaged_results[role] = str(destination.relative_to(output_root))

    required = {
        "camera": camera_source / "camera.pth",
        "point_uv": camera_source / "point_uv.npy",
        "semantic": camera_source / "img.png",
        "object_mask": camera_source / f"{sample}_moge_to_raw_partial_object_mask.png",
        "pixal_glb": pixal_source / "pixal3d.glb",
        "pixal_carrier": pixal_source / "pixal3d_sampled_100k.ply",
        "pixal_input": pixal_source / "pixal3d_input.png",
        "pixal_metadata": pixal_source / "pixal3d_metadata.json",
        "pixal_moge": pixal_source / "pixal_moge_fp16_observation.npz",
    }
    missing = [f"{key}: {path}" for key, path in required.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"{dataset}/{sample} missing retained inputs: {missing}")
    return {
        "sample_id": sample,
        "dataset": dataset,
        "posterior_route": (
            "residual_proximal_visual_override"
            if dataset == "custom" and sample == "cartoon_fox"
            else "shared_posterior_mainline"
        ),
        "paths": {
            "pixal_root": str((sample_root / "inputs" / "pixal" / sample).relative_to(output_root)),
            "camera_root": str((sample_root / "inputs" / "camera" / sample).relative_to(output_root)),
            "partial": str((sample_root / "inputs" / "partial" / f"{sample}.ply").relative_to(output_root)),
            "multiview_manifest": str(portable_manifest_path.relative_to(output_root)),
            "reference_registration": str(
                (registration_root / prior.name).relative_to(output_root)
            ),
            **packaged_results,
        },
    }


def _readme() -> str:
    return """# CompAgent Pixal3D-stage reproduction package

This directory is self-contained for the inference stages beginning with the
retained Pixal3D asset. It contains no GT and no metric-driven selection.

For each Redwood/Custom sample it retains:

- Camera-1 depth/semantic images, camera parameters, UV map and object mask;
- the partial observation;
- Pixal3D input, metadata, textured GLB, ordered 100k carrier and native MoGe cache;
- a portable four-view camera manifest (FOV plus four camera poses);
- the accepted registered prior as a numerical checkpoint;
- the final posterior and the before/after partial-complete overlays.

Run from the GenPC repository root:

```bash
/opt/data/private/cr/miniconda3/envs/genpc/bin/python \
  scripts/reproduce_packaged_mainline.py \
  --bundle-root workspace/compagent_pixal_reproduction_20260925 \
  --dataset redwood --samples 01184 --output-root /tmp/compagent_replay_01184
```

The replay first reconstructs Pixal--MoGe--partial registration from the
retained Pixal3D stage, then runs the frozen posterior solver with the saved
four cameras. `manifest.json` stores SHA-256 for every copied file. The Fox
visual-best result is explicitly recorded as the accepted residual-proximal
visual override; every other sample uses the shared posterior mainline.

`paper_assets/` contains the retained Fox paper visualizations and textured
overlay assets. They are not read by inference.
"""


def _preserve_artifact(
    specification: str,
    output_root: Path,
    file_records: list[dict[str, Any]],
) -> None:
    if "=" not in specification:
        raise ValueError(f"preserved artifact must use SOURCE=DEST syntax: {specification}")
    source_text, destination_text = specification.split("=", 1)
    source = _resolve(source_text)
    destination = output_root / destination_text
    if source.is_dir():
        _copy_directory_files(
            source, destination, file_records, role="preserved_paper_artifact",
        )
    elif source.is_file():
        _copy_file(source, destination, file_records, role="preserved_paper_artifact")
    else:
        raise FileNotFoundError(source)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redwood-cases", type=Path,
                        default=DEFAULT_SOURCE / "redwood_cases.json")
    parser.add_argument("--custom-cases", type=Path,
                        default=DEFAULT_SOURCE / "custom_cases.json")
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--preserve", action="append", default=[], metavar="SOURCE=DEST",
        help="Copy an additional paper/reproduction artifact into the package.",
    )
    args = parser.parse_args()

    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    file_records: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    for dataset, manifest_path in (
        ("redwood", args.redwood_cases.resolve()),
        ("custom", args.custom_cases.resolve()),
    ):
        for record in _load_cases(manifest_path):
            samples.append(_package_sample(
                dataset=dataset,
                record=record,
                output_root=output_root,
                results_root=args.results_root.resolve(),
                file_records=file_records,
            ))

    config_sources = {
        "posterior_mainline.json": ROOT / "configs" / "posterior_mainline.json",
        "registration_broad_continuation.json": (
            ROOT / "configs" / "registration_broad_continuation.json"
        ),
        "residual_proximal_proposal.json": (
            ROOT / "workspace" / "fox_posterior_adaptation_20260921"
            / "high_resolution_expansive_stable_profile.json"
        ),
    }
    for name, source in config_sources.items():
        _copy_file(source, output_root / "configs" / name, file_records, role="inference_config")

    report_sources = (
        args.results_root / "redwood_pointwise_regression.json",
        args.results_root / "custom_pointwise_regression.json",
        DEFAULT_SOURCE / "redwood_metrics.json",
        DEFAULT_SOURCE / "custom_metrics.json",
        DEFAULT_SOURCE / "cartoon_fox_visual_best_metrics.json",
    )
    for source in report_sources:
        if source.is_file():
            _copy_file(source, output_root / "reports" / source.name, file_records, role="audit_report")
    for specification in args.preserve:
        _preserve_artifact(str(specification), output_root, file_records)

    (output_root / "README.md").write_text(_readme(), encoding="utf-8")
    file_records.append({
        "path": str(output_root / "README.md"), "role": "documentation",
        "bytes": int((output_root / "README.md").stat().st_size),
        "sha256": _sha256(output_root / "README.md"), "source": None,
    })
    manifest = {
        "schema": "compagent.pixal3d_reproduction.v1",
        "ground_truth_in_package": False,
        "inference_starts_at": "retained_pixal3d_asset",
        "git": _git_state(),
        "sample_count": len(samples),
        "samples": samples,
        "files": sorted((
            {**record, "path": str(Path(record["path"]).relative_to(output_root))}
            for record in file_records
        ), key=lambda item: item["path"]),
    }
    _write_json(output_root / "manifest.json", manifest)
    print(json.dumps({
        "output_root": str(output_root),
        "samples": len(samples),
        "files": len(file_records),
        "bytes": sum(int(record["bytes"]) for record in file_records),
    }, indent=2))


if __name__ == "__main__":
    main()
