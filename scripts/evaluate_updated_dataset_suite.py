#!/usr/bin/env python3
"""Offline-only evaluation of frozen updated-suite outputs; never called by inference."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_updated_dataset_suite import write_json,sha,ply_count,DATASETS
from src.offline_metrics import evaluate_cd_emd_repeated


def observed_support_metrics(out, dataset, sid, refined, final):
    """One-way observation fit, not complete-shape CD or EMD."""
    from scipy.spatial import cKDTree
    from src.pointcloud_io import load_points
    partial_path=out/'inputs/partial'/f'{sid}.ply'
    partial=load_points(partial_path)
    diagonal=float(np.linalg.norm(np.ptp(partial,axis=0)))
    if not np.isfinite(partial).all() or diagonal<=0:
        raise ValueError('invalid observed support: '+sid)
    baseline=ROOT/DATASETS[dataset][0]/sid
    if sha(baseline/'inputs/partial'/f'{sid}.ply')!=sha(partial_path):
        raise ValueError('old/new partials differ: '+sid)
    stages={'old_registration':baseline/'registration'/sid/'final/camera1_amplified_registered_100k.ply',
            'old_refinement':baseline/'refinement'/sid/'agent_selected_posterior_100k.ply',
            'old_fusion':baseline/'fusion'/sid/'observation_anchored_fused_100k.ply',
            'updated_registration':out/'registration/final/camera1_amplified_registered_100k.ply',
            'updated_refinement':refined,'updated_fusion':final}
    rows=[]
    for stage,path in stages.items():
        digest=sha(path);points=load_points(path)
        if len(points)!=100000 or not np.isfinite(points).all():
            raise ValueError('invalid 100k comparison carrier: '+str(path))
        distances=cKDTree(points).query(partial)[0]
        rows.append({'dataset':dataset,'sample':sid,'stage':stage,'sha256':digest,
                     'path':str(path.resolve()),'mean_input_units':float(distances.mean()),
                     'mean_percent_observed_diagonal':float(distances.mean()/diagonal*100),
                     'p95_percent_observed_diagonal':float(np.quantile(distances,.95)/diagonal*100)})
        if sha(path)!=digest:raise ValueError('comparison carrier changed: '+sid)
    write_json(out/'metrics/observed_support.json',{
        'offline_only':True,'ground_truth_used':False,'partial':str(partial_path.resolve()),
        'partial_sha256':sha(partial_path),'partial_diagonal':diagonal,
        'definition':'For each observed point, nearest distance to the complete 100k carrier; normalize by observed bounding-box diagonal.',
        'limitation':'One-way fit cannot assess unobserved completion quality, semantic correspondence or full-shape CD/EMD.',
        'stages':rows})
    return rows


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=ROOT/'workspace/refinement_updated')
    ap.add_argument('--datasets',nargs='+',default=['redwood','custom','kitti','waymo','aircraft'])
    ap.add_argument('--repeats',type=int,default=3)
    a=ap.parse_args();rows=[];cases=[];support_rows=[]
    protocol={'count':16384,'seed':6145,'repeats':a.repeats,'scale':100,
              'cd':'symmetric CD-L1','emd':'approximate EMD','offline_only':True}
    evaluation=a.root/'offline_evaluation';evaluation.mkdir(exist_ok=True)
    cache_path=evaluation/'cache.json';cache=json.loads(cache_path.read_text()) if cache_path.exists() else {}
    for dataset in a.datasets:
        for receipt in sorted((a.root/dataset).glob('*/completion.json')):
            out=receipt.parent;sid=out.name
            try:
                done=json.loads(receipt.read_text())
            except FileNotFoundError:
                # A budget continuation withdraws the receipt before mutation.
                continue
            if done['status']!='complete':continue
            report=json.loads((out/'refinement/report.json').read_text())
            if report['status'] not in {'pilot_stopped_with_trace','agent_stopped_no_actionable_issue'}:continue
            refined=out/'refinement/selected_100k.ply';final=out/'fusion/observation_anchored_fused_100k.ply'
            if sha(refined)!=done['refinement_sha256'] or sha(final)!=done['final_sha256']:
                raise ValueError('frozen completion changed: '+sid)
            case={'dataset':dataset,'sample':sid,'rounds':len(report['trace']),
                  'status':report['status'],'stop_reason':report.get('stop_reason'),
                  'selected_actions':dict(Counter(t['plan']['decision']['action'] for t in report['trace'])),
                  'accepted_actions':dict(Counter(t['plan']['decision']['action'] for t in report['trace'] if t.get('accepted'))),
                  'final_point_count':ply_count(final),'final_sha256':sha(final)}
            cases.append(case)
            if dataset in {'kitti','waymo'}:
                case['metrics']='NOT_AVAILABLE: no matched complete object GT'
                support_rows.extend(observed_support_metrics(out,dataset,sid,refined,final))
                continue
            gt=(ROOT/'data/custom'/sid/'gt_data'/f'{sid}_gt.ply' if dataset=='custom'
                else ROOT/f'data/{dataset}/gt'/f'{sid}.ply')
            baseline=ROOT/'workspace/refinement_final'/{'custom':'custom10','aircraft':'aircraft40','redwood':'redwood10'}[dataset]/sid
            stages={'registration':out/'registration/final/camera1_amplified_registered_100k.ply',
                    'old_refinement':baseline/'refinement/refined_100k.ply',
                    'old_fusion':baseline/'fusion/final_100k.ply',
                    'updated_refinement':refined,'updated_fusion':final}
            frozen={stage:{'path':str(path.resolve()),'sha256':sha(path)} for stage,path in stages.items()}
            write_json(out/'metrics/frozen_inputs.json',{'protocol':protocol,'stages':frozen,
                       'gt':str(gt.resolve()),'gt_sha256':sha(gt),'offline_only':True})
            sample_rows=[]
            for stage,path in stages.items():
                key=json.dumps([frozen[stage]['sha256'],sha(gt),protocol],sort_keys=True)
                if key not in cache:
                    cache[key]=(np.asarray(evaluate_cd_emd_repeated(path,gt,count=16384,seed=6145,repeats=a.repeats))*100).tolist()
                    write_json(cache_path,cache)
                values=np.asarray(cache[key]);assert sha(path)==frozen[stage]['sha256']
                row={'dataset':dataset,'sample':sid,'stage':stage,'cd_l1_x100':float(values[:,0].mean()),
                     'emd_x100':float(values[:,1].mean()),'emd_std':float(values[:,1].std()),
                     'sha256':frozen[stage]['sha256']}
                rows.append(row);sample_rows.append(row);print(json.dumps(row),flush=True)
            write_json(out/'metrics/metrics.json',{'protocol':protocol,'stages':sample_rows})
    # A finalized case can enter a budget continuation while other cases are
    # evaluated. Publish only receipts still describing the evaluated carrier.
    stable=[]
    for case in cases:
        receipt=a.root/case['dataset']/case['sample']/'completion.json'
        try:
            done=json.loads(receipt.read_text())
        except FileNotFoundError:
            continue
        if done['final_sha256']==case['final_sha256'] and done['rounds']==case['rounds']:
            stable.append(case)
    cases=stable
    keys={(c['dataset'],c['sample']) for c in cases}
    rows=[r for r in rows if (r['dataset'],r['sample']) in keys]
    support_rows=[r for r in support_rows if (r['dataset'],r['sample']) in keys]
    write_json(evaluation/'cases.json',cases);write_json(evaluation/'metrics.json',{'protocol':protocol,'rows':rows})
    write_json(evaluation/'observed_support.json',{'rows':support_rows,'ground_truth_used':False,
               'scope':'One-way observed fit only; not full-shape CD/EMD.'})
    if support_rows:
        with (evaluation/'observed_support.csv').open('w') as f:
            writer=csv.DictWriter(f,fieldnames=list(support_rows[0]));writer.writeheader();writer.writerows(support_rows)
    if rows:
        with (evaluation/'metrics.csv').open('w') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    means={dataset:{stage:{key:float(np.mean([r[key] for r in rows if r['dataset']==dataset and r['stage']==stage]))
                   for key in ['cd_l1_x100','emd_x100']}
                   for stage in sorted({r['stage'] for r in rows if r['dataset']==dataset})}
           for dataset in a.datasets}
    support_means={dataset:{stage:{key:float(np.mean([r[key] for r in support_rows if r['dataset']==dataset and r['stage']==stage]))
                   for key in ['mean_percent_observed_diagonal','p95_percent_observed_diagonal']}
                   for stage in sorted({r['stage'] for r in support_rows if r['dataset']==dataset})}
                   for dataset in a.datasets if dataset in {'kitti','waymo'}}
    write_json(evaluation/'summary.json',{'completed_case_counts':dict(Counter(c['dataset'] for c in cases)),
               'means':means,'observed_support_means':support_means,
               'observed_support_limitations':'One-way fit to input partial only; not a measure of unobserved shape accuracy.',
               'protocol':protocol,'scope':'Only completed frozen cases; this may be a partial dataset report.'})


if __name__=='__main__':main()
