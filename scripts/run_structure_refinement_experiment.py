#!/usr/bin/env python3
"""Run common no-GT experiments from frozen four-stage sample directories."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--mode',choices=('local','registration','planned'),required=True)
    parser.add_argument('--workers',type=int,default=1)
    parser.add_argument('--samples',nargs='+')
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    sources=sorted(p for p in args.source_root.iterdir()
                   if p.is_dir() and (p/'inputs/partial'/f'{p.name}.ply').is_file()
                   and (args.samples is None or p.name in args.samples))
    if not sources:
        raise ValueError('no complete sample input directories found')
    args.output_root.mkdir(parents=True,exist_ok=True)
    state={'ground_truth_used':False,'mode':args.mode,
           'started':datetime.now(timezone.utc).isoformat(),
           'source':str(args.source_root.resolve()),'samples':{}}
    def run(root):
        sid=root.name
        output=args.output_root/sid
        output.mkdir(parents=True,exist_ok=True)
        report=output/('registration_report.json' if args.mode=='registration' else 'report.json')
        if args.resume and report.is_file():
            return sid,{'status':'existing','report':str(report.resolve())}
        script={'local':'probe_local_rigid_refinement.py',
                'planned':'run_coherent_refinement_agent.py',
                'registration':'probe_differentiable_registration.py'}[args.mode]
        command=[sys.executable,str(ROOT/'scripts'/script)]
        if args.mode!='registration':
            command += ['--carrier',str(root/'refinement'/sid/'agent_selected_posterior_100k.ply'),
                        '--gpt-model','gpt-6-astra']
            if args.mode=='local':
                command.append('--review')
        else:
            command += ['--prior',str(root/'registration'/sid/'final/camera1_amplified_registered_100k.ply'),
                        '--camera',str(root/'inputs/camera'/sid/'camera.pth')]
        command += ['--partial',str(root/'inputs/partial'/f'{sid}.ply'),
                    '--multiview-manifest',str(root/'residuals'/sid/'render/render_manifest.json'),
                    '--output-dir',str(output)]
        with (output/'run.log').open('w') as log:
            result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        record={'status':'complete' if result.returncode==0 else 'failed',
                'returncode':result.returncode,'command':command,'report':str(report.resolve())}
        if result.returncode==0:
            data=json.loads(report.read_text())
            record['changed']=bool(data['accepted'] if args.mode=='registration' else data.get('selected_candidate'))
        return sid,record
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        tasks=[pool.submit(run,p) for p in sources]
        for task in as_completed(tasks):
            sid,record=task.result()
            state['samples'][sid]=record
            (args.output_root/'batch.json').write_text(json.dumps(state,indent=2)+'\n')
            print(json.dumps({'sample':sid,**{k:v for k,v in record.items()
                             if k in ('status','changed','returncode')}}),flush=True)
    if any(r['status']=='failed' for r in state['samples'].values()):
        raise SystemExit(1)


if __name__=='__main__':
    main()
