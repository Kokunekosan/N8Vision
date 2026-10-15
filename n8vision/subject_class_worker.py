"""Actual supervised class-head training on frozen pretrained visual features."""
import argparse,hashlib,json,os,sys,uuid
from pathlib import Path

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as source:
  for chunk in iter(lambda:source.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def split_examples(examples):
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
 def load_head(path):
  checkpoint=torch.load(path,map_location='cpu',weights_only=True)
  if checkpoint.get('schema')!=1 or checkpoint.get('encoder_sha256')!=signature:raise ValueError('Classifier requires the exact encoder it was trained with')
  head=torch.nn.Linear(checkpoint['dimension'],len(checkpoint['classes']));head.load_state_dict(checkpoint['weights']);head.eval()
  return checkpoint,head
 def predictions(x,checkpoint,head):
  with torch.no_grad():probabilities=head(x).softmax(-1);scores,indices=probabilities.max(-1)
  answers=[]
  for i,(score,index) in enumerate(zip(scores.tolist(),indices.tolist())):
   cosine=float(x[i]@checkpoint['centroids'][index]);second=float(probabilities[i].topk(2).values[1])
   accepted=score>=.65 and score-second>=.15 and cosine>=checkpoint['minimum_cosine'][index]
   answers.append({'class_key':checkpoint['classes'][index],'label':checkpoint['labels'][index],'score':score,'support_similarity':cosine,'accepted':accepted,'status':'draft' if accepted else 'unidentified'})
  return answers
 if request['mode']=='predict':
  checkpoint,head=load_head(request['checkpoint']);x=features(request['images']);answers=predictions(x,checkpoint,head)
  return {'predictions':answers,'encoder_sha256':signature}
 rows,train_indices,valid_indices,pending=split_examples(request['examples']);classes=sorted({row['class_key'] for row in rows});labels=[next(row['label'] for row in reversed(rows) if row['class_key']==key) for key in classes]
 x=features(rows);target=torch.tensor([classes.index(row['class_key']) for row in rows]);train_x=x[train_indices];train_y=target[train_indices]
 head=torch.nn.Linear(x.shape[1],len(classes));previous=request.get('previous');old=old_head=None
 if previous:
  old,old_head=load_head(previous)
  if not set(old['classes'])<=set(classes):raise ValueError('An active class lacks enough current verified examples; refusing to forget it')
  with torch.no_grad():
   for index,key in enumerate(old['classes']):
    target_index=classes.index(key);head.weight[target_index].copy_(old_head.weight[index]);head.bias[target_index].copy_(old_head.bias[index])
 optimizer=torch.optim.AdamW(head.parameters(),lr=.03,weight_decay=.01)
 counts=torch.bincount(train_y,minlength=len(classes)).float();class_weight=counts.sum()/(len(classes)*counts)
 losses=[]
 for step in range(250):
  optimizer.zero_grad();loss=torch.nn.functional.cross_entropy(head(train_x),train_y,weight=class_weight);loss.backward();optimizer.step();losses.append(float(loss.detach()))
 centroids=torch.stack([torch.nn.functional.normalize(train_x[train_y==i].mean(0),dim=0) for i in range(len(classes))])
 minima=[max(.2,min(.95,float((train_x[train_y==i]@centroids[i]).min())-.05)) for i in range(len(classes))]
 checkpoint={'schema':1,'encoder_sha256':signature,'dimension':x.shape[1],'classes':classes,'labels':labels,'weights':head.state_dict(),'centroids':centroids,'minimum_cosine':minima}
 answers=predictions(x[valid_indices],checkpoint,head);truth=target[valid_indices].tolist();correct=[answer['accepted'] and answer['class_key']==classes[index] for answer,index in zip(answers,truth)]
 accuracy=sum(correct)/len(correct);per_class={key:sum(good for good,index in zip(correct,truth) if classes[index]==key)/sum(classes[index]==key for index in truth) for key in classes}
 baseline=None
 if previous:
  old_indices=[index for index in valid_indices if rows[index]['class_key'] in old['classes']]
  old_answers=predictions(x[old_indices],old,old_head);new_answers=predictions(x[old_indices],checkpoint,head)
  old_correct=[answer['accepted'] and answer['class_key']==rows[index]['class_key'] for answer,index in zip(old_answers,old_indices)]
  new_correct=[answer['accepted'] and answer['class_key']==rows[index]['class_key'] for answer,index in zip(new_answers,old_indices)]
  old_by_class={key:sum(good for good,index in zip(old_correct,old_indices) if rows[index]['class_key']==key)/sum(rows[index]['class_key']==key for index in old_indices) for key in old['classes']}
  new_by_class={key:sum(good for good,index in zip(new_correct,old_indices) if rows[index]['class_key']==key)/sum(rows[index]['class_key']==key for index in old_indices) for key in old['classes']}
  baseline={'old_accuracy':sum(old_correct)/len(old_correct),'candidate_accuracy':sum(new_correct)/len(new_correct),'old_per_class':old_by_class,'candidate_per_class':new_by_class}
 passed=accuracy>=.8 and min(per_class.values())>=.5 and (baseline is None or all(baseline['candidate_per_class'][key]>=score for key,score in baseline['old_per_class'].items()))
 Path(request['checkpoint']).parent.mkdir(parents=True,exist_ok=True);torch.save(checkpoint,request['checkpoint'])
 checks=[{'example_id':rows[index]['id'],'expected':rows[index]['class_key'],'prediction':answer,'correct':good} for index,answer,good in zip(valid_indices,answers,correct)]
 return {'passed':passed,'weights_updated':True,'classes':classes,'labels':labels,'pending_classes':pending,'encoder_sha256':signature,'loss_before':losses[0],'loss_after':losses[-1],'training_examples':[rows[i]['id'] for i in train_indices],'validation_examples':[rows[i]['id'] for i in valid_indices],'trained_examples':[row['id'] for row in rows],'validation':{'accuracy':accuracy,'per_class':per_class,'baseline':baseline,'checks':checks,'source_groups_disjoint':not ({rows[i]['source_group'] for i in train_indices}&{rows[i]['source_group'] for i in valid_indices})},'scope':'visual class head; preferred LLM and part parser weights unchanged'}

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--request',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
 result=run(json.loads(Path(args.request).read_text()));Path(args.output).write_text(json.dumps(result,indent=2))
