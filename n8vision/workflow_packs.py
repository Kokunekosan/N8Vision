"""Optional, data-only still-image workflow packs. No weights ship in core."""
import json
from pathlib import Path
import re
import math

TOKENS=('{{N8VISION_IMAGE}}','{{N8VISION_MASK}}','{{N8VISION_OUTPUT_PREFIX}}','{{N8VISION_RECOVERY_ID}}')

def load(root,pack_id):
 if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}',str(pack_id)):raise ValueError('Invalid workflow pack ID')
 folder=(Path(root)/pack_id).resolve()
 if folder.parent!=Path(root).resolve():raise ValueError('Pack must be inside the expansion folder')
 manifest=json.loads((folder/'pack.json').read_text(encoding='utf-8'))
 if not isinstance(manifest,dict) or not isinstance(manifest.get('name'),str) or not manifest['name'].strip():raise ValueError('Pack needs a name')
 if manifest.get('id')!=pack_id or manifest.get('schema')!=1 or manifest.get('mask_mode')!='boxes_union':raise ValueError('Unsupported workflow pack manifest')
 graph_path=(folder/manifest.get('workflow','')).resolve()
 if graph_path.parent!=folder or graph_path.suffix!='.json':raise ValueError('Workflow must be a JSON file inside its pack')
 graph=json.loads(graph_path.read_text(encoding='utf-8'))
 if not isinstance(graph,dict) or not graph:raise ValueError('Pack graph is empty')
 for node in graph.values():
  if not isinstance(node,dict) or not node.get('class_type') or not isinstance(node.get('inputs'),dict):raise ValueError('Pack graph must use Comfy API format')
 serialized=json.dumps(graph)
 if not all(token in serialized for token in TOKENS):raise ValueError('Pack is missing image, mask or recovery bindings')
 # Owned output routing is mandatory even for an installed, user-selected pack.
 savers=[n for n in graph.values() if n['class_type']=='SaveImage']
 bells=[n for n in graph.values() if n['class_type']=='N8VisionBellringer']
 if len(savers)!=1 or len(bells)!=1:raise ValueError('Pack needs one SaveImage and one N8VisionBellringer')
 if savers[0]['inputs'].get('filename_prefix')!=TOKENS[2] or bells[0]['inputs'].get('recovery_id')!=TOKENS[3]:raise ValueError('Pack must use owned recovery/output bindings')
 bell_id=next(k for k,v in graph.items() if v is bells[0])
 if savers[0]['inputs'].get('images')!=[bell_id,0]:raise ValueError('SaveImage must follow Bellringer')
 padding=manifest.get('padding',0)
 if not isinstance(padding,int) or not 0<=padding<=64:raise ValueError('Mask padding must be 0..64 pixels')
 return manifest,graph

def discover(root):
 packs=[]
 for path in sorted(Path(root).glob('*/pack.json')):
  try:
   manifest,_=load(root,path.parent.name);packs.append(manifest)
  except (OSError,ValueError,TypeError):continue
 return packs

def detector_name(model):
 return str(model or '').split('#')[0].replace('\\','/').split('/')[-1].removesuffix('.pt').casefold()

def matching_rows(rows,manifest):
 models={detector_name(m) for m in manifest.get('detector_models',[])}
 concepts={str(c).casefold() for c in manifest.get('manual_concepts',[])}
 result=[]
 for row in rows:
  row=dict(row)
  if float(row.get('confidence') or 0)<=0:continue
  try:g=json.loads(row['geometry']) if isinstance(row.get('geometry'),str) else row.get('geometry') or {}
  except (ValueError,TypeError):continue
  if not g.get('bbox'):continue
  if detector_name(row.get('model')) in models or (row.get('provider') in ('human-teach','human-correction') and str(row.get('concept','')).casefold() in concepts):
   # This pack promises rectangular removal even if an observation has a mask.
   row['geometry']=json.dumps({'bbox':g['bbox']});result.append(row)
 return result

def save_union_mask(size,regions,padding,destination):
 from PIL import Image,ImageDraw
 w,h=size;mask=Image.new('L',(w,h),0);draw=ImageDraw.Draw(mask);count=0
 for region in regions:
  g=json.loads(region['geometry']) if isinstance(region['geometry'],str) else region['geometry']
  box=g.get('bbox',[])
  if len(box)!=4 or not all(math.isfinite(float(v)) for v in box):raise ValueError('Invalid removal box')
  xa,ya,xb,yb=map(float,box)
  if xb<=xa or yb<=ya:raise ValueError('Removal box is empty')
  x1=max(0,math.floor(xa)-padding);y1=max(0,math.floor(ya)-padding)
  x2=min(w,math.ceil(xb)+padding);y2=min(h,math.ceil(yb)+padding)
  if x2<=x1 or y2<=y1:raise ValueError('Removal box is outside the image')
  draw.rectangle((x1,y1,x2-1,y2-1),fill=255);count+=1
 if not count:raise ValueError('No removal boxes selected')
 mask.save(destination)

def bind(graph,image,mask,prefix,recovery_id):
 values=dict(zip(TOKENS,(image,mask,prefix,recovery_id)))
 def replace(value):
  if isinstance(value,str):
   for token,text in values.items():value=value.replace(token,text)
   return value
  if isinstance(value,list):return [replace(v) for v in value]
  if isinstance(value,dict):return {k:replace(v) for k,v in value.items()}
  return value
 return replace(graph)
