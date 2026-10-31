#!/usr/bin/env python3
"""Collect frozen GPT-refine inputs and results into a portable paper bundle.

The bundle is an archive, not an inference output. Source files are copied
byte-for-byte, and each destination is checksum-verified. GT is never copied.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
OBSERVATION_NAMES = {
    "raw_depth.png", "depth.png", "depth.npy", "mask.png", "camera.pth",
    "camera.json", "point_uv.npy", "viewpoint.npy",
}
EXCLUDED_CAMERA_NAMES = {"qwen_failed_control.png", "qwen_edit_stage1.png"}
EXPERT_NAMES = {
    "expert_distillation_report.json", "expert_local_fit_100k.ply",
    "low_frequency_prior_100k.ply", "posterior_expert_distilled_100k.ply",
    "posterior_expert_distilled_views.png",
    "partial_gray_posterior_expert_distilled_red.ply",
}
FUSED_NAMES = (
    "observation_anchored_fused_100k.ply",
    "observation_anchored_fused_100k_pixal_texture.ply",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def vertex_count(path: Path) -> int:
    with path.open("rb") as handle:
        for line in handle:
            if line.startswith(b"element vertex "):
                return int(line.split()[-1])
            if line.strip() == b"end_header":
                break
    raise ValueError(f"no vertex count in {path}")


def safe_name(value: str) -> str:
    if not value or value in {".", ".."} or Path(value).name != value:
        raise ValueError(f"unsafe dataset/sample name: {value!r}")
    return value


def archive(source: Path, destination: Path, *, required: bool = False) -> dict | None:
    """Copy atomically, never overwrite a different file, and retain provenance."""
    if not source.is_file():
        if required:
            raise FileNotFoundError(source)
        return None
    source_hash = sha256(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or sha256(destination) != source_hash:
            raise FileExistsError(f"bundle destination differs: {destination}")
    else:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".copy-", delete=False) as temp:
            temporary = Path(temp.name)
        try:
            shutil.copy2(source, temporary)
            if sha256(temporary) != source_hash:
                raise IOError(f"checksum mismatch while copying {source}")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return {"source": str(source.resolve()), "bytes": source.stat().st_size,
            "sha256": source_hash}


def add_file(files: dict, sample_root: Path, stage: str, source: Path,
             relative: str | Path, *, required: bool = False) -> str | None:
    relative = Path(stage) / relative
    result = archive(source, sample_root / relative, required=required)
    if result is None:
        return None
    files[relative.as_posix()] = result
    return relative.as_posix()


def add_directory(files: dict, sample_root: Path, stage: str, source_dir: Path,
                  *, names: set[str] | None = None, exclude: set[str] | None = None) -> None:
    if not source_dir.is_dir():
        return
    for source in sorted(source_dir.iterdir()):
        if not source.is_file() or (names is not None and source.name not in names):
            continue
        if exclude and source.name in exclude:
            continue
        add_file(files, sample_root, stage, source, source.name)


def add_tree(files: dict, sample_root: Path, stage: str, source_dir: Path) -> int:
    """Archive a small historical stage tree without retaining symlink dependencies."""
    if not source_dir.is_dir():
        return 0
    count = 0
    for source in sorted(source_dir.rglob("*")):
        if source.is_file():
            relative = source.relative_to(source_dir)
            add_file(files, sample_root, stage, source, relative)
            count += 1
    return count


def checked_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_replay(sample_root: Path, replay: dict, trace: dict) -> Path:
    """Save an independent agent replay command that never overwrites the archive."""
    command = [
        "/opt/data/private/cr/miniconda3/envs/genpc/bin/python",
        "scripts/run_agentic_posterior.py",
    ]
    for option, key in (
        ("--prior", "prior"), ("--partial", "partial"),
        ("--camera", "camera"), ("--semantic", "semantic"),
        ("--multiview-manifest", "multiview_manifest"),
        ("--config-json", "config_json"),
        ("--structural-proposal-config", "structural_proposal_config"),
    ):
        if replay.get(key):
            command.extend((option, '${sample_dir}/' + str(replay[key])))
    command.extend(("--output-dir", "${sample_dir}/replay_output",
                    "--decision-backend", "gpt",
                    "--gpt-model", str(trace["gpt_model"]),
                    "--gpt-provider", str(trace["gpt_provider"]),
                    "--maximum-rounds", str(trace["maximum_rounds"]),
                    "--view-policy", str(trace["view_policy"]),
                    "--maximum-active-views", str(trace["maximum_active_views"]),
                    "--minimum-reference-coverage", str(trace["minimum_reference_coverage"])))
    quoted = [f'"{value}"' if value.startswith("${sample_dir}/") else shlex.quote(value)
              for value in command]
    script = sample_root / "replay_agent.sh"
    script.write_text(
        '#!/bin/sh\nset -eu\n'
        'sample_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        'bundle_root=$(CDPATH= cd -- "${sample_dir}/../../.." && pwd)\n'
        'cd "${bundle_root}/code"\n'
        + ' \\\n  '.join(quoted) + '\n', encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def package_sample(row: dict, fusion_row: dict, agent_root: Path, sample_root: Path,
                   configs: dict[str, str]) -> dict:
    dataset, sample = safe_name(row["dataset"]), safe_name(row["sample"])
    if row["status"] not in {"completed", "completed_existing"}:
        raise ValueError(f"unfinished agent result: {dataset}/{sample}")
    if fusion_row["status"] not in {"completed", "completed_existing"}:
        raise ValueError(f"unfinished fusion result: {dataset}/{sample}")
    inputs = row["inputs"]
    source_root = Path(row["source"])
    files: dict[str, dict] = {}
    replay: dict[str, str | None] = {}

    replay["partial"] = add_file(files, sample_root, "00_observation",
                                 Path(inputs["partial"]), "partial.ply", required=True)
    camera_dir = Path(inputs["camera"]).parent
    add_directory(files, sample_root, "00_observation/camera_used_by_agent",
                  camera_dir, names=OBSERVATION_NAMES)
    replay["camera"] = "00_observation/camera_used_by_agent/camera.pth"
    if replay["camera"] not in files:
        raise FileNotFoundError(inputs["camera"])
    for source in sorted(camera_dir.iterdir()):
        if source.is_file() and source.name not in OBSERVATION_NAMES | EXCLUDED_CAMERA_NAMES:
            add_file(files, sample_root, "01_semantic/camera_used_by_agent",
                     source, source.name)
    selected_dir = source_root / "inputs" / "camera_selected" / sample
    if selected_dir.is_dir() and selected_dir.resolve() != camera_dir.resolve():
        add_directory(files, sample_root, "01_semantic/completion_camera",
                      selected_dir, exclude=EXCLUDED_CAMERA_NAMES)
    if inputs.get("semantic"):
        replay["semantic"] = "01_semantic/camera_used_by_agent/" + Path(inputs["semantic"]).name
        if replay["semantic"] not in files:
            raise FileNotFoundError(inputs["semantic"])
    else:
        replay["semantic"] = None
    add_directory(files, sample_root, "02_pixal3d",
                  source_root / "inputs" / "pixal" / sample)
    for name in ("pixal3d.glb", "pixal3d_sampled_100k.ply", "pixal3d_metadata.json"):
        if f"02_pixal3d/{name}" not in files:
            raise FileNotFoundError(source_root / "inputs" / "pixal" / sample / name)

    prior = Path(inputs["prior"])
    add_directory(files, sample_root, "03_registration", prior.parent)
    replay["prior"] = "03_registration/" + prior.name
    if replay["prior"] not in files:
        raise FileNotFoundError(prior)
    info_path = prior.parent / "camera1_amplified_info.json"
    declared = checked_json(info_path).get("inputs", {}).get("registered_prior") if info_path.is_file() else None
    initial = source_root / "registration_initial" / sample
    declared_path = Path(declared) if declared else None
    bridge_present = bool(declared_path and declared_path.is_file() and
                          initial.is_dir() and declared_path.is_relative_to(initial))
    if bridge_present:
        n_initial = add_tree(files, sample_root, "03_registration/initial", initial)
        replay["historical_registered_prior"] = (
            "03_registration/initial/" + declared_path.relative_to(initial).as_posix()
        )
        bridge_state = "exact_declared_initial_chain_archived"
    else:
        n_initial = 0
        replay["historical_registered_prior"] = None
        bridge_state = "declared_historical_input_unavailable"
    render_manifest = Path(inputs["multiview_manifest"])
    add_directory(files, sample_root, "04_multiview", render_manifest.parent)
    diagnostic = render_manifest.parent.parent / "diagnostic_manifest.json"
    add_file(files, sample_root, "04_multiview", diagnostic, diagnostic.name)
    replay["multiview_manifest"] = "04_multiview/" + render_manifest.name
    if replay["multiview_manifest"] not in files:
        raise FileNotFoundError(render_manifest)

    agent_dir = agent_root / dataset / sample
    add_directory(files, sample_root, "05_refine_agent", agent_dir)
    for candidate in sorted(agent_dir.glob("round_*_structured_expert")):
        add_directory(files, sample_root,
                      f"05_refine_agent/{candidate.name}/prior_projection",
                      candidate / "prior_projection", names=EXPERT_NAMES)
        add_file(files, sample_root, f"05_refine_agent/{candidate.name}",
                 candidate / "run.log", "run.log")
    for name in ("agent_trace.json", "agent_selected_posterior_100k.ply"):
        if f"05_refine_agent/{name}" not in files:
            raise FileNotFoundError(agent_dir / name)

    fusion_dir = Path(fusion_row["fused"]).parent
    add_directory(files, sample_root, "06_fusion", fusion_dir)
    for name in FUSED_NAMES:
        if f"06_fusion/{name}" not in files:
            raise FileNotFoundError(fusion_dir / name)
    if Path(fusion_row["posterior"]).resolve() != Path(row["final"]).resolve():
        raise ValueError(f"fusion input does not match agent output: {dataset}/{sample}")

    for name in ("03_registration/" + prior.name,
                 "05_refine_agent/agent_selected_posterior_100k.ply",
                 *("06_fusion/" + name for name in FUSED_NAMES)):
        if vertex_count(sample_root / name) != 100_000:
            raise ValueError(f"not an ordered 100k carrier: {sample_root / name}")
    trace = checked_json(agent_dir / "agent_trace.json")
    bundle_root = sample_root.parents[2]
    replay["config_json"] = os.path.relpath(bundle_root / configs["posterior_mainline"], sample_root)
    replay["structural_proposal_config"] = (
        os.path.relpath(bundle_root / configs["structural_proposal"], sample_root)
        if inputs.get("semantic") else None
    )
    write_replay(sample_root, replay, trace)
    record = {
        "dataset": dataset, "sample": sample, "status": "complete",
        "source_root": str(source_root.resolve()), "agent_output": str(agent_dir.resolve()),
        "fusion_output": str(fusion_dir.resolve()), "accepted_rounds": row.get("accepted_rounds"),
        "stop_reason": trace.get("stop_reason"), "coverage_before": row.get("coverage_before"),
        "coverage_after": row.get("coverage_after"), "p90_before": row.get("p90_before"),
        "p90_after": row.get("p90_after"), "replay_inputs": replay, "files": files,
        "historical_registration": {
            "status": bridge_state,
            "declared_registered_prior": declared,
            "archived_initial_file_count": n_initial,
        },
        "ground_truth_in_bundle": False,
    }
    write_json(sample_root / "manifest.json", record)
    return {key: record[key] for key in (
        "dataset", "sample", "status", "accepted_rounds", "stop_reason",
        "coverage_before", "coverage_after", "p90_before", "p90_after",
    )} | {"directory": str(sample_root.relative_to(sample_root.parents[2])),
         "historical_registration": bridge_state,
         "file_count": len(files), "bytes": sum(item["bytes"] for item in files.values())}


def readme(index: dict) -> str:
    counts = Counter(row["dataset"] for row in index["samples"])
    bridge = Counter(row["historical_registration"] for row in index["samples"])
    return f"""# GPT v7 Refine Agent — paper artifact bundle

