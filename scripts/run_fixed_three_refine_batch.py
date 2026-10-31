#!/usr/bin/env python3
"""Run frozen fixed-three posterior controls from an agent batch index.

This comparator has no access to GT or the agent's final output. It reuses
the exact same registered prior, partial, camera and four-view manifest.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "iterative_posterior_tto.py"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-index", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dataset", action="append", required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    rows = json.loads(args.batch_index.read_text(encoding="utf-8"))["samples"]
    selected = [r for r in rows if r["dataset"] in set(args.dataset)]
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    status_path = output / "fixed_three_index.json"
    status: list[dict] = []
    for ordinal, row in enumerate(selected, start=1):
        case_dir = output / row["dataset"] / row["sample"]
        final = case_dir / "round_03" / "posterior_prior_100k.ply"
        if final.is_file():
            record = {"dataset": row["dataset"], "sample": row["sample"],
                      "status": "completed_existing", "final": str(final)}
        else:
            case_dir.mkdir(parents=True, exist_ok=True)
            inputs = row["inputs"]
            command = [sys.executable, str(RUNNER)]
            for key in ("prior", "partial", "camera", "multiview_manifest"):
                command.extend(("--" + key.replace("_", "-"), inputs[key]))
            if inputs["semantic"] is None:
                record = {"dataset": row["dataset"], "sample": row["sample"],
                          "status": "missing_semantic_for_fixed_three"}
                status.append(record)
                continue
            command.extend(("--semantic", inputs["semantic"],
                            "--config-json", str(ROOT / "configs" / "posterior_mainline.json"),
                            "--output-dir", str(case_dir), "--outer-rounds", "3",
                            "--device", args.device))
            print(f"[{ordinal}/{len(selected)}] {row['dataset']}/{row['sample']}", flush=True)
            result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, check=False)
            (case_dir / "run.log").write_text(result.stdout, encoding="utf-8")
            record = {"dataset": row["dataset"], "sample": row["sample"],
                      "status": "completed" if result.returncode == 0 and final.is_file() else "failed",
                      "exit_code": result.returncode,
                      "final": str(final) if final.is_file() else None}
            print(f"  {record['status']}", flush=True)
        status.append(record)
        status_path.write_text(json.dumps({"ground_truth_used": False,
                                           "samples": status}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
