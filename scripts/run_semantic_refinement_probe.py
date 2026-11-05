#!/usr/bin/env python3
"""Isolated MLLM-controlled alignment / semantic-handle deformation experiment."""
import argparse,json,hashlib,sys,shutil
from pathlib import Path
from dataclasses import asdict
import numpy as np
from scipy.spatial import cKDTree
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.semantic_handle_refinement import INSTRUCTIONS,schema,render_handle_views,coherent_semantic_candidate
from src.gpt_refine_agent import GPTRefineAgent,render_diagnostic_board,REVIEW_SCHEMA
from src.pointcloud_io import load_points,write_points
from src.multiview_partial_evidence import load_manifest_projectors
from src.saved_camera import SavedCameraProjector
from src.balanced_registration import refine_balanced_sim3
from src.posterior_agent import observe
from src.local_refinement_stage import connectivity_audit


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--case-dir',type=Path,required=True);ap.add_argument('--output-dir',type=Path,required=True);ap.add_argument('--feedback',default='');ap.add_argument('--gpt-model',default='gpt-6-astra');ap.add_argument('--rounds',type=int,default=3)
    ap.add_argument('--initial-plan',type=Path)
    a=ap.parse_args();out=a.output_dir
    if out.exists():raise ValueError('use a fresh experiment directory')
    out.mkdir(parents=True);p=a.case_dir;sid=p.name
    shutil.copytree(p/'inputs',out/'inputs')
    shutil.copytree(p/'prior_generation',out/'prior_generation')
    prior_path=p/'registration/final/camera1_amplified_registered_100k.ply';shutil.copy2(prior_path,out/'initial_registered_100k.ply')
    shutil.copy2(p/'diagnostics/render/render_manifest.json',out/'render_manifest.json')
    partial=load_points(out/'inputs/partial'/f'{sid}.ply');initial=load_points(prior_path);current=initial.copy()
    views=load_manifest_projectors(out/'render_manifest.json');camera=SavedCameraProjector.from_partial(partial,out/'inputs/camera'/sid/'camera.pth',padding=.15,image_shape=(512,512),device='cpu')
    agent=GPTRefineAgent(a.gpt_model,provider='codex');history=[]
    report={'model':a.gpt_model,'reasoning_effort':'medium','ground_truth_used':False,'feedback':a.feedback,'initial_path':str(prior_path.resolve()),'initial_sha256':hashlib.sha256(prior_path.read_bytes()).hexdigest(),'trace':history,'status':'running','instructions':INSTRUCTIONS}
    def save():
        write_points(out/'selected_100k.ply',current);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    for i in range(a.rounds):
        rd=out/f'round_{i+1:02d}';rd.mkdir()
        images=render_handle_views(partial,current,views,rd/'views')
        observation,_=observe(partial,current,views)
        payload={'round':i+1,'remaining_rounds':a.rounds-i,'observation':asdict(observation),'user_feedback':a.feedback,'history':[{'action':t.get('plan',{}).get('decision',{}).get('action'),'part':t.get('plan',{}).get('decision',{}).get('part'),'accepted':t.get('accepted'), 'review':t.get('review'),'error':t.get('error')} for t in history]}
        (rd/'plan_prompt.json').write_text(json.dumps({'instructions':INSTRUCTIONS,'payload':payload},indent=2))
        if i==0 and a.initial_plan:
            original_report=json.loads((a.initial_plan.parent.parent/'report.json').read_text())
            if original_report['initial_sha256']!=report['initial_sha256'] or original_report['model']!=a.gpt_model:
                raise ValueError('cached plan must have identical initial geometry and model')
            plan=json.loads(a.initial_plan.read_text())
            plan['reused_from']=str(a.initial_plan.resolve())
        else:
            plan=agent._request(schema=schema(),name='semantic_refinement_plan',payload=payload,images=images,instructions=INSTRUCTIONS)
        plan['semantic_prompt_version']='semantic_surface_handles_v1'
        (rd/'plan.json').write_text(json.dumps(plan,indent=2));decision=plan['decision'];record={'round':i+1,'plan':plan,'accepted':False};history.append(record);save()
        print('PLAN',i+1,decision['action'],decision['part'],flush=True)
        if decision['action']=='KEEP_CURRENT':break
        if decision['action']=='REFINE_ALIGNMENT':
            candidate,geometry=refine_balanced_sim3(current,partial,camera)
            variants=[(candidate,geometry)] if geometry['accepted'] else []
            if not variants:record['error']='no safe global improvement';save();continue
        else:
            variants=[]
            try:
                for fraction in [1.,.5,.25]:
                    try:
                        candidate,geometry,mask=coherent_semantic_candidate(current,partial,views,decision,fraction)
                    except ValueError as exc:
                        record.setdefault('geometric_rejections',[]).append({'fraction':fraction,'reason':str(exc)})
                        continue
                    strain=geometry['strain'];before=cKDTree(current).query(partial)[0];after=cKDTree(candidate).query(partial)[0]
                    geometry['observation_mean_before']=float(before.mean());geometry['observation_mean_after']=float(after.mean())
                    geometry['connectivity']=connectivity_audit(current,candidate)
                    passed=(after.mean()<=before.mean()*1.02 and geometry['connectivity']['passed'])
                    geometry['strain_policy']='diagnostic_only_no_absolute_stretch_threshold'
                    geometry['hard_passed']=bool(passed);write_points(rd/f'deformation_{fraction}.ply',candidate);(rd/f'deformation_{fraction}.json').write_text(json.dumps(geometry,indent=2))
                    if passed:variants.append((candidate,geometry))
            except ValueError as exc:
                record['error']=str(exc);save();print('REJECT',exc,flush=True);continue
        for vi,(candidate,geometry) in enumerate(variants):
            depth=np.concatenate([partial,current,candidate]);before_board=render_diagnostic_board(partial,current,views,rd/'before.png',depth_reference_points=depth);after_board=render_diagnostic_board(partial,candidate,views,rd/f'after_{vi}.png',depth_reference_points=depth)
            after,_=observe(partial,candidate,views)
            review=agent._request(schema=REVIEW_SCHEMA,name='semantic_deformation_review',payload={'proposal_action':decision['action'],'semantic_plan':decision,'geometry':geometry,'before':asdict(observation),'after':asdict(after)},images=[before_board,after_board],instructions='Review a proposed geometric update. Image 1 is BEFORE and image 2 AFTER, identical cameras and depth scales. Each view has blue OBSERVED PARTIAL, red COMPLETE PRIOR, then overlay. Require semantic part correspondence and genuine local alignment improvement while keeping the full object natural, attachments intact, and other parts stable. Missing scan geometry is unknown. Critically inspect the named part, not only aggregate metrics. Reject stretching, collapse, detached or wrongly associated parts. ACCEPT_UPDATE only with clear evidence. Otherwise TRY_NEXT_CANDIDATE or STOP_KEEP_CURRENT. Never use GT. Explain evidence and uncertainty.')
            record.setdefault('candidates',[]).append({'geometry':geometry,'review':review});record['review']=review['decision'];save()
            print('REVIEW',i+1,review['decision']['action'],flush=True)
            if review['decision']['action']=='ACCEPT_UPDATE':
                current=candidate;record['accepted']=True;write_points(rd/'accepted_100k.ply',current);save();break
            if review['decision']['action']=='STOP_KEEP_CURRENT':break
        if not variants:record['error']='all proposals failed geometry guards';save()
    report['status']='completed';save()
    depth=np.concatenate([partial,initial,current]);render_diagnostic_board(partial,initial,views,out/'before.png',depth_reference_points=depth);render_diagnostic_board(partial,current,views,out/'after.png',depth_reference_points=depth)
    print('DONE',out,flush=True)

if __name__=='__main__':main()
