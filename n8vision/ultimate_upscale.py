"""Still-image workflow based on the user's upscale_only.json, with 0..N LoRAs."""
import json
import math
import copy
import hashlib
from pathlib import Path

NODE_ROLES = {'source':'LoadImage','checkpoint':'CheckpointLoaderSimple',
 'lora':'LoraLoader','text':'CLIPTextEncode','wildcard':'ImpactWildcardEncode',
 'upscale_model':'UpscaleModelLoader','sampler':'UltimateSDUpscale','output':'SaveImage'}

def recipe(shelf, environment_id):
 tools={t['type']:copy.deepcopy(t) for t in shelf.get('tools',[])}
 # Newer Comfy schemas describe dropdowns as COMBO plus options rather than
 # a list in the type position. Present the same contract to both run UIs.
 for tool in tools.values():
  for group in tool.get('inputs',{}).values():
   if not isinstance(group,dict):continue
   for name,spec in group.items():
    if isinstance(spec,list) and spec and spec[0]=='COMBO' and len(spec)>1:
     group[name]=[spec[1].get('options',[]),spec[1]]
 missing=[name for name in NODE_ROLES.values() if name not in tools]
 if missing:raise ValueError('Upscale workflow needs installed nodes: '+', '.join(missing))
 result={'kind':'ultimate_upscale','name':'Ultimate SD Upscale','environment_id':environment_id,
  'roles':{role:tools[name] for role,name in NODE_ROLES.items()},
  'defaults':json.loads(Path(__file__).with_name('upscale_defaults.json').read_text()),
  'upscale_model_default':'swin2srUpscalerX2And_customX2Safetensor.safetensors'}
 result['revision']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 return result

def matches(saved, submitted):
 # Browser JSON cannot exactly round-trip schema integers above 2**53.
 # Compare the server revision, then execute only the saved server topology.
 return (submitted.get('kind')==saved.get('kind') and
  submitted.get('environment_id')==saved.get('environment_id') and
  submitted.get('revision')==saved.get('revision'))

def widgets(role):
 return {**role.get('inputs',{}).get('required',{}),**role.get('inputs',{}).get('optional',{})}

def validate(role, name, value):
 spec=widgets(role).get(name)
 if not spec:raise ValueError('Unknown upscale setting: '+name)
 typ=spec[0];options=spec[1] if len(spec)>1 and isinstance(spec[1],dict) else {}
 if isinstance(typ,list):
  if value not in typ:raise ValueError('Unavailable '+name+': '+str(value))
 elif typ=='BOOLEAN':
  if not isinstance(value,bool):raise ValueError(name+' must be true or false')
 elif typ in ('INT','FLOAT'):
  if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(name+' must be numeric')
  if typ=='INT' and value!=int(value):raise ValueError(name+' must be an integer')
  if value<options.get('min',-math.inf) or value>options.get('max',math.inf):raise ValueError(name+' is outside installed node limits')
 elif typ!='STRING':raise ValueError('Cannot set socket as widget: '+name)
 return value

def compile_prompt(recipe, source_name, req, output_prefix, default_inputs):
 roles=recipe['roles'];prompt={}
 def add(key, **values):
  role=roles[key];nid=str(len(prompt)+1);inputs=default_inputs(role)
  inputs.update(values);prompt[nid]={'class_type':role['type'],'inputs':inputs};return nid
 def out(nid,typ):
  role=next(r for r in roles.values() if r['type']==prompt[nid]['class_type'])
  return [nid,role['outputs'].index(typ)]
 def checked(key,values):return {n:validate(roles[key],n,v) for n,v in values.items()}
 src=add('source',image=source_name)
 ck=add('checkpoint',**checked('checkpoint',{'ckpt_name':req.model}))
 model=out(ck,'MODEL');clip=out(ck,'CLIP');vae=out(ck,'VAE')
 for lora in req.loras:
  lid=add('lora',model=model,clip=clip,**checked('lora',{'lora_name':lora['name'],
   'strength_model':lora.get('model_strength',1),'strength_clip':lora.get('clip_strength',1)}))
  model=out(lid,'MODEL');clip=out(lid,'CLIP')
 # Fixed text avoids relying on Comfy's browser-only populate hook. Impact still
 # processes its supported inline syntax using the per-image recovered prompt.
 pos=add('wildcard',model=model,clip=clip,wildcard_text=req.positive,populated_text=req.positive,mode='fixed',seed=int(req.seed))
 neg=add('text',clip=clip,text=req.negative)
 settings=dict(recipe['defaults']);settings.update(req.upscale_settings)
 model_name=settings.pop('upscale_model','')
 settings.update(seed=int(req.seed),steps=int(req.refinement_steps),cfg=float(req.cfg),sampler_name=req.sampler,scheduler=req.scheduler)
 upmodel=add('upscale_model',**checked('upscale_model',{'model_name':model_name}))
 uid=add('sampler',**checked('sampler',settings),image=out(src,'IMAGE'),model=out(pos,'MODEL'),positive=out(pos,'CONDITIONING'),negative=out(neg,'CONDITIONING'),vae=vae,upscale_model=out(upmodel,'UPSCALE_MODEL'))
 bell=str(len(prompt)+1);prompt[bell]={'class_type':'N8VisionBellringer','inputs':{'image':out(uid,'IMAGE'),'recovery_id':Path(output_prefix).name}}
 add('output',images=[bell,0],filename_prefix=output_prefix)
 return prompt
