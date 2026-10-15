"""Install one profile without deleting existing environments or machine state."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
from n8vision.profiles import profile,default_edition

ROOT=Path(__file__).resolve().parent
ERAX_URL='https://huggingface.co/erax-ai/EraX-NSFW-V1.0/resolve/83b8c11eb32bb54f73d8ca51b6b56ef4292e06fd/erax_nsfw_yolo11m.pt?download=true'

def plan(edition,cuda=False):
 features=profile(edition);env=ROOT/'.venv'
 python=str(env/('Scripts/python.exe' if os.name=='nt' else 'bin/python'))
 pip=[python,'-m','pip','--disable-pip-version-check'];commands=[]
 if not Path(python).exists():commands.append([sys.executable,'-m','venv',str(env)])
 commands.append([*pip,'install','pip==26.2.1','setuptools==84.0.0','wheel==0.48.0','packaging==26.3'])
 commands.append([*pip,'install','-r',str(ROOT/'requirements-lite.lock')])
 if features['inference']:
  channel='https://download.pytorch.org/whl/cu130' if cuda else 'https://download.pytorch.org/whl/cpu'
  build='+cu130' if cuda else '+cpu'
  commands.append([*pip,'install','--index-url',channel,'torch==2.14.0'+build,'torchvision==0.29.1'+build])
  commands.append([*pip,'install','-r',str(ROOT/('requirements-full.lock' if edition=='full' else 'requirements-blurred.lock'))])
 # BiRefNet weights are fetched on demand by Full's subject separation action.
 return env,commands

def lock_records(path,seen=None):
 seen=set() if seen is None else seen;path=Path(path).resolve()
 if path in seen:return set()
 seen.add(path);records=set()
 for line in path.read_text(encoding='utf-8').splitlines():
  line=line.strip()
  if not line or line.startswith('#'):continue
  if line.startswith('-r '):records.update(lock_records(path.parent/line[3:].strip(),seen))
  else:records.add(line)
 return records

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--edition',choices=['lite','blurred','full'],default=None);ap.add_argument('--dry-run',action='store_true');ap.add_argument('--cpu',action='store_true');args=ap.parse_args()
 if args.edition is None and not args.dry_run:
  print('Choose the capacity to install into the shared environment:')
  print('1. Lite — browsing, archive maintenance and filesystem tools')
  print('2. Blurred — all current tools, including inference and processing')
  print('3. Full — Blurred tools plus BiRefNet subject separation')
  while True:
   choice=input('Choice [1]: ').strip().lower() or '1'
   args.edition={'1':'lite','2':'blurred','3':'full','lite':'lite','blurred':'blurred','full':'full'}.get(choice)
   if args.edition:break
   print('Choose 1, 2 or 3.')
 args.edition=args.edition or default_edition(ROOT,installing=True)
 if not args.dry_run and sys.version_info[:2]!=(3,14):raise SystemExit('Use Python 3.14 through py -3.14.')
 cuda=False
 if args.edition!='lite' and not args.cpu and shutil.which('nvidia-smi'):
  cuda=subprocess.run(['nvidia-smi','-L'],capture_output=True).returncode==0
 env,commands=plan(args.edition,cuda)
 if args.dry_run:
  print(json.dumps({'edition':args.edition,'environment':str(env),'commands':commands,'managed_weights':args.edition!='lite','shared_environment':True},indent=2));return 0
 subprocess_env={**os.environ,'PIP_CACHE_DIR':str(ROOT/'cache/pip')}
 target_python=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
 if target_python.exists():subprocess.run([str(target_python),'-c',"import sys;assert sys.version_info[:2]==(3,14),'Existing private environment must use Python 3.14; it was not modified'"],check=True)
 requirements=lock_records(ROOT/'requirements-lite.lock')
 if args.edition!='lite':requirements.update(lock_records(ROOT/('requirements-full.lock' if args.edition=='full' else 'requirements-blurred.lock')))
 signature=hashlib.sha256(('\n'.join(sorted(requirements))+str((sys.version_info[:2],cuda if args.edition!='lite' else False))+'pip26.2.1-setuptools84.0.0-wheel0.48.0-packaging26.3'+('' if args.edition=='lite' else 'torch2.14.0-vision0.29.1')).encode()).hexdigest()
 stamp=env/'.n8vision-install.json'
 core_signature=hashlib.sha256(('\n'.join(sorted(lock_records(ROOT/'requirements-lite.lock')))+str((sys.version_info[:2],False))+'pip26.2.1-setuptools84.0.0-wheel0.48.0-packaging26.3').encode()).hexdigest()
 try:
  receipt=json.loads(stamp.read_text(encoding='utf-8'))
  verified=set(receipt.get('verified_signatures',[]));verified.add(receipt.get('signature',''))
 except (OSError,ValueError):verified=set()
 reuse=signature in verified
 if reuse:print('Reusing the verified installed environment; no duplicate dependency installation.')
 else:
  for command in commands:subprocess.run(command,cwd=ROOT,env=subprocess_env,check=True)
 python=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
 check="import fastapi,uvicorn,PIL,send2trash,qrcode"
 if args.edition!='lite':check+=f";import importlib.metadata as m;assert m.version('torch')=='2.14.0{'+'+'cu130' if cuda else '+'+'cpu'}';import ultralytics,transformers"
 if args.edition=='full':check+=';import timm,einops,kornia,clip'
 subprocess.run([str(python),'-c',check],check=True)
 if args.edition!='lite':
  model=ROOT/'n8vision/models/ultralytics/bbox/erax_nsfw_yolo11m.pt'
  if not model.exists():
   model.parent.mkdir(parents=True,exist_ok=True);partial=model.with_suffix('.pt.part')
   try:
    urllib.request.urlretrieve(ERAX_URL,partial);partial.replace(model)
   finally:partial.unlink(missing_ok=True)
 verified.update([signature,core_signature]);verified.discard('')
 if args.edition=='full':
  blurred_requirements=lock_records(ROOT/'requirements-lite.lock')|lock_records(ROOT/'requirements-blurred.lock')
  blurred_signature=hashlib.sha256(('\n'.join(sorted(blurred_requirements))+str((sys.version_info[:2],cuda))+'pip26.2.1-setuptools84.0.0-wheel0.48.0-packaging26.3'+'torch2.14.0-vision0.29.1').encode()).hexdigest()
  verified.add(blurred_signature)
 stamp.write_text(json.dumps({'signature':signature,'verified_signatures':sorted(verified)}),encoding='utf-8')
 data=ROOT/'data';data.mkdir(exist_ok=True)
 temp=data/'edition.json.tmp';temp.write_text(json.dumps({'edition':args.edition}),encoding='utf-8');temp.replace(data/'edition.json')
 print(f'N8Vision {args.edition.title()} installed. Run N8Vision-{args.edition.title()}.cmd.');return 0

if __name__=='__main__':raise SystemExit(main())
