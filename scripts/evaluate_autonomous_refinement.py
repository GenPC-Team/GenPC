#!/usr/bin/env python3
"""Offline metrics for completed, frozen autonomous runs; never used in planning."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.offline_metrics import evaluate_cd_emd_repeated


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runs-root', type=Path, required=True)
    ap.add_argument('--case-root', type=Path, required=True)
    ap.add_argument('--data-root', type=Path, required=True)
    ap.add_argument('--count', type=int, default=16384)
    ap.add_argument('--seed', type=int, default=6145)
    ap.add_argument('--repeats', type=int, default=3)
    args = ap.parse_args()
    out = args.runs_root/'offline_evaluation'; out.mkdir(exist_ok=True)
    stages = []; cases = []
    for path in sorted(args.runs_root.glob('*/report.json')):
        report = json.loads(path.read_text())
        if report['status'] == 'running' or not (path.parent/'artifacts.json').exists():
            continue
        sample = path.parent.name; case = args.case_root/sample
        gt = args.data_root/sample/'gt_data'/f'{sample}_gt.ply'
        selected = path.parent/'selected_100k.ply'
        # Freeze inference artifacts before any metric computation/GT loading.
        sources = {'registration': case/'registration/final/camera1_amplified_registered_100k.ply',
                   'existing_refinement': case/'refinement/refined_100k.ply',
                   'autonomous_refinement': selected}
        frozen = [{'sample': sample, 'stage': stage, 'path': str(source.resolve()),
                   'sha256': sha(source)} for stage, source in sources.items()]
        for record in frozen:
            record.update(gt=str(gt.resolve()), gt_sha256=sha(gt))
        stages.extend(frozen)
        cases.append({'sample': sample, 'status': report['status'], 'stop_reason': report.get('stop_reason'),
                      'selected_actions': dict(Counter(t['plan']['decision']['action'] for t in report['trace'])),
                      'accepted_actions': dict(Counter(t['plan']['decision']['action'] for t in report['trace'] if t.get('accepted'))),
                      'remaining_inventory': report.get('remaining_inventory', report['trace'][-1]['plan']['decision'].get('mismatch_inventory') if report['trace'] else []),
                      'autonomous': report.get('autonomous', False)})
    if not stages:
        raise ValueError('no completed frozen runs available')
    protocol = {'count': args.count, 'seed': args.seed, 'repeats': args.repeats,
                'metric_scale': 100, 'cd': 'CD-L1', 'emd': 'approximate EMD'}
    manifest = {'timestamp': datetime.now(timezone.utc).isoformat(), 'offline_only': True,
                'protocol': protocol, 'cases': cases, 'stages': stages}
    (out/'frozen_stages.json').write_text(json.dumps(manifest, indent=2))
    cache_path = out/'cache.json'
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    rows = []
    for record in stages:
        key = hashlib.sha256(json.dumps([record['sha256'], record['gt_sha256'], protocol], sort_keys=True).encode()).hexdigest()
        if key not in cache:
            values = np.asarray(evaluate_cd_emd_repeated(Path(record['path']), Path(record['gt']),
                                count=args.count, seed=args.seed, repeats=args.repeats))*100
            cache[key] = values.tolist()
            cache_path.write_text(json.dumps(cache, indent=2))
        values = np.asarray(cache[key])
        assert sha(Path(record['path'])) == record['sha256'], 'inference output changed after freezing'
        row = {**record, 'cd_l1_x100': float(values[:,0].mean()), 'emd_x100': float(values[:,1].mean()),
               'emd_std': float(values[:,1].std()), 'runs_x100': values.tolist()}
        rows.append(row)
        (out/'metrics.json').write_text(json.dumps({**manifest, 'stages': rows, 'complete': len(rows)==len(stages)}, indent=2))
        print(record['sample'], record['stage'], row['cd_l1_x100'], row['emd_x100'], flush=True)
    fields = ['sample', 'stage', 'cd_l1_x100', 'emd_x100', 'emd_std', 'sha256']
    with (out/'metrics.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in rows)
    means = {stage: {metric: float(np.mean([r[metric] for r in rows if r['stage']==stage]))
                      for metric in ['cd_l1_x100', 'emd_x100']}
             for stage in sorted({r['stage'] for r in rows})}
    (out/'summary.json').write_text(json.dumps({'cases': cases, 'protocol': protocol, 'means': means}, indent=2))


if __name__ == '__main__':
    main()
