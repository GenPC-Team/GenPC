#!/usr/bin/env python3
"""Run frozen, no-GT Redwood10 stage ablations and offline CD/EMD audits."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.mainline_paths import REDWOOD10_SAMPLE_IDS


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relocate(value, old_root: str, new_root: str):
    if isinstance(value, dict):
        return {key: relocate(item, old_root, new_root) for key, item in value.items()}
    if isinstance(value, list):
        return [relocate(item, old_root, new_root) for item in value]
    if isinstance(value, str) and value.startswith(old_root + "/"):
        return new_root + value[len(old_root):]
    return value


def require_100k(path: Path) -> None:
    with path.open("rb") as stream:
        header = stream.read(4096).split(b"end_header", 1)[0]
    if b"element vertex 100000" not in header:
        raise ValueError(f"expected an ordered 100k carrier: {path}")


def run_logged(command: list[str], log: Path, env: dict[str, str]) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"command exited {result.returncode}; see {log}")


def write_comparison(output: Path) -> None:
    variants = ("registered_only", "refined_no_fusion", "registered_plus_fusion", "full")
    results = {name: json.loads((output / f"{name}_metrics.json").read_text(encoding="utf-8"))
               for name in variants}
    lookup = {name: {row["sample_id"]: row for row in result["samples"]}
              for name, result in results.items()}
    rows = []
    for sample in REDWOOD10_SAMPLE_IDS:
        row = {"sample": sample}
        for name in variants:
            values = lookup[name][sample]
            row[f"{name}_cd_l1_x100"] = values["cd_l1_x1e2"]
            row[f"{name}_emd_x100"] = values["emd_x1e2"]
        rows.append(row)
    mean = {"sample": "mean"}
    for name in variants:
        summary = results[name]["summary"]
        mean[f"{name}_cd_l1_x100"] = summary["mean_cd_l1_x1e2"]
        mean[f"{name}_emd_x100"] = summary["mean_emd_x1e2"]
    fields = list(rows[0])
    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows([*rows, mean])
    deltas = {name: {
        "cd_l1_x100": mean[f"{name}_cd_l1_x100"] - mean["full_cd_l1_x100"],
        "emd_x100": mean[f"{name}_emd_x100"] - mean["full_emd_x100"],
    } for name in variants if name != "full"}
    (output / "comparison.json").write_text(
        json.dumps({"metric_count": 16384, "seed": 6145, "rows": rows,
                    "mean": mean, "mean_delta_ablation_minus_full": deltas}, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=ROOT / "workspace/redwood10_final")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--aggregate-only", action="store_true")
    args = parser.parse_args()
    package = args.package.resolve()
    output = (args.output_dir or package / "ablations").resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.aggregate_only:
        write_comparison(output)
        print(f"wrote comparison.csv and comparison.json in {output}")
        return

    records = {}
    for sample in REDWOOD10_SAMPLE_IDS:
        case = package / sample
        registered = case / "registration" / sample / "final/camera1_amplified_registered_100k.ply"
        refined = case / "refinement" / sample / "agent_selected_posterior_100k.ply"
        full = case / "fusion" / sample / "observation_anchored_fused_100k.ply"
        partial = case / "inputs" / "partial" / f"{sample}.ply"
        colors = case / "inputs" / "pixal" / sample / "pixal3d_sampled_100k.ply"
        for path in (registered, refined, full, partial, colors):
            if not path.is_file():
                raise FileNotFoundError(path)
        for path in (registered, refined, full, colors):
            require_100k(path)
        source_manifest = case / "residuals" / sample / "render/render_manifest.json"
        source = json.loads(source_manifest.read_text(encoding="utf-8"))
        old_root = str(Path(source["registered_carrier"]).parents[3])
        relocated = relocate(source, old_root, str(case))
        manifest = output / "no_refinement_fused" / sample / "render_manifest.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(relocated, indent=2) + "\n", encoding="utf-8")
        records[sample] = {
            "partial": str(partial), "partial_sha256": sha256(partial),
            "registered": str(registered), "registered_sha256": sha256(registered),
            "refined": str(refined), "refined_sha256": sha256(refined),
            "full": str(full), "full_sha256": sha256(full),
            "same_view_manifest": str(manifest),
            "same_view_manifest_sha256": sha256(manifest),
        }
    protocol = {
        "schema": "compagent.redwood10_ablations.v1",
        "ground_truth_used_for_inference": False,
        "reference": "frozen full route in redwood10_final",
        "variants": {
            "registered_only": "saved registered Pixal carrier; no refinement or fusion",
            "refined_no_fusion": "saved GPT-6 Sol refined carrier; no fusion",
            "registered_plus_fusion": "continuous observation fusion of registered carrier; no refinement",
            "full": "saved GPT-6 Sol refinement followed by continuous fusion",
        },
        "metric": {"count": 16384, "seed": 6145, "scale": 100,
                   "ground_truth_root": str((ROOT / "data/redwood/gt").resolve())},
        "samples": records,
    }
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")
    if args.prepare_only:
        print(f"prepared {len(records)} frozen Redwood10 cases in {output}")
        return

    env = os.environ.copy()
    for sample in REDWOOD10_SAMPLE_IDS:
        case = package / sample
        target = output / "no_refinement_fused" / sample
        fused = target / "observation_anchored_fused_100k.ply"
        if not fused.is_file():
            command = [sys.executable, str(ROOT / "scripts/run_observation_anchored_fusion.py"),
                       "--posterior", records[sample]["registered"],
                       "--partial", records[sample]["partial"],
                       "--multiview-manifest", records[sample]["same_view_manifest"],
                       "--output-dir", str(target), "--mode", "continuous",
                       "--carrier-colors-from", str(case / "inputs/pixal" / sample / "pixal3d_sampled_100k.ply")]
            run_logged(command, target / "fusion.log", env)
        require_100k(fused)
        records[sample]["registered_plus_fusion"] = str(fused)
        records[sample]["registered_plus_fusion_sha256"] = sha256(fused)
        print(f"fusion {sample} complete", flush=True)

    templates = {
        "registered_only": (package, "{sample}/registration/{sample}/final/camera1_amplified_registered_100k.ply"),
        "refined_no_fusion": (package, "{sample}/refinement/{sample}/agent_selected_posterior_100k.ply"),
        "registered_plus_fusion": (output / "no_refinement_fused", "{sample}/observation_anchored_fused_100k.ply"),
        "full": (package, "{sample}/fusion/{sample}/observation_anchored_fused_100k.ply"),
    }
    summaries = {}
    for variant, (prediction_root, prediction_template) in templates.items():
        metric = output / f"{variant}_metrics.json"
        command = [sys.executable, str(ROOT / "scripts/evaluate_completions.py"),
                   "--prediction-root", str(prediction_root),
                   "--prediction-template", prediction_template,
                   "--ground-truth-root", str(ROOT / "data/redwood/gt"),
                   "--output", str(metric), "--count", "16384", "--seed", "6145",
                   "--samples", *REDWOOD10_SAMPLE_IDS]
        run_logged(command, output / f"{variant}_metrics.log", env)
        result = json.loads(metric.read_text(encoding="utf-8"))
        if len(result["samples"]) != len(REDWOOD10_SAMPLE_IDS):
            raise ValueError(f"incomplete metric rows for {variant}")
        summaries[variant] = result["summary"]
        print(f"metric {variant}: {result['summary']}", flush=True)
    protocol["summary"] = summaries
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")
    write_comparison(output)


if __name__ == "__main__":
    main()
