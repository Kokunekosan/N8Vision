"""On-demand foreground separation and conservative annotation inheritance."""
import json
import threading
from pathlib import Path

MODEL_ID='ZhengPeng7/BiRefNet'
REVISION='e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4'
PIPELINE='subjects-s6'
NAME_MIN_CONFIDENCE=.65
INFERENCE_LOCK=threading.RLock()
_models={}
DEFAULT_CLASSES=['woman','man','girl','boy','person','bride','groom','dog','cat','horse','bird','rabbit','wolf','fox','bear','lion','tiger','deer','fish','dragon','robot','alien','elf','fairy','monster','car','truck','motorcycle','bicycle','boat','airplane','hamburger','sandwich','pizza','cake','fruit','food','flower','tree','plant','statue','toy','instrument','chair','table','object']
VERIFICATION_CLASSES={
 'human':['person','woman','man','girl','boy','catgirl','nekojin','anthropomorphic cat person','rider','driver','motorcyclist','cyclist','elf','alien','robot'],
 'animal':['horse','equine','dog','cat','bird','rabbit','wolf','fox','bear','lion','tiger','deer','dragon'],
 'vehicle':['car','motorcycle','bicycle','truck','bus','scooter','boat','airplane','vehicle'],
 'food':['hamburger','sandwich','pizza','cake','fruit','food'],
}
DEFAULT_CLASSES=list(dict.fromkeys([*DEFAULT_CLASSES,*[name for names in VERIFICATION_CLASSES.values() for name in names]]))
NON_SUBJECT_WORDS={'fashion','clothing','clothes','bra','brassiere','brassier','bikini','lingerie','dress','shirt','pants','jacket','hat','shoe','shoes','necklace','face','eye','eyes','mouth','nose','hair','hand','hands','arm','arms','leg','legs','breast','breasts','torso','skin','portrait','lighting','composition','style','background'}

def target_label(label):
 import re
 words=set(re.findall(r'[a-z]+',str(label).casefold()))
 return bool(words) and not words.intersection(NON_SUBJECT_WORDS) and str(label).casefold()!='unidentified subject'

def subject_classes(extra=None):
 return list(dict.fromkeys([*DEFAULT_CLASSES,*[str(x).strip().casefold() for x in (extra or []) if target_label(x)]]))

def family(label):
 words=set(str(label).casefold().split())
 if words.intersection({'woman','female','man','male','girl','boy','person','human','bride','groom','catgirl','nekojin','rider','driver','motorcyclist','cyclist','elf','alien','robot','fairy'}):return 'human'
 if words.intersection(set(VERIFICATION_CLASSES['vehicle'])):return 'vehicle'
 if words.intersection(set(VERIFICATION_CLASSES['food'])):return 'food'
 return label_key(label)

def label_key(label):
 value=str(label).strip().casefold()
 return {'female':'woman','male':'man','equine':'horse','nekojin':'catgirl'}.get(value,value)

def rle(mask):
 import numpy as np
 flat=mask.astype(bool).ravel();edges=np.diff(np.concatenate(([False],flat,[False])).astype('int8'))
 starts=np.flatnonzero(edges==1);ends=np.flatnonzero(edges==-1)
 return [int(v) for pair in zip(starts,ends-starts) for v in pair]

def geometry_mask(geometry,shape):
 import numpy as np
 from PIL import Image,ImageDraw
 h,w=shape;g=geometry;box=g.get('bbox')
 if not isinstance(box,list) or len(box)!=4:return None
 x1,y1,x2,y2=map(int,box)
 if not (0<=x1<x2<=w and 0<=y1<y2<=h):return None
 result=np.zeros(shape,dtype=bool)
 if g.get('polygon'):
  image=Image.new('1',(w,h));ImageDraw.Draw(image).polygon([tuple(p) for p in g['polygon']],fill=1)
  return np.asarray(image,dtype=bool)
 size=g.get('mask_size');runs=g.get('mask_rle')
 if size!=[x2-x1,y2-y1] or not isinstance(runs,list) or len(runs)%2:return None
 flat=np.zeros(size[0]*size[1],dtype=bool)
 for start,length in zip(runs[::2],runs[1::2]):
  if not isinstance(start,int) or not isinstance(length,int) or start<0 or length<=0 or start+length>flat.size:return None
  flat[start:start+length]=True
 if not flat.any():return None
 result[y1:y2,x1:x2]=flat.reshape((size[1],size[0]));return result

