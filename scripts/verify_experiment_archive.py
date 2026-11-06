#!/usr/bin/env python3
"""Verify copied experiment bytes and finalized carriers without old run paths."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.package_updated_dataset_suite import DATASETS, sha
from scripts.run_updated_dataset_suite import ply_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    root = args.archive.resolve()
    manifest = json.loads((root / 'copy_manifest.json').read_text())
    for index, record in enumerate(manifest['files'], 1):
        path = root / record['destination']
        if path.is_symlink() or not path.is_file() or sha(path) != record['sha256']:
            raise ValueError('Archive differs from source: ' + str(path))
        if index % 20000 == 0:
            print('Verified', index, 'files', flush=True)
    counts = {}
    for dataset, expected in DATASETS.items():
        receipts = sorted((root / dataset).glob('*/completion.json'))
        if len(receipts) != expected:
            raise ValueError('Wrong dataset count: ' + dataset)
        for receipt in receipts:
            case = receipt.parent
            done = json.loads(receipt.read_text())
            if done['status'] != 'complete':
                raise ValueError('Unfinished case: ' + str(case))
            for name in ['inputs', 'prior_generation', 'registration', 'diagnostics',
                         'refinement', 'fusion', 'provenance', 'logs', 'metrics']:
                if not (case / name).is_dir():
                    raise ValueError('Missing stage: ' + str(case / name))
            for label, relative in [('refinement', 'refinement/selected_100k.ply'),
                                    ('final', 'fusion/observation_anchored_fused_100k.ply')]:
                path = case / relative
                if sha(path) != done[label + '_sha256'] or ply_count(path) != 100000:
                    raise ValueError('Final carrier mismatch: ' + str(path))
        counts[dataset] = len(receipts)
    result = {'status': 'verified', 'source_files_verified': len(manifest['files']),
              'datasets': counts, 'samples': sum(counts.values()),
              'scope': 'All copied bytes and finalized stage carriers; independent of original absolute paths.'}
    (root / 'archive_verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
