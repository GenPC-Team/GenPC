#!/usr/bin/env python3
"""Astra audit of saved LiDAR priors and their original candidate cameras; no GT."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shutil
import sys
from PIL import Image

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.prior_generation_agent import PriorGenerationAgent, INSTRUCTIONS, PROMPT_VERSION
from scripts.run_updated_dataset_suite import write_json


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def audit(source, output, latest_review=False):
    state=json.loads((source/'prior_agent/prior_agent_manifest.json').read_text())
    sid=state['sample']; camera=source/'inputs/camera'/sid
    out=output/sid;out.mkdir(parents=True,exist_ok=True)
    sources=[camera/'depth.png',camera/'img.png',camera/'semantic_depth_audit.png']
    if latest_review:
        if not state['reviews']:
            raise ValueError('no candidate review is available for escalation')
        review_dir=Path(state['reviews'][-1]['candidate']).parent
        sources=[review_dir/'comparison_depth.png',review_dir/'img.png',review_dir/'semantic_depth_audit.png']
    signature={str(p.resolve()):sha(p) for p in sources}
    result_path=out/'audit.json'
    if result_path.exists():
        old=json.loads(result_path.read_text())
        if old['input_sha256']==signature and old['prompt_version']==PROMPT_VERSION:
            return old
        raise ValueError(f'audit input/policy changed; preserve old output and use a fresh audit directory: {sid}')
    size=Image.open(sources[0]).size
    images=[]
    for name,p in zip(['depth.png','semantic.png','overlay.png'],sources):
        with Image.open(p) as im:
            if im.size!=size:raise ValueError(f'different comparison canvases: {sid}, {p}')
        dst=out/name;shutil.copy2(p,dst);images.append(dst)
    boards=state['view_board']
    if isinstance(boards,str):boards=[boards]
    for i,path in enumerate(boards):
        src=Path(path)
        if not src.exists():src=source/'prior_agent'/src.name
        dst=out/f'candidate_board_{i}.png';shutil.copy2(src,dst);images.append(dst)
    (out/'instructions.txt').write_text(INSTRUCTIONS+'\n')
    write_json(out/'inputs.json',{'input_sha256':signature,'comparison_size':size,
                                'current_view':state['selected_view'],'source':str(source.resolve()),
                                'images':[str(p.resolve()) for p in images],
                                'ground_truth_used':False,'human_sample_hints':False})
    agent=PriorGenerationAgent('gpt-6-astra')
    result=agent.audit_existing_prior(images=images,current_view=state['selected_view'],
             view_ids=list(state['view_candidates']),object_description=state['object_description'])
    result.update(sample=sid,source=str(source.resolve()),input_sha256=signature,
                  ground_truth_used=False,comparison_size=size)
    write_json(result_path,result)
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-root',type=Path,required=True)
    ap.add_argument('--output-root',type=Path,required=True)
    ap.add_argument('--samples',nargs='+');ap.add_argument('--workers',type=int,default=2)
    ap.add_argument('--latest-review',action='store_true',help='Reassess the latest rejected/reviewed candidate and saved view alternatives')
    a=ap.parse_args()
    sources=[a.source_root/n for n in a.samples] if a.samples else sorted(
        p for p in a.source_root.iterdir() if (p/'prior_agent/prior_agent_manifest.json').exists())
    records=[]
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs={pool.submit(audit,p,a.output_root,a.latest_review):p.name for p in sources}
        for job in as_completed(jobs):
            try:
                r=job.result();row={'sample':r['sample'],'action':r['decision']['action'],
                                    'selected_view':r['decision']['selected_view'],'reason':r['decision']['reason']}
            except Exception as exc:row={'sample':jobs[job],'action':'ERROR','error':str(exc)}
            records.append(row);write_json(a.output_root/'summary.json',records)
            print(json.dumps(row,ensure_ascii=False),flush=True)
    if any(r['action']=='ERROR' for r in records):raise SystemExit(1)


if __name__=='__main__':main()