def matching_annotation(candidate,rows,shape,used=None):
 """Labels plus tight spatial identity; masked candidates require pixel agreement."""
 import numpy as np
 used=used or set();mask=candidate['mask'];box=candidate['bbox'];best=None;best_key=(-1,0)
 for row in rows:
  if row['oid'] in used or row['confidence']<=0 or label_key(row['concept'])!=label_key(candidate['concept']):continue
  try:
   g=json.loads(row['geometry']) if isinstance(row['geometry'],str) else row['geometry']
   if g.get('source_size') and g['source_size']!=[shape[1],shape[0]]:continue
   if g.get('scope') in ('image','whole_image','whole-image'):continue
   other=g.get('bbox');a,b,c,d=map(float,other)
   if c<=a or d<=b:continue
   if not (0<=a<c<=shape[1] and 0<=b<d<=shape[0]):continue
   inter=max(0,min(box[2],c)-max(box[0],a))*max(0,min(box[3],d)-max(box[1],b))
   union=(box[2]-box[0])*(box[3]-box[1])+(c-a)*(d-b)-inter
   score=inter/union if union else 0
   if score<.7:continue
   old_mask=geometry_mask(g,shape)
   if old_mask is not None:
    pixel_union=np.logical_or(mask,old_mask).sum();pixel_score=np.logical_and(mask,old_mask).sum()/pixel_union if pixel_union else 0
    if pixel_score<.7:continue
    score=min(score,pixel_score)
   elif row['kind']=='mask':continue # malformed masks are never silently inherited
   key=(int(old_mask is not None),score)
   if key>best_key:best=(row,g,old_mask is not None);best_key=key
  except (ValueError,TypeError,KeyError,OverflowError):continue
 return best

def foreground(image,cache):
 import torch
 from torchvision import transforms
 from transformers import AutoModelForImageSegmentation
 from PIL import Image
 device='cuda' if torch.cuda.is_available() else 'cpu'
 if 'birefnet' not in _models:
  dtype=torch.float16 if device=='cuda' else torch.float32
  model=AutoModelForImageSegmentation.from_pretrained(MODEL_ID,revision=REVISION,code_revision=REVISION,trust_remote_code=True,cache_dir=str(cache)).to(device=device,dtype=dtype).eval()
  _models['birefnet']=(model,device)
 model,device=_models['birefnet']
 transform=transforms.Compose([transforms.Resize((1024,1024)),transforms.ToTensor(),transforms.Normalize([.485,.456,.406],[.229,.224,.225])])
 with torch.inference_mode():prediction=model(transform(image).unsqueeze(0).to(device=device,dtype=next(model.parameters()).dtype))[-1].sigmoid()[0,0].float().cpu()
 mask=transforms.ToPILImage()(prediction).resize(image.size,Image.Resampling.BILINEAR)
 import numpy as np
 return np.asarray(mask)>127

def world(image,classes,weights,confidence=.2,single=False):
 from ultralytics import YOLOWorld
 import ultralytics.nn.text_model as text_model
 weights=Path(weights)
 legacy=Path(__file__).resolve().parent.parent/'yolov8s-worldv2.pt'
 if not weights.is_file() and legacy.is_file():weights=legacy
 text_model.WEIGHTS_DIR=Path(__file__).resolve().parent.parent/'cache/subject-models'
 if 'world' not in _models:
  weights.parent.mkdir(parents=True,exist_ok=True)
  _models['world']=YOLOWorld(str(weights))
 model=_models['world']
 if _models.get('world-classes')!=tuple(classes):
  model.set_classes(classes);_models['world-classes']=tuple(classes)
 result=model(image,conf=confidence,max_det=1 if single else 100,verbose=False)[0]
 if result.boxes is None:return []
 return [{'bbox':list(map(float,b)),'concept':str(result.names[int(c)]),'confidence':float(s)} for b,c,s in zip(result.boxes.xyxy.cpu().tolist(),result.boxes.cls.cpu().tolist(),result.boxes.conf.cpu().tolist())]

