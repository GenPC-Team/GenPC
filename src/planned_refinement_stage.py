"""Invoke the planned local agent inside the existing refinement stage."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from src.local_refinement_stage import connectivity_audit
from src.pointcloud_io import load_points

ROOT = Path(__file__).resolve().parents[1]


def run_planned_review(carrier: Path, partial: Path, manifest: Path,
                       output: Path, *, model: str):
    """Run the common three-attempt policy and return a guarded carrier."""
    output.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(ROOT / "scripts/run_coherent_refinement_agent.py"),
               "--carrier", str(carrier.resolve()), "--partial", str(partial.resolve()),
               "--multiview-manifest", str(manifest.resolve()),
               "--output-dir", str(output.resolve()), "--gpt-model", model,
               "--maximum-rounds", "3"]
    with (output / "run.log").open("w", encoding="utf-8") as log:
        subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    report = json.loads((output / "report.json").read_text())
    if not report["final_integrity"]["passed"]:
        raise ValueError("planned local agent failed cumulative integrity")
    reference = load_points(carrier)
    candidate = load_points(output / "selected_100k.ply")
    changed = not np.array_equal(reference, candidate)
    audit = (connectivity_audit(reference, candidate) if changed
             else {"passed": True, "reason": "identical_carrier"})
    record = {"ground_truth_used": False, "command": command,
              "policy_version": report["policy_version"],
              "report": str((output / "report.json").resolve()),
              "accepted_steps": report["accepted_steps"],
              "cumulative_integrity": report["final_integrity"],
              "changed": bool(changed and audit["passed"]), "connectivity": audit}
    (output / "stage.json").write_text(json.dumps(record, indent=2) + "\n")
    return (candidate if audit["passed"] else reference), record