Frozen 2026-10-31 no-GT experiment: {len(index['samples'])} complete input chains
({', '.join(f'{name} {counts[name]}' for name in sorted(counts))}). This directory
is a *copy* of selected source assets, not a replacement for their original
experiments. The 12 older KITTI/Waymo partials without matching complete
priors/manifests are excluded and listed in `source_batch_index.json`.

Each case lives at `samples/<dataset>/<sample>/`. Open its `manifest.json`
for local relative paths, source provenance, byte sizes, SHA-256 checksums,
no-GT observation summary, stop reason, and inputs needed to rerun the
registered-prior-to-posterior stage.

| Stage | Files to inspect |
| --- | --- |
| `00_observation` | Physical `partial.ply`, acquisition depth/mask, saved Camera-1 parameters and UV mapping. |
| `01_semantic` | Frozen completion image `img.png`, prompts, semantic audit, selected completion camera if distinct. These are *upstream* assets, not regenerated by GPT v7. |
| `02_pixal3d` | Pixal input, textured `pixal3d.glb`, ordered 100k sampled prior, model metadata and MoGe observation cache. |
| `03_registration` | Registered 100k prior used by the agent, camera overlay, Sim(3) info and residual. `initial/` also contains the original native MoGe, two-camera bridge, and initial registration wherever their exact declared source still exists. |
| `04_multiview` | Saved four-camera manifest and available prior/depth/mask projections. The agent's per-round boards below are the most direct blue-partial/red-prior residual visualization. |
| `05_refine_agent` | `round_01_before_board.png`, other per-round boards, accepted-round 100k PLYs, `agent_trace.json`, and final `agent_selected_posterior_100k.ply`. Selected structural-expert projections are included, but rejected/internal solver iteration caches are not. |
| `06_fusion` | `observation_anchored_fused_100k.ply` (final geometry), `observation_anchored_fused_100k_pixal_texture.ply` (same 100k geometry with Pixal colour), overlay, four-view projection, anchor arrays and `fusion_info.json`. |

