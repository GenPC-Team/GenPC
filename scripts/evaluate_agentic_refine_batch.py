#!/usr/bin/env python3
"""Offline-only GT comparison for finished Redwood and Custom refinements.

This entrypoint is separate from inference and reads outputs only after the
agent and fixed-three control have finished. No metric affects any action.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_agentic_refine import evaluate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-index", type=Path, required=True)
    parser.add_argument("--fixed-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--existing-agent-root", type=Path,
                        help="Reuse previously completed excluded development cases")
    parser.add_argument("--existing-agent", action="append", default=[],
                        metavar="DATASET:SAMPLE=PLY",
                        help="Explicit completed GPT pilot output for an excluded case")
    parser.add_argument("--fused-root", type=Path,
                        help="Optional post-refine continuous-fusion outputs to evaluate offline")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=16_384)
    parser.add_argument("--seed", type=int, default=6_145)
    args = parser.parse_args()
    existing = {}
    for item in args.existing_agent:
        key, separator, path = item.partition("=")
        if separator != "=" or ":" not in key or not path:
            parser.error(f"invalid --existing-agent: {item}")
        existing[key] = Path(path)
    rows = json.loads(args.agent_index.read_text(encoding="utf-8"))["samples"]
    report: list[dict] = []
    for row in rows:
        dataset, sample = row["dataset"], row["sample"]
        if dataset not in {"redwood", "custom"}:
            continue
        gt = (args.gt_root / "redwood" / "gt" / f"{sample}.ply" if dataset == "redwood"
              else args.gt_root / "custom" / sample / "gt_data" / f"{sample}_gt.ply")
        agent = (args.agent_index.parent / dataset / sample / "agent_selected_posterior_100k.ply")
        if not agent.is_file() and f"{dataset}:{sample}" in existing:
            agent = existing[f"{dataset}:{sample}"]
        if not agent.is_file() and args.existing_agent_root is not None:
            old_name = f"final_{dataset}_{sample}" if dataset == "redwood" else f"final_{sample}"
            agent = args.existing_agent_root / old_name / "agent_selected_posterior_100k.ply"
        fixed = (args.fixed_root / dataset / sample / "round_03" / "posterior_prior_100k.ply")
        if not agent.is_file() or not fixed.is_file() or not gt.is_file():
            report.append({"dataset": dataset, "sample": sample, "status": "missing_output_or_gt",
                           "agent_exists": agent.is_file(), "fixed_exists": fixed.is_file(),
                           "gt_exists": gt.is_file()})
            continue
        print(dataset, sample, flush=True)
        try:
            agent_score = evaluate(agent, gt, args.count, args.seed)
            fixed_score = evaluate(fixed, gt, args.count, args.seed)
            result = {"dataset": dataset, "sample": sample, "status": "evaluated",
                      "agent": agent_score, "fixed_three": fixed_score}
            if args.fused_root is not None:
                fused = (args.fused_root / dataset / sample /
                         "observation_anchored_fused_100k.ply")
                if fused.is_file():
                    result["fused"] = evaluate(fused, gt, args.count, args.seed)
                else:
                    result["fused_missing"] = True
            report.append(result)
        except Exception as error:
            report.append({"dataset": dataset, "sample": sample, "status": "metric_failed",
                           "error": f"{type(error).__name__}: {error}"})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"gt_used_by_agent": False, "results": report},
                                          indent=2) + "\n", encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"gt_used_by_agent": False, "results": report},
                                      indent=2) + "\n", encoding="utf-8")
    csv_path = args.output.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("dataset", "sample", "method", "cd_l1", "cd_l2", "emd"))
        for row in report:
            if row["status"] != "evaluated":
                continue
            for method in ("fixed_three", "agent", "fused"):
                if method not in row:
                    continue
                score = row[method]
                writer.writerow((row["dataset"], row["sample"], method,
                                 score["cd_l1"], score["cd_l2"], score["emd"]))
    print(f"evaluated={sum(r['status'] == 'evaluated' for r in report)}/{len(report)}", flush=True)


if __name__ == "__main__":
    main()
