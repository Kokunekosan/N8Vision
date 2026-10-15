"""One application, explicit installation/runtime capabilities."""
import os
import importlib.util
import json
from pathlib import Path

PROFILES = {
 'lite': {'name':'Lite','inference':False,'processing':False,'subject_intelligence':False},
 'blurred': {'name':'Blurred','inference':True,'processing':True,'subject_intelligence':False},
 'full': {'name':'Full','inference':True,'processing':True,'subject_intelligence':True},
}

def profile(edition=None):
 key=str(edition or os.environ.get('N8VISION_EDITION','full')).lower()
 if key not in PROFILES:raise ValueError('Unknown N8Vision edition: '+key)
 return {'edition':key,**PROFILES[key],'subject_intelligence_reserved':key=='full'}

def route_capability(path,method='GET'):
 if path.startswith('/api/subjects'):return 'subject_intelligence'
 if path.startswith(('/api/mv/','/api/models','/api/native/','/api/compare/','/api/learning/')) or path=='/api/search/semantic':return 'inference'
 if path.startswith(('/api/comfy/','/api/environments','/api/refinement/','/api/workshop/','/api/training/')) or path=='/api/config/prompt-translator':return 'processing'
 if (path=='/api/jobs' and method=='POST') or path=='/api/config/sanity':return 'inference'
 return None

def default_edition(root,installing=False):
 root=Path(root)
 paths=(root/'edition-default.json',) if installing else (root/'data/edition.json',root/'edition-default.json')
 for path in paths:
  try:return profile(json.loads(path.read_text(encoding='utf-8'))['edition'])['edition']
  except (OSError,ValueError,KeyError):pass
 return 'full'

def missing_modules(edition):
 modules=['fastapi','uvicorn','PIL','send2trash','qrcode']
 if profile(edition)['inference']:modules+=['torch','torchvision','transformers','numpy','cv2','ultralytics','faiss','image_quality_fusion','huggingface_hub','safetensors','accelerate','open_clip','pandas','sklearn','scipy']
 if profile(edition)['subject_intelligence']:modules+=['timm','einops','kornia','clip']
 return [name for name in modules if importlib.util.find_spec(name) is None]
