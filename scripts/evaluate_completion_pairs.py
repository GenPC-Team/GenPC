#!/usr/bin/env python3
"""Offline paired evaluation of frozen outputs, including approximate EMD noise."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.offline_metrics import evaluate_cd_emd_repeated


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-root','candidate-root','ground-truth-root','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--baseline-template',default='{sample}/fusion/{sample}/observation_anchored_fused_100k.ply')
    parser.add_argument('--candidate-template',default='{sample}/final_100k.ply')
    parser.add_argument('--ground-truth-template',default='{sample}.ply')
    parser.add_argument('--samples',nargs='+',required=True)
    parser.add_argument('--count',type=int,default=16384)
    parser.add_argument('--seed',type=int,default=6145)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    if min(args.count,args.repeats)<1 or len(set(args.samples))!=len(args.samples):
        raise ValueError('positive count/repeats and distinct samples are required')
    rows=[]
    existing={}
    report={}
    if args.resume and args.output.exists():
        saved=json.loads(args.output.read_text())
        if any(saved[key]!=getattr(args,key) for key in ('count','seed','repeats')):
            raise ValueError('evaluation protocol changed')
        if [row['sample'] for row in saved['samples']]!=args.samples[:len(saved['samples'])]:
            raise ValueError('evaluation sample order changed')
        existing={row['sample']:row for row in saved['samples']}
        report=saved
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for sid in args.samples:
        baseline=args.baseline_root/args.baseline_template.format(sample=sid)
        candidate=args.candidate_root/args.candidate_template.format(sample=sid)
        gt=args.ground_truth_root/args.ground_truth_template.format(sample=sid)
        hashes={k:hashlib.sha256(p.read_bytes()).hexdigest()
                for k,p in [('baseline',baseline),('candidate',candidate),('ground_truth',gt)]}
        if sid in existing:
            if existing[sid]['sha256']!=hashes:
                raise ValueError(f'evaluation inputs changed: {sid}')
            rows.append(existing[sid])
            continue
        identical=hashes['baseline']==hashes['candidate']
        measurements={'baseline':[],'candidate':[]}
        baseline_runs=evaluate_cd_emd_repeated(baseline,gt,count=args.count,seed=args.seed,repeats=args.repeats)
        candidate_runs=(baseline_runs if identical else evaluate_cd_emd_repeated(
            candidate,gt,count=args.count,seed=args.seed,repeats=args.repeats))
        for a,b in zip(baseline_runs,candidate_runs):
            for key,value in [('baseline',a),('candidate',b)]:
                measurements[key].append([float(x)*100 for x in value])
        row={'sample':sid,'sha256':hashes,'identical':identical,'runs':measurements}
        for key in measurements:
            values=np.asarray(measurements[key])
            row[key]={'cd_l1_x100':float(values[:,0].mean()),'emd_x100':float(values[:,1].mean()),
                      'emd_std':float(values[:,1].std())}
        rows.append(row)
        report={'offline_only':True,'ground_truth_used_in_inference':False,
                'count':args.count,'seed':args.seed,'repeats':args.repeats,
                'input_roots':{key:str(getattr(args,key).resolve()) for key in
                               ('baseline_root','candidate_root','ground_truth_root')},
                'templates':{key:getattr(args,key) for key in
                             ('baseline_template','candidate_template','ground_truth_template')},
                'metric_code_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                                      for name in ('src/offline_metrics.py','utils/loss_util.py')},
                'samples':rows,'complete':len(rows)==len(args.samples)}
        report['means']={key:{metric:float(np.mean([r[key][metric] for r in rows]))
                             for metric in ('cd_l1_x100','emd_x100')}
                         for key in ('baseline','candidate')}
        report['mean_delta']={metric:report['means']['candidate'][metric]-report['means']['baseline'][metric]
                              for metric in ('cd_l1_x100','emd_x100')}
        temporary=args.output.with_suffix('.tmp')
        temporary.write_text(json.dumps(report,indent=2)+'\n')
        temporary.replace(args.output)
        print(json.dumps({'sample':sid,'baseline':row['baseline'],'candidate':row['candidate']}),flush=True)
    print(json.dumps(report['means']),flush=True)


if __name__=='__main__':
    main()
