"""Confirmed composite classes, immutable lessons and atomic trained releases."""
import hashlib,json,os,subprocess,sys,tempfile,threading,time,uuid,logging
from pathlib import Path
from .observation_display import concept_key

TRAIN_LOCK=threading.Lock()
def tables(c):
 from .subject_learning import tables as lesson_tables
 lesson_tables(c)
 for name in ('crop_path','crop_sha256','class_key'):
  if name not in {row[1] for row in c.execute('PRAGMA table_info(subject_learning_examples)')}:c.execute('ALTER TABLE subject_learning_examples ADD COLUMN '+name+' TEXT')
 c.execute('CREATE TABLE IF NOT EXISTS subject_classes(class_key TEXT PRIMARY KEY,label TEXT NOT NULL,created REAL NOT NULL DEFAULT (unixepoch()))')
 c.execute('CREATE TABLE IF NOT EXISTS subject_class_runs(id TEXT PRIMARY KEY,state TEXT NOT NULL,manifest_hash TEXT NOT NULL,report TEXT,created REAL NOT NULL DEFAULT (unixepoch()))')

def record(c,token,label,path,g,root):
 """Only the explicit Learn Subject call may invoke this."""
 from .composite_images import isolate
 tables(c);key=concept_key(label)
 if key in ('unknown','unidentified','unidentified subject'):
  c.execute("UPDATE subject_learning_examples SET state='ownership_only' WHERE id=?",(token,));return {'state':'ownership_only','class_registered':False}
 if len(token)!=32 or any(ch not in '0123456789abcdef' for ch in token):raise ValueError('Invalid teaching revision')
 before=Path(path).stat();data=isolate(path,g);after=Path(path).stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Source changed while capturing its composite')
 digest=hashlib.sha256(data).hexdigest();folder=Path(root)/'examples';folder.mkdir(parents=True,exist_ok=True)
 target=folder/(token+'.png');temporary=folder/(token+'.tmp')
 temporary.write_bytes(data);os.replace(temporary,target)
 c.execute('INSERT OR IGNORE INTO subject_classes(class_key,label) VALUES(?,?)',(key,label))
 c.execute("UPDATE subject_learning_examples SET crop_path=?,crop_sha256=?,class_key=?,state='pending_class_training' WHERE id=?",(str(target),digest,key,token))
 return {'state':'pending_class_training','class_registered':True,'class_key':key}

def dataset(c,root):
 """Use the latest confirmed revision per physical subject; never draft inference."""
 tables(c);rows=[dict(row) for row in c.execute('SELECT * FROM subject_learning_examples ORDER BY created,rowid')];latest={};blocked=[]
 for row in rows:
  snap=json.loads(row['snapshot']);g=snap.get('geometry',{});sid=g.get('subject_id')
  identity=(row['source_sha256'],sid or json.dumps(g.get('base_geometry') or {k:g.get(k) for k in ('bbox','mask_size','mask_rle','polygon')},sort_keys=True))
  latest[identity]=row
 examples=[]
 for row in latest.values():
  snap=json.loads(row['snapshot'])
  if snap.get('confirmation')!='manual':continue
  key=concept_key(row['label'])
  if key in ('unknown','unidentified','unidentified subject'):continue
  try:
   if not row.get('crop_path'):
    path=Path(row['path'])
    if not path.is_file() or sha(path)!=row['source_sha256']:raise ValueError('Legacy source unavailable or changed')
    record(c,row['id'],row['label'],path,snap['geometry'],root)
    row=dict(c.execute('SELECT * FROM subject_learning_examples WHERE id=?',(row['id'],)).fetchone())
   path=Path(row['crop_path'])
   if not path.is_file() or sha(path)!=row['crop_sha256']:raise ValueError('Frozen composite unavailable or changed')
   examples.append({'id':row['id'],'class_key':row['class_key'],'label':row['label'],'image':str(path),'crop_sha256':row['crop_sha256'],'source_group':row['source_sha256']})
  except (OSError,ValueError) as exc:blocked.append({'id':row['id'],'reason':str(exc)})
 # Identical frozen pixels cannot acquire contradictory simultaneous targets.
 by_crop={}
 for row in examples:by_crop.setdefault(row['crop_sha256'],[]).append(row)
 usable=[]
 for same in by_crop.values():
  if len({row['class_key'] for row in same})>1:blocked.extend({'id':row['id'],'reason':'Conflicting labels for identical composite pixels'} for row in same)
  else:usable.append(same[-1])
 return usable,blocked

