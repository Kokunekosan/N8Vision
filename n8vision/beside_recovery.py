"""Save a sibling without overwriting or relocating the donor."""
import os,shutil
from pathlib import Path

def save_beside(fresh,source,method):
 fresh=Path(fresh);source=Path(source)
 if not source.is_file():raise RuntimeError('Beside donor no longer exists; output left in Comfy')
 if fresh.resolve()==source.resolve() or os.path.samefile(fresh,source):raise RuntimeError('Refusing Beside recovery: reported output is the donor')
 before=source.stat();iteration=1
 while True:
  suffix='' if iteration==1 else f'_{iteration}'
  target=source.with_name(f'{source.stem}_{method}{suffix}{fresh.suffix or source.suffix}')
  try:handle=target.open('xb')
  except FileExistsError:iteration+=1;continue
  break
 try:
  with handle, fresh.open('rb') as incoming:shutil.copyfileobj(incoming,handle)
  after=source.stat()
  if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):raise RuntimeError('Beside donor changed during recovery')
 except BaseException:
  target.unlink(missing_ok=True);raise
 # Only the independent staging output may be removed, never the donor.
 try:fresh.unlink()
 except OSError:pass
 return target,iteration
