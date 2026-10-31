"""Parallel scheduling must preserve the per-sample output and resume contract."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from scripts import run_agentic_refine_batch as batch


def test_two_workers_and_resume_keep_one_index_writer(tmp_path, monkeypatch):
    samples = [
        {"dataset": "sample_set", "sample": f"case_{i}", "source": str(tmp_path),
         "inputs": {"prior": "prior.ply", "partial": "partial.ply",
                    "camera": "camera.pth", "semantic": None,
                    "multiview_manifest": "render_manifest.json", "baseline": None}}
        for i in range(4)
    ]
    monkeypatch.setattr(batch, "_discover", lambda sources: (samples, []))
    concurrent = 0
    peak = 0
    calls = 0
    guard = threading.Lock()

    def fake_run(command, **kwargs):
        nonlocal concurrent, peak, calls
        output = Path(command[command.index("--output-dir") + 1])
        with guard:
            concurrent += 1
            peak = max(peak, concurrent)
            calls += 1
        time.sleep(.03)
        output.mkdir(parents=True, exist_ok=True)
        (output / "agent_selected_posterior_100k.ply").write_bytes(b"ply")
        (output / "agent_trace.json").write_text(json.dumps({
            "policy": "deterministic_no_gt_v1", "gpt_model": None,
            "gpt_provider": None, "maximum_rounds": 3,
            "trace": [{"accepted": True}],
            "initial_observation": {"coverage": [.5] * 4,
                                    "partial_to_carrier_p90": .2},
            "final_observation": {"coverage": [.8] * 4,
                                  "partial_to_carrier_p90": .1},
        }))
        with guard:
            concurrent -= 1
        return subprocess.CompletedProcess(command, 0, stdout="ok")

    monkeypatch.setattr(batch.subprocess, "run", fake_run)
    args = ["batch", "--source", f"sample_set={tmp_path}",
            "--output-root", str(tmp_path / "output"), "--workers", "2"]
    monkeypatch.setattr(sys, "argv", args)
    batch.main()
    index = json.loads((tmp_path / "output" / "batch_index.json").read_text())
    assert peak == 2
    assert calls == 4
    assert [row["status"] for row in index["samples"]] == ["completed"] * 4
    assert all(row["elapsed_seconds"] >= 0 for row in index["samples"])

    batch.main()
    resumed = json.loads((tmp_path / "output" / "batch_index.json").read_text())
    assert calls == 4
    assert [row["status"] for row in resumed["samples"]] == ["completed_existing"] * 4