The two final PLYs in `06_fusion` are the paper-ready outputs. The registered
prior in `03_registration` and unfused posterior in `05_refine_agent` show
what refinement and fusion changed. The *point cloud* in
`00_observation/partial.ply` is measured partial input, never GT.

`summary.csv` and `index.json` are no-GT experiment records. Ground truth,
CD and EMD did not enter the agent or fusion. Any offline GT evaluation
should be kept separately and labelled as such. `source_batch_index.json`
and `source_fusion_index.json` are preserved raw provenance snapshots; their
original absolute paths are historical, while per-case `manifest.json` gives
valid paths inside this bundle. Likewise upstream `pixal3d_metadata.json`
and registration-info JSON may contain old absolute paths; use the bundle
manifest for local file discovery. Exact historical initial-registration
chains were archived for {bridge['exact_declared_initial_chain_archived']}
samples; {bridge['declared_historical_input_unavailable']} inherited cases
declare a now-missing upstream file in the source registration metadata.
Those cases remain reproducible from the bundled *registered prior onward*,
but a byte-identical Pixal-to-MoGe bridge replay cannot be guaranteed. Their
individual manifests name the missing historical path. No alternate experiment
was silently substituted.

The preserved source snapshot is in `code/`; `samples/<dataset>/<sample>/replay_agent.sh`
runs one no-GT agent replay into a new `replay_output/` without overwriting
the frozen result. It requires the project Python dependencies, a visible GPU,
and Codex CLI access to the saved GPT model (`gpt-6-sol`). GPT decisions can
vary between replays, so exact output hashes are not promised. Each sample's
`replay_inputs` paths are relative to that sample directory (including
`../../../configs/...`); `manifest.json` records the original SHA-256 for
every archived input and result.

