"""Explicit pixel identity for owned output recovery, without hashing images."""
import json
import os
from pathlib import Path
import threading
import uuid

class PixelRevisions:
 def __init__(self,path):
  self.path=Path(path);self.lock=threading.RLock()
  try:
   value=json.loads(self.path.read_text(encoding='utf-8'))
   self.values=value if isinstance(value,dict) else {}
  except (OSError,ValueError):self.values={}

 @staticmethod
 def key(path):return os.path.normcase(os.path.abspath(path))

 def get(self,path):
  with self.lock:return self.values.get(self.key(path),'')

 def bump(self,path):
  with self.lock:
   revision=uuid.uuid4().hex;values={**self.values,self.key(path):revision}
   self.path.parent.mkdir(parents=True,exist_ok=True)
   temporary=self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.tmp')
   try:
    with temporary.open('w',encoding='utf-8') as handle:
     json.dump(values,handle,separators=(',',':'));handle.flush();os.fsync(handle.fileno())
    os.replace(temporary,self.path)
   finally:temporary.unlink(missing_ok=True)
   self.values=values
   return revision
