"""Train small class heads; retain old heads for classes not admitted this run."""
import torch

def fit(x,target,classes,rows):
 torch.manual_seed(0)
 head=torch.nn.Linear(x.shape[1],len(classes));optimizer=torch.optim.AdamW(head.parameters(),lr=.03,weight_decay=.01)
 counts=torch.bincount(target,minlength=len(classes)).float();weights=counts.sum()/(len(classes)*counts)
 losses=[]
 for _ in range(250):
  optimizer.zero_grad();loss=torch.nn.functional.cross_entropy(head(x),target,weight=weights);loss.backward();optimizer.step();losses.append(float(loss.detach()))
 centroids=torch.stack([torch.nn.functional.normalize(x[target==i].mean(0),dim=0) for i in range(len(classes))])
 minima=[]
 for i in range(len(classes)):
  indices=[j for j in range(len(rows)) if int(target[j])==i];similarities=[]
  for j in indices:
   other=[k for k in indices if rows[k]['source_group']!=rows[j]['source_group']]
   # Source-independent nearest support, never distance to a centroid including itself.
   if other:similarities.append(float((x[j]@x[other].T).max()))
  minima.append(max(.2,min(.95,min(similarities)-.05)))
 return {'dimension':x.shape[1],'classes':classes,'weights':head.state_dict(),'support':x.detach().clone(),'support_classes':target.tolist(),'minimum_cosine':minima,'loss_before':losses[0],'loss_after':losses[-1]}

def branch_predictions(x,branch):
 head=torch.nn.Linear(branch['dimension'],len(branch['classes']));head.load_state_dict(branch['weights']);head.eval()
 with torch.no_grad():probabilities=head(x).softmax(-1);scores,indices=probabilities.max(-1)
 answers=[]
 for i,(score,index) in enumerate(zip(scores.tolist(),indices.tolist())):
  if 'support' in branch:
   support=branch['support'][torch.tensor(branch['support_classes'])==index]
   similarity=float((x[i]@support.T).max())
  else:similarity=float(x[i]@branch['centroids'][index])
  second=float(probabilities[i].topk(2).values[1]);reasons=[]
  if score<.65:reasons.append(f'model score {score:.1%} <65%')
  if score-second<.15:reasons.append(f'lead over next class {score-second:.1%} <15%')
  if similarity<branch['minimum_cosine'][index]:reasons.append(f'source-independent support {similarity:.3f} <{branch["minimum_cosine"][index]:.3f}')
  key=branch['classes'][index]
  if key not in branch.get('enabled_classes',branch['classes']):reasons.append('class is pending further teaching')
  answers.append({'class_key':key,'label':branch.get('labels',branch['classes'])[index],'score':score,'support_similarity':similarity,'accepted':not reasons,'status':'unidentified' if reasons else 'draft','rejection_reasons':reasons})
 return answers

def predict(x,checkpoint):
 if checkpoint.get('schema')==1:return branch_predictions(x,checkpoint)
 result=None
 # Existing unpromoted class heads retain precedence and their original decision rules.
 for branch in checkpoint['branches']:
  answers=branch_predictions(x,branch)
  if result is None:result=answers
  else:
   result=[old if old['accepted'] else new for old,new in zip(result,answers)]
 return result

def combine(previous,branch,promoted,signature,labels):
 branches=[]
 if previous:
  for old in previous.get('branches',[previous]):
   enabled=[key for key in old.get('enabled_classes',old['classes']) if key not in promoted]
   if enabled:branches.append({**old,'enabled_classes':enabled})
 if promoted:branches.append({**branch,'enabled_classes':list(promoted)})
 active=sorted({key for b in branches for key in b['enabled_classes']})
 all_names={key:label for b in branches for key,label in zip(b['classes'],b.get('labels',b['classes']))};all_names.update(labels)
 return {'schema':2,'encoder_sha256':signature,'classes':active,'labels':[all_names[key] for key in active],'branches':branches}
