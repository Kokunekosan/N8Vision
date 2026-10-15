"""Manual subject teaching records and frozen class-training lessons."""
import hashlib,json,uuid

def geometry(value):
 try:return json.loads(value) if isinstance(value,str) else dict(value or {})
 except (TypeError,ValueError):return {}

def is_subject(row):
 g=geometry(row.get('geometry'))
 return g.get('subject_role') is not False and bool(g.get('subject_role') or g.get('subject_pipeline') or row.get('provider')=='subject-intelligence')

def mark_manual(g,reason,label,previous=None):
 result=dict(g)
 result.setdefault('subject_id',uuid.uuid4().hex)
 result['subject_learning']={'revision':uuid.uuid4().hex,'reason':reason,'label':label,'previous_label':previous,'confirmed':False}
 return result

def pending(row):
 state=geometry(row.get('geometry')).get('subject_learning',{})
 return is_subject(row) and bool(state.get('revision')) and not state.get('confirmed') and state.get('label')==row.get('concept')

def identity(row):
 g=geometry(row.get('geometry'))
 for key in ['qwen_review','subject_learning']:g.pop(key,None)
 data={key:row.get(key) for key in ['concept','provider','model','kind']};data['geometry']=g
 return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def tables(c):
 c.execute('''CREATE TABLE IF NOT EXISTS subject_learning_examples(
 id TEXT PRIMARY KEY,path TEXT NOT NULL,source_sha256 TEXT NOT NULL,
 source_size INTEGER NOT NULL,source_mtime_ns INTEGER NOT NULL,
 label TEXT NOT NULL,reason TEXT NOT NULL,snapshot TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'awaiting_trainer',created REAL NOT NULL DEFAULT (unixepoch()))''')

def add_visible_pixels(subject,part):
 """Union an explicitly attached part without importing an inference stack."""
 from PIL import Image,ImageChops,ImageDraw
 boxes=[list(map(int,g['bbox'])) for g in (subject,part)]
 a=min(box[0] for box in boxes);b=min(box[1] for box in boxes);d=max(box[2] for box in boxes);e=max(box[3] for box in boxes)
 union=Image.new('L',(d-a,e-b))
 for g,box in zip((subject,part),boxes):
  x1,y1,x2,y2=box;local=Image.new('L',(x2-x1,y2-y1))
  if g.get('polygon'):
   ImageDraw.Draw(local).polygon([(x-x1,y-y1) for x,y in g['polygon']],fill=255)
  else:
   if g.get('mask_size')!=[x2-x1,y2-y1]:raise ValueError('Mask dimensions do not match its box')
   data=bytearray((x2-x1)*(y2-y1));runs=g.get('mask_rle',[])
   for start,length in zip(runs[::2],runs[1::2]):data[start:start+length]=b'\xff'*length
   local=Image.frombytes('L',local.size,bytes(data))
  layer=Image.new('L',union.size);layer.paste(local,(x1-a,y1-b));union=ImageChops.lighter(union,layer)
 runs=[];start=None
 for index,value in enumerate(union.tobytes()):
  if value and start is None:start=index
  elif not value and start is not None:runs.extend((start,index-start));start=None
 if start is not None:runs.extend((start,union.width*union.height-start))
 if not runs:raise ValueError('Composite mask is empty')
 result=dict(subject)
 if not result.get('base_geometry'):result['base_geometry']={key:value for key,value in subject.items() if key in ['bbox','mask_size','mask_rle','polygon','source_size']}
 result.pop('polygon',None);result.update(bbox=[a,b,d,e],mask_size=[d-a,e-b],mask_rle=runs,subject_composite_ready=True)
 return result

def learn(c,row,path,dataset_root=None):
 if not pending(row):raise ValueError('Learn Subject requires a manual subject label change or added part')
 before=path.stat();digest=hashlib.sha256()
 with path.open('rb') as source:
  for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
 after=path.stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Source changed; review again')
 g=geometry(row['geometry']);state=g['subject_learning'];token=state['revision'];tables(c)
 snapshot={'schema':1,'concept':row['concept'],'provider':row['provider'],'model':row['model'],'kind':row['kind'],'geometry':g,'confirmation':'manual'}
 c.execute('INSERT INTO subject_learning_examples(id,path,source_sha256,source_size,source_mtime_ns,label,reason,snapshot) VALUES(?,?,?,?,?,?,?,?)',
  (token,str(path),digest.hexdigest(),after.st_size,after.st_mtime_ns,row['concept'],state['reason'],json.dumps(snapshot,sort_keys=True)))
 training={}
 if dataset_root is not None:
  from .subject_class_training import record
  training=record(c,token,row['concept'],path,g,dataset_root)
  final=path.stat()
  if (final.st_size,final.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Source changed while freezing the composite')
 g['subject_learning']={**state,'confirmed':True,'example_id':token}
 encoded=json.dumps(g,sort_keys=True,separators=(',',':'))
 changed=c.execute('UPDATE observations SET geometry=?,updated=unixepoch() WHERE rowid=? AND geometry IS ?',(encoded,row['oid'],row['geometry']))
 if changed.rowcount!=1:raise ValueError('Subject changed; refresh and review again')
 return {'ok':True,'example_id':token,'state':'awaiting_trainer','weights_updated':False,'geometry':g,**training}
