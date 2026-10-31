#!/usr/bin/env python3
"""Verify complete carrier outputs and summarize no-reference agent evidence."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re


def _ply_vertices(path: Path) -> int:
    with path.open("rb") as handle:
        header = handle.read(4096).split(b"end_header", 1)[0]
    match = re.search(rb"^element vertex (\d+)$", header, re.MULTILINE)
    if match is None:
        raise ValueError(f"cannot read PLY vertex count: {path}")
    return int(match.group(1))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.batch_index.read_text(encoding="utf-8"))["samples"]
    groups: dict[str, list[dict]] = defaultdict(list)
    issues: list[dict] = []
    for row in rows:
        if not row["status"].startswith("completed"):
            if row["status"] != "excluded_existing_experiment":
                issues.append({"dataset": row["dataset"], "sample": row["sample"],
                               "issue": row["status"]})
            continue
        path = args.batch_index.parent / row["dataset"] / row["sample"]
        final = path / "agent_selected_posterior_100k.ply"
        trace_path = path / "agent_trace.json"
        if not final.is_file() or not trace_path.is_file():
            issues.append({"dataset": row["dataset"], "sample": row["sample"],
                           "issue": "missing_final_or_trace"})
            continue
        vertices = _ply_vertices(final)
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        if vertices != 100_000 or trace.get("carrier_slots") != 100_000:
            issues.append({"dataset": row["dataset"], "sample": row["sample"],
                           "issue": f"carrier_slots={vertices}/{trace.get('carrier_slots')}"})
        chosen_view_counts = [r["active_views"]["view_count"] for r in trace["trace"]
                              if "active_views" in r]
        groups[row["dataset"]].append({
            "sample": row["sample"],
            "accepted_rounds": row.get("accepted_rounds"),
            "view_counts": chosen_view_counts,
            "coverage_gain": row.get("coverage_after", 0) - row.get("coverage_before", 0),
            "p90_reduction": row.get("p90_before", 0) - row.get("p90_after", 0),
            "p90_ratio": row.get("p90_after", 0) / max(row.get("p90_before", 0), 1e-12),
            "final": str(final),
        })
    summary = {}
    for dataset, values in sorted(groups.items()):
        summary[dataset] = {
            "count": len(values),
            "accepted_round_histogram": dict(Counter(v["accepted_rounds"] for v in values)),
            "active_view_histogram": dict(Counter(n for v in values for n in v["view_counts"])),
            "mean_coverage_gain": sum(v["coverage_gain"] for v in values) / len(values),
            "mean_p90_ratio": sum(v["p90_ratio"] for v in values) / len(values),
            "samples": values,
        }
    report = {"ground_truth_used": False, "summary": summary, "issues": issues}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": {k: {field: val for field, val in v.items() if field != "samples"}
                                  for k, v in summary.items()}, "issues": issues}, indent=2), flush=True)


if __name__ == "__main__":
    main()
