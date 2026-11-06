#!/usr/bin/env python3
"""Copy a finalized dataset suite into a fresh, hash-verified paper archive."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo


DATASETS = {'redwood': 10, 'custom': 10, 'kitti': 20, 'waymo': 76, 'aircraft': 40}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--approval-note', default='UNKNOWN',
                        help='Verbatim user acceptance or UNKNOWN when not approved.')
    args = parser.parse_args()
    source, destination = args.source.resolve(), args.destination.resolve()
    if source == destination or source in destination.parents or destination.exists():
        raise ValueError('Destination must be fresh and outside the source tree')
    for dataset, expected in DATASETS.items():
        summary = json.loads((source / dataset / 'summary.json').read_text())
        if summary['sample_count'] != expected or summary['status'] != 'complete_for_current_experiment':
            raise ValueError('Dataset is not finalized: ' + dataset)
    destination.mkdir(parents=True)
    records = []
    top_level = set(DATASETS) | {'offline_evaluation', 'README.md', 'RESULTS.md'}
    for path in sorted(source.rglob('*')):
        if '__pycache__' in path.parts or not path.is_file():
            continue
        relative = path.relative_to(source)
        target_relative = relative if relative.parts[0] in top_level else Path('experiment') / relative
        target = destination / target_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        before = sha(path)
        shutil.copy2(path, target)
        if sha(target) != before:
            raise ValueError('Copy checksum mismatch: ' + str(path))
        records.append({'source': str(relative), 'destination': str(target_relative),
                        'bytes': target.stat().st_size, 'sha256': before})
        if len(records) % 10000 == 0:
            print('Copied and verified', len(records), 'files', flush=True)
    stamp = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    accepted = []
    for dataset in DATASETS:
        for receipt in sorted((destination / dataset).glob('*/completion.json')):
            case = receipt.parent
            report = json.loads((case / 'refinement/report.json').read_text())
            prompts = {str(p.relative_to(destination)): p.read_text()
                       for p in case.rglob('*.txt') if 'prompt' in p.name.lower()}
            accepted.append({
                'timestamp': stamp, 'dataset': dataset, 'sample': case.name,
                'outputs': [str(case / 'fusion/observation_anchored_fused_100k.ply'),
                            str(case / 'fusion/final_red_partial_blue.ply')],
                'inputs': str(case / 'inputs'), 'model': report['model'],
                'checkpoint': 'UNKNOWN', 'verbatim_prompt_files': prompts,
                'refinement_instructions': report['instructions'],
                'per_round_full_prompts': str(case / 'refinement/round_*/plan_prompt.json'),
                'negative_prompt': 'UNKNOWN', 'hosted_seed_steps_guidance_scheduler': 'UNKNOWN',
                'recorded_parameters': str(case / 'provenance'),
                'saved_camera_resize_masks': str(case / 'inputs/camera'),
                'postprocessing': 'Saved RMBG/Pixal/MoGe/registration; autonomous six-view refinement; continuous fusion.',
                'approval': args.approval_note,
                'preservation': 'Do not overwrite approved artifacts without asking.',
                'exactly_reproducible': False,
                'note': 'Historical per-file metadata remains authoritative; unknown fields are not inferred.'})
    (destination / 'accepted_results.json').write_text(json.dumps(accepted, indent=2, ensure_ascii=False) + '\n')
    (destination / 'copy_manifest.json').write_text(json.dumps({
        'timestamp': stamp, 'source': str(source), 'destination': str(destination),
        'status': 'verified', 'sample_count': len(accepted), 'file_count': len(records),
        'bytes': sum(row['bytes'] for row in records), 'files': records,
        'historical_paths': 'JSON paths are preserved verbatim. Use source/destination mapping to locate archived files.'}, indent=2) + '\n')
    (destination / 'SHA256SUMS').write_text(''.join(f"{row['sha256']}  {row['destination']}\n" for row in records))
    print(json.dumps({'samples': len(accepted), 'files': len(records), 'destination': str(destination)}), flush=True)


if __name__ == '__main__':
    main()
