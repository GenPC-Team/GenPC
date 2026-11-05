#!/usr/bin/env python3
"""Audit fixed diagnostic views and partial visibility, without completion or GT."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.diagnostic_view_policy import fixed_six_view_manifest
from src.multiview_partial_evidence import PoseProjector
from src.pointcloud_io import load_points
from src.zbuffer import zbuffer_depth_with_indices


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();rows=[]
    for path in sorted(args.dataset_root.glob('*/*/diagnostics/render/render_manifest.json')):
        case=path.parents[2];source=json.loads(path.read_text());manifest=fixed_six_view_manifest(source)
        centre=np.asarray(manifest['centre']);directions=[];seen=np.zeros(0,dtype=bool)
        partial=load_points(case/'inputs/partial'/f'{case.name}.ply')
        seen=np.zeros(len(partial),dtype=bool);counts=[]
        for item in manifest['views']:
            pose=np.asarray(item['camera_pose']);offset=pose[:3,3]-centre
            directions.append(offset/np.linalg.norm(offset))
            view=PoseProjector(pose,float(manifest['field_of_view_degrees']),512)
            uv,depth=view.project(partial)
            _,_,index=zbuffer_depth_with_indices(uv,depth,view.image_shape,0)
            seen[np.unique(index[index>=0])]=True;counts.append(int(seen.sum()))
        angles=np.degrees(np.arccos(np.clip(np.asarray(directions)@np.asarray(directions).T,-1,1)))
        rows.append({'dataset':case.parent.name,'sample':case.name,'manifest':str(path.resolve()),
                     'source_preserved':manifest['views'][:4]==source['views'],'view_count':6,
                     'added_angles_degrees':[-35,35],
                     'minimum_new_to_original_angle_degrees':float(angles[4:,:4].min()),
                     'partial_points':len(partial),'four_view_unique_visible_fraction':counts[3]/len(partial),
                     'six_view_unique_visible_fraction':counts[5]/len(partial),
                     'additional_visible_fraction':(counts[5]-counts[3])/len(partial)})
        print(case.parent.name,case.name,'audited',flush=True)
    summaries={}
    for dataset in sorted({r['dataset'] for r in rows}):
        subset=[r for r in rows if r['dataset']==dataset]
        summaries[dataset]={'count':len(subset),**{key:float(np.mean([r[key] for r in subset])) for key in
                           ['four_view_unique_visible_fraction','six_view_unique_visible_fraction','additional_visible_fraction']}}
    result={'policy':'preserve_four_plus_fixed_elevation_pair_v1','ground_truth_used':False,
            'performance_evaluation':False,'resolution':512,'splat_radius':0,
            'interpretation':'Unique already-scanned point slots visible in synthetic diagnostic projections; not new physical observations or a completion metric.',
            'datasets':summaries,'cases':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
