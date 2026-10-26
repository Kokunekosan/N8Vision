"""Separate negative evidence from intentional observation deletion."""
import json

def negative(row):
 try:g=json.loads(row['geometry'] or '{}') if isinstance(row.get('geometry'),str) else row.get('geometry') or {}
 except (ValueError,TypeError):return False
 return float(row.get('confidence') or 0)<0 and g.get('_n8_review')=='negative'

def reject_or_delete(c,ref):
 action=ref['action']
 if action not in ('reject','delete'):raise ValueError('Expected reject or delete')
 key=(ref['path'],ref['concept'],ref['provider'],ref['model'],ref['kind'],ref.get('geometry'))
 where='path=? AND concept=? AND provider=? AND model=? AND kind=? AND geometry IS ?'
 row=c.execute('SELECT confidence FROM observations WHERE '+where,key).fetchone()
 if row is None:raise LookupError('Observation not found')
 c.execute('CREATE TABLE IF NOT EXISTS corrections(id INTEGER PRIMARY KEY AUTOINCREMENT,path TEXT NOT NULL,original_concept TEXT,original_provider TEXT,original_model TEXT,original_kind TEXT,geometry TEXT,action TEXT NOT NULL,corrected_concept TEXT,created REAL NOT NULL DEFAULT (unixepoch()))')
 geometry=ref.get('geometry')
 if action=='reject':
  g=json.loads(geometry or '{}')
  if not isinstance(g,dict):raise ValueError('Detection geometry must be an object')
  g['_n8_review']='negative';geometry=json.dumps(g,sort_keys=True,separators=(',',':'))
  c.execute('UPDATE observations SET confidence=?,geometry=?,updated=unixepoch() WHERE '+where,(-max(abs(float(row['confidence'])),1e-9),geometry,*key))
 else:
  c.execute('DELETE FROM observations WHERE '+where,key)
  # Deleting a previously rejected observation also withdraws that negative
  # lesson. The delete audit entry is not a training correction.
  c.execute('DELETE FROM corrections WHERE path=? AND original_concept=? AND original_provider=? AND original_model=? AND original_kind=? AND geometry IS ? AND action=?',(*key,'reject'))
 c.execute('INSERT INTO corrections(path,original_concept,original_provider,original_model,original_kind,geometry,action,corrected_concept) VALUES(?,?,?,?,?,?,?,NULL)',(*key[:5],geometry,action))
 return {'ok':True,'action':action,'corrected_concept':None}
