"""Explicit cleanup; uncertainty about availability always preserves records."""
import hashlib,json,re
from pathlib import Path
from .observation_display import geometry
from .subject_learning import identity

def missing_local_model(row,root,models_root):
 if row['provider']=='ultralytics-erax':
  base=Path(models_root)/'bbox'
  return base.is_dir() and not (base/'erax_nsfw_yolo11m.pt').exists()
 if row['provider']!='ultralytics':return False
 name=re.sub(r'#conf=[0-9.]+$','',row['model'] or '')
 if Path(name).suffix.lower() not in ('.pt','.onnx','.engine','.yaml','.yml'):return False
 # Auto-download builtins and remote model IDs are not removable local detectors.
 if not Path(name).is_absolute() and '/' not in name and '\\' not in name:
  if name in ('yolov8n-oiv7.pt','yolov8s-worldv2.pt'):return False
  bases=[Path(models_root)/family for family in ('bbox','seg')]
  if not all(base.is_dir() for base in bases):return False
  return not any(p.name.casefold()==name.casefold() for base in bases for p in base.rglob('*') if p.is_file())
 path=Path(name)
 if not path.is_absolute():path=Path(root)/path
 # An offline drive or unavailable model directory is not evidence of uninstall.
 try:
  path.relative_to(Path(models_root))
  return Path(models_root).is_dir() and not path.exists()
 except ValueError:pass
 return path.parent.is_dir() and not path.exists()

def preview(c,root,models_root,include_reviewed=False):
 rows=[dict(row) for row in c.execute('SELECT rowid AS oid,* FROM observations')]
 referenced=set()
 for row in rows:
  for part in geometry(row).get('subject_parts',[]):
   if part.get('id'):referenced.add(part['id'])
 candidates=[];protected=0;models={};availability={}
 has_corrections=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='corrections'").fetchone()
 corrected={(row[0],row[1],row[2]) for row in c.execute('SELECT DISTINCT path,original_provider,original_model FROM corrections')} if has_corrections else set()
 for row in rows:
  model_key=(row['provider'],row['model'])
  if model_key not in availability:availability[model_key]=missing_local_model(row,root,models_root)
  if not availability[model_key]:continue
  g=geometry(row)
  if not include_reviewed and (g.get('review_status')=='approved' or g.get('subject_learning') or g.get('subject_parts') or identity(row) in referenced):
   protected+=1;continue
  # Relabels recorded by the user remain useful even without the original model.
  taught=(row['path'],row['provider'],row['model']) in corrected
  if taught and not include_reviewed:protected+=1;continue
  candidates.append(row);models[row['model']]=models.get(row['model'],0)+1
 encoded=json.dumps(candidates,sort_keys=True,separators=(',',':'),default=str)
 return candidates,{'observations':len(candidates),'protected':protected,'models':[{'model':name,'observations':count} for name,count in sorted(models.items())],'token':hashlib.sha256(encoded.encode()).hexdigest()}

def detach_removed(c,deleted):
 """Remove live ownership references; committed teaching snapshots stay intact."""
 from .subject_learning import add_visible_pixels
 identities={identity(row) for row in deleted};subjects={geometry(row).get('subject_id') for row in deleted}-{None}
 deleted_ids={row['oid'] for row in deleted}
 for raw in c.execute('SELECT rowid AS oid,* FROM observations').fetchall():
  row=dict(raw)
  if row['oid'] in deleted_ids:continue
  g=geometry(row);parts=g.get('subject_parts',[]);remaining=[part for part in parts if part.get('id') not in identities];changed=len(parts)!=len(remaining)
  if changed:
   base=g.get('base_geometry')
   if base:
    for key in ('bbox','mask_size','mask_rle','polygon'):g.pop(key,None)
    g.update(base)
    for part in remaining:g=add_visible_pixels(g,part['geometry'])
   else:g['subject_composite_ready']=False
   g['subject_parts']=remaining
  for key in ('owner_subject_id','suggested_owner_subject_id'):
   if g.get(key) in subjects:g.pop(key);g['ownership_status']='unresolved';changed=True
  if changed:
   g.pop('qwen_review',None)
   if g.get('subject_learning') and not g['subject_learning'].get('confirmed'):g.pop('subject_learning',None)
   c.execute('UPDATE observations SET geometry=?,updated=unixepoch() WHERE rowid=?',(json.dumps(g,sort_keys=True,separators=(',',':')),row['oid']))
