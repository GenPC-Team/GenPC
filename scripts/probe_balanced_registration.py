#!/usr/bin/env python3
"""Compare fine-registration ablations using frozen, dataset-organized inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.balanced_registration import refine_balanced_sim3
from src.pointcloud_io import load_points,write_points
from src.multiview_partial_evidence import load_manifest_projectors
from src.gpt_refine_agent import render_diagnostic_board
from src.saved_camera import SavedCameraProjector


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input-root',type=Path,default=ROOT/'workspace/refinement_final')
    ap.add_argument('--output-root',type=Path,required=True)
    ap.add_argument('--cases',nargs='+',required=True,help='dataset/sample')
    ap.add_argument('--render',action='store_true')
    a=ap.parse_args();a.output_root.mkdir(parents=True,exist_ok=True)
    summary=[]
    for case in a.cases:
        p=a.input_root/case;out=a.output_root/case/'registration';out.mkdir(parents=True,exist_ok=True)
        if (out/'comparison.json').exists():
            summary.append(json.loads((out/'comparison.json').read_text()));continue
        prior_path=p/'registration/final/camera1_amplified_registered_100k.ply'
        partial_path=p/'inputs/partial'/f'{p.name}.ply'
        manifest=p/'diagnostics/render/render_manifest.json'
        prior,partial=load_points(prior_path),load_points(partial_path)
        views=load_manifest_projectors(manifest)
        camera=p/'inputs/camera'/p.name/'camera.pth'
        projector=SavedCameraProjector.from_partial(partial,camera,padding=.15,image_shape=(512,512),device='cpu')
        record={'case':case,'ground_truth_used':False,'inputs':{},'variants':{}}
        for name,path in [('prior',prior_path),('partial',partial_path),('views',manifest),('camera',camera)]:
            record['inputs'][name]={'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        for name,reciprocal,balanced in [('joint_only',False,False),('reciprocal_only',True,False),('balanced_only',False,True),('full',True,True)]:
            result,report=refine_balanced_sim3(prior,partial,projector,reciprocal=reciprocal,balanced=balanced)
            dest=out/name;dest.mkdir(exist_ok=True)
            write_points(dest/'registered_100k.ply',result)
            report['code_sha256']=hashlib.sha256((ROOT/'src/balanced_registration.py').read_bytes()).hexdigest()
            (dest/'report.json').write_text(json.dumps(report,indent=2)+'\n')
            record['variants'][name]={k:report[k] for k in ['accepted','before','after']}
            if a.render and name=='full':
                depth=np.concatenate([partial,prior,result])
                render_diagnostic_board(partial,prior,views,out/'before.png',depth_reference_points=depth)
                render_diagnostic_board(partial,result,views,out/'after.png',depth_reference_points=depth)
        (out/'comparison.json').write_text(json.dumps(record,indent=2)+'\n');summary.append(record)
        (a.output_root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        r=record['variants']['full'];print(case,r['accepted'],r['before']['balanced_mean'],r['after']['balanced_mean'],flush=True)
    (a.output_root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

if __name__=='__main__':main()
