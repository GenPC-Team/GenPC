#!/usr/bin/env python3
"""Run a shared, annotation-free refinement policy on archived registered cases."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--samples', nargs='+')
    parser.add_argument('--gpus', nargs='+', default=['0'])
    parser.add_argument('--rounds', type=int, default=8)
    args = parser.parse_args()
    names = args.samples or sorted(p.name for p in args.input_root.iterdir() if p.is_dir())
    cases = [args.input_root/name for name in names]
    for case in cases:
        for relative in [f'inputs/partial/{case.name}.ply',
                         f'inputs/camera/{case.name}/camera.pth',
                         'registration/final/camera1_amplified_registered_100k.ply',
                         'diagnostics/render/render_manifest.json']:
            if not (case/relative).is_file():
                raise FileNotFoundError(case/relative)
    args.output_root.mkdir(parents=True, exist_ok=True)
    if any((args.output_root/case.name).exists() for case in cases):
        raise ValueError('use fresh per-case output directories; accepted runs are never overwritten')
    sources = [ROOT/'scripts/run_semantic_refinement_continuation.py',
               ROOT/'src/semantic_refinement_policy.py', ROOT/'src/refinement_evidence.py',
               ROOT/'src/semantic_handle_refinement.py']
    manifest = {'started': datetime.now(timezone.utc).isoformat(), 'samples': names,
                'round_budget': args.rounds, 'model': 'gpt-6-astra', 'reasoning_effort': 'medium',
                'autonomous_refinement': True, 'human_feedback': False, 'ground_truth_used': False,
                'starting_stage': 'archived_fixed_registration',
                'scope': 'Refinement autonomy only; upstream archived priors retain their original provenance.',
                'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                'results': []}
    manifest_path = args.output_root/'batch.json'
    manifest_path.write_text(json.dumps(manifest, indent=2))
    devices = queue.Queue()
    for gpu in args.gpus:
        devices.put(gpu)

    def run(case):
        gpu = devices.get()
        try:
            out = args.output_root/case.name
            logs = args.output_root/'logs'; logs.mkdir(exist_ok=True)
            command = [sys.executable, str(ROOT/'scripts/run_semantic_refinement_continuation.py'),
                       '--case-dir', str(case.resolve()), '--output-dir', str(out.resolve()),
                       '--autonomous', '--views', '6', '--rounds', str(args.rounds)]
            environment = {**os.environ, 'CUDA_VISIBLE_DEVICES': gpu,
                           'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'}
            print('START', case.name, 'GPU', gpu, flush=True)
            with (logs/f'{case.name}.log').open('w') as log:
                completed = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
            result = {'sample': case.name, 'returncode': completed.returncode, 'command': command, 'gpu': gpu}
            if (out/'report.json').exists():
                report = json.loads((out/'report.json').read_text())
                result['status'] = report['status']
                result['accepted_rounds'] = [t['round'] for t in report['trace'] if t.get('accepted')]
                result['actions'] = [t['plan']['decision']['action'] for t in report['trace']]
            print('FINISH', case.name, result, flush=True)
            return result
        finally:
            devices.put(gpu)

    with ThreadPoolExecutor(max_workers=len(args.gpus)) as executor:
        futures = [executor.submit(run, case) for case in cases]
        for future in as_completed(futures):
            manifest['results'].append(future.result())
            manifest_path.write_text(json.dumps(manifest, indent=2))
    manifest['finished'] = datetime.now(timezone.utc).isoformat()
    manifest['all_processes_succeeded'] = all(r['returncode'] == 0 for r in manifest['results'])
    manifest_path.write_text(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
