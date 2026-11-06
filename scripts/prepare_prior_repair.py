#!/usr/bin/env python3
"""Prepare a fresh Image Gen task from an Astra prior audit without changing archives."""
import argparse
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_prior_generation_agent import _camera_files, enrich
from scripts.run_updated_dataset_suite import write_json, sha
from src.prior_generation_agent import compose_depth_edit_prompt


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--audit',type=Path,required=True)
    ap.add_argument('--output-root',type=Path,required=True)
    a=ap.parse_args();audit=json.loads(a.audit.read_text());decision=audit['decision']
    if decision['action'] not in {'REGENERATE','RESELECT_VIEW'}:
        raise ValueError('repair needs a concrete regeneration or reselection decision')
    source=Path(audit['source']);old=json.loads((source/'prior_agent/prior_agent_manifest.json').read_text())
    out=a.output_root.resolve();sid=old['sample'];agent=out/'prior_agent'
    if (agent/'prior_agent_manifest.json').exists():
        state=json.loads((agent/'prior_agent_manifest.json').read_text())
        if (out/'repair_provenance.json').exists() and json.loads((out/'repair_provenance.json').read_text())['audit_sha256']!=sha(a.audit):
            raise ValueError('repair audit changed; preserve this attempt')
        if state.get('depth_interpretation'):
            print(state['current_prompt_file']);return
    else:
        agent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(source/'prior_agent/candidates',agent/'candidates')
        boards=old['view_board'];boards=[boards] if isinstance(boards,str) else boards
        copied=[]
        for path in boards:
            src=Path(path);dest=agent/src.name;shutil.copy2(src,dest);copied.append(str(dest))
        partial=out/'inputs/partial'/f'{sid}.ply';partial.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source/'inputs/partial'/f'{sid}.ply',partial)
        selected=decision['selected_view'];camera=out/'inputs/camera'/sid
        _camera_files(agent/'candidates'/selected,camera)
        prompt_path=agent/'round_00_prompt.txt';prompt=compose_depth_edit_prompt(object_description=old['object_description'])
        prompt_path.write_text(prompt+'\n')
        state={'schema':'compagent.prior_agent.v1','sample':sid,'ground_truth_used':False,
               'object_description':old['object_description'],'input_partial':str(partial),
               'input_partial_sha256':sha(partial),'view_candidates':{v:str(agent/'candidates'/v/'depth.png') for v in old['view_candidates']},
               'camera_source':None,'selected_view':selected,'selected_depth':str(camera/'depth.png'),
               'camera_dir':str(camera),'view_board':copied,'base_prompt':old['base_prompt'],
               'selection':{'decision':{'view_id':selected,'reason':decision['view_quality_evidence']},
                            'model':'gpt-6-astra','reasoning_effort':json.loads(a.audit.read_text())['reasoning_effort'],'provider':'saved_prior_audit'},
               'current_prompt_file':str(prompt_path),'reviews':[],'accepted':None}
        write_json(agent/'prior_agent_manifest.json',state)
        shutil.copy2(a.audit,out/'source_audit.json')
        write_json(out/'repair_provenance.json',{'source':str(source),'audit':str(a.audit.resolve()),
                    'audit_sha256':sha(a.audit),'old_view':old['selected_view'],'new_view':selected,
                    'ground_truth_used':False,'image_generator':'Codex built-in Image Gen',
                    'old_assets_preserved':True})
    # Re-read the selected depth independently; a new view must not inherit
    # the old view's directional correction or rejected RGB as its reference.
    enrich(SimpleNamespace(output_root=out,feedback='',model='gpt-6-astra',include_depth_framing=True))


if __name__=='__main__':main()