def separate(image,mask,classes,weights,existing=None,sam=None):
 """Use archived whole-subject instances before proposing foreground-only targets."""
 import cv2,numpy as np
 from PIL import Image
 h,w=mask.shape;neutral=np.full((h,w,3),127,dtype='uint8');neutral[mask]=np.asarray(image)[mask]
 classes=subject_classes(classes)
 detections=[]
 detections.extend(d for d in world(Image.fromarray(neutral),classes,weights) if target_label(d['concept']))
 # Second pass inspects each major connected foreground crop with independent
 # vocabularies. Multiple names/instances are allowed, including high-confidence
 # composites; the single-target fallback runs only after component discovery.
 count,components,stats,_=cv2.connectedComponentsWithStats(mask.astype('uint8'),8)
 min_area=max(16,int(w*h*.0005))
 regions=sorted(range(1,count),key=lambda i:int(stats[i,cv2.CC_STAT_AREA]),reverse=True)
 for component in [i for i in regions if stats[i,cv2.CC_STAT_AREA]>=min_area][:8]:
  left,top,width,height=map(int,stats[component,:4]);crop=Image.fromarray(neutral).crop((left,top,left+width,top+height))
  for category,vocabulary in VERIFICATION_CLASSES.items():
   for detection in world(crop,vocabulary,weights,confidence=.15):
    if not target_label(detection['concept']):continue
    x1,y1,x2,y2=detection['bbox']
    detections.append({**detection,'bbox':[x1+left,y1+top,x2+left,y2+top],'verification_pass':category,'component_naming_pass':True})
 min_area=max(16,int(w*h*.0005));proposals=[]
 for detection in detections:
  try:x1,y1,x2,y2=[int(round(v)) for v in detection['bbox']]
  except (ValueError,TypeError,OverflowError):continue
  x1=max(0,x1);y1=max(0,y1);x2=min(w,x2);y2=min(h,y2)
  if x1>=x2 or y1>=y2:continue
  portion=np.zeros_like(mask);portion[y1:y2,x1:x2]=mask[y1:y2,x1:x2]
  saved=detection.get('saved_mask')
  if saved is not None:portion=saved.copy()
  if portion.sum()<min_area or portion.sum()/((x2-x1)*(y2-y1))<.1:continue
  proposal={**detection,'bbox':[x1,y1,x2,y2],'mask':portion,'mask_pixels':int(portion.sum()),'has_saved_mask':False,'review_required':True}
  if proposal['confidence']>=NAME_MIN_CONFIDENCE:
   annotated=[{**row,'oid':row.get('oid',i)} for i,row in enumerate(existing or [])]
   inherited=matching_annotation(proposal,annotated,(h,w))
   if inherited and inherited[2]:
    proposal['mask']=geometry_mask(inherited[1],(h,w));proposal['has_saved_mask']=True
    proposal['mask_pixels']=int(proposal['mask'].sum())
  proposals.append(proposal)
 def contained(child,parent):
  a,b,c,d=child['bbox'];x,y,z,t=parent['bbox']
  return max(0,min(c,z)-max(a,x))*max(0,min(d,t)-max(b,y))/max(1,(c-a)*(d-b))>.9
 # A generic Human/Person/Object box enclosing localized subjects is not another instance.
 def generic_parent(p):
  if p['concept'].casefold() not in ('human','person','object'):return False
  children=[q for q in proposals if q is not p and q['concept'].casefold() not in ('human','person','object') and (family(q['concept'])==family(p['concept']) or p['concept'].casefold()=='object' or p.get('automatic_draft')) and contained(q,p)]
  if not children:return False
  if not p.get('has_saved_mask') or p['concept'].casefold()=='object':return True
  if p.get('automatic_draft') and len({family(q['concept']) for q in children})>1:return True
  # Even a large group mask must not swallow two separately localized individuals.
  for i,a in enumerate(children):
   for b in children[i+1:]:
    intersection=np.logical_and(a['mask'],b['mask']).sum();union=np.logical_or(a['mask'],b['mask']).sum()
    if intersection/max(1,union)<.4:return True
  return False
 proposals=[p for p in proposals if not generic_parent(p)]
 # Count real occupied pixels, not the area of a sparse mask's enclosing box.
 proposals.sort(key=lambda c:(not c.get('has_saved_mask',False),-c['mask_pixels'] if c.get('has_saved_mask') else 0,not c.get('archived_target',False),-c['confidence']))
 candidates=[]
 for candidate in proposals:
  duplicate=False
  for accepted in candidates:
   if family(candidate['concept'])!=family(accepted['concept']):continue
   intersection=np.logical_and(candidate['mask'],accepted['mask']).sum()
   union=np.logical_or(candidate['mask'],accepted['mask']).sum()
   inherited_layers=(candidate.get('has_saved_mask') or accepted.get('has_saved_mask')) and intersection/max(1,min(candidate['mask'].sum(),accepted['mask'].sum()))>.9
   if intersection/max(1,union)>.95 or inherited_layers:
    duplicate=True;break
  if not duplicate:candidates.append(candidate)
 for component in range(1,count):
  if stats[component,cv2.CC_STAT_AREA]<min_area:continue
  region=components==component
  if any(np.logical_and(region,c['mask']).any() for c in candidates):continue
  ys,xs=np.where(region);bounds=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]
  focused=world(Image.fromarray(neutral).crop(bounds),classes,weights,confidence=.05,single=True)
  focused=[d for d in focused if target_label(d['concept'])]
  name=focused[0]['concept'] if focused else 'unidentified subject';score=focused[0]['confidence'] if focused else 0
  candidates.append({'bbox':bounds,'mask':region,'concept':name,'confidence':score,'review_required':True,'focused_pass':True})
 for candidate in candidates:
  # Existing whole-target identity is authoritative over a crop's clothing/part guess.
  if candidate.get('trusted_name') or candidate['confidence']>=NAME_MIN_CONFIDENCE or candidate.get('focused_pass'):continue
  focused=world(Image.fromarray(neutral).crop(candidate['bbox']),classes,weights,confidence=.05,single=True)
  candidate['focused_pass']=True
  if focused and target_label(focused[0]['concept']) and family(focused[0]['concept'])==family(candidate['concept']) and focused[0]['confidence']>candidate['confidence']:
   candidate['concept']=focused[0]['concept'];candidate['confidence']=focused[0]['confidence']
 if sam:
  overlaps=set()
  for i,a in enumerate(candidates):
   for j,b in enumerate(candidates[i+1:],i+1):
    intersection=np.logical_and(a['mask'],b['mask']).sum()
    if intersection/max(1,min(a['mask'].sum(),b['mask'].sum()))>.05:overlaps.update((i,j))
  for index in sorted(overlaps):
   candidate=candidates[index]
   if candidate.get('has_saved_mask'):candidate['instance_separation']='inherited';continue
   try:
    segmented=geometry_mask(sam(candidate['bbox']),(h,w))
    if segmented is None:raise ValueError('SAM returned no usable subject pixels')
    # Keep the original target box, and use only BiRefNet foreground inside it.
    x1,y1,x2,y2=candidate['bbox'];isolated=np.zeros_like(mask)
    isolated[y1:y2,x1:x2]=segmented[y1:y2,x1:x2]&mask[y1:y2,x1:x2]
    if isolated.sum()<min_area:raise ValueError('SAM subject mask is empty after foreground intersection')
    candidate['mask']=isolated;candidate['instance_separation']='sam';candidate['mask_pixels']=int(isolated.sum())
   except Exception as exc:
    candidate['instance_separation']='unresolved';candidate['separation_error']=str(exc)
  for i,a in enumerate(candidates):
   conflicts=0
   for j,b in enumerate(candidates):
    if i!=j and family(a['concept'])!=family(b['concept']):conflicts+=int(np.logical_and(a['mask'],b['mask']).sum())
   if conflicts:a['separation_conflict_pixels']=conflicts
 candidates=deduplicate_instances(candidates)
 for i,a in enumerate(candidates):
  a.pop('separation_conflict_pixels',None)
  conflict=sum(int(np.logical_and(a['mask'],b['mask']).sum()) for j,b in enumerate(candidates) if i!=j)
  if conflict:a['separation_conflict_pixels']=conflict
 return accept_names(candidates)

