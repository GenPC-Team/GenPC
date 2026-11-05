#!/usr/bin/env python3
"""Isolated 2D+3D residual registration from a saved MoGe-aligned carrier."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from src.differentiable_registration import refine_differentiable_sim3
from src.gpt_refine_agent import render_diagnostic_board
from src.multiview_partial_evidence import load_manifest_projectors
from src.pointcloud_io import load_points,write_points
from src.saved_camera import SavedCameraProjector


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('prior','partial','camera','multiview-manifest','output-dir'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--device',default='cuda')
    args=parser.parse_args()
    prior,partial=load_points(args.prior),load_points(args.partial)
    projector=SavedCameraProjector.from_partial(partial,args.camera,padding=.15,
                                               image_shape=(512,512),device=args.device)
    result,report=refine_differentiable_sim3(prior,partial,projector,device=args.device)
    out=args.output_dir
    out.mkdir(parents=True,exist_ok=True)
    report['inputs']={key:str(getattr(args,key).resolve())
                      for key in ('prior','partial','camera','multiview_manifest')}
    write_points(out/'registered_100k.ply',result)
    views=load_manifest_projectors(args.multiview_manifest)
    render_diagnostic_board(partial,prior,views,out/'before.png')
    render_diagnostic_board(partial,result,views,out/'after.png')
    (out/'registration_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'output':str(out),'accepted':report['accepted'],
                      'before':report['before'],'after':report['after']}),flush=True)


if __name__=='__main__':
    main()
