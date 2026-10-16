"""Stable directory-grouped natural order, independent of set/chunk history."""
import re

def natural(value):
 return tuple((0,int(piece)) if piece.isdecimal() else (1,piece.casefold()) for piece in re.split(r'(\d+)',value) if piece)

def filesystem_key(path):
 raw=str(path).replace('\\','/');parts=raw.rstrip('/').split('/')
 return (tuple(natural(part) for part in parts[:-1]),natural(parts[-1]),raw.casefold(),raw)

def ordered_paths(paths):
 return sorted(paths,key=filesystem_key)
