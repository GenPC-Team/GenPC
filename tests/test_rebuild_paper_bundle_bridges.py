"""The bridge replay must consume only hashed frozen inputs."""

from __future__ import annotations

import json

import pytest

from scripts import rebuild_paper_bundle_bridges as rebuild


PLY_100K = (b"ply\nformat ascii 1.0\nelement vertex 100000\n"
            b"property float x\nproperty float y\nproperty float z\nend_header\n")


def test_input_contract_rejects_changed_frozen_asset(tmp_path):
    sample_dir = tmp_path / "samples/custom/example"
    paths = rebuild.input_paths(sample_dir, "example")
    archived = {}
    for name, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PLY_100K if name in {"pixal_prior", "frozen_prior"} else b"frozen")
        archived[path.relative_to(sample_dir).as_posix()] = {"sha256": rebuild.sha256(path)}
    (sample_dir / "manifest.json").write_text(json.dumps({"files": archived}))
    validated = rebuild.validate_inputs(sample_dir, paths)
    assert set(validated) == set(paths)
    paths["partial"].write_bytes(b"mutated")
    with pytest.raises(ValueError, match="checksum changed"):
        rebuild.validate_inputs(sample_dir, paths)


def test_output_manifest_does_not_hash_itself(tmp_path):
    (tmp_path / "native").mkdir()
    (tmp_path / "native/points.ply").write_bytes(b"points")
    (tmp_path / "rebuild_manifest.json").write_text("{}")
    files = rebuild.output_files(tmp_path)
    assert list(files) == ["native/points.ply"]
    assert files["native/points.ply"]["sha256"] == rebuild.sha256(tmp_path / "native/points.ply")
