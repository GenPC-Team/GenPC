#!/usr/bin/env python3
"""Resume the shared autonomous refinement and fusion route on saved datasets.

Inputs come only from archived priors/registration. This runner never reads GT.
Every sample keeps its upstream assets, refinement trace and fusion together.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {
    'redwood': ('workspace/refinement_final/redwood10', 'workspace/refinement_final/redwood10', '*/inputs/partial/*.ply'),
    'custom': ('workspace/refinement_final/custom10', 'data/custom', '*/partial_data/single_scan/*.ply'),
    'kitti': ('workspace/kitti20_imagegen_20261103', 'data/kitti', 'partial/*/*.ply'),
    'waymo': ('workspace/waymo76_imagegen_20261103', 'data/waymo', '*/*.ply'),
    'aircraft': ('workspace/refinement_final/aircraft40', 'data/aircraft', 'partial/*.ply'),
}
FINISHED = {'pilot_stopped_with_trace', 'agent_stopped_no_actionable_issue'}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def case_sources(source):
    sid = source.name
    canonical = (source/'diagnostics/render/render_manifest.json').is_file()
    registration = source/'registration' if canonical else source/'registration'/sid
    diagnostics = source/'diagnostics' if canonical else source/'residuals'/sid
    prior = source/'prior_generation' if canonical else source/'prior_agent'
    required = [source/'inputs/partial'/f'{sid}.ply', source/'inputs/camera'/sid/'camera.pth',
                registration/'final/camera1_amplified_registered_100k.ply',
                diagnostics/'render/render_manifest.json']
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    if not prior.is_dir():
        raise FileNotFoundError(prior)
    return {'inputs': source/'inputs', 'prior_generation': prior,
            'registration': registration, 'diagnostics': diagnostics}, required


def validated_prior_source(output_root, dataset, sid, archived):
    """LiDAR priors must have a fresh audit or a completed reviewed rebuild."""
    if dataset not in {'kitti','waymo'}:
        return archived
    audit_path=output_root/f'{dataset}_prior_audit'/sid/'audit.json'
    audit=json.loads(audit_path.read_text())
    if audit['model']!='gpt-6-astra' or audit['reasoning_effort'] not in {'medium', 'low'}:
        raise ValueError(f'fresh Astra prior audit required: {sid}')
    # KITTI's refreshed run explicitly fixes its documented Y-down input
    # convention. Even an old depth/RGB pair consistent with each other must
    # not bypass that camera refresh in this experiment.
    if audit['decision']['action']=='KEEP_PRIOR' and dataset!='kitti':
        for path,digest in audit['input_sha256'].items():
            if sha(Path(path))!=digest:
                raise ValueError(f'audited prior changed: {sid}')
        return archived
    rebuilt=output_root/'prior_rebuild'/dataset/sid
    if dataset=='kitti':
        metadata=json.loads((rebuilt/'coordinate_refresh.json').read_text())
        if metadata['world_up'] != [0.,-1.,0.]:
            raise ValueError('KITTI camera refresh must preserve documented negative-Y up')
    state=json.loads((rebuilt/'prior_agent/prior_agent_manifest.json').read_text())
    accepted=state.get('accepted')
    if not accepted:
        raise ValueError(f'prior repair still pending: {sid}')
    review=state['reviews'][accepted['review_index']]['decision']
    if (review['model']!='gpt-6-astra' or review['reasoning_effort'] not in {'medium', 'low'}
            or review['decision']['action']!='ACCEPT'
            or not review['decision']['image_plane_orientation_match']):
        raise ValueError(f'new prior has not passed Astra orientation review: {sid}')
    for field in ['source','installed','pixal_input']:
        path_key={'source':'source_image','installed':'installed_image','pixal_input':'pixal_input'}[field]
        if sha(Path(accepted[path_key]))!=accepted[field+'_sha256']:
            raise ValueError(f'accepted prior asset changed: {sid}')
    return rebuilt


def prepare_case(source, out):
    directories, required = case_sources(source)
    signature = {str(p.resolve()): sha(p) for p in required}
    manifest = out/'upstream.json'
    if manifest.exists():
        previous = json.loads(manifest.read_text())
        if previous['input_sha256'] != signature:
            raise ValueError(f'upstream inputs changed for {out.name}')
        if (source/'provenance').is_dir():
            shutil.copytree(source/'provenance',out/'provenance/upstream',dirs_exist_ok=True)
        return
    out.mkdir(parents=True, exist_ok=True)
    for name, path in directories.items():
        shutil.copytree(path, out/name, dirs_exist_ok=True)
    provenance = out/'provenance'; provenance.mkdir(exist_ok=True)
    for name in ['generation.json', 'semantic.png', 'four_stage_pipeline.json', 'artifacts.json',
                 'coordinate_refresh.json', 'repair_provenance.json', 'source_audit.json',
                 'geometry_queue.json']:
        if (source/name).is_file():
            shutil.copy2(source/name, provenance/name)
    for path in source.glob('*.log'):
        shutil.copy2(path, provenance/path.name)
    if (source/'logs').is_dir():
        shutil.copytree(source/'logs', provenance/'logs', dirs_exist_ok=True)
    if (source/'provenance').is_dir():
        shutil.copytree(source/'provenance',provenance/'upstream',dirs_exist_ok=True)
    write_json(manifest, {'source': str(source.resolve()), 'input_sha256': signature,
                         'scope': 'Reuse archived prior and fixed registration; fresh autonomous refinement and fusion.',
                         'historical_model_metadata_preserved': True, 'ground_truth_used': False})


def install_registration_override(out, candidate_root, *, environment):
    """Install a frozen sparse-audit selection before any new refinement."""
    candidate_root = candidate_root.resolve()
    selected = candidate_root/'registered_100k.ply'
    report_path = candidate_root/'report.json'
    report = json.loads(report_path.read_text())
    if report.get('ground_truth_used') is not False or report.get('status') != 'complete':
        raise ValueError('registration override must be a completed no-GT audit')
    sid = out.name
    partial = out/'inputs/partial'/f'{sid}.ply'
    source_partial = [digest for path,digest in report['input_sha256'].items()
                      if path.endswith('/inputs/partial/'+sid+'.ply')]
    if source_partial != [sha(partial)]:
        raise ValueError('registration override partial mismatch')
    for path,digest in report['input_sha256'].items():
        if sha(Path(path)) != digest:
            raise ValueError('registration audit input changed: '+path)
    signature = {'candidate':str(selected),'sha256':sha(selected),'report_sha256':sha(report_path)}
    receipt = out/'registration_override.json'
    final = out/'registration/final/camera1_amplified_registered_100k.ply'
    if receipt.exists():
        previous = json.loads(receipt.read_text())
        if previous['signature'] != signature:
            raise ValueError('registration override changed; use a fresh output root')
        if previous['status']=='complete':
            if sha(final)!=signature['sha256']:
                raise ValueError('installed registration changed')
            if not (out/'diagnostics/render/render_manifest.json').is_file():
                raise ValueError('override diagnostics missing')
            return
    elif (out/'refinement').exists() or (out/'fusion').exists():
        raise ValueError('cannot change registration after refinement/fusion starts')
    if ply_count(selected)!=100000:
        raise ValueError('registration override must retain 100000 points')
    write_json(receipt, {'status':'preparing','signature':signature})
    archive = out/'provenance/original_registration'
    if not archive.exists():
        shutil.move(str(out/'registration'),str(archive))
    archive_views = out/'provenance/original_diagnostics'
    if not archive_views.exists():
        shutil.move(str(out/'diagnostics'),str(archive_views))
    shutil.copytree(candidate_root,out/'registration/sparse_audit',dirs_exist_ok=True)
    final.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(selected,final)
    write_json(final.parent/'sparse_observation.json',report)
    (out/'logs').mkdir(exist_ok=True)
    command=[sys.executable,str(ROOT/'scripts/run_multiview_diagnostics.py'),
             '--registered-prior',str(final.resolve()),'--partial',str(partial.resolve()),
             '--camera',str((out/'inputs/camera'/sid/'camera.pth').resolve()),
             '--output-dir',str((out/'diagnostics').resolve())]
    with (out/'logs/registration_diagnostics.log').open('w') as log:
        subprocess.run(command,cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT,check=True)
    write_json(receipt,{'status':'complete','signature':signature,'command':command,
                       'selected_route':report['selected_route'],'ground_truth_used':False})


def ply_count(path):
    with path.open('rb') as stream:
        for _ in range(100):
            line = stream.readline()
            if line.startswith(b'element vertex '):
                return int(line.split()[-1])
            if line == b'end_header\n' or not line:
                break
    raise ValueError(f'PLY has no vertex count: {path}')


def mark_interrupted(run, reason):
    path = run/'report.json'
    if not path.exists():
        return
    report = json.loads(path.read_text())
    if report['status'] != 'running':
        return
    report['status'] = 'interrupted_execution'; report['stop_reason'] = reason
    if report['trace']:
        last = report['trace'][-1]
        if not last.get('accepted') and not last.get('error'):
            last['interrupted_transport'] = True
            last['error'] = 'Execution interrupted before completed review; not a geometric rejection.'
    write_json(path, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, default=ROOT/'workspace/refinement_updated')
    parser.add_argument('--source-root', type=Path,
                        help='Reuse a completed dataset/sample archive, e.g. workspace/astra_final, in a fresh output root.')
    parser.add_argument('--registration-root', type=Path,
                        help='Explicit frozen audit selections at dataset/sample/registered_100k.ply; regenerate diagnostics before refinement.')
    parser.add_argument('--datasets', nargs='+', choices=list(DATASETS), default=['custom','aircraft'])
    parser.add_argument('--gpus', nargs='+', default=['1', '2', '3', '5'])
    parser.add_argument('--rounds', type=int, default=32)
    parser.add_argument('--exclude-samples', nargs='*', default=[])
    parser.add_argument('--samples', nargs='+')
    parser.add_argument('--manifest-name', default='suite.json')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--import-pilot', type=Path)
    args = parser.parse_args()
    cases = []
    for dataset in args.datasets:
        archived, data, pattern = DATASETS[dataset]
        files = sorted((args.source_root/dataset).glob('*/inputs/partial/*.ply')
                       if args.source_root else (ROOT/data).glob(pattern))
        if not files:
            raise ValueError(f'no inputs found: {dataset}')
        for partial in files:
            sid = partial.stem
            if dataset == 'custom':
                sid = partial.parents[2].name
            if sid in args.exclude_samples:
                continue
            if args.samples and sid not in args.samples:
                continue
            if args.source_root:
                source = (args.source_root/dataset/sid).resolve()
                if source == (args.output_root/dataset/sid).resolve():
                    raise ValueError('Use a fresh output root; accepted archives are immutable')
                completed = json.loads((source/'completion.json').read_text())
                if (completed['status'] != 'complete' or completed['ground_truth_used']
                        or sha(source/'fusion/observation_anchored_fused_100k.ply') != completed['final_sha256']):
                    raise ValueError('Source archive is not a verified completed case: ' + sid)
            else:
                source = validated_prior_source(args.output_root, dataset, sid, ROOT/archived/sid)
            _, required = case_sources(source)
            if sha(partial) != sha(required[0]):
                raise ValueError(f'current partial differs from archived partial: {partial}')
            cases.append({'dataset': dataset, 'sample': sid, 'source': source,
                          'output': args.output_root/dataset/sid})
    args.output_root.mkdir(parents=True, exist_ok=True)
    state = {'started': datetime.now(timezone.utc).isoformat(), 'rounds': args.rounds,
             'model': 'gpt-6-astra', 'reasoning_effort': 'low', 'ground_truth_used': False,
             'counts': {d: sum(c['dataset']==d for c in cases) for d in args.datasets},
             'results': []}
    if args.registration_root:
        state['registration_root'] = str(args.registration_root.resolve())
    manifest = args.output_root/args.manifest_name
    write_json(manifest, state)
    devices = queue.Queue()
    for gpu in args.gpus:
        devices.put(gpu)

    def run(case):
        gpu = devices.get()
        try:
            out = case['output']; sid = case['sample']
            prepare_case(case['source'], out)
            if args.registration_root:
                environment = {**os.environ, 'CUDA_VISIBLE_DEVICES':gpu,
                               'OPENBLAS_NUM_THREADS':'1', 'OMP_NUM_THREADS':'1'}
                install_registration_override(out,args.registration_root/case['dataset']/sid,
                                              environment=environment)
            elif (out/'registration_override.json').exists():
                raise ValueError('resume must explicitly retain --registration-root')
            if args.prepare_only:
                return {'dataset': case['dataset'], 'sample': sid, 'status': 'prepared'}
            refinement = out/'refinement'
            if args.import_pilot and case['dataset']=='custom' and not refinement.exists():
                pilot = args.import_pilot/sid
                if (pilot/'report.json').is_file():
                    report = json.loads((pilot/'report.json').read_text())
                    if report['status'] == 'running':
                        raise ValueError(f'cannot import a running pilot: {sid}')
                    shutil.copytree(pilot, refinement)
                    write_json(out/'pilot_import.json', {'source': str(pilot.resolve()),
                               'selected_sha256': sha(pilot/'selected_100k.ply')})
            report_path = refinement/'report.json'
            report = json.loads(report_path.read_text()) if report_path.exists() else None
            commands = []
            environment = {**os.environ, 'CUDA_VISIBLE_DEVICES': gpu,
                           'OPENBLAS_NUM_THREADS':'1', 'OMP_NUM_THREADS':'1'}
            done = report and report['status'] in FINISHED and (
                report['status']=='agent_stopped_no_actionable_issue' or len(report['trace'])>=args.rounds)
            if not done:
                command = [sys.executable, str(ROOT/'scripts/run_semantic_refinement_continuation.py'),
                           '--case-dir', str(out.resolve()), '--output-dir', str(refinement.resolve()),
                           '--autonomous', '--views','6','--rounds',str(args.rounds)]
                if refinement.exists():
                    command.append('--resume')
                commands.append(command)
                logs = out/'logs'; logs.mkdir(exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
                with (logs/f'refinement_{stamp}.log').open('w') as log:
                    result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
                if result.returncode:
                    mark_interrupted(refinement, f'subprocess_exit_{result.returncode}; inspect logs')
                    raise RuntimeError(f'refinement exit {result.returncode}; checkpoint saved')
                report = json.loads(report_path.read_text())
            if report['status'] not in FINISHED:
                raise RuntimeError(f'refinement not finalized: {report["status"]}')
            selected = refinement/'selected_100k.ply'
            if ply_count(selected) != 100000:
                raise ValueError('refined carrier must contain 100000 ordered points')
            fusion = out/'fusion'; final = fusion/'observation_anchored_fused_100k.ply'
            receipt = out/'completion.json'
            old = json.loads(receipt.read_text()) if receipt.exists() else {}
            if old.get('refinement_sha256') != sha(selected) or not final.exists():
                command = [sys.executable,str(ROOT/'scripts/run_observation_anchored_fusion.py'),
                           '--posterior',str(selected.resolve()),'--partial',str((out/'inputs/partial'/f'{sid}.ply').resolve()),
                           '--multiview-manifest',str((out/'diagnostics/render/render_manifest.json').resolve()),
                           '--mode','continuous','--carrier-colors-from',str((out/'inputs/pixal'/sid/'pixal3d_sampled_100k.ply').resolve()),
                           '--output-dir',str(fusion.resolve())]
                commands.append(command); (out/'logs').mkdir(exist_ok=True)
                with (out/'logs/fusion.log').open('w') as log:
                    subprocess.run(command,cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT,check=True)
            if ply_count(final) != 100000:
                raise ValueError('fusion output must contain 100000 points')
            completed = {'dataset':case['dataset'],'sample':sid,'status':'complete',
                         'refinement_status':report['status'],'rounds':len(report['trace']),
                         'accepted_rounds':[t['round'] for t in report['trace'] if t.get('accepted')],
                         'stop_reason':report.get('stop_reason'),'ground_truth_used':False,
                         'refinement_sha256':sha(selected),'final_sha256':sha(final),'commands':commands,
                         'final_point_count':100000,'timestamp':datetime.now(timezone.utc).isoformat()}
            write_json(receipt,completed)
            write_json(out/'artifacts.json', {'inputs':'inputs','prior_generation':'prior_generation',
                       'registration':'registration','diagnostics':'diagnostics','refinement':'refinement',
                       'fusion':'fusion','final_pointcloud':'fusion/observation_anchored_fused_100k.ply',
                       'colored_overlay':'refinement/visualization/refined_red_partial_blue.ply',
                       'final_colored_overlay':'fusion/final_red_partial_blue.ply',
                       'provenance':'provenance','completion':'completion.json'})
            return completed
        except Exception as exc:
            return {'dataset':case['dataset'],'sample':case['sample'],'status':'failed',
                    'error':str(exc),'timestamp':datetime.now(timezone.utc).isoformat()}
        finally:
            devices.put(gpu)

    with ThreadPoolExecutor(max_workers=len(args.gpus)) as pool:
        futures = [pool.submit(run,c) for c in cases]
        for future in as_completed(futures):
            result = future.result(); state['results'].append(result)
            write_json(manifest,state); print(json.dumps(result),flush=True)
    state['finished'] = datetime.now(timezone.utc).isoformat()
    state['all_succeeded'] = all(r['status'] in {'complete','prepared'} for r in state['results'])
    write_json(manifest,state)
    if not state['all_succeeded']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
