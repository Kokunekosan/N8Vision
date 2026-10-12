"""N8Vision Bridge P.10 for ComfyUI.

Discovery/control-plane bridge. It proclaims ComfyUI to N8Vision, exposes a read-only
Tool Shelf inventory of installed nodes and their declared sockets/widgets, and retains
the canvas-only Load Workflow command. It never installs dependencies and loading a
workflow never queues it.
"""
import json, os, urllib.request
from pathlib import Path

WEB_DIRECTORY = "./web"

def _workflow_dirs(root: Path) -> list[str]:
    found=[]; explicit=os.environ.get("N8VISION_WORKFLOWS")
    if explicit: found.append(Path(explicit).expanduser())
    user_root=root/"user"; default=user_root/"default"/"workflows"
    if default.is_dir():found.append(default)
    if user_root.is_dir():
        try:
            for profile in sorted(user_root.iterdir(),key=lambda p:p.name.lower()):
                candidate=profile/"workflows"
                if profile.name!="default" and candidate.is_dir():found.append(candidate)
        except OSError:pass
    result=[];seen=set()
    for path in found:
        try:value=str(path.resolve())
        except OSError:value=str(path.absolute())
        key=os.path.normcase(value)
        if key not in seen:seen.add(key);result.append(value)
    return result

def _output_root(root:Path)->str:
    try:
        import folder_paths
        return str(Path(folder_paths.get_output_directory()).resolve())
    except Exception:return str((root/'output').resolve())

def _jsonable(v):
    if v is None or isinstance(v,(str,int,float,bool)):return v
    if isinstance(v,(list,tuple)):return [_jsonable(x) for x in v]
    if isinstance(v,dict):return {str(k):_jsonable(x) for k,x in v.items()}
    return str(v)

def _tool_shelf():
    import nodes
    shelf=[]
    display=getattr(nodes,'NODE_DISPLAY_NAME_MAPPINGS',{}) or {}
    for name,cls in sorted((getattr(nodes,'NODE_CLASS_MAPPINGS',{}) or {}).items(),key=lambda kv:kv[0].lower()):
        try: inputs=cls.INPUT_TYPES() if hasattr(cls,'INPUT_TYPES') else {}
        except Exception as e: inputs={'_inspection_error':str(e)}
        shelf.append({'type':name,'display_name':display.get(name,name),'category':getattr(cls,'CATEGORY',''),
                      'inputs':_jsonable(inputs),'outputs':_jsonable(getattr(cls,'RETURN_TYPES',()) or ()),
                      'output_names':_jsonable(getattr(cls,'RETURN_NAMES',()) or ()),
                      'output_node':bool(getattr(cls,'OUTPUT_NODE',False))})
    return {'bridge':'n8vision-bridge-p10','agent_required':False,'install_dependencies':False,
            'n8vision_global':True,'tools':shelf}

def _checkpoint_shape(name: str) -> dict:
    """Load one checkpoint through Comfy's own classifier and report the resulting model shape.

    This deliberately does not duplicate Comfy model detection. load_checkpoint_guess_config is
    the same front door Comfy uses when a checkpoint is actually loaded; N8Vision only serializes
    the classification Comfy produced.
    """
    import gc, inspect
    import folder_paths, comfy.sd
    path=folder_paths.get_full_path_or_raise("checkpoints",name)
    kwargs={"output_vae":True,"output_clip":True}
    try: kwargs["embedding_directory"]=folder_paths.get_folder_paths("embeddings")
    except Exception: pass
    sig=inspect.signature(comfy.sd.load_checkpoint_guess_config)
    kwargs={k:v for k,v in kwargs.items() if k in sig.parameters}
    loaded=comfy.sd.load_checkpoint_guess_config(path,**kwargs)
    model=loaded[0] if len(loaded)>0 else None
    clip=loaded[1] if len(loaded)>1 else None
    vae=loaded[2] if len(loaded)>2 else None
    mc=getattr(getattr(model,"model",None),"model_config",None)
    latent=getattr(mc,"latent_format",None)
    target=None
    try: target=mc.clip_target() if mc and hasattr(mc,"clip_target") else None
    except Exception: pass
    def cname(x): return x.__class__.__module__+"."+x.__class__.__name__ if x is not None else None
    out={
      "checkpoint":name,
      "comfy_model_config":cname(mc),
      "model":cname(model),"clip":cname(clip),"vae":cname(vae),
      "latent_format":cname(latent),"clip_target":cname(target),
      "unet_config":_jsonable(getattr(mc,"unet_config",None)),
      "sampling_settings":_jsonable(getattr(mc,"sampling_settings",None)),
      "supported_inference_dtypes":[str(x) for x in (getattr(mc,"supported_inference_dtypes",None) or [])],
    }
    del loaded,model,clip,vae,mc,latent,target
    gc.collect()
    try:
        import comfy.model_management as mm
        mm.soft_empty_cache()
    except Exception: pass
    return out

