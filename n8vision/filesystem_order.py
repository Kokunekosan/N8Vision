"""Stable directory-grouped natural order, independent of set/chunk history."""
import re

def natural(value):
 return tuple((0,int(piece)) if piece.isdecimal() else (1,piece.casefold()) for piece in re.split(r'(\d+)',value) if piece)

def filesystem_key(path):
 raw=str(path).replace('\\','/');parts=raw.rstrip('/').split('/')
 return (tuple(natural(part) for part in parts[:-1]),natural(parts[-1]),raw.casefold(),raw)

def ordered_paths(paths):
 return sorted(paths,key=filesystem_key)


def walk_images(root,recursive,extensions,on_directory=None):
 """Yield ordered folders incrementally; never inventory the whole tree first."""
 import os
 from pathlib import Path
 pending=[Path(root)]
 while pending:
  folder=pending.pop()
  try:
   stamp=folder.stat().st_mtime_ns
   with os.scandir(folder) as entries:
    files=[];children=[]
    for entry in entries:
     if entry.is_dir(follow_symlinks=False):
      if recursive and entry.name not in ('.N8VisionCache','.N8VisionExport'):children.append(Path(entry.path))
     elif Path(entry.name).suffix.lower() in extensions and entry.is_file(follow_symlinks=False):files.append(entry.path)
   for raw in sorted(files,key=filesystem_key):yield Path(raw)
   if on_directory:on_directory(str(folder),stamp)
   pending.extend(sorted(children,key=lambda p:(natural(p.name),str(p).casefold(),str(p)),reverse=True))
  except OSError:continue
