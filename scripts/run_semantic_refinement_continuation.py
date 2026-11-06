#!/usr/bin/env python3
"""Isolated MLLM-controlled alignment / semantic-handle deformation experiment."""
import argparse,json,hashlib,sys,shutil
from pathlib import Path
from dataclasses import asdict,replace
import numpy as np
from scipy.spatial import cKDTree
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.semantic_handle_refinement import render_handle_views,coherent_semantic_candidate,smooth_semantic_candidate,render_semantic_zooms,validate_semantic_plan,protect_displacement
from src.gpt_refine_agent import GPTRefineAgent,render_diagnostic_board,REVIEW_SCHEMA
from src.pointcloud_io import load_points,write_points,jsonable
from src.multiview_partial_evidence import load_manifest_projectors
from src.saved_camera import SavedCameraProjector
from src.balanced_registration import refine_balanced_sim3
from src.posterior_agent import observe
from src.local_refinement_stage import connectivity_audit
from src.deformation_graph import local_surface_graph,edge_strain
from src.refinement_evidence import candidate_audit,carrier_digest,residual_regions,render_residual_comparison,observed_support_audit,semantic_part_evidence,discover_residual_windows,rejection_evidence
from src.semantic_refinement_policy import planning_contract,COMPLETION_SCHEMA,COMPLETION_INSTRUCTIONS

