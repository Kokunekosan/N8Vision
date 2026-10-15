"""Freeze exactly the visible composite, without its surrounding scene."""
import io
from PIL import Image,ImageDraw,ImageOps

def isolate(path,g):
 with Image.open(path) as raw:source=ImageOps.exif_transpose(raw).convert('RGB')
 box=g.get('bbox');size=g.get('mask_size');runs=g.get('mask_rle')
 if not box or len(box)!=4:raise ValueError('Subject needs a mask bounding box')
 x,y,right,bottom=map(int,box)
 if not (0<=x<right<=source.width and 0<=y<bottom<=source.height):raise ValueError('Subject mask is outside the source image')
 if g.get('source_size') and list(source.size)!=g['source_size']:raise ValueError('Subject dimensions differ from source')
 mask=Image.new('L',(right-x,bottom-y))
 if g.get('polygon'):
  ImageDraw.Draw(mask).polygon([(px-x,py-y) for px,py in g['polygon']],fill=255)
 else:
  if size!=list(mask.size) or not isinstance(runs,list) or len(runs)%2:raise ValueError('Subject mask pixels are invalid')
  data=bytearray(mask.width*mask.height)
  for start,length in zip(runs[::2],runs[1::2]):
   if not isinstance(start,int) or not isinstance(length,int) or start<0 or length<=0 or start+length>len(data):raise ValueError('Subject mask run is invalid')
   data[start:start+length]=b'\xff'*length
  mask=Image.frombytes('L',mask.size,bytes(data))
 tight=mask.getbbox()
 if not tight:raise ValueError('Subject mask is empty')
 image=Image.new('RGB',mask.size,(127,127,127));image.paste(source.crop(box),(0,0),mask);image=image.crop(tight)
 image.thumbnail((1024,1024),Image.Resampling.LANCZOS)
 output=io.BytesIO();image.save(output,'PNG');return output.getvalue()
