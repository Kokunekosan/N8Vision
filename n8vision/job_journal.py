"""Durable diagnostic snapshots, never a queue to resume."""
import json,os,uuid
from pathlib import Path

FIELDS=('id','kind','state','phase','done','total','updated','created','current_model','last_image','model_index','model_total','model_done','model_images','error')
def summarize(job):
 result={k:job[k] for k in FIELDS if k in job}
 recovery=job.get('recovery_progress') or (job.get('result') or {}).get('recovery')
 if isinstance(recovery,dict):result['recovery']={k:recovery.get(k,0) for k in ('recovered','failed','total')}
 return result

def atomic_json(path,data):
 path=Path(path);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
 try:
  with temp.open('w',encoding='utf-8') as stream:
   json.dump(data,stream,indent=2);stream.flush();os.fsync(stream.fileno())
  os.replace(temp,path)
 finally:temp.unlink(missing_ok=True)

def read_valid(path):
 value=json.loads(Path(path).read_text(encoding='utf-8'))
 if not isinstance(value,dict) or not isinstance(value.get('jobs'),list):raise ValueError('Invalid journal structure')
 if any(not isinstance(job,dict) for job in value['jobs']):raise ValueError('Invalid job record')
 return value

def write(path,data):
 path=Path(path);backup=path.with_suffix(path.suffix+'.bak')
 try:previous=read_valid(path)
 except (OSError,ValueError):previous=None
 if previous is not None:atomic_json(backup,previous)
 atomic_json(path,data)

def recover(path):
 path=Path(path);errors=[]
 for source in [path,path.with_suffix(path.suffix+'.bak')]:
  if not source.exists():continue
  try:return read_valid(source),source!=path,errors
  except (OSError,ValueError) as error:errors.append(str(error))
 return None,False,errors
