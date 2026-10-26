"""Task-specific YOLO labels: unmasked annotations cover their entire box."""
import math

def clipped_box(geometry,width,height):
 box=geometry.get('bbox')
 if not isinstance(box,(list,tuple)) or len(box)!=4:raise ValueError('Training annotation needs a bounding box')
 x1,y1,x2,y2=map(float,box)
 if width<=0 or height<=0 or not all(math.isfinite(v) for v in (x1,y1,x2,y2)):raise ValueError('Invalid training image/box dimensions')
 x1,x2=max(0,min(width,x1)),max(0,min(width,x2));y1,y2=max(0,min(height,y1)),max(0,min(height,y2))
 if x2<=x1 or y2<=y1:raise ValueError('Training box is empty or outside the image')
 return x1,y1,x2,y2

def label_lines(annotation,class_id,width,height,task,mask_polygons):
 g=annotation['geometry_obj'];x1,y1,x2,y2=clipped_box(g,width,height)
 if task=='detect':
  values=[(x1+x2)/(2*width),(y1+y2)/(2*height),(x2-x1)/width,(y2-y1)/height]
  return [str(class_id)+' '+' '.join(f'{v:.6f}' for v in values)]
 if task!='segment':raise ValueError('Unsupported YOLO training task')
 masked='polygon' in g or 'mask_rle' in g
 polygons=mask_polygons(g,width,height) if masked else [[(x1,y1),(x2,y1),(x2,y2),(x1,y2)]]
 lines=[]
 for polygon in polygons:
  if len(polygon)<3:continue
  values=[]
  for px,py in polygon:
   if not math.isfinite(float(px)) or not math.isfinite(float(py)):raise ValueError('Non-finite mask polygon')
   values.extend((max(0,min(1,float(px)/width)),max(0,min(1,float(py)/height))))
  if len(set(zip(values[::2],values[1::2])))>=3:lines.append(str(class_id)+' '+' '.join(f'{v:.6f}' for v in values))
 if not lines:raise ValueError('Saved mask contains no usable foreground polygon; repaint it or use a bare box')
 return lines
