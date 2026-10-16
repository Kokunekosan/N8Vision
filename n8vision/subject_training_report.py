"""Readable class-level diagnostics; validation policy remains in the worker."""
def describe_training(result):
 validation=result.get('validation') or {}
 names=dict(zip(result.get('classes',[]),result.get('labels',[])))
 name=lambda key:names.get(key,key)
 lines=['Classes trained: '+(', '.join(name(k) for k in result.get('classes',[])) or 'not recorded')]
 accuracy=validation.get('accuracy')
 reasons=[]
 if accuracy is not None:
  lines.append(f'Validation: {accuracy:.1%} accepted and correctly labeled; required overall >=80%, each class >=50%, no regression on active classes.')
  if accuracy<.8:reasons.append(f'overall accepted accuracy {accuracy:.1%} is below 80%')
 for key,score in validation.get('per_class',{}).items():
  checks=[c for c in validation.get('checks',[]) if c.get('expected')==key]
  failures=[c for c in checks if not c.get('correct')]
  counts={}
  for check in failures:
   prediction=check.get('prediction') or {}
   if not prediction.get('accepted'):
    gates=prediction.get('rejection_reasons') or ['confidence, margin or visual-support gate failed']
    reason='abstained: '+', '.join(gates)
   else:reason='confused with '+name(prediction.get('class_key','unknown'))
   counts[reason]=counts.get(reason,0)+1
  detail='; '.join(f'{count} {reason}' for reason,count in sorted(counts.items()))
  lines.append(f'{name(key)}: {score:.1%}'+(f' ({len(checks)-len(failures)}/{len(checks)} accepted correct)' if checks else '')+(' — '+detail if detail else ''))
  if score<.5:reasons.append(f'{name(key)} accepted accuracy {score:.1%} is below 50%')
 baseline=validation.get('baseline') or {}
 for key,old in baseline.get('old_per_class',{}).items():
  new=baseline.get('candidate_per_class',{}).get(key)
  if new is not None and new<old:reasons.append(f'{name(key)} regressed from {old:.1%} to {new:.1%} versus active model')
 if not result.get('passed'):
  lines.append('Rejected because: '+('; '.join(reasons) or 'validation did not pass; see detailed report'))
  lines.append('Active model retained.' if result.get('had_active_model',True) else 'No active model exists; candidate was not activated.')
 else:lines.append('Validation passed; class model activated.' if result.get('activated') else 'Validation passed.')
 if result.get('pending_classes'):lines.append('Deferred (fewer than 3 distinct source images): '+', '.join(name(k) for k in result['pending_classes']))
 return lines
