"""Run optional pretrained parsers and persist draft ownership/composites."""
import json,os,subprocess,sys,tempfile,time,uuid
from pathlib import Path

def release_idle_comfy(url):
 from urllib.parse import urlsplit
 from urllib.request import urlopen,Request
 if urlsplit(url).hostname not in ('127.0.0.1','localhost','::1'):return False
 try:
  with urlopen(url.rstrip('/')+'/queue',timeout=2) as response:queue=json.load(response)
  if queue.get('queue_running') or queue.get('queue_pending'):return False
  with urlopen(Request(url.rstrip('/')+'/free',data=b'{"unload_models":true,"free_memory":true}',headers={'Content-Type':'application/json'}),timeout=2):return True
 except Exception:return False

def backend_status(root):
 root=Path(root)
 return {engine:{'source':(root/repo/'projects/PartGLEE/partglee').is_dir(),'weights':(root/'weights'/weight).is_file()} for engine,repo,weight in [('partglee','PartGLEE','PartGLEE-RN50.pth'),('langhops','LangHOPS','LangHOPS-full.pth')]}

def infer(root,engine,paths,progress=None):
 root=Path(root).resolve();status=backend_status(root)[engine]
 if not all(status.values()):raise RuntimeError('Run Install-SubjectParts.cmd to prepare the selected reconstruction backend')
 with tempfile.TemporaryDirectory(prefix='n8-reconstruct-',dir=root) as raw:
  temp=Path(raw);request=temp/'request.json';output=temp/'result.json';log=temp/'worker.log'
  request.write_text(json.dumps({'paths':paths}),encoding='utf-8')
  command=[sys.executable,str(Path(__file__).with_name('subjectifier_worker.py')),'--root',str(root),'--engine',engine,'--request',str(request),'--output',str(output)]
  with log.open('w',encoding='utf-8') as stream:
   child=subprocess.Popen(command,stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
   try:
    deadline=time.monotonic()+1800
    while child.poll() is None:
     if progress:progress(0,len(paths),phase='Reconstructing subjects with '+engine)
     if time.monotonic()>deadline:raise TimeoutError('Subject reconstruction exceeded 30 minutes')
     time.sleep(.25)
   except BaseException:
    child.terminate()
    try:child.wait(timeout=10)
    except subprocess.TimeoutExpired:child.kill();child.wait(timeout=10)
    raise
  if child.returncode:raise RuntimeError('Reconstruction backend failed: '+log.read_text(encoding='utf-8',errors='replace')[-12000:])
  return json.loads(output.read_text(encoding='utf-8'))

def persist(c,image,rows):
 import numpy as np
 from .subjects import geometry_mask,rle
 from .subject_learning import geometry,is_subject,identity
 shape=(image['source_size'][1],image['source_size'][0]);backend=image['backend'];provider='subjectifier-'+backend;model=backend+'-h1';used=set();created=0;attached=0;subject_ids={}
 def mask_geometry(mask):
  ys,xs=np.where(mask)
  if not len(xs):raise ValueError('Empty composite')
  a,b,d,e=int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1
  return {'bbox':[a,b,d,e],'mask_size':[d-a,e-b],'mask_rle':rle(mask[b:e,a:d]),'source_size':image['source_size']}
 def part_row(item):
  g={**item['geometry'],'source_size':image['source_size'],'subject_role':False,'review_status':'draft','ownership_query':item['query']}
  return {'path':image['path'],'concept':item['concept'],'confidence':item['confidence'],'provider':provider+'-parts','model':model,'kind':'mask','geometry':json.dumps(g,sort_keys=True,separators=(',',':'))}
 def write_part(row):
  c.execute('INSERT OR IGNORE INTO observations(path,concept,confidence,provider,model,kind,geometry) VALUES(?,?,?,?,?,?,?)',tuple(row[key] for key in ['path','concept','confidence','provider','model','kind','geometry']))
 for subject in image['subjects']:
  target=geometry_mask(subject['geometry'],shape)
  if target is None:raise ValueError('Backend returned invalid subject mask')
  candidates=[]
  for row in rows:
   if row['oid'] in used or not is_subject(row) or row['confidence']<=0:continue
   old=geometry(row['geometry']);mask=geometry_mask(old,shape)
   if mask is None:continue
   iou=np.logical_and(mask,target).sum()/max(1,np.logical_or(mask,target).sum())
   if iou>=.55:candidates.append((float(iou),row,old))
  match=max(candidates,key=lambda value:value[0]) if candidates else None
  old=match[2] if match else {};parts=[part for part in old.get('subject_parts',[]) if part.get('confirmation')=='manual']
  subject_id=old.get('subject_id') or uuid.uuid4().hex;subject_ids[subject['query']]=subject_id
  for item in subject['parts']:
   row=part_row(item);write_part(row);key=identity(row)
   if not any(part.get('id')==key for part in parts):parts.append({'id':key,'owner_subject_id':subject_id,'concept':row['concept'],'provider':row['provider'],'model':model,'geometry':geometry(row['geometry']),'confidence':row['confidence'],'confirmation':'machine-draft'})
  base=old.get('base_geometry',old) if match else subject['base_geometry']
  # Preserve all original visible base pixels and all explicitly attached parts.
  base_mask=geometry_mask(base,shape)
  if base_mask is not None:target|=base_mask
  for part in parts:
   part_mask=geometry_mask(part.get('geometry',{}),shape)
   if part_mask is not None:target|=part_mask
  g={**old,**mask_geometry(target),'subject_id':subject_id,'base_geometry':{key:value for key,value in base.items() if key not in ['subject_parts','base_geometry','qwen_review','subject_learning']},'subject_parts':parts,'subject_role':True,'subject_pipeline':model,'reconstruction_backend':backend,'subject_composite_ready':True,'ownership_status':'draft','reconstruction_proposed_concept':subject['proposed_concept']}
  if not match:g.update(proposed_concept=subject['proposed_concept'],name_confidence=subject['confidence'],name_accepted=subject['confidence']>=.65)
  # A previous language review described a different composite; don't present it
  # as a current interpretation after reconstruction changes its visible pixels.
  g.pop('qwen_review',None)
  encoded=json.dumps(g,sort_keys=True,separators=(',',':'))
  if match:
   row=match[1];used.add(row['oid'])
   changed=c.execute('UPDATE observations SET geometry=?,updated=unixepoch() WHERE rowid=? AND geometry IS ?',(encoded,row['oid'],row['geometry']))
   if changed.rowcount!=1:raise ValueError('Subject changed during reconstruction')
   attached+=1
  else:
   c.execute('INSERT OR IGNORE INTO observations(path,concept,confidence,provider,model,kind,geometry) VALUES(?,?,?,?,?,?,?)',(image['path'],subject['concept'],max(.01,subject['confidence']),provider,model,'mask',encoded));created+=1
 for item in image['unresolved_parts']:
  row=part_row(item);g=geometry(row['geometry']);g['ownership_status']='unresolved';g['suggested_owner_subject_id']=subject_ids[image['subjects'][item['suggested_owner']]['query']];row['geometry']=json.dumps(g,sort_keys=True,separators=(',',':'));write_part(row)
 return {'created':created,'updated':attached,'unresolved_parts':len(image['unresolved_parts'])}
