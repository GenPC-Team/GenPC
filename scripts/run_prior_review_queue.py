#!/usr/bin/env python3
"""Review each newly generated prior once, preserving rejected-candidate evidence."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_updated_dataset_suite import sha,write_json


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--gpu',default='5')
    a=ap.parse_args();rows=[]
    for path in sorted(a.root.glob('*/prior_agent/prior_agent_manifest.json')):
        out=path.parents[1];state=json.loads(path.read_text());image=out/'semantic.png'
        if state.get('accepted') or not image.exists():continue
        digest=sha(image)
        if any(r['candidate_sha256']==digest for r in state['reviews']):continue
        command=[sys.executable,str(ROOT/'scripts/run_prior_generation_agent.py'),'review',
                 '--output-root',str(out.resolve()),'--candidate',str(image.resolve()),'--model','gpt-6-astra']
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        with (out/f'review_{stamp}.log').open('w') as log:
            completed=subprocess.run(command,cwd=ROOT,env={**os.environ,'CUDA_VISIBLE_DEVICES':a.gpu,
                   'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'},stdout=log,stderr=subprocess.STDOUT)
        state=json.loads(path.read_text());row={'sample':state['sample'],'returncode':completed.returncode,
             'accepted':bool(state.get('accepted')),'candidate_sha256':digest,
             'next_prompt':None if state.get('accepted') else state['current_prompt_file']}
        rows.append(row);print(json.dumps(row),flush=True)
    write_json(a.root/'latest_review_queue.json',rows)


if __name__=='__main__':main()
