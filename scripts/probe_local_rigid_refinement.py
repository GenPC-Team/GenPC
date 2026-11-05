#!/usr/bin/env python3
"""Generate local rigid proposals from frozen refinement, without GT access."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import shutil
import hashlib
from dataclasses import asdict
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.coherent_local_refinement import local_rigid_candidates
from src.gpt_refine_agent import GPTRefineAgent, render_diagnostic_board
from src.posterior_agent import observe
from src.multiview_partial_evidence import load_manifest_projectors
from src.pointcloud_io import load_points, write_points


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--carrier', type=Path, required=True)
    parser.add_argument('--partial', type=Path, required=True)
    parser.add_argument('--multiview-manifest', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--review', action='store_true')
    parser.add_argument('--gpt-model', default='gpt-6-astra')
    args = parser.parse_args()
    carrier, partial = load_points(args.carrier), load_points(args.partial)
    candidates, report = local_rigid_candidates(carrier, partial)
    report['policy_version'] = 'local_rigid_v2_depth_structure_review'
    report['code_sha256'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        for name in ('src/coherent_local_refinement.py','src/gpt_refine_agent.py',
                     'scripts/probe_local_rigid_refinement.py')}
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    views = load_manifest_projectors(args.multiview_manifest)
    before, caches = observe(partial, carrier, views)
    report['before_observation'] = asdict(before)
    candidates.sort(key=lambda x: -x[1]['mean_observation_gain'])
    for i, (points, record, weight) in enumerate(candidates):
        depth_reference = np.r_[partial,carrier,points]
        write_points(out/f'candidate_{i:02d}.ply', points)
        render_diagnostic_board(partial, carrier, views, out/f'before_{i:02d}.png',depth_reference_points=depth_reference)
        render_diagnostic_board(partial, points, views, out/f'candidate_{i:02d}.png',depth_reference_points=depth_reference)
        record['candidate'] = str((out/f'candidate_{i:02d}.ply').resolve())
        focus = np.r_[carrier[weight>.5], points[weight>.5]]
        render_diagnostic_board(partial, carrier, views, out/f'local_{i:02d}_before.png', focus_points=focus,depth_reference_points=depth_reference)
        render_diagnostic_board(partial, points, views, out/f'local_{i:02d}_after.png', focus_points=focus,depth_reference_points=depth_reference)
    report['selected_candidate'] = None
    if args.review and candidates:
        agent = GPTRefineAgent(args.gpt_model, provider='codex')
        for i,(points,record,weight) in enumerate(candidates[:3]):
            after,_ = observe(partial,points,views,caches=caches)
            record['after_observation'] = asdict(after)
            # The complete four-view evidence is checked before visual review.
            if any(b<a-.02 for a,b in zip(before.coverage,after.coverage)):
                record['review_rejected'] = 'view_coverage_regressed'
                continue
            record['gpt_review'] = agent.review(
                before, after, before_board=out/f'before_{i:02d}.png', after_board=out/f'candidate_{i:02d}.png',
                profile='LOCAL_RIGID_TRANSLATION', transport='COHERENT_PARTIAL_RESIDUAL',
                integrity={'passed': True}, remaining_candidates=min(3,len(candidates))-i-1,
                local_boards=(out/f'local_{i:02d}_before.png',out/f'local_{i:02d}_after.png'),
                local_diagnostics={k:v for k,v in record.items() if k not in
                                   ('partial_ids','source_ids','line_search')},
            )
            action=record['gpt_review']['decision']['action']
            if action == 'ACCEPT_UPDATE':
                report['selected_candidate'] = record['candidate']
                break
            if action == 'STOP_KEEP_CURRENT':
                break
    if args.review:
        shutil.copyfile(report['selected_candidate'] or args.carrier, out/'selected_100k.ply')
    report['inputs'] = {key: str(getattr(args, key).resolve())
                        for key in ('carrier','partial','multiview_manifest')}
    report['input_sha256'] = {key: hashlib.sha256(getattr(args,key).read_bytes()).hexdigest()
                              for key in report['inputs']}
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'output': str(out), 'regions': len(report['regions']),
                      'eligible': len(candidates)}), flush=True)


if __name__ == '__main__':
    main()
