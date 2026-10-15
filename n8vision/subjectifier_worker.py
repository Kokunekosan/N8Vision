"""Optional pretrained object/part runner, isolated from Vision's web process."""
import argparse,json,os,sys,time
from pathlib import Path

def run(root,engine,paths,output):
 root=Path(root).resolve();repo=root/('PartGLEE' if engine=='partglee' else 'LangHOPS')
 sys.path[:0]=[str(root/'legacy'),str(root/'deps'),str(repo),str(repo/'projects/PartGLEE')];os.chdir(repo)
 os.environ['DETECTRON2_DATASETS']=str(repo/'datasets')
 import torch,numpy as np
 if not torch.cuda.is_available():raise RuntimeError('This reconstruction backend currently requires an NVIDIA CUDA GPU')
 import torch.nn.functional as F
 from PIL import Image,ImageOps
 from detectron2.config import get_cfg
 from detectron2.projects.partglee import add_partglee_config,PartGLEE
 from transformers.utils import logging
 logging.set_verbosity_error()
 cfg=get_cfg();add_partglee_config(cfg)
 config='projects/PartGLEE/configs/Inference/RN50/paco.yaml' if engine=='partglee' else 'projects/PartGLEE/configs/Training/Joint-Training-Swin-L_LLM.yaml'
 cfg.merge_from_file(config);cfg.MODEL.TEXT.ARCH='clip_teacher';cfg.MODEL.DEVICE='cuda'
 cfg.MODEL.WEIGHTS=str(root/'weights'/('PartGLEE-RN50.pth' if engine=='partglee' else 'LangHOPS-full.pth'))
 if not Path(cfg.MODEL.WEIGHTS).is_file():raise RuntimeError('Pretrained checkpoint has not finished downloading')
 state=torch.load(cfg.MODEL.WEIGHTS,map_location='cpu',weights_only=True,mmap=True);state=state.get('model',state)
 query_position=state.get('partglee.obj_queries_pos.weight')
 if query_position is not None:cfg.MODEL.MaskDINO.NUM_OBJECT_QUERIES=query_position.shape[0]
 if engine=='langhops':
  # Published checkpoint architecture must match; unrelated selected chat models
  # cannot replace this trainable parser's internal language encoder.
  if any('vision_tower' in key for key in state):
   cfg.MODEL.LLM.LLM_TYPE='google/paligemma2-3b-pt-448';cfg.MODEL.LLM.HIDDEN_SIZE=2304;cfg.MODEL.LLM.VLM.IS_VLM=True
  cfg.MODEL.LLM.USE_LLM=True;cfg.MODEL.MaskDINO.Q_FORMER=False
  cfg.MODEL.MaskDINO.TOPK_OBJECT_QUERIES=30
  cfg.MODEL.LLM.PART_QUERY_MODE='clip_query';cfg.MODEL.LLM.PART_CLS_EMBED='learnable'
 cfg.freeze()
 from transformers.modeling_utils import no_init_weights
 with no_init_weights():model=PartGLEE(cfg).eval()
 if engine=='langhops':model.partglee.llm_model.half()
 model.cuda();expected=model.state_dict()
 state={key.replace('.text_model.','.') if key.replace('.text_model.','.') in expected else key:value for key,value in state.items()}
 missing,unexpected=model.load_state_dict(state,strict=False)
 # Old CLIP registers position_ids as a buffer; newer versions derive it.
 unexpected=[key for key in unexpected if not key.endswith('.position_ids')]
 if missing or unexpected:raise RuntimeError('Checkpoint mismatch: '+json.dumps({'missing':missing[:20],'unexpected':unexpected[:20]}))
 print('Pretrained checkpoint matched completely',flush=True)
 del state
 objects=['person','woman','man','robot','dog','cat','horse','animal','car','motorcycle','bicycle','vehicle','food','object']
 parts=['head','face','torso','arm','forearm','hand','leg','foot','hair','ear','tail','wing','wheel','door','handlebar','mechanical limb']
 core=model.partglee;core.test_topk_per_image['custom']=60;core.test_object_inst_num['custom']=50;core.test_part_inst_num['custom']=10
 trace={}
 def object_hook(module,args,result):trace['objects']=result[0]
 def part_hook(module,args,result):trace['parts']=result[0]
 handles=[core.object_predictor.register_forward_hook(object_hook),core.part_predictor.register_forward_hook(part_hook)]
 if engine=='langhops':
  core.cat_hierachies['custom']={'id':{i:list(range(len(objects),len(objects)+len(parts))) for i in range(len(objects))}}
  original_prepare=core.prepare_multimodal_llm_input
  def prepare(*args,**kwargs):
   result=original_prepare(*args,**kwargs);trace['part_ids']=result.get('part_ids_list');return result
  core.prepare_multimodal_llm_input=prepare
 def geometry(mask):
  ys,xs=np.where(mask)
  if not len(xs):return None
  a,b,c,d=int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1;crop=mask[b:d,a:c]
  flat=crop.ravel();edges=np.diff(np.concatenate(([False],flat,[False])).astype('int8'));starts=np.flatnonzero(edges==1);ends=np.flatnonzero(edges==-1)
  return {'bbox':[a,b,c,d],'mask_size':[c-a,d-b],'mask_rle':[int(v) for pair in zip(starts,ends-starts) for v in pair]}
 results=[]
 for path in paths:
  before=Path(path).stat();trace.clear()
  with Image.open(path) as raw:image=ImageOps.exif_transpose(raw).convert('RGB')
  original_size=image.size;image.thumbnail((1024,1024));array=np.asarray(image).copy();h,w=array.shape[:2]
  tensor=torch.from_numpy(array).permute(2,0,1).float().cuda()
  batch=[{'image':tensor,'height':h,'width':w,'custom_object_categories':objects,'custom_part_categories':parts}]
  with torch.inference_mode(),torch.autocast('cuda',enabled=engine=='langhops',dtype=torch.float16):
   padded=model.preprocess_image(batch,'custom').tensor.shape[-2:]
   # Run real pretrained inference; hooks retain raw per-query results before
   # the public evaluator flattens and discards ownership provenance.
   model(batch)
  after=Path(path).stat()
  if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError('Source changed during reconstruction')
  obj=trace['objects'];part=trace['parts'];topk=core.topk_object_queries_num
  parent_queries=torch.topk(obj['pred_logits'].max(-1)[0],topk,1)[1][0].tolist()
  if engine=='partglee':
   # Q-Former returns [part_slot, object_query, hidden]; upstream directly
   # reshapes it. Preserve that actual ordering, not assumed contiguous groups.
   parent_map=[parent_queries[i%topk] for i in range(part['pred_masks'].shape[1])]
  else:
   groups=trace.get('part_ids')
   if not groups:raise RuntimeError('LangHOPS did not expose its per-object part-query groups')
   parent_map=[parent_queries[i] for i,ids in enumerate(groups[0]) for _ in ids]
   if len(parent_map)!=part['pred_masks'].shape[1]:raise RuntimeError('LangHOPS query ownership shape mismatch')
  def decoded(logits):
   mask=F.interpolate(logits[None,None].float(),size=padded,mode='bilinear',align_corners=False)[0,0,:h,:w]
   mask=F.interpolate(mask[None,None],size=(original_size[1],original_size[0]),mode='bilinear',align_corners=False)[0,0]
   return (mask>0).cpu().numpy()
  subjects=[];query_owner={}
  object_scores,object_labels=obj['pred_logits'][0].sigmoid().max(-1)
  for query in parent_queries:
   score=float(object_scores[query]);label=objects[int(object_labels[query])]
   if score<.30:continue
   mask=decoded(obj['pred_masks'][0,query]);g=geometry(mask)
   if g is None or mask.sum()<16:continue
   # Collapse near-identical object queries, preserving distinct touching bodies.
   match=next((i for i,s in enumerate(subjects) if np.logical_and(mask,s['mask']).sum()/max(1,np.logical_or(mask,s['mask']).sum())>=.85),None)
   if match is not None:query_owner[query]=match;continue
   query_owner[query]=len(subjects);subjects.append({'query':query,'concept':label if score>=.65 else 'unidentified subject','proposed_concept':label,'confidence':score,'geometry':g,'mask':mask,'parts':[]})
  candidates=[]
  part_scores,part_labels=part['pred_logits'][0].sigmoid().max(-1)
  for query in torch.argsort(part_scores,descending=True).tolist():
   score=float(part_scores[query])
   if score<.20:break
   owner=query_owner.get(parent_map[query])
   if owner is None:continue
   mask=decoded(part['pred_masks'][0,query]);g=geometry(mask)
   if g is None or mask.sum()<16:continue
   label=parts[int(part_labels[query])]
   duplicate=next((item for item in candidates if np.logical_and(mask,item['mask']).sum()/max(1,np.logical_or(mask,item['mask']).sum())>=.85),None)
   if duplicate:
    if duplicate['owner']!=owner:duplicate['conflict']=True
    continue
   fractions=[float(np.logical_and(mask,s['mask']).sum()/mask.sum()) for s in subjects]
   conflict=any(i!=owner and fraction>.6 and fraction>fractions[owner]+.15 for i,fraction in enumerate(fractions))
   candidates.append({'concept':label,'confidence':score,'geometry':g,'mask':mask,'owner':owner,'query':query,'conflict':conflict})
  unresolved=[]
  for item in candidates:
   owner=item.pop('owner');mask=item.pop('mask')
   if item.pop('conflict'):item['suggested_owner']=owner;unresolved.append(item)
   else:subjects[owner]['parts'].append(item);subjects[owner]['mask']|=mask
  for subject in subjects:
   subject['base_geometry']=subject['geometry'];subject['geometry']=geometry(subject.pop('mask'))
  results.append({'path':path,'source_signature':[before.st_size,before.st_mtime_ns],'source_size':list(original_size),'subjects':subjects,'unresolved_parts':unresolved,'backend':engine,'ownership_status':'draft','part_proposal_minimum':.20,'best_part_score':float(part_scores.max())})
 for handle in handles:handle.remove()
 Path(output).write_text(json.dumps({'images':results,'backend':engine,'checkpoint_matched':True}),encoding='utf-8')

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--engine',choices=['partglee','langhops'],required=True);parser.add_argument('--request',required=True);parser.add_argument('--output',required=True)
 args=parser.parse_args();request=json.loads(Path(args.request).read_text());run(args.root,args.engine,request['paths'],args.output)
