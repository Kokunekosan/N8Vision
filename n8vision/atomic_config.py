"""Serialized, atomic JSON saves with bounded Windows sharing-lock retries."""
import json
import os
import tempfile
import threading
import time
from pathlib import Path

CONFIG_WRITE_LOCK=threading.RLock()


def save_json(path, value):
 payload=json.dumps(value,indent=2,sort_keys=True).encode('utf-8')
 path=Path(path)
 with CONFIG_WRITE_LOCK:
  path.parent.mkdir(parents=True,exist_ok=True)
  fd,name=tempfile.mkstemp(prefix=path.stem+'.',suffix='.tmp',dir=path.parent)
  try:
   with os.fdopen(fd,'wb') as stream:
    stream.write(payload);stream.flush();os.fsync(stream.fileno())
   delays=(.025,.05,.1,.2,.4)
   for attempt in range(len(delays)+1):
    try:os.replace(name,path);break
    except PermissionError:
     if attempt==len(delays):raise
     time.sleep(delays[attempt])
    except OSError as error:
     if getattr(error,'winerror',None) not in (5,32,33) or attempt==len(delays):raise
     time.sleep(delays[attempt])
  finally:
   try:os.unlink(name)
   except FileNotFoundError:pass
   except OSError:pass  # Do not hide the actual save error if cleanup is also locked.