def same_instance(a,b):
 import numpy as np
 ma,mb=a['mask'],b['mask'];intersection=np.logical_and(ma,mb).sum();union=np.logical_or(ma,mb).sum()
 overlap=intersection/max(1,union)
 if overlap>=.9:return True
 x,y,z,t=a['bbox'];p,q,r,s=b['bbox']
 bi=max(0,min(z,r)-max(x,p))*max(0,min(t,s)-max(y,q));bu=(z-x)*(t-y)+(r-p)*(s-q)-bi
 box_overlap=bi/max(1,bu)
 return overlap>=.65 and box_overlap>=.5

def deduplicate_instances(candidates):
 """Cluster by actual pixels, with complete-link grouping to avoid bridge merges."""
 groups=[]
 for candidate in sorted(candidates,key=lambda c:(not c.get('has_saved_mask',False),-int(c['mask'].sum()),-c['confidence'])):
  group=next((g for g in groups if all(same_instance(candidate,other) for other in g)),None)
  if group is None:groups.append([candidate])
  else:group.append(candidate)
 result=[]
 for group in groups:
  representative=dict(group[0]);best=max(group,key=lambda c:(c.get('trusted_name',False),c['confidence']))
  representative['concept']=best['concept'];representative['confidence']=best['confidence']
  representative['duplicate_proposals_collapsed']=len(group)-1
  result.append(representative)
 return result

