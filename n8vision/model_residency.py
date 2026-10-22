"""Process-local model leases and two-minute idle eviction."""
import threading,time,functools,gc,sys,logging,inspect
from collections.abc import MutableMapping
from contextlib import contextmanager

REGISTRY=[]
LOG=logging.getLogger('n8vision')

class ModelCache(MutableMapping):
 def __init__(self,name,clock=time.monotonic):
  self.name=name;self.clock=clock;self.data={};self.used={};self.pins={};self.handoff_pending=set();self.lock=threading.RLock();self.local=threading.local();REGISTRY.append(self)
 def _touch(self,key):
  self.used[key]=self.clock();scope=getattr(self.local,'scope',None)
  if scope is not None and key not in scope:scope.add(key);self.pins[key]=self.pins.get(key,0)+1
 def __getitem__(self,key):
  with self.lock:value=self.data[key];self._touch(key);return value
 def __setitem__(self,key,value):
  with self.lock:self.data[key]=value;self._touch(key)
 def __delitem__(self,key):
  with self.lock:del self.data[key];self.used.pop(key,None)
 def __iter__(self):
  with self.lock:return iter(list(self.data))
 def __len__(self):
  with self.lock:return len(self.data)
 @contextmanager
 def lease(self):
  if getattr(self.local,'scope',None) is not None:
   yield;return
  scope=set();self.local.scope=scope
  try:yield
  finally:
   with self.lock:
    for key in scope:self.pins[key]-=1;self.used[key]=self.clock()
    handoff=any(key in self.handoff_pending and not self.pins[key] for key in scope)
   self.local.scope=None
   if handoff:release_models()
 def use(self,fn):
  @functools.wraps(fn)
  def wrapped(*args,**kwargs):
   with self.lease():return fn(*args,**kwargs)
  wrapped.__signature__=inspect.signature(fn,eval_str=True)
  return wrapped
 def evict(self,force=False):
  removed=[]
  with self.lock:
   for key in list(self.data):
    if self.pins.get(key,0):
     if force:self.handoff_pending.add(key)
     continue
    if not force and key not in self.handoff_pending and self.clock()-self.used[key]<120:continue
    value=self.data.pop(key);self.used.pop(key,None);self.pins.pop(key,None)
    self.handoff_pending.discard(key)
    pool=getattr(value,'_n8_brisque_pool',None)
    if pool:pool.shutdown(wait=False)
    removed.append(str(key));del value
  if removed:LOG.info('Released idle Vision models (%s): %s',self.name,', '.join(removed))
  return removed

def release_models(force=False):
 removed=[]
 for cache in list(REGISTRY):removed.extend(cache.evict(force))
 if removed:
  gc.collect();torch=sys.modules.get('torch')
  if torch is not None and torch.cuda.is_available():torch.cuda.empty_cache()
 return removed

def start_reaper():
 def loop():
  while True:
   time.sleep(10)
   try:release_models()
   except Exception:LOG.exception('Vision idle model cleanup failed')
 threading.Thread(target=loop,name='n8-idle-model-release',daemon=True).start()
