"""Source-disjoint evaluation and class admission for exact custom labels."""
import hashlib

def folds(examples):
 groups={}
 for row in examples:groups.setdefault(row['class_key'],set()).add(row['source_group'])
 eligible={key for key,value in groups.items() if len(value)>=3}
 rows=[row for row in examples if row['class_key'] in eligible]
 if len(eligible)<2:raise ValueError('Need two classes with at least three distinct source images each')
 group_classes={}
 for row in rows:group_classes.setdefault(row['source_group'],set()).add(row['class_key'])
 k=min(5,min(len(groups[key]) for key in eligible))
 for attempt in range(64):
  counts=[{key:0 for key in eligible} for _ in range(k)];sizes=[0]*k;assignment={}
  ordered=sorted(group_classes,key=lambda g:(min(len(groups[key]) for key in group_classes[g]),-len(group_classes[g]),hashlib.sha256((str(attempt)+g).encode()).hexdigest()))
  for group in ordered:
   keys=group_classes[group]
   slot=min(range(k),key=lambda i:(sum(counts[i][key]/len(groups[key]) for key in keys),sizes[i],i))
   assignment[group]=slot;sizes[slot]+=1
   for key in keys:counts[slot][key]+=1
  if all(all(len(groups[key])-counts[i][key]>=2 for key in eligible) for i in range(k)) and all(sizes):break
 else:raise ValueError('Shared source images cannot form safe cross-validation folds yet')
 splits=[]
 for fold in range(k):
  train=[i for i,row in enumerate(rows) if assignment[row['source_group']]!=fold]
  valid=[i for i,row in enumerate(rows) if assignment[row['source_group']]==fold]
  splits.append((train,valid))
 return rows,splits,sorted(set(groups)-eligible)

def admission(classes,rows,answers,previous_answers=None,previous_classes=()):
 metrics={};promoted=[];retained=[];pending=[]
 for key in classes:
  positive=[i for i,row in enumerate(rows) if row['class_key']==key]
  predicted=[i for i,a in enumerate(answers) if a['accepted'] and a['class_key']==key]
  tp=sum(rows[i]['class_key']==key for i in predicted);fp=len(predicted)-tp
  precision=tp/len(predicted) if predicted else 0.;recall=tp/len(positive)
  reasons=[]
  if precision<.8:reasons.append(f'accepted precision {precision:.1%} <80% ({fp} false positives)')
  if recall<.5:reasons.append(f'accepted recall {recall:.1%} <50%')
  baseline=None
  if previous_answers is not None and key in previous_classes:
   old_tp=sum(previous_answers[i]['accepted'] and previous_answers[i]['class_key']==key for i in positive)
   old_pred=[i for i,a in enumerate(previous_answers) if a['accepted'] and a['class_key']==key]
   old_precision=sum(rows[i]['class_key']==key for i in old_pred)/len(old_pred) if old_pred else 0.
   baseline={'precision':old_precision,'recall':old_tp/len(positive)}
   if precision<baseline['precision'] or recall<baseline['recall']:reasons.append('candidate regresses versus active class; previous head retained')
  sources=len({rows[i]['source_group'] for i in positive})
  metrics[key]={'precision':precision,'recall':recall,'true_positive':tp,'false_positive':fp,'validation_examples':len(positive),'source_images':sources,'reasons':reasons,'baseline_retest':baseline,'status':'retained' if reasons and key in previous_classes else 'pending' if reasons else 'promoted'}
  (retained if reasons and key in previous_classes else pending if reasons else promoted).append(key)
 return metrics,promoted,retained,pending

def diagnostics(result):
 names=dict(zip(result['classes'],result['labels']));name=lambda k:names.get(k,k)
 lines=['Classes evaluated: '+', '.join(name(k) for k in result['classes'])]
 v=result['validation'];lines.append(f'Source-disjoint {v["folds"]}-fold validation: {len(v["checks"])} held-out predictions, overall accepted accuracy {v["accuracy"]:.1%} (descriptive; admission is per class).')
 lines.append('Admission requires >=80% accepted precision and >=50% accepted recall per class. Existing heads are checked by replay; their replay results are not independent held-out validation.')
 for key,m in v['class_metrics'].items():
  lines.append(f'{name(key)}: {m["status"]}; precision {m["precision"]:.1%}, recall {m["recall"]:.1%}; {m["true_positive"]}/{m["validation_examples"]} correct accepted, {m["false_positive"]} false positives; {m["source_images"]} sources'+(' — '+'; '.join(m['reasons']) if m['reasons'] else '')+(' (very small evaluation set)' if m['source_images']<10 else ''))
  errors={}
  for check in v['checks']:
   if check['expected']!=key or check['correct']:continue
   prediction=check['prediction'];reason='confused with '+name(prediction['class_key']) if prediction['accepted'] else 'abstained: '+', '.join(prediction.get('rejection_reasons',[]))
   errors[reason]=errors.get(reason,0)+1
  for reason,count in errors.items():lines.append(f'  {name(key)}: {count} {reason}')
 lines.append('Class updates admitted: '+(', '.join(name(k) for k in result['promoted_classes']) or 'none'))
 if result.get('retained_classes'):lines.append('Existing heads retained: '+', '.join(name(k) for k in result['retained_classes']))
 if result.get('pending_classes'):lines.append('Needs more teaching: '+', '.join(name(k) for k in result['pending_classes']))
 lines.append('Probabilities are model scores, not calibrated certainty. Exact labels remain separate; no ancestry is inferred from label text.')
 return lines
