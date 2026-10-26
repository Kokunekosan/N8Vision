"""Carry source text through cleanup without re-encoding output pixels."""
import json
import os
import struct
import tempfile
import zlib
from pathlib import Path
from PIL import Image
from PIL.PngImagePlugin import PngInfo


def snapshot(path):
 with Image.open(path) as image:
  image.load()
  return {key:value for key,value in image.info.items() if isinstance(value,str)}


def restore(path, original, operation):
 path=Path(path)
 data=path.read_bytes()
 if not data.startswith(b'\x89PNG\r\n\x1a\n'):
  raise ValueError('Cleanup metadata preservation requires PNG output')
 chunks=[];offset=8;ended=False
 while offset<len(data):
  if offset+12>len(data):raise ValueError('Truncated PNG chunk')
  size=struct.unpack('>I',data[offset:offset+4])[0];end=offset+12+size
  if end>len(data):raise ValueError('Truncated PNG payload')
  kind=data[offset+4:offset+8];body=data[offset+8:end-4]
  if zlib.crc32(kind+body)&0xffffffff != struct.unpack('>I',data[end-4:end])[0]:raise ValueError('Invalid PNG checksum')
  chunks.append((kind,data[offset:end]));offset=end
  if kind==b'IEND':ended=True;break
 if not ended:raise ValueError('Missing PNG end')
 cleanup=snapshot(path)
 info=PngInfo()
 for key,value in original.items():info.add_itxt(key,value)
 note='n8vision_cleanup'
 while note in original:note+='_' 
 info.add_itxt(note,json.dumps({'operation':operation,'output_text':cleanup},ensure_ascii=False))
 extra=[]
 for kind,body,*_ in info.chunks:
  extra.append(struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff))
 result=bytearray(data[:8])
 for kind,raw in chunks:
  if kind==b'IEND':result.extend(b''.join(extra))
  if kind not in {b'tEXt',b'zTXt',b'iTXt'}:result.extend(raw)
 fd,tmp=tempfile.mkstemp(prefix=path.name+'.metadata-',dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as stream:stream.write(result);stream.flush();os.fsync(stream.fileno())
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
