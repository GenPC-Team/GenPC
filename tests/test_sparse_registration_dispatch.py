import json
import sys
from pathlib import Path

import pytest
from scripts import run_fixed_pixal_moge_registration as runner


@pytest.mark.parametrize('sparse', [False, True])
def test_explicit_option_isolates_registration_stages(tmp_path, monkeypatch, sparse):
    commands = []
    monkeypatch.setattr(runner, '_require', lambda *a: None)
    monkeypatch.setattr(runner, '_run', lambda command, **kwargs: commands.append(command))
    args = ['registration', '--samples', 'sample', '--output-root', str(tmp_path), '--dry-run']
    if sparse:
        args.append('--sparse-observation')
    monkeypatch.setattr(sys, 'argv', args)
    runner.main()
    scripts = [Path(command[1]).name for command in commands]
    assert scripts[:2] == ['run_pixal_native_moge_registration.py', 'run_pixal_moge_two_camera_bridge.py']
    if sparse:
        assert len(scripts) == 7
        assert '--sparse-observation' not in commands[1]
        assert '--sparse-observation' in commands[-1]
        assert 'sparse_bridge' in commands[-1][commands[-1].index('--output-dir')+1]
    else:
        assert len(scripts) == 6
        assert '--sparse-observation' not in commands[1]
        assert 'run_pixal_moge_joint_bundle.py' in scripts


@pytest.mark.parametrize('old_sparse', [False, True])
def test_existing_final_cannot_switch_mode(tmp_path, monkeypatch, old_sparse):
    final = tmp_path / 'sample/final'
    final.mkdir(parents=True)
    (final/runner.REGISTERED_PRIOR_FILENAME).write_text('accepted output')
    if old_sparse:
        (final/'sparse_observation.json').write_text('{}')
    monkeypatch.setattr(runner, '_require', lambda *a: None)
    monkeypatch.setattr(runner, '_run', lambda *a, **kw: pytest.fail('must not execute'))
    args = ['registration', '--samples', 'sample', '--output-root', str(tmp_path)]
    if not old_sparse:
        args.append('--sparse-observation')
    monkeypatch.setattr(sys, 'argv', args)
    runner.main()
    report = json.loads((tmp_path/'batch_manifest.json').read_text())
    assert report['status']['sample']['state'] == 'failed'
    assert 'mode changed' in report['status']['sample']['error']
    assert (final/runner.REGISTERED_PRIOR_FILENAME).read_text() == 'accepted output'
