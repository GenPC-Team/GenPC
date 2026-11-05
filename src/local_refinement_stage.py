"""Run the bounded local proposal tool inside the refinement stage."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.sparse.csgraph import connected_components

from src.deformation_graph import local_surface_graph
from src.pointcloud_io import load_points

ROOT = Path(__file__).resolve().parents[1]


def connectivity_audit(reference, candidate):
    """Reject a significant surface component splitting or merging."""
    if reference.shape != candidate.shape or not np.isfinite(candidate).all():
        return {"passed": False, "reason": "invalid_carrier"}
    labels = []
    minimum = max(32, int(.001 * len(reference)))
    for points in (reference, candidate):
        graph, _, _ = local_surface_graph(points, neighbours=12, edge_ratio=1.85)
        _, lab = connected_components(graph, directed=False)
        labels.append(lab)

    def splits(a, b):
        count = 0
        for k, size in enumerate(np.bincount(a)):
            if size >= minimum and np.sum(np.bincount(b[a == k]) >= minimum) > 1:
                count += 1
        return count

    broken, merged = splits(*labels), splits(*labels[::-1])
    return {"passed": not (broken or merged), "broken_components": broken,
            "merged_components": merged, "minimum_significant_size": minimum,
            "carrier_slots": len(reference)}


def run_local_review(carrier: Path, partial: Path, manifest: Path,
                     output: Path, *, model: str):
    """Return a reviewed, connectivity-checked carrier; never read GT."""
    output.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(ROOT / "scripts/probe_local_rigid_refinement.py"),
               "--carrier", str(carrier.resolve()), "--partial", str(partial.resolve()),
               "--multiview-manifest", str(manifest.resolve()),
               "--output-dir", str(output.resolve()), "--review", "--gpt-model", model]
    with (output / "run.log").open("w", encoding="utf-8") as log:
        subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    report = json.loads((output / "report.json").read_text())
    reference = load_points(carrier)
    candidate = load_points(output / "selected_100k.ply")
    changed = not np.array_equal(reference, candidate)
    audit = (connectivity_audit(reference, candidate) if changed
             else {"passed": True, "reason": "identical_carrier"})
    record = {"ground_truth_used": False, "command": command,
              "policy_version": report["policy_version"],
              "report": str((output / "report.json").resolve()),
              "changed": bool(changed and audit["passed"]), "connectivity": audit}
    (output / "stage.json").write_text(json.dumps(record, indent=2) + "\n")
    return (candidate if audit["passed"] else reference), record