POLICY_VERSION='autonomous_inventory_v10'


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--case-dir',type=Path,required=True);ap.add_argument('--output-dir',type=Path,required=True);ap.add_argument('--feedback',default='');ap.add_argument('--gpt-model',default='gpt-6-astra');ap.add_argument('--rounds',type=int,default=3)
    ap.add_argument('--initial-plan',type=Path)
    ap.add_argument('--start-carrier',type=Path)
    ap.add_argument('--previous-plan',type=Path)
    ap.add_argument('--autonomous',action='store_true')
    ap.add_argument('--resume',action='store_true')
    ap.add_argument('--allow-observation-field',action='store_true')
    ap.add_argument('--allow-posterior',action='store_true')
    ap.add_argument('--posterior-config',type=Path,default=ROOT/'configs/posterior_mainline.json')
    ap.add_argument('--device',default='cuda')
    ap.add_argument('--views',type=int,choices=[4,6],default=6)
    ap.add_argument('--protected-indices',type=Path)
    ap.add_argument('--feedback-images',type=Path,nargs='*',default=[])
    a=ap.parse_args()
    if a.autonomous and any((a.feedback,a.feedback_images,a.previous_plan,a.initial_plan,a.start_carrier,a.protected_indices)):
        ap.error('autonomous runs start from fixed registration and cannot consume feedback, annotations, cached plans or protected slots')
    if a.autonomous:
        a.allow_observation_field=True;a.allow_posterior=True
    out=a.output_dir
    if out.exists() and not a.resume:raise ValueError('use a fresh experiment directory')
    out.mkdir(parents=True,exist_ok=True);p=a.case_dir;sid=p.name
    method=out/'method'/POLICY_VERSION;method.mkdir(parents=True,exist_ok=True)
    for source in [Path(__file__), *(ROOT/'src'/name for name in ['semantic_refinement_policy.py','refinement_evidence.py','semantic_handle_refinement.py','diagnostic_view_policy.py','gpt_refine_agent.py','deformation_graph.py','observation_anchored_fusion.py','balanced_registration.py'])]:
        shutil.copy2(source,method/source.name)
    (method/'arguments.json').write_text(json.dumps(jsonable(vars(a)),indent=2))
    feedback_images=[]
    for i,path in enumerate(a.feedback_images):
        dest=out/'feedback'/f'annotation_{i+1}{path.suffix}';dest.parent.mkdir(exist_ok=True)
        shutil.copy2(path,dest);feedback_images.append(dest)
    if a.allow_posterior:
        shutil.copy2(a.posterior_config,method/'posterior_config.json')
        for name in ['posterior_adapter.py','posterior_types.py','posterior_deformation.py','partial_transport.py','carrier_protection.py']:
            shutil.copy2(ROOT/'src'/name,method/name)
    shutil.copytree(p/'inputs',out/'inputs',dirs_exist_ok=True)
    shutil.copytree(p/'prior_generation',out/'prior_generation',dirs_exist_ok=True)
    prior_path=a.start_carrier or p/'registration/final/camera1_amplified_registered_100k.ply';shutil.copy2(prior_path,out/'initial_registered_100k.ply')
    shutil.copy2(p/'diagnostics/render/render_manifest.json',out/'render_manifest.json')
    partial=load_points(out/'inputs/partial'/f'{sid}.ply');initial=load_points(prior_path);current=initial.copy()
    if a.views==6:
        from src.diagnostic_view_policy import fixed_six_view_manifest
        manifest=fixed_six_view_manifest(json.loads((out/'render_manifest.json').read_text()))
        (out/'render_manifest.json').write_text(json.dumps(manifest,indent=2))
    protected=np.load(a.protected_indices) if a.protected_indices else np.array([],dtype=int)
    rest_graph,_,_=local_surface_graph(initial,neighbours=12,edge_ratio=1.85)
    if a.protected_indices:shutil.copy2(a.protected_indices,out/'protected_indices.npy')
    views=load_manifest_projectors(out/'render_manifest.json');camera=SavedCameraProjector.from_partial(partial,out/'inputs/camera'/sid/'camera.pth',padding=.15,image_shape=(512,512),device='cpu')
    agent=GPTRefineAgent(a.gpt_model,provider='codex');history=[]
    last_region=json.loads(a.previous_plan.read_text())['decision'] if a.previous_plan else {}
    instructions,plan_schema=planning_contract(observation_field=a.allow_observation_field,posterior=a.allow_posterior,autonomous=a.autonomous)
    stalled=0
    report={'model':a.gpt_model,'reasoning_effort':'low','ground_truth_used':False,'feedback':a.feedback,'initial_path':str(prior_path.resolve()),'initial_sha256':hashlib.sha256(prior_path.read_bytes()).hexdigest(),'trace':history,'status':'running','instructions':instructions,'view_count':a.views,'protected_indices':str(a.protected_indices) if a.protected_indices else None,'evidence_policy':POLICY_VERSION,'autonomous':a.autonomous}
    if a.resume and (out/'report.json').exists():
        report=json.loads((out/'report.json').read_text());history=report['trace'];current=load_points(out/'selected_100k.ply')
        if a.autonomous and not report.get('autonomous',False):raise ValueError('cannot label an assisted history autonomous')
        if report['initial_sha256']!=hashlib.sha256(prior_path.read_bytes()).hexdigest():
            raise ValueError('resume must preserve the original loop rest carrier')
        report['status']='running';report.pop('stop_reason',None)
        report.setdefault('reasoning_revisions', []).append({
            'from_round': len(history)+1, 'model': a.gpt_model,
            'reasoning_effort': 'low', 'previous_report_effort': report['reasoning_effort']})
        report['current_reasoning_effort']='low'
        report.setdefault('policy_revisions',[]).append({'from_round':len(history)+1,'change':'fixed-rest audit, repeat detection, and available-action update','available_actions':plan_schema['properties']['action']['enum'],'instructions':instructions,'feedback':a.feedback})
        for t in reversed(history):
            if t.get('plan',{}).get('decision',{}).get('windows'):
                last_region=t['plan']['decision'];break
        # Recover omitted numerical fields from this run's own saved solver
        # records. Accepted decisions and coordinates remain unchanged.
        for t in history:
            rejected=t.get('geometric_rejections',[])
            if not rejected:continue
            saved={}
            for path in (out/f"round_{t['round']:02d}").glob('*.json'):
                value=json.loads(path.read_text())
                if isinstance(value,dict) and 'operator' in value and 'fraction' in value:
                    saved[(value['operator'],value['fraction'])]=(path,value)
            for entry in rejected:
                found=saved.get((entry.get('operator'),entry.get('fraction')))
                if found:
                    path,value=found
                    entry.update(rejection_evidence(value));entry['evidence_source']=str(path)
    failed_images=[]
    reviewed={c['candidate_digest']:c['review']['decision'] for t in history for c in t.get('candidates',[]) if 'candidate_digest' in c}
    exhausted_observation_states={t['input_carrier_digest'] for t in history if t.get('exhausted_observation_field') and t.get('policy_version')==POLICY_VERSION}
    exhausted_posterior_states={t['input_carrier_digest'] for t in history if t.get('exhausted_posterior') and t.get('policy_version')==POLICY_VERSION}
    report['current_evidence_policy']=POLICY_VERSION
    def qualify(candidate,geometry):
        audit=candidate_audit(initial,current,candidate,rest_graph,protected)
        geometry['integrity_audit']=audit
        geometry['current_regional_support']=observed_support_audit(current,candidate,partial,camera)
        geometry['initial_regional_support']=observed_support_audit(initial,candidate,partial,camera)
        geometry['hard_passed']=bool(geometry.get('hard_passed',True) and audit['passed']
                                     and geometry['current_regional_support']['passed']
                                     and geometry['initial_regional_support']['passed'])
        return geometry['hard_passed']
    report['rejection_evidence_revision']='numerical_rejection_v1'
    report.setdefault('rejection_evidence_revisions',[]).append({
        'from_round':len(history)+1,'revision':'numerical_rejection_v1',
        'change':'Expose existing numerical gate criteria and failed checks; geometry rules unchanged.'})
    def save():
        write_points(out/'selected_100k.ply',current);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    for i in range(len(history),a.rounds):
        rd=out/f'round_{i+1:02d}';rd.mkdir(exist_ok=True)
        images=render_handle_views(partial,current,views,rd/'views')
        zooms=render_semantic_zooms(images,last_region,rd/'zooms')
        discovery=discover_residual_windows(partial,current,views) if a.autonomous else None
        if discovery:
            (rd/'residual_discovery.json').write_text(json.dumps(discovery,indent=2))
            zooms+=render_semantic_zooms(images,discovery,rd/'discovery_zooms')
        observation,_=observe(partial,current,views)
        input_digest=carrier_digest(current)
        round_schema=json.loads(json.dumps(plan_schema))
        if input_digest in exhausted_observation_states:
            round_schema['properties']['action']['enum']=[x for x in round_schema['properties']['action']['enum'] if x!='REFINE_OBSERVED']
        if input_digest in exhausted_posterior_states:
            round_schema['properties']['action']['enum']=[x for x in round_schema['properties']['action']['enum'] if x!='UPDATE_POSTERIOR']
        payload={'available_actions':round_schema['properties']['action']['enum'],'view_count':len(views),'protected_surface_slots':len(protected),'round':i+1,'remaining_rounds':a.rounds-i,'observation':asdict(observation),'user_feedback':a.feedback,'residual_discovery':discovery,'history':[{'action':t.get('plan',{}).get('decision',{}).get('action'),'part':t.get('plan',{}).get('decision',{}).get('part'),'mismatch_inventory':t.get('plan',{}).get('decision',{}).get('mismatch_inventory'),'accepted':t.get('accepted'), 'review':t.get('review'),'error':t.get('error'),'geometric_rejections':t.get('geometric_rejections'),'correspondence_validation':t.get('correspondence_validation'),'repeated_candidates':t.get('repeated_candidates')} for t in history]}
        payload['numerical_gate_policy']={
            'distributed_fields':'Require more than 1% reduction in observed mean nearest distance, solver integrity, connectivity, and regional/carrier audits.',
            'semantic_deformation':'Allow at most 2% observed mean-distance regression, require positive Jacobian, connectivity, and regional/carrier audits.',
            'interpretation':'These are numerical candidate gates, not semantic correspondence evidence; inspect the reported failed checks and measurements.'}
        (rd/'plan_prompt.json').write_text(json.dumps({'instructions':instructions,'payload':payload},indent=2))
        if i==0 and a.initial_plan:
            original_report=json.loads((a.initial_plan.parent.parent/'report.json').read_text())
            if original_report['initial_sha256']!=report['initial_sha256'] or original_report['model']!=a.gpt_model:
                raise ValueError('cached plan must have identical initial geometry and model')
            plan=json.loads(a.initial_plan.read_text())
            plan['reused_from']=str(a.initial_plan.resolve())
        else:
            plan=agent._request(schema=round_schema,name='semantic_refinement_plan',payload=payload,images=images+zooms+feedback_images+failed_images,instructions=instructions)
        plan['semantic_prompt_version']='paired_semantic_surface_handles_v2'
        (rd/'plan.json').write_text(json.dumps(plan,indent=2));decision=plan['decision'];record={'round':i+1,'plan':plan,'accepted':False,'input_carrier_digest':input_digest,'policy_version':POLICY_VERSION};history.append(record);save()
        print('PLAN',i+1,decision['action'],decision['part'],flush=True)
        if decision['action']=='KEEP_CURRENT':
            if a.autonomous and not any(x['status']=='actionable' for x in decision['mismatch_inventory']):
                stop_payload={'plan':decision,'observation':asdict(observation),'history':payload['history'],'residual_discovery':discovery}
                (rd/'completion_prompt.json').write_text(json.dumps({'instructions':COMPLETION_INSTRUCTIONS,'payload':stop_payload},indent=2))
                stop_review=agent._request(schema=COMPLETION_SCHEMA,name='semantic_completion_audit',payload=stop_payload,images=images+zooms,instructions=COMPLETION_INSTRUCTIONS)
                (rd/'completion_review.json').write_text(json.dumps(stop_review,indent=2));record['completion_review']=stop_review
                if stop_review['decision']['action']=='STOP':
                    report['status']='agent_stopped_no_actionable_issue'
                    report['stop_reason']=stop_review['decision']['reason'];report['remaining_inventory']=decision['mismatch_inventory'];save();break
                record['error']='Completion audit requests reassessment: '+json.dumps(stop_review['decision']);save();continue
            stalled+=1;record['error']='Unresolved mismatch: refresh semantic evidence or try another part/tool before stopping.';save()
            if stalled>=3:
                report['stop_reason']='three evidence-refresh attempts exhausted; unresolved';break
            continue
        stalled=0
        if decision['windows']:last_region=decision
        if decision['action']=='DEFORM_REGION':
            validation,marked=validate_semantic_plan(current,partial,views,decision,images,rd/'correspondence_check',require_target_windows=True)
            record['correspondence_validation']=validation
            (rd/'correspondence_check/validation.json').write_text(json.dumps(validation,indent=2))
            if not validation['valid']:
                failed_images=marked;record['error']='Cross-view semantic correspondence inconsistent; see exact reprojections and green windows in diagnostic images.';save();continue
        failed_images=[]
        if decision['action'] in ('REFINE_OBSERVED','UPDATE_POSTERIOR'):
            if decision['action']=='REFINE_OBSERVED':
                from src.observation_anchored_fusion import fuse_continuous_observation_field,ContinuousObservationFusionConfig
                full,_,_,field_info=fuse_continuous_observation_field(current,partial,views,config=ContinuousObservationFusionConfig(num_views=len(views),enforce_edge_strain_limits=False))
                operator_name='baseline_fine_observation_field';artifact_stem='observation_field'
                solver_passed=True
            else:
                from src.posterior_adapter import PosteriorAdapter,PosteriorAdapterConfig
                config=replace(PosteriorAdapterConfig(**json.loads(a.posterior_config.read_text())),enforce_edge_strain_limits=False)
                full,estimate,_=PosteriorAdapter(config,device=a.device).run(current,partial,camera,view_projectors=views,transport_projectors=(camera,))
                field_info=jsonable(estimate);operator_name='baseline_partial_ot_posterior';artifact_stem='posterior'
                solver_passed=bool(estimate.get('integrity',{}).get('passed',False))
            graph,metric,_=local_surface_graph(current,neighbours=12,edge_ratio=1.85)
            full=protect_displacement(current,full,metric,protected,.06*np.linalg.norm(np.ptp(current,axis=0)))
            before=cKDTree(current).query(partial)[0];variants=[]
            for fraction in (1.,.5,.25):
                candidate=current+fraction*(full-current)
                candidate[protected]=initial[protected]
                after=cKDTree(candidate).query(partial)[0];strain=edge_strain(current,candidate,graph)
                geometry={'operator':operator_name,'fraction':fraction,'field':field_info,'strain':strain,'mean_before':float(before.mean()),'mean_after':float(after.mean()),'connectivity':connectivity_audit(current,candidate)}
                geometry['solver_integrity_passed']=solver_passed
                geometry['criteria']={'required_relative_mean_improvement':.01}
                geometry['gate_checks']={'solver_integrity':bool(solver_passed),
                    'observed_mean_improvement':bool(after.mean()<before.mean()*.99),
                    'connectivity':bool(geometry['connectivity']['passed'])}
                geometry['hard_passed']=all(geometry['gate_checks'].values())
                passed=qualify(candidate,geometry)
                write_points(rd/f'{artifact_stem}_{fraction}.ply',candidate);(rd/f'{artifact_stem}_{fraction}.json').write_text(json.dumps(geometry,indent=2))
                if passed:variants.append((candidate,geometry))
                else:record.setdefault('geometric_rejections',[]).append(rejection_evidence(geometry))
        elif decision['action']=='REFINE_ALIGNMENT':
            candidate,geometry=refine_balanced_sim3(current,partial,camera)
            geometry['gate_checks']={'balanced_alignment_accepted':bool(geometry['accepted'])}
            geometry['hard_passed']=geometry['accepted']
            variants=[(candidate,geometry)] if qualify(candidate,geometry) else []
            if not variants:
                record.setdefault('geometric_rejections',[]).append(rejection_evidence(geometry))
                record['error']='no safe global improvement';save();continue
        else:
            variants=[];fallbacks=[]
            for operator_name,operator in [('smooth',smooth_semantic_candidate),('rigid',coherent_semantic_candidate)]:
                eligible=[]
                for fraction in [1.,.5,.25]:
                    try:
                        candidate,geometry,mask=operator(current,partial,views,decision,fraction,protected_ids=protected)
                    except ValueError as exc:
                        record.setdefault('geometric_rejections',[]).append({'operator':operator_name,'fraction':fraction,'reason':str(exc)})
                        continue
                    strain=geometry['strain'];before=cKDTree(current).query(partial)[0];after=cKDTree(candidate).query(partial)[0]
                    geometry['observation_mean_before']=float(before.mean());geometry['observation_mean_after']=float(after.mean())
                    geometry['connectivity']=connectivity_audit(current,candidate)
                    geometry['criteria']={'maximum_relative_mean_regression':.02,'jacobian_must_be_positive':True}
                    geometry['gate_checks']={'observed_mean_regression':bool(after.mean()<=before.mean()*1.02),
                        'connectivity':bool(geometry['connectivity']['passed']),
                        'positive_jacobian':bool(geometry.get('minimum_full_rank_jacobian_determinant',1)>0)}
                    passed=all(geometry['gate_checks'].values())
                    geometry['hard_passed']=bool(passed);passed=qualify(candidate,geometry)
                    write_points(rd/f'{operator_name}_{fraction}.ply',candidate);(rd/f'{operator_name}_{fraction}.json').write_text(json.dumps(geometry,indent=2))
                    if passed:eligible.append((candidate,geometry))
                    else:record.setdefault('geometric_rejections',[]).append(rejection_evidence(geometry))
                if eligible:
                    eligible.sort(key=lambda pair:np.mean(pair[1]['handle_error_after']))
                    variants.append(eligible[0]);fallbacks.extend(eligible[1:])
            variants.extend(fallbacks)
        for vi,(candidate,geometry) in enumerate(variants):
            digest=carrier_digest(candidate)
            if digest in reviewed or digest==input_digest:
                record.setdefault('repeated_candidates',[]).append({'candidate_digest':digest,'prior_review':reviewed.get(digest),'reason':'identical ordered candidate already reviewed or unchanged'})
                continue
            depth=np.concatenate([partial,current,candidate]);before_board=render_diagnostic_board(partial,current,views,rd/'before.png',depth_reference_points=depth);after_board=render_diagnostic_board(partial,candidate,views,rd/f'after_{vi}.png',depth_reference_points=depth)
            after,_=observe(partial,candidate,views)
            evidence=residual_regions(partial,current,candidate,views)
            (rd/f'local_evidence_{vi}.json').write_text(json.dumps(evidence,indent=2))
            local_image=render_residual_comparison(partial,current,candidate,views,evidence['review_regions'],rd/f'local_comparison_{vi}.png')
            part_evidence=semantic_part_evidence(partial,current,candidate,views,decision)
            part_image=None
            if part_evidence is not None:
                (rd/f'semantic_part_evidence_{vi}.json').write_text(json.dumps(part_evidence,indent=2))
                part_image=render_residual_comparison(partial,current,candidate,views,part_evidence['review_regions'],rd/f'semantic_part_comparison_{vi}.png')
            review_payload={'proposal_action':decision['action'],'semantic_plan':decision,'geometry':geometry,'before':asdict(observation),'after':asdict(after),'local_evidence':{k:v for k,v in evidence.items() if k!='regions'}}
            review_payload['semantic_part_evidence']=part_evidence
            review_instructions='Review a proposed geometric update. Image 1 is BEFORE and image 2 AFTER, identical cameras and depth scales. Each view has blue OBSERVED PARTIAL, red COMPLETE PRIOR, then overlay. Image 3, if present, contains identical local crops: observed / before overlay / after overlay, including the most improved and the most regressed (or least improved) observed regions. Purple is screen overlap only; use 3D residuals for depth agreement. Require semantic correspondence and local alignment improvement while keeping the full object natural and attachments intact. Missing scan geometry is unknown. The integrity_audit directly measures protected slot coordinates against the frozen loop start: exactly_preserved=true and zero maximum_displacement verify those slots. Do not infer that other slots are protected. Cumulative strain uses a fixed rest graph. For small distributed corrections, measured local 3D gains with stable visible structure can support acceptance even when the full-object board change is subtle. Nearest-distance gains alone do not prove a semantic correspondence; reject identifiable wrong associations, stretching, collapse, or detachment. ACCEPT_UPDATE with supported improvement and no demonstrated structural regression; otherwise TRY_NEXT_CANDIDATE or STOP_KEEP_CURRENT with concrete evidence. Never use GT.'
            review_instructions+=' Stretch percentiles are descriptive only; do not use 1.5 expansion, 0.6 compression, or another invented universal ratio as an acceptance boundary. Substantial proportional correction can be appropriate for a generated prior. Distinguish supported shape correction from visible unnatural distortion, folding, wrong correspondence or collapse. Cite concrete local evidence when rejecting shape changes.'
            review_instructions+=' When present, the final image shows the proposed SAME part in both selected views, with identical observed/before/after crops. semantic_part_evidence measures observed-to-part distance using only the corresponding prior slots, fixed before/after, excluding unrelated neighbouring surfaces. Treat the windows as a semantic hypothesis to verify visually, not proven segmentation. A global or neighbour-assisted nearest-distance gain cannot replace improvement of the named part. Inspect attachment transitions and any other affected region as well.'
            review_images=[x for x in [before_board,after_board,local_image,part_image] if x]
            (rd/f'review_prompt_{vi}.json').write_text(json.dumps({'instructions':review_instructions,'payload':review_payload,'images':[str(x) for x in review_images]},indent=2))
            review=agent._request(schema=REVIEW_SCHEMA,name='semantic_deformation_review',payload=review_payload,images=review_images,instructions=review_instructions)
            reviewed[digest]=review['decision']
            record.setdefault('candidates',[]).append({'candidate_digest':digest,'geometry':geometry,'review':review});record['review']=review['decision'];save()
            print('REVIEW',i+1,review['decision']['action'],flush=True)
            if review['decision']['action']=='ACCEPT_UPDATE':
                current=candidate;record['accepted']=True;write_points(rd/'accepted_100k.ply',current);save();break
            if review['decision']['action']=='STOP_KEEP_CURRENT':
                record.setdefault('failed_operators',[]).append(geometry.get('operator','alignment'))
        if decision['action']=='REFINE_OBSERVED' and not record['accepted']:
            exhausted_observation_states.add(input_digest);record['exhausted_observation_field']=True
            record['error']='All fixed observation-field fractions exhausted at unchanged geometry; inspect rejection evidence and choose another route.'
            save()
        if decision['action']=='UPDATE_POSTERIOR' and not record['accepted']:
            exhausted_posterior_states.add(input_digest);record['exhausted_posterior']=True
            record['error']='All fixed baseline posterior fractions exhausted at unchanged geometry; inspect rejection evidence and choose another route.'
            save()
        if not variants:record['error']='all proposals failed geometry guards';save()
    if report['status']=='running':report['status']='pilot_stopped_with_trace'
    report.setdefault('stop_reason','round_budget_exhausted; assess remaining residuals');save()
    depth=np.concatenate([partial,initial,current]);render_diagnostic_board(partial,initial,views,out/'before.png',depth_reference_points=depth);render_diagnostic_board(partial,current,views,out/'after.png',depth_reference_points=depth)
    points=np.concatenate([current,partial]);colors=np.concatenate([np.tile(np.array([230,80,80])/255,(len(current),1)),np.tile(np.array([45,105,230])/255,(len(partial),1))])
    write_points(out/'visualization/refined_red_partial_blue.ply',points,colors)
    (out/'artifacts.json').write_text(json.dumps({'refinement':'selected_100k.ply','colored_overlay':'visualization/refined_red_partial_blue.ply','before':'before.png','after':'after.png','report':'report.json','inputs':'inputs','method':'method','autonomous':a.autonomous,'status':report['status']},indent=2))
    print('DONE',out,flush=True)

if __name__=='__main__':main()
