#!/usr/bin/env python3
"""Archive a built-in Image Gen result and its exact submitted prior prompt."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
from PIL import Image

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_updated_dataset_suite import sha,write_json


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output-root',type=Path,required=True)
    ap.add_argument('--generated',type=Path,required=True)
    ap.add_argument('--prompt-file',type=Path,required=True,
                    help='Exact prompt file submitted to the built-in tool, not a later revision.')
    a=ap.parse_args();root=a.output_root.resolve()
    state=json.loads((root/'prior_agent/prior_agent_manifest.json').read_text())
    if state.get('accepted'):raise ValueError('accepted prior is immutable; use a new experiment')
    digest=sha(a.generated);folder=root/'prior_agent/generations'/digest
    folder.mkdir(parents=True,exist_ok=True)
    shutil.copy2(a.generated,folder/'image.png');shutil.copy2(a.prompt_file,folder/'prompt.txt')
    with Image.open(a.generated) as image:size=image.size;mode=image.mode
    record={'timestamp':datetime.now(timezone.utc).isoformat(),'generator':'Codex built-in Image Gen',
            'model_checkpoint':'UNKNOWN','seed':'UNKNOWN','steps':'UNKNOWN','guidance':'UNKNOWN',
            'exactly_reproducible':False,'prompt_file':str(folder/'prompt.txt'),
            'prompt':a.prompt_file.read_text().strip(),'negative_prompt':None,
            'reference_image':state['selected_depth'],'reference_sha256':sha(Path(state['selected_depth'])),
            'semantic_sha256':digest,'source_image':str(a.generated.resolve()),
            'native_size':size,'native_mode':mode,'transparent_background':False,
            'postprocessing':'pending RMBG and same-canvas review'}
    write_json(folder/'generation.json',record)
    shutil.copy2(folder/'image.png',root/'semantic.png');write_json(root/'generation.json',record)
    print(root/'semantic.png')


if __name__=='__main__':main()
