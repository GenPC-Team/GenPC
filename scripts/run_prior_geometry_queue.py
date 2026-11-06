#!/usr/bin/env python3
"""Rebuild Pixal/MoGe, fixed registration and diagnostics for accepted new priors."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_updated_dataset_suite import write_json


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--roots',nargs='+',type=Path,required=True)
    ap.add_argument('--gpu',default='1')
    ap.add_argument('--require-all',action='store_true',help='Fail if any prepared prior is still unaccepted')
    a=ap.parse_args();failed=[]
    for root in a.roots:
        for path in sorted(root.glob('*/prior_agent/prior_agent_manifest.json')):
            state=json.loads(path.read_text())
            if not state.get('accepted'):
                if a.require_all:failed.append({'sample':state['sample'],'reason':'prior_not_accepted'})
                continue
            out=path.parents[1]
            command=[sys.executable,str(ROOT/'scripts/run_four_stage_pipeline.py'),
                     '--output-root',str(out.resolve()),'--gpt-model','gpt-6-astra','--stop-after','diagnostics']
            stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
            with (out/f'geometry_{stamp}.log').open('w') as log:
                result=subprocess.run(command,cwd=ROOT,env={**os.environ,'CUDA_VISIBLE_DEVICES':a.gpu,
                       'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'},stdout=log,stderr=subprocess.STDOUT)
            record={'sample':state['sample'],'returncode':result.returncode,'command':command,
                    'timestamp':datetime.now(timezone.utc).isoformat(),'ground_truth_used':False}
            write_json(out/'geometry_queue.json',record);print(json.dumps(record),flush=True)
            if result.returncode:failed.append(record)
    if failed:
        print(json.dumps({'incomplete_geometry':failed}),flush=True)
        raise SystemExit(1)


if __name__=='__main__':main()
