"""Non-destructive presentation of classifier observations."""
import json,re

PLURALS={'hands':'hand','feet':'foot','arms':'arm','legs':'leg','eyes':'eye','ears':'ear','fingers':'finger','toes':'toe','heads':'head','faces':'face','women':'woman','men':'man','people':'person'}
def concept_key(value):
 value=' '.join(str(value or '').casefold().split())
 return PLURALS.get(value,value)

def geometry(row):
 try:return json.loads(row.get('geometry') or '{}') if isinstance(row.get('geometry'),str) else (row.get('geometry') or {})
 except (ValueError,TypeError):return {}

def subject(row):
 g=geometry(row)
 if g.get('subject_role') is False:return False
 return bool(g.get('subject_role') or g.get('subject_pipeline') or row.get('provider')=='subject-intelligence')

def _intervals(g):
 """Sparse global scanlines, preserving actual mask pixels."""
 box=g.get('bbox');size=g.get('mask_size');runs=g.get('mask_rle')
 if not box or not size or not isinstance(runs,list) or len(runs)%2:return None
 x,y,x2,y2=map(int,box);w,h=map(int,size)
 if w<=0 or h<=0 or [w,h]!=[x2-x,y2-y]:return None
 rows={}
 for start,length in zip(runs[::2],runs[1::2]):
  if not isinstance(start,int) or not isinstance(length,int) or start<0 or length<=0 or start+length>w*h:return None
  while length:
   yy,xx=divmod(start,w);n=min(length,w-xx);rows.setdefault(y+yy,[]).append((x+xx,x+xx+n));start+=n;length-=n
 for yy,ranges in rows.items():
  merged=[]
  for a,b in sorted(ranges):
   if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
   else:merged.append((a,b))
  rows[yy]=merged
 return rows

def same_pixels(a,b):
 ga,gb=geometry(a),geometry(b);ba,bb=ga.get('bbox'),gb.get('bbox')
 if not ba or not bb:return False
 if ga.get('source_size')!=gb.get('source_size'):return False
 x,y=max(ba[0],bb[0]),max(ba[1],bb[1]);xx,yy=min(ba[2],bb[2]),min(ba[3],bb[3])
 area=lambda box:max(0,box[2]-box[0])*max(0,box[3]-box[1])
 inter=max(0,xx-x)*max(0,yy-y);union=area(ba)+area(bb)-inter
 if not union or inter/union<.85:return False
 if a.get('kind')=='mask' and b.get('kind')=='mask':
  ma,mb=_intervals(ga),_intervals(gb)
  if ma is None or mb is None:
   return _sampled_mask_overlap(ga,gb)
  aa=sum(r-l for line in ma.values() for l,r in line);ab=sum(r-l for line in mb.values() for l,r in line);overlap=0
  for line in ma.keys() & mb.keys():
   ra,rb=ma[line],mb[line];i=j=0
   while i<len(ra) and j<len(rb):
    overlap+=max(0,min(ra[i][1],rb[j][1])-max(ra[i][0],rb[j][0]))
    if ra[i][1]<rb[j][1]:i+=1
    else:j+=1
  return bool(aa+ab-overlap) and overlap/(aa+ab-overlap)>=.85
 return True

def _sampled_mask_overlap(a,b):
 """Bounded polygon comparison; never infer identical masks from their boxes."""
 from PIL import Image,ImageDraw,ImageChops
 boxes=[a['bbox'],b['bbox']];x=min(box[0] for box in boxes);y=min(box[1] for box in boxes)
 right=max(box[2] for box in boxes);bottom=max(box[3] for box in boxes)
 scale=min(1,256/max(right-x,bottom-y));size=(max(1,round((right-x)*scale)),max(1,round((bottom-y)*scale)))
 masks=[]
 for g in (a,b):
  image=Image.new('L',size);draw=ImageDraw.Draw(image)
  if g.get('polygon'):draw.polygon([((px-x)*scale,(py-y)*scale) for px,py in g['polygon']],fill=255)
  else:
   intervals=_intervals(g)
   if intervals is None:return False
   for line,ranges in intervals.items():
    for left,end in ranges:draw.rectangle(((left-x)*scale,(line-y)*scale,(end-x)*scale,(line+1-y)*scale),fill=255)
  masks.append(image)
 union=ImageChops.lighter(*masks).histogram()[255]
 return bool(union) and ImageChops.darker(*masks).histogram()[255]/union>=.85

def display_rows(rows):
 rows=[dict(row) for row in rows];kept=[];buckets={}
 for index,row in sorted(enumerate(rows),key=lambda item:(-float(item[1].get('confidence') or 0),item[0])):
  if row.get('confidence',0)<=0 or row.get('kind') not in ('bbox','mask'):kept.append((index,row));continue
  key=(concept_key(row.get('concept')),subject(row));group=buckets.setdefault(key,[])
  if any(same_pixels(row,other) for other in group):continue
  group.append(row);kept.append((index,row))
 return [row for index,row in sorted(kept)]

def annotate(rows):
 visible=display_rows(rows)
 return [{**dict(row),'presentation_hidden':dict(row) not in visible} for row in rows]