def _checkpoint_inventory() -> dict:
    import folder_paths
    names=list(folder_paths.get_filename_list("checkpoints") or [])
    rows=[]
    for i,name in enumerate(names):
        try: rows.append({"ok":True,**_checkpoint_shape(name)})
        except Exception as e: rows.append({"ok":False,"checkpoint":name,"error":str(e)})
    return {"bridge":"n8vision-bridge-p10","classifier":"comfy.sd.load_checkpoint_guess_config","checkpoints":rows}

def _install_routes():
    try:
        from aiohttp import web
        from server import PromptServer
        routes=PromptServer.instance.routes
        @routes.get('/n8vision/tool-shelf')
        async def n8vision_tool_shelf(_request):return web.json_response(_tool_shelf())
        @routes.get('/n8vision/checkpoints/interrogate')
        async def n8vision_checkpoint_interrogate(_request):
            # Deliberately serial: Comfy owns model loading/classification and GPU/RAM cleanup.
            return web.json_response(_checkpoint_inventory())
        @routes.get('/n8vision/output-target')
        async def n8vision_output_target(request):
            import folder_paths
            filename=request.query.get('filename','');subfolder=request.query.get('subfolder','')
            if not filename:return web.json_response({'error':'filename required'},status=400)
            root=Path(folder_paths.get_output_directory()).resolve()
            target=(root/subfolder/filename).resolve()
            try:target.relative_to(root)
            except ValueError:return web.json_response({'error':'output escapes Comfy output root'},status=400)
            return web.json_response({'target':str(target),'filename':filename,'subfolder':subfolder,'type':request.query.get('type','output')})
    except Exception as e:print('[N8Vision] Tool Shelf route unavailable:',e)

def _proclaim()->None:
    try:
        custom_node=Path(__file__).resolve().parent;root=custom_node.parent.parent
        body={'id':'comfyui','name':'ComfyUI','kind':'comfy','root':str(root),'output_root':_output_root(root),
              'api_url':'http://127.0.0.1:8188','workflow_dirs':_workflow_dirs(root),'bridge':'n8vision-bridge-p10'}
        req=urllib.request.Request('http://127.0.0.1:8189/api/environments/proclaim',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
        urllib.request.urlopen(req,timeout=.35).close()
    except Exception:pass

class N8VisionLoadWorkflow:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'workflow_path':('STRING',{'default':''})}}
    RETURN_TYPES=();FUNCTION='load_workflow';CATEGORY='N8Vision';OUTPUT_NODE=True
    DESCRIPTION='Loads a saved UI workflow onto the connected Comfy canvas. It does not queue or execute it.'
    def load_workflow(self,workflow_path):
        path=Path(workflow_path).expanduser().resolve()
        if not path.is_file():raise FileNotFoundError(f'N8Vision workflow not found: {path}')
        doc=json.loads(path.read_text(encoding='utf-8'))
        from server import PromptServer
        PromptServer.instance.send_sync('n8vision.load_workflow',{'workflow':doc,'path':str(path)})
        return ()

class N8VisionGlobal:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{}}
    RETURN_TYPES=();FUNCTION='global_socket';CATEGORY='N8Vision';OUTPUT_NODE=True
    DESCRIPTION=('N8Vision graph-local bridge marker/control socket. Standalone: no agent required. '
                 'External reasoners may use the bridge later. N8Vision may inspect and mutate declared graph state, '
                 'but this node never installs custom nodes, Python packages, models, or other dependencies.')
    def global_socket(self):return ()

class N8VisionTextReturn:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'text':('STRING',{'forceInput':True}),'request_id':('STRING',{'default':''})}}
    RETURN_TYPES=();FUNCTION='return_text';CATEGORY='N8Vision';OUTPUT_NODE=True
    DESCRIPTION='Returns a completed STRING to N8Vision. Native progress_text events carry the live token stream.'
    def return_text(self,text,request_id):
        from server import PromptServer
        PromptServer.instance.send_sync('n8vision.text_result',{'request_id':request_id,'text':text})
        return ()


class N8VisionBellringer:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'image':('IMAGE',{'forceInput':True}),'recovery_id':('STRING',{'default':''})}}
    RETURN_TYPES=('IMAGE',);RETURN_NAMES=('image',);FUNCTION='ring';CATEGORY='N8Vision'
    DESCRIPTION='Transparent IMAGE passthrough. Rings N8Vision when execution reaches the recovery boundary; pixels are returned unchanged.'
    def ring(self,image,recovery_id):
        from server import PromptServer
        PromptServer.instance.send_sync('n8vision.bell',{'recovery_id':recovery_id})
        return (image,)

NODE_CLASS_MAPPINGS={'N8VisionLoadWorkflow':N8VisionLoadWorkflow,'N8VisionGlobal':N8VisionGlobal,'N8VisionTextReturn':N8VisionTextReturn,'N8VisionBellringer':N8VisionBellringer}
NODE_DISPLAY_NAME_MAPPINGS={'N8VisionLoadWorkflow':'N8Vision Load Workflow','N8VisionGlobal':'N8Vision Global','N8VisionTextReturn':'N8Vision Text Return','N8VisionBellringer':'N8Vision Bellringer'}
_install_routes();_proclaim()
