"""Directory-only snapshots: stat known nodes, enumerate only changed nodes."""
import os,threading,hashlib
from pathlib import Path

class DirectoryTree:
 def __init__(self):self.roots={};self.lock=threading.Lock()
 def snapshot(self,root):
  root=Path(root);key=str(root).casefold()
  with self.lock:
   if key not in self.roots:
    if len(self.roots)>=16:self.roots.pop(next(iter(self.roots)))
    self.roots[key]={}
   cache=self.roots[key];seen=set();stack=[str(root)];paths=[];incomplete=False
   while stack:
    path=stack.pop()
    if path in seen:continue
    seen.add(path)
    try:
     st=os.stat(path);signature=(st.st_dev,st.st_ino,st.st_mtime_ns,st.st_ctime_ns)
     previous=cache.get(path)
     if previous and previous[0]==signature:children=previous[1]
     else:
      with os.scandir(path) as entries:
       children=sorted((e.path for e in entries if e.is_dir(follow_symlinks=False) and not e.is_symlink() and not (hasattr(e,'is_junction') and e.is_junction())),key=str.casefold)
      cache[path]=(signature,children)
    except (FileNotFoundError,NotADirectoryError):cache.pop(path,None);continue
    except (PermissionError,OSError):incomplete=True;continue
    if path!=str(root):paths.append(path)
    stack.extend(children)
   for path in list(cache):
    if path not in seen:del cache[path]
   paths.sort(key=str.casefold)
   revision=hashlib.sha256('\0'.join(paths).encode()).hexdigest()
   return {'root':str(root),'paths':paths,'revision':revision,'incomplete':incomplete}
