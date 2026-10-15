"""Standard-library-only launch identity; no image or model imports."""
import ctypes
import json
import os
from pathlib import Path
import socket
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

MESSAGE="Vision already running. Don't waste resources on trying to run it twice"

def instance_file():
 override=os.environ.get('N8VISION_INSTANCE_FILE')
 return Path(override) if override else Path(os.environ.get('LOCALAPPDATA',Path.home()))/'N8Vision'/'running-instance.json'

def local_url(url):
 try:
  p=urllib.parse.urlsplit(url)
  return p.scheme=='http' and p.hostname in ('127.0.0.1','localhost','::1') and not p.username and not p.password and (p.port or 80)>0 and p.path in ('','/') and not p.query and not p.fragment
 except ValueError:return False

def identify(url):
 if not local_url(url):return False
 try:
  with urllib.request.urlopen(url.rstrip('/')+'/api/instance',timeout=.7) as r:
   return json.load(r).get('program')=='N8Vision'
 except (OSError,ValueError,urllib.error.URLError):
  # Recognize an already-running pre-edition install without invoking GPU health.
  try:
   with urllib.request.urlopen(url,timeout=.7) as r:html=r.read(65536).decode('utf-8','replace')
   return '<title>N8Vision</title>' in html and '/static/app.js' in html
  except (OSError,urllib.error.URLError):return False

def running_url(default='http://127.0.0.1:8189'):
 try:
  url=json.loads(instance_file().read_text(encoding='utf-8')).get('url','')
  if identify(url):return url
 except (OSError,ValueError):pass
 for url in dict.fromkeys([default,'http://127.0.0.1:8189']):
  if identify(url):return url
 return None

class InstanceLock:
 def __init__(self,name='Global\\N8Vision.Server.Instance'):self.handle=None;self.socket=None;self.name=name
 def acquire(self):
  if os.name=='nt':
   api=ctypes.WinDLL('kernel32',use_last_error=True)
   api.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p];api.CreateMutexW.restype=ctypes.c_void_p
   api.CloseHandle.argtypes=[ctypes.c_void_p]
   handle=api.CreateMutexW(None,False,self.name)
   error=ctypes.get_last_error()
   if not handle:
    if error==5:return False
    raise OSError(error,'Cannot establish the N8Vision instance lock')
   if error==183:api.CloseHandle(handle);return False
   self.handle=handle;return True
  sock=socket.socket()
  try:sock.bind(('127.0.0.1',48189))
  except OSError:sock.close();return False
  self.socket=sock;return True
 def close(self):
  if self.handle:
   api=ctypes.WinDLL('kernel32',use_last_error=True);api.CloseHandle.argtypes=[ctypes.c_void_p];api.CloseHandle(self.handle);self.handle=None
  if self.socket:self.socket.close();self.socket=None

def announce(url,edition):
 p=instance_file();p.parent.mkdir(parents=True,exist_ok=True)
 temp=p.with_name(p.name+'.'+str(os.getpid())+'.tmp')
 temp.write_text(json.dumps({'program':'N8Vision','url':url,'pid':os.getpid(),'edition':edition}),encoding='utf-8');temp.replace(p)

def forget():
 p=instance_file()
 try:
  if json.loads(p.read_text(encoding='utf-8')).get('pid')==os.getpid():p.unlink(missing_ok=True)
 except (OSError,ValueError):pass

def find(url):
 if not local_url(url):return
 try:
  request=urllib.request.Request(url.rstrip('/')+'/api/instance/attention',data=b'{}',headers={'Content-Type':'application/json'},method='POST')
  urllib.request.urlopen(request,timeout=1).close()
 except OSError:pass
 webbrowser.open(url,new=0,autoraise=True)

def duplicate_dialog(url=None):
 try:
  import tkinter as tk
  root=tk.Tk();root.title('N8Vision');root.resizable(False,False)
  tk.Label(root,text=MESSAGE,wraplength=420,padx=20,pady=18).pack()
  buttons=tk.Frame(root);buttons.pack(pady=(0,16))
  tk.Button(buttons,text='Okay',width=12,command=root.destroy).pack(side='left',padx=8)
  def locate():
   target=url or running_url()
   if target:find(target)
   root.destroy()
  tk.Button(buttons,text='Find',width=12,command=locate).pack(side='left',padx=8)
  root.attributes('-topmost',True);root.mainloop()
 except Exception:
  print(MESSAGE)
  if url:print('Existing UI: '+url)
