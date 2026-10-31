"""Frozen paper archives retain source provenance and an executable replay chain."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from scripts import package_refine_agent_paper as bundle


PLY_100K = (b"ply\nformat ascii 1.0\nelement vertex 100000\n"
            b"property float x\nproperty float y\nproperty float z\nend_header\n")


def _file(path: Path, content: bytes = b"asset") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.mark.parametrize("historical", [True, False])
def test_package_sample_preserves_exact_chain_and_replay(tmp_path, historical):
    source = tmp_path / "source"
    output = tmp_path / "bundle"
    sample = "case_a"
    camera = _file(source / "inputs/camera/case_a/camera.pth")
    semantic = _file(camera.parent / "img.png")
    partial = _file(source / "inputs/partial/case_a.ply")
    for name in ("pixal3d.glb", "pixal3d_sampled_100k.ply", "pixal3d_metadata.json"):
        _file(source / "inputs/pixal/case_a" / name)
    prior = _file(source / "registration_selected/case_a/camera1_amplified_registered_100k.ply",
                  PLY_100K)
    initial = source / "registration_initial/case_a/final/camera1_amplified_registered_100k.ply"
    if historical:
        _file(initial, PLY_100K)
        _file(source / "registration_initial/case_a/bridge/bridge_info.json", b"{}")
    _file(prior.parent / "camera1_amplified_info.json",
          json.dumps({"inputs": {"registered_prior": str(initial)}}).encode())
    manifest = _file(source / "residuals/case_a/render/render_manifest.json", b"{}")
    agent_dir = tmp_path / "agent" / "custom" / sample
    posterior = _file(agent_dir / "agent_selected_posterior_100k.ply", PLY_100K)
    _file(agent_dir / "agent_trace.json", json.dumps({
        "gpt_model": "gpt-6-sol", "gpt_provider": "codex", "maximum_rounds": 6,
        "maximum_active_views": 6, "view_policy": "adaptive",
        "minimum_reference_coverage": .85, "stop_reason": "accepted",
    }).encode())
    fusion_dir = tmp_path / "fusion"
    fused = _file(fusion_dir / "observation_anchored_fused_100k.ply", PLY_100K)
    _file(fusion_dir / "observation_anchored_fused_100k_pixal_texture.ply", PLY_100K)
    for config in ("posterior_mainline.json", "structural_proposal.json"):
        _file(output / "configs" / config, b"{}")
    row = {"dataset": "custom", "sample": sample, "source": str(source),
           "status": "completed", "inputs": {
               "partial": str(partial), "camera": str(camera), "semantic": str(semantic),
               "prior": str(prior), "multiview_manifest": str(manifest),
           }, "final": str(posterior)}
    fusion_row = {"status": "completed", "posterior": str(posterior), "fused": str(fused)}
    sample_root = output / "samples/custom/case_a"
    configs = {"posterior_mainline": "configs/posterior_mainline.json",
               "structural_proposal": "configs/structural_proposal.json"}
    record = bundle.package_sample(row, fusion_row, tmp_path / "agent", sample_root, configs)
    manifest_data = bundle.checked_json(sample_root / "manifest.json")
    expected = ("exact_declared_initial_chain_archived" if historical else
                "declared_historical_input_unavailable")
    assert record["historical_registration"] == expected
    assert manifest_data["historical_registration"]["status"] == expected
    assert ("03_registration/initial/bridge/bridge_info.json" in manifest_data["files"]) == historical
    assert all(bundle.sha256(sample_root / path) == meta["sha256"]
               for path, meta in manifest_data["files"].items())
    assert subprocess.run(["sh", "-n", str(sample_root / "replay_agent.sh")],
                          check=False).returncode == 0
    assert record == bundle.package_sample(row, fusion_row, tmp_path / "agent", sample_root,
                                            configs)
    _file(partial, b"changed")
    with pytest.raises(FileExistsError):
        bundle.package_sample(row, fusion_row, tmp_path / "agent", sample_root, configs)


def test_archive_rejects_unsafe_sample_names():
    for value in ("", ".", "..", "../case", "nested/case"):
        with pytest.raises(ValueError):
            bundle.safe_name(value)
