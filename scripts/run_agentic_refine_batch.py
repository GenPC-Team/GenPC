#!/usr/bin/env python3
"""Resume-safe batch runner for the isolated no-GT refine experiment.

Sources are ordered by priority per dataset, so a newer rerun can supersede an
older package while still using the older one for missing sample IDs. This
script only consumes existing registered priors, partials, cameras, and saved
multiview manifests. It never reads ground truth or evaluation metrics.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "scripts" / "run_agentic_posterior.py"
FUSION_BATCH = ROOT / "scripts" / "fuse_agentic_refine_batch.py"
sys.path.insert(0, str(ROOT))
from src.gpt_refine_agent import PROMPT_VERSION


def _source(text: str) -> tuple[str, Path]:
    dataset, separator, root = text.partition("=")
    if not separator or not dataset or not root:
        raise argparse.ArgumentTypeError("--source must be DATASET=/absolute/source/root")
    path = Path(root).resolve()
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"source root does not exist: {path}")
    return dataset, path


def _inputs(source: Path, sample: str) -> dict[str, Path | None]:
    prior_candidates = (
        source / "reference_registration" / sample / "final" / "camera1_amplified_registered_100k.ply",
        source / "registration_selected" / sample / "camera1_amplified_registered_100k.ply",
    )
    camera_candidates = (
        source / "inputs" / "camera" / sample,
        source / "inputs" / "camera_selected" / sample,
    )
    prior = next((p for p in prior_candidates if p.is_file()), None)
    camera_dir = next((p for p in camera_candidates if (p / "camera.pth").is_file()), None)
    return {
        "prior": prior,
        "partial": source / "inputs" / "partial" / f"{sample}.ply",
        "camera": camera_dir / "camera.pth" if camera_dir else None,
        "semantic": camera_dir / "img.png" if camera_dir else None,
        "multiview_manifest": source / "residuals" / sample / "render" / "render_manifest.json",
        "baseline": source / "posterior" / sample / "round_03" / "posterior_prior_100k.ply",
    }


def _discover(sources: list[tuple[str, Path]]) -> tuple[list[dict], list[dict]]:
    chosen: dict[tuple[str, str], dict] = {}
    incomplete: dict[tuple[str, str], dict] = {}
    for dataset, source in sources:
        for partial in sorted((source / "inputs" / "partial").glob("*.ply")):
            key = (dataset, partial.stem)
            if key in chosen:
                continue
            paths = _inputs(source, partial.stem)
            missing = sorted(k for k, p in paths.items()
                             if k not in ("baseline", "semantic") and
                             (p is None or not p.is_file()))
            if missing:
                # A lower-priority source may have a complete input chain.
                incomplete[key] = {"dataset": dataset, "sample": partial.stem,
                                   "source": str(source), "missing": missing}
                continue
            chosen[key] = {
                "dataset": dataset,
                "sample": partial.stem,
                "source": str(source),
                "inputs": {k: str(p) if p is not None and p.is_file() else None
                           for k, p in paths.items()},
            }
    return ([chosen[key] for key in sorted(chosen)],
            [incomplete[key] for key in sorted(incomplete) if key not in chosen])


def _save(path: Path, rows: list[dict], incomplete: list[dict], *,
          decision_backend: str, gpt_model: str | None,
          gpt_provider: str | None,
          structural_proposal_config: str | None,
          maximum_rounds: int) -> None:
    path.write_text(json.dumps({"ground_truth_used_by_agent": False,
                                "decision_backend": decision_backend,
                                "gpt_model": gpt_model,
                                "gpt_provider": gpt_provider,
                                "gpt_prompt_version": PROMPT_VERSION if decision_backend == "gpt" else None,
                                "structural_proposal_config": structural_proposal_config,
                                "maximum_rounds": maximum_rounds,
                                "updated_utc": datetime.now(timezone.utc).isoformat(),
                                "incomplete_inputs": incomplete,
                                "samples": rows}, indent=2) + "\n", encoding="utf-8")


def _record_completed(row: dict, final: Path, audit_path: Path, status: str) -> None:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    row["status"] = status
    row["final"] = str(final)
    row["accepted_rounds"] = sum(bool(item.get("accepted")) for item in audit["trace"])
    row["coverage_before"] = sum(audit["initial_observation"]["coverage"]) / 4
    row["coverage_after"] = sum(audit["final_observation"]["coverage"]) / 4
    row["p90_before"] = audit["initial_observation"]["partial_to_carrier_p90"]
    row["p90_after"] = audit["final_observation"]["partial_to_carrier_p90"]


def _run_case(row: dict, output: Path, args: argparse.Namespace,
              structural_config: str | None) -> None:
    """Run one independent case; only the caller writes the shared index."""
    case_dir = output / row["dataset"] / row["sample"]
    final = case_dir / "agent_selected_posterior_100k.ply"
    audit_path = case_dir / "agent_trace.json"
    if final.is_file() and audit_path.is_file():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        expected_policy = (f"gpt_vision_no_gt_{PROMPT_VERSION}" if args.decision_backend == "gpt"
                           else "deterministic_no_gt_v1")
        if (audit.get("policy") != expected_policy or audit.get("gpt_model") != args.gpt_model
                or audit.get("gpt_provider") != (args.gpt_provider if args.decision_backend == "gpt" else None)
                or audit.get("maximum_rounds", 3) != args.maximum_rounds):
            raise ValueError(f"existing output uses another agent backend: {case_dir}")
        _record_completed(row, final, audit_path, "completed_existing")
        return
    case_dir.mkdir(parents=True, exist_ok=True)
    inputs = row["inputs"]
    command = [sys.executable, str(AGENT)]
    for name in ("prior", "partial", "camera", "multiview_manifest"):
        command.extend(("--" + name.replace("_", "-"), inputs[name]))
    if inputs["semantic"] is not None:
        command.extend(("--semantic", inputs["semantic"]))
    command.extend(("--config-json", str(ROOT / "configs" / "posterior_mainline.json"),
                    "--output-dir", str(case_dir), "--device", args.device,
                    "--decision-backend", args.decision_backend,
                    "--maximum-rounds", str(args.maximum_rounds)))
    if args.gpt_model is not None:
        command.extend(("--gpt-model", args.gpt_model,
                        "--gpt-provider", args.gpt_provider))
    if structural_config is not None and inputs["semantic"] is not None:
        command.extend(("--structural-proposal-config", structural_config))
    started = time.monotonic()
    try:
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        (case_dir / "run.log").write_text(result.stdout, encoding="utf-8")
        if result.returncode == 0 and final.is_file() and audit_path.is_file():
            _record_completed(row, final, audit_path, "completed")
        else:
            row["status"] = "failed"
            row["exit_code"] = result.returncode
    except Exception as error:
        row["status"] = "failed"
        row["error"] = f"{type(error).__name__}: {error}"
    row["elapsed_seconds"] = round(time.monotonic() - started, 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=_source, action="append", required=True,
                        help="DATASET=/absolute/source/root; repeat in descending priority")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--exclude", action="append", default=[],
                        help="Skip an already-tested DATASET:SAMPLE")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--workers", type=int, default=1,
                        help="Independent per-sample workers; use at most two on a 24GB GPU")
    parser.add_argument("--decision-backend", choices=("deterministic", "gpt"),
                        default="deterministic")
    parser.add_argument("--gpt-model")
    parser.add_argument("--gpt-provider", choices=("codex", "api"), default="codex")
    parser.add_argument("--maximum-rounds", type=int, default=3,
                        help="Safety ceiling; GPT may stop earlier using observed evidence")
    parser.add_argument("--structural-proposal-config", type=Path,
                        help="Opt-in complete-graph proposal route for the GPT controller")
    parser.add_argument("--fusion-output-root", type=Path,
                        help="After GPT refine, run the accepted continuous fusion into this separate root")
    parser.add_argument("--fusion-pilot", action="append", default=[],
                        help="Excluded pilot DATASET:SAMPLE=PLY, passed to the fusion stage")
    args = parser.parse_args()
    if args.decision_backend == "gpt" and not args.gpt_model:
        parser.error("--gpt-model is required with --decision-backend gpt")
    if not 1 <= args.maximum_rounds <= 6:
        parser.error("--maximum-rounds must be between 1 and 6")
    if not 1 <= args.workers <= 2:
        parser.error("--workers must be 1 or 2 (24GB GPU safety limit)")
    if args.fusion_output_root is not None and args.decision_backend != "gpt":
        parser.error("--fusion-output-root currently requires --decision-backend gpt")
    if args.fusion_pilot and args.fusion_output_root is None:
        parser.error("--fusion-pilot requires --fusion-output-root")
    if args.structural_proposal_config is not None and (
        args.decision_backend != "gpt" or not args.structural_proposal_config.is_file()
    ):
        parser.error("--structural-proposal-config requires GPT backend and an existing file")
    structural_config = (str(args.structural_proposal_config.resolve())
                         if args.structural_proposal_config is not None else None)
    rows, incomplete = _discover(args.source)
    excluded = set(args.exclude)
    for row in rows:
        row["status"] = ("excluded_existing_experiment" if
                         f"{row['dataset']}:{row['sample']}" in excluded else "pending")
    print(json.dumps({"discovered": len(rows), "by_dataset": {
        name: sum(row["dataset"] == name for row in rows)
        for name in sorted({row["dataset"] for row in rows})
    }, "excluded": len([r for r in rows if r["status"].startswith("excluded")]),
       "incomplete_inputs": incomplete}, indent=2), flush=True)
    if args.dry_run:
        for row in rows:
            print(row["dataset"], row["sample"], row["status"], row["source"])
        return
    output = args.output_root.resolve()
    provider = args.gpt_provider if args.decision_backend == "gpt" else None
    output.mkdir(parents=True, exist_ok=True)
    index = output / "batch_index.json"
    if index.is_file():
        prior_index = json.loads(index.read_text(encoding="utf-8"))
        prior_backend = prior_index.get("decision_backend", "deterministic")
        if (prior_backend != args.decision_backend or prior_index.get("gpt_model") != args.gpt_model
                or prior_index.get("gpt_provider") != provider
                or prior_index.get("structural_proposal_config") != structural_config
                or prior_index.get("maximum_rounds", 3) != args.maximum_rounds
                or (args.decision_backend == "gpt" and
                    prior_index.get("gpt_prompt_version") != PROMPT_VERSION)):
            raise ValueError("refusing to mix GPT and deterministic results or different models in one output root")
    _save(index, rows, incomplete, decision_backend=args.decision_backend,
          gpt_model=args.gpt_model, gpt_provider=provider,
          structural_proposal_config=structural_config,
          maximum_rounds=args.maximum_rounds)
    pending = [(ordinal, row) for ordinal, row in enumerate(rows, start=1)
               if row["status"] == "pending"]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {}
        for ordinal, row in pending:
            print(f"[{ordinal}/{len(rows)}] queued {row['dataset']}/{row['sample']}", flush=True)
            futures[pool.submit(_run_case, row, output, args, structural_config)] = row
        for future in as_completed(futures):
            row = futures[future]
            future.result()
            print(f"  {row['dataset']}/{row['sample']}: {row['status']} "
                  f"rounds={row.get('accepted_rounds', 0)} "
                  f"elapsed={row.get('elapsed_seconds', 0):.1f}s", flush=True)
            _save(index, rows, incomplete, decision_backend=args.decision_backend,
                  gpt_model=args.gpt_model, gpt_provider=provider,
                  structural_proposal_config=structural_config,
                  maximum_rounds=args.maximum_rounds)
    if args.fusion_output_root is not None:
        command = [sys.executable, str(FUSION_BATCH), "--agent-index", str(index),
                   "--output-root", str(args.fusion_output_root.resolve())]
        for pilot in args.fusion_pilot:
            command.extend(("--pilot", pilot))
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
