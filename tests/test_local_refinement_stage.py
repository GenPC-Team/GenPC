import json
from pathlib import Path

import numpy as np
import pytest

from src.local_refinement_stage import run_local_review
from src.planned_refinement_stage import run_planned_review
from src.pointcloud_io import load_points, write_points


@pytest.mark.parametrize("planned", [False, True])
@pytest.mark.parametrize("break_surface", [False, True])
def test_local_stage_cannot_bypass_connectivity_guard(tmp_path, monkeypatch, break_surface, planned):
    x, y = np.meshgrid(np.linspace(0, 1, 20), np.linspace(0, .2, 6))
    original = np.column_stack([x.ravel(), y.ravel(), np.zeros(x.size)])
    carrier = tmp_path / "carrier.ply"
    write_points(carrier, original)
    candidate = load_points(carrier)
    if break_surface:
        candidate[candidate[:, 0] > .5, 0] += 2.
    else:
        candidate[:, 2] += .01

    def fake_review(command, **kwargs):
        out = Path(command[command.index("--output-dir") + 1])
        write_points(out / "selected_100k.ply", candidate)
        (out / "report.json").write_text(json.dumps({
            "policy_version": "test", "selected_candidate": "accepted_by_visual_reviewer",
            "final_integrity": {"passed": True}, "accepted_steps": 1}))

    monkeypatch.setattr("src.local_refinement_stage.subprocess.run", fake_review)
    runner = run_planned_review if planned else run_local_review
    result, record = runner(
        carrier, tmp_path / "partial.ply", tmp_path / "views.json",
        tmp_path / "local", model="test-model")
    assert record["changed"] == (not break_surface)
    np.testing.assert_array_equal(result, load_points(carrier) if break_surface
                                  else load_points(tmp_path / "local/selected_100k.ply"))
    assert not record["ground_truth_used"]
