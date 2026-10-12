"""Tiny opt-in proclamation helper for Python-based image environments.
Edit the declaration below, then import/call proclaim() during host startup.
No N8Vision package dependency; failure is intentionally harmless.
"""
import json, urllib.request
N8VISION='http://127.0.0.1:8189'
DECLARATION={
 'name':'My Image Environment','kind':'generic','root':None,
 'api_url':None,'workflow_dirs':[],'start_command':None,
}
def proclaim(declaration=None):
 data=json.dumps(declaration or DECLARATION).encode('utf-8')
 req=urllib.request.Request(N8VISION+'/api/environments/proclaim',data=data,headers={'Content-Type':'application/json'},method='POST')
 try:
  with urllib.request.urlopen(req,timeout=.5) as r:return r.status<300
 except Exception:return False