def duplicate_subject_rows(rows,shape,active=None):
 """Find redundant subject-role rows; non-subject annotations never participate."""
 candidates=[]
 for row in rows:
  try:g=json.loads(row['geometry']) if isinstance(row['geometry'],str) else row['geometry']
  except (TypeError,ValueError):continue
  if g.get('subject_role') is False:continue
  if not (g.get('subject_role') or g.get('subject_pipeline') or row['provider']=='subject-intelligence'):continue
  mask=geometry_mask(g,shape)
  if mask is None:continue
  candidates.append({'row':row,'geometry':g,'mask':mask,'bbox':g['bbox'],'protected':row['provider']!='subject-intelligence' or g.get('review_status')=='approved','confidence':float(g.get('name_confidence',row['confidence']))})
 active=active or set()
 candidates.sort(key=lambda c:(bool(active) and c['row']['oid'] not in active,not c['protected'],not (c['geometry'].get('name_accepted') or c['confidence']>=NAME_MIN_CONFIDENCE),-int(c['mask'].sum()),-c['confidence']))
 groups=[];duplicates=[]
 for candidate in candidates:
  group=next((group for group in groups if all(same_instance(candidate,other) for other in group)),None)
  if group is None:groups.append([candidate])
  else:group.append(candidate);duplicates.append(candidate)
 return duplicates

def accept_names(candidates):
 """Separate localization confidence from the authority to assign a noun."""
 import numpy as np
 accepted=[]
 for candidate in candidates:
  score=float(candidate['confidence'])
  trusted=candidate.get('trusted_name',False)
  qualified=trusted or score>=NAME_MIN_CONFIDENCE
  if not qualified:
   # A weak alternate name for the exact same region is not an extra subject.
   redundant=any((other.get('trusted_name') or float(other['confidence'])>=NAME_MIN_CONFIDENCE) and (family(candidate['concept'])==family(other['concept']) or not candidate.get('component_naming_pass')) and np.logical_and(candidate['mask'],other['mask']).sum()/max(1,np.logical_or(candidate['mask'],other['mask']).sum())>=.8 for other in candidates if other is not candidate)
   if redundant:continue
  candidate['name_confidence']=score;candidate['name_min_confidence']=NAME_MIN_CONFIDENCE
  candidate['name_accepted']=bool(qualified and candidate['concept'].casefold()!='unidentified subject')
  if not qualified:
   candidate['proposed_concept']=candidate['concept'];candidate['concept']='unidentified subject'
  accepted.append(candidate)
 return accepted

def analyze(path,cache,weights,classes,existing=None,sam=None):
 from PIL import Image,ImageOps
 with INFERENCE_LOCK:
  with Image.open(path) as source:image=ImageOps.exif_transpose(source).convert('RGB')
  mask=foreground(image,cache)
  return separate(image,mask,classes,weights,existing,sam),mask.shape

def superseded_composite(concept,geometry,candidates,shape):
 """Retire only generic automatic drafts now covered by multiple named instances."""
 import numpy as np
 if str(concept).casefold() not in ('object','unidentified subject','human','person'):return False
 old=geometry_mask(geometry,shape)
 if old is None:return False
 children=[c for c in candidates if c['concept'].casefold() not in ('object','unidentified subject','human','person') and np.logical_and(c['mask'],old).sum()/max(1,c['mask'].sum())>.8]
 if len(children)<2:return False
 distinct=any(family(a['concept'])!=family(b['concept']) or np.logical_and(a['mask'],b['mask']).sum()/max(1,np.logical_or(a['mask'],b['mask']).sum())<.4 for i,a in enumerate(children) for b in children[i+1:])
 if not distinct:return False
 covered=np.zeros(shape,dtype=bool)
 for child in children:covered|=child['mask']
 return np.logical_and(old,covered).sum()/max(1,old.sum())>=.8
