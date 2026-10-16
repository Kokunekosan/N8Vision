"""Independent foreground extraction and bounded optional YOLO naming."""
import json,time,logging
from PIL import Image,ImageOps
from . import subjects
LOG=logging.getLogger('n8vision')

def extract(path,cache):
 import cv2,numpy as np
 with subjects.INFERENCE_LOCK:
  start=time.perf_counter()
  with Image.open(path) as source:image=ImageOps.exif_transpose(source).convert('RGB')
  mask=subjects.foreground(image,cache)
  count,labels,stats,_=cv2.connectedComponentsWithStats(mask.astype('uint8'),8)
  minimum=max(16,int(mask.size*.0005));candidates=[]
  for i in range(1,count):
   if stats[i,cv2.CC_STAT_AREA]<minimum:continue
   x,y,w,h=map(int,stats[i,:4]);region=labels==i
   candidates.append({'concept':'unidentified subject','confidence':1.,'bbox':[x,y,x+w,y+h],'mask':region})
  model,device=subjects._models.get('birefnet',(None,'unknown'))
  LOG.info('Foreground extraction: %s, %.2fs, %s regions; no YOLO naming',device,time.perf_counter()-start,len(candidates))
  return candidates,mask.shape

def name_regions(path,rows,weights,classes,max_passes,progress=None):
 """Hard budget per IMAGE, including every broad/family retry. Never modifies masks."""
 import numpy as np
 start=time.perf_counter();used=0;updates=[]
 with subjects.INFERENCE_LOCK:
  with Image.open(path) as source:image=ImageOps.exif_transpose(source).convert('RGB')
  shape=(image.height,image.width)
  # A broad pass per region first; optional retries cannot starve later regions.
  targets=[]
  for row in rows:
   g=json.loads(row['geometry']) if isinstance(row['geometry'],str) else row['geometry']
   mask=subjects.geometry_mask(g,shape)
   if mask is None:continue
   x,y,z,t=map(int,g['bbox']);pixels=np.asarray(image.crop((x,y,z,t))).copy();pixels[~mask[y:t,x:z]]=127
   targets.append((row,g,Image.fromarray(pixels),None))
  best={};vocabularies=[subjects.subject_classes(classes),*subjects.VERIFICATION_CLASSES.values()]
  for vocabulary in vocabularies:
   for index,(row,g,crop,_) in enumerate(targets):
    if used>=max_passes:break
    if index in best and best[index]['confidence']>=subjects.NAME_MIN_CONFIDENCE:continue
    if progress:progress()
    results=subjects.world(crop,vocabulary,weights,confidence=.05,single=True);used+=1
    # A tiny enclosed object is not a supported name for the entire region.
    for result in results:
     x,y,z,t=result['bbox'];coverage=max(0,z-x)*max(0,t-y)/max(1,crop.width*crop.height)
     if not subjects.target_label(result['concept']) or coverage<.5:continue
     if index not in best or result['confidence']>best[index]['confidence']:best[index]=result
   if used>=max_passes:break
  for index,(row,g,_,_) in enumerate(targets):
   proposal=best.get(index)
   if not proposal:continue
   accepted=proposal['confidence']>=subjects.NAME_MIN_CONFIDENCE
   changed={**g,'name_confidence':proposal['confidence'],'name_accepted':accepted,'name_min_confidence':subjects.NAME_MIN_CONFIDENCE,'proposed_concept':proposal['concept'],'naming_method':'yolast','yolast_passes':used}
   updates.append((row,proposal['concept'] if accepted else 'unidentified subject',changed))
 LOG.info('YOLAST naming: %s/%s passes, %.2fs; %s regions inspected',used,max_passes,time.perf_counter()-start,min(len(targets),used))
 return updates,used,max(0,len(targets)-min(len(targets),used))
