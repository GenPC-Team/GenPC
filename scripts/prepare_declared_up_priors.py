#!/usr/bin/env python3
"""Rebuild unknown-camera prior tasks using a documented input-coordinate up axis."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_updated_dataset_suite import write_json,sha


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-root',type=Path,required=True)
    ap.add_argument('--output-root',type=Path,required=True)
    ap.add_argument('--world-up',nargs=3,type=float,required=True)
    ap.add_argument('--axis-evidence',required=True)
    a=ap.parse_args();records=[]
    for source in sorted(a.source_root.iterdir()):
        path=source/'prior_agent/prior_agent_manifest.json'
        if not path.exists():continue
        old=json.loads(path.read_text());sid=old['sample'];out=a.output_root/sid
        out.mkdir(parents=True,exist_ok=True)
        try:
            state_path=out/'prior_agent/prior_agent_manifest.json'
            if not state_path.exists():
                command=[sys.executable,str(ROOT/'scripts/run_prior_generation_agent.py'),'prepare',
                         '--sample',sid,'--partial',str((source/'inputs/partial'/f'{sid}.ply').resolve()),
                         '--object',old['object_description'],'--output-root',str(out.resolve()),
                         '--view-candidates','20','--world-up',*map(str,a.world_up),'--model','gpt-6-astra']
                with (out/'prepare.log').open('w') as log:
                    subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            state=json.loads(state_path.read_text())
            camera=json.loads(Path(state['camera_dir']).joinpath('camera.json').read_text())
            if camera['world_up']!=a.world_up:raise ValueError('existing camera has a different up convention')
            write_json(out/'coordinate_refresh.json',{'source':str(source.resolve()),
                'old_depth_sha256':sha(source/'inputs/camera'/sid/'depth.png'),
                'world_up':a.world_up,'axis_evidence':a.axis_evidence,'ground_truth_used':False,
                'new_view':state['selected_view'],'new_depth_sha256':sha(Path(state['selected_depth']))})
            if not state.get('depth_interpretation'):
                command=[sys.executable,str(ROOT/'scripts/run_prior_generation_agent.py'),'enrich',
                         '--output-root',str(out.resolve()),'--include-depth-framing','--model','gpt-6-astra']
                with (out/'enrich.log').open('w') as log:
                    subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            state=json.loads(state_path.read_text())
            row={'sample':sid,'status':'accepted' if state.get('accepted') else 'ready_for_imagegen','depth':state['selected_depth'],
                 'prompt':state['current_prompt_file']}
        except Exception as exc:row={'sample':sid,'status':'error','error':str(exc)}
        records.append(row);write_json(a.output_root/'preparation.json',records)
        print(json.dumps(row,ensure_ascii=False),flush=True)
    if any(x['status']=='error' for x in records):raise SystemExit(1)


if __name__=='__main__':main()
