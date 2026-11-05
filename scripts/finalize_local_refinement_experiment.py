#!/usr/bin/env python3
"""Audit local connectivity and execute the unchanged final fusion stage.

Unchanged refined inputs reuse their previously executed fusion result by
content equality. No GT or completion metric is read by this script.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.local_refinement_stage import connectivity_audit
from src.pointcloud_io import load_points


def relocate(value,old,new):
    if isinstance(value,str): return value.replace(old,new)
    if isinstance(value,list): return [relocate(x,old,new) for x in value]
    if isinstance(value,dict): return {k:relocate(v,old,new) for k,v in value.items()}
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','local-root','output-root'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--workers',type=int,default=1)
    args=parser.parse_args()
    sources=sorted(p for p in args.source_root.iterdir()
                   if p.is_dir() and (p/'inputs/partial'/f'{p.name}.ply').is_file())
    for root in sources:
        if not (args.local_root/root.name/'report.json').is_file():
            raise FileNotFoundError(f'local review is incomplete: {root.name}')
    args.output_root.mkdir(parents=True,exist_ok=True)
    def run(root):
        sid=root.name
        out=args.output_root/sid
        out.mkdir(parents=True,exist_ok=True)
        report=json.loads((args.local_root/sid/'report.json').read_text())
        candidate=args.local_root/sid/'selected_100k.ply'
        baseline=root/'refinement'/sid/'agent_selected_posterior_100k.ply'
        reference,points=load_points(baseline),load_points(candidate)
        changed=not np.array_equal(reference,points)
        audit=connectivity_audit(reference,points) if changed else {'passed':True,'reason':'identical_carrier'}
        selected=candidate if audit['passed'] else baseline
        shutil.copyfile(selected,out/'refined_100k.ply')
        changed=changed and audit['passed']
        state={'ground_truth_used':False,'connectivity':audit,'changed':changed,
               'source_root':str(root.resolve()),'local_report':str((args.local_root/sid/'report.json').resolve()),
               'architecture':['prior_generation_agent','registration','refinement_agent','fusion']}
        if changed:
            manifest=json.loads((root/'residuals'/sid/'render/render_manifest.json').read_text())
            old=str(Path(manifest['registered_carrier']).parents[3])
            manifest=relocate(manifest,old,str(root.resolve()))
            path=out/'render_manifest.json'
            path.write_text(json.dumps(manifest,indent=2)+'\n')
            command=[sys.executable,str(ROOT/'scripts/run_observation_anchored_fusion.py'),
                     '--posterior',str(out/'refined_100k.ply'),
                     '--partial',str(root/'inputs/partial'/f'{sid}.ply'),
                     '--multiview-manifest',str(path),'--mode','continuous',
                     '--carrier-colors-from',str(root/'inputs/pixal'/sid/'pixal3d_sampled_100k.ply'),
                     '--output-dir',str(out/'fusion')]
            with (out/'fusion.log').open('w') as log:
                subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            final=out/'fusion/observation_anchored_fused_100k.ply'
            state['fusion']={'mode':'executed','command':command}
        else:
            final=root/'fusion'/sid/'observation_anchored_fused_100k.ply'
            state['fusion']={'mode':'cached_identical_refined_input','source':str(final.resolve())}
        shutil.copyfile(final,out/'final_100k.ply')
        state['final_sha256']=hashlib.sha256((out/'final_100k.ply').read_bytes()).hexdigest()
        (out/'finalization.json').write_text(json.dumps(state,indent=2)+'\n')
        return sid,state
    records={}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(run,p) for p in sources]):
            sid,state=future.result(); records[sid]=state
            (args.output_root/'batch.json').write_text(json.dumps(records,indent=2)+'\n')
            print(json.dumps({'sample':sid,'changed':state['changed'],'connectivity':state['connectivity']}),flush=True)


if __name__=='__main__':
    main()