def sha(path):
 digest=hashlib.sha256()
 with Path(path).open('rb') as source:
  for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
 return digest.hexdigest()

def manifest_hash(rows):
 # Dataset order and local cache paths are not training targets.
 semantic=[{key:row.get(key) for key in ('id','class_key','label','crop_sha256','source_group')} for row in rows]
 semantic.sort(key=lambda row:row['id'])
 return hashlib.sha256(json.dumps(semantic,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def validate_snapshot(original,current,trained_ids):
 before={row['id']:row for row in original};after={row['id']:row for row in current}
 target=lambda row:tuple(row.get(field) for field in ('class_key','label','crop_sha256','source_group'))
 current_targets={target(row) for row in current}
 missing=[key for key in trained_ids if key not in after and (key not in before or target(before[key]) not in current_targets)]
 changed=[key for key in trained_ids if key in after and (key not in before or manifest_hash([before[key]])!=manifest_hash([after[key]]))]
 if missing or changed:raise ValueError('A lesson used by this candidate was relabeled, replaced, or lost its verified pixels during training; candidate was not activated')
 return len(set(after)-set(before))

def encoder_path(parser_root):
 for repo in ('PartGLEE','LangHOPS'):
  path=Path(parser_root)/repo/'projects/PartGLEE/clip_vit_base_patch32'
  if (path/'pytorch_model.bin').is_file():return path
 raise ValueError('Run Install-SubjectParts.cmd once to install the shared visual encoder')

def run_worker(root,parser_root,payload,progress=None):
 root=Path(root);root.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='worker-',dir=root) as raw:
  folder=Path(raw);request=folder/'request.json';output=folder/'result.json';log=folder/'worker.log'
  request.write_text(json.dumps({**payload,'encoder':str(encoder_path(parser_root)),'parser_root':str(parser_root),'feature_cache':str(root/'features')}),encoding='utf-8')
  with log.open('w',encoding='utf-8') as stream:
   child=subprocess.Popen([sys.executable,str(Path(__file__).with_name('subject_class_worker.py')),'--request',str(request),'--output',str(output)],stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
   try:
    deadline=time.monotonic()+1800
    while child.poll() is None:
     if progress:progress(0,len(payload.get('examples',payload.get('images',[]))),phase='Learning composite classes' if payload['mode']=='train' else 'Recognizing learned classes')
     if time.monotonic()>deadline:raise TimeoutError('Composite class worker exceeded 30 minutes')
     time.sleep(.25)
   except BaseException:
    child.terminate()
    try:child.wait(timeout=5)
    except subprocess.TimeoutExpired:child.kill();child.wait()
    raise
  if child.returncode:raise RuntimeError(log.read_text(encoding='utf-8',errors='replace')[-6000:])
  return json.loads(output.read_text(encoding='utf-8'))

def active(root):
 file=Path(root)/'active.json'
 if not file.is_file():return None
 result=json.loads(file.read_text());revision=result['revision']
 if not isinstance(revision,str) or len(revision)!=32 or any(c not in '0123456789abcdef' for c in revision):raise ValueError('Invalid active class revision')
 checkpoint=Path(root)/'releases'/revision/'classifier.pt'
 if sha(checkpoint)!=result['checkpoint_sha256']:raise ValueError('Active classifier checksum mismatch')
 return {**result,'checkpoint':str(checkpoint)}

def status(c,root):
 tables(c);classes=[]
 for row in c.execute('SELECT class_key,label FROM subject_classes ORDER BY label COLLATE NOCASE'):
  counts=c.execute('SELECT COUNT(*),COUNT(DISTINCT source_sha256) FROM subject_learning_examples WHERE class_key=? AND crop_path IS NOT NULL',(row['class_key'],)).fetchone()
  classes.append({'class_key':row['class_key'],'label':row['label'],'lessons':counts[0],'source_images':counts[1],'ready':counts[1]>=3})
 runs=[dict(row) for row in c.execute('SELECT id,state,manifest_hash,report,created FROM subject_class_runs ORDER BY created DESC,rowid DESC LIMIT 5')]
 return {'classes':classes,'ready':sum(row['ready'] for row in classes)>=2,'active':active(root),'runs':runs,'minimum_sources_per_class':3,'training_scope':'composite visual class head'}

def rollback(root):
 if not TRAIN_LOCK.acquire(blocking=False):raise ValueError('Wait for class training before rollback')
 try:
  current=active(root)
  if not current or not current.get('previous_revision'):raise ValueError('No previous trained revision is available')
  previous=current['previous_revision']
  if len(previous)!=32 or any(ch not in '0123456789abcdef' for ch in previous):raise ValueError('Invalid previous revision')
  folder=Path(root)/'releases'/previous;report=json.loads((folder/'report.json').read_text())
  if not report.get('passed'):raise ValueError('Previous revision did not pass validation')
  pointer={'revision':previous,'checkpoint_sha256':sha(folder/'classifier.pt'),'encoder_sha256':report['encoder_sha256'],'classes':report.get('active_classes',report['classes']),'validation':report['validation'],'previous_revision':None}
  temporary=Path(root)/'active.tmp';temporary.write_text(json.dumps(pointer,indent=2));os.replace(temporary,Path(root)/'active.json');return pointer
 finally:TRAIN_LOCK.release()

def train(db,root,parser_root,progress=None):
 if not TRAIN_LOCK.acquire(blocking=False):raise ValueError('Composite class training is already running')
 root=Path(root);revision=uuid.uuid4().hex;release=root/'releases'/revision;release.mkdir(parents=True,exist_ok=False)
 try:
  with db() as c:
   rows,blocked=dataset(c,root);fingerprint=manifest_hash(rows)
   c.execute('INSERT INTO subject_class_runs(id,state,manifest_hash) VALUES(?,?,?)',(revision,'training',fingerprint))
  previous=active(root)
  groups={}
  for row in rows:groups.setdefault(row['class_key'],{'label':row['label'],'sources':set(),'count':0});groups[row['class_key']]['sources'].add(row['source_group']);groups[row['class_key']]['count']+=1
  summary='; '.join(f'{g["label"]}: {g["count"]} examples / {len(g["sources"])} source images'+(' (deferred: needs 3 sources)' if len(g['sources'])<3 else '') for g in groups.values())
  logging.getLogger('n8vision').info('Subject training dataset: %s',summary or 'no confirmed examples')
  if progress:progress(0,len(rows),phase='Training classes: '+summary)
  from .subject_class_validation import folds
  try:
   eligible,_,pending=folds(rows)
  except ValueError as exc:
   result={'deferred':True,'activated':False,'revision':revision,'blocked':blocked,'diagnostics':['Training deferred: '+str(exc),'Teaching examples retained; no candidate trained or rejected.','Available classes: '+(summary or 'none')]}
   with db() as c:c.execute('UPDATE subject_class_runs SET state=?,report=? WHERE id=?',('deferred',json.dumps(result),revision))
   (release/'report.json').write_text(json.dumps(result,indent=2))
   return result
  result=run_worker(root,parser_root,{'mode':'train','examples':rows,'checkpoint':str(release/'classifier.pt'),'previous':previous and previous['checkpoint']},progress)
  if progress:progress(len(rows),len(rows),phase='Validating learned classes')
  with db() as c:
   current,_=dataset(c,root)
   result['new_lessons_waiting']=validate_snapshot(rows,current,result.get('trained_examples',[row['id'] for row in rows]))
   result.update(revision=revision,blocked=blocked,manifest_hash=fingerprint)
   result['had_active_model']=bool(previous)
   result['activated']=bool(result.get('passed'))
   from .subject_training_report import describe_training
   result.setdefault('diagnostics',describe_training(result))
   if result.get('passed'):
    pointer={'revision':revision,'checkpoint_sha256':sha(release/'classifier.pt'),'encoder_sha256':result['encoder_sha256'],'classes':result.get('active_classes',result['classes']),'validation':result['validation'],'previous_revision':previous and previous['revision']}
    temp=root/'active.tmp';temp.write_text(json.dumps(pointer,indent=2));os.replace(temp,root/'active.json')
    for example_id in result.get('activated_examples',result['trained_examples']):c.execute("UPDATE subject_learning_examples SET state='trained_class' WHERE id=?",(example_id,))
   c.execute('UPDATE subject_class_runs SET state=?,report=? WHERE id=?',('active' if result.get('passed') else 'rejected',json.dumps(result),revision))
  result['activated']=bool(result.get('passed'))
  (release/'report.json').write_text(json.dumps(result,indent=2));return result
 except BaseException as exc:
  with db() as c:
   tables(c);c.execute('UPDATE subject_class_runs SET state=?,report=? WHERE id=?',('failed',json.dumps({'error':str(exc)}),revision))
  raise
 finally:TRAIN_LOCK.release()