Code revision: `{index['code_revision']}` on branch
`{index['code_branch']}`. Module map: `src/gpt_refine_agent.py` (GPT
observation/decision), `src/posterior_agent.py` (no-GT metrics/verifier),
`scripts/run_agentic_posterior.py` (bounded loop),
`src/posterior_adapter.py` (Partial OT and deformation),
`scripts/fuse_agentic_refine_batch.py` (separate fusion), and
`scripts/package_refine_agent_paper.py` (this archive). Configuration
snapshots are under `configs/`. These code snapshots do not include model
weights or a locked system environment.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-index", type=Path, required=True)
    parser.add_argument("--fusion-index", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    agent_index, fusion_index = checked_json(args.agent_index), checked_json(args.fusion_index)
    fusion_rows = {item["sample"]: item for item in fusion_index["records"]}
    rows = agent_index["samples"]
    if len(rows) != len(fusion_rows):
        raise ValueError("agent and fusion indexes have different sample counts")
    output = args.output_root.resolve()
    if output == args.agent_index.parent.resolve() or output == args.fusion_index.parent.resolve():
        raise ValueError("output cannot replace a source directory")
    output.mkdir(parents=True, exist_ok=True)
    config_sources = {
        "posterior_mainline": ROOT / "configs" / "posterior_mainline.json",
        "structural_proposal": Path(agent_index["structural_proposal_config"]),
    }
    configs = {}
    for name, source in config_sources.items():
        destination = output / "configs" / (name + ".json")
        archive(source, destination, required=True)
        configs[name] = str(destination.relative_to(output))
    code_files = {}
    for folder in ("src", "utils", "scripts", "configs"):
        for source in sorted((ROOT / folder).rglob("*")):
            if not source.is_file() or "__pycache__" in source.parts:
                continue
            if folder in {"src", "utils", "scripts"} and source.suffix != ".py":
                continue
            relative = source.relative_to(ROOT)
            code_files[relative.as_posix()] = archive(source, output / "code" / relative,
                                                      required=True)
    for name, source in (
        ("source_batch_index.json", args.agent_index),
        ("source_fusion_index.json", args.fusion_index),
        ("no_gt_batch_audit.json", args.agent_index.parent.parent / "no_gt_batch_audit.json"),
    ):
        archive(source, output / name, required=True)
    records = []
    for row in rows:
        dataset, sample = safe_name(row["dataset"]), safe_name(row["sample"])
        key = f"{dataset}:{sample}"
        if key not in fusion_rows:
            raise KeyError(f"missing fusion record: {key}")
        sample_root = output / "samples" / dataset / sample
        records.append(package_sample(row, fusion_rows[key], args.agent_index.parent,
                                      sample_root, configs))
        print(f"[{len(records):02d}/{len(rows)}] {key} — {records[-1]['file_count']} files", flush=True)
    code_revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    code_branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    index = {"schema": "compagent.refine_agent_paper_bundle.v1",
             "created_utc": datetime.now(timezone.utc).isoformat(),
             "code_revision": code_revision, "code_branch": code_branch,
             "source_agent_index": str(args.agent_index.resolve()),
             "source_fusion_index": str(args.fusion_index.resolve()),
             "ground_truth_used_by_agent": False, "ground_truth_in_bundle": False,
             "code_files": code_files,
             "samples": records}
    write_json(output / "index.json", index)
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "dataset", "sample", "directory", "status", "accepted_rounds",
            "stop_reason", "coverage_before", "coverage_after", "p90_before",
            "p90_after", "historical_registration", "file_count", "bytes",
        ))
        writer.writeheader()
        writer.writerows(records)
    (output / "README.md").write_text(readme(index), encoding="utf-8")
    print(f"complete: {len(records)} samples, {sum(row['bytes'] for row in records)} bytes", flush=True)


if __name__ == "__main__":
    main()
