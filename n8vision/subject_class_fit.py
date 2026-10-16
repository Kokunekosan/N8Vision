"""Cross-validated candidate training; never publish weights to the live archive."""
import torch
try:
 from .subject_class_heads import fit,predict,combine
 from .subject_class_validation import folds,admission,diagnostics
except ImportError:
 from subject_class_heads import fit,predict,combine
 from subject_class_validation import folds,admission,diagnostics

def train_features(examples,x,signature,previous=None):
 rows,splits,pending=folds(examples)
 lookup={row['id']:i for i,row in enumerate(examples)};x=x[[lookup[row['id']] for row in rows]]
 classes=sorted({row['class_key'] for row in rows});labels=[next(row['label'] for row in reversed(rows) if row['class_key']==key) for key in classes]
 target=torch.tensor([classes.index(row['class_key']) for row in rows]);answers=[None]*len(rows);fold_models=[]
 for train,valid in splits:
  branch=fit(x[train],target[train],classes,[rows[i] for i in train]);branch['labels']=labels
  checkpoint=combine(None,branch,classes,signature,dict(zip(classes,labels)))
  predictions=predict(x[valid],checkpoint)
  for i,a in zip(valid,predictions):answers[i]=a
  fold_models.append((branch,valid))
 previous_answers=predict(x,previous) if previous else None
 metrics,promoted,_,weak=admission(classes,rows,answers,previous_answers,previous['classes'] if previous else ())
 # Check the actual retained-head routing too. Only remove admissions, never tune
 # scores/cutoffs against held-out rows. Legacy-head results are replay checks.
 for _ in range(len(classes)+1):
  if not promoted:break
  routed=[None]*len(rows)
  for branch,valid in fold_models:
   checkpoint=combine(previous,branch,promoted,signature,dict(zip(classes,labels)))
   for i,a in zip(valid,predict(x[valid],checkpoint)):routed[i]=a
  routed_metrics,_,_,_=admission(classes,rows,routed,previous_answers,previous['classes'] if previous else ())
  keep=[key for key in promoted if not routed_metrics[key]['reasons']]
  for key in promoted:metrics[key]=routed_metrics[key]
  if keep==promoted:break
  promoted=keep
 retained=[key for key in (previous['classes'] if previous else []) if key not in promoted]
 for key in classes:
  if key not in promoted:
   metrics[key]['status']='retained' if key in retained else 'pending'
   if not metrics[key]['reasons']:metrics[key]['reasons']=['not admitted by composed recognition validation']
 branch=fit(x,target,classes,rows);branch['labels']=labels
 checkpoint=combine(previous,branch,promoted,signature,dict(zip(classes,labels)))
 correct=[a['accepted'] and a['class_key']==row['class_key'] for a,row in zip(answers,rows)]
 checks=[{'example_id':row['id'],'expected':row['class_key'],'prediction':a,'correct':good} for row,a,good in zip(rows,answers,correct)]
 result={'passed':bool(promoted),'partial_activation':bool(promoted) and len(promoted)<len(classes),'weights_updated':True,'classes':classes,'labels':labels,'active_classes':checkpoint['classes'],'promoted_classes':promoted,'retained_classes':retained,'pending_classes':sorted(set(pending)|{key for key in classes if key not in promoted and key not in retained}),'encoder_sha256':signature,'loss_before':branch['loss_before'],'loss_after':branch['loss_after'],'trained_examples':[row['id'] for row in rows],'activated_examples':[row['id'] for row in rows if row['class_key'] in promoted],'validation_examples':[row['id'] for row in rows],'training_examples':[row['id'] for row in rows],'validation':{'method':'source-group cross-validation; retained heads checked by replay, not independent validation','folds':len(splits),'accuracy':sum(correct)/len(correct),'per_class':{key:m['recall'] for key,m in metrics.items()},'class_metrics':metrics,'checks':checks,'source_groups_disjoint':all(not ({rows[i]['source_group'] for i in train}&{rows[i]['source_group'] for i in valid}) for train,valid in splits)},'scope':'exact-label visual class heads; encoder, LM and part-parser weights unchanged'}
 result['diagnostics']=diagnostics(result)
 return checkpoint,result
