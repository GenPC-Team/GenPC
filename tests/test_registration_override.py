import json
from pathlib import Path
import pytest
from scripts import run_updated_dataset_suite as suite


def make_case(tmp_path):
    out=tmp_path/'run'/'object'; candidate=tmp_path/'audit'/'object'
    partial=out/'inputs/partial/object.ply'; partial.parent.mkdir(parents=True); partial.write_bytes(b'partial')
    (out/'registration/final').mkdir(parents=True)
    (out/'registration/final/camera1_amplified_registered_100k.ply').write_bytes(b'old')
    (out/'diagnostics').mkdir();(out/'provenance').mkdir()
    candidate.mkdir(parents=True); (candidate/'registered_100k.ply').write_bytes(b'new')
    report={'ground_truth_used':False,'status':'complete','input_sha256':{str(partial):suite.sha(partial)},'selected_route':'sparse'}
    (candidate/'report.json').write_text(json.dumps(report))
    return out,candidate


def test_override_installs_before_diagnostics_and_guards_resume(tmp_path,monkeypatch):
    out,candidate=make_case(tmp_path)
    monkeypatch.setattr(suite,'ply_count',lambda p:100000)
    calls=[]
    def run(command,**kwargs):
        calls.append(command)
        assert (out/'registration/final/camera1_amplified_registered_100k.ply').read_bytes()==b'new'
        dest=out/'diagnostics/render';dest.mkdir(parents=True);(dest/'render_manifest.json').write_text('{}')
    monkeypatch.setattr(suite.subprocess,'run',run)
    suite.install_registration_override(out,candidate,environment={})
    assert (out/'provenance/original_registration/final/camera1_amplified_registered_100k.ply').read_bytes()==b'old'
    suite.install_registration_override(out,candidate,environment={})
    assert len(calls)==1
    (candidate/'registered_100k.ply').write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):
        suite.install_registration_override(out,candidate,environment={})


def test_override_rejects_wrong_partial(tmp_path):
    out,candidate=make_case(tmp_path)
    (out/'inputs/partial/object.ply').write_bytes(b'wrong partial')
    with pytest.raises(ValueError,match='partial mismatch'):
        suite.install_registration_override(out,candidate,environment={})


def test_override_rejects_started_refinement(tmp_path):
    out,candidate=make_case(tmp_path);(out/'refinement').mkdir()
    with pytest.raises(ValueError,match='after refinement'):
        suite.install_registration_override(out,candidate,environment={})
