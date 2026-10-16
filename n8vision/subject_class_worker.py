"""Actual supervised class-head training on frozen pretrained visual features."""
import argparse,hashlib,json,os,sys,uuid
from pathlib import Path

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as source:
  for chunk in iter(lambda:source.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def split_examples(examples):
 # Legacy fixture helper. Production training uses subject_class_validation.folds.
 groups={}
 for row in examples:groups.setdefault(row['class_key'],set()).add(row['source_group'])
 eligible={key for key,value in groups.items() if len(value)>=3}
 rows=[row for row in examples if row['class_key'] in eligible]
 if len(eligible)<2:raise ValueError('Need at least two confirmed classes, with three distinct source images per class (two training, one validation)')
 validation=set()
 for key in sorted(eligible):
  if groups[key]&validation:continue
  choices=sorted(groups[key],key=lambda group:hashlib.sha256(group.encode()).hexdigest())
  chosen=next((group for group in choices if all(len(groups[other]-(validation|{group}))>=2 for other in eligible)),None)
  if chosen is None:raise ValueError('Subjects sharing source images cannot form a separate validation set yet')
  validation.add(chosen)
 train=[i for i,row in enumerate(rows) if row['source_group'] not in validation];valid=[i for i,row in enumerate(rows) if row['source_group'] in validation]
 return rows,train,valid,sorted(set(groups)-eligible)

def run(request):
 parser_root=Path(request['parser_root']);sys.path[:0]=[str(parser_root/'legacy'),str(parser_root/'deps')]
 import torch
 from PIL import Image
 from transformers import CLIPModel,CLIPImageProcessor
 torch.set_num_threads(max(1,min(4,os.cpu_count() or 1)));torch.manual_seed(0)
 encoder=Path(request['encoder']);signature=hashlib.sha256(''.join(digest(encoder/name) for name in ('pytorch_model.bin','config.json','preprocessor_config.json')).encode()).hexdigest()
 model,loading=CLIPModel.from_pretrained(str(encoder),local_files_only=True,output_loading_info=True)
 missing=loading.get('missing_keys',[]);unexpected=[key for key in loading.get('unexpected_keys',[]) if not key.endswith('position_ids')]
 if missing or unexpected or loading.get('mismatched_keys'):raise ValueError('Visual encoder checkpoint does not match its architecture')
 model=model.cpu().eval()
 for parameter in model.parameters():parameter.requires_grad_(False)
 processor=CLIPImageProcessor.from_pretrained(str(encoder),local_files_only=True)
 def features(rows):
  vectors=[]
  for row in rows:
   image_path=Path(row['image'])
   if digest(image_path)!=row['crop_sha256']:raise ValueError('Frozen composite checksum changed')
   cache=Path(request['feature_cache'])/(signature+'-'+row['crop_sha256']+'.pt') if request.get('feature_cache') else None
   if cache and cache.is_file():
    cached=torch.load(cache,map_location='cpu',weights_only=True)
    if isinstance(cached,torch.Tensor) and cached.shape==(model.config.projection_dim,) and torch.isfinite(cached).all():vectors.append(cached);continue
   with Image.open(image_path) as image:inputs=processor(images=image.convert('RGB'),return_tensors='pt')
   with torch.no_grad():vector=model.get_image_features(**inputs).float()
   vector=torch.nn.functional.normalize(vector,dim=-1)[0];vectors.append(vector)
   if cache:
    cache.parent.mkdir(parents=True,exist_ok=True);temporary=cache.with_suffix('.'+uuid.uuid4().hex+'.tmp');torch.save(vector,temporary);os.replace(temporary,cache)
  return torch.stack(vectors)
 # Both legacy single-head checkpoints and class-admitted registries are readable.
 try:
  from .subject_class_heads import predict
  from .subject_class_fit import train_features
 except ImportError:
  from subject_class_heads import predict
  from subject_class_fit import train_features
 def load_checkpoint(path):
  checkpoint=torch.load(path,map_location='cpu',weights_only=True)
  if checkpoint.get('schema') not in (1,2) or checkpoint.get('encoder_sha256')!=signature:raise ValueError('Classifier requires the exact encoder it was trained with')
  return checkpoint
 if request['mode']=='predict':
  checkpoint=load_checkpoint(request['checkpoint'])
  return {'predictions':predict(features(request['images']),checkpoint),'encoder_sha256':signature}
 previous=load_checkpoint(request['previous']) if request.get('previous') else None
 checkpoint,result=train_features(request['examples'],features(request['examples']),signature,previous)
 Path(request['checkpoint']).parent.mkdir(parents=True,exist_ok=True);torch.save(checkpoint,request['checkpoint'])
 return result

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--request',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
 result=run(json.loads(Path(args.request).read_text()));Path(args.output).write_text(json.dumps(result,indent=2))
