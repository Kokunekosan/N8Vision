"""User-prompted instance drafts. Hint boxes never clip the resulting masks."""
import numpy as np
from PIL import Image,ImageOps
from . import subjects

def build(path,parent,hints,cache,sam,weights,max_passes,progress=None):
 with subjects.INFERENCE_LOCK:
  with Image.open(path) as source:image=ImageOps.exif_transpose(source).convert('RGB')
  shape=(image.height,image.width);parent_mask=subjects.geometry_mask(parent,shape)
  if parent_mask is None:raise ValueError('Selected subject needs a valid mask')
  x,y,z,t=map(int,parent['bbox']);crop=image.crop((x,y,z,t));local_parent=parent_mask[y:t,x:z]
  foreground=subjects.foreground(crop,cache)&local_parent
  boxes=[[a-x,b-y,c-x,d-y] for a,b,c,d in hints]
  if progress:progress(1,len(hints)+2,phase='Guided SAM instance masks')
  masks=sam(crop,boxes)
  if len(masks)!=len(hints):raise ValueError('SAM did not return one mask per hint; original retained')
  candidates=[]
  for index,mask in enumerate(masks):
   region=np.asarray(mask,dtype=bool)&foreground
   if not region.any():raise ValueError(f'Hint {index+1} returned no foreground pixels; adjust its box')
   yy,xx=np.nonzero(region);a,b,c,d=int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)
   candidates.append({'concept':'unidentified subject','confidence':1.,'bbox':[a+x,b+y,c+x,d+y],'mask':region,'local_bbox':[a,b,c,d],'hint_index':index})
  # Identical prompt results are an unresolved split, never silently two subjects.
  for i,a in enumerate(candidates):
   for b in candidates[i+1:]:
    overlap=np.logical_and(a['mask'],b['mask']).sum()/max(1,np.logical_or(a['mask'],b['mask']).sum())
    if overlap>=.9:raise ValueError('Two hints returned the same subject. Tighten or reposition them; original retained.')
  passes=0
  vocabularies=[subjects.subject_classes(),*subjects.VERIFICATION_CLASSES.values()]
  for vocabulary in vocabularies:
   for candidate in candidates:
    if passes>=max_passes:break
    if candidate.get('name_accepted'):continue
    if progress:progress(1,len(hints)+2,phase=f'YOLAST naming pass {passes+1}/{max_passes}')
    a,b,c,d=candidate['local_bbox'];pixels=np.asarray(crop.crop((a,b,c,d))).copy();pixels[~candidate['mask'][b:d,a:c]]=127
    names=subjects.world(Image.fromarray(pixels),vocabulary,weights,confidence=.05,single=True);passes+=1
    for name in names:
     if not subjects.target_label(name['concept']):continue
     if name['confidence']>candidate.get('name_confidence',0):
      candidate['name_confidence']=name['confidence'];candidate['proposed_concept']=name['concept']
      if name['confidence']>=subjects.NAME_MIN_CONFIDENCE:candidate.update(concept=name['concept'],name_accepted=True)
   if passes>=max_passes:break
  results=[]
  for candidate in candidates:
   a,b,c,d=candidate['local_bbox'];region=candidate['mask']
   conflicts=sum(int(np.logical_and(region,other['mask']).sum()) for other in candidates if other is not candidate)
   g={'bbox':candidate['bbox'],'mask_size':[c-a,d-b],'mask_rle':subjects.rle(region[b:d,a:c]),'source_size':[shape[1],shape[0]],'scope':'mask','method':'birefnet+sam-guided','subject_role':True,'subject_pipeline':subjects.PIPELINE,'review_status':'draft','review_required':True,'name_accepted':candidate.get('name_accepted',False),'name_confidence':candidate.get('name_confidence',0),'proposed_concept':candidate.get('proposed_concept'),'guided_hint':hints[candidate['hint_index']],'instance_separation':'sam-guided','separation_conflict_pixels':conflicts}
   results.append({'concept':candidate['concept'],'confidence':1.,'geometry':g})
  return {'candidates':results,'naming_passes':passes,'overlap_review_required':any(r['geometry']['separation_conflict_pixels'] for r in results)}
