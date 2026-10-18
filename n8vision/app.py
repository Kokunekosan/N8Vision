from __future__ import annotations
import io, json, os, sys, math, shutil, sqlite3, threading, time, uuid, logging, hashlib, re, secrets, socket, zipfile, subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from PIL import Image, ImageOps, ImageDraw, ImageFont
from send2trash import send2trash
from .profiles import profile,route_capability,missing_modules
from .filesystem_order import filesystem_key
EDITION=profile()
_missing=missing_modules(EDITION['edition'])
if _missing:raise RuntimeError("N8Vision edition dependencies missing: "+", ".join(_missing))

ROOT=Path(__file__).resolve().parent.parent; STATIC=ROOT/'static'; DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
MODELS=Path(__file__).resolve().parent/'models'; ULTRA_MODELS=MODELS/'ultralytics'
CACHE=ROOT/'cache'; HF_CACHE=CACHE/'huggingface'; HF_CACHE.mkdir(parents=True,exist_ok=True)
# Keep downloaded Hub assets with N8Vision instead of the user's C: profile.
os.environ.setdefault('HF_TOKEN_PATH',str(Path(os.environ.get('HF_HOME') or Path.home()/'.cache/huggingface')/'token'))
os.environ.setdefault('HF_HOME',str(HF_CACHE))
os.environ.setdefault('HF_HUB_CACHE',str(HF_CACHE/'hub'))
os.environ.setdefault('TRANSFORMERS_CACHE',str(HF_CACHE/'transformers'))
LOG=logging.getLogger('n8vision')
if not LOG.handlers:
 h=logging.StreamHandler(); h.setFormatter(logging.Formatter('[N8Vision] %(message)s')); LOG.addHandler(h)
LOG.setLevel(logging.INFO)
LOG.propagate=False
LOG.info('Persistent Hugging Face cache: %s',HF_CACHE)
(ULTRA_MODELS/'bbox').mkdir(parents=True,exist_ok=True); (ULTRA_MODELS/'seg').mkdir(parents=True,exist_ok=True)
MASTER_DB_PATH=DATA/'n8vision.sqlite3'; SESSIONS=DATA/'sessions'; SESSIONS.mkdir(exist_ok=True); LENS_CONFIG_PATH=DATA/'lens_config.json'; IMAGE_EXTS={'.png','.jpg','.jpeg','.webp','.gif','.bmp','.tif','.tiff','.avif'}
app=FastAPI(title='N8Vision',version='I.2b'); app.mount('/static',StaticFiles(directory=STATIC),name='static')
@app.middleware('http')
async def edition_capabilities(request:Request,call_next):
 capability=route_capability(request.url.path,request.method)
 if capability and not EDITION[capability]:
  return Response(json.dumps({'detail':f"{EDITION['name']} does not enable {capability}. Start Blurred or Full to use it."}),status_code=403,media_type='application/json')
 return await call_next(request)

@app.get('/api/edition')
def edition_info():return {**EDITION,'version':'I.2t-l-Z1y','subject_intelligence_available':EDITION['subject_intelligence']}

LOCAL_ATTENTION=0
@app.get('/api/instance')
def instance_info():return {'program':'N8Vision','edition':EDITION['edition'],'pid':os.getpid()}

@app.get('/api/instance/attention')
@app.post('/api/instance/attention')
def instance_attention(request:Request):
 global LOCAL_ATTENTION
 if not _is_loopback(request.client.host if request.client else None) or _public_request(request):raise HTTPException(403,'Host-local attention only')
 if request.method=='POST':LOCAL_ATTENTION+=1
 return {'sequence':LOCAL_ATTENTION}

JOBS:dict[str,dict[str,Any]]={}; LOCK=threading.Lock(); MODEL_CACHE={}
OUTPUT_RECOVERY_LOCK=threading.RLock()
PENDING_COMFY_OUTPUTS:dict[str,dict[str,Any]]={}
COMFY_RECOVERY_BATCHES:dict[str,dict[str,Any]]={}
COMFY_TEXT_LOCK=threading.Condition(threading.RLock())
COMFY_TEXT_STREAMS:dict[str,dict[str,Any]]={}
COMFY_TEXT_PROMPTS:dict[str,str]={}
COMFY_SHELF_SCANNED_THIS_RUN:set[str]=set()
COMFY_SHELF_SCAN_ONCE_LOCK=threading.Lock()
LENS_CONFIG_LOCK=threading.RLock()
JOB_JOURNAL_PATH=DATA/'active_jobs.json'
STALE_JOB_REPORT:dict[str,Any]={'count':0,'jobs':[]}
OBS_REV=0
STOP_REQUESTED=False
SHUTDOWN_SEALED=False
SHUTDOWN_BROWSER_ACK=threading.Event()
DB_ACTIVITY=threading.Condition(); DB_ACTIVE=0; DB_ACCEPTING=True
# One archive gate: database operations wait their turn instead of competing until SQLite returns 'database is locked'.
DB_QUEUE_LOCK=threading.RLock()
# P.53 fixed recovery slots: 0=live, A=last clean shutdown, B=verified fallback.
SESSION_ZERO=SESSIONS/'session-0.sqlite3'
SESSION_A=SESSIONS/'session-A.sqlite3'
SESSION_B=SESSIONS/'session-B.sqlite3'
DB_PATH=SESSION_ZERO
LAUNCH_REPORT={'ready':False,'deferred':True,'missing':0,'groups':[]}
LAUNCH_VERIFY_LOCK=threading.Lock()
# P.51 startup ordering barrier: verification -> Sweepy -> background inspectors.
# Inspectors must not wake merely because LAUNCH_REPORT.ready flipped true.
ARCHIVE_MAINTENANCE_DONE=threading.Event()
LAUNCH_VERIFY_STARTED=False
# Installation state lives under data/, never in the replaceable release payload.
CONFIG_PATH=DATA/'n8vision_config.json'
LEGACY_CONFIG_PATH=ROOT/'n8vision_config.json'
CONFIG_SCHEMA_VERSION=1
CONFIG_DEFAULTS={'collisions_always_rename':True,
 'schema_version':CONFIG_SCHEMA_VERSION,
 'grid_detail':'hover','sanity_badges':'compact','grid_gap_tenths':1,'viewer_target':'system',
 'enable_lan':False,'persistent_credentials':False,'enable_public':False,'public_auto_start':False,'cloudflared_path':'','public_tunnel_mode':'quick','public_named_hostname':'','public_token_file':'','public_external_managed':False,
 'filter_presets':{},
 'yolo':{'enabled_models':[],'world_classes':[],'batch_size':16},
 'sanity':{'thumbnail':256,'edge_threshold':24,'light_blur':1.0,'medium_blur':2.5,'heavy_blur':4.0,'grade_b_largest_fraction':0.10,'uncapped_unsanity':False},
 'thumbnail_cache':{'path':'','max_axis':300,'producer_version':2,'delete_orphans_on_maintenance':True,'max_mb':200,'warm_archive':True},
 'ringworld':{'buffer_rows':50,'south_bias':2},
 'archive_maintenance':{'quiet_seconds':5},
 'storage_classes':{},
 'archive_roots':[],
 'refinement_recipe':{},
 'workshop_functions':[],
 'comfy_output_subfolder':'N8Vision',
 'prompt_translator':{'model':'','type':'stable_diffusion','device':'default'},
 'checkpoint_library':{'environment_id':'','updated':0,'checkpoints':{}},
 'comfy_tool_shelves':{'updated':0,'environments':{}},
 'learning':{'maintenance_enabled':False,'maintenance_time':'03:00','correction_threshold':25,'last_maintenance_day':''}
}
NETWORK_SESSION_ID=uuid.uuid4().hex
PAIRINGS:dict[str,float]={}
SESSION_CREDENTIALS:set[str]=set()
ADMIN_BOOTSTRAP_PATH=DATA/'admin_bootstrap.json'
ADMIN_BOOTSTRAP_LOCK=threading.RLock()
PUBLIC_TUNNEL_LOCK=threading.RLock()
PUBLIC_TUNNEL={'process':None,'url':'','state':'stopped','error':'','started':0.0}
THUMB_CACHE_ROOT_CACHE:Path|None=None
THUMB_TRIM_LAST:dict[str,float]={}

# Browse is foreground work. Background observers stay parked from navigation request
# until the matching client transaction reports that its grid has stabilized. Long recursive
# walks are kept alive by a browser heartbeat; only an actually abandoned transaction times out.
BROWSE_GATE_LOCK=threading.RLock()
BROWSE_ACTIVE_TOKEN=None
BROWSE_GATE_LAST_HEARTBEAT=0.0
BROWSE_QUIET_UNTIL=0.0
BROWSE_ABANDON_SECONDS=30.0
BROWSE_QUIESCENCE_SECONDS=5.0
# P.55 interactive grid governor. Any grid mutation/row request derates observation CPU pools
# to one worker. Repeated activity extends the hold; normal throttle returns after 500ms quiet.
GRID_GOVERNOR_LOCK=threading.RLock()
GRID_GOVERNOR_UNTIL=0.0
GRID_GOVERNOR_SETTLE_SECONDS=.5

def _grid_governor_touch(reason='grid'):
 global GRID_GOVERNOR_UNTIL
 with GRID_GOVERNOR_LOCK:
  GRID_GOVERNOR_UNTIL=max(GRID_GOVERNOR_UNTIL,time.monotonic()+GRID_GOVERNOR_SETTLE_SECONDS)
 return GRID_GOVERNOR_UNTIL

def _grid_governor_active():
 with GRID_GOVERNOR_LOCK:return time.monotonic()<GRID_GOVERNOR_UNTIL

def _grid_worker_cap(requested):
 return 1 if _grid_governor_active() else max(1,int(requested or 1))

def _browse_gate_begin(token,path='',recursive=False):
 global BROWSE_ACTIVE_TOKEN,BROWSE_GATE_LAST_HEARTBEAT,BROWSE_QUIET_UNTIL
 with BROWSE_GATE_LOCK:
  BROWSE_ACTIVE_TOKEN=token;BROWSE_GATE_LAST_HEARTBEAT=time.monotonic();BROWSE_QUIET_UNTIL=0.0
 LOG.info('Browse foreground gate: parked background observations · tx=%s · %s · recursive=%s',token,path,recursive)

def _browse_gate_heartbeat(token):
 global BROWSE_GATE_LAST_HEARTBEAT
 with BROWSE_GATE_LOCK:
  if token and token==BROWSE_ACTIVE_TOKEN:
   BROWSE_GATE_LAST_HEARTBEAT=time.monotonic();return True
 return False

def _browse_gate_stable(token=None,force=False):
 global BROWSE_ACTIVE_TOKEN,BROWSE_QUIET_UNTIL
 with BROWSE_GATE_LOCK:
  if not force and token!=BROWSE_ACTIVE_TOKEN:return False
  BROWSE_ACTIVE_TOKEN=None;BROWSE_QUIET_UNTIL=time.monotonic()+BROWSE_QUIESCENCE_SECONDS
 LOG.info('Browse grid stable: tx=%s · startup housekeeping eligible after %.1fs quiescence',token,BROWSE_QUIESCENCE_SECONDS)
 return True

def _browse_gate_paused():
 global BROWSE_ACTIVE_TOKEN,BROWSE_QUIET_UNTIL
 now=time.monotonic()
 with BROWSE_GATE_LOCK:
  if BROWSE_ACTIVE_TOKEN:
   sess=globals().get('BROWSE_SESSIONS',{}).get(BROWSE_ACTIVE_TOKEN,{})
   settled=sess.get('complete') and now-float(sess.get('completed_at',now))>=15
   if not settled and now-BROWSE_GATE_LAST_HEARTBEAT <= BROWSE_ABANDON_SECONDS:return True
   dead=BROWSE_ACTIVE_TOKEN;BROWSE_ACTIVE_TOKEN=None;BROWSE_QUIET_UNTIL=now+BROWSE_QUIESCENCE_SECONDS
   LOG.warning('Browse foreground gate released: tx=%s · %s; entering %.1fs quiescence',dead,'completed catalog grid-ack timeout' if settled else 'missed heartbeat',BROWSE_QUIESCENCE_SECONDS)
  return now < BROWSE_QUIET_UNTIL

def _merge_defaults(dst,defaults):
 out=dict(dst) if isinstance(dst,dict) else {}
 for k,v in defaults.items():
  if k not in out:out[k]=json.loads(json.dumps(v))
  elif isinstance(v,dict) and isinstance(out.get(k),dict):out[k]=_merge_defaults(out[k],v)
 return out
def _save_config(d):
 CONFIG_PATH.parent.mkdir(parents=True,exist_ok=True)
 tmp=CONFIG_PATH.with_suffix('.tmp');tmp.write_text(json.dumps(d,indent=2,sort_keys=True),encoding='utf-8');tmp.replace(CONFIG_PATH)
def _load_config():
 d={}
 try:
  if CONFIG_PATH.exists():d=json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
  elif LEGACY_CONFIG_PATH.exists():
   d=json.loads(LEGACY_CONFIG_PATH.read_text(encoding='utf-8'))
   LOG.info('Migrating legacy config into persistent installation state: %s',CONFIG_PATH)
 except Exception as e:LOG.warning('Config read warning: %s',e);d={}
 d=_merge_defaults(d if isinstance(d,dict) else {},CONFIG_DEFAULTS)
 d['schema_version']=CONFIG_SCHEMA_VERSION
 # First launch and schema/default additions are materialized immediately.
 try:
  if not CONFIG_PATH.exists() or json.loads(CONFIG_PATH.read_text(encoding='utf-8'))!=d:_save_config(d)
 except Exception:_save_config(d)
 return d
def _netcfg():
 d=_load_config();return {k:d.get(k) for k in ('enable_lan','persistent_credentials','enable_public','public_auto_start','public_tunnel_mode','public_named_hostname','public_token_file','public_external_managed')}
def _lan_ip():
 try:
  sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.connect(('10.255.255.255',1));ip=sock.getsockname()[0];sock.close();return ip
 except Exception:
  try:return socket.gethostbyname(socket.gethostname())
  except Exception:return '127.0.0.1'
def _credential_ok(token:str|None)->bool:
 if not token:return False
 if token in SESSION_CREDENTIALS:return True
 cfg=_load_config()
 if _admin_ok(token):return True
 if bool(cfg.get('persistent_credentials',False)):
  digest=hashlib.sha256(token.encode()).hexdigest()
  return digest in set(cfg.get('persistent_credential_hashes',[])) or digest in {x.get('credential_hash') for x in cfg.get('paired_devices',[]) if isinstance(x,dict)}
 return False

def _admin_ok(token:str|None)->bool:
 if not token:return False
 digest=hashlib.sha256(token.encode()).hexdigest()
 cfg=_load_config()
 return any(isinstance(d,dict) and d.get('role')=='admin' and secrets.compare_digest(str(d.get('credential_hash','')),digest) for d in cfg.get('paired_devices',[]))

def _admin_bootstrap_valid(code:str)->bool:
 # Code is generated from the host's filesystem/console, never from HTTP.
 with ADMIN_BOOTSTRAP_LOCK:
  try:record=json.loads(ADMIN_BOOTSTRAP_PATH.read_text(encoding='utf-8'))
  except Exception:return False
  if time.time()>float(record.get('expires',0)):
   ADMIN_BOOTSTRAP_PATH.unlink(missing_ok=True);return False
  expected=str(record.get('hash',''))
  if not secrets.compare_digest(hashlib.sha256(code.encode()).hexdigest(),expected):return False
  ADMIN_BOOTSTRAP_PATH.unlink(missing_ok=True)
  return True

def _issue_admin_credential(name:str)->dict:
 credential=secrets.token_urlsafe(48);digest=hashlib.sha256(credential.encode()).hexdigest()
 cfg=_load_config();devices=[d for d in cfg.get('paired_devices',[]) if isinstance(d,dict)]
 devices.append({'id':uuid.uuid4().hex[:12],'name':name[:80],'credential_hash':digest,'paired':time.time(),'role':'admin'})
 cfg['paired_devices']=devices;_save_config(cfg)
 return {'credential':credential,'device_id':devices[-1]['id'],'role':'admin','persistent':True}

def _is_loopback(host:str|None)->bool:
 return host in {'127.0.0.1','::1','localhost'}

def _public_request(request:Request)->bool:
 # Reverse tunnels originate from loopback, so client.host alone cannot distinguish them.
 # Cloudflare supplies the original client address; generic reverse proxies normally supply X-Forwarded-For.
 return bool(request.headers.get('CF-Connecting-IP') or request.headers.get('X-Forwarded-For'))

@app.middleware('http')
async def network_auth(request:Request,call_next):
 path=request.url.path
 token=request.headers.get('X-N8Vision-Credential')
 if not token and path in {'/api/file','/api/grid-overlay','/api/thumb'}:
  token=request.cookies.get('n8vision_media')
 # Host authorization is an explicit one-time console secret; never localhost inference.
 if path=='/api/network/admin/bootstrap':return await call_next(request)
 admin_paths={'/api/network/settings','/api/network/pairing','/api/network/revoke-all',
              '/api/network/revoke-device','/api/network/devices',
              '/api/network/public/settings','/api/network/public/start','/api/network/public/stop'}
 if path.startswith('/api/network/admin/') or path in admin_paths:
  if not _admin_ok(token):return Response('N8Vision Admin credential required',status_code=403)
  return await call_next(request)
 cfg=_netcfg();public_req=cfg['enable_public'] and _public_request(request)
 if not public_req and _is_loopback(request.client.host if request.client else None):
  return await call_next(request)
 if path.startswith('/static/') or path in {'/','/api/network/pair','/api/network/status'}:
  return await call_next(request)
 if not _credential_ok(token):return Response('N8Vision device pairing required',status_code=401)
 return await call_next(request)

@app.post('/api/network/media-session')
def media_session(request:Request):
 token=request.headers.get('X-N8Vision-Credential')
 if not _credential_ok(token):raise HTTPException(401,'Valid device pairing required')
 response=JSONResponse({'ok':True},headers={'Cache-Control':'no-store'})
 secure=request.url.scheme=='https' or (_public_request(request) and request.headers.get('X-Forwarded-Proto','').lower()=='https')
 response.set_cookie('n8vision_media',token,httponly=True,secure=secure,samesite='strict',path='/api/')
 return response

class NetworkSettingsRequest(BaseModel):
 enable_lan:bool
 persistent_credentials:bool

class PublicSettingsRequest(BaseModel):
 enable_public:bool
 auto_start:bool=False
 cloudflared_path:str=''
 tunnel_mode:str='quick'
 named_hostname:str=''
 token_file:str=''
 external_managed:bool=False

class PairRequest(BaseModel):
 pairing_token:str
 device_name:str|None=None
class RevokeDeviceRequest(BaseModel):
 device_id:str

class DisplaySettingsRequest(BaseModel):
 grid_detail:str
 grid_gap_tenths:int|None=None

class SanityDisplaySettingsRequest(BaseModel):
 sanity_badges:str

class SanitySettingsRequest(BaseModel):
 thumbnail:int=256
 edge_threshold:int=24
 light_blur:float=1.0
 medium_blur:float=2.5
 heavy_blur:float=4.0
 grade_b_largest_fraction:float=0.10
 uncapped_unsanity:bool=False

class DefaultRootRequest(BaseModel):
 path:str|None=None

class ThumbnailCacheRequest(BaseModel):
 path:str|None=None

class FilterPresetRequest(BaseModel):
 name:str
 state:dict[str,Any]

def _cloudflared_executable():
 cfg=_load_config(); custom=str(cfg.get('cloudflared_path','') or '').strip()
 if custom and Path(custom).is_file():return custom
 return shutil.which('cloudflared') or ''

def _public_snapshot():
 with PUBLIC_TUNNEL_LOCK:
  proc=PUBLIC_TUNNEL.get('process'); alive=bool(proc and proc.poll() is None)
  if not alive and PUBLIC_TUNNEL.get('state') in {'starting','online'}:PUBLIC_TUNNEL['state']='stopped'
  external=_netcfg().get('public_tunnel_mode')=='named' and bool(_netcfg().get('public_external_managed'))
  return {'enabled':bool(_netcfg().get('enable_public')),'auto_start':bool(_netcfg().get('public_auto_start')),'state':('external' if external else PUBLIC_TUNNEL.get('state','stopped')),'url':('https://'+str(_netcfg().get('public_named_hostname') or '') if external else PUBLIC_TUNNEL.get('url','')),'error':PUBLIC_TUNNEL.get('error',''),'cloudflared':_cloudflared_executable(),'alive':alive,'mode':_netcfg().get('public_tunnel_mode','quick'),'named_hostname':_netcfg().get('public_named_hostname',''),'token_file':_netcfg().get('public_token_file',''),'external_managed':bool(_netcfg().get('public_external_managed'))}

def _tunnel_reader(proc):
 url_re=re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com',re.I)
 try:
  for raw in iter(proc.stderr.readline,''):
   if not raw:break
   line=raw.strip(); m=url_re.search(line)
   if m:
    with PUBLIC_TUNNEL_LOCK:
     PUBLIC_TUNNEL['url']=m.group(0).rstrip('/');PUBLIC_TUNNEL['state']='online';PUBLIC_TUNNEL['error']=''
    LOG.info('Public portal online: %s',m.group(0))
   if PUBLIC_TUNNEL.get('mode')=='named' and ('Registered tunnel connection' in line or 'Connection registered' in line):
    with PUBLIC_TUNNEL_LOCK:
     PUBLIC_TUNNEL['state']='online';PUBLIC_TUNNEL['error']=''
  rc=proc.wait()
  with PUBLIC_TUNNEL_LOCK:
   if PUBLIC_TUNNEL.get('process') is proc:
    PUBLIC_TUNNEL['state']='stopped';PUBLIC_TUNNEL['process']=None
    if rc and not PUBLIC_TUNNEL.get('error'):PUBLIC_TUNNEL['error']=f'cloudflared exited with code {rc}'
 except Exception as e:
  with PUBLIC_TUNNEL_LOCK:PUBLIC_TUNNEL['state']='error';PUBLIC_TUNNEL['error']=str(e)

def _start_public_tunnel():
 exe=_cloudflared_executable()
 if not exe:raise RuntimeError('cloudflared was not found. Install it or set its executable path in Public Portal settings.')
 with PUBLIC_TUNNEL_LOCK:
  proc=PUBLIC_TUNNEL.get('process')
  if proc and proc.poll() is None:return _public_snapshot()
  port=int(os.environ.get('N8VISION_PORT','8189'))
  flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
  cfg=_load_config(); mode=cfg.get('public_tunnel_mode','quick')
  if mode=='named' and cfg.get('public_external_managed'):
   raise RuntimeError('This named tunnel is managed by the Cloudflare service. No second connector is needed.')
  if mode=='named':
   hostname=str(cfg.get('public_named_hostname','')).strip().lower()
   token_file=Path(str(cfg.get('public_token_file','')).strip()).expanduser()
   if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',hostname) or '.' not in hostname:raise RuntimeError('Configure the named tunnel hostname first.')
   if not token_file.is_file():raise RuntimeError('Named tunnel token file not found. Save the Cloudflare tunnel token in a host-local file.')
   args=[exe,'tunnel','--no-autoupdate','run','--token-file',str(token_file)]
  else:args=[exe,'tunnel','--no-autoupdate','--url',f'http://127.0.0.1:{port}']
  proc=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,bufsize=1,creationflags=flags)
  PUBLIC_TUNNEL.update({'process':proc,'url':('https://'+hostname if mode=='named' else ''),'mode':mode,'state':'starting','error':'','started':time.time()})
 threading.Thread(target=_tunnel_reader,args=(proc,),name='n8-public-tunnel',daemon=True).start()
 return _public_snapshot()

def _stop_public_tunnel():
 with PUBLIC_TUNNEL_LOCK:
  proc=PUBLIC_TUNNEL.get('process');PUBLIC_TUNNEL['process']=None;PUBLIC_TUNNEL['url']='';PUBLIC_TUNNEL['state']='stopped';PUBLIC_TUNNEL['error']=''
 if proc and proc.poll() is None:
  try:proc.terminate();proc.wait(timeout=4)
  except Exception:
   try:proc.kill()
   except Exception:pass
 return _public_snapshot()

@app.get('/api/network/public/status')
def public_status():return _public_snapshot()

@app.put('/api/network/public/settings')
def public_settings(req:PublicSettingsRequest):
 cfg=_load_config();cfg['enable_public']=bool(req.enable_public);cfg['public_auto_start']=bool(req.auto_start);cfg['cloudflared_path']=str(req.cloudflared_path or '').strip();cfg['public_tunnel_mode']=req.tunnel_mode if req.tunnel_mode in ('quick','named') else 'quick';cfg['public_named_hostname']=str(req.named_hostname or '').strip().lower();cfg['public_token_file']=str(req.token_file or '').strip();cfg['public_external_managed']=bool(req.external_managed);_save_config(cfg)
 if not req.enable_public:_stop_public_tunnel()
 return _public_snapshot()

@app.post('/api/network/public/start')
def public_start():
 cfg=_load_config()
 if not bool(cfg.get('enable_public')):raise HTTPException(409,'Enable Public Portal first.')
 try:return _start_public_tunnel()
 except Exception as e:raise HTTPException(503,str(e))

@app.post('/api/network/public/stop')
def public_stop():return _stop_public_tunnel()

class AdminBootstrapRequest(BaseModel):
 code:str
 device_name:str='Host administrator'
class AdminGrantRequest(BaseModel):
 device_id:str

@app.post('/api/network/admin/bootstrap')
def admin_bootstrap(req:AdminBootstrapRequest):
 if not _admin_bootstrap_valid(req.code):raise HTTPException(403,'Invalid or expired host authorization code')
 return _issue_admin_credential(req.device_name)

@app.get('/api/network/admin/me')
def admin_me():return {'role':'admin'}

@app.post('/api/network/admin/grant')
def admin_grant(req:AdminGrantRequest):
 cfg=_load_config();devices=cfg.get('paired_devices',[])
 for d in devices:
  if isinstance(d,dict) and d.get('id')==req.device_id:
   d['role']='admin';_save_config(cfg);return {'ok':True,'device_id':req.device_id,'role':'admin'}
 raise HTTPException(404,'Persistent paired device not found')

@app.get('/api/network/status')
def network_status():
 cfg=_netcfg();port=int(os.environ.get('N8VISION_PORT','8189'))
 return {**cfg,'lan_ip':_lan_ip(),'port':port,'session_id':NETWORK_SESSION_ID,'restart_required':False,'bind_host':os.environ.get('N8VISION_BIND_HOST','127.0.0.1'),'public':_public_snapshot()}

@app.put('/api/network/settings')
def network_settings(req:NetworkSettingsRequest):
 cfg=_load_config();old_lan=bool(cfg.get('enable_lan',False));cfg['enable_lan']=bool(req.enable_lan);cfg['persistent_credentials']=bool(req.persistent_credentials)
 if not req.persistent_credentials:cfg.pop('persistent_credential_hashes',None)
 _save_config(cfg)
 return {**_netcfg(),'restart_required':old_lan!=req.enable_lan}

@app.post('/api/network/pairing')
def create_pairing():
 cfg=_netcfg(); pub=_public_snapshot()
 if not cfg['enable_lan'] and not (cfg['enable_public'] and pub.get('state') in ('online','external')):raise HTTPException(409,'Enable LAN or start the Public Portal before pairing another device.')
 pair=secrets.token_urlsafe(32);PAIRINGS[pair]=time.time()+600
 port=int(os.environ.get('N8VISION_PORT','8189'));base=pub.get('url') if cfg['enable_public'] and pub.get('state') in ('online','external') else f'http://{_lan_ip()}:{port}';url=f'{base}/?pair={pair}'
 try:
  import qrcode
  import qrcode.image.svg
  img=qrcode.make(url,image_factory=qrcode.image.svg.SvgPathImage)
  out=io.BytesIO();img.save(out);svg=out.getvalue().decode('utf-8')
 except Exception as e:raise HTTPException(500,f'QR generator unavailable: {e}')
 return {'url':url,'svg':svg,'expires_in':600}

@app.post('/api/network/pair')
def pair_device(req:PairRequest):
 expiry=PAIRINGS.pop(req.pairing_token,None)
 if not expiry or expiry<time.time():raise HTTPException(401,'Pairing token is invalid or expired. Generate a new QR from the host.')
 credential=secrets.token_urlsafe(48);SESSION_CREDENTIALS.add(credential)
 cfg=_load_config()
 digest=hashlib.sha256(credential.encode()).hexdigest();device_id=uuid.uuid4().hex[:12]
 if bool(cfg.get('persistent_credentials',False)):
  hashes=list(dict.fromkeys(cfg.get('persistent_credential_hashes',[])+[digest]));cfg['persistent_credential_hashes']=hashes
  devices=list(cfg.get('paired_devices',[]));devices.append({'id':device_id,'name':(req.device_name or 'Paired browser')[:80],'credential_hash':digest,'paired':time.time(),'role':'device'});cfg['paired_devices']=devices;_save_config(cfg)
 return {'credential':credential,'device_id':device_id,'session_id':NETWORK_SESSION_ID,'persistent':bool(cfg.get('persistent_credentials',False))}

@app.post('/api/network/revoke-all')
def revoke_all_devices():
 SESSION_CREDENTIALS.clear();cfg=_load_config();cfg.pop('persistent_credential_hashes',None);cfg.pop('paired_devices',None);_save_config(cfg);return {'ok':True}

@app.get('/api/network/devices')
def network_devices():
 cfg=_load_config();return {'devices':[{'id':x.get('id'),'name':x.get('name','Paired browser'),'paired':x.get('paired'),'role':x.get('role','device')} for x in cfg.get('paired_devices',[]) if isinstance(x,dict)]}
@app.post('/api/network/revoke-device')
def revoke_device(req:RevokeDeviceRequest):
 cfg=_load_config();devices=list(cfg.get('paired_devices',[]));gone=[x for x in devices if x.get('id')==req.device_id];cfg['paired_devices']=[x for x in devices if x.get('id')!=req.device_id]
 hashes=set(cfg.get('persistent_credential_hashes',[]))
 for x in gone:hashes.discard(x.get('credential_hash'))
 cfg['persistent_credential_hashes']=list(hashes);_save_config(cfg);return {'ok':True,'revoked':len(gone)}

def _write_active_job_journal():
 # Persist only work that would be unsafe to pretend survived a process exit.
 # The journal is diagnostic/recovery metadata, never a resume queue.
 with LOCK:
  active=[dict(j) for j in JOBS.values() if j.get('state') in ('queued','running')]
 tmp=JOB_JOURNAL_PATH.with_suffix('.tmp')
 try:
  if active:
   tmp.write_text(json.dumps({'session_id':NETWORK_SESSION_ID,'updated':time.time(),'jobs':active},indent=2),encoding='utf-8')
   tmp.replace(JOB_JOURNAL_PATH)
  else:
   tmp.unlink(missing_ok=True); JOB_JOURNAL_PATH.unlink(missing_ok=True)
 except Exception as e:
  LOG.warning('Could not update active-job journal: %s',e)

def _purge_stale_job_journal():
 global STALE_JOB_REPORT
 if not JOB_JOURNAL_PATH.exists(): return
 try:
  d=json.loads(JOB_JOURNAL_PATH.read_text(encoding='utf-8'))
  jobs=[j for j in d.get('jobs',[]) if isinstance(j,dict) and j.get('state') in ('queued','running')]
  STALE_JOB_REPORT={'count':len(jobs),'jobs':[{'id':j.get('id'),'kind':j.get('kind','unknown'),'state':j.get('state','unknown'),'done':j.get('done',0),'total':j.get('total',0)} for j in jobs]}
  if jobs:
   LOG.error('Previous session ended with %s unfinished job(s); they cannot be resumed and were purged.',len(jobs))
   for j in jobs: LOG.error('Abandoned job: %s %s — %s/%s complete',j.get('kind','unknown'),j.get('id','?'),j.get('done',0),j.get('total',0))
 except Exception as e:
  STALE_JOB_REPORT={'count':1,'jobs':[{'kind':'job-journal','state':'invalid','error':str(e)}]}
  LOG.error('Previous active-job journal was unreadable and was purged: %s',e)
 finally:
  JOB_JOURNAL_PATH.unlink(missing_ok=True)
  JOB_JOURNAL_PATH.with_suffix('.tmp').unlink(missing_ok=True)

_purge_stale_job_journal()

def sqlite_ok(path:Path)->bool:
 try:
  if not path.exists(): return False
  c=sqlite3.connect(path,timeout=5); row=c.execute('PRAGMA quick_check').fetchone(); c.close(); return bool(row and row[0]=='ok')
 except sqlite3.Error:return False

def _copy_sqlite_into(src:Path,dst:Path):
 """Copy a verified SQLite generation into a fresh live slot."""
 tmp=dst.with_suffix(dst.suffix+'.tmp')
 tmp.unlink(missing_ok=True)
 shutil.copy2(src,tmp)
 if not sqlite_ok(tmp):
  tmp.unlink(missing_ok=True);raise RuntimeError(f'Copied recovery slot failed verification: {src.name}')
 tmp.replace(dst)

def prepare_working_database():
 """P.53 fixed-slot recovery: interrupted 0 -> A -> B -> legacy master -> blank.

 0 from a force-close is valuable work, so it gets first recovery priority. A is the most
 recent clean shutdown. B is the known-good fallback. Only one source is folded into the new 0.
 """
 # Stale WAL/SHM belong to the old live connection. sqlite_ok() opens 0 first so SQLite can
 # recover its WAL before we copy it.
 source=None
 if SESSION_ZERO.exists():
  if sqlite_ok(SESSION_ZERO):
   source=SESSION_ZERO;LOG.warning('Recovery slots: interrupted 0 verified; recovering live work')
  else:
   bad=SESSIONS/'session-malformed-0.sqlite3'
   bad.unlink(missing_ok=True);SESSION_ZERO.replace(bad)
   LOG.warning('Recovery slots: interrupted 0 failed verification; parked as %s',bad.name)
 if source is None and SESSION_A.exists():
  if sqlite_ok(SESSION_A):
   source=SESSION_A;LOG.info('Recovery slots: A verified; folding last clean session into 0')
  else:
   bad=SESSIONS/'session-malformed-A.sqlite3'
   bad.unlink(missing_ok=True);SESSION_A.replace(bad)
   LOG.warning('Recovery slots: A failed verification; parked as %s; trying B',bad.name)
 if source is None and SESSION_B.exists():
  if sqlite_ok(SESSION_B):
   source=SESSION_B;LOG.warning('Recovery slots: B verified; using fallback')
  else:
   bad=SESSIONS/'session-malformed-B.sqlite3'
   bad.unlink(missing_ok=True);SESSION_B.replace(bad)
   LOG.error('Recovery slots: B also failed verification; parked as %s',bad.name)

 # Transition only: P.52 and earlier may still have the compiled master. It is import material,
 # not part of the fixed-slot lifecycle.
 if source is None and MASTER_DB_PATH.exists() and sqlite_ok(MASTER_DB_PATH):
  source=MASTER_DB_PATH;LOG.warning('Recovery slots: importing legacy master into 0')

 if source is not None:
  # If source itself is 0, preserve it through a temporary sibling before recreating 0.
  if source==SESSION_ZERO:
   tmp=SESSIONS/'session-0.recovering.sqlite3'
   tmp.unlink(missing_ok=True);shutil.copy2(SESSION_ZERO,tmp)
   if not sqlite_ok(tmp):raise RuntimeError('Interrupted 0 recovery copy failed verification')
   SESSION_ZERO.unlink(missing_ok=True);tmp.replace(SESSION_ZERO)
  else:_copy_sqlite_into(source,SESSION_ZERO)
 else:
  SESSION_ZERO.unlink(missing_ok=True)
  LOG.warning('Recovery slots: no usable generation found; starting a blank 0')

 # A that successfully supplied 0 becomes B, but only after 0 exists and verifies.
 # This is the user's A->0, old B delete, A->B promotion ordering.
 if source==SESSION_A:
  if not sqlite_ok(SESSION_ZERO):raise RuntimeError('Live 0 failed verification after folding A')
  SESSION_B.unlink(missing_ok=True)
  SESSION_A.replace(SESSION_B)
  LOG.info('Recovery slots: promoted verified A -> B after successful fold into 0')
 return source

prepare_working_database()
def load_lens_config():
 try:
  d=json.loads(LENS_CONFIG_PATH.read_text(encoding='utf-8'))
  return d if isinstance(d,dict) else {}
 except Exception:return {}
def save_lens_config(d):
 # Lens controls can save from overlapping UI requests. Serialize the complete
 # write and give each write its own temporary file so Windows never sees two
 # requests fighting over lens_config.tmp.
 with LENS_CONFIG_LOCK:
  LENS_CONFIG_PATH.parent.mkdir(parents=True,exist_ok=True)
  tmp=LENS_CONFIG_PATH.with_name(f'{LENS_CONFIG_PATH.name}.{uuid.uuid4().hex}.tmp')
  try:
   tmp.write_text(json.dumps(d,indent=2,sort_keys=True),encoding='utf-8')
   tmp.replace(LENS_CONFIG_PATH)
  finally:
   try:
    if tmp.exists():tmp.unlink()
   except OSError:pass
def lens_threshold(identity,default=.25):
 try:return max(.0,min(1.0,float(load_lens_config().get(identity,{}).get('confidence',default))))
 except Exception:return default
def bump_obs_revision():
 global OBS_REV
 with LOCK:
  OBS_REV+=1
  return OBS_REV

@contextmanager
def db():
 global DB_ACTIVE
 # Archive access is serialized deliberately. Background writers queue behind user work (and vice versa)
 # rather than failing to instantiate observations when SQLite is busy. Keep individual write scopes short.
 DB_QUEUE_LOCK.acquire()
 with DB_ACTIVITY:
  if not DB_ACCEPTING:
   DB_QUEUE_LOCK.release()
   raise RuntimeError('N8Vision database is shutting down')
  DB_ACTIVE+=1
 c=None
 try:
  c=sqlite3.connect(DB_PATH,timeout=30); c.row_factory=sqlite3.Row; c.execute('PRAGMA busy_timeout=60000'); c.execute('PRAGMA journal_mode=WAL')
  c.execute('''CREATE TABLE IF NOT EXISTS observations(path TEXT NOT NULL,concept TEXT NOT NULL,confidence REAL NOT NULL,provider TEXT NOT NULL,model TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'class',geometry TEXT,updated REAL NOT NULL DEFAULT (unixepoch()),PRIMARY KEY(path,concept,provider,model,kind,geometry))''')
  c.execute('''CREATE TABLE IF NOT EXISTS embeddings(path TEXT NOT NULL,provider TEXT NOT NULL,model TEXT NOT NULL,dim INTEGER NOT NULL,vector BLOB NOT NULL,updated REAL NOT NULL DEFAULT (unixepoch()),PRIMARY KEY(path,provider,model))''')
  c.execute('''CREATE TABLE IF NOT EXISTS tracked_files(path TEXT PRIMARY KEY,sha256 TEXT,size INTEGER,mtime REAL,orphaned INTEGER NOT NULL DEFAULT 0,last_seen REAL NOT NULL DEFAULT (unixepoch()))''')
  c.execute('''CREATE TABLE IF NOT EXISTS fs_history(id INTEGER PRIMARY KEY AUTOINCREMENT,op TEXT NOT NULL,payload TEXT NOT NULL,created REAL NOT NULL DEFAULT (unixepoch()),undone REAL,error TEXT)''')
  # migrate 0.2 DB
  for col,decl in [('kind',"TEXT NOT NULL DEFAULT 'class'"),('geometry','TEXT')]:
   try:c.execute(f'ALTER TABLE observations ADD COLUMN {col} {decl}')
   except sqlite3.OperationalError:pass
  # Legacy databases created before geometry was part of the observation identity still
  # have the old PK. That silently collapses multiple boxes of the same concept to one.
  info=c.execute("PRAGMA table_info(observations)").fetchall()
  pkcols=[r['name'] for r in sorted((r for r in info if r['pk']),key=lambda r:r['pk'])]
  wanted=['path','concept','provider','model','kind','geometry']
  if pkcols!=wanted:
   LOG.warning('Migrating legacy observations primary key %s -> %s for multi-instance detections',pkcols,wanted)
   c.execute('''CREATE TABLE observations_v2(
    path TEXT NOT NULL,concept TEXT NOT NULL,confidence REAL NOT NULL,provider TEXT NOT NULL,model TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'class',geometry TEXT,updated REAL NOT NULL DEFAULT (unixepoch()),
    PRIMARY KEY(path,concept,provider,model,kind,geometry))''')
   c.execute('''INSERT OR REPLACE INTO observations_v2(path,concept,confidence,provider,model,kind,geometry,updated)
                SELECT path,concept,confidence,provider,model,kind,geometry,updated FROM observations''')
   c.execute('DROP TABLE observations')
   c.execute('ALTER TABLE observations_v2 RENAME TO observations')
  yield c
  c.commit()
 finally:
  try:
   if c is not None: c.close()
  finally:
   with DB_ACTIVITY:
    DB_ACTIVE-=1
    DB_ACTIVITY.notify_all()
   DB_QUEUE_LOCK.release()



def file_sha256(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def _merge_path_rows(c,src:str,target:str):
 """Relocate an asset's own records. Never blend with an unrelated destination asset."""
 if src==target:return
 # A destination can have fossil analysis even when its file was absent. A move
 # takes ownership of that path; no analysis from the previous occupant survives.
 c.execute('DELETE FROM observations WHERE path=?',(target,))
 c.execute('DELETE FROM embeddings WHERE path=?',(target,))
 c.execute('DELETE FROM tracked_files WHERE path=?',(target,))
 c.execute('UPDATE observations SET path=? WHERE path=?',(target,src))
 c.execute('UPDATE embeddings SET path=? WHERE path=?',(target,src))
 c.execute('UPDATE tracked_files SET path=?,orphaned=0,last_seen=unixepoch() WHERE path=?',(target,src))
 pp=Path(target)
 try:
  st=pp.stat()
  c.execute('INSERT INTO tracked_files(path,size,mtime,orphaned,last_seen) VALUES(?,?,?,0,unixepoch()) ON CONFLICT(path) DO UPDATE SET size=excluded.size,mtime=excluded.mtime,orphaned=0,last_seen=unixepoch()',
   (target,st.st_size,st.st_mtime))
 except OSError:pass

def reconcile_processed_folders():
 """Cheap launch verification: presence only. No hashes and no relocation guesses."""
 global LAUNCH_REPORT
 try:
  with db() as c:
   known={r['path'] for r in c.execute('SELECT path FROM tracked_files').fetchall()}
   known.update(r['path'] for r in c.execute('SELECT DISTINCT path FROM observations').fetchall())
   known.update(r['path'] for r in c.execute('SELECT DISTINCT path FROM embeddings').fetchall())
   missing=[]
   for raw in sorted(known):
    rp=Path(raw)
    if not _volume_root(rp).exists():
     continue
    if rp.is_file():
     c.execute('INSERT OR IGNORE INTO tracked_files(path,orphaned,last_seen) VALUES(?,0,unixepoch())',(raw,))
     c.execute('UPDATE tracked_files SET orphaned=0,last_seen=unixepoch() WHERE path=?',(raw,))
    else:
     missing.append(raw);_cache_mark_path(raw,'purgatory');c.execute('INSERT OR IGNORE INTO tracked_files(path,orphaned,last_seen) VALUES(?,1,unixepoch())',(raw,));c.execute('UPDATE tracked_files SET orphaned=1 WHERE path=?',(raw,))
   c.commit()
   groups={}
   for raw in missing: groups[str(Path(raw).parent)]=groups.get(str(Path(raw).parent),0)+1
   top=sorted(({'folder':k,'missing':v} for k,v in groups.items()),key=lambda x:(-x['missing'],x['folder'].lower()))[:12]
   LAUNCH_REPORT={'ready':True,'known':len(known),'missing':len(missing),'groups':top,'offer_discard':bool(missing),'abandoned_jobs':STALE_JOB_REPORT}
   if missing:LOG.info('Launch verification: %s/%s known files missing',len(missing),len(known))
 except Exception as e:
  LAUNCH_REPORT={'ready':True,'error':str(e),'missing':0,'groups':[],'abandoned_jobs':STALE_JOB_REPORT};LOG.warning('Startup verification failed: %s',e)

def _start_launch_verification_once():
 """Run archive presence verification only after the first grid is stable.

 It is background housekeeping, not part of interactive browse. BRISQUE already waits for
 LAUNCH_REPORT.ready, so this naturally orders: grid stable -> archive verify -> BRISQUE.
 """
 global LAUNCH_VERIFY_STARTED,LAUNCH_REPORT
 with LAUNCH_VERIFY_LOCK:
  if LAUNCH_VERIFY_STARTED:return False
  LAUNCH_VERIFY_STARTED=True
  LAUNCH_REPORT={'ready':False,'deferred':False,'running':True,'missing':0,'groups':[]}
 LOG.info('Launch verification: deferred archive presence check starting after catalog settles')
 threading.Thread(target=_verification_then_janitor,name='n8vision-presence-check',daemon=True).start()
 return True

def _session_janitor():
 """P.53 Sweepy only removes detritus; A/B/0 have explicit lifecycle meaning."""
 while not LAUNCH_REPORT.get('ready'):time.sleep(.5)
 if LAUNCH_REPORT.get('error'):
  LOG.warning('Sweepy skipped because launch verification failed: %s',LAUNCH_REPORT.get('error'));return
 quiet=max(1.0,float(_load_config().get('archive_maintenance',{}).get('quiet_seconds',5) or 5))
 calm=None
 while True:
  paused=_browse_gate_paused();now=time.monotonic()
  if paused:calm=None
  else:
   calm=calm or now
   if now-calm>=quiet:break
  time.sleep(.25)
 keep=[p.name for p in (SESSION_ZERO,SESSION_A,SESSION_B) if p.exists()]
 LOG.info('Sweepy: fixed slots present: %s',', '.join(keep) if keep else 'none')
 removed=0;reclaimed=0
 def sweep(p:Path,why):
  nonlocal removed,reclaimed
  try:
   if not p.exists() or p in (SESSION_ZERO,SESSION_A,SESSION_B):return
   n=p.stat().st_size;p.unlink();removed+=1;reclaimed+=n
   LOG.info('Sweepy: swept %s · %.1f MB · %s',why,n/1048576,p.name)
  except OSError as ex:LOG.warning('Sweepy: could not sweep %s: %s',p,ex)
 # Only names whose lifecycle is explicitly obsolete are automatic garbage.
 for p in SESSIONS.glob('session-malformed-*.sqlite3'):sweep(p,'malformed recovery slot')
 for p in SESSIONS.glob('session-*.working.sqlite3'):sweep(p,'legacy working generation')
 for p in SESSIONS.glob('session-*.sealed.sqlite3'):sweep(p,'legacy sealed generation')
 q=SESSIONS/'quarantine'
 if q.exists():
  for p in q.glob('*'):
   if p.is_file():sweep(p,'quarantined husk')
 for p in DATA.glob('n8vision.malformed-*.sqlite3'):sweep(p,'legacy malformed master')
 LOG.info('Sweepy: shift complete · swept %s · reclaimed %.1f MB · fixed recovery slots untouched',removed,reclaimed/1048576)

def _verification_then_janitor():
 # P.51: make startup housekeeping a real pipeline instead of three racers watching the
 # same ready bit. Verification owns the baton until Sweepy has had first access to the DB;
 # only then may BRISQUE/background inspectors start.
 try:
  reconcile_processed_folders()
  if LAUNCH_REPORT.get('error'):
   LOG.warning('Launch verification: terminal failure; Sweepy will preserve recovery material')
  else:
   LOG.info('Launch verification: complete · %s known · %s missing',LAUNCH_REPORT.get('known',0),LAUNCH_REPORT.get('missing',0))
  LOG.info('Archive janitor: Sweepy has the floor; background inspectors remain parked')
  _session_janitor()
 finally:
  ARCHIVE_MAINTENANCE_DONE.set()
  LOG.info('Startup housekeeping complete: background inspectors released')
  try:_noticer_inspections()
  except Exception:LOG.exception('Initial archive inspection intake failed')

@app.on_event('startup')
def startup_reconcile():
 cfg=_load_config()
 if bool(cfg.get('enable_public')) and bool(cfg.get('public_auto_start')):
  def _public_boot():
   try:_start_public_tunnel()
   except Exception as e:LOG.warning('Public portal auto-start failed: %s',e)
  threading.Thread(target=_public_boot,name='n8-public-start',daemon=True).start()
 if EDITION['processing']:threading.Thread(target=_startup_comfy_tool_shelf_scan,name='n8vision-comfy-shelf-scan',daemon=True).start()
 # Presence verification used to start immediately and hammer the same filesystem while the
 # first recursive browse was trying to enumerate it. Defer it until the client has a stable grid.
 threading.Thread(target=_cache_maintenance,name='n8vision-cache-maintenance',daemon=True).start()
 if EDITION['inference']:threading.Thread(target=_background_brisque_service,name='n8vision-background-observations',daemon=True).start()

@app.get('/api/launch-verification')
def launch_verification():
 return {**LAUNCH_REPORT,'maintenance_done':ARCHIVE_MAINTENANCE_DONE.is_set(),'browse_paused':_browse_gate_paused()}

@app.get('/api/inspectors/status')
def inspectors_status():
 with db() as c:
  missing_sanity=c.execute("SELECT COUNT(*) FROM tracked_files t WHERE t.orphaned=0 AND NOT EXISTS (SELECT 1 FROM observations o WHERE o.path=t.path AND o.provider='native-raster-sanity' AND o.kind='receipt')").fetchone()[0]
  missing_brisque=c.execute("SELECT COUNT(*) FROM tracked_files t WHERE t.orphaned=0 AND NOT EXISTS (SELECT 1 FROM observations o WHERE o.path=t.path AND o.provider=? AND o.model=? AND o.concept='brisque_raw')",(BRISQUE_OBS_PROVIDER,BRISQUE_OBS_MODEL)).fetchone()[0]
 return {'validation_started':LAUNCH_VERIFY_STARTED,'validation_ready':bool(LAUNCH_REPORT.get('ready')),'maintenance_done':ARCHIVE_MAINTENANCE_DONE.is_set(),'browse_paused':_browse_gate_paused(),'unscanned_sanity':missing_sanity,'unscanned_brisque':missing_brisque,'automatic_jobs':[{'id':j['id'],'state':j['state'],'total':j['total']} for j in list(JOBS.values()) if j.get('kind')=='sanity-v4' and j.get('state') in ('queued','running')]}


class ShutdownRequest(BaseModel):
 discard_invalids:bool=False

def _verify_and_checkpoint_working():
 c=sqlite3.connect(DB_PATH,timeout=30)
 try:
  c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
  row=c.execute('PRAGMA quick_check').fetchone()
  if not row or row[0]!='ok': raise RuntimeError('Working session failed SQLite quick_check')
 finally:
  c.close()

def _seal_session():
 """P.53 clean shutdown: verified live 0 becomes A. B is never rewritten at shutdown."""
 _verify_and_checkpoint_working()
 if not sqlite_ok(SESSION_ZERO):raise RuntimeError('Live session 0 failed final verification')
 # An old A can only exist when it was not consumed/promoted at this launch (e.g. unusual
 # transition state). Replace it only after 0 has passed verification.
 SESSION_A.unlink(missing_ok=True)
 SESSION_ZERO.replace(SESSION_A)
 for suffix in ('-wal','-shm'):
  Path(str(SESSION_ZERO)+suffix).unlink(missing_ok=True)
 LOG.info('Recovery slots: clean shutdown promoted 0 -> A; B left untouched')
 return SESSION_A

@app.post('/api/clean-shutdown')
def clean_shutdown(req:ShutdownRequest):
 global STOP_REQUESTED,DB_ACCEPTING
 if req.discard_invalids: purge_orphans()
 STOP_REQUESTED=True
 with LOCK:
  for j in JOBS.values():
   if j.get('state') in ('queued','running'):j['cancel_requested']=True;j['updated']=time.time()
 _write_active_job_journal()
 deadline=time.time()+30; active=[]
 while time.time()<deadline:
  with LOCK: active=[x for x in JOBS.values() if x.get('state') in ('queued','running')]
  if not active: break
  time.sleep(.1)
 with DB_ACTIVITY:
  DB_ACCEPTING=False
  while DB_ACTIVE and time.time()<deadline:
   DB_ACTIVITY.wait(timeout=max(.01,deadline-time.time()))
  if DB_ACTIVE:
   DB_ACCEPTING=True; STOP_REQUESTED=False
   raise HTTPException(503,f'Clean shutdown timed out waiting for {DB_ACTIVE} database connection(s)')
 try:
  sealed=_seal_session()
 except Exception:
  with DB_ACTIVITY: DB_ACCEPTING=True
  STOP_REQUESTED=False
  raise
 global SHUTDOWN_SEALED
 SHUTDOWN_SEALED=True
 SHUTDOWN_BROWSER_ACK.clear()
 def finish_after_browser():
  # Browser gets the response while the server is still alive. Its pagehide/unload beacon
  # acknowledges that the tab actually began closing. Fallback prevents an immortal console
  # when a browser refuses scripted close.
  SHUTDOWN_BROWSER_ACK.wait(timeout=8.0)
  time.sleep(.20)
  os._exit(0)
 threading.Thread(target=finish_after_browser,name='shutdown-browser-handshake',daemon=True).start()
 return {'ok':True,'session':sealed.name,'active_abandoned':len(active),'awaiting_browser_close':True}

@app.post('/api/clean-shutdown/browser-closing')
def clean_shutdown_browser_closing():
 if SHUTDOWN_SEALED:SHUTDOWN_BROWSER_ACK.set()
 return {'ok':True}


@app.post('/api/restart-server')
def restart_server():
 """Restart only the N8Vision process. The browser remains open and reconnects in place."""
 global STOP_REQUESTED,DB_ACCEPTING
 STOP_REQUESTED=True
 with LOCK:
  for j in JOBS.values():
   if j.get('state') in ('queued','running'):j['cancel_requested']=True;j['updated']=time.time()
 _write_active_job_journal()
 deadline=time.time()+30
 while time.time()<deadline:
  with LOCK: active=[x for x in JOBS.values() if x.get('state') in ('queued','running')]
  if not active:break
  time.sleep(.1)
 with DB_ACTIVITY:
  DB_ACCEPTING=False
  while DB_ACTIVE and time.time()<deadline:DB_ACTIVITY.wait(timeout=max(.01,deadline-time.time()))
  if DB_ACTIVE:
   DB_ACCEPTING=True;STOP_REQUESTED=False
   raise HTTPException(503,f'Restart timed out waiting for {DB_ACTIVE} database connection(s)')
 try:_verify_and_checkpoint_working()
 except Exception:
  with DB_ACTIVITY:DB_ACCEPTING=True
  STOP_REQUESTED=False
  raise
 def relaunch():
  time.sleep(.35)
  args=[sys.executable,str(ROOT/'run.py'),'--no-browser','--instance-restart','--edition',EDITION['edition'],'--port',str(os.environ.get('N8VISION_PORT','8189'))]
  host=os.environ.get('N8VISION_BIND_HOST')
  if host:args.extend(['--host',host])
  os.execv(sys.executable,args)
 threading.Thread(target=relaunch,name='n8vision-restart',daemon=True).start()
 return {'ok':True,'restarting':True}

@app.get('/api/orphans')
def orphan_status():
 with db() as c:
  files=c.execute('SELECT COUNT(*) FROM tracked_files WHERE orphaned=1').fetchone()[0]
  obs=c.execute('SELECT COUNT(*) FROM observations WHERE path IN (SELECT path FROM tracked_files WHERE orphaned=1)').fetchone()[0]
  emb=c.execute('SELECT COUNT(*) FROM embeddings WHERE path IN (SELECT path FROM tracked_files WHERE orphaned=1)').fetchone()[0]
 return {'files':files,'observations':obs,'embeddings':emb}

@app.post('/api/orphans/purge')
def purge_orphans():
 with db() as c:
  paths=[r['path'] for r in c.execute('SELECT path FROM tracked_files WHERE orphaned=1').fetchall()]
  if paths:
   c.execute('DELETE FROM observations WHERE path IN (SELECT path FROM tracked_files WHERE orphaned=1)')
   c.execute('DELETE FROM embeddings WHERE path IN (SELECT path FROM tracked_files WHERE orphaned=1)')
   c.execute('DELETE FROM tracked_files WHERE orphaned=1')
 return {'purged_files':len(paths)}

def norm(raw:str)->Path:
 try:return Path(raw).expanduser().resolve()
 except Exception as e:raise HTTPException(400,f'Invalid path: {e}')
def _volume_root(p:Path)->Path:
 p=p.resolve()
 if os.name=='nt': return Path(p.drive+'\\') if p.drive else Path(ROOT.anchor)
 return Path('/')

def _volume_key(p:Path)->str:
 root=_volume_root(p)
 if os.name=='nt':
  try:
   import ctypes
   serial=ctypes.c_ulong();maxcomp=ctypes.c_ulong();flags=ctypes.c_ulong()
   ok=ctypes.windll.kernel32.GetVolumeInformationW(str(root),None,0,ctypes.byref(serial),ctypes.byref(maxcomp),ctypes.byref(flags),None,0)
   if ok:return f'winvol:{serial.value:08X}'
  except Exception:pass
 return 'root:'+str(root).casefold()

def _detected_storage_class(p:Path)->str:
 if os.name!='nt':return 'fixed'
 try:
  import ctypes;typ=int(ctypes.windll.kernel32.GetDriveTypeW(str(_volume_root(p))))
  return {2:'removable',3:'fixed',4:'network',5:'removable',6:'volatile'}.get(typ,'fixed')
 except Exception:return 'fixed'

def storage_class(p:Path)->str:
 cfg=_load_config();entry=cfg.get('storage_classes',{}).get(_volume_key(p),{})
 chosen=str(entry.get('class','auto')) if isinstance(entry,dict) else str(entry or 'auto')
 return _detected_storage_class(p) if chosen=='auto' else chosen

def _default_thumbnail_cache_root(source:Path|None=None)->Path:
 return _volume_root(source or ROOT)/'.N8VisionCache'

def thumbnail_cache_root(source:Path|None=None)->Path:
 cfg=_load_config();raw=str(cfg.get('thumbnail_cache',{}).get('path','') or '').strip()
 return norm(raw) if raw else _default_thumbnail_cache_root(source)

def _inside(path:Path,root:Path)->bool:
 try:path.relative_to(root);return True
 except ValueError:return False

def _cache_db(root:Path):
 root.mkdir(parents=True,exist_ok=True);c=sqlite3.connect(root/'cache-index.sqlite3',timeout=15);c.row_factory=sqlite3.Row
 c.execute("CREATE TABLE IF NOT EXISTS assets(source_path TEXT NOT NULL,content_sha TEXT,size INTEGER,mtime_ns INTEGER,kind TEXT NOT NULL,asset_path TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'active',volume_key TEXT,updated REAL NOT NULL,PRIMARY KEY(source_path,kind,asset_path))")
 c.execute('CREATE INDEX IF NOT EXISTS idx_cache_identity ON assets(content_sha,size,mtime_ns,kind,state)');return c

def _tracked_sha(path:str)->str|None:
 try:
  with db() as c:
   r=c.execute('SELECT sha256 FROM tracked_files WHERE path=?',(path,)).fetchone();return r['sha256'] if r else None
 except Exception:return None

def _cache_trim_thumbnails(root:Path):
 cfg=_load_config();limit=max(16,int(cfg.get('thumbnail_cache',{}).get('max_mb',200)))*1024*1024;now=time.time();key=str(root)
 if now-THUMB_TRIM_LAST.get(key,0)<5:return
 THUMB_TRIM_LAST[key]=now
 try:
  c=_cache_db(root);rows=c.execute("SELECT asset_path,updated FROM assets WHERE kind='thumbnail' ORDER BY updated ASC").fetchall();items=[];total=0
  for r in rows:
   p=Path(r['asset_path'])
   try:size=p.stat().st_size
   except OSError:size=0
   items.append((p,size));total+=size
  for p,size in items:
   if total<=limit:break
   try:p.unlink(missing_ok=True)
   except OSError:continue
   c.execute("DELETE FROM assets WHERE kind='thumbnail' AND asset_path=?",(str(p),));total-=size
  c.commit();c.close()
 except Exception as e:LOG.debug('Thumbnail cache trim skipped: %s',e)

def _cache_register(source:Path,kind:str,asset:Path):
 try:
  st=source.stat();root=thumbnail_cache_root(source);sha=_tracked_sha(str(source))
  with _cache_db(root) as c:c.execute('INSERT OR REPLACE INTO assets(source_path,content_sha,size,mtime_ns,kind,asset_path,state,volume_key,updated) VALUES(?,?,?,?,?,?,?,?,?)',(str(source),sha,st.st_size,st.st_mtime_ns,kind,str(asset),'active',_volume_key(source),time.time()))
  if kind=='thumbnail':_cache_trim_thumbnails(root)
 except Exception as e:LOG.debug('Cache index register skipped: %s',e)

def _cache_reusable(source:Path,kind:str)->Path|None:
 try:
  root=thumbnail_cache_root(source);st=source.stat();sha=_tracked_sha(str(source));c=_cache_db(root)
  try:
   row=c.execute("SELECT * FROM assets WHERE content_sha=? AND kind=? AND state IN ('active','purgatory') ORDER BY updated DESC LIMIT 1",(sha,kind)).fetchone() if sha else None
   if not row:row=c.execute("SELECT * FROM assets WHERE size=? AND mtime_ns=? AND kind=? AND state IN ('active','purgatory') ORDER BY updated DESC LIMIT 1",(st.st_size,st.st_mtime_ns,kind)).fetchone()
   if row and Path(row['asset_path']).is_file():
    c.execute("UPDATE assets SET source_path=?,content_sha=COALESCE(?,content_sha),state='active',volume_key=?,updated=? WHERE asset_path=?",(str(source),sha,_volume_key(source),time.time(),row['asset_path']));c.commit();return Path(row['asset_path'])
  finally:c.close()
 except Exception:pass
 return None

def _cache_mark_path(raw:str,state='purgatory',new_path:str|None=None,content_sha:str|None=None):
 p=Path(raw);root=thumbnail_cache_root(p)
 try:
  c=_cache_db(root)
  if new_path:c.execute("UPDATE assets SET source_path=?,content_sha=COALESCE(?,content_sha),state='active',updated=? WHERE source_path=?",(new_path,content_sha,time.time(),raw))
  else:c.execute('UPDATE assets SET state=?,updated=? WHERE source_path=?',(state,time.time(),raw))
  c.commit();c.close()
 except Exception:pass

def _mounted_roots():
 if os.name=='nt':
  import string;return [f'{d}:\\' for d in string.ascii_uppercase if Path(f'{d}:\\').exists()]
 return ['/']

def _cache_maintenance():
 cfg=_load_config();tc=cfg.get('thumbnail_cache',{})
 if not bool(tc.get('delete_orphans_on_maintenance',True)):return {'deleted':0}
 raw=str(tc.get('path','') or '').strip();roots=[Path(raw)] if raw else [_default_thumbnail_cache_root(Path(x)) for x in _mounted_roots()]
 deleted=0
 for root in dict.fromkeys(roots):
  if not root.exists():continue
  try:
   c=_cache_db(root);rows=c.execute("SELECT asset_path FROM assets WHERE state='purgatory'").fetchall()
   for r in rows:
    try:Path(r['asset_path']).unlink(missing_ok=True);deleted+=1
    except Exception:pass
   c.execute("DELETE FROM assets WHERE state='purgatory'");c.commit();c.close()
  except Exception:pass
 return {'deleted':deleted}

def image_file(p):
 if not (p.is_file() and p.suffix.lower() in IMAGE_EXTS):return False
 try:
  if _inside(p.resolve(),thumbnail_cache_root(p).resolve()):return False
 except Exception:pass
 return True

def module(name):
 try:
  m=__import__(name); return True,getattr(m,'__version__','installed')
 except Exception as e:return False,str(e)
def hardware_status():
 if not EDITION['inference']:return {'cpu':{'logical':os.cpu_count() or 1},'accelerator':{'kind':'cpu','available':False,'reason':'Inference disabled in Lite'}}
 out={'cpu':{'logical':os.cpu_count() or 1},'accelerator':{'kind':'cpu','available':False}}
 try:
  import torch
  out['torch']=getattr(torch,'__version__','unknown')
  out['accelerator']['cuda_build']=getattr(torch.version,'cuda',None)
  if torch.cuda.is_available():
   i=torch.cuda.current_device();prop=torch.cuda.get_device_properties(i)
   out['accelerator'].update({'kind':'cuda','available':True,'device':i,'name':torch.cuda.get_device_name(i),'vram_gb':round(prop.total_memory/(1024**3),1),'capability':list(torch.cuda.get_device_capability(i))})
  else:out['accelerator']['reason']='torch.cuda.is_available() is false'
 except Exception as e:out['accelerator']['reason']=f'{type(e).__name__}: {e}'
 return out

def _accelerator_device():
 try:
  import torch
  return 'cuda' if torch.cuda.is_available() else 'cpu'
 except Exception:return 'cpu'

def _amp_context(torch,device):
 # CLIP/transformer inference belongs on Tensor cores when CUDA is available.
 # autocast keeps model storage simple while dispatching eligible GEMMs/convolutions in FP16.
 return torch.autocast(device_type='cuda',dtype=torch.float16) if device=='cuda' else __import__('contextlib').nullcontext()

def _module_device_dtype(module):
 try:
  param=next(module.parameters())
  return str(param.device),str(param.dtype).replace('torch.','')
 except Exception:
  return 'unknown','unknown'

def _yuan_device_report(extractor):
 """Report the actual devices used inside Yuan's third-party extractor."""
 out={}
 for label,obj,attr in (
  ('semantic_clip',getattr(extractor,'clip_model',None),'model'),
  ('aesthetic_clip',getattr(extractor,'laion_model',None),'clip_model'),
  ('aesthetic_head',getattr(extractor,'laion_model',None),'aesthetic_model')):
  mod=getattr(obj,attr,None) if obj is not None else None
  if mod is not None: out[label]=dict(zip(('device','dtype'),_module_device_dtype(mod)))
 return out

def provider_status():
 if not EDITION['inference']:return [{'id':'archive','name':'Archive and filesystem','installed':True,'detail':'Lite: inference environments are not initialized'}]
 out=[]
 for ident,name,mods in [('clip','CLIP classification + embeddings',['torch','transformers']),('quality','Yuan image quality (1–10)',['torch','huggingface_hub','safetensors']),('faiss','FAISS vector search',['faiss']),('yolo','Ultralytics detector / segmenter',['ultralytics']),('sam','SAM box-to-mask segmentation',['torch','transformers'])]:
  checks=[module(x) for x in mods]
  installed=all(x[0] for x in checks); detail=' · '.join(f'{m}: {v}' for m,(_,v) in zip(mods,checks))
  if ident=='clip' and installed:
   try:
    from transformers.models.clip.modeling_clip import CLIPModel
    from transformers.models.clip.processing_clip import CLIPProcessor
    hw=hardware_status();acc=hw.get('accelerator',{})
    detail+=f" · CLIP import: ready · target: {acc.get('kind','cpu').upper()}"
    if acc.get('name'):detail+=f" ({acc['name']})"
   except Exception as e:
    installed=False; detail+=f' · CLIP import FAILED: {type(e).__name__}: {e}'
  out.append({'id':ident,'name':name,'installed':installed,'detail':detail})
 return out
@app.get('/')
def index():return FileResponse(STATIC/'index.html',headers={'Cache-Control':'no-store, max-age=0'})
@app.get('/api/health')
def health():return {'ok':True,'version':'I.2','providers':provider_status(),'hardware':hardware_status()}
@app.get('/api/roots')
def roots():return {'roots':_mounted_roots()}

def _archive_roots_cfg():
 cfg=_load_config();out=[]
 for raw in cfg.get('archive_roots',[]):
  try:
   p=norm(str(raw))
   if p.exists() and p.is_dir():out.append(str(p))
  except Exception:pass
 return out

def _path_contains(parent:Path,child:Path)->bool:
 try:child.resolve().relative_to(parent.resolve());return True
 except Exception:return False

def _is_volume_root(p:Path)->bool:
 try:return p.resolve()==_volume_root(p).resolve()
 except Exception:return False

@app.get('/api/archive-roots')
def archive_roots():return {'roots':_archive_roots_cfg()}

@app.post('/api/archive-roots/scan')
def archive_root_scan(payload:dict):
 p=norm(str(payload.get('path','')))
 if not p.exists() or not p.is_dir():raise HTTPException(404,'Directory not found')
 # Hygiene: whole-volume adoption is intentionally config-file-only. It remains legal
 # when explicitly written into archive_roots by an operator.
 if _is_volume_root(p):raise HTTPException(403,'Volume roots may only be registered in n8vision_config.json')
 cfg=_load_config();roots=[]
 for raw in cfg.get('archive_roots',[]):
  try:
   q=norm(str(raw))
   if q.exists() and q.is_dir():roots.append(q)
  except Exception:pass
 # Already enclosed means there is nothing new to promote.
 enclosing=next((q for q in roots if _path_contains(q,p)),None)
 if enclosing:return {'ok':True,'root':str(enclosing),'roots':[str(x) for x in roots],'already_covered':True,'absorbed':[]}
 # Bottom-up promotion: adopting an ancestor absorbs descendant root headers. Image
 # intelligence is path-addressed, so no observations/embeddings are discarded or recopied.
 absorbed=[q for q in roots if _path_contains(p,q)]
 roots=[q for q in roots if q not in absorbed];roots.append(p)
 roots=sorted(dict.fromkeys(roots),key=lambda x:str(x).casefold())
 cfg['archive_roots']=[str(x) for x in roots];_save_config(cfg)
 return {'ok':True,'root':str(p),'roots':[str(x) for x in roots],'absorbed':[str(x) for x in absorbed]}

def obs_for(paths,prefix=None):
 # Browse used to scan every observation below the directory prefix and discard rows
 # that were not in the current file snapshot.  On large recursive roots that can turn
 # one browse into a huge DB read while analysis is also writing observations.  Query
 # only the files we are actually returning, in SQLite-friendly chunks.
 obs={x:[] for x in paths}
 if paths:
  with db() as c:
   step=800
   for start in range(0,len(paths),step):
    chunk=paths[start:start+step]
    marks=','.join('?'*len(chunk))
    rows=c.execute(f'SELECT path,concept,confidence,provider,model,kind,geometry FROM observations WHERE path IN ({marks})',chunk).fetchall()
    for r in rows:obs[r['path']].append(dict(r))
 from .observation_display import annotate
 return {path:annotate(rows) for path,rows in obs.items()}
# P.29 chunk-pipe browse sessions.  The old monolithic /api/browse remains below as a
# compatibility path, but the web client uses start/chunk so large libraries never have to
# survive one enormous JSON response.  Prepared chunks are bounded and disposable.
BROWSE_CHUNK_SIZE=500
BROWSE_SESSIONS:dict[str,dict[str,Any]]={}
BROWSE_SESSIONS_LOCK=threading.RLock()

# I.2t: shared directory stamps; one background sweep, no verification jobs.
from .noticer import NewNoticer
NOTICERS={}
NOTICERS_LOCK=threading.RLock()
INSPECTION_INTAKE_LOCK=threading.Lock()
def _get_noticer(path,recursive):
 key=(str(path),bool(recursive))
 with NOTICERS_LOCK:
  if key not in NOTICERS:NOTICERS[key]=NewNoticer(path,recursive,IMAGE_EXTS)
  return NOTICERS[key]

def _noticer_register(watcher):
 # Commit before advancing: DB failures keep the same batch eligible for retry.
 with watcher.lock:
  records=list(watcher.events[watcher.intake_cursor:])
  if not records:return 0
  with db() as c:
   before=c.total_changes
   c.executemany("INSERT INTO tracked_files(path,size,mtime,orphaned,last_seen) VALUES(?,?,?,0,unixepoch()) ON CONFLICT(path) DO NOTHING",
    [(x['path'],x['size'],x['mtime']) for x in records])
   inserted=c.total_changes-before
  watcher.intake_cursor+=len(records)
 return inserted

def _noticer_inspections():
 if not EDITION['inference']:return None
 with INSPECTION_INTAKE_LOCK:return _noticer_inspections_locked()

def _noticer_inspections_locked():
 # Preserve the startup/foreground gates and submit one bounded Sanity bite.
 if not ARCHIVE_MAINTENANCE_DONE.is_set() or _browse_gate_paused():return None
 with LOCK:
  if any(j.get('state') in ('queued','running') and j.get('kind')=='sanity-v4' for j in JOBS.values()):return None
 with db() as c:
  paths=[r['path'] for r in c.execute("SELECT t.path FROM tracked_files t WHERE t.orphaned=0 AND NOT EXISTS (SELECT 1 FROM observations o WHERE o.path=t.path AND o.provider='native-raster-sanity' AND o.kind='receipt') LIMIT 128").fetchall()]
 if not paths:return None
 cfg=_load_config().get('sanity',{})
 req=RasterSanityRequest(paths=paths,**{k:cfg[k] for k in ('thumbnail','edge_threshold','light_blur','medium_blur','heavy_blur','grade_b_largest_fraction') if k in cfg})
 job=raster_sanity_v4(req)
 LOG.info('Automatic Sanity queued %d files · job=%s',len(paths),job['id'])
 return job

def _noticer_tick():
 # Configured archives participate even when no browser catalog is mounted.
 for raw in _archive_roots_cfg():_get_noticer(norm(raw),True)
 with NOTICERS_LOCK:watchers=list(NOTICERS.values())
 for watcher in watchers:
  if STOP_REQUESTED:return
  try:
   watcher.sweep();registered=_noticer_register(watcher)
   if registered:LOG.info('New Noticer: %s · %d new image(s)',watcher.root,registered)
  except Exception:LOG.exception('New Noticer intake failed: %s',watcher.root)
 # A seeded archive is sufficient to start initial validation when no browse
 # is preparing. Do not depend forever on a browser grid-ready acknowledgement.
 if not LAUNCH_VERIFY_STARTED and watchers and not _browse_gate_paused():
  _start_launch_verification_once()
 try:_noticer_inspections()
 except Exception:LOG.exception('New Noticer automatic inspection failed')

def _noticer_background():
 while not STOP_REQUESTED:
  _noticer_tick()
  time.sleep(10)

@app.on_event('startup')
def start_new_noticer():
 threading.Thread(target=_noticer_background,name='n8-new-noticer',daemon=True).start()

@app.get('/api/browse/new')
def browse_new(path:str=Query(...),recursive:bool=False,since:int=Query(0,ge=0),epoch:str=Query('')):
 watcher=_get_noticer(norm(path),recursive)
 if time.monotonic()-watcher.last_check>9:
  watcher.sweep()
 packet=watcher.packet(since if epoch==watcher.epoch else 0)
 obs=obs_for([x['path'] for x in packet['files']])
 for record in packet['files']:record['observations']=obs.get(record['path'],[])
 packet['observation_revision']=OBS_REV
 return packet

def _browse_chunk_worker(token:str,p:Path,recursive:bool):
 from .filesystem_order import ordered_paths
 t0=time.perf_counter();total=0;batch=[]
 try:
  def candidates():
   watcher=_get_noticer(p,recursive)
   watcher.sweep()
   with watcher.lock:
    paths=list(watcher.files);notice_cursor=len(watcher.events);notice_epoch=watcher.epoch
   with BROWSE_SESSIONS_LOCK:
    sess=BROWSE_SESSIONS.get(token)
    if sess:sess['notice_cursor']=notice_cursor;sess['notice_epoch']=notice_epoch
   for raw in ordered_paths(paths):yield Path(raw)
  def publish(paths,chunk_index=None):
   nonlocal total
   records=[]
   for x in paths:
    try:st=x.stat()
    except (FileNotFoundError,PermissionError,OSError):continue
    record={'name':x.name,'path':str(x),'size':st.st_size,'mtime':st.st_mtime}
    if BROWSE_SESSIONS.get(token,{}).get('mobile'):
     try:
      with Image.open(x) as image:
       w,h=image.size
       if image.format in {'JPEG','TIFF','WEBP'} and image.getexif().get(274,1) in (5,6,7,8):w,h=h,w
      record.update(width=w,height=h)
     except (OSError,ValueError):pass
    records.append(record)
   if records:
    obs=obs_for([x['path'] for x in records])
    for x in records:x['observations']=obs.get(x['path'],[])
    # Preserve the global directory/filename order across chunk boundaries.
   with BROWSE_SESSIONS_LOCK:
    sess=BROWSE_SESSIONS.get(token)
    if not sess or sess.get('cancelled'):return False
    if chunk_index is None:
     chunk_index=len(sess['chunks']);sess['chunks'].append(records)
    else:sess['chunks'][chunk_index]=records
    total+=len(records);sess['prepared']=total;sess['updated']=time.monotonic()
   LOG.info('Browse chunk prepared: tx=%s · chunk=%d · %d files · prepared=%d',token,chunk_index,len(records),total)
   return True
  with BROWSE_SESSIONS_LOCK:paged=bool(BROWSE_SESSIONS.get(token,{}).get('paged'))
  if paged:
   paths=list(candidates())
   with BROWSE_SESSIONS_LOCK:
    sess=BROWSE_SESSIONS.get(token)
    if not sess or sess.get('cancelled'):return
    sess.update(paths_ready=True,path_index=paths,total_files=len(paths),total_chunks=(len(paths)+BROWSE_CHUNK_SIZE-1)//BROWSE_CHUNK_SIZE)
   LOG.info('Windowed catalog indexed: tx=%s · %s paths · page metadata prepared only on request',token,len(paths))
   while not STOP_REQUESTED:
    with BROWSE_SESSIONS_LOCK:
     sess=BROWSE_SESSIONS.get(token)
     if not sess or sess.get('cancelled'):return
     pending=sorted(i for i in sess['requested_pages'] if i not in sess['chunks'] and i<sess['total_chunks'])
     index=pending[0] if pending else None
    if index is None:time.sleep(.05);continue
    start=index*BROWSE_CHUNK_SIZE
    if not publish(paths[start:start+BROWSE_CHUNK_SIZE],index):return
   return
  for x in candidates():
   with BROWSE_SESSIONS_LOCK:
    sess=BROWSE_SESSIONS.get(token)
    if not sess or sess.get('cancelled'):return
   batch.append(x)
   if len(batch)>=BROWSE_CHUNK_SIZE:
    if not publish(batch):return
    batch=[]
  if batch and not publish(batch):return
  with BROWSE_SESSIONS_LOCK:
   sess=BROWSE_SESSIONS.get(token)
   if sess and not sess.get('cancelled'):
    sess['complete']=True;sess['prepared']=total;sess['updated']=time.monotonic();sess['completed_at']=time.monotonic()
  LOG.info('Browse chunks complete: %s · recursive=%s · %d files · %.3fs total',p,recursive,total,time.perf_counter()-t0)
 except Exception as e:
  LOG.exception('Browse chunk worker failed: %s · recursive=%s',p,recursive)
  with BROWSE_SESSIONS_LOCK:
   sess=BROWSE_SESSIONS.get(token)
   if sess:sess['error']=f'{type(e).__name__}: {e}';sess['complete']=True;sess['updated']=time.monotonic();sess['completed_at']=time.monotonic()


DIRECTORY_TREE_CACHE={}
DIRECTORY_TREE_LOCK=threading.Lock()
@app.get('/api/directories')
def directories(path:str=Query(...)):
 p=norm(path);key=str(p).casefold()
 try:
  st=p.stat()
  if not p.is_dir():raise HTTPException(404,'Directory not found')
  signature=(st.st_dev,st.st_ino,st.st_mtime_ns,st.st_ctime_ns)
  with DIRECTORY_TREE_LOCK:
   cached=DIRECTORY_TREE_CACHE.get(key)
   if cached and cached[0]==signature:return cached[1]
   dirs=sorted((x for x in p.iterdir() if x.is_dir()),key=lambda x:x.name.casefold())
   result={'path':str(p),'parent':str(p.parent) if p.parent!=p else None,'directories':[{'name':x.name,'path':str(x)} for x in dirs]}
   after=p.stat()
   if signature==(after.st_dev,after.st_ino,after.st_mtime_ns,after.st_ctime_ns):
    if len(DIRECTORY_TREE_CACHE)>=2048:DIRECTORY_TREE_CACHE.pop(next(iter(DIRECTORY_TREE_CACHE)))
    DIRECTORY_TREE_CACHE[key]=(signature,result)
   return result
 except FileNotFoundError:
  with DIRECTORY_TREE_LOCK:DIRECTORY_TREE_CACHE.pop(key,None)
  raise HTTPException(404,'Directory not found')
 except PermissionError:raise HTTPException(403,'Permission denied')

@app.get('/api/browse/start')
def browse_start(path:str=Query(...),recursive:bool=False,tx:str=Query(''),mobile:bool=False,windowed:bool=False,previous_tx:str=Query('')):
 p=norm(path);tx=tx or uuid.uuid4().hex
 if not p.exists() or not p.is_dir():raise HTTPException(404,'Directory not found')
 _browse_gate_begin(tx,str(p),recursive)
 try:dirs=sorted((x for x in p.iterdir() if x.is_dir()),key=lambda x:x.name.casefold())
 except PermissionError:
  _browse_gate_stable(tx);raise HTTPException(403,'Permission denied')
 # Desktop preparation retains its existing supersession behavior. Mobile snapshots remain
 # available for reverse paging until their caller explicitly replaces its previous transaction.
 with BROWSE_SESSIONS_LOCK:
  for old,sess in list(BROWSE_SESSIONS.items()):
   if old!=tx and not sess.get('paged',sess.get('mobile')):sess['cancelled']=True
  if previous_tx and previous_tx!=tx:
   previous=BROWSE_SESSIONS.get(previous_tx)
   if previous and previous.get('paged',previous.get('mobile')):
    previous['cancelled']=True;previous['chunks'].clear()
  BROWSE_SESSIONS[tx]={'path':str(p),'recursive':recursive,'mobile':mobile,'paged':mobile or windowed,'requested_pages':set(),'paths_ready':False,'chunks':{} if mobile or windowed else [],'complete':False,'error':None,'prepared':0,'cancelled':False,'updated':time.monotonic()}
 threading.Thread(target=_browse_chunk_worker,args=(tx,p,recursive),name=f'browse-{tx[:8]}',daemon=True).start()
 LOG.info('Browse chunk pipe opened: tx=%s · %s · recursive=%s · bite=%d · mode=%s',tx,p,recursive,BROWSE_CHUNK_SIZE,'mobile demand' if mobile else 'desktop window demand' if windowed else 'full catalog')
 return {'browse_tx':tx,'path':str(p),'parent':str(p.parent) if p.parent!=p else None,'directories':[{'name':x.name,'path':str(x)} for x in dirs],'recursive':recursive,'chunk_size':BROWSE_CHUNK_SIZE}

@app.get('/api/browse/range')
def browse_range(tx:str=Query(...),first:int=Query(...,ge=0),last:int=Query(...,ge=0)):
 if last<first or last-first>=200000:raise HTTPException(400,'Invalid selection range')
 with BROWSE_SESSIONS_LOCK:
  sess=BROWSE_SESSIONS.get(tx)
  if not sess or sess.get('cancelled'):raise HTTPException(409,'Browse changed; choose the selection anchor again')
  paths=sess.get('path_index')
  if paths is None:raise HTTPException(409,'Archive index not ready; retry selection')
  if last>=len(paths):raise HTTPException(400,'Selection range exceeds archive')
  result=[{'path':str(path),'index':index} for index,path in enumerate(paths[first:last+1],first)]
 return {'browse_tx':tx,'paths':result}

@app.get('/api/browse/chunk')
def browse_chunk(tx:str=Query(...),index:int=Query(...,ge=0)):
 # Brief long-poll avoids a hot request loop while the disk is preparing the next bite.
 deadline=time.monotonic()+1.0
 while True:
  with BROWSE_SESSIONS_LOCK:
   sess=BROWSE_SESSIONS.get(tx)
   if not sess:raise HTTPException(404,'Browse transaction expired')
   if sess.get('cancelled'):raise HTTPException(409,'Browse transaction superseded')
   chunks=sess['chunks']
   if sess.get('paged'):
    sess['requested_pages'].add(index)
    if sess.get('error'):return {'browse_tx':tx,'index':index,'files':[],'prepared':sess['prepared'],'complete':True,'error':sess['error']}
    if sess.get('paths_ready') and (index in chunks or index>=sess['total_chunks']):
     return {'browse_tx':tx,'index':index,'files':chunks.get(index,[]),'prepared':sess['total_files'],'metadata_prepared':sess['prepared'],'complete':index>=sess['total_chunks']-1,'error':None,'notice_cursor':sess.get('notice_cursor',0),'notice_epoch':sess.get('notice_epoch','')}
   elif index<len(chunks):
    return {'browse_tx':tx,'index':index,'files':chunks[index],'prepared':sess['prepared'],'complete':bool(sess['complete'] and index==len(chunks)-1),'error':sess.get('error'),'notice_cursor':sess.get('notice_cursor',0),'notice_epoch':sess.get('notice_epoch','')}
   if sess['complete']:
    return {'browse_tx':tx,'index':index,'files':[],'prepared':sess['prepared'],'complete':True,'error':sess.get('error'),'notice_cursor':sess.get('notice_cursor',0),'notice_epoch':sess.get('notice_epoch','')}
  if time.monotonic()>=deadline:return {'browse_tx':tx,'index':index,'files':[],'prepared':sess['prepared'],'complete':False,'waiting':True}
  time.sleep(.05)

@app.get('/api/browse')
def browse(path:str=Query(...),recursive:bool=False,tx:str=Query('')):
 p=norm(path); t0=time.perf_counter(); tx=tx or uuid.uuid4().hex; _browse_gate_begin(tx,str(p),recursive)
 if not p.exists() or not p.is_dir():
  _browse_gate_stable(tx);raise HTTPException(404,'Directory not found')
 try:
  t=time.perf_counter();dirs=sorted((x for x in p.iterdir() if x.is_dir()),key=lambda x:x.name.casefold());LOG.info('Browse phase directories: %d · %.3fs',len(dirs),time.perf_counter()-t)
  t=time.perf_counter();it=p.rglob('*') if recursive else p.iterdir();files=sorted((x for x in it if image_file(x)),key=lambda x:filesystem_key(x));LOG.info('Browse phase enumerate: %d images · %.3fs',len(files),time.perf_counter()-t)
 except PermissionError:
  _browse_gate_stable(tx);raise HTTPException(403,'Permission denied')
 except Exception:
  _browse_gate_stable(tx);LOG.exception('Browse phase enumerate failed: %s · recursive=%s',p,recursive);raise
 # Snapshot metadata before querying observations. Files can legitimately disappear while
 # a live output tree is being browsed; that is not a failed browse. Skip only the raced file.
 t=time.perf_counter();records=[]
 for x in files:
  try:st=x.stat()
  except (FileNotFoundError,PermissionError,OSError):continue
  records.append({'name':x.name,'path':str(x),'size':st.st_size,'mtime':st.st_mtime})
 LOG.info('Browse phase stat: %d records · %.3fs',len(records),time.perf_counter()-t)
 try:
  t=time.perf_counter();paths=[x['path'] for x in records];obs=obs_for(paths);LOG.info('Browse phase observations: %d paths · %.3fs',len(paths),time.perf_counter()-t)
  t=time.perf_counter()
  for x in records:x['observations']=obs.get(x['path'],[])
  payload={'browse_tx':tx,'path':str(p),'parent':str(p.parent) if p.parent!=p else None,'directories':[{'name':x.name,'path':str(x)} for x in dirs],'files':records,'recursive':recursive}
  LOG.info('Browse phase assemble: %.3fs',time.perf_counter()-t)
  LOG.info('Browse complete: %s · recursive=%s · %d files · %d dirs · %.3fs total',p,recursive,len(records),len(dirs),time.perf_counter()-t0)
  # Gate intentionally remains parked until /api/browse/stable from the client.
  return payload
 except Exception:
  _browse_gate_stable(tx);LOG.exception('Browse phase archive/assembly failed: %s · recursive=%s',p,recursive);raise

@app.post('/api/browse/heartbeat')
def browse_heartbeat(payload:dict):
 token=str(payload.get('tx') or '')
 return {'ok':_browse_gate_heartbeat(token),'tx':token}

@app.post('/api/grid/activity')
def grid_activity(payload:dict):
 reason=str(payload.get('reason') or 'grid')[:80]
 _grid_governor_touch(reason)
 return {'ok':True,'worker_cap':1,'settle_seconds':GRID_GOVERNOR_SETTLE_SECONDS}


@app.post('/api/browse/stable')
def browse_stable(payload:dict):
 token=str(payload.get('tx') or '')
 ok=_browse_gate_stable(token)
 if ok:_start_launch_verification_once()
 return {'ok':ok,'tx':token,'quiescence_seconds':BROWSE_QUIESCENCE_SECONDS,'launch_verification_started':LAUNCH_VERIFY_STARTED}

class ObservationRequest(BaseModel):
 paths:list[str]

class ObservationCorrectionRequest(BaseModel):
 path:str
 concept:str
 provider:str
 model:str
 kind:str
 geometry:str|None=None
 action:str
 corrected_concept:str|None=None

class TeachConceptRequest(BaseModel):
 path:str
 concept:str
 scope:str='bbox'
 geometry:dict|None=None
 provider:str|None=None
 model:str|None=None
 confidence:float|None=None
 replace_observation:dict|None=None

@app.get('/api/observations/custom-labels')
def custom_observation_labels():
 with db() as c:
  rows=c.execute("SELECT DISTINCT concept FROM observations WHERE provider IN ('human-correction','human-teach') AND confidence>0 ORDER BY concept COLLATE NOCASE").fetchall()
  labels=[str(r[0]).strip() for r in rows if str(r[0]).strip()]
  if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='corrections'").fetchone():
   labels.extend(str(r[0]).strip() for r in c.execute("SELECT DISTINCT corrected_concept FROM corrections WHERE corrected_concept IS NOT NULL AND action IN ('teach','relabel')") if str(r[0]).strip())
 unique={}
 for label in labels:unique.setdefault(label.casefold(),label)
 return {'labels':sorted(unique.values(),key=str.casefold)}

@app.post('/api/observations/correct')
def correct_observation(req:ObservationCorrectionRequest):
 p=norm(req.path)
 if not image_file(p):raise HTTPException(404,'Image not found')
 if req.action not in ('reject','relabel'):raise HTTPException(400,'action must be reject or relabel')
 corrected=(req.corrected_concept or '').strip()
 if req.action=='relabel' and not corrected:raise HTTPException(400,'Relabel needs a corrected concept')
 with db() as c:
  row=c.execute('SELECT confidence FROM observations WHERE path=? AND concept=? AND provider=? AND model=? AND kind=? AND geometry IS ?',
    (str(p),req.concept,req.provider,req.model,req.kind,req.geometry)).fetchone()
  if not row:raise HTTPException(404,'Observation not found')
  original_conf=abs(float(row['confidence']))
  c.execute('UPDATE observations SET confidence=?,updated=unixepoch() WHERE path=? AND concept=? AND provider=? AND model=? AND kind=? AND geometry IS ?',
    (-max(original_conf,1e-9),str(p),req.concept,req.provider,req.model,req.kind,req.geometry))
  c.execute('CREATE TABLE IF NOT EXISTS corrections(id INTEGER PRIMARY KEY AUTOINCREMENT,path TEXT NOT NULL,original_concept TEXT,original_provider TEXT,original_model TEXT,original_kind TEXT,geometry TEXT,action TEXT NOT NULL,corrected_concept TEXT,created REAL NOT NULL DEFAULT (unixepoch()))')
  c.execute('INSERT INTO corrections(path,original_concept,original_provider,original_model,original_kind,geometry,action,corrected_concept) VALUES(?,?,?,?,?,?,?,?)',
    (str(p),req.concept,req.provider,req.model,req.kind,req.geometry,req.action,corrected or None))
  if req.action=='relabel':
   from .subject_learning import geometry as learning_geometry,is_subject,mark_manual
   corrected_geometry=req.geometry
   if corrected!=req.concept and is_subject({'geometry':req.geometry,'provider':req.provider}):
    corrected_geometry=json.dumps(mark_manual(learning_geometry(req.geometry),'label_changed',corrected,req.concept),sort_keys=True,separators=(',',':'))
   c.execute('INSERT OR REPLACE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,?,?,?,?,?,unixepoch())',
     (str(p),corrected,1.0,'human-correction',f'relabel:{req.provider}:{req.model}',req.kind,corrected_geometry))
 bump_obs_revision()
 return {'ok':True,'action':req.action,'corrected_concept':corrected or None,'revision':OBS_REV}

class SubjectObservationRef(BaseModel):
 path:str
 concept:str
 provider:str
 model:str
 kind:str
 geometry:str|None=None

def subject_observation(c,ref):
 row=c.execute('SELECT rowid AS oid,* FROM observations WHERE path=? AND concept=? AND provider=? AND model=? AND kind=? AND geometry IS ? AND confidence>0',
  (str(norm(ref.path)),ref.concept,ref.provider,ref.model,ref.kind,ref.geometry)).fetchone()
 if not row:raise HTTPException(409,'Observation changed; refresh and select it again')
 return dict(row)

@app.post('/api/observations/learn-subject')
def learn_subject(req:SubjectObservationRef):
 from .subject_learning import learn
 path=norm(req.path)
 if not image_file(path):raise HTTPException(404,'Image not found')
 try:
  with db() as c:result=learn(c,subject_observation(c,req),path,subject_class_root())
 except ValueError as exc:raise HTTPException(409,str(exc))
 bump_obs_revision()
 if EDITION['subject_intelligence'] and result.get('class_registered') and subject_class_settings()['auto_train']:schedule_subject_class_training()
 return result

class SubjectPartRequest(BaseModel):
 subject:SubjectObservationRef
 part:SubjectObservationRef

@app.post('/api/observations/subject-part')
def add_subject_part(req:SubjectPartRequest):
 from .subject_learning import geometry as learning_geometry,is_subject,mark_manual,identity
 if str(norm(req.subject.path))!=str(norm(req.part.path)):raise HTTPException(400,'Parts must come from the same image')
 with db() as c:
  subject=subject_observation(c,req.subject);part=subject_observation(c,req.part)
  if not is_subject(subject) or subject['kind']!='mask':raise HTTPException(400,'Choose a masked Subject as owner')
  if subject['oid']==part['oid'] or is_subject(part) or part['kind']!='mask':raise HTTPException(400,'Choose an ordinary part mask, not another Subject')
  g=learning_geometry(subject['geometry']);pg=learning_geometry(part['geometry'])
  size=g.get('source_size')
  box=pg.get('bbox');ms=pg.get('mask_size');runs=pg.get('mask_rle')
  valid=bool(size and box and ms and isinstance(runs,list) and runs and len(runs)%2==0)
  if valid:
   try:
    x1,y1,x2,y2=box;valid=(0<=x1<x2<=size[0] and 0<=y1<y2<=size[1] and ms==[round(x2-x1),round(y2-y1)] and all(isinstance(s,int) and isinstance(n,int) and s>=0 and n>0 and s+n<=ms[0]*ms[1] for s,n in zip(runs[::2],runs[1::2])))
   except (TypeError,ValueError):valid=False
  if not valid:raise HTTPException(400,'Part needs valid mask pixels')
  key=identity(part);parts=list(g.get('subject_parts',[]))
  existing=next((item for item in parts if item.get('id')==key),None)
  if existing and existing.get('confirmation')!='machine-draft':raise HTTPException(409,'Part already belongs to this subject')
  from .subject_learning import add_visible_pixels
  g.setdefault('subject_id',__import__('uuid').uuid4().hex)
  for other in c.execute('SELECT rowid AS oid,* FROM observations WHERE path=? AND confidence>0',(subject['path'],)).fetchall():
   if other['oid']==subject['oid']:continue
   old=learning_geometry(other['geometry']);owned=list(old.get('subject_parts',[]))
   matched=[item for item in owned if item.get('id')==key]
   if not matched:continue
   if any(item.get('confirmation')!='machine-draft' for item in matched):raise HTTPException(409,'Part already has a manually confirmed owner')
   remaining=[item for item in owned if item.get('id')!=key]
   base=old.get('base_geometry')
   if not base:raise HTTPException(409,'Original owner mask unavailable; redraw its mask before reassignment')
   rebuilt=dict(old)
   for field in ('bbox','mask_size','mask_rle','polygon'):rebuilt.pop(field,None)
   rebuilt.update(base);rebuilt['subject_parts']=remaining
   for item in remaining:rebuilt=add_visible_pixels(rebuilt,item['geometry'])
   rebuilt.setdefault('ownership_corrections',[]).append({'part_id':key,'new_owner_subject_id':g['subject_id'],'confirmation':'manual'})
   c.execute('UPDATE observations SET geometry=?,updated=unixepoch() WHERE rowid=?',(json.dumps(rebuilt,sort_keys=True,separators=(',',':')),other['oid']))
  if existing:existing['confirmation']='manual'
  else:parts.append({'id':key,'concept':part['concept'],'provider':part['provider'],'model':part['model'],'geometry':pg,'confirmation':'manual'})
  for item in parts:item['owner_subject_id']=g['subject_id']
  g['subject_parts']=parts
  try:g=add_visible_pixels(g,pg)
  except ValueError as exc:raise HTTPException(400,str(exc))
  g=mark_manual(g,'part_added',subject['concept'])
  c.execute('UPDATE observations SET geometry=?,updated=unixepoch() WHERE rowid=? AND geometry IS ?',
   (json.dumps(g,sort_keys=True,separators=(',',':')),subject['oid'],subject['geometry']))
 bump_obs_revision();return {'ok':True,'geometry':g}

@app.post('/api/observations/teach')
def teach_concept(req:TeachConceptRequest):
 p=norm(req.path); concept=req.concept.strip()
 if not image_file(p):raise HTTPException(404,'Image not found')
 if not concept:raise HTTPException(400,'Concept name required')
 scope=req.scope if req.scope in ('bbox','image','mask') else 'bbox'
 with Image.open(p) as im:w,h=im.size
 geom=dict(req.geometry or {}); geom['source_size']=[w,h]
 origin_provider=(req.provider or 'human-teach').strip()
 origin_model=(req.model or 'concept-bank').strip()
 origin_conf=float(req.confidence) if req.confidence is not None else 1.0
 if not (0<origin_conf<=1):raise HTTPException(400,'Confidence must be between 0 and 1')
 if scope=='image':geom={'scope':'image','source_size':[w,h]}
 else:
  b=geom.get('bbox')
  if not isinstance(b,list) or len(b)!=4:raise HTTPException(400,'bbox requires four coordinates')
  x1,y1,x2,y2=map(float,b); x1,x2=sorted((max(0,x1),min(w,x2))); y1,y2=sorted((max(0,y1),min(h,y2)))
  if x2-x1<1 or y2-y1<1:raise HTTPException(400,'Box is empty')
  if scope=='mask':
   ms=geom.get('mask_size'); runs=geom.get('mask_rle')
   if not isinstance(ms,list) or len(ms)!=2 or not all(isinstance(n,int) and n>0 for n in ms):raise HTTPException(400,'mask_size requires width and height')
   if ms[0]!=round(x2-x1) or ms[1]!=round(y2-y1):raise HTTPException(400,'Mask dimensions must match its crop')
   if not isinstance(runs,list) or len(runs)%2:raise HTTPException(400,'mask_rle must be start/length pairs')
   total=ms[0]*ms[1]
   clean=[]
   for i in range(0,len(runs),2):
    s,n=int(runs[i]),int(runs[i+1])
    if s<0 or n<1 or s+n>total:raise HTTPException(400,'Invalid mask run')
    clean.extend((s,n))
   geom={'bbox':[x1,y1,x2,y2],'mask_size':ms,'mask_rle':clean,'source_size':[w,h],'scope':'mask'}
   if req.provider:geom['source_provider']=origin_provider
   if req.model:geom['source_model']=origin_model
   if (req.geometry or {}).get('method'):geom['method']=req.geometry['method']
   geom['review_status']='approved'
  else:geom={'bbox':[x1,y1,x2,y2],'source_size':[w,h],'scope':'bbox'}
 if scope=='mask':
  metadata=dict(req.geometry or {})
  if req.replace_observation:
   old_geometry=req.replace_observation.get('geometry') or {}
   try:old_geometry=json.loads(old_geometry) if isinstance(old_geometry,str) else old_geometry
   except (TypeError,ValueError):old_geometry={}
   for key in ('subject_role','subject_pipeline','birefnet_revision','subject_learning','subject_parts','subject_id','subject_composite_ready','subject_backend','base_geometry'):
    if key in old_geometry:metadata[key]=old_geometry[key]
  for key in ('subject_role','subject_pipeline','birefnet_revision','subject_learning','subject_parts','subject_id','subject_composite_ready','subject_backend','base_geometry'):
   if key in metadata:geom[key]=metadata[key]
 gj=json.dumps(geom,separators=(',',':'),sort_keys=True)
 with db() as c:
  # Replace only the explicitly selected mask, never a neighboring detection.
  # One transaction: an unsuccessful write rolls back the original observation.
  old=req.replace_observation
  if old:
   if old.get('kind')!='mask' or scope!='mask':raise HTTPException(400,'Only an existing mask can be replaced')
   old_geom=old.get('geometry')
   if isinstance(old_geom,dict):old_geom=json.dumps(old_geom,separators=(',',':'),sort_keys=True)
   deleted=c.execute('DELETE FROM observations WHERE path=? AND concept=? AND provider=? AND model=? AND kind=? AND geometry=?',
    (str(p),old.get('concept'),old.get('provider'),old.get('model'),'mask',old_geom)).rowcount
   if deleted!=1:raise HTTPException(409,'Selected mask changed; refresh and select it again')
  c.execute('INSERT OR REPLACE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,?,?,?,?,?,unixepoch())',
    (str(p),concept,origin_conf,origin_provider,origin_model,scope,gj))
  c.execute('CREATE TABLE IF NOT EXISTS corrections(id INTEGER PRIMARY KEY AUTOINCREMENT,path TEXT NOT NULL,original_concept TEXT,original_provider TEXT,original_model TEXT,original_kind TEXT,geometry TEXT,action TEXT NOT NULL,corrected_concept TEXT,created REAL NOT NULL DEFAULT (unixepoch()))')
  c.execute('INSERT INTO corrections(path,original_kind,geometry,action,corrected_concept) VALUES(?,?,?,?,?)',(str(p),scope,gj,'teach',concept))
 bump_obs_revision()
 return {'ok':True,'concept':concept,'scope':scope,'geometry':geom,'revision':OBS_REV}
@app.post('/api/observations')
def observations(req:ObservationRequest):
 out={x:[] for x in req.paths}
 if req.paths:
  with db() as c:
   step=800
   for start in range(0,len(req.paths),step):
    chunk=req.paths[start:start+step]
    marks=','.join('?'*len(chunk))
    rows=c.execute(f"SELECT path,concept,confidence,provider,model,kind,geometry FROM observations WHERE path IN ({marks})",chunk).fetchall()
    for r in rows:out.setdefault(r['path'],[]).append(dict(r))
 from .observation_display import annotate
 out={path:annotate(rows) for path,rows in out.items()}
 return {'revision':OBS_REV,'observations':out}

class DetectorCleanupRequest(BaseModel):
 token:str
 include_reviewed:bool=False

@app.get('/api/maintenance/removed-detectors')
def removed_detector_preview(include_reviewed:bool=False):
 from .detector_cleanup import preview
 with db() as c:_,summary=preview(c,ROOT,ULTRA_MODELS,include_reviewed)
 return summary

@app.post('/api/maintenance/removed-detectors')
def removed_detector_cleanup(req:DetectorCleanupRequest):
 from .detector_cleanup import preview,detach_removed
 with db() as c:
  if not c.in_transaction:c.execute('BEGIN IMMEDIATE')
  rows,summary=preview(c,ROOT,ULTRA_MODELS,req.include_reviewed)
  if summary['token']!=req.token:raise HTTPException(409,'Detector records or installed files changed; preview cleanup again')
  if req.include_reviewed:detach_removed(c,rows)
  for row in rows:c.execute('DELETE FROM observations WHERE rowid=?',(row['oid'],))
 if rows:bump_obs_revision()
 return {**summary,'deleted':len(rows),'revision':OBS_REV}

@app.get('/api/tags/discovered')
def discovered_tags():
 # Vocabulary comes only from positive observations actually discovered in the library.
 # Model class dictionaries and zero-confidence receipts never leak into the filter picker.
 with db() as c:
  rows=c.execute("SELECT concept,provider,model,kind,COUNT(*) AS detections,MAX(confidence) AS confidence FROM observations WHERE kind!='receipt' AND confidence>0 GROUP BY concept,provider,model,kind ORDER BY concept COLLATE NOCASE,provider,model").fetchall()
 return {'tags':[dict(r) for r in rows]}

@app.get('/api/thumb')
def thumb(path:str=Query(...)):
 p=norm(path)
 if not image_file(p):raise HTTPException(404,'Image not found')
 try:
  st=p.stat();cfg=_load_config().get('thumbnail_cache',{});max_axis=300;producer=int(cfg.get('producer_version',1))
  # Source identity makes changed pixels produce a new cache object. Cache objects are
  # disposable derived data and are deliberately unrelated to the source directory tree.
  identity=f'v{producer}|{max_axis}|{p}|{st.st_size}|{st.st_mtime_ns}'
  key=hashlib.sha256(identity.encode('utf-8','surrogatepass')).hexdigest()
  root=thumbnail_cache_root(p);out=root/'thumbnails'/key[:2]/key[2:4]/(key+'.webp')
  reuse=_cache_reusable(p,'thumbnail')
  if reuse is not None:out=reuse
  if not out.exists():
   out.parent.mkdir(parents=True,exist_ok=True)
   with Image.open(p) as src:
    im=ImageOps.exif_transpose(src);im.thumbnail((max_axis,max_axis),Image.Resampling.LANCZOS)
    if im.mode not in ('RGB','RGBA'):im=im.convert('RGBA' if 'A' in im.getbands() else 'RGB')
    tmp=out.with_name(out.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
     im.save(tmp,format='WEBP',quality=82,method=4)
     tmp.replace(out)
    finally:tmp.unlink(missing_ok=True)
  _cache_register(p,'thumbnail',out)
  # Hold the bytes before returning. Cache maintenance/delete may unlink the disposable
  # WEBP immediately after this point; the response must not retain a lazy path to it.
  try: payload=out.read_bytes()
  except FileNotFoundError:
   if not image_file(p): raise HTTPException(410,'Image was deleted')
   raise HTTPException(404,'Thumbnail cache object vanished; retry')
  return Response(content=payload,media_type='image/webp',headers={'Cache-Control':'private, max-age=86400'})
 except PermissionError as e:raise HTTPException(500,f'Thumbnail cache is not writable: {e}')
 except Exception as e:raise HTTPException(422,f'Cannot create thumbnail: {e}')



def _overlay_color(provider:str,model:str):
 # Match the browser's stable detector-family hue closely enough for the grid legend.
 import colorsys
 model=re.sub(r'#conf=[0-9.]+$','',str(model or ''))
 if str(provider or '')=='ultralytics-world':model=re.sub(r'#vocab=[^#]+$','',model)
 h=2166136261
 for ch in (str(provider or '')+'|'+model):
  h ^= ord(ch); h=(h*16777619)&0xffffffff
 hue=(h%360)/360.0
 r,g,b=colorsys.hls_to_rgb(hue,.62,.78)
 return (int(r*255),int(g*255),int(b*255))

def _grid_overlay_rows(path:str,kind:str):
 with db() as c:
  rows=c.execute("SELECT concept,confidence,provider,model,kind,geometry FROM observations WHERE path=? AND kind IN ('bbox','mask') AND confidence>0 AND geometry IS NOT NULL",(path,)).fetchall()
 out=[]
 from .observation_display import display_rows
 for r in display_rows(rows):
  try:g=json.loads(r['geometry']) if isinstance(r['geometry'],str) else (r['geometry'] or {})
  except Exception:continue
  if kind=='boxes' and not g.get('bbox'):continue
  if kind=='masks' and not (g.get('polygon') or (g.get('mask_rle') and g.get('mask_size') and g.get('bbox'))):continue
  out.append((dict(r),g))
 return out

@app.get('/api/grid-overlay')
def grid_overlay(path:str=Query(...),kind:str=Query(...)):
 """Disposable 300px presentation geometry. Canonical observations stay in SQLite."""
 if kind not in {'boxes','masks'}:raise HTTPException(400,'kind must be boxes or masks')
 p=norm(path)
 if not image_file(p):raise HTTPException(404,'Image not found')
 rows=_grid_overlay_rows(str(p),kind)
 if not rows:return Response(status_code=204,headers={'Cache-Control':'no-store, max-age=0'})
 try:
  st=p.stat()
  with Image.open(p) as src:
   sw,sh=src.size
   if src.getexif().get(274,1) in (5,6,7,8):sw,sh=sh,sw
  scale=min(1.0,300.0/max(sw,sh));tw=max(1,round(sw*scale));th=max(1,round(sh*scale))
  receipt=json.dumps([(r['concept'],r['confidence'],r['provider'],r['model'],r['kind'],g) for r,g in rows],sort_keys=True,separators=(',',':'),default=str)
  key=hashlib.sha256(f'overlay-v1|{kind}|{p}|{st.st_size}|{st.st_mtime_ns}|{tw}x{th}|{receipt}'.encode('utf-8','surrogatepass')).hexdigest()
  root=thumbnail_cache_root(p)/'overlays'/kind/key[:2]/key[2:4]
  ext='.svg' if kind=='boxes' else '.png';out=root/(key+ext)
  if not out.exists():
   out.parent.mkdir(parents=True,exist_ok=True)
   tmp=out.with_name(out.name+'.'+uuid.uuid4().hex+'.tmp')
   if kind=='boxes':
    bits=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {tw} {th}" preserveAspectRatio="xMidYMid meet">']
    for r,g in rows:
     x1,y1,x2,y2=map(float,g['bbox']);x1*=scale;y1*=scale;x2*=scale;y2*=scale
     rr,gg,bb=_overlay_color(r['provider'],r['model']);c=f'rgb({rr},{gg},{bb})'
     concept=r['concept']
     if g.get('subject_role') is not False and (g.get('subject_role') or g.get('subject_pipeline') or r['provider']=='subject-intelligence'):
      concept='Subject — '+('Unidentified' if concept.casefold()=='unidentified subject' else concept)
     score=float(g.get('name_confidence',r['confidence'])) if g.get('name_accepted') else float(r['confidence'])
     label=f"{concept} {round(score*100)}%"
     import html
     bits.append(f'<rect x="{x1:.2f}" y="{y1:.2f}" width="{max(0,x2-x1):.2f}" height="{max(0,y2-y1):.2f}" fill="none" stroke="{c}" stroke-width="2"/>')
     bits.append(f'<text x="{x1+2:.2f}" y="{max(10,y1+10):.2f}" fill="{c}" stroke="black" stroke-width="2" paint-order="stroke" font-family="sans-serif" font-size="9">{html.escape(label)}</text>')
    bits.append('</svg>');tmp.write_text(''.join(bits),encoding='utf-8')
   else:
    im=Image.new('RGBA',(tw,th),(0,0,0,0));draw=ImageDraw.Draw(im,'RGBA')
    for r,g in rows:
     c=_overlay_color(r['provider'],r['model']);fill=(*c,62);stroke=(*c,210)
     if g.get('polygon'):
      pts=[(float(q[0])*scale,float(q[1])*scale) for q in g['polygon']];draw.polygon(pts,fill=fill,outline=stroke)
     elif g.get('mask_rle') and g.get('mask_size') and g.get('bbox'):
      mw=int(g['mask_size'][0]);ox=float(g['bbox'][0]);oy=float(g['bbox'][1])
      for i in range(0,len(g['mask_rle']),2):
       pos=int(g['mask_rle'][i]);n=int(g['mask_rle'][i+1])
       while n>0:
        yy=pos//mw;xx=pos%mw;take=min(n,mw-xx)
        x0=(ox+xx)*scale;y0=(oy+yy)*scale;x1=(ox+xx+take)*scale;y1=(oy+yy+1)*scale
        draw.rectangle((x0,y0,max(x0+1,x1),max(y0+1,y1)),fill=fill)
        pos+=take;n-=take
    im.save(tmp,format='PNG',optimize=True)
   tmp.replace(out)
  _cache_register(p,'overlay-'+kind,out)
  return FileResponse(out,media_type='image/svg+xml' if kind=='boxes' else 'image/png',headers={'Cache-Control':'no-store, max-age=0'})
 except Exception as e:raise HTTPException(422,f'Cannot create grid overlay: {e}')

def _rel_model_path(p:Path)->str:
 try:return str(p.relative_to(ROOT))
 except ValueError:return str(p)

def scan_ultralytics_models(probe:bool=True):
 """Find local Ultralytics models. Probe loads metadata only; inference happens in jobs."""
 found=[]
 for family in ('bbox','seg'):
  base=ULTRA_MODELS/family
  for p in sorted(base.rglob('*')):
   if not p.is_file() or p.suffix.lower() not in {'.pt','.onnx','.engine','.yaml','.yml'}:continue
   item={'engine':'ultralytics','family':family,'name':p.name,'path':str(p),'display_path':_rel_model_path(p),'enabled':True,'ok':None,'task':family,'classes':[],'error':None}
   if probe:
    try:
     from ultralytics import YOLO
     m=YOLO(str(p))
     item['task']=str(getattr(m,'task',family) or family)
     names=getattr(m,'names',{}) or {}
     if isinstance(names,dict):item['classes']=[str(v) for _,v in sorted(names.items())]
     else:item['classes']=[str(v) for v in names]
     item['ok']=True
    except Exception as e:
     item['ok']=False;item['error']=str(e)
   found.append(item)
 # Built-in general-purpose lenses. Ultralytics downloads the small official weights on first use,
 # then uses its local cache. These are virtual entries, so users do not have to hunt model repositories.
 found.extend([
  {'engine':'ultralytics','family':'bbox','name':'Open Images 601','path':'builtin:oiv7','display_path':'yolov8n-oiv7.pt',
   'enabled':True,'ok':True,'task':'detect','classes':['601 Open Images V7 classes'],'error':None,'builtin':True},
  {'engine':'ultralytics-world','family':'bbox','name':'YOLO-World','path':'builtin:world','display_path':'yolov8s-worldv2.pt',
   'enabled':True,'ok':True,'task':'open-vocabulary detect','classes':['user vocabulary'],'error':None,'builtin':True},
  {'engine':'ultralytics','family':'bbox','name':'EraX NSFW V1.0','path':'builtin:erax','display_path':'models/ultralytics/bbox/erax_nsfw_yolo11m.pt',
   'enabled':True,'ok':(ULTRA_MODELS/'bbox'/'erax_nsfw_yolo11m.pt').is_file(),'task':'detect','classes':['anus','make_love','nipple','penis','vagina'],'error':None if (ULTRA_MODELS/'bbox'/'erax_nsfw_yolo11m.pt').is_file() else 'Run install.cmd to download managed weights','builtin':True}
 ])
 return found

@app.get('/api/models')
def models(probe:bool=True):
 ms=scan_ultralytics_models(probe);cfg=load_lens_config()
 for m in ms:
  m['confidence']=float(cfg.get(m['path'],{}).get('confidence',.25))
  m['enabled']=bool(cfg.get(m['path'],{}).get('enabled',m.get('enabled',True)))
 yc=_load_config().get('yolo',{})
 return {'roots':{'ultralytics':str(ULTRA_MODELS)},'models':ms,'world_classes':yc.get('world_classes',[]),'batch_size':int(yc.get('batch_size',16) or 16)}

class LensConfigRequest(BaseModel):
 confidence:float|None=None
 enabled:bool|None=None

@app.put('/api/models/lens-config')
def set_lens_config(path:str,req:LensConfigRequest):
 discovered={m['path']:m for m in scan_ultralytics_models(False)}
 if path not in discovered:raise HTTPException(404,'Unknown lens')
 with LENS_CONFIG_LOCK:
  cfg=load_lens_config(); item=cfg.setdefault(path,{})
  if req.confidence is not None:item['confidence']=max(.0,min(1.0,float(req.confidence)))
  if req.enabled is not None:item['enabled']=bool(req.enabled)
  save_lens_config(cfg)
  result={'path':path,'confidence':float(item.get('confidence',.25)),'enabled':bool(item.get('enabled',True))}
 return result

class YoloSettingsRequest(BaseModel):
 world_classes:list[str]=[]
 batch_size:int=16

@app.put('/api/models/yolo-settings')
def set_yolo_settings(req:YoloSettingsRequest):
 cfg=_load_config(); y=cfg.setdefault('yolo',{})
 y['world_classes']=list(dict.fromkeys(x.strip() for x in req.world_classes if x.strip()))
 y['batch_size']=max(1,min(128,int(req.batch_size or 16)))
 _save_config(cfg);return y

class ModelSweepRequest(BaseModel):
 paths:list[str]
 engine:str='ultralytics'
 models:list[str]=[]
 confidence:float=.25
 thresholds:dict[str,float]={}
 batch_size:int=16
 world_classes:list[str]=[]

def examined_paths(paths,provider,model):
 if not paths:return set()
 found=set()
 with db() as c:
  for start in range(0,len(paths),800):
   chunk=paths[start:start+800];marks=','.join('?'*len(chunk))
   rows=c.execute(f"SELECT DISTINCT path FROM observations WHERE path IN ({marks}) AND provider=? AND model=?",
                  (*chunk,provider,model)).fetchall()
   found.update(r[0] for r in rows)
 return found

def write_lens_receipt(c,path,provider,model):
 c.execute("INSERT OR REPLACE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,?,?,?,'receipt',NULL,unixepoch())",
           (path,'__lens_examined__',0.0,provider,model))

def _analysis_cancelled(job_id=None):
 if STOP_REQUESTED:raise JobCancelled('Clean shutdown requested')
 if job_id:
  with LOCK:
   if JOBS.get(job_id,{}).get('cancel_requested'):raise JobCancelled('Stopped by user')

def _yolo_decode_one(raw):
 """Decode one YOLO input off the inference thread. OpenCV matches Ultralytics' BGR ndarray contract."""
 try:
  import cv2
  image=cv2.imread(raw,cv2.IMREAD_COLOR)
  if image is None:raise ValueError('decoder returned no pixels')
  return image,None
 except Exception as e:
  return None,str(e)

def _yolo_batch_stream(pending,batch_size,job_id=None):
 """Keep several batches decoding ahead of CUDA so inference is not waiting on disk/JPEG work.

 If our eager decoder cannot read any member of a batch, hand that whole batch back to
 Ultralytics as paths. That preserves the old loader as a compatibility fallback.
 """
 from concurrent.futures import ThreadPoolExecutor
 from collections import deque
 bs=max(1,int(batch_size or 1)); workers=max(2,min(6,(os.cpu_count() or 4)-2)); depth=3
 batches=[]
 for start in range(0,len(pending),bs):
  batch=[p for p in pending[start:start+bs] if image_file(Path(p))]
  if batch:batches.append((start,batch))
 if not batches:return
 with ThreadPoolExecutor(max_workers=_grid_worker_cap(workers),thread_name_prefix='yolo-decode') as pool:
  q=deque(); next_i=0
  def submit(i):
   start,batch=batches[i]
   q.append((start,batch,[pool.submit(_yolo_decode_one,p) for p in batch],time.perf_counter()))
  while next_i<min(depth,len(batches)):
   submit(next_i);next_i+=1
  while q:
   _analysis_cancelled(job_id)
   start,batch,futures,_submitted=q.popleft(); decoded=[]; failures=[]
   wait_t0=time.perf_counter()
   for raw,f in zip(batch,futures):
    image,err=f.result()
    if err:failures.append((raw,err))
    decoded.append(image)
   # Refill before yielding: while CUDA handles this batch, workers decode the next one.
   if next_i<len(batches):submit(next_i);next_i+=1
   sources=batch if failures else decoded
   yield start,batch,sources,(time.perf_counter()-wait_t0)*1000.0,len(failures)

def yolo_model_sweep(paths,model_paths,conf,batch_size=16,progress=None,job_id=None,thresholds=None):
 from ultralytics import YOLO
 paths=[str(norm(x)) for x in paths];total=len(paths)*len(model_paths);overall=0;summary=[]
 for mi,model_path in enumerate(model_paths):
  model_path=str(norm(model_path));model_name=Path(model_path).name
  lens_conf=max(.0,min(1.0,float((thresholds or {}).get(model_path,conf))))
  receipt_model=f'{model_path}#conf={lens_conf:.4f}'
  if job_id:
   with LOCK:JOBS[job_id].update(phase='verifying')
  already=examined_paths(paths,'ultralytics',receipt_model);pending=[p for p in paths if p not in already]
  overall+=len(already)
  if progress:progress(overall,total)
  if not pending:
   LOG.info('YOLO sweep: %s skipped — all %s images already examined',model_name,len(paths))
   summary.append({'model':model_name,'path':model_path,'images':0,'detections':0,'skipped':len(already),'errors':[]});continue
  LOG.info('YOLO sweep: loading %s (%s/%s); %s pending, %s already examined',model_name,mi+1,len(model_paths),len(pending),len(already))
  model=YOLO(model_path);names=getattr(model,'names',{}) or {};detections=0;analyzed=0;errors=[]
  if job_id:
   with LOCK:JOBS[job_id].update(phase='inferring')
  if job_id:
   with LOCK:JOBS[job_id].update(model_index=mi+1,model_total=len(model_paths),current_model=model_name,model_done=len(already),model_images=len(paths))
  with db() as c:
   for start,batch,sources,decode_wait_ms,decode_failures in _yolo_batch_stream(pending,batch_size,job_id):
    _analysis_cancelled(job_id)
    try:
     infer_t0=time.perf_counter()
     results=model(sources,conf=lens_conf,max_det=300,verbose=False)
     infer_ms=(time.perf_counter()-infer_t0)*1000.0
     _analysis_cancelled(job_id)
     for raw,result in zip(batch,results):
      _analysis_cancelled(job_id)
      c.execute("DELETE FROM observations WHERE path=? AND provider='ultralytics' AND model=?",(raw,receipt_model))
      boxes=[]
      if result.boxes is not None:
       boxes=result.boxes.xyxy.cpu().tolist();cls=result.boxes.cls.cpu().tolist();scores=result.boxes.conf.cpu().tolist()
       for n,(box,ci,score) in enumerate(zip(boxes,cls,scores)):
        geom={'bbox':box,'instance':n,'source_size':[int(result.orig_shape[1]),int(result.orig_shape[0])]}
        if result.masks is not None and n<len(result.masks.xy):geom['polygon']=result.masks.xy[n].tolist()
        concept=str(result.names[int(ci)] if hasattr(result,'names') else names[int(ci)])
        c.execute("INSERT OR REPLACE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,?,?,?,?,?,unixepoch())",
                  (raw,concept,float(score),'ultralytics',receipt_model,'mask' if 'polygon' in geom else 'bbox',json.dumps(geom)))
      if not boxes:write_lens_receipt(c,raw,'ultralytics',receipt_model)
      stored=len(boxes)
      if job_id:
       with LOCK:JOBS[job_id].update(last_image=Path(raw).name,last_returned=len(boxes),last_stored=stored)
      detections+=len(boxes);analyzed+=1;overall+=1
      if job_id:
       with LOCK:JOBS[job_id].update(current_model=model_name,model_done=len(already)+analyzed,model_images=len(paths),updated=time.time())
     c.commit();bump_obs_revision()
     # P.36 emergency brake: detector files are untrusted producers. Pace durable
     # image throughput so a prolific model cannot monopolize observation storage.
     target_batch_s=len(batch)/240.0
     elapsed_batch_s=time.perf_counter()-infer_t0
     brake_s=max(0.0,target_batch_s-elapsed_batch_s)
     if brake_s:
      deadline=time.monotonic()+brake_s
      while time.monotonic()<deadline:
       _analysis_cancelled(job_id);time.sleep(min(.025,max(0.0,deadline-time.monotonic())))
     LOG.info('YOLO flow: %s · %s images · decode wait %.0f ms · infer %.0f ms · brake %.0f ms · eager decode fallbacks %s',model_name,len(batch),decode_wait_ms,infer_ms,brake_s*1000.0,decode_failures)
     # A batch is the durable work/checkpoint unit, but progress is cumulative
     # across the whole sweep. Publish only after the batch is committed so the
     # meter and throughput describe real completed work, not result-unpacking.
     if progress:progress(overall,total)
     # P.38 control-plane yield: Stop Analysis must get CPU/thread admission even when
     # batches finish much faster than a human can click.
     time.sleep(.01)
     _analysis_cancelled(job_id)
    except JobCancelled:
     # Cancellation is control flow, not a failed YOLO batch.  Let the job runner
     # mark the sweep stopped and, critically, do not schedule the next batch.
     raise
    except Exception as e:
     errors.append(str(e));overall+=len(batch)
     if progress:progress(overall,total)
  summary.append({'model':model_name,'path':model_path,'images':analyzed,'detections':detections,'skipped':len(already),'errors':errors})
  LOG.info('YOLO sweep: %s complete — %s new, %s skipped, %s detections',model_name,analyzed,len(already),detections)
  del model
  try:
   import torch
   if torch.cuda.is_available():torch.cuda.empty_cache()
  except Exception:pass
 return {'engine':'ultralytics','models':summary,'model_count':len(summary),'model_images':total,'detections':sum(x['detections'] for x in summary),'skipped':sum(x['skipped'] for x in summary)}


def builtin_lens_sweep(paths,lenses,conf,batch_size=16,world_classes=None,progress=None,job_id=None,thresholds=None):
 """Run N8Vision's built-in broad lenses sequentially using the same observation/receipt contract as local YOLO."""
 from ultralytics import YOLO
 import hashlib
 paths=[str(norm(x)) for x in paths]; world_classes=[x.strip() for x in (world_classes or []) if x.strip()]
 total=len(paths)*len(lenses); overall=0; summary=[]
 for mi,lens in enumerate(lenses):
  if lens=='builtin:oiv7':
   weights='yolov8n-oiv7.pt'; provider='ultralytics-oiv7'; identity=weights; display='Open Images 601'
   model=YOLO(weights)
  elif lens=='builtin:world':
   if not world_classes:
    # No vocabulary means there is nothing meaningful for this lens to examine.
    overall+=len(paths); summary.append({'model':'YOLO-World','path':lens,'images':0,'detections':0,'skipped':len(paths),'errors':['No YOLO-World vocabulary supplied']}); continue
   try:
    from ultralytics import YOLOWorld
    model=YOLOWorld('yolov8s-worldv2.pt')
   except ImportError:
    model=YOLO('yolov8s-worldv2.pt')
   model.set_classes(world_classes)
   vocab_sig=hashlib.sha1('\n'.join(x.casefold() for x in world_classes).encode()).hexdigest()[:12]
   provider='ultralytics-world'; identity=f'yolov8s-worldv2.pt#vocab={vocab_sig}'; display='YOLO-World'
  elif lens=='builtin:erax':
   weights=ULTRA_MODELS/'bbox'/'erax_nsfw_yolo11m.pt'
   if not weights.is_file():
    overall+=len(paths);summary.append({'model':'EraX NSFW V1.0','path':lens,'images':0,'detections':0,'skipped':len(paths),'errors':['Managed EraX weights are not installed; run install.cmd']});continue
   provider='ultralytics-erax';identity='erax-ai/EraX-NSFW-V1.0@83b8c11';display='EraX NSFW V1.0';model=YOLO(str(weights))
  else: continue
  lens_conf=max(.0,min(1.0,float((thresholds or {}).get(lens,conf))))
  identity=f'{identity}#conf={lens_conf:.4f}'
  already=examined_paths(paths,provider,identity);pending=[p for p in paths if p not in already];overall+=len(already)
  if progress:progress(overall,total)
  detections=0;analyzed=0;errors=[]
  if job_id:
   with LOCK:JOBS[job_id].update(model_index=mi+1,model_total=len(lenses),current_model=display,model_done=len(already),model_images=len(paths))
  with db() as c:
   for start,batch,sources,decode_wait_ms,decode_failures in _yolo_batch_stream(pending,batch_size,job_id):
    _analysis_cancelled(job_id)
    try:
     infer_t0=time.perf_counter()
     results=model(sources,conf=lens_conf,max_det=300,verbose=False)
     infer_ms=(time.perf_counter()-infer_t0)*1000.0
     _analysis_cancelled(job_id)
     for raw,result in zip(batch,results):
      _analysis_cancelled(job_id)
      c.execute("DELETE FROM observations WHERE path=? AND provider=? AND model=?",(raw,provider,identity))
      boxes=[]
      if result.boxes is not None:
       boxes=result.boxes.xyxy.cpu().tolist(); cls=result.boxes.cls.cpu().tolist(); scores=result.boxes.conf.cpu().tolist()
       for n,(box,ci,score) in enumerate(zip(boxes,cls,scores)):
        geom={'bbox':box,'instance':n,'source_size':[int(result.orig_shape[1]),int(result.orig_shape[0])]}
        concept=str(result.names[int(ci)])
        c.execute("INSERT OR REPLACE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,?,?,?,'bbox',?,unixepoch())",
                  (raw,concept,float(score),provider,identity,json.dumps(geom)))
      if not boxes:write_lens_receipt(c,raw,provider,identity)
      stored=len(boxes)
      if job_id:
       with LOCK:JOBS[job_id].update(last_image=Path(raw).name,last_returned=len(boxes),last_stored=stored)
      detections+=len(boxes);analyzed+=1;overall+=1
      if job_id:
       with LOCK:JOBS[job_id].update(current_model=display,model_done=len(already)+analyzed,model_images=len(paths),updated=time.time())
     c.commit();bump_obs_revision()
     LOG.info('YOLO flow: %s · %s images · decode wait %.0f ms · infer %.0f ms · eager decode fallbacks %s',display,len(batch),decode_wait_ms,infer_ms,decode_failures)
     # A batch is the durable work/checkpoint unit, but progress is cumulative
     # across the whole sweep. Publish only after the batch is committed so the
     # meter and throughput describe real completed work, not result-unpacking.
     if progress:progress(overall,total)
    except JobCancelled:
     # Cancellation is control flow, not a failed YOLO batch.  Let the job runner
     # mark the sweep stopped and, critically, do not schedule the next batch.
     raise
    except Exception as e:
     errors.append(str(e));overall+=len(batch)
     if progress:progress(overall,total)
  summary.append({'model':display,'path':lens,'images':analyzed,'detections':detections,'skipped':len(already),'errors':errors})
  del model
  try:
   import torch
   if torch.cuda.is_available():torch.cuda.empty_cache()
  except Exception:pass
 return {'engine':'builtin-lenses','models':summary,'model_count':len(summary),'model_images':total,'detections':sum(x['detections'] for x in summary),'skipped':sum(x['skipped'] for x in summary)}


@app.post('/api/models/sweep')
def model_sweep(req:ModelSweepRequest):
 if req.engine!='ultralytics':raise HTTPException(400,'Unsupported engine')
 discovered={m['path']:m for m in scan_ultralytics_models(False)}
 selected=req.models or list(discovered)
 selected=[x for x in selected if x in discovered]
 if not selected:raise HTTPException(400,'No enabled Ultralytics models selected')
 local=[x for x in selected if not x.startswith('builtin:')]; builtin=[x for x in selected if x.startswith('builtin:')]
 jid=uuid.uuid4().hex[:12]; total=len(req.paths)*len(selected)
 JOBS[jid]={'id':jid,'kind':'vision-sweep','state':'queued','done':0,'total':total,'created':time.time(),
            'model_index':0,'model_total':len(selected),'current_model':'','model_done':0,'model_images':len(req.paths),'detections':0}
 _write_active_job_journal()
 def run():
  try:
   JOBS[jid]['state']='running'; _write_active_job_journal(); detections=0; summaries=[]; done_offset=0
   if local:
    r=yolo_model_sweep(req.paths,local,req.confidence,req.batch_size,
       progress=lambda d,t:job_progress(jid,d,total),job_id=jid,thresholds=req.thresholds)
    detections+=r['detections'];summaries+=r['models'];done_offset=len(req.paths)*len(local)
   if builtin:
    r=builtin_lens_sweep(req.paths,builtin,req.confidence,req.batch_size,req.world_classes,
       progress=lambda d,t:job_progress(jid,done_offset+d,total),job_id=jid,thresholds=req.thresholds)
    detections+=r['detections'];summaries+=r['models']
   JOBS[jid].update(state='done',result={'models':summaries,'detections':detections},done=total,detections=detections); _write_active_job_journal()
  except JobCancelled as e:
   JOBS[jid].update(state='stopped',error=str(e),updated=time.time());_write_active_job_journal();LOG.info('Job %s stopped: vision sweep — %s',jid,e)
  except Exception as e:
   JOBS[jid].update(state='error',error=str(e)); _write_active_job_journal();LOG.exception('Job %s failed: vision sweep — %s',jid,e)
 threading.Thread(target=run,daemon=True).start()
 return JOBS[jid]

class Paths(BaseModel):paths:list[str]
class MoveRequest(Paths):destination:str
class RenameRequest(BaseModel):path:str;name:str
class MkdirRequest(BaseModel):parent:str;name:str
class ClassifyRequest(Paths):labels:list[str];model:str='openai/clip-vit-base-patch32'
class EmbedRequest(Paths):model:str='openai/clip-vit-base-patch32'
class DetectRequest(Paths):model:str='yolo11n.pt';confidence:float=.25
class SegmentRequest(Paths):model:str='facebook/sam-vit-base';source_provider:str='ultralytics';min_confidence:float=.25
class SemanticRequest(BaseModel):query:str;model:str='openai/clip-vit-base-patch32';limit:int=500;paths:list[str]|None=None
class SimilarRequest(BaseModel):path:str;model:str='openai/clip-vit-base-patch32';limit:int=500;paths:list[str]|None=None
class UniqueRequest(BaseModel):model:str='openai/clip-vit-base-patch32';neighbors:int=8;paths:list[str]|None=None
class DuplicateRequest(BaseModel):model:str='openai/clip-vit-base-patch32';neighbors:int=8;paths:list[str]|None=None;candidate_similarity:float=.985


def _fs_history_add(c,op:str,payload:dict):
 c.execute('INSERT INTO fs_history(op,payload) VALUES(?,?)',(op,json.dumps(payload,separators=(",",":"))))
 return c.execute('SELECT last_insert_rowid()').fetchone()[0]

def _fs_history_rows(limit=50):
 with db() as c:
  rows=c.execute('SELECT id,op,payload,created,undone,error FROM fs_history ORDER BY id DESC LIMIT ?',(max(1,min(500,int(limit))),)).fetchall()
 return [dict(r)|{'payload':json.loads(r['payload'])} for r in rows]

@app.get('/api/files/history')
def file_history(limit:int=50):return {'history':_fs_history_rows(limit)}

@app.post('/api/files/undo')
def undo_file_action():
 with db() as c:
  row=c.execute('SELECT id,op,payload FROM fs_history WHERE undone IS NULL ORDER BY id DESC LIMIT 1').fetchone()
  if not row:raise HTTPException(404,'Nothing to undo')
  hid,op,payload=row['id'],row['op'],json.loads(row['payload'])
  try:
   if op in ('move','rename'):
    pairs=payload.get('items',[])
    for item in reversed(pairs):
     src=Path(item['from']);dst=Path(item['to'])
     if not dst.exists():raise RuntimeError(f'Current file is missing: {dst}')
     if src.exists():raise RuntimeError(f'Original path is occupied: {src}')
     src.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(dst),str(src));_merge_path_rows(c,str(dst),str(src));_cache_mark_path(str(dst),new_path=str(src),content_sha=_tracked_sha(str(src)))
   elif op=='mkdir':
    target=Path(payload['path'])
    if target.exists():target.rmdir()
   elif op=='delete':
    raise RuntimeError('Delete was sent to the operating-system Recycle Bin. Restore it there; N8Vision cannot safely address an individual Recycle Bin item.')
   else:raise RuntimeError(f'Unsupported history operation: {op}')
   c.execute('UPDATE fs_history SET undone=unixepoch(),error=NULL WHERE id=?',(hid,));c.commit();bump_obs_revision()
   return {'undone':hid,'op':op}
  except Exception as e:
   c.execute('UPDATE fs_history SET error=? WHERE id=?',(str(e),hid));c.commit();raise HTTPException(409,str(e))

@app.post('/api/files/delete')
def delete(req:Paths):
 # "Polite nuclear delete": park background observers, delete from filesystem first,
 # then atomically erase the successfully deleted identities from N8Vision's archive.
 requested=[str(norm(raw)) for raw in req.paths]
 started=time.perf_counter();done=[];failed=[]
 _delete_gate_paths(requested,True)
 try:
  # Give any already-running BRISQUE bite a brief chance to leave the critical path.
  # Its result is independently gated below, so deletion never waits indefinitely.
  time.sleep(.05)
  for raw in requested:
   p=Path(raw)
   if not p.exists():
    # Already absent: explicit Delete still means forget this identity.
    done.append(raw);continue
   try:
    send2trash(str(p));done.append(raw)
   except Exception as e:
    failed.append({'path':raw,'error':str(e)})
  filesystem_done=time.perf_counter()
  if done:
   with db() as c:
    for raw in done:
     _cache_mark_path(raw,'purgatory')
     _purge_deleted_identity(c,raw)
    _fs_history_add(c,'delete',{'items':done})
    c.commit()
   bump_obs_revision()
   LOG.info('Nuclear delete: filesystem + archive purged for %s path(s); %s failed',len(done),len(failed))
  LOG.info('Delete timing: filesystem %.3fs · archive %.3fs · total %.3fs',filesystem_done-started,time.perf_counter()-filesystem_done,time.perf_counter()-started)
  return {'deleted':done,'failed':failed}
 finally:
  _delete_gate_paths(requested,False)

class CollisionSettings(BaseModel):always_rename:bool=True
@app.get('/api/files/collision-settings')
def collision_settings():return {'always_rename':bool(_load_config().get('collisions_always_rename',True))}
@app.put('/api/files/collision-settings')
def set_collision_settings(req:CollisionSettings):
 cfg=_load_config();cfg['collisions_always_rename']=req.always_rename;_save_config(cfg)
 return {'always_rename':req.always_rename}

def _unique_move_target(dest:Path,name:str,reserved:set[str])->Path:
 base=Path(name);candidate=dest/name;idx=1
 while candidate.exists() or os.path.normcase(str(candidate)).casefold() in reserved:
  candidate=dest/f'{base.stem}_{idx:03d}{base.suffix}';idx+=1
 return candidate

@app.post('/api/files/move')
def move(req:MoveRequest):
 dest=norm(req.destination)
 if not dest.is_dir():raise HTTPException(400,'Destination folder does not exist')
 sources=[norm(raw) for raw in req.paths]
 sources=list(dict.fromkeys(sources))
 for src in sources:
  if not src.is_file():raise HTTPException(404,f'Source missing or not a file: {src}')
  if src.parent==dest:continue
 # Preflight the entire batch, including incoming/incoming collisions.
 reserved=set();plan=[];collisions=[]
 always=bool(_load_config().get('collisions_always_rename',True))
 for src in sources:
  if src.parent==dest:continue
  requested=dest/src.name
  target=_unique_move_target(dest,src.name,reserved)
  if target!=requested:collisions.append({'from':str(src),'requested':str(requested),'proposed':str(target)})
  reserved.add(os.path.normcase(str(target)).casefold())
  plan.append((src,target))
 if collisions and not always:
  raise HTTPException(409,detail={'message':'Filename collisions require a decision. Enable Always Rename in Settings to preserve all files automatically.','collisions':collisions})
 moved=[]
 # Commit one file at a time. A crash cannot leave completed files without a
 # journal record; incomplete batches are represented by their completed items.
 with db() as c:
  for src,target in plan:
   if target.exists():raise HTTPException(409,f'Destination became occupied: {target}')
   try:
    shutil.move(str(src),str(target))
    try:
     _merge_path_rows(c,str(src),str(target))
     item={'from':str(src),'to':str(target),'collision_renamed':target.name!=src.name}
     _fs_history_add(c,'move',{'items':[item]})
     c.commit()
    except Exception:
     c.rollback()
     if not src.exists() and target.exists():shutil.move(str(target),str(src))
     raise
    _cache_mark_path(str(src),new_path=str(target),content_sha=_tracked_sha(str(target)))
    moved.append(item)
   except Exception as e:
    LOG.exception('Move stopped after %s completed files',len(moved))
    raise HTTPException(409,detail={'error':str(e),'completed':moved})
 if moved:bump_obs_revision()
 return {'moved':moved,'collisions_renamed':sum(bool(x['collision_renamed']) for x in moved)}
@app.post('/api/files/rename')
def rename(req:RenameRequest):
 src=norm(req.path);target=src.with_name(req.name)
 if not src.exists():raise HTTPException(404,'File not found')
 if target.exists():raise HTTPException(409,'Destination exists')
 src.rename(target)
 with db() as c:
  _merge_path_rows(c,str(src),str(target));_fs_history_add(c,'rename',{'items':[{'from':str(src),'to':str(target)}]})
 _cache_mark_path(str(src),new_path=str(target),content_sha=_tracked_sha(str(target)))
 return {'from':str(src),'to':str(target)}
@app.post('/api/files/mkdir')
def mkdir(req:MkdirRequest):
 target=norm(req.parent)/req.name;target.mkdir(exist_ok=False)
 with db() as c:_fs_history_add(c,'mkdir',{'path':str(target)})
 return {'path':str(target)}
@app.get('/api/file')
def file(path:str=Query(...)):
 p=norm(path)
 if not image_file(p):raise HTTPException(404,'Image not found')
 return FileResponse(p)

def clip_parts(model_name):
 import torch
 try:
  from transformers.models.clip.modeling_clip import CLIPModel
  from transformers.models.clip.processing_clip import CLIPProcessor
 except Exception as e:
  LOG.exception('CLIP provider import failed')
  raise RuntimeError(f'CLIP provider unavailable: {type(e).__name__}: {e}') from e
 key=('clip',model_name); cached=MODEL_CACHE.get(key)
 if cached:return cached
 device=_accelerator_device()
 LOG.info('Loading CLIP model %s on %s (Hub cache: %s)',model_name,device,HF_CACHE)
 try:
  m=CLIPModel.from_pretrained(model_name,local_files_only=True).to(device).eval(); p=CLIPProcessor.from_pretrained(model_name,local_files_only=True)
  LOG.info('CLIP loaded from local cache')
 except Exception:
  LOG.info('CLIP is not fully cached; allowing one-time Hub download for %s',model_name)
  m=CLIPModel.from_pretrained(model_name).to(device).eval(); p=CLIPProcessor.from_pretrained(model_name)
 LOG.info('CLIP ready: %s',model_name)
 MODEL_CACHE[key]=(torch,m,p,device);return MODEL_CACHE[key]
def _feature_tensor(value):
 # Transformers API compatibility: get_*_features may return Tensor directly,
 # BaseModelOutputWithPooling, or another ModelOutput-like wrapper.
 if hasattr(value,'norm'):
  return value
 for name in ('pooler_output','image_embeds','text_embeds','last_hidden_state'):
  candidate=getattr(value,name,None)
  if candidate is not None:
   if name=='last_hidden_state' and getattr(candidate,'ndim',0)>=3:
    candidate=candidate[:,0]
   return candidate
 if isinstance(value,(tuple,list)) and value:
  return _feature_tensor(value[0])
 raise TypeError(f'Cannot extract feature tensor from {type(value).__name__}')

def iqf_head():
 import torch
 from huggingface_hub import hf_hub_download
 from safetensors.torch import load_file
 key=('quality','matthewyuan/image-quality-fusion-full'); cached=MODEL_CACHE.get(key)
 if cached:return cached
 repo='matthewyuan/image-quality-fusion'; filename='model.safetensors'
 try:
  weights=hf_hub_download(repo_id=repo,filename=filename,cache_dir=str(HF_CACHE/'hub'),local_files_only=True)
  LOG.info('Yuan fusion weights found locally: %s',weights)
 except Exception:
  LOG.info('Yuan fusion weights are not cached; downloading once from Hugging Face')
  weights=hf_hub_download(repo_id=repo,filename=filename,cache_dir=str(HF_CACHE/'hub'))
 state=load_file(weights,device='cpu')
 class IQF(torch.nn.Module):
  def __init__(self,hidden_dim=256,dropout_rate=.3):
   super().__init__()
   self.brisque_net=torch.nn.Sequential(torch.nn.Linear(1,64),torch.nn.ReLU(),torch.nn.Dropout(dropout_rate),torch.nn.Linear(64,hidden_dim//4),torch.nn.ReLU())
   self.laion_net=torch.nn.Sequential(torch.nn.Linear(1,64),torch.nn.ReLU(),torch.nn.Dropout(dropout_rate),torch.nn.Linear(64,hidden_dim//4),torch.nn.ReLU())
   self.clip_net=torch.nn.Sequential(torch.nn.Linear(512,hidden_dim),torch.nn.ReLU(),torch.nn.Dropout(dropout_rate),torch.nn.Linear(hidden_dim,hidden_dim//2),torch.nn.ReLU(),torch.nn.Dropout(dropout_rate))
   self.fusion_net=torch.nn.Sequential(torch.nn.Linear(hidden_dim,hidden_dim),torch.nn.ReLU(),torch.nn.Dropout(dropout_rate),torch.nn.Linear(hidden_dim,hidden_dim//2),torch.nn.ReLU(),torch.nn.Dropout(dropout_rate),torch.nn.Linear(hidden_dim//2,1))
  def forward(self,brisque,laion,clip):
   if brisque.dim()==1:brisque=brisque.unsqueeze(1)
   if laion.dim()==1:laion=laion.unsqueeze(1)
   fused=torch.cat((self.brisque_net(brisque),self.laion_net(laion),self.clip_net(clip)),dim=1)
   return 1.0+torch.sigmoid(self.fusion_net(fused))*9.0
 head=IQF();head.load_state_dict(state,strict=True);head.eval()
 MODEL_CACHE[key]=(torch,head)
 return MODEL_CACHE[key]

def iqf_extractor():
 key=('quality-extractor','mattkyuan/image-quality-fusion'); cached=MODEL_CACHE.get(key)
 if cached:return cached
 try:
  from image_quality_fusion.data.preprocessing import ImageQualityExtractor
 except Exception as e:
  raise RuntimeError('Full Yuan fusion feature extractor is not installed. Run install.cmd, then restart N8Vision.') from e
 LOG.info('Loading Yuan BRISQUE + LAION + CLIP feature extractor')
 ex=ImageQualityExtractor()
 # Upstream CLIPSemanticAnalyzer is hard-wired to MPS-or-CPU. On CUDA hosts that
 # silently strands Yuan's semantic CLIP on CPU even though its aesthetic model
 # correctly auto-selects CUDA. Repair that device choice locally without editing
 # the installed third-party package.
 try:
  import torch
  if torch.cuda.is_available() and getattr(ex,'clip_model',None) is not None:
   ex.clip_model.device=torch.device('cuda')
   ex.clip_model.model=ex.clip_model.model.to(ex.clip_model.device).eval()
 except Exception:
  LOG.exception('Could not promote Yuan semantic CLIP to CUDA')
 # Yuan's upstream optimized batch path also hard-wires semantic CLIP to
 # MPS-or-CPU. Replace only that feeder so its existing batch extractor can use
 # the same CUDA model we promoted above.
 try:
  import types,torch
  if torch.cuda.is_available() and getattr(ex,'clip_model',None) is not None:
   def _n8_cuda_batch_clip(self,images):
    tensors=[self.clip_model.preprocess(img).unsqueeze(0) for img in images]
    batch=torch.cat(tensors,dim=0).to(self.clip_model.device,non_blocking=True)
    with torch.inference_mode(),torch.autocast(device_type='cuda',dtype=torch.float16):
     embeddings=self.clip_model.model.encode_image(batch)
    return [row for row in embeddings.float().cpu()]
   ex._batch_clip_embeddings=types.MethodType(_n8_cuda_batch_clip,ex)
 except Exception:
  LOG.exception('Could not install Yuan CUDA batch feeder')
 LOG.info('Yuan extractor devices: %s',_yuan_device_report(ex))
 MODEL_CACHE[key]=ex;return ex

ACCEL_TUNING_PATH=DATA/'accelerator_tuning.json'
def _accel_tuning_read():
 try:return json.loads(ACCEL_TUNING_PATH.read_text(encoding='utf-8')) if ACCEL_TUNING_PATH.exists() else {}
 except Exception:return {}
def _accel_tuning_write(d):
 try:
  tmp=ACCEL_TUNING_PATH.with_name(f'{ACCEL_TUNING_PATH.name}.{uuid.uuid4().hex}.tmp')
  tmp.write_text(json.dumps(d,indent=2,sort_keys=True),encoding='utf-8');tmp.replace(ACCEL_TUNING_PATH)
 except Exception:LOG.exception('Could not persist accelerator tuning')
def _quality_tune_key(torch,device,model_name):
 if str(device).startswith('cuda'):
  try:hw=torch.cuda.get_device_name(0)
  except Exception:hw='cuda'
 else:hw=str(device)
 return f'quality-p16|{hw}|{model_name}|{torch.__version__}|amp-fp16'

BRISQUE_OBS_PROVIDER='opencv-brisque-bg-v1'
BRISQUE_OBS_MODEL='opencv-quality'

def _brisque_cached_raw(paths):
 out={}
 if not paths:return out
 vals=[str(norm(x)) for x in paths]
 with db() as c:
  for i in range(0,len(vals),400):
   part=vals[i:i+400]; qs=','.join('?' for _ in part)
   rows=c.execute(f"SELECT path,confidence,geometry,updated FROM observations WHERE provider=? AND model=? AND concept='brisque_raw' AND path IN ({qs})",[BRISQUE_OBS_PROVIDER,BRISQUE_OBS_MODEL,*part]).fetchall()
   for r in rows:
    try:
     pp=Path(r['path']); mtime=pp.stat().st_mtime
     if float(r['updated'] or 0) < float(mtime):continue
     g=json.loads(r['geometry'] or '{}'); raw=float(g.get('raw',r['confidence'])); out[r['path']]=raw
    except Exception:pass
 return out

def _store_brisque_raw(items):
 if not items:return
 with db() as c:
  for path,raw in items:
   if _delete_gate_contains(path) or _browse_gate_paused() or not Path(path).is_file():continue
   c.execute("INSERT OR REPLACE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,?,?,?,?,?,unixepoch())",(str(path),'brisque_raw',float(raw),BRISQUE_OBS_PROVIDER,BRISQUE_OBS_MODEL,'metric',json.dumps({'raw':float(raw)})))
  c.commit()
 bump_obs_revision()

# Foreground filesystem mutation gate. Background observers must never resurrect deleted paths.
DELETE_IN_PROGRESS=set()
DELETE_GATE_LOCK=threading.RLock()

def _delete_gate_paths(paths,active=True):
 with DELETE_GATE_LOCK:
  if active: DELETE_IN_PROGRESS.update(str(x) for x in paths)
  else:
   for x in paths: DELETE_IN_PROGRESS.discard(str(x))

def _delete_gate_contains(path):
 with DELETE_GATE_LOCK:return str(path) in DELETE_IN_PROGRESS

def _purge_deleted_identity(c,raw):
 # A successful user delete is authoritative: remove every path-owned archive record now,
 # rather than leaving an orphan for next-launch reconciliation.
 c.execute('DELETE FROM observations WHERE path=?',(raw,))
 c.execute('DELETE FROM embeddings WHERE path=?',(raw,))
 c.execute('DELETE FROM tracked_files WHERE path=?',(raw,))
 try:c.execute('DELETE FROM corrections WHERE path=?',(raw,))
 except sqlite3.OperationalError:pass

def _background_brisque_capacity():
 if _grid_governor_active():return 1
 if _browse_gate_paused():return 0
 # Foreground owns the machine. Filesystem mutations are nuclear-priority and park observers.
 with DELETE_GATE_LOCK:
  if DELETE_IN_PROGRESS:return 0
 with LOCK:
  kinds=[j.get('kind') for j in JOBS.values() if j.get('state') in ('queued','running')]
 if not kinds:return _quality_brisque_workers()
 if any(k in ('sanity-v4','quality') for k in kinds):return 0
 if any(k in ('detect','segment','classify','embed') for k in kinds):return 2
 return 1

def _background_brisque_service():
 # Wait for launch reconciliation/DB housekeeping rather than racing server startup.
 # Background observation work also observes a short quiescence window after foreground
 # activity ends so model teardown, CUDA cleanup, commits, and UI refreshes can settle.
 from concurrent.futures import ThreadPoolExecutor
 from image_quality_fusion.models.brisque_opencv import OpenCVBRISQUEModel
 import threading as _threading
 # P.51: verification-ready is not permission to inspect. Sweepy gets exclusive startup
 # housekeeping first, including its post-browse quiet interval. The event is also released
 # after a failed verification so observers do not deadlock the process forever.
 while not STOP_REQUESTED and not ARCHIVE_MAINTENANCE_DONE.wait(.5):pass
 if STOP_REQUESTED:return
 QUIESCENCE_SECONDS=5.0
 quiet_since=time.monotonic()
 foreground_was_active=False
 tls=_threading.local(); max_workers=_quality_brisque_workers()
 def score(path):
  if _delete_gate_contains(path) or _browse_gate_paused():return None
  if not hasattr(tls,'model'):tls.model=OpenCVBRISQUEModel()
  try:
   result=(str(path),float(tls.model.calculate_brisque_score(str(path))))
   if _delete_gate_contains(path) or not Path(path).is_file():return None
   return result
  except Exception as e:LOG.warning('Background BRISQUE failed for %s: %s',path,e);return None
 LOG.info('Background observation service ready: BRISQUE up to %s workers',max_workers)
 with ThreadPoolExecutor(max_workers=max_workers,thread_name_prefix='bg-brisque') as pool:
  while not STOP_REQUESTED:
   with LOCK:
    foreground_active=any(j.get('state') in ('queued','running') for j in JOBS.values())
   now=time.monotonic()
   if foreground_active:
    foreground_was_active=True
   elif foreground_was_active:
    # The last foreground job just released the machine. Start the quiet clock now,
    # not at the job's nominal completion timestamp.
    quiet_since=now
    foreground_was_active=False
   if not foreground_active and now-quiet_since < QUIESCENCE_SECONDS:
    time.sleep(.25);continue
   cap=_background_brisque_capacity()
   if cap<=0:time.sleep(.5);continue
   try:
    with db() as c:
     rows=c.execute("SELECT t.path FROM tracked_files t LEFT JOIN observations o ON o.path=t.path AND o.provider=? AND o.model=? AND o.concept='brisque_raw' WHERE t.orphaned=0 AND (o.path IS NULL OR (t.mtime IS NOT NULL AND o.updated < t.mtime)) LIMIT ?",(BRISQUE_OBS_PROVIDER,BRISQUE_OBS_MODEL,max(16,cap*8))).fetchall()
    paths=[r['path'] for r in rows if image_file(norm(r['path']))]
    if not paths:time.sleep(2.0);continue
    # Submit only the currently allowed slice; capacity is reconsidered every bite.
    bite=paths[:max(1,cap)]
    got=[x for x in pool.map(score,bite) if x is not None]
    _store_brisque_raw(got)
    if got:LOG.info('Background BRISQUE archived %s observation(s) at capacity %s',len(got),cap)
   except Exception as e:
    if not STOP_REQUESTED:LOG.warning('Background BRISQUE service: %s',e)
    time.sleep(1.0)

def _quality_brisque_workers():
 try:
  import psutil
  physical=psutil.cpu_count(logical=False) or 1
 except Exception:
  physical=max(1,(os.cpu_count() or 2)//2)
 return max(1,min(physical-2, max(4, physical//2)))

def _install_resident_brisque(ex):
 """Give Yuan a job-resident BRISQUE worker pool instead of rebuilding a model/pool per batch."""
 if getattr(ex,'_n8_brisque_pool',None) is not None:return
 import threading,types
 from concurrent.futures import ThreadPoolExecutor
 from image_quality_fusion.models.brisque_opencv import OpenCVBRISQUEModel
 workers=_quality_brisque_workers();tls=threading.local()
 def score(path):
  if not hasattr(tls,'model'):tls.model=OpenCVBRISQUEModel()
  try:return tls.model.calculate_brisque_score(str(path))
  except Exception as e:
   LOG.warning('BRISQUE failed for %s: %s',path,e);return 50.0
 ex._n8_brisque_pool=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='n8-brisque')
 ex._n8_brisque_workers=workers
 def resident_batch(self,image_paths,num_workers=None):
  return list(self._n8_brisque_pool.map(score,image_paths))
 ex._batch_brisque_parallel=types.MethodType(resident_batch,ex)
 LOG.info('Yuan BRISQUE resident pool ready: %s workers',workers)

def _yuan_batch_features(ex,paths,stage):
 """Run one true Yuan inference batch with separately timed CPU/GPU legs."""
 images=[];valid=[]
 t=time.perf_counter()
 for pp in paths:
  try:
   with Image.open(pp) as im:images.append(ImageOps.exif_transpose(im).convert('RGB').copy())
   valid.append(pp)
  except Exception as e:LOG.warning('Quality image load failed for %s: %s',pp,e)
 stage['yuan_decode']+=time.perf_counter()-t
 if not images:return []
 t=time.perf_counter();clip_embeddings=ex._batch_clip_embeddings(images);stage['yuan_semantic_clip']+=time.perf_counter()-t
 t=time.perf_counter();cached=_brisque_cached_raw(valid);missing=[pp for pp in valid if str(pp) not in cached]
 if missing:
  fresh=ex._batch_brisque_parallel(missing);_store_brisque_raw(list(zip([str(x) for x in missing],fresh)));cached.update({str(pp):float(v) for pp,v in zip(missing,fresh)})
 brisque_scores=[cached[str(pp)] for pp in valid];stage['yuan_brisque']+=time.perf_counter()-t
 t=time.perf_counter();aesthetic_scores=ex.laion_model.batch_calculate_aesthetic_scores_from_clip(clip_embeddings);stage['yuan_aesthetic']+=time.perf_counter()-t
 rows=[]
 for pp,br,ae,emb in zip(valid,brisque_scores,aesthetic_scores,clip_embeddings):
  rows.append({'image_path':str(pp),'brisque_raw':float(br),'aesthetic_raw':float(ae),'brisque_normalized':ex.brisque_model.normalize_score(float(br)),'aesthetic_normalized':ex.laion_model.normalize_score(float(ae)),'clip_embedding':emb.numpy()})
 return rows

def quality_paths(paths,model_name='openai/clip-vit-base-patch32',progress=None,batch_size=16):
 """Yuan quality fusion with persistent accelerator tuning and independent work units."""
 import numpy as np
 torch,clip,proc,device=clip_parts(model_name);_,head=iqf_head();head=head.to(device).eval();extractor=iqf_extractor();_install_resident_brisque(extractor)
 results=[];done=0;stage={'yuan_decode':0.0,'yuan_brisque':0.0,'yuan_semantic_clip':0.0,'yuan_aesthetic':0.0,'n8_clip':0.0,'fusion':0.0,'archive':0.0}
 yuan_devices=_yuan_device_report(extractor);clip_device,clip_dtype=_module_device_dtype(clip)
 tune_key=_quality_tune_key(torch,device,model_name);tuning=_accel_tuning_read();receipt=tuning.get(tune_key,{})
 # P.15 could persist batch=1 before it had sampled anything. Only trust v2 receipts.
 learned=int(receipt.get('batch_size',0) or 0) if int(receipt.get('tuner_version',0) or 0)>=3 else 0
 probe_sizes=[8,16,32,64,128,256,512];probe_index=0
 current=max(8,learned) if learned else probe_sizes[0]
 tuning_active=not bool(learned) and str(device).startswith('cuda');best_batch=current;best_rate=0.0;previous_rate=None
 # Filesystem/checkpoint work units stay large and independent of GPU inference batches.
 work_unit=max(256,current*2)
 start=0
 try:
  while start<len(paths):
   raw_unit=paths[start:start+min(work_unit,len(paths)-start)];valid_unit=[norm(x) for x in raw_unit if image_file(norm(x))]
   LOG.info('Quality work unit %s-%s / %s (target inference batch %s%s)',start+1,start+len(raw_unit),len(paths),current,' tuning' if tuning_active else '')
   pos=0
   while pos<len(valid_unit):
    infer_paths=valid_unit[pos:pos+current]
    if not infer_paths:break
    batch_wall=time.perf_counter()
    try:
     feature_rows=_yuan_batch_features(extractor,infer_paths,stage)
     if not feature_rows:pos+=len(infer_paths);continue
     actual=[Path(r['image_path']) for r in feature_rows]
     # Canonical N8Vision CLIP is a true GPU batch too.
     t=time.perf_counter();images=[]
     for pp in actual:
      with Image.open(pp) as im:images.append(ImageOps.exif_transpose(im).convert('RGB').copy())
     pix=proc(images=images,return_tensors='pt')['pixel_values'].to(device,non_blocking=True)
     with torch.inference_mode(),_amp_context(torch,device):
      iv=_feature_tensor(clip.get_image_features(pixel_values=pix));iv=iv/iv.norm(dim=-1,keepdim=True)
     vectors=iv.float().detach().cpu().numpy().astype('float32');stage['n8_clip']+=time.perf_counter()-t
     brs=torch.tensor([float(r['brisque_normalized']) for r in feature_rows],dtype=torch.float32,device=device)
     las=torch.tensor([float(r['aesthetic_normalized']) for r in feature_rows],dtype=torch.float32,device=device)
     cvs=torch.tensor(np.stack([r['clip_embedding'] for r in feature_rows]),dtype=torch.float32,device=device)
     t=time.perf_counter()
     with torch.inference_mode():scores=head(brs,las,cvs).detach().float().cpu().numpy().reshape(-1)
     stage['fusion']+=time.perf_counter()-t
     t=time.perf_counter()
     with db() as c:
      for pp,r,score,vec in zip(actual,feature_rows,scores,vectors):
       br=float(r['brisque_normalized']);la=float(r['aesthetic_normalized']);score=float(score)
       c.execute("DELETE FROM observations WHERE path=? AND (provider LIKE 'clip-triage%' OR provider='clip-triage-caliper-v1' OR provider LIKE 'yuan-iqf%')",(str(pp),))
       c.execute("INSERT OR REPLACE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,?,?,?,?,?,unixepoch())",(str(pp),'quality',score/10.0,'yuan-iqf-v2','matthewyuan/image-quality-fusion','quality',json.dumps({'score':score,'brisque':br,'aesthetic':la})))
       c.execute("INSERT OR REPLACE INTO embeddings(path,provider,model,dim,vector,updated) VALUES(?,?,?,?,?,unixepoch())",(str(pp),'clip',model_name,len(vec),vec.tobytes()))
       results.append({'path':str(pp),'score':score,'brisque':br,'aesthetic':la})
      c.commit()
     bump_obs_revision();stage['archive']+=time.perf_counter()-t
    except RuntimeError as e:
     if tuning_active and 'out of memory' in str(e).lower() and best_rate>0:
      LOG.warning('Quality tuning hit accelerator memory limit at batch %s; keeping %s',current,best_batch)
      if str(device).startswith('cuda'):torch.cuda.empty_cache()
      current=best_batch;tuning_active=False
      tuning[tune_key]={'tuner_version':3,'batch_size':best_batch,'target_pps':round(best_rate,3),'device':str(device),'model':model_name,'updated':time.time()};_accel_tuning_write(tuning)
      continue
     raise
    elapsed=max(.001,time.perf_counter()-batch_wall);rate=len(feature_rows)/elapsed
    if rate>best_rate:best_rate=rate;best_batch=len(feature_rows)
    # Calibration must sample several real batch sizes before it can settle.
    if tuning_active and len(infer_paths)==current:
     gain=None if previous_rate is None else (rate/previous_rate-1.0)
     if previous_rate is not None and probe_index>=2 and gain<.10:
      tuning_active=False;current=best_batch
      tuning[tune_key]={'tuner_version':3,'batch_size':best_batch,'target_pps':round(best_rate,3),'device':str(device),'model':model_name,'updated':time.time()};_accel_tuning_write(tuning)
      LOG.info('Quality accelerator tuned: batch %s at %.2f p/s',best_batch,best_rate)
     else:
      previous_rate=rate;probe_index+=1
      if probe_index<len(probe_sizes):current=probe_sizes[probe_index]
      else:
       tuning_active=False;current=best_batch
       tuning[tune_key]={'tuner_version':3,'batch_size':best_batch,'target_pps':round(best_rate,3),'device':str(device),'model':model_name,'updated':time.time()};_accel_tuning_write(tuning)
    pos+=len(infer_paths);done+=len(infer_paths)
    telemetry={'device':device,'model_device':clip_device,'model_dtype':clip_dtype,'yuan_devices':yuan_devices,'inference_batch':len(infer_paths),'learned_batch':learned or (best_batch if not tuning_active else None),'target_pps':round(float(receipt.get('target_pps',0) or best_rate),2),'tuning':tuning_active,'brisque_workers':getattr(extractor,'_n8_brisque_workers',1),'stage_seconds':{k:round(v,3) for k,v in stage.items()}}
    if progress:progress(done,len(paths),telemetry=telemetry)
   start+=len(raw_unit)
  if tuning_active and best_rate>0:
   tuning[tune_key]={'tuner_version':3,'batch_size':best_batch,'target_pps':round(best_rate,3),'device':str(device),'model':model_name,'updated':time.time()};_accel_tuning_write(tuning)
 finally:
  # Keep model objects resident, but the worker threads belong to this Quality job.
  pool=getattr(extractor,'_n8_brisque_pool',None)
  if pool is not None:
   pool.shutdown(wait=True);extractor._n8_brisque_pool=None
 return {'processed':done,'results':results,'provider':'yuan-iqf-v2','batch_size':best_batch if not learned else learned,'device':device,'model_device':clip_device,'model_dtype':clip_dtype,'yuan_devices':yuan_devices,'target_pps':round(best_rate or float(receipt.get('target_pps',0) or 0),3),'brisque_workers':getattr(extractor,'_n8_brisque_workers',1),'stage_seconds':{k:round(v,3) for k,v in stage.items()}}

def classify_paths(paths,labels,model_name,progress=None,batch_size=32,triage=False):
 import numpy as np
 torch,m,proc,device=clip_parts(model_name)
 if not labels:raise ValueError('Provide at least one candidate label')
 # Text vectors are constant for a label set; compute once.
 tkey=('clip-text',model_name,tuple(labels))
 text_features=MODEL_CACHE.get(tkey)
 if text_features is None:
  ti=proc(text=labels,return_tensors='pt',padding=True)
  ti={k:v.to(device) for k,v in ti.items()}
  with torch.inference_mode():
   text_features=_feature_tensor(m.get_text_features(**ti))
   text_features=text_features/text_features.norm(dim=-1,keepdim=True)
  MODEL_CACHE[tkey]=text_features
 results=[];done=0
 with db() as c:
  for start in range(0,len(paths),max(1,batch_size)):
   raws=[];images=[]
   for raw in paths[start:start+max(1,batch_size)]:
    p=norm(raw)
    if not image_file(p):continue
    try:
     with Image.open(p) as im:images.append(ImageOps.exif_transpose(im).convert('RGB').copy());raws.append(str(p))
    except Exception:continue
   if not raws:continue
   inp=proc(images=images,return_tensors='pt');pix=inp['pixel_values'].to(device)
   with torch.inference_mode():
    iv=_feature_tensor(m.get_image_features(pixel_values=pix))
    iv=iv/iv.norm(dim=-1,keepdim=True)
    # CLIP's learned logit scale makes independent sigmoid scores useful as ranking/gating scores.
    scale=m.logit_scale.exp().clamp(max=100)
    cosine=iv@text_features.T
    logits=scale*cosine
    if triage:
     # Triage is a signed comparison, not a forced probability distribution.
     # Map normalized cosine similarity [-1,+1] onto [0,1] only for display/storage.
     # Crucially, scores are NOT normalized against each other.
     scores=((cosine+1.0)/2.0).clamp(0,1).detach().cpu().numpy()
    else:
     scores=logits.sigmoid().detach().cpu().numpy()
   vectors=iv.detach().cpu().numpy().astype('float32')
   for row,(raw,vec) in enumerate(zip(raws,vectors)):
    if triage:
     c.execute("DELETE FROM observations WHERE path=? AND (provider LIKE 'clip-triage%' OR provider='clip-triage-caliper-v1')",(raw,))
    c.execute('INSERT OR REPLACE INTO embeddings(path,provider,model,dim,vector,updated) VALUES(?,?,?,?,?,unixepoch())',
              (raw,'clip',model_name,len(vec),vec.tobytes()))
    ranked=sorted(zip(labels,scores[row].tolist()),key=lambda x:x[1],reverse=True)
    if triage:
     vals=dict(zip(labels,scores[row].tolist()))
     good_labels=labels[:4];bad_labels=labels[4:]
     good=sum(vals[x] for x in good_labels)/max(1,len(good_labels))
     bad_mean=sum(vals[x] for x in bad_labels)/max(1,len(bad_labels))
     bad_peak=max((vals[x] for x in bad_labels),default=0.0)
     failed=max(0.0,min(1.0,0.5+((0.65*bad_mean+0.35*bad_peak)-good)*3.0))
     for axis,axis_score in vals.items():
      c.execute("INSERT OR REPLACE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,?,?,?,'caliper',NULL,unixepoch())",
                (raw,axis,float(axis_score),'clip-triage-caliper-v1',model_name))
     c.execute("INSERT OR REPLACE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,?,?,?,'class',?,unixepoch())",
               (raw,'failed',float(failed),'clip-triage-v4',model_name,json.dumps({'good_mean':good,'bad_mean':bad_mean,'bad_peak':bad_peak,'axes':{k:float(v) for k,v in vals.items()}})))
     item={'path':raw,'failed':float(failed),'axes':{k:float(v) for k,v in vals.items()}}
    else:
     for concept,conf in ranked:
      c.execute("INSERT OR REPLACE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,?,?,?,'class',NULL,unixepoch())",
                (raw,concept,float(conf),'clip-zero-shot',model_name))
     item={'path':raw,'labels':[{'concept':x,'confidence':float(y)} for x,y in ranked]}
    results.append(item)
   c.commit();done+=len(raws);bump_obs_revision()
   if progress:progress(done,len(paths))
 return {'device':device,'model':model_name,'results':results,'embedded':done,'batch_size':batch_size}

@app.post('/api/mv/classify')
def classify(req:ClassifyRequest):
 labels=[x.strip() for x in req.labels if x.strip()]
 if len(labels)<1:raise HTTPException(400,'Provide at least one candidate label')
 try:return {'status':'ok',**classify_paths(req.paths,labels,req.model)}
 except Exception as e:raise HTTPException(500,f'Classification failed: {e}')

def embed_paths(paths,model_name,progress=None,batch_size=64):
 """Batched CLIP embeddings with explicit CUDA routing and stage telemetry."""
 import numpy as np
 from concurrent.futures import ThreadPoolExecutor
 torch,m,proc,device=clip_parts(model_name);done=0;batch_size=max(1,int(batch_size or 64))
 model_device,model_dtype=_module_device_dtype(m)
 if device=='cuda' and not model_device.startswith('cuda'):
  raise RuntimeError(f'CUDA selected but CLIP parameters are on {model_device}')
 decode_workers=max(1,min(4,(os.cpu_count() or 2)//2))
 stage={'decode':0.0,'preprocess':0.0,'h2d':0.0,'inference':0.0,'d2h':0.0,'archive':0.0};batches=0
 def load_one(raw):
  p=norm(raw)
  if not image_file(p):return None
  try:
   with Image.open(p) as im:return str(p),ImageOps.exif_transpose(im).convert('RGB').copy()
  except Exception as e:
   LOG.warning('Embedding decode skipped %s: %s',p,e);return None
 LOG.info('Embedding pipeline: target=%s actual_model=%s dtype=%s batch=%s decode_workers=%s model=%s',device,model_device,model_dtype,batch_size,decode_workers,model_name)
 with ThreadPoolExecutor(max_workers=_grid_worker_cap(decode_workers),thread_name_prefix='embed-decode') as pool:
  for start in range(0,len(paths),batch_size):
   t=time.perf_counter();loaded=[x for x in pool.map(load_one,paths[start:start+batch_size]) if x is not None];stage['decode']+=time.perf_counter()-t
   if not loaded:
    if progress:progress(min(len(paths),start+batch_size),len(paths))
    continue
   raws=[x[0] for x in loaded];images=[x[1] for x in loaded]
   t=time.perf_counter();inputs=proc(images=images,return_tensors='pt');pix=inputs['pixel_values'];stage['preprocess']+=time.perf_counter()-t
   t=time.perf_counter()
   if device=='cuda':pix=pix.pin_memory().to(device,non_blocking=True)
   else:pix=pix.to(device)
   if device=='cuda':torch.cuda.synchronize()
   stage['h2d']+=time.perf_counter()-t
   if str(pix.device)!=model_device:raise RuntimeError(f'Embedding tensor is on {pix.device}, model is on {model_device}')
   t=time.perf_counter()
   with torch.inference_mode(),_amp_context(torch,device):
    v=_feature_tensor(m.get_image_features(pixel_values=pix));v=v/v.norm(dim=-1,keepdim=True)
   if device=='cuda':torch.cuda.synchronize()
   stage['inference']+=time.perf_counter()-t
   t=time.perf_counter();vectors=v.float().detach().cpu().numpy().astype('float32');stage['d2h']+=time.perf_counter()-t
   t=time.perf_counter()
   with db() as c:
    c.executemany('INSERT OR REPLACE INTO embeddings(path,provider,model,dim,vector,updated) VALUES(?,?,?,?,?,unixepoch())',[(raw,'clip',model_name,len(vec),vec.tobytes()) for raw,vec in zip(raws,vectors)])
   stage['archive']+=time.perf_counter()-t
   done+=len(raws);batches+=1;bump_obs_revision()
   tele={'device':device,'model_device':model_device,'model_dtype':model_dtype,'tensor_device':str(pix.device),'batch_size':len(raws),'batches':batches,'stage_seconds':{k:round(v,3) for k,v in stage.items()}}
   if progress:progress(min(len(paths),start+batch_size),len(paths),telemetry=tele)
 return {'embedded':done,'device':device,'precision':'fp16-autocast' if device=='cuda' else 'fp32','model':model_name,'model_device':model_device,'model_dtype':model_dtype,'batch_size':batch_size,'decode_workers':decode_workers,'batches':batches,'stage_seconds':{k:round(v,3) for k,v in stage.items()}}
@app.post('/api/mv/embed')
def embed(req:EmbedRequest):
 try:return embed_paths(req.paths,req.model)
 except Exception as e:raise HTTPException(500,f'Embedding failed: {e}')

def detect_paths(paths,model_name,conf,progress=None):
 from ultralytics import YOLO
 key=('yolo',model_name);model=MODEL_CACHE.get(key) or YOLO(model_name);MODEL_CACHE[key]=model;done=0
 with db() as c:
  for i,raw in enumerate(paths):
   p=norm(raw)
   if not image_file(p):continue
   result=model(str(p),conf=conf,verbose=False)[0]; c.execute("DELETE FROM observations WHERE path=? AND provider='ultralytics' AND model=?",(str(p),model_name))
   names=result.names
   if result.boxes is not None:
    boxes=result.boxes.xyxy.cpu().tolist(); cls=result.boxes.cls.cpu().tolist(); scores=result.boxes.conf.cpu().tolist()
    for n,(box,ci,score) in enumerate(zip(boxes,cls,scores)):
     geom={'bbox':box,'instance':n,'source_size':[int(result.orig_shape[1]),int(result.orig_shape[0])]}
     if result.masks is not None and n<len(result.masks.xy):geom['polygon']=result.masks.xy[n].tolist()
     c.execute("INSERT OR REPLACE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,?,?,?,?,?,unixepoch())",(str(p),str(names[int(ci)]),float(score),'ultralytics',model_name,'mask' if 'polygon' in geom else 'bbox',json.dumps(geom)))
   done+=1
   if progress:progress(i+1,len(paths))
 bump_obs_revision();return {'analyzed':done,'model':model_name}
@app.post('/api/mv/detect')
def detect(req:DetectRequest):
 try:return detect_paths(req.paths,req.model,req.confidence)
 except Exception as e:raise HTTPException(500,f'Detection failed: {e}')

SAM_INFERENCE_LOCK=threading.RLock()

def _sam_box_geometry(path,bbox):
 """The single SAM implementation used by Mask Studio and global SAM Boxes.

 Produces the exact editable crop-RLE contract consumed by Mask Studio.
 Does not save observations or decide their detector identity.
 """
 import numpy as np
 from ultralytics import SAM
 p=norm(path)
 if not image_file(p):raise ValueError(f'Image not found: {p}')
 if len(bbox)!=4:raise ValueError('bbox requires four coordinates')
 with Image.open(p) as im:
  w,h=ImageOps.exif_transpose(im).size
 x1,y1,x2,y2=map(float,bbox)
 x1,x2=sorted((max(0,x1),min(w,x2)))
 y1,y2=sorted((max(0,y1),min(h,y2)))
 if x2-x1<2 or y2-y1<2:raise ValueError('Box is empty')
 with SAM_INFERENCE_LOCK:
  weight=SAM_MODELS/'sam_b.pt'
  old=os.getcwd();os.chdir(SAM_MODELS)
  try:
   model=MODEL_CACHE.get('sam-box')
   if model is None:
    model=SAM(str(weight if weight.exists() else 'sam_b.pt'))
    MODEL_CACHE['sam-box']=model
  finally:os.chdir(old)
  result=model(str(p),bboxes=[[x1,y1,x2,y2]],verbose=False)[0]
 if result.masks is None or len(result.masks.data)<1:raise RuntimeError('SAM returned no mask')
 mask=result.masks.data[0].detach().cpu().numpy()>0.5
 if mask.shape!=(h,w):
  mask=np.asarray(Image.fromarray(mask.astype('uint8')).resize((w,h),Image.Resampling.NEAREST))>0
 xa,ya,xb,yb=map(int,(round(x1),round(y1),round(x2),round(y2)))
 crop=mask[ya:yb,xa:xb]
 if crop.size==0 or not crop.any():raise RuntimeError('SAM returned an empty mask')
 return {'bbox':[xa,ya,xb,yb],'mask_size':[int(crop.shape[1]),int(crop.shape[0])],
         'mask_rle':_rle_from_binary(crop),'method':'sam','review_required':True}

def segment_paths(paths,model_name,source=None,min_conf=None,progress=None):
 """Attach SAM masks to every unmasked, object-localized box in the requested paths.

 Provider, detector availability and confidence are provenance, not eligibility.
 Whole-image observations are never segmented. Each source row is updated in place.
 """
 done=0;created=0;already_masked=0;ineligible=0;failed=0;boxes_found=0;eligible=0
 with db() as c:
  for i,raw in enumerate(paths):
   p=norm(raw)
   rows=c.execute("SELECT rowid AS oid,concept,confidence,provider,model,kind,geometry FROM observations WHERE path=? AND geometry IS NOT NULL",(str(p),)).fetchall()
   for r in rows:
    try:g=json.loads(r['geometry'] or '{}')
    except (ValueError,TypeError):failed+=1;continue
    if not isinstance(g,dict):ineligible+=1;continue
    # Whole-image is a semantic scope, not a test of the box's dimensions.
    if r['kind']=='image' or str(g.get('scope','')).lower() in ('image','whole_image','whole-image'):
     continue
    box=g.get('bbox')
    if not isinstance(box,(list,tuple)) or len(box)!=4:continue
    try:
     coords=[float(v) for v in box]
     if not all(math.isfinite(v) for v in coords) or abs(coords[2]-coords[0])<2 or abs(coords[3]-coords[1])<2:
      ineligible+=1;continue
    except (TypeError,ValueError,OverflowError):ineligible+=1;continue
    boxes_found+=1
    # Valid existing segmentation is never overwritten; broken mask labels with
    # bbox geometry can still be repaired by SAM.
    has_rle=isinstance(g.get('mask_rle'),list) and bool(g['mask_rle']) and isinstance(g.get('mask_size'),list) and len(g['mask_size'])==2
    has_polygon=bool(g.get('polygon'))
    if has_rle or has_polygon:
     already_masked+=1;continue
    eligible+=1
    try:
     mask=_sam_box_geometry(p,coords)
     if not g.get('source_size'):
      with Image.open(p) as im:g['source_size']=list(ImageOps.exif_transpose(im).size)
     geom={**g,**mask,'scope':'mask','review_status':'draft',
           'source_provider':r['provider'],'source_model':r['model'],
           'source_confidence':r['confidence'],'source_bbox':box,
           'source_instance':g.get('instance'),'sam_model':'sam_b.pt'}
     encoded=json.dumps(geom,separators=(',',':'),sort_keys=True)
     c.execute('SAVEPOINT sam_observation')
     try:
      changed=c.execute("UPDATE observations SET kind='mask',geometry=?,updated=unixepoch() WHERE rowid=? AND kind=? AND geometry IS ?",
                        (encoded,r['oid'],r['kind'],r['geometry']))
      if changed.rowcount!=1:raise RuntimeError('Source observation changed during SAM conversion')
      c.execute('RELEASE SAVEPOINT sam_observation')
     except Exception:
      c.execute('ROLLBACK TO SAVEPOINT sam_observation')
      c.execute('RELEASE SAVEPOINT sam_observation')
      raise
     created+=1
    except Exception as e:
     failed+=1;LOG.warning('SAM Boxes failed %s (%s, %s): %s',p,r['concept'],r['model'],e)
   done+=1
   if progress:progress(i+1,len(paths))
 LOG.info('SAM Boxes: %d images, %d boxes found, %d eligible, %d masks attached, %d already masked, %d ineligible, %d failures',done,boxes_found,eligible,created,already_masked,ineligible,failed)
 if created:bump_obs_revision()
 return {'analyzed':done,'boxes_found':boxes_found,'boxes_eligible':eligible,
         'masks_created':created,'masks_skipped':already_masked+ineligible,
         'masks_already_masked':already_masked,'masks_ineligible':ineligible,'masks_failed':failed,
         'model':'sam_b.pt','requested_model':model_name}
@app.post('/api/mv/segment')
def segment(req:SegmentRequest):
 try:return segment_paths(req.paths,req.model,req.source_provider,req.min_confidence)
 except Exception as e:raise HTTPException(500,f'Segmentation failed: {e}')

@app.post('/api/search/semantic')
def semantic(req:SemanticRequest):
 try:
  import numpy as np
  torch,m,proc,device=clip_parts(req.model); inputs=proc(text=[req.query],return_tensors='pt',padding=True); ids=inputs['input_ids'].to(device);att=inputs.get('attention_mask');att=att.to(device) if att is not None else None
  with torch.inference_mode():
   q=_feature_tensor(m.get_text_features(input_ids=ids,attention_mask=att));q=q/q.norm(dim=-1,keepdim=True)
  qv=q[0].cpu().numpy().astype('float32'); allowed=set(req.paths) if req.paths else None
  with db() as c:rows=c.execute("SELECT path,dim,vector FROM embeddings WHERE provider='clip' AND model=?",(req.model,)).fetchall()
  vals=[]
  for r in rows:
   if allowed is not None and r['path'] not in allowed:continue
   v=np.frombuffer(r['vector'],dtype='float32'); vals.append((r['path'],float(v@qv)))
  vals.sort(key=lambda x:x[1],reverse=True);return {'results':[{'path':p,'score':s} for p,s in vals[:req.limit]],'searched':len(vals)}
 except Exception as e:raise HTTPException(500,f'Semantic search failed: {e}')

@app.get('/api/config')
def client_config():
 cfg=_load_config()
 mode=os.environ.get('N8VISION_GRID_DETAIL',str(cfg.get('grid_detail','hover'))).lower()
 if mode not in {'hover','diagnostic'}:mode='hover'
 root=cfg.get('default_root')
 sanity_badges=str(cfg.get('sanity_badges','compact')).lower()
 if sanity_badges not in {'compact','verbose'}:sanity_badges='compact'
 return {'grid_detail':mode,'grid_gap_tenths':max(0,min(20,int(cfg.get('grid_gap_tenths',1)))),'viewer_target':str(cfg.get('viewer_target','system') or 'system'),'sanity_badges':sanity_badges,'default_root':root if root and Path(root).exists() else None,'filter_presets':cfg.get('filter_presets',{}),'sanity':cfg.get('sanity',CONFIG_DEFAULTS['sanity']),'thumbnail_cache':{'path':str(cfg.get('thumbnail_cache',{}).get('path','') or ''),'automatic':not bool(cfg.get('thumbnail_cache',{}).get('path')),'max_axis':300,'delete_orphans_on_maintenance':bool(cfg.get('thumbnail_cache',{}).get('delete_orphans_on_maintenance',True))},'ringworld':cfg.get('ringworld',CONFIG_DEFAULTS['ringworld']),'thumbnail_warm':{'max_mb':int(cfg.get('thumbnail_cache',{}).get('max_mb',200)),'enabled':bool(cfg.get('thumbnail_cache',{}).get('warm_archive',True))},'prompt_translator':cfg.get('prompt_translator',CONFIG_DEFAULTS['prompt_translator']),'checkpoint_library':cfg.get('checkpoint_library',CONFIG_DEFAULTS['checkpoint_library'])}

@app.put('/api/config/display')
def display_settings(req:DisplaySettingsRequest):
 mode=req.grid_detail.lower()
 if mode not in {'hover','diagnostic'}:raise HTTPException(400,'grid_detail must be hover or diagnostic')
 cfg=_load_config();cfg['grid_detail']=mode
 if req.grid_gap_tenths is not None:cfg['grid_gap_tenths']=max(0,min(20,int(req.grid_gap_tenths)))
 _save_config(cfg);return {'grid_detail':mode,'grid_gap_tenths':cfg.get('grid_gap_tenths',1)}

@app.put('/api/config/sanity-display')
def sanity_display_settings(req:SanityDisplaySettingsRequest):
 mode=req.sanity_badges.lower()
 if mode not in {'compact','verbose'}:raise HTTPException(400,'sanity_badges must be compact or verbose')
 cfg=_load_config();cfg['sanity_badges']=mode;_save_config(cfg);return {'sanity_badges':mode}

@app.put('/api/config/sanity')
def sanity_settings(req:SanitySettingsRequest):
 cfg=_load_config()
 cfg['sanity']={
  'thumbnail':max(64,min(512,int(req.thumbnail))),
  'edge_threshold':max(1,min(254,int(req.edge_threshold))),
  'light_blur':max(0.0,min(12.0,float(req.light_blur))),
  'medium_blur':max(0.0,min(12.0,float(req.medium_blur))),
  'heavy_blur':max(0.0,min(12.0,float(req.heavy_blur))),
  'grade_b_largest_fraction':max(0.0,min(1.0,float(req.grade_b_largest_fraction))),
  'uncapped_unsanity':bool(req.uncapped_unsanity)
 }
 _save_config(cfg);return {'sanity':cfg['sanity']}

@app.put('/api/config/default-root')
def default_root(req:DefaultRootRequest):
 cfg=_load_config()
 if req.path:
  root=norm(req.path)
  if not root.exists() or not root.is_dir():raise HTTPException(400,'Default root must be an existing directory')
  cfg['default_root']=str(root)
 else:cfg.pop('default_root',None)
 _save_config(cfg);return {'default_root':cfg.get('default_root')}

@app.put('/api/config/thumbnail-cache')
def thumbnail_cache_settings(req:ThumbnailCacheRequest):
 global THUMB_CACHE_ROOT_CACHE
 cfg=_load_config();tc=cfg.setdefault('thumbnail_cache',{})
 if req.path:
  root=norm(req.path);root.mkdir(parents=True,exist_ok=True)
  if not root.is_dir():raise HTTPException(400,'Thumbnail cache path must be a directory')
  # Prove writability now instead of discovering it while scrolling the grid.
  probe=root/('.n8vision-write-test-'+uuid.uuid4().hex)
  try:probe.write_bytes(b'');probe.unlink()
  except Exception as e:raise HTTPException(400,f'Thumbnail cache path is not writable: {e}')
  tc['path']=str(root)
 else:tc['path']=''
 tc['max_axis']=300;tc.setdefault('producer_version',1);_save_config(cfg);THUMB_CACHE_ROOT_CACHE=None
 return {'path':str(tc.get('path','') or ''),'max_axis':300,'automatic':not bool(tc.get('path')),'delete_orphans_on_maintenance':bool(tc.get('delete_orphans_on_maintenance',True))}

class ThumbnailMaintenanceRequest(BaseModel):
 delete_orphans_on_maintenance:bool
class StorageClassRequest(BaseModel):
 path:str; storage_class:str='auto'
class DriveExportRequest(BaseModel):
 path:str; include_thumbnails:bool=True; include_projects:bool=True

@app.put('/api/config/thumbnail-maintenance')
def thumbnail_maintenance_settings(req:ThumbnailMaintenanceRequest):
 cfg=_load_config();tc=cfg.setdefault('thumbnail_cache',{});tc['delete_orphans_on_maintenance']=bool(req.delete_orphans_on_maintenance);_save_config(cfg)
 return {'delete_orphans_on_maintenance':tc['delete_orphans_on_maintenance']}

@app.get('/api/storage-class')
def get_storage_class(path:str):
 p=norm(path);key=_volume_key(p);cfg=_load_config();entry=cfg.get('storage_classes',{}).get(key,{})
 return {'volume_key':key,'root':str(_volume_root(p)),'detected':_detected_storage_class(p),'configured':entry.get('class','auto') if isinstance(entry,dict) else 'auto','effective':storage_class(p)}

@app.put('/api/storage-class')
def set_storage_class(req:StorageClassRequest):
 p=norm(req.path);val=req.storage_class.lower()
 if val not in {'auto','fixed','removable','network','volatile'}:raise HTTPException(400,'Invalid storage class')
 cfg=_load_config();cfg.setdefault('storage_classes',{})[_volume_key(p)]={'class':val,'root_hint':str(_volume_root(p))};_save_config(cfg)
 return get_storage_class(str(p))

def _drive_export(path:Path,include_thumbnails=True,include_projects=True):
 vol=_volume_root(path);dest=vol/'.N8VisionExport';dest.mkdir(parents=True,exist_ok=True)
 stamp=time.strftime('%Y%m%d-%H%M%S');tmpdb=dest/f'catalog-{stamp}.tmp.sqlite3';outzip=dest/f'n8vision-snapshot-{stamp}.zip';prefix=str(vol)
 src=sqlite3.connect(DB_PATH);src.row_factory=sqlite3.Row;dst=sqlite3.connect(tmpdb)
 try:
  dst.execute('CREATE TABLE observations(path TEXT,concept TEXT,confidence REAL,provider TEXT,model TEXT,kind TEXT,geometry TEXT,updated REAL)')
  dst.execute('CREATE TABLE embeddings(path TEXT,provider TEXT,model TEXT,dim INTEGER,vector BLOB,updated REAL)')
  dst.execute('CREATE TABLE tracked_files(path TEXT,sha256 TEXT,size INTEGER,mtime REAL,orphaned INTEGER,last_seen REAL)')
  dst.execute('CREATE TABLE corrections(id INTEGER,path TEXT,original_concept TEXT,original_provider TEXT,original_model TEXT,original_kind TEXT,geometry TEXT,action TEXT,corrected_concept TEXT,created REAL)')
  for table in ('observations','embeddings','tracked_files'):
   rows=src.execute(f'SELECT * FROM {table} WHERE path LIKE ?',(prefix+'%',)).fetchall()
   if rows:
    cols=rows[0].keys();qs=','.join('?'*len(cols));dst.executemany(f"INSERT INTO {table}({','.join(cols)}) VALUES({qs})",([r[c] for c in cols] for r in rows))
  try:
   rows=src.execute('SELECT * FROM corrections WHERE path LIKE ?',(prefix+'%',)).fetchall()
   if rows:
    cols=rows[0].keys();qs=','.join('?'*len(cols));dst.executemany(f"INSERT INTO corrections({','.join(cols)}) VALUES({qs})",([r[c] for c in cols] for r in rows))
  except sqlite3.OperationalError:pass
  dst.commit()
 finally:src.close();dst.close()
 counts={};c=sqlite3.connect(tmpdb)
 for t in ('tracked_files','observations','embeddings','corrections'):counts[t]=c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
 c.close()
 handshake={'schema':'n8vision-drive-export-v1','created':time.time(),'n8vision_version':'P.11','volume_key':_volume_key(path),'volume_root':str(vol),'storage_class':storage_class(path),'counts':counts,'relative_paths':True,'archive':outzip.name}
 with zipfile.ZipFile(outzip,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  z.write(tmpdb,'catalog.sqlite3');z.writestr('handshake.json',json.dumps(handshake,indent=2))
  if include_thumbnails:
   cache=thumbnail_cache_root(path)
   if cache.exists() and _volume_root(cache)==vol:
    for f in cache.rglob('*'):
     if f.is_file():z.write(f,'cache/'+str(f.relative_to(cache)).replace('\\','/'))
  if include_projects:
   project_roots=[vol/'N8Vision',vol/'.N8VisionProjects']
   for pr in project_roots:
    if not pr.exists():continue
    for mf in pr.rglob('n8vision-project.json'):
     try:z.write(mf,'projects/'+str(mf.relative_to(vol)).replace('\\','/'))
     except Exception:pass
 tmpdb.unlink(missing_ok=True);handshake['bytes']=outzip.stat().st_size;(dest/'handshake.json').write_text(json.dumps(handshake,indent=2),encoding='utf-8')
 return {'ok':True,'archive':str(outzip),'handshake':str(dest/'handshake.json'),'counts':counts,'bytes':handshake['bytes']}

@app.post('/api/drive-export')
def drive_export(req:DriveExportRequest):return _drive_export(norm(req.path),req.include_thumbnails,req.include_projects)

@app.get('/api/filter-presets')
def filter_presets():return {'presets':_load_config().get('filter_presets',{})}

@app.put('/api/filter-presets')
def save_filter_preset(req:FilterPresetRequest):
 name=req.name.strip()
 if not name:raise HTTPException(400,'Preset name required')
 cfg=_load_config();presets=cfg.setdefault('filter_presets',{});presets[name]=req.state;_save_config(cfg);return {'name':name,'presets':presets}

@app.delete('/api/filter-presets/{name}')
def delete_filter_preset(name:str):
 cfg=_load_config();presets=cfg.setdefault('filter_presets',{});presets.pop(name,None);_save_config(cfg);return {'presets':presets}

def _comparison_rows(model,paths):
 # None retains the unscoped API behavior; an explicit empty scope is empty.
 with db() as c:
  if paths is None:return c.execute("SELECT path,dim,vector FROM embeddings WHERE provider='clip' AND model=?",(model,)).fetchall()
  result=[];scope=list(dict.fromkeys(paths))
  for start in range(0,len(scope),800):
   chunk=scope[start:start+800];marks=','.join('?'*len(chunk))
   result.extend(c.execute(f"SELECT path,dim,vector FROM embeddings WHERE provider='clip' AND model=? AND path IN ({marks})",[model,*chunk]).fetchall())
  return result

@app.post('/api/compare/similar')
def compare_similar(req:SimilarRequest):
 try:
  import numpy as np
  target=str(norm(req.path));allowed=set(req.paths) if req.paths else None
  with db() as c:
   row=c.execute("SELECT dim,vector FROM embeddings WHERE path=? AND provider='clip' AND model=?",(target,req.model)).fetchone()
   if not row:raise HTTPException(409,'Selected image has no CLIP embedding yet')
  rows=_comparison_rows(req.model,req.paths)
  q=np.frombuffer(row['vector'],dtype='float32');vals=[]
  for r in rows:
   if r['path']==target or (allowed is not None and r['path'] not in allowed):continue
   v=np.frombuffer(r['vector'],dtype='float32');vals.append((r['path'],float(v@q)))
  vals.sort(key=lambda x:x[1],reverse=True)
  return {'source':target,'results':[{'path':p,'score':score} for p,score in vals[:req.limit]],'searched':len(vals)}
 except HTTPException:raise
 except Exception as e:raise HTTPException(500,f'Similarity search failed: {e}')

@app.post('/api/compare/unique')
def compare_unique(req:UniqueRequest):
 """Approximate library uniqueness from mean cosine distance to K nearest neighbors.
 HNSW keeps this usable for large libraries; results are transient UI scores for now."""
 try:
  import numpy as np
  try:import faiss
  except Exception:raise HTTPException(409,'FAISS is not installed; install the classifier/vector provider first')
  allowed=set(req.paths) if req.paths else None
  rows=_comparison_rows(req.model,req.paths)
  rows=[r for r in rows if allowed is None or r['path'] in allowed]
  if len(rows)<2:return {'results':[],'searched':len(rows),'neighbors':0}
  paths=[r['path'] for r in rows];x=np.vstack([np.frombuffer(r['vector'],dtype='float32') for r in rows]).astype('float32')
  faiss.normalize_L2(x);dim=x.shape[1];k=max(1,min(int(req.neighbors),32,len(rows)-1))
  index=faiss.IndexHNSWFlat(dim,24,faiss.METRIC_INNER_PRODUCT);index.hnsw.efConstruction=80;index.hnsw.efSearch=max(48,k*4);index.add(x)
  d,_=index.search(x,k+1);neighbor_sim=d[:,1:k+1].mean(axis=1);scores=1.0-neighbor_sim
  result=[{'path':p,'score':float(v)} for p,v in zip(paths,scores)];result.sort(key=lambda z:z['score'],reverse=True)
  return {'results':result,'searched':len(result),'neighbors':k,'method':'HNSW mean neighbor cosine distance'}
 except HTTPException:raise
 except Exception as e:raise HTTPException(500,f'Uniqueness analysis failed: {e}')


def _pixel_digest(path:str)->str:
 """Hash decoded pixels, dimensions and mode, deliberately ignoring file container/metadata."""
 with Image.open(path) as im:
  im=ImageOps.exif_transpose(im).convert('RGBA')
  h=hashlib.sha256()
  h.update(f'{im.width}x{im.height}:RGBA:'.encode('ascii'))
  h.update(im.tobytes())
  return h.hexdigest()

@app.post('/api/compare/duplicates')
def compare_duplicates(req:DuplicateRequest):
 """Filter to exact visual duplicates, using CLIP neighbors only as candidate generation.
 This avoids all-pairs pixel comparison while still ignoring container metadata/encoding."""
 try:
  import numpy as np
  try:import faiss
  except Exception:raise HTTPException(409,'FAISS is not installed; install the classifier/vector provider first')
  allowed=set(req.paths) if req.paths else None
  rows=_comparison_rows(req.model,req.paths)
  rows=[r for r in rows if (allowed is None or r['path'] in allowed) and Path(r['path']).is_file()]
  if len(rows)<2:return {'results':[],'groups':0,'searched':len(rows),'candidates':0,'neighbors':0}
  paths=[r['path'] for r in rows];x=np.vstack([np.frombuffer(r['vector'],dtype='float32') for r in rows]).astype('float32')
  faiss.normalize_L2(x);k=max(1,min(int(req.neighbors),32,len(rows)-1));dim=x.shape[1]
  index=faiss.IndexHNSWFlat(dim,24,faiss.METRIC_INNER_PRODUCT);index.hnsw.efConstruction=80;index.hnsw.efSearch=max(48,k*4);index.add(x)
  sims,inds=index.search(x,k+1);candidate=set();threshold=max(-1.0,min(1.0,float(req.candidate_similarity)))
  for i in range(len(paths)):
   for sim,j in zip(sims[i,1:],inds[i,1:]):
    if j<0 or float(sim)<threshold:continue
    a,b=sorted((i,int(j)));candidate.add((a,b))
  involved={i for pair in candidate for i in pair};digests={}
  for i in involved:
   try:digests[i]=_pixel_digest(paths[i])
   except Exception as e:LOG.warning('Duplicate pixel check skipped %s: %s',paths[i],e)
  by_digest={}
  for i,d in digests.items():by_digest.setdefault(d,[]).append(i)
  groups=[]
  for members in by_digest.values():
   if len(members)<2:continue
   # Require at least one candidate edge so hashing cannot create an unrelated global scan.
   member_set=set(members)
   if not any(a in member_set and b in member_set for a,b in candidate):continue
   groups.append(sorted(members,key=lambda z:paths[z].lower()))
  groups.sort(key=lambda g:(-len(g),paths[g[0]].lower()))
  results=[]
  for group_id,members in enumerate(groups,1):
   for i in members:results.append({'path':paths[i],'score':1.0,'group':group_id,'group_size':len(members)})
  return {'results':results,'groups':len(groups),'searched':len(paths),'candidates':len(candidate),'neighbors':k,'candidate_similarity':threshold,'method':'CLIP near-neighbor candidates + decoded-pixel SHA-256'}
 except HTTPException:raise
 except Exception as e:raise HTTPException(500,f'Duplicate analysis failed: {e}')

class SubjectRequest(BaseModel):
 paths:list[str]
 classes:list[str]=[]
 max_passes:int=Field(default=8,ge=1,le=100)

SUBJECT_JOB_LOCK=threading.Lock()
def subject_paths(payload,progress=None):
 from .subjects import analyze,matching_annotation,rle,DEFAULT_CLASSES,REVISION,PIPELINE,target_label,superseded_composite,NAME_MIN_CONFIDENCE,duplicate_subject_rows
 created=0;inherited=0;attached=0;retired=0;failed=[]
 classes=list(dict.fromkeys(x.strip() for x in payload['classes'] if x.strip())) or _load_config().get('yolo',{}).get('world_classes') or DEFAULT_CLASSES
 # Serialize read/compare/write across subject jobs; never hold the DB during inference.
 with SUBJECT_JOB_LOCK:
  for index,raw in enumerate(payload['paths']):
   if progress:progress(index,len(payload['paths']))
   p=norm(raw)
   if not image_file(p):failed.append({'path':str(p),'error':'Image not found'});continue
   try:
    before=p.stat();source_signature=(before.st_mtime_ns,before.st_size)
    with db() as c:
     existing=[dict(row) for row in c.execute("SELECT rowid AS oid,concept,confidence,provider,model,kind,geometry FROM observations WHERE path=? AND kind IN ('bbox','mask') AND confidence>0",(str(p),)).fetchall()]
    candidates,shape=analyze(p,HF_CACHE,ULTRA_MODELS/'bbox'/'yolov8s-worldv2.pt',classes,existing,lambda box:_sam_box_geometry(p,box))
    after=p.stat()
    if (after.st_mtime_ns,after.st_size)!=source_signature:raise RuntimeError('Image changed during subject separation; retry it')
    if progress:progress(index,len(payload['paths'])) # cancellation before persistence
    changed=False;used=set()
    with db() as c:
     rows=[dict(row) for row in c.execute("SELECT rowid AS oid,concept,confidence,provider,model,kind,geometry FROM observations WHERE path=? AND kind IN ('bbox','mask') AND confidence>0",(str(p),)).fetchall()]
     removed_ids=set()
     for row in rows:
      try:old_geometry=json.loads(row['geometry'])
      except (TypeError,ValueError):continue
      if row['provider']!='subject-intelligence':
       trusted=bool(re.match(r'^(human|user|manual)(?:$|[-_:])',row['provider'],re.I)) or old_geometry.get('review_status')=='approved'
       accepted_score=float(old_geometry.get('name_confidence',row['confidence'])) if old_geometry.get('name_accepted') else float(row['confidence'])
       if not trusted and accepted_score<NAME_MIN_CONFIDENCE and (old_geometry.get('subject_role') or old_geometry.get('subject_pipeline')):
        marked={key:value for key,value in old_geometry.items() if key not in ('subject_role','subject_pipeline')}
        encoded=json.dumps(marked,sort_keys=True,separators=(',',':'))
        c.execute('UPDATE observations SET geometry=?,updated=unixepoch() WHERE rowid=? AND geometry IS ?',(encoded,row['oid'],row['geometry']))
        row['geometry']=encoded;changed=True
       continue
      if old_geometry.get('review_status')=='draft' and target_label(row['concept']) and float(row['confidence'])<NAME_MIN_CONFIDENCE:
       marked={**old_geometry,'proposed_concept':row['concept'],'name_confidence':float(row['confidence']),'name_min_confidence':NAME_MIN_CONFIDENCE,'name_accepted':False}
       encoded=json.dumps(marked,sort_keys=True,separators=(',',':'))
       c.execute("UPDATE observations SET concept='unidentified subject',geometry=?,updated=unixepoch() WHERE rowid=? AND geometry IS ?",(encoded,row['oid'],row['geometry']))
       row['concept']='unidentified subject';row['geometry']=encoded;old_geometry=marked;changed=True
      if old_geometry.get('method') not in ('birefnet','birefnet+sam') or old_geometry.get('review_status')!='draft':continue
      excluded=not target_label(row['concept']) and row['concept'].casefold()!='unidentified subject'
      if not excluded and not superseded_composite(row['concept'],old_geometry,candidates,shape):continue
      removed=c.execute('DELETE FROM observations WHERE rowid=? AND geometry IS ?',(row['oid'],row['geometry'])).rowcount
      retired+=removed;changed=changed or bool(removed)
      if removed:removed_ids.add(row['oid'])
     rows=[row for row in rows if row['oid'] not in removed_ids and (target_label(row['concept']) or row['concept'].casefold()=='unidentified subject')]
     for candidate in candidates:
      match=matching_annotation(candidate,rows,shape,used)
      if match and match[2]:
       row,old,_=match;used.add(row['oid']);inherited+=1
       marked={**old,'subject_role':True,'subject_pipeline':old.get('subject_pipeline') or PIPELINE}
       for key in ('name_confidence','name_min_confidence','name_accepted','proposed_concept'):
        if key in candidate:marked[key]=candidate[key]
       if marked!=old:
        encoded=json.dumps(marked,sort_keys=True,separators=(',',':'))
        updated=c.execute('UPDATE observations SET geometry=?,updated=unixepoch() WHERE rowid=? AND geometry IS ?',(encoded,row['oid'],row['geometry']))
        if updated.rowcount!=1:raise RuntimeError('Annotation changed during subject marking')
        changed=True
       continue
      x1,y1,x2,y2=candidate['bbox']
      mask=candidate['mask'][y1:y2,x1:x2]
      geometry={'bbox':candidate['bbox'],'mask_size':[x2-x1,y2-y1],'mask_rle':rle(mask),'source_size':[shape[1],shape[0]],'scope':'mask','method':'birefnet','review_required':True,'review_status':'draft','subject_role':True,'subject_pipeline':PIPELINE,'birefnet_revision':REVISION,'focused_pass':candidate.get('focused_pass',False)}
      for key in ('verification_pass','component_naming_pass','instance_separation','separation_error','separation_conflict_pixels','name_confidence','name_min_confidence','name_accepted','proposed_concept'):
       if key in candidate:geometry[key]=candidate[key]
      if candidate.get('instance_separation')=='sam':geometry['method']='birefnet+sam'
      if match:
       row,old,_=match;used.add(row['oid'])
       # Keep source label, detector identity and canonical box; crop into that box.
       box=list(map(int,old['bbox']));a,b,d,e=box;crop=candidate['mask'][b:e,a:d]
       geometry={**old,**geometry,'bbox':old['bbox'],'mask_size':[d-a,e-b],'mask_rle':rle(crop),'source_provider':row['provider'],'source_model':row['model']}
       encoded=json.dumps(geometry,sort_keys=True,separators=(',',':'))
       updated=c.execute("UPDATE observations SET kind='mask',geometry=?,updated=unixepoch() WHERE rowid=? AND kind=? AND geometry IS ?",(encoded,row['oid'],row['kind'],row['geometry']))
       if updated.rowcount!=1:raise RuntimeError('Annotation changed during subject inheritance')
       attached+=1;changed=True
      else:
       encoded=json.dumps(geometry,sort_keys=True,separators=(',',':'))
       inserted=c.execute("INSERT OR IGNORE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,?,?,?,'mask',?,unixepoch())",(str(p),candidate['concept'],max(.01,candidate['confidence']),'subject-intelligence',PIPELINE,encoded))
       created+=inserted.rowcount;changed=changed or bool(inserted.rowcount)
       if inserted.rowcount:used.add(inserted.lastrowid)
     persisted=[dict(row) for row in c.execute("SELECT rowid AS oid,concept,confidence,provider,model,kind,geometry FROM observations WHERE path=? AND kind='mask' AND confidence>0",(str(p),)).fetchall()]
     for duplicate in duplicate_subject_rows(persisted,shape,used):
      row=duplicate['row']
      if duplicate['protected']:
       geometry={key:value for key,value in duplicate['geometry'].items() if key!='subject_pipeline'};geometry['subject_role']=False
       c.execute('UPDATE observations SET geometry=?,updated=unixepoch() WHERE rowid=? AND geometry IS ?',(json.dumps(geometry,sort_keys=True,separators=(',',':')),row['oid'],row['geometry']))
      else:
       retired+=c.execute('DELETE FROM observations WHERE rowid=? AND geometry IS ?',(row['oid'],row['geometry'])).rowcount
      changed=True
    if changed:bump_obs_revision()
   except JobCancelled:raise
   except Exception as exc:failed.append({'path':str(p),'error':str(exc)})
   if progress:progress(index+1,len(payload['paths']))
 return {'analyzed':len(payload['paths']),'masks_created':created,'masks_inherited':inherited,'boxes_enriched':attached,'non_subject_drafts_retired':retired,'failed':failed,'review_required':True}

def independent_subject_job(payload,progress=None):
 from .subject_stages import extract,name_regions
 from .subjects import geometry_mask,same_instance,rle,PIPELINE,REVISION
 from .subject_learning import is_subject
 stage=payload['stage'];created=0;named=0;passes=0;untested=0;failed=[]
 with SUBJECT_JOB_LOCK:
  for index,raw in enumerate(payload['paths']):
   if progress:progress(index,len(payload['paths']),phase='Extracting foreground' if stage=='extract' else 'YOLAST naming')
   p=norm(raw)
   try:
    before=p.stat();signature=(before.st_mtime_ns,before.st_size)
    with db() as c:rows=[dict(r) for r in c.execute("SELECT rowid AS oid,* FROM observations WHERE path=? AND kind='mask' AND confidence>0",(str(p),))]
    rows=[r for r in rows if is_subject(r)]
    if stage=='extract':candidates,shape=extract(p,HF_CACHE)
    else:
     # Optional naming only fills unidentified subjects; confirmed/custom identities stay intact.
     rows=[r for r in rows if r['concept'].strip().casefold() in ('unknown','unidentified','unidentified subject')]
     updates,used,pending=name_regions(p,rows,ULTRA_MODELS/'bbox'/'yolov8s-worldv2.pt',payload.get('classes',[]),payload['max_passes'],lambda:progress(index,len(payload['paths'])) if progress else None)
     passes+=used;untested+=pending
    after=p.stat()
    if (after.st_mtime_ns,after.st_size)!=signature:raise ValueError('Source changed during inference; retry this image')
    if progress:progress(index,len(payload['paths']))
    changed=False
    with db() as c:
     if stage=='extract':
      # Re-read after inference; never retire or relabel existing annotations here.
      current=[dict(r) for r in c.execute("SELECT rowid AS oid,* FROM observations WHERE path=? AND kind='mask' AND confidence>0",(str(p),))]
      existing=[]
      for row in current:
       if not is_subject(row):continue
       try:
        g=json.loads(row['geometry']);mask=geometry_mask(g,shape)
        if mask is not None:existing.append({'bbox':g['bbox'],'mask':mask})
       except (ValueError,TypeError):continue
      for candidate in candidates:
       if any(same_instance(candidate,old) for old in existing):continue
       x,y,z,t=candidate['bbox']
       g={'bbox':[x,y,z,t],'mask_size':[z-x,t-y],'mask_rle':rle(candidate['mask'][y:t,x:z]),'source_size':[shape[1],shape[0]],'scope':'mask','method':'birefnet','subject_role':True,'subject_pipeline':PIPELINE,'birefnet_revision':REVISION,'review_status':'draft','review_required':True,'name_accepted':False,'extraction_only':True}
       inserted=c.execute("INSERT OR IGNORE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,'unidentified subject',1,'subject-intelligence',?,'mask',?,unixepoch())",(str(p),PIPELINE,json.dumps(g,sort_keys=True,separators=(',',':'))))
       created+=inserted.rowcount;changed=changed or bool(inserted.rowcount)
     else:
      for row,label,g in updates:
       updated=c.execute('UPDATE observations SET concept=?,geometry=?,updated=unixepoch() WHERE rowid=? AND concept=? AND geometry IS ? AND confidence>0',(label,json.dumps(g,sort_keys=True,separators=(',',':')),row['oid'],row['concept'],row['geometry']))
       if updated.rowcount!=1:raise ValueError('Subject changed during naming; refresh and retry')
       named+=int(label!='unidentified subject');changed=True
    if changed:bump_obs_revision()
   except JobCancelled:raise
   except Exception as exc:failed.append({'path':str(p),'error':str(exc)})
   if progress:progress(index+1,len(payload['paths']))
 return {'stage':stage,'images':len(payload['paths']),'masks_created':created,'subjects_named':named,'yolast_passes':passes,'regions_deferred_by_budget':untested,'failed':failed,'review_required':True}

@app.post('/api/subjects/name')
def subject_name(req:SubjectRequest):
 if not EDITION['subject_intelligence']:raise HTTPException(403,'Subject naming requires Full')
 if not req.paths or len(req.paths)>1000:raise HTTPException(400,'Choose between 1 and 1000 images')
 if len(req.classes)>200 or any(len(x)>100 for x in req.classes):raise HTTPException(400,'Subject vocabulary is too large')
 cfg=_load_config();cfg.setdefault('subject_naming',{})['max_passes']=req.max_passes;_save_config(cfg)
 return start_job('subject-yolast-naming',independent_subject_job,{'stage':'name','paths':list(dict.fromkeys(req.paths)),'classes':req.classes,'max_passes':req.max_passes})

@app.get('/api/subjects/naming/settings')
def subject_naming_settings():
 return {'max_passes':max(1,min(100,int(_load_config().get('subject_naming',{}).get('max_passes',8))))}


GUIDED_SUBJECT_REVIEWS={}

class GuidedSubjectRequest(SubjectObservationRef):
 hints:list[list[float]]
 max_passes:int=Field(default=17,ge=0,le=100)

def guided_subject_job(payload,progress=None):
 from .subject_guided import build
 import numpy as np
 ref=SubjectObservationRef(**payload['subject']);p=norm(ref.path)
 with SUBJECT_JOB_LOCK:
  with db() as c:row=subject_observation(c,ref)
  before=p.stat();signature=[before.st_mtime_ns,before.st_size]
  parent=json.loads(row['geometry'])
  def sam_crop(image,boxes):
   from ultralytics import SAM
   with SAM_INFERENCE_LOCK:
    model=MODEL_CACHE.get('sam-box')
    if model is None:
     weight=SAM_MODELS/'sam_b.pt'
     model=SAM(str(weight if weight.exists() else 'sam_b.pt'));MODEL_CACHE['sam-box']=model
    result=model(image,bboxes=boxes,verbose=False)[0]
   if result.masks is None:raise ValueError('SAM returned no masks')
   masks=[]
   for tensor in result.masks.data:
    mask=tensor.detach().cpu().numpy()>.5
    if mask.shape!=(image.height,image.width):mask=np.asarray(Image.fromarray(mask.astype('uint8')).resize(image.size,Image.Resampling.NEAREST))>0
    masks.append(mask)
   return masks
  result=build(p,parent,payload['hints'],HF_CACHE,sam_crop,ULTRA_MODELS/'bbox'/'yolov8s-worldv2.pt',payload['max_passes'],progress)
  after=p.stat()
  if [after.st_mtime_ns,after.st_size]!=signature:raise ValueError('Source changed during split; original retained')
  if progress:progress(len(payload['hints'])+2,len(payload['hints'])+2,phase='Split ready for review')
  token=uuid.uuid4().hex
  with LOCK:
   GUIDED_SUBJECT_REVIEWS[token]={'subject':payload['subject'],'signature':signature,'result':result,'created':time.time()}
   for key in list(GUIDED_SUBJECT_REVIEWS):
    if time.time()-GUIDED_SUBJECT_REVIEWS[key]['created']>86400:GUIDED_SUBJECT_REVIEWS.pop(key,None)
  return {'review_id':token,'subjects':len(result['candidates']),'naming_passes':result['naming_passes'],'path':str(p),'parent_bbox':parent['bbox']}

@app.post('/api/subjects/guided-split')
def queue_guided_subject(req:GuidedSubjectRequest):
 if not EDITION['subject_intelligence']:raise HTTPException(403,'Guided subjects require Full')
 if not 2<=len(req.hints)<=16:raise HTTPException(400,'Mark between 2 and 16 sub-subjects')
 with db() as c:row=subject_observation(c,req)
 from .subject_learning import is_subject
 if not is_subject(row):raise HTTPException(400,'Select a subject mask')
 g=json.loads(row['geometry']);x,y,z,t=g['bbox']
 for box in req.hints:
  if len(box)!=4 or not all(math.isfinite(v) for v in box):raise HTTPException(400,'Invalid hint box')
  a,b,d,e=box
  if not (x<=a<d<=z and y<=b<e<=t and d-a>=2 and e-b>=2):raise HTTPException(400,'Hints must be inside the selected subject crop')
 return start_job('subject-guided-split',guided_subject_job,{'subject':{k:v for k,v in req.model_dump().items() if k not in ('hints','max_passes')},'hints':req.hints,'max_passes':req.max_passes})

@app.get('/api/subjects/guided-split/{token}')
def guided_subject_review(token:str):
 with LOCK:review=GUIDED_SUBJECT_REVIEWS.get(token)
 if not review:raise HTTPException(404,'Split review expired; run again')
 return review['result']

class GuidedSubjectCommit(BaseModel):
 labels:list[str]

@app.post('/api/subjects/guided-split/{token}/accept')
def accept_guided_subject(token:str,req:GuidedSubjectCommit):
 with LOCK:review=GUIDED_SUBJECT_REVIEWS.get(token)
 if not review:raise HTTPException(404,'Split review expired; run again')
 results=review['result']['candidates']
 if len(req.labels)!=len(results) or any(not label.strip() or len(label)>200 for label in req.labels):raise HTTPException(400,'Name each result, or leave it as unidentified subject')
 ref=SubjectObservationRef(**review['subject']);p=norm(ref.path);st=p.stat()
 if [st.st_mtime_ns,st.st_size]!=review['signature']:raise HTTPException(409,'Source changed; run split again')
 with SUBJECT_JOB_LOCK:
  with db() as c:
   parent=subject_observation(c,ref);g=json.loads(parent['geometry']);g['subject_role']=False;g['guided_split_replaced']=True
   c.execute('UPDATE observations SET geometry=?,updated=unixepoch() WHERE rowid=?',(json.dumps(g,sort_keys=True,separators=(',',':')),parent['oid']))
   for candidate,label in zip(results,req.labels):
    label=label.strip();geometry={**candidate['geometry'],'review_status':'approved','review_required':False,'guided_split_parent':parent['oid']}
    if label!=candidate['concept']:
     from .subject_learning import mark_manual
     geometry=mark_manual(geometry,'label_changed',label,candidate['concept'])
     geometry['name_accepted']=label.casefold() not in ('unknown','unidentified','unidentified subject');geometry['name_confidence']=1.
    c.execute("INSERT INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,1,'subject-intelligence','subjects-guided','mask',?,unixepoch())",(str(p),label,json.dumps(geometry,sort_keys=True,separators=(',',':'))))
 with LOCK:GUIDED_SUBJECT_REVIEWS.pop(token,None)
 bump_obs_revision()
 return {'ok':True,'subjects':len(results),'training_started':False}


@app.post('/api/subjects/separate')
def subject_separate(req:SubjectRequest):
 if not EDITION['subject_intelligence']:raise HTTPException(403,'Subject separation requires Full')
 if not req.paths or len(req.paths)>1000:raise HTTPException(400,'Choose between 1 and 1000 images')
 if len(req.classes)>200 or any(len(x)>100 for x in req.classes):raise HTTPException(400,'Subject vocabulary is too large')
 return start_job('subject-separation',independent_subject_job,{'stage':'extract','paths':list(dict.fromkeys(req.paths))})

class SubjectQwenRequest(BaseModel):
 paths:list[str]
 environment_id:str|None=None
 model:str|None=None

def subject_qwen_paths(payload,progress=None):
 from .subject_queries import ComfyQuery,montage,workflow,parse_reply
 env=_find_comfy_env(payload.get('environment_id'));cfg=_load_config();translator=cfg.get('prompt_translator',{}) or {}
 model=payload.get('model') or translator.get('model')
 if not model:raise RuntimeError('Choose an image-capable Qwen model in Prompt Translator settings first')
 client=ComfyQuery(env['api_url']);client.validate(model)
 targets=[];class_hints=[]
 with db() as c:
  if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='subject_classes'").fetchone():class_hints=[row[0] for row in c.execute('SELECT label FROM subject_classes ORDER BY created DESC LIMIT 64')]
  for raw in payload['paths']:
   for row in c.execute("SELECT rowid AS oid,path,concept,confidence,provider,model,kind,geometry FROM observations WHERE path=? AND kind='mask' AND confidence>0",(str(norm(raw)),)).fetchall():
    if payload.get('unidentified_only') and row['concept'].casefold()!='unidentified subject':continue
    try:geometry=json.loads(row['geometry'])
    except (TypeError,ValueError):continue
    if geometry.get('subject_role') is False:continue
    if geometry.get('subject_role') or geometry.get('subject_pipeline') or row['provider']=='subject-intelligence':targets.append((dict(row),geometry))
 if not targets:raise RuntimeError('No subject masks selected. Separate subjects first.')
 if len(targets)>200:raise RuntimeError('Choose a smaller batch: at most 200 subject queries per job')
 replies=[];failed=[]
 for index,(row,geometry) in enumerate(targets):
  if progress:progress(index,len(targets),phase='Preparing subject query')
  prompt_id=None
  try:
   source=norm(row['path']);before=source.stat();signature=(before.st_size,before.st_mtime_ns)
   image=client.upload(montage(source,geometry));graph=workflow(model,image,str(translator.get('type') or 'stable_diffusion'),str(translator.get('device') or 'default'),class_hints=class_hints)
   prompt_id=client.submit(graph)
   text=client.wait(prompt_id,progress=(lambda:progress(index,len(targets),phase='Waiting for Comfy subject query')) if progress else None)
   interpretation=parse_reply(text)
   if progress:progress(index,len(targets),phase='Saving subject review')
   after=source.stat()
   if (after.st_size,after.st_mtime_ns)!=signature:raise RuntimeError('Source changed during query; result was not attached')
   review={**interpretation,'raw_text':text[:16000],'environment_id':env['id'],'model':model,'prompt_id':prompt_id,'updated':time.time(),'status':'draft'}
   updated_geometry={**geometry,'qwen_review':review}
   with db() as c:
    updated=c.execute('UPDATE observations SET geometry=?,updated=unixepoch() WHERE rowid=? AND path=? AND geometry IS ?',(json.dumps(updated_geometry,sort_keys=True,separators=(',',':')),row['oid'],row['path'],row['geometry']))
    if updated.rowcount!=1:raise RuntimeError('Subject changed during query; result was not attached')
   bump_obs_revision();replies.append({'path':row['path'],'subject':row['concept'],'review':review})
  except JobCancelled:
   if prompt_id:
    # Remove only our own pending prompt. Never interrupt unrelated Comfy work.
    try:client.post('/queue',{'delete':[prompt_id]})
    except Exception:pass
   raise
  except Exception as exc:failed.append({'path':row['path'],'subject':row['concept'],'prompt_id':prompt_id,'error':str(exc)})
  if progress:progress(index+1,len(targets),phase='Subject query complete')
 return {'subjects_reviewed':len(replies),'reviews':replies,'failed':failed,'review_required':True}

@app.post('/api/subjects/interpret')
def subject_qwen_queue(req:SubjectQwenRequest):
 if not EDITION['subject_intelligence']:raise HTTPException(403,'Subject interpretation requires Full')
 if not req.paths or len(req.paths)>100:raise HTTPException(400,'Choose between 1 and 100 images')
 return start_job('subject-qwen-review',subject_qwen_paths,{'paths':list(dict.fromkeys(req.paths)),'environment_id':req.environment_id,'model':req.model})

def reconstruction_root():
 return Path((_load_config().get('subject_reconstruction',{}) or {}).get('root') or ROOT/'cache/subjectifier')

def subject_class_root():return Path(DB_PATH).parent/'subject-classes'

@app.get('/api/subjects/classes/status')
def subject_class_status():
 from .subject_class_training import status
 with db() as c:result=status(c,subject_class_root())
 with SUBJECT_CLASS_QUEUE_LOCK:
  with LOCK:busy=next((dict(job) for job in JOBS.values() if job.get('kind')=='subject-class-training' and job.get('state') in ('queued','running')),None)
  queue_pending=SUBJECT_CLASS_PENDING.is_set()
 return {**result,**subject_class_settings(),'training':{'state':busy['state'] if busy else ('queued' if queue_pending else 'idle'),'job_id':busy and busy['id'],'queued_update':queue_pending}}

@app.get('/api/subjects/classes/settings')
def subject_class_settings():return {'auto_train':bool((_load_config().get('subject_class_training') or {}).get('auto_train',True))}

class SubjectClassSettings(BaseModel):
 auto_train:bool

@app.put('/api/subjects/classes/settings')
def set_subject_class_settings(req:SubjectClassSettings):
 cfg=_load_config();cfg.setdefault('subject_class_training',{})['auto_train']=req.auto_train;_save_config(cfg);return subject_class_settings()

def subject_class_train_job(payload,progress=None):
 from .subject_class_training import train
 return train(db,subject_class_root(),reconstruction_root(),progress)

SUBJECT_CLASS_QUEUE_LOCK=threading.RLock()
SUBJECT_CLASS_AUTOTRAIN_LOCK=threading.Lock()
SUBJECT_CLASS_PENDING=threading.Event()
SUBJECT_CLASS_FORCED=threading.Event()

@app.post('/api/subjects/classes/train')
def queue_subject_class_training():
 with SUBJECT_CLASS_QUEUE_LOCK:
  with LOCK:
   existing=next((dict(job) for job in JOBS.values() if job.get('kind')=='subject-class-training' and job.get('state') in ('queued','running')),None)
  if existing:
   schedule_subject_class_training(force=True)
   return {**existing,'reused':True,'queued_update':True}
  job=start_job('subject-class-training',subject_class_train_job,{})
  return {**job,'reused':False,'queued_update':False}

def schedule_subject_class_training(force=False):
 # One waiting pass absorbs repeated clicks and manual teaching commits.
 with SUBJECT_CLASS_QUEUE_LOCK:
  SUBJECT_CLASS_PENDING.set()
  if force:SUBJECT_CLASS_FORCED.set()
  if not SUBJECT_CLASS_AUTOTRAIN_LOCK.acquire(blocking=False):return
 def schedule():
  try:
   time.sleep(1)
   while True:
    with LOCK:busy=any(job.get('kind')=='subject-class-training' and job.get('state') in ('queued','running') for job in JOBS.values())
    if not busy:break
    if STOP_REQUESTED:return
    time.sleep(.25)
   with SUBJECT_CLASS_QUEUE_LOCK:
    forced=SUBJECT_CLASS_FORCED.is_set();SUBJECT_CLASS_PENDING.clear();SUBJECT_CLASS_FORCED.clear()
    if STOP_REQUESTED or (not forced and not subject_class_settings()['auto_train']):return
    if not forced:
     result=subject_class_status()
     if not result['ready']:return
     from .subject_class_training import dataset,manifest_hash
     with db() as c:rows,_=dataset(c,subject_class_root())
     fingerprint=manifest_hash(rows)
     if result['runs'] and result['runs'][0]['manifest_hash']==fingerprint:return
    queue_subject_class_training()
  except Exception as exc:LOG.warning('Composite class training not queued: %s',exc)
  finally:
   with SUBJECT_CLASS_QUEUE_LOCK:
    SUBJECT_CLASS_AUTOTRAIN_LOCK.release()
    if STOP_REQUESTED:SUBJECT_CLASS_PENDING.clear();SUBJECT_CLASS_FORCED.clear()
    elif SUBJECT_CLASS_PENDING.is_set():schedule_subject_class_training(force=SUBJECT_CLASS_FORCED.is_set())
 threading.Thread(target=schedule,daemon=True,name='subject-class-teaching').start()

@app.post('/api/subjects/classes/rollback')
def rollback_subject_classes():
 from .subject_class_training import rollback
 try:return rollback(subject_class_root())
 except ValueError as exc:raise HTTPException(409,str(exc))

class ConfirmSubjectClassRequest(SubjectObservationRef):
 source:str='language_model'

@app.post('/api/subjects/classes/confirm')
def confirm_subject_class(req:ConfirmSubjectClassRequest):
 from .subject_learning import geometry,is_subject,mark_manual
 if req.source not in ('language_model','trained'):raise HTTPException(400,'Choose a language-model or learned-class proposal')
 with db() as c:
  row=subject_observation(c,req);g=geometry(row['geometry'])
  if row['kind']!='mask' or not is_subject(row):raise HTTPException(400,'Choose a masked Subject')
  proposal=g.get('qwen_review' if req.source=='language_model' else 'trained_class_review') or {}
  label=proposal.get('label','').strip()
  if not label or label.casefold() in ('unknown','unidentified','unidentified subject') or (req.source=='trained' and not proposal.get('accepted')):raise HTTPException(400,'No supported class proposal to confirm')
  changed=mark_manual(g,'label_confirmed',label,row['concept']);changed['confirmed_class_source']={'source':req.source,'model':proposal.get('model') or proposal.get('revision')}
  c.execute('UPDATE observations SET confidence=-ABS(confidence),updated=unixepoch() WHERE rowid=?',(row['oid'],))
  c.execute("INSERT OR REPLACE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,1,'human-correction',?,'mask',?,unixepoch())",(row['path'],label,'subject-class-confirm:'+row['provider']+':'+row['model'],json.dumps(changed,sort_keys=True,separators=(',',':'))))
 bump_obs_revision();return {'ok':True,'label':label,'geometry':changed,'learn_required':True}

class RecognizeSubjectClassesRequest(BaseModel):
 paths:list[str]
 apply_unidentified:bool=True

def recognize_subject_classes(payload,progress=None):
 import tempfile
 from .subject_class_training import active,run_worker,sha
 from .composite_images import isolate
 from .subject_learning import geometry,is_subject
 trained=active(subject_class_root())
 if not trained:raise ValueError('No validated subject classes yet; confirm lessons and train first')
 targets=[]
 with db() as c:
  for raw in payload['paths']:
   for row in c.execute("SELECT rowid AS oid,* FROM observations WHERE path=? AND kind='mask' AND confidence>0",(str(norm(raw)),)):
    row=dict(row)
    if is_subject(row):targets.append(row)
 if not targets or len(targets)>200:raise ValueError('Choose between 1 and 200 masked subjects')
 with tempfile.TemporaryDirectory(prefix='recognize-',dir=subject_class_root()) as raw:
  folder=Path(raw);images=[];signatures=[]
  for index,row in enumerate(targets):
   path=Path(row['path']);before=path.stat();data=isolate(path,geometry(row['geometry']));after=path.stat()
   if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Source changed while preparing recognition')
   signatures.append((after.st_size,after.st_mtime_ns));image=folder/(str(index)+'.png');image.write_bytes(data);images.append({'image':str(image),'crop_sha256':sha(image)})
  result=run_worker(subject_class_root(),reconstruction_root(),{'mode':'predict','images':images,'checkpoint':trained['checkpoint']},progress)
 predictions=result.get('predictions',[])
 if len(predictions)!=len(targets):raise ValueError('Recognition returned an incomplete result set; no reviews applied')
 reviewed=0;applied=0;accepted=0;reasons={}
 with db() as c:
  if active(subject_class_root())['revision']!=trained['revision']:raise ValueError('Active class model changed; run recognition again')
  for row,signature,prediction in zip(targets,signatures,predictions):
   st=Path(row['path']).stat()
   if (st.st_size,st.st_mtime_ns)!=signature:raise ValueError('Source changed; learned review was not applied')
   g=geometry(row['geometry']);g['trained_class_review']={**prediction,'revision':trained['revision']}
   label=row['concept'];accepted+=int(prediction['accepted'])
   if prediction['accepted'] and payload.get('apply_unidentified',True) and label.strip().casefold() in ('unknown','unidentified','unidentified subject'):
    label=prediction['label'];g.update(name_accepted=True,name_confidence=prediction['score'],naming_method='learned-classifier');applied+=1
   if not prediction['accepted']:
    for reason in prediction.get('rejection_reasons',[]):reasons[reason]=reasons.get(reason,0)+1
   update=c.execute('UPDATE observations SET concept=?,geometry=?,updated=unixepoch() WHERE rowid=? AND concept=? AND geometry IS ?',(label,json.dumps(g,sort_keys=True,separators=(',',':')),row['oid'],row['concept'],row['geometry']))
   if update.rowcount!=1:raise ValueError('Subject changed; learned review was not applied')
   reviewed+=1
 if reviewed:bump_obs_revision()
 summary=f'Learned recognition: {reviewed} subjects, {accepted} accepted, {applied} unidentified subjects labeled, {reviewed-accepted} abstained'
 LOG.info('%s; active classes: %s',summary,', '.join(trained['classes']))
 for reason,count in reasons.items():LOG.info('Recognition abstentions: %s — %s',count,reason)
 return {'reviewed':reviewed,'accepted':accepted,'applied':applied,'abstained':reviewed-accepted,'summary':summary,'paths':list(dict.fromkeys(payload['paths'])),'revision':trained['revision'],'predictions':predictions,'review_required':True}

@app.post('/api/subjects/classes/recognize')
def queue_recognize_subject_classes(req:RecognizeSubjectClassesRequest):
 if not req.paths or len(req.paths)>100:raise HTTPException(400,'Select between 1 and 100 images')
 return start_job('subject-class-recognition',recognize_subject_classes,{'paths':list(dict.fromkeys(req.paths)),'apply_unidentified':req.apply_unidentified})

@app.get('/api/subjects/reconstruction/status')
def reconstruction_status():
 if not EDITION['subject_intelligence']:raise HTTPException(403,'Subject reconstruction requires Full')
 from .subject_reconstruction import backend_status
 return {'backends':backend_status(reconstruction_root())}

class SubjectReconstructionSettings(BaseModel):
 auto_language_model:bool=False

@app.get('/api/subjects/reconstruction/settings')
def reconstruction_settings():
 return {'auto_language_model':bool((_load_config().get('subject_reconstruction',{}) or {}).get('auto_language_model',False))}

@app.put('/api/subjects/reconstruction/settings')
def save_reconstruction_settings(req:SubjectReconstructionSettings):
 cfg=_load_config();cfg.setdefault('subject_reconstruction',{})['auto_language_model']=req.auto_language_model;_save_config(cfg)
 return reconstruction_settings()

class SubjectReconstructionRequest(BaseModel):
 paths:list[str]
 engine:str='partglee'

def reconstruct_subject_paths(payload,progress=None):
 from .subject_reconstruction import infer,persist
 paths=[str(norm(path)) for path in payload['paths']];snapshots={}
 with db() as c:
  for path in paths:snapshots[path]=[dict(row) for row in c.execute('SELECT rowid AS oid,* FROM observations WHERE path=?',(path,))]
 from .subjects import INFERENCE_LOCK
 while not INFERENCE_LOCK.acquire(timeout=.25):
  if progress:progress(0,len(paths),phase='Waiting for subject model')
 try:
  if payload['engine']=='langhops':
   try:
    from .subject_reconstruction import release_idle_comfy
    release_idle_comfy(_find_comfy_env(None)['api_url'])
   except Exception:pass
  result=infer(reconstruction_root(),payload['engine'],paths,progress)
 finally:INFERENCE_LOCK.release()
 completed=[]
 for index,image in enumerate(result['images']):
  path=image['path']
  if progress:progress(index,len(paths),phase='Saving reconstructed subject drafts')
  signature=norm(path).stat()
  if [signature.st_size,signature.st_mtime_ns]!=image['source_signature']:raise RuntimeError('Source changed during reconstruction')
  with db() as c:
   current=[dict(row) for row in c.execute('SELECT rowid AS oid,* FROM observations WHERE path=?',(path,))]
   if current!=snapshots[path]:raise RuntimeError('Annotations changed during reconstruction; refresh and rerun')
   # Retire only this backend's old ordinary automatic part drafts. Manual
   # corrections and their frozen training snapshots remain intact.
   provider='subjectifier-'+payload['engine']+'-parts'
   for row in current:
    if row['provider']==provider and row['confidence']>0:
     g=json.loads(row['geometry'] or '{}')
     if g.get('review_status')!='approved':c.execute('DELETE FROM observations WHERE rowid=?',(row['oid'],))
   saved=persist(c,image,current)
  bump_obs_revision();completed.append({'path':path,**saved})
  if progress:progress(index+1,len(paths),phase='Subject drafts saved')
 result={'images':completed,'backend':payload['engine'],'review_required':True,'weights_updated':False}
 if reconstruction_settings()['auto_language_model']:
  with db() as c:
   unidentified=[path for path in paths if c.execute("SELECT 1 FROM observations WHERE path=? AND concept='unidentified subject' AND kind='mask' AND confidence>0",(path,)).fetchone()]
  if unidentified:
   try:result['language_review']=subject_qwen_paths({'paths':unidentified,'unidentified_only':True},progress)
   except JobCancelled:raise
   except Exception as exc:result['language_review_error']=str(exc)
 return result

@app.post('/api/subjects/reconstruct')
def queue_subject_reconstruction(req:SubjectReconstructionRequest):
 if not EDITION['subject_intelligence']:raise HTTPException(403,'Subject reconstruction requires Full')
 if req.engine not in ('partglee','langhops'):raise HTTPException(400,'Unknown reconstruction backend')
 if not req.paths or len(req.paths)>25:raise HTTPException(400,'Choose between 1 and 25 images')
 return start_job('subject-reconstruction',reconstruct_subject_paths,{'paths':list(dict.fromkeys(req.paths)),'engine':req.engine})

class JobCancelled(Exception): pass

def job_progress(jid,done,total,**meta):
 if STOP_REQUESTED: raise JobCancelled('Clean shutdown requested')
 now=time.time()
 with LOCK:
  job=JOBS.get(jid,{})
  if job.get('cancel_requested'): raise JobCancelled('Stopped by user')
  # Throughput starts AFTER the first completed return. The first item is warm-up,
  # not evidence of steady-state classifier speed.
  prev_done=int(job.get('_rate_done',0) or 0); prev_t=job.get('_rate_time')
  if prev_t is None and done>0:
   job['_rate_done']=done;job['_rate_time']=now;job['rate_started']=now
  elif prev_t is not None and done>prev_done:
   dt=max(.001,now-float(prev_t));inst=(done-prev_done)/dt
   old=job.get('items_per_second');job['items_per_second']=inst if old is None else (.30*inst+.70*float(old))
   job['_rate_done']=done;job['_rate_time']=now
   rate=float(job['items_per_second']);job['eta_seconds']=max(0,(total-done)/rate) if rate>0 else None
  job.update(done=done,total=total,updated=now)
  if meta: job.update(meta)
def start_job(kind,fn,*args):
 if not EDITION['inference']:raise HTTPException(403,'Lite does not start inference/processing jobs')
 if STOP_REQUESTED: raise HTTPException(503,'N8Vision is shutting down')
 # Sanity is one logical producer job. Repeated UI/directory requests while it owns the
 # floor return the existing job instead of creating overlapping or queued copies.
 if kind=='sanity-v4':
  with LOCK:
   for existing in JOBS.values():
    if existing.get('kind')=='sanity-v4' and existing.get('state') in {'queued','running'}:
     existing['singleton_reused']=True
     return existing
 payload=args[0] if args else None
 if isinstance(payload,dict) and isinstance(payload.get('paths'),list): total=len(payload['paths'])
 elif isinstance(payload,(list,tuple,set)): total=len(payload)
 else: total=0
 jid=uuid.uuid4().hex[:12];JOBS[jid]={'id':jid,'kind':kind,'state':'queued','done':0,'total':total,'created':time.time()}
 if kind.startswith('comfy:') and isinstance(payload,dict): payload['_n8_batch_id']=jid
 _write_active_job_journal()
 def run():
  try:
   JOBS[jid]['state']='running'; _write_active_job_journal()
   if kind=='subject-class-training':LOG.info('Job %s started: %s (collecting confirmed teaching set)',jid,kind)
   else:LOG.info('Job %s started: %s (%s items)',jid,kind,JOBS[jid]['total'])
   res=fn(*args,progress=lambda d,t,**meta:job_progress(jid,d,t,**meta))
   if kind.startswith('comfy:'):
    with OUTPUT_RECOVERY_LOCK:b=COMFY_RECOVERY_BATCHES.get(jid)
    if b and not b.get('complete'):
     JOBS[jid].update(state='recovering',phase='recovering',result=res,done=int(b.get('terminal',0)),total=int(b.get('total',JOBS[jid]['total'])),updated=time.time())
    elif b:
     JOBS[jid].update(state='done',phase='complete',result={**(res or {}),'recovery':dict(b)},done=int(b.get('terminal',0)),total=int(b.get('total',JOBS[jid]['total'])),updated=time.time())
    else:JOBS[jid].update(state='done',phase='dispatched',result=res,done=JOBS[jid]['total'],updated=time.time())
    LOG.info('Job %s dispatched: %s',jid,kind)
   else:
    JOBS[jid].update(state='done',result=res,done=JOBS[jid]['total'],updated=time.time())
    if kind=='subject-class-training':
     from .subject_training_report import describe_training
     diagnostics=res.get('diagnostics') or describe_training(res)
     outcome='Waiting for more teaching examples' if res.get('deferred') else 'Class model activated' if res.get('activated') else 'Candidate rejected by validation'
     JOBS[jid]['phase']=outcome
     for line in diagnostics:LOG.info('Job %s: %s',jid,line)
    else:LOG.info('Job %s complete: %s',jid,kind)
   _write_active_job_journal()
  except JobCancelled as e:
   JOBS[jid].update(state='stopped',error=str(e),updated=time.time()); _write_active_job_journal(); LOG.info('Job %s stopped: %s',jid,kind)
  except Exception as e:
   JOBS[jid].update(state='error',error=str(e)); _write_active_job_journal(); LOG.exception('Job %s failed: %s — %s',jid,kind,e)
 threading.Thread(target=run,daemon=True).start();return JOBS[jid]

class RasterSanityRequest(Paths):
 thumbnail:int=256
 edge_threshold:int=24
 light_blur:float=1.0
 medium_blur:float=2.5
 heavy_blur:float=4.0
 grade_b_largest_fraction:float=0.10
 force:bool=False
 manual:bool=False

SANITY_VERSION='sanity-v4'
# Classification policy is deliberately NOT part of the expensive measurement identity.
# Changing this value re-maths archived measurements; it does not justify reopening pixels.
GRADE_B_LARGEST_FRACTION=0.10
SANITY_RECIPE_ID='v4-classifier-r2-coherence'


def _edge_metrics(gray,threshold,grid=8):
 """Thresholded edge census, contour organization, and spatial occupancy."""
 from PIL import ImageFilter
 edge=gray.filter(ImageFilter.FIND_EDGES);w,h=edge.size
 if w>4 and h>4:edge=edge.crop((2,2,w-2,h-2));w,h=edge.size
 data=edge.tobytes();mask=bytearray(1 if v>=threshold else 0 for v in data)
 total=max(1,w*h);edge_count=sum(mask)
 occupied=0;cell_densities=[]
 for gy in range(grid):
  y0=gy*h//grid;y1=(gy+1)*h//grid
  for gx in range(grid):
   x0=gx*w//grid;x1=(gx+1)*w//grid;area=max(1,(x1-x0)*(y1-y0));n=0
   for yy in range(y0,y1):n+=sum(mask[yy*w+x0:yy*w+x1])
   d=n/area;cell_densities.append(d)
   if n>=max(1,int(area*.005)):occupied+=1
 occupancy=occupied/(grid*grid)
 if not edge_count:return {'density':0.0,'components':0,'largest_component':0,'largest_fraction':0.0,'mean_component':0.0,'occupancy':0.0,'cell_densities':cell_densities}
 seen=bytearray(total);sizes=[]
 for seed,on in enumerate(mask):
  if not on or seen[seed]:continue
  seen[seed]=1;stack=[seed];size=0
  while stack:
   q=stack.pop();size+=1;y,x=divmod(q,w)
   for yy in range(max(0,y-1),min(h,y+2)):
    base=yy*w
    for xx in range(max(0,x-1),min(w,x+2)):
     n=base+xx
     if n!=q and mask[n] and not seen[n]:seen[n]=1;stack.append(n)
  sizes.append(size)
 largest=max(sizes)
 return {'density':edge_count/total,'components':len(sizes),'largest_component':largest,'largest_fraction':largest/edge_count,
         'mean_component':edge_count/len(sizes),'occupancy':occupancy,'cell_densities':cell_densities}


def _sanity_classify(levels,grade_b_largest_fraction=GRADE_B_LARGEST_FRACTION):
 """Classification recipe only. It may change without invalidating compatible measurements."""
 raw,light,medium,heavy=levels
 if raw['density']<.005 and light['density']<.002:return 'Blank'
 if raw['density']>=.20 and raw['occupancy']>=.70 and medium['density']<.005:
  # Dense fine detail is not automatically noise. Real structure (fur, foliage,
  # engraving, eldritch eyelashes, etc.) survives the light blur coherently,
  # while unstructured pixel/static noise collapses quickly.
  fine_coherence=light['density']/max(raw['density'],1e-9)
  if fine_coherence>=.35:return None
  if light['largest_fraction']>=grade_b_largest_fraction:return 'Grade B Meat'
  return 'Noise'
 if raw['density']>=.003 and light['occupancy']<=.35 and raw['occupancy']<=.55:return 'Blob'
 return None


def _sanity_measurement_model(thumbnail,edge_threshold,radii):
 # Stable identity for pixel-derived facts. Verdict thresholds intentionally excluded.
 return f'{SANITY_VERSION};measure;thumb={thumbnail};threshold={edge_threshold};blur={radii[1]:g},{radii[2]:g},{radii[3]:g};grid=8'


def _sanity_measurements_compatible(geom,thumbnail,edge_threshold,radii):
 """Accept current or legacy Sanity receipts when their archived primitive measurements match requested sensor settings."""
 try:
  if not isinstance(geom,dict) or not isinstance(geom.get('levels'),list) or len(geom['levels'])!=4:return False
  if int(geom.get('thumbnail_limit',-1))!=int(thumbnail):return False
  if int(geom.get('edge_threshold',-1))!=int(edge_threshold):return False
  old=[float(x) for x in geom.get('blur_radii',[])]
  if len(old)!=4 or any(abs(a-b)>1e-9 for a,b in zip(old,radii)):return False
  # Ensure the fields consumed by current classification/verbose diagnostics actually exist.
  for level in geom['levels']:
   if not isinstance(level,dict) or not all(k in level for k in ('density','components','largest_fraction','occupancy')):return False
  return True
 except Exception:return False


def _physical_cpu_cores():
 """Best-effort physical core count without adding a runtime dependency."""
 try:
  if os.name=='nt':
   import subprocess
   cmd=['powershell','-NoProfile','-Command','(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum']
   out=subprocess.check_output(cmd,stderr=subprocess.DEVNULL,text=True,timeout=3).strip()
   if out and int(out)>0:return int(out)
  elif Path('/proc/cpuinfo').exists():
   pairs=set();phys=core=None
   for line in Path('/proc/cpuinfo').read_text(errors='ignore').splitlines()+['']:
    if line.startswith('physical id'):phys=line.split(':',1)[1].strip()
    elif line.startswith('core id'):core=line.split(':',1)[1].strip()
    elif not line.strip():
     if phys is not None and core is not None:pairs.add((phys,core))
     phys=core=None
   if pairs:return len(pairs)
 except Exception:pass
 # Most desktop CPUs expose two SMT threads per physical core; this fallback is
 # deliberately conservative because Sanity's normal policy only gets half the silicon.
 logical=os.cpu_count() or 1
 return max(1,logical//2) if logical>2 else logical

def _sanity_worker_ceiling():
 cfg=_load_config().get('sanity',{})
 physical=max(1,_physical_cpu_cores())
 uncapped=bool(cfg.get('uncapped_unsanity',False))
 return (physical if uncapped else max(1,physical//2)),physical,uncapped

def raster_sanity_paths(paths,thumbnail=256,edge_threshold=24,light_blur=1.0,medium_blur=2.5,heavy_blur=4.0,grade_b_largest_fraction=GRADE_B_LARGEST_FRACTION,force=False,progress=None):
 """Sanity v4: reuse compatible archived measurements, re-math verdicts, and open pixels only for missing/stale sensor facts."""
 from PIL import ImageFilter
 thumbnail=max(64,min(512,int(thumbnail)));edge_threshold=max(1,min(254,int(edge_threshold)))
 radii=[0.0,max(0.0,min(12.0,float(light_blur))),max(0.0,min(12.0,float(medium_blur))),max(0.0,min(12.0,float(heavy_blur)))];grade_b_largest_fraction=max(0.0,min(1.0,float(grade_b_largest_fraction)))
 measurement_model=_sanity_measurement_model(thumbnail,edge_threshold,radii)
 verdict_model=f'{measurement_model};recipe={SANITY_RECIPE_ID};gradeb={grade_b_largest_fraction:.6g}'
 candidates=[str(norm(x)) for x in paths]
 # One archive read builds the whole plan. Prefer newest compatible receipt per path, including legacy v2/v3/v4 leftovers.
 archived={}
 if not force and candidates:
  wanted=set(candidates)
  with db() as c:
   step=800
   for st in range(0,len(candidates),step):
    chunk=candidates[st:st+step];marks=','.join('?'*len(chunk))
    rows=c.execute(f"SELECT path,model,geometry,updated FROM observations WHERE path IN ({marks}) AND provider IN ('native-raster-sanity','native-raster-sanity-v2') AND kind='receipt' ORDER BY updated DESC",chunk).fetchall()
    for r in rows:
     if r['path'] in archived:continue
     try:g=json.loads(r['geometry'] or '{}')
     except Exception:continue
     if _sanity_measurements_compatible(g,thumbnail,edge_threshold,radii):archived[r['path']]=g
 queue=[];reused=[];current=[]
 for x in candidates:
  g=archived.get(x) if not force else None
  if g is None:queue.append(x);continue
  if g.get('measurement_model')==measurement_model and g.get('recipe_id')==SANITY_RECIPE_ID and abs(float(g.get('grade_b_largest_fraction',-1))-grade_b_largest_fraction)<1e-12:current.append(x)
  else:reused.append((x,g))
 LOG.info('Raster sanity v4 plan: %s already current, %s archive-only re-maths, %s rasters need measurement',len(current),len(reused),len(queue))
 done=failed=passed=0;reasons={};remeasured=0;remathed=0
 stats_lock=threading.Lock()

 def persist(path,geom):
  nonlocal done,failed,passed,remathed
  verdict=_sanity_classify(geom['levels'],grade_b_largest_fraction)
  geom=dict(geom);geom.update({'version':4,'verdict':verdict or 'Pass','grade_b_largest_fraction':grade_b_largest_fraction,'grade_b_level':'light','measurement_model':measurement_model,'recipe_id':SANITY_RECIPE_ID})
  payload=json.dumps(geom,separators=(',',':'),sort_keys=True)
  # Clean all previous Sanity leftovers for this path, then write one canonical measurement receipt + current derived class.
  with db() as c:
   c.execute("DELETE FROM observations WHERE path=? AND provider IN ('native-raster-sanity-v2','native-raster-sanity')",(str(path),))
   c.execute('INSERT OR REPLACE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,?,?,?,?,?,unixepoch())',
    (str(path),'Sanity inspected',1.0,'native-raster-sanity',measurement_model,'receipt',payload))
   if verdict:
    c.execute('INSERT OR REPLACE INTO observations(path,concept,confidence,provider,model,kind,geometry,updated) VALUES(?,?,?,?,?,?,?,unixepoch())',
     (str(path),f'Sanity: {verdict}',1.0,'native-raster-sanity',verdict_model,'class',payload))
  with stats_lock:
   if verdict:failed+=1;reasons[verdict]=reasons.get(verdict,0)+1
   else:passed+=1
   done+=1

 # Reclassification is archive arithmetic only: no Pillow, no raster I/O.
 for i,(raw_path,g) in enumerate(reused):
  try:persist(raw_path,g);remathed+=1
  except Exception as e:LOG.warning('Raster sanity v4 could not re-math archived measurements for %s: %s',raw_path,e)
  if progress:progress(i+1,len(reused)+len(queue))

 def measure_one(raw_path):
  p=norm(raw_path)
  if not image_file(p):return False
  try:
   with Image.open(p) as im:
    im=ImageOps.exif_transpose(im).convert('L');im.thumbnail((thumbnail,thumbnail),Image.Resampling.BILINEAR)
    levels=[]
    for radius in radii:
     sample=im if radius==0 else im.filter(ImageFilter.GaussianBlur(radius=radius))
     levels.append(_edge_metrics(sample,edge_threshold))
    geom={'thumbnail_size':list(im.size),'thumbnail_limit':thumbnail,'edge_threshold':edge_threshold,'blur_radii':radii,'levels':levels}
   persist(str(p),geom);return True
  except Exception as e:LOG.warning('Raster sanity v4 could not inspect %s: %s',p,e);return False

 # Adaptive Sanity: one logical job, multiple image workers. Normal mode may use at
 # most half the physical cores; Uncapped UnSanity may explore all physical cores.
 # Each step is accepted only when its aggregate completed+archived p/s improves by 10%.
 from concurrent.futures import ThreadPoolExecutor,as_completed
 ceiling,physical,uncapped=_sanity_worker_ceiling();workers=1;best_rate=0.0;cursor=0;measured_done=0
 LOG.info('Sanity worker policy: physical=%s ceiling=%s uncapped=%s',physical,ceiling,uncapped)
 while cursor<len(queue):
  # Probe each worker count on a useful but bounded wave, then stay at the last useful level.
  probing=workers<ceiling
  wave_n=min(len(queue)-cursor,max(16,workers*16) if probing else len(queue)-cursor)
  wave=queue[cursor:cursor+wave_n];cursor+=wave_n;t0=time.perf_counter();wave_ok=0
  with ThreadPoolExecutor(max_workers=_grid_worker_cap(workers),thread_name_prefix='sanity') as pool:
   futures=[pool.submit(measure_one,x) for x in wave]
   for fut in as_completed(futures):
    if fut.result():wave_ok+=1
    measured_done+=1
    if progress:progress(len(reused)+measured_done,len(reused)+len(queue))
  elapsed=max(.001,time.perf_counter()-t0);rate=wave_ok/elapsed
  LOG.info('Sanity adaptive wave: workers=%s completed=%s elapsed=%.2fs rate=%.2f p/s',workers,wave_ok,elapsed,rate)
  if not probing:continue
  if best_rate<=0 or rate>=best_rate*1.10:
   best_rate=max(best_rate,rate);workers+=1
  else:
   workers=max(1,workers-1);ceiling=workers
  remeasured+=wave_ok
 # The final non-probe wave increments here; probe waves were also accumulated above.
 # Recompute from successful raster persists to avoid per-thread counter races.
 remeasured=max(remeasured,done-remathed)
 if done:bump_obs_revision()
 return {'processed':done,'already_current':len(current),'remeasured':remeasured,'remathed_from_archive':remathed,'passed':passed,'failed':failed,'queued_for_measurement':len(queue),'reasons':reasons,'tool':SANITY_VERSION,'measurement_model':measurement_model,'verdict_model':verdict_model}

def _purge_sanity_for_paths(paths):
 """Manual reassessment semantics: shown/selected files lose all Sanity-owned leftovers before the fresh scan."""
 candidates=[str(norm(x)) for x in paths]
 if not candidates:return 0
 deleted=0
 with db() as c:
  for st in range(0,len(candidates),800):
   chunk=candidates[st:st+800];marks=','.join('?'*len(chunk))
   cur=c.execute(f"DELETE FROM observations WHERE path IN ({marks}) AND provider IN ('native-raster-sanity-v2','native-raster-sanity')",chunk)
   deleted+=max(0,cur.rowcount or 0)
 if deleted:bump_obs_revision()
 LOG.info('Manual Sanity purge: removed %s prior observation(s) for %s requested image(s)',deleted,len(candidates))
 return deleted

@app.post('/api/native/raster-sanity-v4')
@app.post('/api/native/raster-sanity-v3')
def raster_sanity_v4(req:RasterSanityRequest):
 # Manual buttons mean "challenge these verdicts": purge the captured shown/selected
 # set first and force fresh raster measurement. Automatic callers remain archive-first.
 force=bool(req.force or req.manual)
 if req.manual:_purge_sanity_for_paths(req.paths)
 return start_job('sanity-v4',raster_sanity_paths,req.paths,req.thumbnail,req.edge_threshold,req.light_blur,req.medium_blur,req.heavy_blur,req.grade_b_largest_fraction,force)

class BulkRequest(Paths):kind:str;labels:list[str]=[];model:str|None=None;confidence:float=.25
@app.post('/api/jobs')
def create_job(req:BulkRequest):
 if req.kind=='classify':
  labels=[x.strip() for x in req.labels if x.strip()]
  if not labels: raise HTTPException(400,'Need at least one label')
  return start_job('classify',classify_paths,req.paths,labels,req.model or 'openai/clip-vit-base-patch32')
 if req.kind=='embed':return start_job('embed',embed_paths,req.paths,req.model or 'openai/clip-vit-base-patch32')
 if req.kind=='detect':return start_job('detect',detect_paths,req.paths,req.model or 'yolo11n.pt',req.confidence)
 if req.kind=='segment':return start_job('segment',segment_paths,req.paths,req.model or 'facebook/sam-vit-base','ultralytics',req.confidence)
 raise HTTPException(400,'Unknown job kind')

class QualityRequest(Paths):
 model:str='openai/clip-vit-base-patch32'
 batch_size:int=32
 force:bool=False
class DiscardShownRequest(BaseModel):
 paths:list[str]


@app.post('/api/mv/quality-known')
def quality_known(req:QualityRequest):
 with db() as c:
  known={r[0] for r in c.execute("SELECT DISTINCT path FROM observations WHERE provider='yuan-iqf-v2' AND model='matthewyuan/image-quality-fusion' AND kind='quality'").fetchall()}
 seen=[x for x in req.paths if x in known]
 return {'requested':len(req.paths),'seen':len(seen),'unseen':len(req.paths)-len(seen)}

@app.post('/api/mv/quality')
def quality(req:QualityRequest):
 with db() as c:
  known={r[0] for r in c.execute("SELECT DISTINCT path FROM observations WHERE provider='yuan-iqf-v2' AND model='matthewyuan/image-quality-fusion' AND kind='quality'").fetchall()}
 todo=list(req.paths) if req.force else [x for x in req.paths if x not in known]
 if not todo:return {'state':'done','kind':'quality','done':0,'total':0,'cached':len(req.paths)}
 job=start_job('quality',lambda ps,progress=None:quality_paths(ps,req.model,progress=progress,batch_size=req.batch_size),todo)
 job['cached']=len(req.paths)-len(todo)
 return job

class LensFindingsDeleteRequest(BaseModel):
 paths:list[str]
 lens:str

@app.post('/api/models/delete-findings')
def delete_lens_findings(req:LensFindingsDeleteRequest):
 paths=list(dict.fromkeys(str(norm(x)) for x in req.paths))
 if not paths:return {'deleted':0,'files':0}
 lens=req.lens
 if lens=='builtin:oiv7':provider='ultralytics-oiv7';base='yolov8n-oiv7.pt'
 elif lens=='builtin:world':provider='ultralytics-world';base='yolov8s-worldv2.pt'
 else:provider='ultralytics';base=str(norm(lens))
 deleted=0
 with db() as c:
  for start in range(0,len(paths),500):
   chunk=paths[start:start+500];marks=','.join('?'*len(chunk));args=[*chunk,provider,base,base+'#%']
   deleted+=c.execute(f"SELECT COUNT(*) FROM observations WHERE path IN ({marks}) AND provider=? AND (model=? OR model LIKE ?)",args).fetchone()[0]
   c.execute(f"DELETE FROM observations WHERE path IN ({marks}) AND provider=? AND (model=? OR model LIKE ?)",args)
 bump_obs_revision()
 return {'deleted':deleted,'files':len(paths),'lens':lens}

@app.post('/api/dev/analysis/shown')
def discard_shown_analysis(req:DiscardShownRequest):
 # Production-safe scoped reset: delete derived state only for the exact client-visible population.
 paths=list(dict.fromkeys(str(norm(x)) for x in req.paths))
 if not paths:return {'discarded':{'files':0,'observations':0,'embeddings':0}}
 observations=embeddings=0
 with db() as c:
  for start in range(0,len(paths),500):
   chunk=paths[start:start+500]; marks=','.join('?'*len(chunk))
   observations+=c.execute(f'SELECT COUNT(*) FROM observations WHERE path IN ({marks})',chunk).fetchone()[0]
   embeddings+=c.execute(f'SELECT COUNT(*) FROM embeddings WHERE path IN ({marks})',chunk).fetchone()[0]
   c.execute(f'DELETE FROM observations WHERE path IN ({marks})',chunk)
   c.execute(f'DELETE FROM embeddings WHERE path IN ({marks})',chunk)
 bump_obs_revision()
 return {'discarded':{'files':len(paths),'observations':observations,'embeddings':embeddings}}

@app.delete('/api/dev/analysis')
def discard_analysis():
 # Development whiteboard reset: never touches source images or folders.
 with db() as c:
  observations=c.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
  embeddings=c.execute('SELECT COUNT(*) FROM embeddings').fetchone()[0]
  c.execute('DELETE FROM observations'); c.execute('DELETE FROM embeddings')
 with LOCK:
  jobs=len(JOBS); JOBS.clear()
 return {'discarded':{'observations':observations,'embeddings':embeddings,'jobs':jobs}}

@app.post('/api/jobs/stop-analysis')
def stop_analysis():
 stopped=[]
 with LOCK:
  for jid,j in JOBS.items():
   if j.get('state') in ('queued','running') and not str(j.get('kind','')).startswith('external:'):
    j['cancel_requested']=True;j['updated']=time.time();stopped.append(jid)
 _write_active_job_journal()
 LOG.info('Stop Analysis requested for %s active analysis job(s)',len(stopped))
 return {'requested':len(stopped),'jobs':stopped}

@app.get('/api/jobs')
def jobs():return {'jobs':sorted(JOBS.values(),key=lambda x:x['created'],reverse=True)[:20],'observation_revision':OBS_REV}

# --- P.90 Learning Loop: box -> SAM/paint -> YOLO model evolution ---
SAM_MODELS=MODELS/'sam'; SAM_MODELS.mkdir(parents=True,exist_ok=True)
LEARNING_ROOT=ROOT/'learning'; LEARNING_ROOT.mkdir(parents=True,exist_ok=True)
LEARNING_LOCK=threading.RLock()

class SamMaskRequest(BaseModel):
 path:str; bbox:list[float]
class YoloEvolutionRequest(BaseModel):
 mode:str='new'                 # new | add_class | add_segmentation | retrain
 name:str='n8vision-seg'
 base_model:str|None=None
 classes:list[str]|None=None
 epochs:int=100
 imgsz:int=640
 batch:int=-1
 device:str|None=None
class LearningSettingsRequest(BaseModel):
 maintenance_enabled:bool=False
 maintenance_time:str='03:00'
 correction_threshold:int=25

def _rle_from_binary(a):
 flat=a.reshape(-1);out=[];i=0;n=len(flat)
 while i<n:
  if not flat[i]:i+=1;continue
  start=i
  while i<n and flat[i]:i+=1
  out.extend((int(start),int(i-start)))
 return out

def _binary_from_geometry(g,w,h):
 import numpy as np
 a=np.zeros((h,w),dtype=np.uint8)
 if g.get('mask_rle') and g.get('mask_size') and g.get('bbox'):
  mw,mh=map(int,g['mask_size']);x1,y1,_,_=map(lambda x:int(round(float(x))),g['bbox']);flat=np.zeros(mw*mh,dtype=np.uint8)
  for i in range(0,len(g['mask_rle']),2):
   st,ln=map(int,g['mask_rle'][i:i+2]);flat[st:st+ln]=1
  crop=flat.reshape((mh,mw));xa=max(0,x1);ya=max(0,y1);xb=min(w,x1+mw);yb=min(h,y1+mh)
  if xb>xa and yb>ya:a[ya:yb,xa:xb]=crop[ya-y1:yb-y1,xa-x1:xb-x1]
 elif g.get('polygon'):
  import cv2
  pts=np.asarray(g['polygon'],dtype=np.int32).reshape((-1,1,2));cv2.fillPoly(a,[pts],1)
 return a

def _mask_polygon(g,w,h):
 import cv2, numpy as np
 a=_binary_from_geometry(g,w,h)
 contours,_=cv2.findContours(a,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
 polys=[]
 for c in contours:
  if cv2.contourArea(c)<2:continue
  eps=max(.5,.0015*cv2.arcLength(c,True));q=cv2.approxPolyDP(c,eps,True).reshape(-1,2)
  if len(q)>=3:polys.append(q)
 return polys

@app.post('/api/learning/sam-mask')
def learning_sam_mask(req:SamMaskRequest):
 try:return _sam_box_geometry(req.path,req.bbox)
 except Exception as e:raise HTTPException(500,f'SAM box-to-mask failed: {e}')

def _learning_model_rows():
 models=scan_ultralytics_models(False);out=[]
 for m in models:
  classes=list(m.get('classes') or [])
  if not classes and Path(str(m.get('path',''))).is_file():
   try:
    from ultralytics import YOLO
    names=getattr(YOLO(str(m['path'])),'names',{}) or {};classes=list(names.values()) if isinstance(names,dict) else list(names)
   except Exception:pass
  out.append({**m,'classes':classes,'segmentation':m.get('family')=='seg' or m.get('task')=='segment'})
 return out

@app.get('/api/learning/options')
def learning_options():
 cfg=_load_config().get('learning',{});models=_learning_model_rows()
 bbox_only=[]
 for m in models:
  if not m['segmentation']:
   for cls in m.get('classes',[]):bbox_only.append({'model':m['path'],'model_name':m['name'],'class':cls})
 with db() as c:
  concepts=[r[0] for r in c.execute("SELECT DISTINCT concept FROM observations WHERE confidence>0 AND kind IN ('bbox','mask') ORDER BY concept COLLATE NOCASE").fetchall()]
  human=int(c.execute("SELECT COUNT(*) FROM corrections WHERE action IN ('teach','relabel','reject')").fetchone()[0]) if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='corrections'").fetchone() else 0
 return {'models':models,'bbox_only':bbox_only,'concepts':concepts,'settings':cfg,'manual_observations':human}

@app.put('/api/learning/settings')
def learning_settings(req:LearningSettingsRequest):
 if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',req.maintenance_time):raise HTTPException(400,'maintenance_time must be HH:MM')
 cfg=_load_config();cfg['learning']={'maintenance_enabled':bool(req.maintenance_enabled),'maintenance_time':req.maintenance_time,'correction_threshold':max(1,int(req.correction_threshold)),'last_maintenance_day':cfg.get('learning',{}).get('last_maintenance_day','')};_save_config(cfg);return cfg['learning']

def _training_annotations(classes=None):
 wanted=set(classes or []);out={}
 with db() as c:
  rows=c.execute("SELECT path,concept,provider,model,kind,geometry,updated FROM observations WHERE confidence>0 AND kind IN ('bbox','mask') AND geometry IS NOT NULL ORDER BY updated").fetchall()
 for r in rows:
  if wanted and r['concept'] not in wanted:continue
  try:g=json.loads(r['geometry'])
  except Exception:continue
  if not g.get('bbox'):continue
  # Prefer masks. A later mask for the same path/concept/bbox supersedes a bare box.
  key=(r['path'],r['concept'],tuple(round(float(x),2) for x in g['bbox']))
  old=out.get(key)
  if old is None or (r['kind']=='mask' and old['kind']!='mask'):out[key]={**dict(r),'geometry_obj':g}
 return list(out.values())

def _seg_architecture_for(base:str|None):
 if not base:return 'yolo11n-seg.pt'
 stem=Path(base).stem.lower()
 # Official/custom filenames commonly retain the YOLO generation/size token.
 m=re.search(r'(yolo(?:v)?\d+)([nslmx])',stem)
 if m:return f'{m.group(1)}{m.group(2)}-seg.yaml'
 return 'yolo11n-seg.yaml'

def _evolve_yolo(req:YoloEvolutionRequest,progress=None):
 from ultralytics import YOLO
 import yaml
 mode=req.mode.lower().strip()
 if mode not in {'new','add_class','add_segmentation','retrain'}:raise RuntimeError('Unknown evolution mode')
 selected=list(req.classes or [])
 # Add-Class and Retrain retain the extant vocabulary: replay archived masks for old classes
 # alongside the new/corrected observations instead of teaching the network to forget.
 if req.base_model and mode in {'add_class','retrain'}:
  try:
   old_names=getattr(YOLO(req.base_model),'names',{}) or {};old_classes=list(old_names.values()) if isinstance(old_names,dict) else list(old_names)
   selected=sorted(set(selected)|set(map(str,old_classes)),key=str.lower)
  except Exception:pass
 annotations=_training_annotations(selected or None)
 masks=[x for x in annotations if x['kind']=='mask']
 if not masks:raise RuntimeError('No masked observations match this training request. Box/paint examples first.')
 classes=sorted(set(x['concept'] for x in masks),key=str.lower);class_id={x:i for i,x in enumerate(classes)}
 run_id=time.strftime('%Y%m%d-%H%M%S');name=_safe_name(req.name);root=LEARNING_ROOT/name/run_id;images=root/'dataset'/'images'/'train';labels=root/'dataset'/'labels'/'train';images.mkdir(parents=True);labels.mkdir(parents=True)
 by_path={}
 for x in masks:by_path.setdefault(x['path'],[]).append(x)
 total=len(by_path)
 for i,(raw,items) in enumerate(by_path.items(),1):
  src=norm(raw)
  if not image_file(src):continue
  with Image.open(src) as im:w,h=im.size
  dst=images/f'{i:06d}{src.suffix.lower()}';shutil.copy2(src,dst);lines=[]
  for x in items:
   for poly in _mask_polygon(x['geometry_obj'],w,h):
    pts=[]
    for px,py in poly:pts.extend((max(0,min(1,float(px)/w)),max(0,min(1,float(py)/h))))
    if len(pts)>=6:lines.append(str(class_id[x['concept']])+' '+' '.join(f'{q:.6f}' for q in pts))
  (labels/f'{i:06d}.txt').write_text('\n'.join(lines),encoding='utf-8')
  if progress:progress(i,total,phase='assembling-segmentation-dataset')
 data={'path':str(root/'dataset'),'train':'images/train','val':'images/train','names':{i:c for c,i in class_id.items()}}
 data_path=root/'dataset.yaml';data_path.write_text(yaml.safe_dump(data,sort_keys=False),encoding='utf-8')
 base=req.base_model
 if mode=='new':model=YOLO('yolo11n-seg.pt')
 elif mode=='add_segmentation':
  if not base:raise RuntimeError('Add Segmentation requires an existing detector model')
  model=YOLO(_seg_architecture_for(base));model.load(base)
 else:
  if not base:raise RuntimeError(f'{mode} requires an existing model')
  model=YOLO(base)
 result=model.train(data=str(data_path),epochs=max(1,int(req.epochs)),imgsz=max(128,int(req.imgsz)),batch=int(req.batch),device=req.device or None,project=str(root/'runs'),name='evolve',exist_ok=True)
 best=Path(getattr(result,'save_dir',root/'runs'/'evolve'))/'weights'/'best.pt'
 if not best.exists():raise RuntimeError(f'Training completed but best.pt was not found at {best}')
 final=ULTRA_MODELS/'seg'/f'{name}.pt';shutil.copy2(best,final)
 receipt={'schema':1,'mode':mode,'name':name,'base_model':base,'classes':classes,'samples':len(by_path),'masked_instances':len(masks),'epochs':int(req.epochs),'imgsz':int(req.imgsz),'created':time.time(),'correction_baseline':time.time(),'best':str(best),'installed':str(final),'dataset':str(data_path)};_write_json(root/'n8vision-evolution.json',receipt)
 return receipt

@app.post('/api/learning/evolve')
def learning_evolve(req:YoloEvolutionRequest):
 if req.mode!='new' and req.base_model and not Path(req.base_model).is_file():raise HTTPException(404,'Base YOLO model not found')
 return start_job('learning:yolo-evolve',_evolve_yolo,req)

def _maintenance_candidates():
 cfg=_load_config().get('learning',{});threshold=max(1,int(cfg.get('correction_threshold',25) or 25));out=[]
 for receipt_path in LEARNING_ROOT.glob('*/*/n8vision-evolution.json'):
  r=_read_json(receipt_path,{})
  installed=Path(str(r.get('installed') or ''))
  if not installed.is_file():continue
  # Only the newest receipt for a deployed path is relevant.
  newer=False
  for other in LEARNING_ROOT.glob('*/*/n8vision-evolution.json'):
   if other==receipt_path:continue
   q=_read_json(other,{})
   if q.get('installed')==r.get('installed') and float(q.get('created',0))>float(r.get('created',0)):newer=True;break
  if newer:continue
  classes=set(r.get('classes') or []);since=float(r.get('correction_baseline') or r.get('created') or 0)
  with db() as c:
   rows=c.execute("SELECT original_concept,corrected_concept,action,created FROM corrections WHERE created>? ORDER BY created",(since,)).fetchall()
  relevant=[x for x in rows if (x['corrected_concept'] in classes or x['original_concept'] in classes)]
  if len(relevant)>=threshold:out.append((r,len(relevant)))
 return out

def _learning_maintenance_loop():
 while True:
  try:
   time.sleep(30);cfg=_load_config();lc=cfg.get('learning',{})
   if not lc.get('maintenance_enabled'):continue
   hhmm=time.strftime('%H:%M');today=time.strftime('%Y-%m-%d')
   if hhmm!=str(lc.get('maintenance_time','03:00')) or lc.get('last_maintenance_day')==today:continue
   lc['last_maintenance_day']=today;cfg['learning']=lc;_save_config(cfg)
   for r,count in _maintenance_candidates():
    req=YoloEvolutionRequest(mode='retrain',name=r.get('name') or Path(r['installed']).stem,base_model=r['installed'],classes=r.get('classes') or [],epochs=int(r.get('epochs') or 100),imgsz=int(r.get('imgsz') or 640),batch=-1)
    job=start_job('learning:maintenance-retrain',_evolve_yolo,req)
    LOG.info('Maintenance retrain queued: %s · %s manual corrections · job %s',r.get('name'),count,job['id'])
  except Exception as e:LOG.exception('Learning maintenance check failed: %s',e)
threading.Thread(target=_learning_maintenance_loop,daemon=True,name='n8-learning-maintenance').start()

# --- 0.9.0 Ordering: durable training projects + external work shelves ---
TRAINING_DEFAULT=ROOT/'training'; TRAINING_DEFAULT.mkdir(parents=True,exist_ok=True)
WORKFLOWS=Path(__file__).resolve().parent/'workflows'; WORKFLOWS.mkdir(parents=True,exist_ok=True)
ENV_CONFIG_PATH=DATA/'environments.json'
MODEL_LANGUAGE_PROFILES={
 'sdxl-generic':{'name':'SDXL Generic','architecture':'sdxl','caption_form':'tags','nominal_resolution':1024,'bucket':True},
 'pony':{'name':'Pony','architecture':'sdxl','inherits':'sdxl-generic','caption_form':'tags','nominal_resolution':1024,'bucket':True},
 'illustrious':{'name':'Illustrious','architecture':'sdxl','inherits':'sdxl-generic','caption_form':'tags','nominal_resolution':1024,'bucket':True},
}
TRAINER_TARGETS={
 'comfy-trainlora':{'name':'Comfy Native / TrainLoRA','caption_ext':'.txt'},
 'civitai':{'name':'CivitAI','caption_ext':'.txt'},
}
def _safe_name(s:str)->str:
 s=''.join(c if c.isalnum() or c in '._-' else '_' for c in s.strip()).strip('._')
 return s or 'training_project'
def _project_file(folder:Path)->Path:return folder/'n8vision-project.json'
def _read_json(path:Path,default):
 try:return json.loads(path.read_text(encoding='utf-8'))
 except Exception:return default
def _write_json(path:Path,data):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(path)
def _load_project(folder:str):
 p=norm(folder); mf=_project_file(p)
 if not mf.exists():raise HTTPException(404,'Not an N8Vision training project')
 d=_read_json(mf,None)
 if not isinstance(d,dict):raise HTTPException(500,'Invalid training project manifest')
 return p,d
def _save_project(p:Path,d:dict):
 d['updated']=time.time();_write_json(_project_file(p),d)
class TrainingCreateRequest(BaseModel):
 name:str; paths:list[str]; root:str|None=None; model_profile:str='sdxl-generic'; trainer:str='comfy-trainlora'
class TrainingAddRequest(BaseModel):
 project:str; paths:list[str]
class TrainingPolicyRequest(BaseModel):
 project:str; term:str; state:int; paths:list[str]|None=None
class TrainingAssembleRequest(BaseModel):
 project:str; trainer:str|None=None; model_profile:str|None=None
class TrainingReviewRequest(BaseModel):
 project:str; paths:list[str]; include:bool|None=None; reviewed:bool|None=None
class TrainingNeighborsRequest(BaseModel):
 project:str; path:str; limit:int=48
@app.get('/api/training/options')
def training_options():return {'default_root':str(TRAINING_DEFAULT),'model_profiles':MODEL_LANGUAGE_PROFILES,'trainers':TRAINER_TARGETS}
@app.post('/api/training/create')
def training_create(req:TrainingCreateRequest):
 if not req.paths:raise HTTPException(400,'No source images')
 if req.model_profile not in MODEL_LANGUAGE_PROFILES:raise HTTPException(400,'Unknown model-language profile')
 if req.trainer not in TRAINER_TARGETS:raise HTTPException(400,'Unknown trainer target')
 name=_safe_name(req.name);root=norm(req.root) if req.root else TRAINING_DEFAULT;root.mkdir(parents=True,exist_ok=True);folder=root/name
 if folder.exists() and any(folder.iterdir()):raise HTTPException(409,f'Project folder already exists and is not empty: {folder}')
 folder.mkdir(parents=True,exist_ok=True);items=[]
 for i,raw in enumerate(dict.fromkeys(req.paths),1):
  src=norm(raw)
  if not image_file(src):continue
  dest=folder/f'{name}_{i:06d}{src.suffix.lower()}'
  shutil.copy2(src,dest)
  h=hashlib.sha256()
  with src.open('rb') as f:
   for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
  try:
   with Image.open(src) as im:w,hgt=im.size
  except Exception:w=hgt=None
  items.append({'id':uuid.uuid4().hex,'source_path':str(src),'source_sha256':h.hexdigest(),'original_name':src.name,'file':dest.name,'width':w,'height':hgt,'terms':{},'reviewed':False,'include':True})
 project={'schema':1,'name':name,'folder':str(folder),'created':time.time(),'updated':time.time(),'revision':1,'model_profile':req.model_profile,'working_target':req.trainer,'batch_terms':{},'items':items,'targets':{}}
 _save_project(folder,project);return {'project':project}
@app.get('/api/training/project')
def training_project(path:str):
 _,d=_load_project(path);return {'project':d}
@app.post('/api/training/add')
def training_add(req:TrainingAddRequest):
 p,d=_load_project(req.project)
 existing_hashes={x.get('source_sha256') for x in d.get('items',[]) if x.get('source_sha256')}
 existing_sources={x.get('source_path') for x in d.get('items',[]) if x.get('source_path')}
 used={x.get('file') for x in d.get('items',[]) if x.get('file')}
 next_i=1
 prefix=f"{d.get('name','training_project')}_"
 for fn in used:
  if isinstance(fn,str) and fn.startswith(prefix):
   try:next_i=max(next_i,int(Path(fn).stem.rsplit('_',1)[1])+1)
   except Exception:pass
 added=[];duplicates=[];skipped=[]
 for raw in dict.fromkeys(req.paths):
  src=norm(raw)
  if not image_file(src):skipped.append(str(src));continue
  h=hashlib.sha256()
  with src.open('rb') as f:
   for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
  digest=h.hexdigest()
  if digest in existing_hashes or str(src) in existing_sources:
   duplicates.append(str(src));continue
  while True:
   fn=f"{d.get('name','training_project')}_{next_i:06d}{src.suffix.lower()}";next_i+=1
   if fn not in used and not (p/fn).exists():break
  dest=p/fn;shutil.copy2(src,dest)
  try:
   with Image.open(src) as im:w,hgt=im.size
  except Exception:w=hgt=None
  item={'id':uuid.uuid4().hex,'source_path':str(src),'source_sha256':digest,'original_name':src.name,'file':fn,'width':w,'height':hgt,'terms':{},'reviewed':False,'include':True}
  d.setdefault('items',[]).append(item);added.append(item);used.add(fn);existing_hashes.add(digest);existing_sources.add(str(src))
 if added:
  d['revision']=int(d.get('revision',0))+1
  for target in d.setdefault('targets',{}).values():target['status']='stale'
  _save_project(p,d)
 return {'project':d,'added':len(added),'duplicates':len(duplicates),'skipped':len(skipped)}
@app.post('/api/training/policy')
def training_policy(req:TrainingPolicyRequest):
 p,d=_load_project(req.project);state=max(-1,min(1,int(req.state)));term=req.term.strip()
 if not term:raise HTTPException(400,'Empty term')
 if req.paths is None:
  d.setdefault('batch_terms',{})[term]=state
 else:
  wanted=set(req.paths)
  for item in d.get('items',[]):
   full=str(p/item['file'])
   if full in wanted or item['file'] in wanted or item.get('source_path') in wanted:item.setdefault('terms',{})[term]=state
 d['revision']=int(d.get('revision',0))+1
 for target in d.setdefault('targets',{}).values():target['status']='stale'
 _save_project(p,d);return {'project':d}
@app.post('/api/training/review')
def training_review(req:TrainingReviewRequest):
 p,d=_load_project(req.project);wanted=set(req.paths);changed=0
 for item in d.get('items',[]):
  full=str(p/item['file'])
  if full in wanted or item.get('file') in wanted or item.get('source_path') in wanted:
   if req.include is not None:item['include']=bool(req.include)
   if req.reviewed is not None:item['reviewed']=bool(req.reviewed)
   changed+=1
 if changed:
  d['revision']=int(d.get('revision',0))+1
  for target in d.setdefault('targets',{}).values():target['status']='stale'
  _save_project(p,d)
 return {'project':d,'changed':changed}

def _unpack_vec(blob,dim):
 import struct
 try:return struct.unpack('<'+'f'*int(dim),blob)
 except Exception:return None
@app.post('/api/training/neighbors')
def training_neighbors(req:TrainingNeighborsRequest):
 p,d=_load_project(req.project);src=norm(req.path);limit=max(1,min(200,int(req.limit)))
 for item in d.get('items',[]):
  if str(p/item.get('file',''))==str(src) and item.get('source_path'):
   src=norm(item['source_path']);break
 with db() as c:
  row=c.execute("SELECT provider,model,dim,vector FROM embeddings WHERE path=? ORDER BY updated DESC LIMIT 1",(str(src),)).fetchone()
  if not row:raise HTTPException(409,'This image has no archived embedding yet.')
  provider,model,dim,blob=row;seed=_unpack_vec(blob,dim)
  if not seed:raise HTTPException(500,'Stored embedding is unreadable.')
  candidates=c.execute("SELECT path,dim,vector FROM embeddings WHERE provider=? AND model=? AND path<>?",(provider,model,str(src))).fetchall()
 scored=[]
 for path,cdim,cblob in candidates:
  if int(cdim)!=int(dim):continue
  v=_unpack_vec(cblob,cdim)
  if not v:continue
  score=sum(a*b for a,b in zip(seed,v));scored.append((score,path))
 scored.sort(reverse=True)
 return {'seed':str(src),'provider':provider,'model':model,'neighbors':[{'path':x,'similarity':float(sc)} for sc,x in scored[:limit]]}

def _bucket_for(w,h,res=1024):
 if not w or not h:return None
 ratio=float(w)/float(h);step=64;area=res*res
 bw=max(step,round((area*ratio)**.5/step)*step);bh=max(step,round((area/ratio)**.5/step)*step)
 scale=min(1.0,bw/float(w),bh/float(h))
 return {'width':int(bw),'height':int(bh),'scale':round(scale,4),'upscale':False}
@app.get('/api/training/diagnostics')
def training_diagnostics(path:str):
 p,d=_load_project(path);included=[x for x in d.get('items',[]) if x.get('include',True)]
 buckets={};reviewed=0
 for x in included:
  if x.get('reviewed'):reviewed+=1
  b=_bucket_for(x.get('width'),x.get('height'),MODEL_LANGUAGE_PROFILES.get(d.get('model_profile'),{}).get('nominal_resolution',1024))
  if b:
   key=f"{b['width']}x{b['height']}";buckets[key]=buckets.get(key,0)+1
 return {'included':len(included),'excluded':len(d.get('items',[]))-len(included),'reviewed':reviewed,'unreviewed':len(included)-reviewed,'buckets':dict(sorted(buckets.items(),key=lambda kv:(-kv[1],kv[0])))}

def _effective_terms(d,item):
 terms=dict(d.get('batch_terms',{}));terms.update(item.get('terms',{}));return terms
@app.post('/api/training/assemble')
def training_assemble(req:TrainingAssembleRequest):
 p,d=_load_project(req.project);trainer=req.trainer or d.get('working_target','comfy-trainlora');profile=req.model_profile or d.get('model_profile','sdxl-generic')
 if trainer not in TRAINER_TARGETS or profile not in MODEL_LANGUAGE_PROFILES:raise HTTPException(400,'Unknown target/profile')
 out=p/'assembled'/trainer;out.mkdir(parents=True,exist_ok=True)
 neg={};manifest=[]
 for item in d.get('items',[]):
  if not item.get('include',True):continue
  src=p/item['file'];dst=out/item['file'];shutil.copy2(src,dst)
  terms=_effective_terms(d,item);pos=[k for k,v in terms.items() if int(v)>0];bad=[k for k,v in terms.items() if int(v)<0]
  dst.with_suffix(TRAINER_TARGETS[trainer]['caption_ext']).write_text(', '.join(pos),encoding='utf-8')
  if bad:neg[item['file']]=bad
  manifest.append({'file':item['file'],'positive':pos,'negative':bad,'source_sha256':item.get('source_sha256'),'bucket':_bucket_for(item.get('width'),item.get('height'),MODEL_LANGUAGE_PROFILES[profile].get('nominal_resolution',1024)),'reviewed':bool(item.get('reviewed'))})
 _write_json(out/'n8vision-negatives.json',neg);_write_json(out/'n8vision-manifest.json',{'trainer':trainer,'model_profile':profile,'source_revision':d.get('revision'),'items':manifest})
 d['working_target']=trainer;d['model_profile']=profile;d.setdefault('targets',{})[trainer]={'status':'assembled','revision':d.get('revision'),'output':str(out),'model_profile':profile};_save_project(p,d)
 return {'output':str(out),'files':len(manifest),'project':d}

# P.01: prepared Comfy training workspaces are deliberate, editable jobs.
# N8Vision prepares them; the human queues them in Comfy after inspection/tweaking.
class TrainingPrepareComfyRequest(BaseModel):
 project:str; environment_id:str|None=None
class TrainingArchiveRequest(BaseModel):
 project:str; archive_root:str|None=None; include_results:bool=True
class TrainingResumeRequest(BaseModel):
 archive:str; environment_id:str|None=None

def _find_comfy_env(environment_id=None):
 envs=_load_envs().get('environments',[])
 if environment_id:
  env=next((x for x in envs if x.get('id')==environment_id),None)
  if not env:raise HTTPException(404,'Comfy environment not found')
  if env.get('kind')!='comfy':raise HTTPException(400,'Selected environment is not ComfyUI')
  return env
 env=next((x for x in envs if x.get('kind')=='comfy'),None)
 if not env:raise HTTPException(409,'No ComfyUI environment has proclaimed itself yet.')
 return env

def _comfy_output_root(env):
 root=env.get('output_root')
 if root:return norm(root)
 raise HTTPException(409,'N8Vision Bridge has not proclaimed ComfyUI’s configured output directory. Update/restart the N8Vision Bridge extension.')

def _native_train_workflow():
 candidates=[WORKFLOWS/'N8Train-SDXL.json',WORKFLOWS/'N8Train.json']
 for p in candidates:
  if p.exists():return p
 raise HTTPException(500,'Native Shelf N8Train workflow is missing.')

def _node_title(n):
 return str(n.get('title') or n.get('properties',{}).get('Node name for S&R') or n.get('type') or '')

def _patch_native_train_workflow(doc,dataset_folder,project_name):
 """Patch by identities discovered from the Native Shelf itself, not hard-coded node IDs."""
 hits={'dataset':0,'lora':0,'loss':0}
 for n in doc.get('nodes',[]):
  typ=str(n.get('type','')); title=_node_title(n); vals=n.get('widgets_values')
  if not isinstance(vals,list):continue
  # The shelf defines which node types/widgets constitute the contract. User-overwritten shelf copies remain authoritative.
  if typ=='LoadImageTextDataSetFromFolder' or 'ImageTextDataSet' in typ:
   if vals: vals[0]=str(dataset_folder);hits['dataset']+=1
  elif typ=='SaveLoRA' or title=='SaveLoRA':
   if vals: vals[0]=f'loras/{project_name}';hits['lora']+=1
  elif typ=='LossGraphNode' or title=='LossGraphNode':
   if vals: vals[0]=f'{project_name}_loss';hits['loss']+=1
 if not hits['dataset']:raise HTTPException(409,'Native Shelf training workflow has no dataset target.')
 return hits

def _stage_workflow_in_comfy(env,workflow_path:Path):
 # Queue only the tiny bridge command. The training graph is loaded into the UI and is NOT queued.
 import urllib.request
 base=str(env.get('api_url') or '').rstrip('/')
 if not base:return {'staged':False,'error':'Comfy API URL unavailable'}
 prompt={'1':{'class_type':'N8VisionLoadWorkflow','inputs':{'workflow_path':str(workflow_path)}}}
 body=json.dumps({'prompt':prompt,'client_id':'n8vision-'+uuid.uuid4().hex[:8]}).encode('utf-8')
 try:
  req=urllib.request.Request(base+'/prompt',data=body,headers={'Content-Type':'application/json'},method='POST')
  with urllib.request.urlopen(req,timeout=2.0) as r: reply=json.loads(r.read().decode('utf-8') or '{}')
  return {'staged':True,'prompt_id':reply.get('prompt_id')}
 except Exception as e:
  LOG.warning('Comfy workflow staging bridge unavailable: %s',e)
  return {'staged':False,'error':str(e)}

@app.post('/api/training/prepare-comfy')
def training_prepare_comfy(req:TrainingPrepareComfyRequest):
 p,d=_load_project(req.project);env=_find_comfy_env(req.environment_id);outroot=_comfy_output_root(env)
 workspace=outroot/'N8Vision'/'N8Train'/d['name'];dataset=workspace/'dataset';workspace.mkdir(parents=True,exist_ok=True)
 # Rebuild the consumable dataset from project truth.
 if dataset.exists():shutil.rmtree(dataset)
 dataset.mkdir(parents=True,exist_ok=True)
 trainer=d.get('working_target','comfy-trainlora');profile=d.get('model_profile','sdxl-generic');manifest=[]
 for item in d.get('items',[]):
  if not item.get('include',True):continue
  src=p/item['file'];dst=dataset/item['file'];shutil.copy2(src,dst)
  terms=_effective_terms(d,item);pos=[k for k,v in terms.items() if int(v)>0];bad=[k for k,v in terms.items() if int(v)<0]
  dst.with_suffix('.txt').write_text(', '.join(pos),encoding='utf-8')
  manifest.append({'file':item['file'],'positive':pos,'negative':bad,'source_sha256':item.get('source_sha256'),'bucket':_bucket_for(item.get('width'),item.get('height'),MODEL_LANGUAGE_PROFILES[profile].get('nominal_resolution',1024))})
 shelf=_native_train_workflow();wf=json.loads(shelf.read_text(encoding='utf-8'));hits=_patch_native_train_workflow(wf,dataset,d['name'])
 workflow_path=workspace/f"{d['name']}.json";_write_json(workflow_path,wf)
 snapshot={'schema':1,'project':d['name'],'source_project':str(p),'source_revision':d.get('revision'),'trainer':trainer,'model_profile':profile,'prepared':time.time(),'dataset':str(dataset),'workflow':str(workflow_path),'native_shelf':str(shelf),'targets':hits,'items':manifest}
 _write_json(workspace/'manifest.json',snapshot)
 d['prepared_workspace']=str(workspace);d['prepared_workflow']=str(workflow_path);d['state']='prepared';_save_project(p,d)
 stage=_stage_workflow_in_comfy(env,workflow_path)
 return {'project':d,'workspace':str(workspace),'dataset':str(dataset),'workflow':str(workflow_path),'targets':hits,'stage':stage,'note':'Prepared and staged in ComfyUI when the bridge is available. Training is never auto-queued.'}

@app.post('/api/training/archive')
def training_archive(req:TrainingArchiveRequest):
 p,d=_load_project(req.project);workspace=Path(d.get('prepared_workspace') or '')
 if not workspace.exists():raise HTTPException(409,'Project has no prepared Comfy workspace to archive.')
 archive_root=norm(req.archive_root) if req.archive_root else workspace.parent/'Archive';archive_root.mkdir(parents=True,exist_ok=True)
 archive=archive_root/f"{d['name']}.zip";tmp=archive.with_suffix('.zip.tmp')
 import zipfile
 with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for f in workspace.rglob('*'):
   if f.is_file():z.write(f,f.relative_to(workspace))
  # Preserve N8Vision project truth inside the box as a resume/rebuild receipt.
  z.write(_project_file(p),'n8vision-project.json')
 with zipfile.ZipFile(tmp,'r') as z:
  bad=z.testzip()
  if bad:raise HTTPException(500,f'Archive verification failed at {bad}')
 tmp.replace(archive)
 shutil.rmtree(workspace)
 d['state']='archived';d['archive']=str(archive);d['archived']=time.time();d.pop('prepared_workspace',None);d.pop('prepared_workflow',None);_save_project(p,d)
 return {'project':d,'archive':str(archive),'removed_workspace':str(workspace)}

@app.post('/api/training/resume')
def training_resume(req:TrainingResumeRequest):
 archive=norm(req.archive)
 if not archive.exists():raise HTTPException(404,'Training archive not found.')
 env=_find_comfy_env(req.environment_id);outroot=_comfy_output_root(env)
 import zipfile
 with zipfile.ZipFile(archive,'r') as z:
  names=z.namelist();receipt=json.loads(z.read('n8vision-project.json')) if 'n8vision-project.json' in names else None
  name=_safe_name((receipt or {}).get('name') or archive.stem);workspace=outroot/'N8Vision'/'N8Train'/name
  if workspace.exists() and any(workspace.iterdir()):raise HTTPException(409,f'Resume workspace already exists: {workspace}')
  workspace.mkdir(parents=True,exist_ok=True)
  for info in z.infolist():
   if info.filename=='n8vision-project.json':continue
   target=(workspace/info.filename).resolve()
   if workspace.resolve() not in target.parents and target!=workspace.resolve():raise HTTPException(400,'Unsafe path in archive')
   z.extract(info,workspace)
 return {'workspace':str(workspace),'workflow':str(next(iter(workspace.glob('*.json')),'')),'archive':str(archive),'note':'Archive retained as frozen checkpoint.'}

def _load_envs():
 d=_read_json(ENV_CONFIG_PATH,{'environments':[]});return d if isinstance(d,dict) else {'environments':[]}
def _save_envs(d):_write_json(ENV_CONFIG_PATH,d)
class EnvironmentProclaimRequest(BaseModel):
 id:str|None=None; name:str; kind:str; root:str|None=None; output_root:str|None=None; api_url:str|None=None; workflow_dirs:list[str]=[]; start_command:list[str]|None=None; bridge:str|None=None; capabilities:dict[str,Any]|None=None
@app.post('/api/environments/proclaim')
def environment_proclaim(req:EnvironmentProclaimRequest):
 d=_load_envs();env=req.model_dump();env['id']=req.id or _safe_name(req.name).lower();env['last_seen']=time.time();envs=[x for x in d.get('environments',[]) if x.get('id')!=env['id']];envs.append(env);d['environments']=envs;_save_envs(d)
 if env.get('kind')=='comfy':threading.Thread(target=_scan_comfy_tool_shelf_once,args=(env,),name='n8vision-comfy-shelf-proclaim',daemon=True).start()
 return {'ok':True,'environment':env}
def _env_online(env):
 if not env.get('api_url'):return False
 try:
  import urllib.request
  with urllib.request.urlopen(env['api_url'],timeout=.35) as r:return r.status<500
 except Exception:return False
def _scan_workflows(dirs):
 out=[]
 for raw in dirs:
  try:
   p=norm(raw)
   if p.exists():
    for x in sorted(p.rglob('*')):
     if x.is_file() and x.suffix.lower() in {'.json','.yaml','.yml','.txt'}:out.append({'name':x.stem,'path':str(x)})
  except Exception:pass
 return out[:2000]
@app.get('/api/environments')
def environments():
 d=_load_envs();out=[]
 for env in d.get('environments',[]):
  e=dict(env);e['online']=_env_online(e);e['workflows']=_scan_workflows(e.get('workflow_dirs',[]));out.append(e)
 internal=_scan_workflows([str(WORKFLOWS)])
 return {'internal':internal,'environments':out,'workflow_folder':str(WORKFLOWS)}
@app.post('/api/environments/start/{env_id}')
def environment_start(env_id:str):
 import subprocess
 env=next((x for x in _load_envs().get('environments',[]) if x.get('id')==env_id),None)
 if not env:raise HTTPException(404,'Unknown environment')
 cmd=env.get('start_command')
 if not cmd:raise HTTPException(400,'No start command registered for this environment')
 subprocess.Popen(cmd,cwd=env.get('root') or None,creationflags=(getattr(subprocess,'CREATE_NEW_CONSOLE',0) if os.name=='nt' else 0))
 return {'started':True,'id':env_id}

class PromptTranslatorSettingsRequest(BaseModel):
 model:str=''; type:str='stable_diffusion'; device:str='default'

@app.put('/api/config/prompt-translator')
def prompt_translator_settings(req:PromptTranslatorSettingsRequest):
 cfg=_load_config();cfg['prompt_translator']={'model':req.model.strip(),'type':req.type or 'stable_diffusion','device':req.device or 'default'};_save_config(cfg)
 return {'ok':True,'prompt_translator':cfg['prompt_translator']}

def _prompt_dialect(text:str)->str:
 """Cheap conservative syntax classifier. Comma-list prompts are tags unless prose is unambiguous."""
 t=(text or '').strip()
 if not t:return 'tags'
 parts=[x.strip() for x in t.split(',') if x.strip()]
 booru_markers=len(re.findall(r'(?<!\w)(?:\d+(?:girl|boy)s?|looking_at_\w+|[a-z0-9]+_[a-z0-9_]+|\([^)]*:[0-9.]+\))',t.lower()))
 sentence_ends=len(re.findall(r'[.!?](?:\s|$)',t))
 prose_words=len(re.findall(r'\b(?:the|a|an|with|wearing|standing|sitting|while|which|who|under|behind|beside)\b',t.lower()))
 # Generation metadata is overwhelmingly comma-tag syntax. Ordinary tag phrases such as
 # "standing with arms crossed" must not turn a Pony prompt into prose.
 if len(parts)>=3 and sentence_ends<2:return 'tags'
 if booru_markers>=2:return 'tags'
 if sentence_ends>=2 or (len(parts)<=2 and len(t.split())>=8 and prose_words>=2):return 'natural'
 return 'hybrid'

def _target_prompt_dialect(model:str)->str:
 """Target dialect is deliberately binary. Unknown/any is not an execution dialect."""
 n=(model or '').lower()
 if any(x in n for x in ('pony','illustrious','animagine','novelai','nai')):return 'tags'
 if any(x in n for x in ('flux','kontext','qwen','klein','hunyuan','lumina','wan')):return 'natural'
 # Pony/Illustrious/Animagine and the SD families are tag-native. Unknown legacy
 # checkpoints conservatively fall back to tags rather than waking a translator speculatively.
 return 'tags'

def _translation_instruction(text:str,source:str,target:str)->str:
 if target=='natural':
  task='Translate the source image prompt from booru/tag syntax into concise grammatical natural-language image-prompt prose.'
 else:
  task='Translate the source image prompt into concise booru-style comma-separated tags.'
 fence=(
  'OUTPUT CONTRACT -- FOLLOW EXACTLY:\n'
  '- Return ONLY the translated image prompt.\n'
  '- Preserve every distinct semantic attribute, visual concept, relationship, and emphasis from the source.\n'
  '- You MAY combine adjacent, overlapping, or repeated grammatical fragments when their complete meaning is preserved (for example, "long hair, red hair" may become "long red hair").\n'
  '- Do NOT add, infer, censor, omit, simplify, summarize, generalize, or embellish concepts.\n'
  '- Do NOT introduce the result or say "here is".\n'
  '- Do NOT explain the translation, describe changes, provide reasoning, commentary, notes, or process.\n'
  '- Do NOT use headings, labels, quotation marks, or code fences around the result.'
 )
 return f"{task}\n\n{fence}\n\n<SOURCE_PROMPT>\n{text}\n</SOURCE_PROMPT>"

def _translator_prompt(cfg:dict,text:str,source:str,target:str,request_id:str):
 tr=cfg.get('prompt_translator',{}) or {};model=str(tr.get('model') or '').strip()
 if not model:raise RuntimeError('Prompt translation is required, but no global Prompt Translator model is selected in Settings.')
 # Core Comfy nodes only: CLIPLoader -> TextGenerate -> N8VisionTextReturn.
 return {
  '1':{'class_type':'CLIPLoader','inputs':{'clip_name':model,'type':str(tr.get('type') or 'stable_diffusion'),'device':str(tr.get('device') or 'default')}},
  '2':{'class_type':'TextGenerate','inputs':{'clip':['1',0],'prompt':_translation_instruction(text,source,target),'max_length':512,'sampling_mode':'on','sampling_mode.temperature':0.7,'sampling_mode.top_k':64,'sampling_mode.top_p':0.95,'sampling_mode.min_p':0.05,'sampling_mode.repetition_penalty':1.05,'sampling_mode.seed':0,'sampling_mode.presence_penalty':0.0,'thinking':False,'use_default_template':True,'mtp':'off'}},
  '3':{'class_type':'N8VisionTextReturn','inputs':{'text':['2',0],'request_id':request_id}}
 }

def _translate_via_comfy(env:dict,text:str,target:str,stream_key:str,timeout:float=180.0)->str:
 source=_prompt_dialect(text)
 # Old checkpoint libraries may still contain P.70-era values such as `any`/`unknown`.
 # Those are not dialects and must never wake the translator. Translation is opt-in:
 # only a positively-known tags<->natural mismatch may create a TextGenerate job.
 target=str(target or '').strip().lower()
 if not text or target not in {'tags','natural'} or source=='hybrid' or source==target:return text
 cfg=_load_config();request_id=uuid.uuid4().hex
 with COMFY_TEXT_LOCK:COMFY_TEXT_STREAMS[request_id]={'request_id':request_id,'stream_key':stream_key,'source_dialect':source,'target_dialect':target,'text':'','status':'waiting','updated':time.time()}
 prompt=_translator_prompt(cfg,text,source,target,request_id);base=env['api_url'].rstrip('/')
 import urllib.request,urllib.error
 body=json.dumps({'prompt':prompt,'client_id':'n8vision-text'}).encode();rq=urllib.request.Request(base+'/prompt',data=body,headers={'Content-Type':'application/json'},method='POST')
 try:
  with urllib.request.urlopen(rq,timeout=15) as r:ans=json.loads(r.read().decode())
 except urllib.error.HTTPError as e:raise RuntimeError(f"Comfy rejected prompt translation: HTTP {e.code}\n{e.read().decode(errors='replace')}") from e
 pid=str(ans.get('prompt_id') or '')
 with COMFY_TEXT_LOCK:
  st=COMFY_TEXT_STREAMS[request_id];st['prompt_id']=pid;st['status']='waiting';COMFY_TEXT_PROMPTS[pid]=request_id;COMFY_TEXT_LOCK.notify_all()
  end=time.time()+timeout
  while st.get('status') not in {'complete','error'} and time.time()<end:COMFY_TEXT_LOCK.wait(timeout=min(1.0,max(.05,end-time.time())))
  if st.get('status')=='complete':return str(st.get('text') or text).strip() or text
  if st.get('status')=='error':raise RuntimeError(str(st.get('error') or 'Prompt translator failed.'))
  raise RuntimeError('Prompt translator timed out waiting for Comfy text return.')

class PromptPretranslateRequest(BaseModel):
 environment_id:str; items:list[dict[str,str]]=[]; target_dialect:str

@app.post('/api/refinement/pretranslate')
def refinement_pretranslate(req:PromptPretranslateRequest):
 env=_find_comfy_env(req.environment_id);target=str(req.target_dialect or '').lower()
 if target not in {'tags','natural'}:raise HTTPException(400,'Target prompt dialect must be tags or natural.')
 out=[]
 for item in req.items:
  path=str(item.get('path') or '');row={'path':path}
  for side in ('positive','negative'):
   text=str(item.get(side) or '');source=_prompt_dialect(text)
   row[side+'_source_dialect']=source
   row[side]=_translate_via_comfy(env,text,target,f'preflight:{Path(path).name}:{side}') if text and source in {'tags','natural'} and source!=target else text
  out.append(row)
 return {'ok':True,'target_dialect':target,'items':out}

class ComfyTextStreamRequest(BaseModel):
 environment_id:str|None=None; prompt_id:str|None=None; request_id:str|None=None; node_id:str|None=None; text:str=''; final:bool=False; error:str|None=None

@app.post('/api/comfy/text-stream')
def comfy_text_stream(req:ComfyTextStreamRequest):
 rid=str(req.request_id or '')
 with COMFY_TEXT_LOCK:
  if not rid and req.prompt_id:rid=COMFY_TEXT_PROMPTS.get(str(req.prompt_id),'')
  if not rid or rid not in COMFY_TEXT_STREAMS:return {'ok':True,'ignored':'text stream not owned by N8Vision'}
  st=COMFY_TEXT_STREAMS[rid]
  if req.text:st['text']=req.text;st['status']='receiving'
  if req.error:st['error']=req.error;st['status']='error'
  if req.final:st['status']='complete'
  st['updated']=time.time();COMFY_TEXT_LOCK.notify_all();return {'ok':True,'request_id':rid,'status':st['status']}

@app.get('/api/comfy/text-streams')
def comfy_text_streams():
 cutoff=time.time()-600
 with COMFY_TEXT_LOCK:
  return {'streams':[dict(v) for v in COMFY_TEXT_STREAMS.values() if float(v.get('updated',0))>=cutoff][-50:]}

@app.get('/api/comfy/text-stream/{request_id}')
def comfy_text_stream_get(request_id:str):
 with COMFY_TEXT_LOCK:
  st=COMFY_TEXT_STREAMS.get(request_id)
  if not st:raise HTTPException(404,'Unknown text stream')
  return dict(st)

class RefinementRecipeRequest(BaseModel):
 recipe:dict[str,Any]

@app.get('/api/refinement/recipe')
def refinement_recipe_get():
 return {'recipe':_load_config().get('refinement_recipe',{})}

@app.put('/api/refinement/recipe')
def refinement_recipe_put(req:RefinementRecipeRequest):
 cfg=_load_config();cfg['refinement_recipe']=req.recipe;_save_config(cfg);return {'ok':True,'recipe':req.recipe}

@app.delete('/api/refinement/recipe')
def refinement_recipe_delete():
 cfg=_load_config();cfg['refinement_recipe']={};_save_config(cfg);return {'ok':True,'recipe':{}}

class WorkshopFunctionRequest(BaseModel):
 function:dict[str,Any]

@app.get('/api/workshop/functions')
def workshop_functions_get():
 return {'functions':_load_config().get('workshop_functions',[])}

@app.put('/api/workshop/functions')
def workshop_functions_put(req:WorkshopFunctionRequest):
 cfg=_load_config();items=list(cfg.get('workshop_functions',[]));fn=dict(req.function)
 fid=str(fn.get('id') or uuid.uuid4().hex);fn['id']=fid
 items=[x for x in items if str(x.get('id'))!=fid];items.append(fn);cfg['workshop_functions']=items;_save_config(cfg)
 return {'ok':True,'function':fn,'functions':items}

@app.delete('/api/workshop/functions/{function_id}')
def workshop_functions_delete(function_id:str):
 cfg=_load_config();items=[x for x in cfg.get('workshop_functions',[]) if str(x.get('id'))!=function_id];cfg['workshop_functions']=items;_save_config(cfg);return {'ok':True,'functions':items}

@app.post('/api/refinement/metadata')
def refinement_metadata(req:Paths):
 items=[]
 for raw in req.paths:
  p=norm(raw)
  if p.is_file():items.append({'path':str(p),'name':p.name,'metadata':_generation_metadata(p)})
 return {'items':items}

def _checkpoint_dialect_from_comfy(row:dict)->dict:
    # Comfy owns architecture identification; N8Vision only maps that result to one of
    # the two useful conditioning dialects. There is no unknown/any execution dialect.
    hay=' '.join(str(row.get(k) or '') for k in ('checkpoint','comfy_model_config','clip_target','latent_format')).lower()
    if any(x in hay for x in ('flux','hunyuan','lumina','wan','qwen','kontext','klein')):
        return {'preferred':'natural','compatible':['natural','hybrid'],'confidence':'architecture','source':'comfy'}
    return {'preferred':'tags','compatible':['tags','hybrid'],'confidence':'conservative','source':'comfy'}

def _checkpoint_library_path()->Path:return DATA/'checkpoint_library.json'

def _read_checkpoint_library()->dict:
    return _read_json(_checkpoint_library_path(),{'version':1,'environment_id':'','updated':0,'checkpoints':{}})

@app.get('/api/comfy/checkpoint-library')
def checkpoint_library_get():return _read_checkpoint_library()

@app.post('/api/comfy/checkpoint-library/{env_id}/refresh')
def checkpoint_library_refresh(env_id:str):
    env=next((x for x in _load_envs().get('environments',[]) if x.get('id')==env_id),None)
    if not env or env.get('kind')!='comfy':raise HTTPException(404,'Comfy environment not found')
    if not _env_online(env):raise HTTPException(409,'Comfy is offline')
    base=str(env.get('api_url') or '').rstrip('/')
    import urllib.request
    try:
        with urllib.request.urlopen(base+'/n8vision/checkpoints/interrogate',timeout=3600) as r:raw=json.loads(r.read().decode('utf-8'))
    except Exception as e:raise HTTPException(502,f'Checkpoint interrogation failed: {e}')
    rows={}
    for row in raw.get('checkpoints',[]):
        name=str(row.get('checkpoint') or '')
        if not name:continue
        item=dict(row);item['dialect']=_checkpoint_dialect_from_comfy(item) if item.get('ok') else {'preferred':_target_prompt_dialect(name),'compatible':['tags','hybrid'] if _target_prompt_dialect(name)=='tags' else ['natural','hybrid'],'confidence':'filename-fallback','source':'n8vision'}
        rows[name]=item
    lib={'version':1,'environment_id':env_id,'updated':time.time(),'classifier':raw.get('classifier'),'bridge':raw.get('bridge'),'checkpoints':rows}
    _write_json(_checkpoint_library_path(),lib)
    cfg=_load_config();cfg['checkpoint_library']={'environment_id':env_id,'updated':lib['updated'],'count':len(rows),'file':str(_checkpoint_library_path())};_save_config(cfg)
    return lib

COMFY_TOOL_SHELF_PATH=DATA/'comfy_tool_shelves.json'
COMFY_TOOL_SHELF_LOCK=threading.RLock()

def _read_comfy_tool_shelves()->dict:
 with COMFY_TOOL_SHELF_LOCK:return _read_json(COMFY_TOOL_SHELF_PATH,{'version':1,'updated':0,'environments':{}})

def _write_comfy_tool_shelves(d:dict)->None:
 with COMFY_TOOL_SHELF_LOCK:_write_json(COMFY_TOOL_SHELF_PATH,d)

def _inspect_comfy_tool_shelf(env:dict,timeout:float=30.0)->dict:
 """Explicit shelf scan. Normal jobs consume the written inventory and never interrogate Comfy."""
 base=str(env.get('api_url') or '').rstrip('/')
 import urllib.request
 bridge_error=None
 try:
  started=time.monotonic()
  with urllib.request.urlopen(base+'/n8vision/tool-shelf',timeout=timeout) as r:data=json.loads(r.read().decode('utf-8'))
  data['inspection_source']='n8vision-bridge';data['inspection_seconds']=round(time.monotonic()-started,3)
 except Exception as e:
  bridge_error=str(e)
  try:
   started=time.monotonic()
   with urllib.request.urlopen(base+'/object_info',timeout=timeout) as r:raw=json.loads(r.read().decode('utf-8'))
   tools=[]
   for name,d in raw.items():
    if not isinstance(d,dict):continue
    tools.append({'type':name,'display_name':d.get('display_name') or name,'category':d.get('category',''),'inputs':d.get('input',{}),'outputs':d.get('output',[]),'output_names':d.get('output_name',[]),'output_node':bool(d.get('output_node',False))})
   data={'bridge':env.get('bridge'),'fallback':'object_info','agent_required':False,'install_dependencies':False,'tools':tools,
         'inspection_source':'object_info','inspection_seconds':round(time.monotonic()-started,3),'bridge_error':bridge_error}
  except Exception as e2:raise RuntimeError(f'Bridge shelf failed ({bridge_error}); Comfy object_info failed ({e2})')
 data['environment_id']=env.get('id');data['scanned']=time.time()
 cache=_read_comfy_tool_shelves();cache.setdefault('environments',{})[str(env.get('id'))]=data;cache['updated']=time.time();_write_comfy_tool_shelves(cache)
 LOG.info('Comfy Tool Shelf scanned: %s · %s tools · %.3fs via %s',env.get('name') or env.get('id'),len(data.get('tools',[])),data.get('inspection_seconds',0),data.get('inspection_source'))
 return data

def _scan_comfy_tool_shelf_once(env:dict):
 env_id=str(env.get('id') or '')
 if not env_id:return
 with COMFY_SHELF_SCAN_ONCE_LOCK:
  if env_id in COMFY_SHELF_SCANNED_THIS_RUN:return
  COMFY_SHELF_SCANNED_THIS_RUN.add(env_id)
 try:
  # A proclamation can arrive just before Comfy finishes binding all routes.
  time.sleep(.5)
  if not _env_online(env):raise RuntimeError('Comfy is offline')
  _inspect_comfy_tool_shelf(env)
 except Exception as e:
  with COMFY_SHELF_SCAN_ONCE_LOCK:COMFY_SHELF_SCANNED_THIS_RUN.discard(env_id)
  LOG.warning('Launch Tool Shelf scan skipped for %s: %s',env.get('name') or env_id,e)

def _startup_comfy_tool_shelf_scan():
 # Scan each known online Comfy once. A later Bridge proclamation covers the opposite launch order.
 time.sleep(2.0)
 for env in _load_envs().get('environments',[]):
  if env.get('kind')=='comfy' and _env_online(env):_scan_comfy_tool_shelf_once(env)

@app.get('/api/comfy/tool-shelf/{env_id}')
def comfy_tool_shelf(env_id:str):
 env=next((x for x in _load_envs().get('environments',[]) if x.get('id')==env_id),None)
 if not env or env.get('kind')!='comfy':raise HTTPException(404,'Comfy environment not found')
 data=_read_comfy_tool_shelves().get('environments',{}).get(env_id)
 if not data:raise HTTPException(409,'No cached Comfy Tool Shelf yet. Run Refresh Shelves once.')
 return data

@app.post('/api/comfy/tool-shelf/{env_id}/refresh')
def comfy_tool_shelf_refresh(env_id:str):
 env=next((x for x in _load_envs().get('environments',[]) if x.get('id')==env_id),None)
 if not env or env.get('kind')!='comfy':raise HTTPException(404,'Comfy environment not found')
 if not _env_online(env):raise HTTPException(409,'Comfy is offline')
 try:return _inspect_comfy_tool_shelf(env)
 except Exception as e:raise HTTPException(502,f'Could not inspect Comfy Tool Shelf: {e}')

class ExternalPrepareRequest(BaseModel):
 environment_id:str; workflow:str; paths:list[str]
class RegionChoice(BaseModel):
 path:str; geometry:str; queued:bool=True
class ExternalDispatchRequest(BaseModel):
 environment_id:str; workflow:str; paths:list[str]; regions:list[RegionChoice]=[]; positive:str=''; negative:str=''

def _replace_token(obj,token,value):
 if isinstance(obj,str):return obj.replace(token,value)
 if isinstance(obj,list):return [_replace_token(x,token,value) for x in obj]
 if isinstance(obj,dict):return {k:_replace_token(v,token,value) for k,v in obj.items()}
 return obj

def _workflow_tokens(path:Path):
 try: raw=path.read_text(encoding='utf-8')
 except Exception:return []
 return sorted(set(re.findall(r'\{\{N8VISION_[A-Z0-9_]+\}\}',raw)))

def _comfy_workflow_info(path:Path):
 """Describe a Comfy shelf workflow without requiring N8Vision placeholders."""
 try: obj=json.loads(path.read_text(encoding='utf-8'))
 except Exception:return {'format':'unknown','requires_mask':False,'bindings':{}}
 ui=isinstance(obj,dict) and isinstance(obj.get('nodes'),list)
 nodes=obj.get('nodes',[]) if ui else []
 bindings={}
 if ui:
  for n in nodes:
   typ=str(n.get('type','')); title=str(n.get('title',''))
   if typ=='LoadImage' and 'image' not in bindings:bindings['image']=n.get('id')
   if typ=='LoadImageMask' and 'mask' not in bindings:bindings['mask']=n.get('id')
   if typ in {'Power Prompt (rgthree)','PowerPrompt'} and 'positive' not in bindings:bindings['positive']=n.get('id')
   if typ=='CLIPTextEncode' and ('negative' in title.lower()) and 'negative' not in bindings:bindings['negative']=n.get('id')
 return {'format':'ui' if ui else 'api','requires_mask':bool(bindings.get('mask')) or '{{N8VISION_MASK}}' in _workflow_tokens(path),'bindings':bindings}

def _comfy_ui_to_api(doc:dict):
 """Convert Comfy's saved UI graph into the node dictionary accepted by /prompt.
 Keeps custom node class names intact; only graph wiring/widget serialization is translated.
 """
 if not (isinstance(doc,dict) and isinstance(doc.get('nodes'),list)):return doc.get('prompt',doc) if isinstance(doc,dict) else doc
 links={int(x[0]):x for x in doc.get('links',[]) if isinstance(x,list) and len(x)>=5}
 out={}
 controls={'fixed','increment','decrement','randomize'}
 for n in doc['nodes']:
  if not isinstance(n,dict) or n.get('mode')==4:continue
  vals=list(n.get('widgets_values') or []); vi=0; inputs={}
  for inp in n.get('inputs',[]) or []:
   name=inp.get('name'); lid=inp.get('link')
   if not name:continue
   if lid is not None and int(lid) in links:
    L=links[int(lid)];inputs[name]=[str(L[1]),int(L[2])];continue
   if inp.get('widget') is not None and vi<len(vals):
    inputs[name]=vals[vi];vi+=1
    # Comfy stores seed's control-after-generate choice as an extra UI widget value.
    if str(name).lower() in {'seed','noise_seed'} and vi<len(vals) and isinstance(vals[vi],str) and vals[vi].lower() in controls:vi+=1
  out[str(n['id'])]={'inputs':inputs,'class_type':n.get('type'),'_meta':{'title':n.get('title') or n.get('type')}}
 return out

def _bind_comfy_inputs(prompt:dict,info:dict,image_name:str,mask_name:str|None,positive:str,negative:str):
 b=info.get('bindings') or {}
 def node(k):return prompt.get(str(b.get(k))) if b.get(k) is not None else None
 if node('image') is not None:node('image').setdefault('inputs',{})['image']=image_name
 if mask_name and node('mask') is not None:
  node('mask').setdefault('inputs',{})['image']=mask_name
  node('mask')['inputs'].setdefault('channel','alpha')
 if node('positive') is not None:node('positive').setdefault('inputs',{})['prompt']=positive or ''
 if node('negative') is not None:node('negative').setdefault('inputs',{})['text']=negative or ''
 return prompt

def _validate_comfy_prompt(prompt:dict,requires_mask=False,mask_name=None):
 if not isinstance(prompt,dict) or not prompt:raise RuntimeError('Comfy preflight: converted prompt is empty or not an object.')
 bad=[k for k,v in prompt.items() if not isinstance(v,dict) or not v.get('class_type') or not isinstance(v.get('inputs'),dict)]
 if bad:raise RuntimeError('Comfy preflight: invalid API nodes: '+', '.join(map(str,bad[:12])))
 if requires_mask and not mask_name:raise RuntimeError('Comfy preflight: workflow requires a mask, but this work item has none.')

def _normalize_fooocus_metadata(meta:dict):
 """Normalize Fooocus image metadata into the generation fields Comfy can consume directly.

 The source block remains provenance: scheme/version select the dialect, while Fooocus-only
 controls (notably ADM guidance) stay intact instead of being guessed into generic Comfy inputs.
 """
 if not isinstance(meta,dict):return None
 scheme=str(meta.get('metadata_scheme','')).lower()
 version=str(meta.get('version',''))
 if scheme!='fooocus' and not version.lower().startswith('fooocus'):return None
 out={'scheme':'fooocus','version':str(meta.get('version') or ''),'positive':str(meta.get('full_prompt') or meta.get('prompt') or ''),'negative':str(meta.get('full_negative_prompt') or meta.get('negative_prompt') or meta.get('negative') or ''),'model':meta.get('base_model') or None,'model_hash':meta.get('base_model_hash') or None,'clip_skip':meta.get('clip_skip'),'cfg':meta.get('guidance_scale'),'seed':meta.get('seed'),'steps':meta.get('steps'),'sampler':meta.get('sampler'),'scheduler':meta.get('scheduler'),'denoise':meta.get('denoise'),'adm_guidance':meta.get('adm_guidance'),'loras':[]}
 ls=meta.get('loras') or meta.get('LoRAs') or []
 if isinstance(ls,list):
  for ent in ls:
   if isinstance(ent,(list,tuple)) and ent:
    item={'name':Path(str(ent[0])).stem,'source':'fooocus'}
    if len(ent)>1:item['weight']=str(ent[1])
    out['loras'].append(item)
   elif isinstance(ent,dict):
    n=ent.get('name') or ent.get('model')
    if n:
     item={'name':Path(str(n)).stem,'source':'fooocus'}
     if ent.get('weight') is not None:item['weight']=str(ent.get('weight'))
     out['loras'].append(item)
 claimed={'metadata_scheme','version','full_prompt','full_negative_prompt','base_model','base_model_hash','clip_skip','guidance_scale','seed','steps','sampler','scheduler','denoise','adm_guidance','loras','LoRAs'}
 # prompt/styles are deliberately retained as provenance, not graph instructions.
 out['provenance']={'prompt':meta.get('prompt'),'styles':meta.get('styles')}
 claimed.update({'prompt','styles','negative_prompt','negative'})
 out['unconsumed']={k:v for k,v in meta.items() if k not in claimed}
 return out

def _generation_metadata(path:Path):
 out={'positive':'','negative':'','loras':[],'seed':None,'model':None,'steps':None,'cfg':None,'sampler':None,'scheduler':None,'denoise':None,'raw_keys':[],'metadata_scheme':None,'metadata_version':None,'model_hash':None,'clip_skip':None,'adm_guidance':None,'unconsumed':{}}
 try:
  with Image.open(path) as im:
   info={str(k):v for k,v in (im.info or {}).items() if isinstance(v,(str,int,float))}
 except Exception:return out
 out['raw_keys']=sorted(info.keys())
 params=str(info.get('parameters','') or '')
 if params:
  neg='';pos=params
  if '\nNegative prompt:' in params:pos,rest=params.split('\nNegative prompt:',1);neg=rest
  else:rest=''
  # A1111/Fooocus tail begins at Steps. Keep negative text before it.
  if '\nSteps:' in neg:neg,tail=neg.split('\nSteps:',1);tail='Steps:'+tail
  elif '\nSteps:' in pos:pos,tail=pos.split('\nSteps:',1);tail='Steps:'+tail
  else:tail=''
  out['positive']=pos.strip();out['negative']=neg.strip()
  sm=re.search(r'(?:^|,\s*)Seed:\s*(\d+)',tail)
  if sm:out['seed']=int(sm.group(1))
  mm=re.search(r'(?:^|,\s*)Model:\s*([^,\n]+)',tail)
  if mm:out['model']=mm.group(1).strip()
 # Generator JSON may live in any PNG text chunk. Identify the dialect from the payload,
 # not from a historical container-key convention such as Comment/Description.
 metadata_objects=[]
 for key,raw in info.items():
  if not isinstance(raw,str) or not raw.lstrip().startswith('{'):continue
  try: meta=json.loads(raw)
  except Exception:continue
  if isinstance(meta,dict):metadata_objects.append((key,meta))
 # Fooocus is self-declaring. Prefer it before generic JSON so prompt payloads are assigned
 # positive/negative semantically instead of by text order.
 metadata_objects.sort(key=lambda kv:0 if str(kv[1].get('metadata_scheme','')).lower()=='fooocus' or str(kv[1].get('version','')).lower().startswith('fooocus') else 1)
 for key,meta in metadata_objects:
  foo=_normalize_fooocus_metadata(meta)
  if foo:
   out['metadata_scheme']=foo['scheme'];out['metadata_version']=foo['version'] or None
   for src,dst in (('positive','positive'),('negative','negative'),('model','model'),('model_hash','model_hash'),('clip_skip','clip_skip'),('cfg','cfg'),('seed','seed'),('steps','steps'),('sampler','sampler'),('scheduler','scheduler'),('denoise','denoise'),('adm_guidance','adm_guidance')):
    if foo.get(src) not in (None,''):out[dst]=foo[src]
   out['loras'].extend(x for x in foo['loras'] if x not in out['loras'])
   out['unconsumed']=foo['unconsumed']
   continue
  if not out['positive']:
   out['positive']=str(meta.get('prompt') or meta.get('positive_prompt') or '')
  if not out['negative']:
   out['negative']=str(meta.get('negative_prompt') or meta.get('negative') or '')
  ls=meta.get('loras') or meta.get('LoRAs') or []
  if isinstance(ls,list):
   for ent in ls:
    if isinstance(ent,(list,tuple)) and ent:
     item={'name':Path(str(ent[0])).stem,'source':'metadata'}
     if len(ent)>1:item['weight']=str(ent[1])
     out['loras'].append(item)
    elif isinstance(ent,dict):
     n=ent.get('name') or ent.get('model')
     if n:out['loras'].append({'name':Path(str(n)).stem,'source':'metadata','weight':str(ent.get('weight',''))})
 pj=info.get('prompt')
 if pj:
  try:
   obj=json.loads(pj) if isinstance(pj,str) else pj
   texts=[];loaded=[]
   if isinstance(obj,dict):
    for node in obj.values():
     if not isinstance(node,dict):continue
     ct=str(node.get('class_type',''));inp=node.get('inputs',{}) or {}
     if ct in {'CLIPTextEncode','Power Prompt (rgthree)','PowerPrompt'} and isinstance(inp.get('text'),str):texts.append(inp['text'])
     if 'Lora' in ct or 'LoRA' in ct:
      n=inp.get('lora_name')
      if isinstance(n,str):
       item={'name':Path(n).stem,'source':'node'}
       if inp.get('strength_model') is not None:item['model_strength']=inp.get('strength_model')
       if inp.get('strength_clip') is not None:item['clip_strength']=inp.get('strength_clip')
       out['loras'].append(item)
     if 'CheckpointLoader' in ct:
      n=inp.get('ckpt_name') or inp.get('checkpoint') or inp.get('model_name')
      if isinstance(n,str):out['model']=n
     if 'Sampler' in ct:
      for src,dst in (('seed','seed'),('noise_seed','seed'),('steps','steps'),('cfg','cfg'),('sampler_name','sampler'),('scheduler','scheduler'),('denoise','denoise')):
       if inp.get(src) is not None:out[dst]=inp.get(src)
   if texts and not out['positive']:out['positive']=texts[0]
   if len(texts)>1 and not out['negative']:out['negative']=texts[1]
   for n in loaded:
    if not any(x.get('name')==Path(n).stem for x in out['loras']):out['loras'].append({'name':Path(n).stem,'source':'node'})
  except Exception:pass
 # Declarations are executable provenance; leave them visible/editable in positive text.
 for field in ('positive','negative'):
  for name,weight in re.findall(r'<lora:([^:>]+)(?::([^>]+))?>',out[field],flags=re.I):
   item={'name':name.strip(),'source':'prompt'}
   if weight.strip():item['weight']=weight.strip()
   if item not in out['loras']:out['loras'].append(item)
 return out

def _region_rows(path:str):
 with db() as c:rows=c.execute("SELECT concept,confidence,provider,model,kind,geometry FROM observations WHERE path=? AND kind IN ('bbox','mask') AND geometry IS NOT NULL ORDER BY concept,confidence DESC",(str(norm(path)),)).fetchall()
 return [dict(r) for r in rows]

def _mask_for(src:Path,geometry_text:str,dest:Path):
 try:g=json.loads(geometry_text)
 except Exception as e:raise RuntimeError(f'Invalid stored geometry: {e}')
 with Image.open(src) as im:w,h=im.size
 mask=Image.new('L',(w,h),0)
 from PIL import ImageDraw
 d=ImageDraw.Draw(mask)
 if g.get('polygon'):
  pts=[(float(a),float(b)) for a,b in g['polygon']];d.polygon(pts,fill=255)
 elif g.get('rle') and g.get('size'):
  # SAM stores [start,end) runs over a row-major HxW mask.
  mh,mw=map(int,g['size']);small=Image.new('L',(mw,mh),0);pix=small.load()
  for a,b in g['rle']:
   for q in range(int(a),int(b)):pix[q%mw,q//mw]=255
  mask=small.resize((w,h),Image.Resampling.NEAREST) if (mw,mh)!=(w,h) else small
 elif g.get('bbox'):
  x1,y1,x2,y2=map(float,g['bbox']);d.rectangle((x1,y1,x2,y2),fill=255)
 else:raise RuntimeError('Geometry has no polygon, RLE mask, or bbox')
 mask.save(dest)

def _assert_workflow(env,workflow):
 wf=norm(workflow);allowed={x['path'] for x in _scan_workflows(env.get('workflow_dirs',[]))}
 if str(wf) not in allowed:raise HTTPException(403,'Workflow is not on this environment shelf')
 return wf

@app.post('/api/environments/prepare')
def environment_prepare(req:ExternalPrepareRequest):
 env=next((x for x in _load_envs().get('environments',[]) if x.get('id')==req.environment_id),None)
 if not env:raise HTTPException(404,'Unknown environment')
 wf=_assert_workflow(env,req.workflow);items=[]
 for raw in req.paths:
  p=norm(raw)
  if not image_file(p):continue
  items.append({'path':str(p),'name':p.name,'metadata':_generation_metadata(p),'regions':_region_rows(str(p))})
 info=_comfy_workflow_info(wf) if env.get('kind')=='comfy' else {'format':'unknown','requires_mask':False,'bindings':{}}
 return {'workflow':wf.stem,'tokens':_workflow_tokens(wf),'format':info['format'],'requires_mask':info['requires_mask'],'bindings':info['bindings'],'items':items}

def _comfy_batch(paths,env,workflow,regions=None,positive='',negative='',progress=None):
 import urllib.request,urllib.error
 root=norm(env.get('root') or '.');input_dir=root/'input';input_dir.mkdir(parents=True,exist_ok=True)
 wf_path=norm(workflow);template=json.loads(wf_path.read_text(encoding='utf-8'));info=_comfy_workflow_info(wf_path);base=env['api_url'].rstrip('/');results=[]
 choices=[r for r in (regions or []) if r.get('queued',True)]
 by_path={}
 for r in choices:by_path.setdefault(str(norm(r['path'])),[]).append(r)
 work=[]
 for raw in paths:
  src=norm(raw);rs=by_path.get(str(src),[])
  if info['requires_mask']:
   for r in rs:work.append((src,r))
  else:work.append((src,None))
 if not work:raise RuntimeError('Workflow requires a mask, but no regions are queued. Nothing was submitted to Comfy.')
 for i,(src,region) in enumerate(work,1):
  stem=f'N8Vision_{uuid.uuid4().hex[:8]}';img_name=f'{stem}_{src.name}';shutil.copy2(src,input_dir/img_name);mask_name=None
  if region:
   mask_name=f'{stem}_mask.png';_mask_for(src,region['geometry'],input_dir/mask_name)
  # Shelf files are normally Comfy UI graphs. Convert first, then bind ordinary node inputs.
  prompt=_comfy_ui_to_api(template)
  prompt=_replace_token(prompt,'{{N8VISION_IMAGE}}',img_name)
  if mask_name:prompt=_replace_token(prompt,'{{N8VISION_MASK}}',mask_name)
  prompt=_replace_token(prompt,'{{N8VISION_PROMPT}}',positive or '')
  prompt=_replace_token(prompt,'{{N8VISION_NEGATIVE}}',negative or '')
  prompt=_bind_comfy_inputs(prompt,info,img_name,mask_name,positive,negative)
  _validate_comfy_prompt(prompt,info['requires_mask'],mask_name)
  # Keep the exact last payload for diagnosis without making the normal log enormous.
  debug_dir=DATA/'debug';debug_dir.mkdir(parents=True,exist_ok=True);debug_file=debug_dir/'last_comfy_submission.json'
  debug_file.write_text(json.dumps({'prompt':prompt},indent=2,ensure_ascii=False),encoding='utf-8')
  body=json.dumps({'prompt':prompt}).encode('utf-8');rq=urllib.request.Request(base+'/prompt',data=body,headers={'Content-Type':'application/json'},method='POST')
  try:
   with urllib.request.urlopen(rq,timeout=15) as resp:submitted=json.loads(resp.read().decode('utf-8','replace'))
  except urllib.error.HTTPError as e:
   try:detail=e.read().decode('utf-8','replace')
   except Exception:detail='(Comfy returned no readable response body)'
   concept=region.get('concept') if region else '(whole image)'
   raise RuntimeError(f"Comfy rejected workflow {wf_path.stem} for {src.name} / {concept}\nHTTP {e.code} {e.reason}\nPayload: {debug_file}\nStaged image: {img_name}\nStaged mask: {mask_name or '(none)'}\n\n{detail}") from e
  except urllib.error.URLError as e:
   raise RuntimeError(f"Could not reach Comfy at {base}: {e.reason}") from e
  results.append({'source':str(src),'concept':region.get('concept') if region else None,'prompt_id':submitted.get('prompt_id')})
  if progress:progress(i,len(work))
 return {'submitted':results,'note':'Submitted to Comfy queue. Temporary masks live in Comfy input; N8Vision preserves prompt IDs.'}

@app.post('/api/environments/dispatch')
def environment_dispatch(req:ExternalDispatchRequest):
 env=next((x for x in _load_envs().get('environments',[]) if x.get('id')==req.environment_id),None)
 if not env:raise HTTPException(404,'Unknown environment')
 if not req.paths:raise HTTPException(400,'No images staged')
 wf=_assert_workflow(env,req.workflow)
 if env.get('kind')=='comfy':
  regs=[r.model_dump() for r in req.regions]
  # attach concepts for job receipts without trusting client geometry for semantics
  for r in regs:
   try:
    g=r['geometry'];match=next((x for x in _region_rows(r['path']) if x['geometry']==g),None)
    if match:r['concept']=match['concept']
   except Exception:pass
  return start_job(f"external:{env.get('name','Comfy')}:{wf.stem}",_comfy_batch,req.paths,env,str(wf),regs,req.positive,req.negative)
 raise HTTPException(501,f"Dispatch adapter not implemented for {env.get('kind')}; shelf discovery is working.")


# --- P.56 deterministic single-stage refinement recipe executor ---
class RefinementDispatchRequest(BaseModel):
 environment_id:str; recipe:dict[str,Any]; paths:list[str]; model:str=''; positive:str=''; negative:str=''; seed:int=0; source_steps:int=0; refinement_steps:int=10; cfg:float=8.0; sampler:str=''; scheduler:str=''; loras:list[dict[str,Any]]=[]; destination:str='comfy'; prompt_mode:str='per_image_metadata'; translated_prompts:dict[str,dict[str,str]]={}

def _recipe_inputs(role):
 d=role.get('inputs',{}) if isinstance(role,dict) else {};return {**(d.get('required',{}) or {}),**(d.get('optional',{}) or {})}
def _spec_type(spec):return spec[0] if isinstance(spec,list) and spec else spec
def _default_inputs(role):
 out={}
 for name,spec in _recipe_inputs(role).items():
  if not isinstance(spec,list) or not spec:continue
  typ=spec[0];cfg=spec[1] if len(spec)>1 and isinstance(spec[1],dict) else {}
  if isinstance(typ,list):out[name]=cfg.get('default',typ[0] if typ else '')
  elif typ in ('INT','FLOAT','STRING','BOOLEAN'):
   out[name]=cfg.get('default',0 if typ in ('INT','FLOAT') else (False if typ=='BOOLEAN' else ''))
 return out
def _input_name(role,typ,preferred=()):
 ins=_recipe_inputs(role)
 for n in preferred:
  if n in ins and _spec_type(ins[n])==typ:return n
 for n,s in ins.items():
  if _spec_type(s)==typ:return n
 return None
def _output_index(role,typ):
 outs=role.get('outputs',[]) or []
 try:return [str(x) for x in outs].index(typ)
 except ValueError:raise RuntimeError(f"{role.get('type')} does not provide {typ}")
def _set_widget(inp,role,value,names):
 allin=_recipe_inputs(role)
 for n in names:
  if n in allin:inp[n]=value;return n
 return None

def _refinement_prompt(recipe,source_name,req,output_prefix='N8Vision/Refinement'):
 roles=recipe.get('roles',{});needed=('source','checkpoint','lora','encode','text','sampler','decode','output')
 if any(k not in roles for k in needed):raise RuntimeError('Refinement recipe is incomplete. Create a new graph.')
 prompt={};seq=0
 def add(rolekey):
  nonlocal seq;seq+=1;r=roles[rolekey];nid=str(seq);prompt[nid]={'class_type':r['type'],'inputs':_default_inputs(r)};return nid,r,prompt[nid]['inputs']
 src,sr,si=add('source')
 # First experiment intentionally requires an image/path widget. Tool Shelf discovery may show broader IMAGE producers,
 # but an unbindable source is rejected rather than guessed at.
 if not _set_widget(si,sr,source_name,('image','filename','file','path')):raise RuntimeError(f"Selected image source {sr['type']} has no bindable image/file/path widget. Create a new graph and choose a source that accepts a staged image.")
 ck,cr,ci=add('checkpoint');_set_widget(ci,cr,req.model,('ckpt_name','checkpoint','model_name','model'))
 model=[ck,_output_index(cr,'MODEL')];clip=[ck,_output_index(cr,'CLIP')];vae=[ck,_output_index(cr,'VAE')]
 for ent in req.loras:
  lid,lr,li=add('lora');mn=_input_name(lr,'MODEL',('model',));cn=_input_name(lr,'CLIP',('clip',));
  if not mn or not cn:raise RuntimeError(f"LoRA tool {lr['type']} lost MODEL/CLIP sockets")
  li[mn]=model;li[cn]=clip;_set_widget(li,lr,ent.get('name',''),('lora_name','lora','name'));_set_widget(li,lr,float(ent.get('model_strength',1)),('strength_model','model_strength','strength'));_set_widget(li,lr,float(ent.get('clip_strength',1)),('strength_clip','clip_strength'))
  model=[lid,_output_index(lr,'MODEL')];clip=[lid,_output_index(lr,'CLIP')]
 enc,er,ei=add('encode');ei[_input_name(er,'IMAGE',('pixels','images','image'))]=[src,_output_index(sr,'IMAGE')];ei[_input_name(er,'VAE',('vae',))]=vae;latent=[enc,_output_index(er,'LATENT')]
 cond=[]
 for text in (req.positive,req.negative):
  tid,tr,ti=add('text');ti[_input_name(tr,'CLIP',('clip',))]=clip;_set_widget(ti,tr,text,('text','prompt','string'));cond.append([tid,_output_index(tr,'CONDITIONING')])
 sam,sar,sai=add('sampler');sai[_input_name(sar,'MODEL',('model',))]=model
 # CONDITIONING is intentionally named here because positive/negative are semantically distinct despite identical types.
 pin=_input_name(sar,'CONDITIONING',('positive',));nin=next((n for n,s in _recipe_inputs(sar).items() if _spec_type(s)=='CONDITIONING' and n!=pin),None)
 if not pin or not nin:raise RuntimeError(f"Sampler {sar['type']} does not expose distinguishable positive/negative CONDITIONING inputs")
 sai[pin]=cond[0];sai[nin]=cond[1];sai[_input_name(sar,'LATENT',('latent_image','samples','latent'))]=latent
 # P.62 salvage refinery: continue from the source's known diffusion history without injecting fresh noise.
 source_steps=max(0,int(req.source_steps));refinement_steps=max(1,int(req.refinement_steps));total_steps=source_steps+refinement_steps
 _set_widget(sai,sar,int(req.seed),('seed','noise_seed'));_set_widget(sai,sar,total_steps,('steps',));_set_widget(sai,sar,float(req.cfg),('cfg','cfg_scale'));_set_widget(sai,sar,req.sampler,('sampler_name','sampler'));_set_widget(sai,sar,req.scheduler,('scheduler',))
 # This recipe deliberately requires Advanced-sampler controls. A conventional denoise input is a different future graph.
 if _set_widget(sai,sar,'disable',('add_noise',)) is None:raise RuntimeError(f"Sampler {sar['type']} has no add_noise control. Choose KSampler (Advanced) for the salvage refinery.")
 if _set_widget(sai,sar,source_steps,('start_at_step',)) is None:raise RuntimeError(f"Sampler {sar['type']} has no start_at_step control. Choose KSampler (Advanced) for the salvage refinery.")
 if _set_widget(sai,sar,total_steps,('end_at_step',)) is None:raise RuntimeError(f"Sampler {sar['type']} has no end_at_step control. Choose KSampler (Advanced) for the salvage refinery.")
 _set_widget(sai,sar,'disable',('return_with_leftover_noise',))
 lat2=[sam,_output_index(sar,'LATENT')]
 dec,dr,di=add('decode');di[_input_name(dr,'LATENT',('samples','latent'))]=lat2;di[_input_name(dr,'VAE',('vae',))]=vae
 # P.80 Bellringer: transparent IMAGE passthrough immediately before whatever SaveImage the recipe owns.
 seq+=1;bell=str(seq);prompt[bell]={'class_type':'N8VisionBellringer','inputs':{'image':[dec,_output_index(dr,'IMAGE')],'recovery_id':Path(output_prefix).name}}
 out,orr,oi=add('output');oi[_input_name(orr,'IMAGE',('images','image'))]=[bell,0];_set_widget(oi,orr,output_prefix,('filename_prefix','prefix'))
 return prompt

def _refinement_batch(reqdict,progress=None):
 import urllib.request,urllib.error,shutil
 req=RefinementDispatchRequest(**reqdict);env=_find_comfy_env(req.environment_id);root=norm(env.get('root') or '.');input_dir=root/'input';input_dir.mkdir(parents=True,exist_ok=True);base=env['api_url'].rstrip('/');submitted=[]
 batch_id=str(reqdict.get('_n8_batch_id') or uuid.uuid4().hex[:12]);batch_sources=[str(norm(x)) for x in req.paths if image_file(norm(x))]
 if req.destination in {'beside','replace'}:
  with OUTPUT_RECOVERY_LOCK:COMFY_RECOVERY_BATCHES[batch_id]={'id':batch_id,'kind':'refinement','total':len(batch_sources),'terminal':0,'recovered':0,'failed':0,'sources':batch_sources,'targets':[],'complete':False,'updated':time.time()}
 total=max(1,len(req.paths))
 for i,raw in enumerate(req.paths):
  src=norm(raw)
  if not image_file(src):continue
  rel=Path('N8Vision')/'refinement'/f'{uuid.uuid4().hex[:10]}_{src.name}';dest=input_dir/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
  # Batch runs share one wizard/model/LoRA setup, but sequential items recover their own CLIP text.
  # Metadata-less/raw images inherit the wizard prompt, so a raw batch naturally uses one shared prompt.
  item_req=req.model_copy(deep=True)
  if req.prompt_mode=='per_image_metadata':
   meta=_generation_metadata(src)
   item_req=req.model_copy(deep=True)
   item_req.positive=str(meta.get('positive') or req.positive or '')
   item_req.negative=str(meta.get('negative') or req.negative or '')
   # Refinement history belongs to the image, not the batch. Raw images retain the wizard fallback (normally zero).
   if meta.get('steps') is not None:
    try:item_req.source_steps=max(0,int(meta.get('steps')))
    except (TypeError,ValueError):pass
  # P.71: the selected checkpoint owns its dialect. The recipe name does not.
  # Prefer the one-time Comfy interrogation library; filename heuristics are only a fallback for uncatalogued models.
  lib=_read_checkpoint_library(); row=None
  wanted=str(item_req.model or '').replace('\\','/').lower(); wanted_base=wanted.rsplit('/',1)[-1]
  for ck_name,ck_row in (lib.get('checkpoints',{}) or {}).items():
   n=str(ck_name or '').replace('\\','/').lower()
   if n==wanted or n.rsplit('/',1)[-1]==wanted_base:
    row=ck_row;break
  # Never trust a persisted P.70/P.71 dialect value blindly: libraries survive upgrades.
  # Reinterpret the stored Comfy interrogation through the current binary policy so
  # stale `any`/`unknown` values cannot manufacture a translation job.
  if row:
   target_dialect=str((_checkpoint_dialect_from_comfy(row) or {}).get('preferred') or _target_prompt_dialect(item_req.model))
  else:
   target_dialect=_target_prompt_dialect(item_req.model)
  # Metadata prompts already have a known generation dialect when their source model is recorded.
  # That evidence outranks syntax guessing: a Pony-authored prompt going to a Pony/tag target is
  # already valid even if style expansion made the text look sentence-like. Do not even call the
  # translator gate in that case, so no translator model can be loaded accidentally.
  source_model=str(meta.get('model') or '') if req.prompt_mode=='per_image_metadata' else ''
  source_dialect=_target_prompt_dialect(source_model) if source_model else None
  # Translation is a PRE-LAUNCH wizard action. Execute is forbidden from waking TextGenerate.
  # Consume only translations explicitly completed and supplied by the UI.
  prepared=(req.translated_prompts or {}).get(str(src),{}) or {}
  if prepared.get('positive'):item_req.positive=str(prepared['positive'])
  if prepared.get('negative'):item_req.negative=str(prepared['negative'])
  # Name the Comfy asset before generation. SaveImage may append its own counter, but this job token makes the prefix unique.
  job_token=uuid.uuid4().hex
  output_prefix=f"N8Vision/{src.stem}_{_method_slug(req.recipe.get('name') or 'Refine')}_{job_token}"
  prompt=_refinement_prompt(req.recipe,str(rel).replace('\\','/'),item_req,output_prefix)
  body=json.dumps({'prompt':prompt,'client_id':'n8vision-refinement'}).encode();request=urllib.request.Request(base+'/prompt',data=body,headers={'Content-Type':'application/json'},method='POST')
  try:
   with urllib.request.urlopen(request,timeout=15) as r:ans=json.loads(r.read().decode())
  except urllib.error.HTTPError as e:raise RuntimeError(f"Comfy rejected refinement for {src.name}: HTTP {e.code}\n{e.read().decode(errors='replace')}") from e
  pid=ans.get('prompt_id')
  submitted.append({'source':str(src),'prompt_id':pid,'destination':req.destination,'staged':str(dest),'prompt_source':'image metadata' if req.prompt_mode=='per_image_metadata' and (item_req.positive!=req.positive or item_req.negative!=req.negative) else 'wizard fallback'})
  if pid and req.destination in {'beside','replace'}:
   _arm_comfy_output_recovery(pid,{'source':str(src),'destination':req.destination,'method':str(req.recipe.get('name') or 'Refine'),'environment_id':req.environment_id,'output_prefix':output_prefix,'job_token':job_token,'iteration':0,'batch_id':batch_id})
  if progress:progress(i+1,total)
 return {'submitted':submitted,'destination':req.destination,'batch_mode':'sequential','prompt_mode':req.prompt_mode,'note':'Queued sequentially in Comfy from one setup. Each generated image uses its own recovered CLIP text when present; metadata-less images use the wizard prompt. Beside/Replace outputs are recovered when the Comfy bridge reports output ready.'}

class ComfyOutputReadyRequest(BaseModel):
 environment_id:str|None=None; prompt_id:str|None=None; outputs:list[dict[str,Any]]=[]

def _reported_comfy_output(env,outputs,expected_prefix):
 root=_comfy_output_root(env);cfg=_load_config();sub=str(cfg.get('comfy_output_subfolder') or 'N8Vision').strip('/\\')
 allowed=(root/sub).resolve();expected=Path(str(expected_prefix)).name
 matches=[]
 # Deterministic recovery only: trust the asset Comfy reports for this owned prompt, then verify it matches our preassigned unique prefix.
 for item in outputs or []:
  name=str(item.get('filename') or '');folder=str(item.get('subfolder') or '')
  if not name or not Path(name).stem.startswith(expected):continue
  try:
   # N8Vision Bridge resolves the target through Comfy's own folder_paths.
   # Older bridges fall back to the proclaimed output root.
   q=Path(str(item.get('target'))).resolve() if item.get('target') else (root/folder/name).resolve()
   if q.is_file() and (q==allowed or allowed in q.parents):matches.append(q)
  except OSError:pass
 if not matches:return None
 if len(matches)>1:raise RuntimeError(f'Comfy reported multiple assets matching unique output prefix {expected_prefix}')
 return matches[0]

def _method_slug(name):
 s=re.sub(r'[^A-Za-z0-9._-]+','-',str(name or 'Process')).strip('-_.')
 return s or 'Process'

def _recover_comfy_asset(pending,env,outputs):
 src=norm(pending['source']);fresh=_reported_comfy_output(env,outputs,pending.get('output_prefix',''))
 if fresh is None:raise RuntimeError(f"Comfy reported output ready, but did not report the asset assigned to this job ({pending.get('output_prefix')}).")
 if not src.parent.exists():raise RuntimeError(f'Source folder disappeared before output recovery: {src.parent}')
 mode=pending.get('destination')
 if mode=='replace':
  if src.exists():send2trash(str(src))
  target=src
 else:
  method=_method_slug(pending.get('method'));base=f'{src.stem}_{method}';ext=fresh.suffix or src.suffix
  target=src.parent/f'{base}{ext}';iteration=1
  while target.exists():
   iteration+=1;target=src.parent/f'{base}_{iteration}{ext}'
  pending['iteration']=iteration
 # shutil.move is deliberate: recovered Comfy assets leave the output staging tree.
 shutil.move(str(fresh),str(target))
 return target

def _history_output_rows(doc,prompt_id):
 entry=(doc or {}).get(str(prompt_id)) or (doc or {}).get(prompt_id) or {}
 rows=[]
 for out in (entry.get('outputs') or {}).values():
  if not isinstance(out,dict):continue
  for key in ('images','gifs'):
   for item in out.get(key,[]) or []:
    if isinstance(item,dict) and item.get('filename'):
     rows.append({'filename':item.get('filename'),'subfolder':item.get('subfolder') or '','type':item.get('type') or 'output'})
 return rows

def _finish_comfy_recovery(pending,ok,target=None,error=None):
 batch_id=str(pending.get('batch_id') or '')
 if not batch_id:return
 with OUTPUT_RECOVERY_LOCK:
  b=COMFY_RECOVERY_BATCHES.get(batch_id)
  if not b:return
  b['terminal']=int(b.get('terminal',0))+1
  if ok:
   b['recovered']=int(b.get('recovered',0))+1
   if target:b.setdefault('targets',[]).append(str(target))
  else:
   b['failed']=int(b.get('failed',0))+1
   if error:b.setdefault('errors',[]).append(str(error))
  b['updated']=time.time();b['complete']=b['terminal']>=b['total']
  job=JOBS.get(batch_id)
  if job:
   job.update(done=int(b['terminal']),total=int(b['total']),phase='recovering',updated=time.time())
   if b['complete']:
    job.update(state='done',phase='complete',result={**(job.get('result') or {}),'recovery':dict(b)})
   elif job.get('state') not in {'error','stopped'}:job['state']='recovering'
  if b['complete']:LOG.info('Comfy batch %s complete: %s recovered, %s failed',batch_id,b['recovered'],b['failed'])
  _write_active_job_journal()

@app.get('/api/comfy/recovery-batch/{batch_id}')
def comfy_recovery_batch(batch_id:str):
 with OUTPUT_RECOVERY_LOCK:
  b=COMFY_RECOVERY_BATCHES.get(str(batch_id))
  if not b:raise HTTPException(404,'Recovery batch not found')
  job=JOBS.get(str(batch_id),{})
  if job.get('state') in {'error','stopped'} and not b.get('complete'):
   missing=max(0,int(b.get('total',0))-int(b.get('terminal',0)));b['failed']=int(b.get('failed',0))+missing;b['terminal']=int(b.get('total',0));b['complete']=True;b['updated']=time.time()
   if job.get('error'):b.setdefault('errors',[]).append(str(job.get('error')))
  return dict(b)

class ViewRefreshRequest(BaseModel):
 roots:list[str]=[];recursive:bool=False

@app.post('/api/view-refresh')
def view_refresh(req:ViewRefreshRequest):
 records=[];seen=set()
 for raw in req.roots:
  p=norm(raw)
  if not p.exists() or not p.is_dir():continue
  try:it=p.rglob('*') if req.recursive else p.iterdir()
  except (PermissionError,OSError):continue
  for x in it:
   if not image_file(x):continue
   try:key=str(x.resolve()).casefold()
   except OSError:continue
   if key in seen:continue
   seen.add(key)
   try:st=x.stat()
   except (FileNotFoundError,PermissionError,OSError):continue
   records.append({'name':x.name,'path':str(x),'size':st.st_size,'mtime':st.st_mtime})
 obs=obs_for([x['path'] for x in records])
 for x in records:x['observations']=obs.get(x['path'],[])
 return {'files':records,'roots':req.roots,'recursive':req.recursive}

def _watch_comfy_output(prompt_id):
 """P.84 server-side output recovery. Browser events are hints, not the transport contract."""
 import urllib.request
 pid=str(prompt_id or '')
 if not pid:return
 # Long enough for real refinement/upscale jobs; cheap polling against local Comfy history.
 for _ in range(1800):
  with OUTPUT_RECOVERY_LOCK:pending=PENDING_COMFY_OUTPUTS.get(pid)
  if not pending:return
  try:
   env=_find_comfy_env(pending.get('environment_id'));base=str(env.get('api_url') or '').rstrip('/')
   if base:
    with urllib.request.urlopen(base+'/history/'+urllib.parse.quote(pid,safe=''),timeout=3.0) as r:doc=json.loads(r.read().decode('utf-8','replace') or '{}')
    outputs=_history_output_rows(doc,pid)
    if outputs:
     target=_recover_comfy_asset(pending,env,outputs)
     with OUTPUT_RECOVERY_LOCK:PENDING_COMFY_OUTPUTS.pop(pid,None)
     LOG.info('Comfy refinement complete; output recovered server-side: %s -> %s',pid,target)
     _finish_comfy_recovery(pending,True,target=target)
     return
  except Exception as e:
   # History is empty while a prompt is running. Real recovery errors are retried because filesystem visibility can lag history.
   pass
  time.sleep(1.0)
 with OUTPUT_RECOVERY_LOCK:PENDING_COMFY_OUTPUTS.pop(pid,None)
 _finish_comfy_recovery(pending,False,error='output recovery timed out')
 LOG.warning('Comfy output recovery watcher timed out for prompt %s',pid)

def _arm_comfy_output_recovery(prompt_id,pending):
 pid=str(prompt_id or '')
 if not pid:return
 with OUTPUT_RECOVERY_LOCK:PENDING_COMFY_OUTPUTS[pid]=pending
 threading.Thread(target=_watch_comfy_output,args=(pid,),name=f'n8vision-output-{pid[:8]}',daemon=True).start()

@app.post('/api/comfy/output-ready')
def comfy_output_ready(req:ComfyOutputReadyRequest):
 pid=str(req.prompt_id or '')
 if not pid:return {'ok':True,'ignored':'no prompt id'}
 with OUTPUT_RECOVERY_LOCK:pending=PENDING_COMFY_OUTPUTS.pop(pid,None)
 if not pending:return {'ok':True,'ignored':'prompt not owned by an N8Vision recovery job'}
 try:
  env=_find_comfy_env(pending.get('environment_id') or req.environment_id);target=_recover_comfy_asset(pending,env,req.outputs)
  _finish_comfy_recovery(pending,True,target=target)
  return {'ok':True,'recovered':str(target),'mode':pending.get('destination'),'source':pending.get('source')}
 except Exception:
  # Keep it retryable if the bridge beat filesystem visibility by a moment.
  with OUTPUT_RECOVERY_LOCK:PENDING_COMFY_OUTPUTS[pid]=pending
  raise

@app.post('/api/refinement/dispatch')
def refinement_dispatch(req:RefinementDispatchRequest):
 if req.destination not in {'beside','replace','comfy'}:raise HTTPException(400,'Unknown refinement destination')
 # Recipe from persistent config is authoritative; do not accept topology smuggled in per-run.
 saved=_load_config().get('refinement_recipe',{})
 if not saved or saved.get('roles')!=req.recipe.get('roles'):raise HTTPException(409,'Refinement recipe changed. Reopen Refine SDXL.')
 payload=req.model_dump();payload['recipe']=saved
 return start_job('comfy:refinement',_refinement_batch,payload)

# --- P.73 Workshop executable compiler ---
class WorkshopDispatchRequest(BaseModel):
 function_id:str; paths:list[str]; model:str=''; positive:str=''; negative:str=''; destination:str='beside'

def _ws_required(role):
 ins=role.get('inputs') or {}; return (ins.get('required') or {}) if isinstance(ins,dict) else {}
def _ws_optional(role):
 ins=role.get('inputs') or {}; return (ins.get('optional') or {}) if isinstance(ins,dict) else {}
def _ws_spec_type(spec):
 if isinstance(spec,(list,tuple)) and spec:return spec[0] if isinstance(spec[0],str) else None
 return spec if isinstance(spec,str) else None
def _ws_defaults(role):
 out={}
 for n,s in {**_ws_required(role),**_ws_optional(role)}.items():
  typ=_ws_spec_type(s); cfg=s[1] if isinstance(s,(list,tuple)) and len(s)>1 and isinstance(s[1],dict) else {}
  if isinstance(s,(list,tuple)) and s and isinstance(s[0],list):out[n]=cfg.get('default',s[0][0] if s[0] else '')
  elif typ in ('INT','FLOAT','STRING','BOOLEAN'):
   out[n]=cfg.get('default',0 if typ in ('INT','FLOAT') else (False if typ=='BOOLEAN' else ''))
 return out

def _ws_tool(shelf,*names):
 tools=shelf.get('tools') or []
 for name in names:
  q=next((x for x in tools if x.get('type')==name),None)
  if q:return q
 return None

def _ws_compile(fn,shelf,image_name,model,positive,negative,output_prefix):
 """Compile a bound Workshop role-chain using Comfy's advertised socket shapes.
 Infrastructure is selected from the Tool Shelf; bound role nodes remain exactly what the user chose.
 """
 prompt={}; seq=0; pool=[]
 def add(role):
  nonlocal seq;seq+=1;nid=str(seq);prompt[nid]={'class_type':role['type'],'inputs':_ws_defaults(role)}
  for oi,typ in enumerate(role.get('outputs') or []):pool.append((str(typ),nid,oi,role.get('type')))
  return nid,prompt[nid]['inputs']
 def latest(typ,exclude=None):
  for t,n,i,k in reversed(pool):
   if t==typ and n!=exclude:return [n,i]
  return None
 # Image source is infrastructure, not a Workshop role.
 srcrole=_ws_tool(shelf,'LoadImage')
 if not srcrole:raise RuntimeError('Workshop compiler: Comfy Tool Shelf has no LoadImage node.')
 sid,si=add(srcrole);si['image']=image_name
 # Add a checkpoint loader only when downstream sockets need model/clip/vae infrastructure.
 bound=[r for key in (fn.get('grammar',{}).get('ordered') or []) if (r:=(fn.get('roles') or {}).get(key))]
 needtypes={_ws_spec_type(s) for r in bound for s in _ws_required(r).values()}
 ckrole=_ws_tool(shelf,'CheckpointLoaderSimple')
 if {'MODEL','CLIP','VAE'} & needtypes:
  if not ckrole:raise RuntimeError('Workshop compiler: graph needs MODEL/CLIP/VAE but Comfy exposes no CheckpointLoaderSimple.')
  cid,ci=add(ckrole)
  ckfield=next((n for n in _ws_required(ckrole) if n in ('ckpt_name','checkpoint','model_name','model')),None)
  if not ckfield:raise RuntimeError('Workshop compiler: checkpoint loader has no checkpoint selector.')
  ci[ckfield]=model
 # Text conditioning is infrastructure when a bound node asks directly for CONDITIONING.
 textrole=_ws_tool(shelf,'CLIPTextEncode')
 def make_text(text):
  if not textrole:return None
  tid,ti=add(textrole);clip=latest('CLIP',tid)
  if not clip:raise RuntimeError('Workshop compiler: text conditioning requested but no CLIP output is available.')
  cn=next((n for n,s in _ws_required(textrole).items() if _ws_spec_type(s)=='CLIP'),None);tn=next((n for n in _ws_required(textrole) if n in ('text','prompt','string')),None)
  if cn:ti[cn]=clip
  if tn:ti[tn]=text
  return [tid,next((i for i,t in enumerate(textrole.get('outputs') or []) if str(t)=='CONDITIONING'),0)]
 poscond=negcond=None
 # Compile the ordered bound roles. Required sockets are wired by advertised Comfy type.
 for role in bound:
  nid,inp=add(role); reqs=_ws_required(role)
  condnames=[n for n,s in reqs.items() if _ws_spec_type(s)=='CONDITIONING']
  for n,spec in reqs.items():
   typ=_ws_spec_type(spec)
   if typ=='CONDITIONING':
    if len(condnames)>1 or n.lower() in ('positive','negative'):
     if poscond is None:poscond=make_text(positive)
     if negcond is None:negcond=make_text(negative)
     inp[n]=negcond if ('neg' in n.lower() or (len(condnames)>1 and n==condnames[1])) else poscond
    else:
     link=latest('CONDITIONING',nid)
     if link:inp[n]=link
   elif typ and typ not in ('INT','FLOAT','STRING','BOOLEAN'):
    link=latest(typ,nid)
    if link:inp[n]=link
  missing=[n for n,s in reqs.items() if _ws_spec_type(s) not in ('INT','FLOAT','STRING','BOOLEAN') and n not in inp]
  if missing:raise RuntimeError(f"Workshop compiler: {role['type']} has unwired required inputs: {', '.join(missing)}")
 # Save whatever final IMAGE the chain produced.
 outrole=_ws_tool(shelf,'SaveImage')
 if not outrole:raise RuntimeError('Workshop compiler: Comfy Tool Shelf has no SaveImage node.')
 image=latest('IMAGE')
 if not image:raise RuntimeError('Workshop compiler: bound graph does not produce an IMAGE for SaveImage.')
 # P.80: Bellringer is deliberately not a Save node. It passes IMAGE unchanged so users remain free to use any saver.
 bid=str(len(prompt)+1);prompt[bid]={'class_type':'N8VisionBellringer','inputs':{'image':image,'recovery_id':Path(output_prefix).name}};image=[bid,0]
 oid,oi=add(outrole);imgn=next((n for n,s in _ws_required(outrole).items() if _ws_spec_type(s)=='IMAGE'),None) or 'images';oi[imgn]=image
 if 'filename_prefix' in {**_ws_required(outrole),**_ws_optional(outrole)}:oi['filename_prefix']=output_prefix
 return prompt

def _workshop_batch(reqdict,progress=None):
 import urllib.request,urllib.error,shutil
 req=WorkshopDispatchRequest(**reqdict);batch_id=str(reqdict.get('_n8_batch_id') or uuid.uuid4().hex[:12]);cfg=_load_config();fn=next((x for x in cfg.get('workshop_functions',[]) if str(x.get('id'))==req.function_id),None)
 if not fn:raise RuntimeError('Workshop function not found.')
 env=_find_comfy_env(fn.get('environment_id'));base=env['api_url'].rstrip('/');root=norm(env.get('root') or '.');input_dir=root/'input';input_dir.mkdir(parents=True,exist_ok=True)
 # P.89: Workshop consumes the launch/manual Tool Shelf snapshot. Running a function must
 # never turn into another full Comfy /object_info interrogation.
 shelf=_read_comfy_tool_shelves().get('environments',{}).get(str(env.get('id')))
 if not shelf:raise RuntimeError('Workshop Tool Shelf cache is empty. Use Refresh Shelves once, then retry.')
 submitted=[];total=max(1,len(req.paths))
 if req.destination in {'beside','replace'}:
  batch_sources=[str(norm(x)) for x in req.paths if image_file(norm(x))]
  with OUTPUT_RECOVERY_LOCK:COMFY_RECOVERY_BATCHES[batch_id]={'id':batch_id,'kind':'workshop','total':len(batch_sources),'terminal':0,'recovered':0,'failed':0,'sources':batch_sources,'targets':[],'complete':False,'updated':time.time()}
 for i,rawpath in enumerate(req.paths):
  src=norm(rawpath)
  if not image_file(src):continue
  rel=Path('N8Vision')/'workshop'/f'{uuid.uuid4().hex[:10]}_{src.name}';dest=input_dir/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
  meta=_generation_metadata(src);positive=str(meta.get('positive') or req.positive or '');negative=str(meta.get('negative') or req.negative or '')
  lib=_read_checkpoint_library();row=next((v for k,v in (lib.get('checkpoints') or {}).items() if str(k).replace('\\','/').lower().rsplit('/',1)[-1]==str(req.model).replace('\\','/').lower().rsplit('/',1)[-1]),None)
  dialect=str((_checkpoint_dialect_from_comfy(row) or {}).get('preferred') if row else _target_prompt_dialect(model));positive=_translate_via_comfy(env,positive,dialect,f'workshop:{src.name}:positive');negative=_translate_via_comfy(env,negative,dialect,f'workshop:{src.name}:negative')
  token=uuid.uuid4().hex;prefix=f"N8Vision/{src.stem}_{_method_slug(fn.get('name') or 'Workshop')}_{token}"
  graph=_ws_compile(fn,shelf,str(rel).replace('\\','/'),req.model,positive,negative,prefix);_validate_comfy_prompt(graph)
  body=json.dumps({'prompt':graph,'client_id':'n8vision-workshop'}).encode();rq=urllib.request.Request(base+'/prompt',data=body,headers={'Content-Type':'application/json'},method='POST')
  try:
   with urllib.request.urlopen(rq,timeout=20) as r:ans=json.loads(r.read().decode())
  except urllib.error.HTTPError as e:raise RuntimeError(f"Comfy rejected Workshop function {fn.get('name')} for {src.name}: HTTP {e.code}\n{e.read().decode(errors='replace')}") from e
  pid=ans.get('prompt_id');submitted.append({'source':str(src),'prompt_id':pid})
  if pid and req.destination in {'beside','replace'}:
   _arm_comfy_output_recovery(pid,{'source':str(src),'destination':req.destination,'method':str(fn.get('name') or 'Workshop'),'environment_id':fn.get('environment_id'),'output_prefix':prefix,'job_token':token,'iteration':0,'batch_id':batch_id})
  if progress:progress(i+1,total)
 return {'submitted':submitted,'function':fn.get('name'),'destination':req.destination}

@app.post('/api/workshop/dispatch')
def workshop_dispatch(req:WorkshopDispatchRequest):
 if req.destination not in {'beside','replace','comfy'}:raise HTTPException(400,'Unknown Workshop destination')
 if not req.paths:raise HTTPException(400,'No images selected')
 return start_job('comfy:workshop',_workshop_batch,req.model_dump())
