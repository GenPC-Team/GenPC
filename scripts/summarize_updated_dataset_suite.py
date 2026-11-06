"""Export dataset-local offline tables from frozen evaluation records."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean


EXPECTED = {'redwood': 10, 'custom': 10, 'kitti': 20, 'waymo': 76, 'aircraft': 40}


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'workspace/refinement_updated')
    args = parser.parse_args()
    evaluation = args.root / 'offline_evaluation'
    cases = read(evaluation / 'cases.json')
    metrics = read(evaluation / 'metrics.json')
    support = read(evaluation / 'observed_support.json')['rows']
    metric_index = {(r['dataset'], r['sample'], r['stage']): r for r in metrics['rows']}
    support_index = {(r['dataset'], r['sample'], r['stage']): r for r in support}
    for dataset, expected in EXPECTED.items():
        rows, selected, accepted = [], Counter(), Counter()
        efforts = set()
        pending_extensions = []
        for case in cases:
            if case['dataset'] != dataset:
                continue
            sid = case['sample']
            receipt = args.root / dataset / sid / 'completion.json'
            # A budget continuation may have withdrawn or replaced this evaluation.
            if not receipt.exists():
                continue
            done = read(receipt)
            if done['final_sha256'] != case['final_sha256'] or done['rounds'] != case['rounds']:
                continue
            report = read(args.root / dataset / sid / 'refinement/report.json')
            def collect_efforts(value):
                if isinstance(value, dict):
                    if 'reasoning_effort' in value:
                        efforts.add(value['reasoning_effort'])
                    for child in value.values():
                        collect_efforts(child)
                elif isinstance(value, list):
                    for child in value:
                        collect_efforts(child)
            collect_efforts(report)
            row = {'sample': sid, 'rounds': case['rounds'],
                   'final_sha256': case['final_sha256'], 'stop_reason': case['stop_reason']}
            if case['stop_reason'].startswith('round_budget_exhausted') and case['rounds'] < 64:
                pending_extensions.append(sid)
            index = metric_index if dataset in {'redwood', 'custom', 'aircraft'} else support_index
            old = index[dataset, sid, 'old_fusion']
            new = index[dataset, sid, 'updated_fusion']
            if new['sha256'] != case['final_sha256']:
                raise ValueError('Evaluation hash mismatch: ' + sid)
            if dataset in {'redwood', 'custom', 'aircraft'}:
                for label, values in [('old', old), ('new', new)]:
                    row[label + '_cd_x100'] = values['cd_l1_x100']
                    row[label + '_emd_x100'] = values['emd_x100']
            else:
                for label, values in [('old', old), ('new', new)]:
                    row[label + '_observed_mean_percent'] = values['mean_percent_observed_diagonal']
                    row[label + '_observed_p95_percent'] = values['p95_percent_observed_diagonal']
            rows.append(row)
            selected.update(case['selected_actions'])
            accepted.update(case['accepted_actions'])
        rows.sort(key=lambda row: row['sample'])
        metric_keys = [key for key in rows[0] if key.startswith(('old_', 'new_'))] if rows else []
        summary = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'status': 'complete_for_current_experiment' if len(rows) == expected and not pending_extensions else 'partial',
            'sample_count': len(rows), 'expected_count': expected,
            'pending_budget_extensions': pending_extensions,
            'model': 'gpt-6-astra', 'reasoning_effort': next(iter(efforts)) if len(efforts) == 1 else 'mixed',
            'recorded_reasoning_efforts': sorted(efforts),
            'means': {key: mean(row[key] for row in rows) for key in metric_keys},
            'selected_actions': dict(selected), 'accepted_actions': dict(accepted),
            'scope': 'Frozen evaluated cases only. Combined model/controller/prior changes; not a model-only ablation.',
            'rows': rows,
        }
        if dataset in {'redwood', 'custom', 'aircraft'}:
            summary['protocol'] = metrics['protocol']
            for name in ['cd', 'emd']:
                summary[name + '_improved'] = sum(row['new_' + name + '_x100'] < row['old_' + name + '_x100'] for row in rows)
            filename = 'metrics.csv'
        else:
            summary['metrics'] = 'CD/EMD unavailable: no matched complete-object GT.'
            summary['limitation'] = 'Observed support is one-way partial-to-carrier distance as percent of the observed bounding-box diagonal. It does not assess hidden shape quality.'
            filename = 'observed_support.csv'
        destination = args.root / dataset
        destination.mkdir(parents=True, exist_ok=True)
        (destination / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        with (destination / filename).open('w') as stream:
            if rows:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        print(dataset, summary['status'], len(rows), '/', expected)


if __name__ == '__main__':
    main()
