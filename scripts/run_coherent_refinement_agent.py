#!/usr/bin/env python3
"""Plan, act and review bounded local rigid moves using positive partial evidence."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.coherent_local_refinement import local_rigid_candidates
from src.gpt_refine_agent import GPTRefineAgent, render_diagnostic_board
from src.local_refinement_stage import connectivity_audit
from src.multiview_partial_evidence import load_manifest_projectors
from src.planned_local_refinement import (
    POLICY_VERSION, REGION_INSTRUCTIONS, CumulativeLocalGuard,
    annotate_region_handles, plan_region, square_crop_projectors,
)
from src.pointcloud_io import jsonable, load_points, write_points
from src.posterior_agent import observe


def candidate_key(record):
    return hashlib.sha256(json.dumps({
        'source': sorted(record['source_ids']),
        'translation': np.round(record['translation'], 9).tolist(),
    }, sort_keys=True).encode()).hexdigest()


def run(args):
    if not 1 <= args.maximum_rounds <= 3:
        raise ValueError('local planning uses one to three bounded rounds')
    out = args.output_dir
    if (out/'report.json').exists():
        raise ValueError('use a new output directory for a new local policy run')
    out.mkdir(parents=True, exist_ok=True)
    initial, partial = load_points(args.carrier), load_points(args.partial)
    if len(initial) != 100_000:
        raise ValueError('the complete ordered 100k carrier is required')
    shutil.copyfile(args.carrier, out/'reference_100k.ply')
    views = load_manifest_projectors(args.multiview_manifest)
    agent = GPTRefineAgent(args.gpt_model, provider='codex')
    guard = CumulativeLocalGuard(initial, partial)
    current = initial.copy()
    observation, caches = observe(partial, current, views)
    report = {
        'policy_version': POLICY_VERSION, 'ground_truth_used': False,
        'category_or_part_rules_used': False, 'gpt_model': args.gpt_model,
        'maximum_rounds': args.maximum_rounds, 'region_instructions': REGION_INSTRUCTIONS,
        'before_observation': asdict(observation), 'regions': [], 'trace': [],
        'selected_candidate': None,
        'inputs': {key: str(getattr(args, key).resolve()) for key in
                   ('carrier', 'partial', 'multiview_manifest')},
        'input_sha256': {key: hashlib.sha256(getattr(args, key).read_bytes()).hexdigest() for key in
                         ('carrier', 'partial', 'multiview_manifest')},
        'code_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
            'src/coherent_local_refinement.py', 'src/planned_local_refinement.py',
            'src/gpt_refine_agent.py', 'src/local_refinement_stage.py',
            'scripts/run_coherent_refinement_agent.py')},
    }
    rejected = set()
    history = []
    for round_index in range(args.maximum_rounds):
        directory = out/f'round_{round_index+1:02d}'
        directory.mkdir(exist_ok=True)
        generated, geometric_report = local_rigid_candidates(current, partial)
        report['config'] = geometric_report['config']
        round_record = {'round': round_index+1, 'geometry': geometric_report,
                        'before_observation': asdict(observation)}
        report['trace'].append(round_record)
        candidates = []
        for points, record, weight in generated:
            record['round'] = round_index+1
            record['cumulative_integrity'] = guard.check(points)
            report['regions'].append(record)
            if candidate_key(record) in rejected:
                record['planning_rejected'] = 'already_rejected_association'
            elif not record['cumulative_integrity']['passed']:
                record['planning_rejected'] = record['cumulative_integrity']['reason']
            else:
                candidates.append((points, record, weight))
        candidates.sort(key=lambda item: -item[1]['mean_observation_gain'])
        if not candidates:
            round_record['stop'] = 'no_supported_safe_region'
            break
        depth_reference = np.concatenate([partial, current, *[x[0] for x in candidates]])
        full_before = render_diagnostic_board(
            partial, current, views, directory/'before.png', depth_reference_points=depth_reference)
        crops_before, crops_after = [], []
        for i, (points, record, weight) in enumerate(candidates):
            path = directory/f'region_{i:02d}.ply'
            write_points(path, points)
            record['candidate'] = str(path.resolve())
            focus = np.concatenate([current[weight > .5], points[weight > .5],
                                    partial[np.asarray(record['partial_ids'])]])
            crops = square_crop_projectors(views, focus)
            crops_before.append(render_diagnostic_board(
                partial, current, crops, directory/f'region_{i:02d}_before.png',
                depth_reference_points=depth_reference))
            crops_after.append(render_diagnostic_board(
                partial, points, crops, directory/f'region_{i:02d}_after.png',
                depth_reference_points=depth_reference))
        overview = annotate_region_handles(
            full_before, directory/'numbered_regions.png', partial, current, views, candidates)
        plan = plan_region(agent, candidates, overview=overview, crops=crops_before,
                           history=history, rounds_left=args.maximum_rounds-round_index)
        round_record['plan'] = plan
        if plan['decision']['action'] == 'KEEP_CURRENT':
            round_record['stop'] = 'planner_kept_current'
            break
        chosen = plan['decision']['candidate_id']
        points, record, weight = candidates[chosen]
        after, _ = observe(partial, points, views, caches=caches)
        record['after_observation'] = asdict(after)
        integrity = connectivity_audit(current, points)
        round_record['chosen_candidate_id'] = chosen
        round_record['connectivity'] = integrity
        reason = None
        if not integrity['passed']:
            reason = 'connectivity_failed'
        elif any(b < a-.02 for a, b in zip(observation.coverage, after.coverage)):
            reason = 'view_coverage_regressed'
        else:
            full_after = render_diagnostic_board(
                partial, points, views, directory/'proposal.png', depth_reference_points=depth_reference)
            review = agent.review(
                observation, after, before_board=full_before, after_board=full_after,
                profile='PLANNED_LOCAL_RIGID', transport='COHERENT_PARTIAL_RESIDUAL',
                integrity=integrity,
                remaining_candidates=max(0, min(len(candidates)-1, args.maximum_rounds-round_index-1)),
                local_boards=(crops_before[chosen], crops_after[chosen]),
                local_diagnostics={
                    'planned_correspondence': plan['decision'],
                    'cumulative_integrity': record['cumulative_integrity'],
                    'local_gain': record['local_gain'], 'local_strain': record['local_strain'],
                    'previous_accepted_cores': len(guard.cores),
                })
            record['gpt_review'] = review
            round_record['review'] = review
            if review['decision']['action'] != 'ACCEPT_UPDATE':
                reason = review['decision']['reason']
                round_record['review_stop'] = review['decision']['action'] == 'STOP_KEEP_CURRENT'
        accepted = reason is None
        round_record['accepted'] = accepted
        history.append({'round': round_index+1, 'accepted': accepted,
                        'association': plan['decision'], 'failure': reason})
        if accepted:
            current, observation = points, after
            core = np.flatnonzero(weight > .999999)
            guard.protect_core(current, core)
            np.save(directory/'protected_core.npy', core)
            report['selected_candidate'] = record['candidate']
            round_record['protected_core'] = str((directory/'protected_core.npy').resolve())
        else:
            rejected.add(candidate_key(record))
            if round_record.get('review_stop'):
                break
    report['after_observation'] = asdict(observation)
    report['accepted_steps'] = sum(bool(x.get('accepted')) for x in report['trace'])
    report['final_integrity'] = guard.check(current)
    if not report['final_integrity']['passed']:
        raise RuntimeError('final cumulative integrity failed')
    if report['selected_candidate'] is None:
        shutil.copyfile(args.carrier, out/'selected_100k.ply')
    else:
        write_points(out/'selected_100k.ply', current)
    (out/'report.json').write_text(json.dumps(jsonable(report), indent=2)+'\n')
    print(json.dumps({'output': str(out), 'accepted_steps': report['accepted_steps'],
                      'policy': POLICY_VERSION}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('carrier', 'partial', 'multiview-manifest', 'output-dir'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--gpt-model', default='gpt-6-astra')
    parser.add_argument('--maximum-rounds', type=int, default=3)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
