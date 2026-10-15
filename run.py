from __future__ import annotations
import argparse
import threading
import webbrowser
import json
from pathlib import Path
import os
import subprocess
import shlex
import secrets
import hashlib
import time
from n8vision.profiles import default_edition,missing_modules
from urllib.request import urlopen


def open_when_ready(server,url,open_viewer,stop,probe=None):
    probe=probe or urlopen
    while not stop.is_set():
        if server.started:
            try:
                with probe(url,timeout=1) as response:
                    ready=response.status==200 and b'<title>N8Vision</title>' in response.read(65536)
                if ready and not stop.is_set():
                    open_viewer();return
            except Exception:
                pass
        stop.wait(.2)


def main():
    ap = argparse.ArgumentParser(description="N8Vision local visual file manager")
    ap.add_argument("--host", default=None, help="Override configured bind host")
    ap.add_argument("--port", type=int, default=8189)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--grid-detail", choices=["hover","diagnostic"], default=None, help="Grid observation display mode")
    ap.add_argument('--admin-code', action='store_true', help='Print one-time host authorization code (10 minutes), then exit')
    ap.add_argument('--edition',choices=['lite','blurred','full'],default=os.environ.get('N8VISION_EDITION') or default_edition(Path(__file__).parent))
    ap.add_argument('--instance-restart',action='store_true',help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.admin_code:
        code=secrets.token_urlsafe(24)
        target=Path(__file__).with_name('data')/'admin_bootstrap.json'
        target.parent.mkdir(parents=True,exist_ok=True)
        tmp=target.with_suffix('.tmp')
        tmp.write_text(json.dumps({'hash':hashlib.sha256(code.encode()).hexdigest(),'expires':time.time()+600}),encoding='utf-8')
        try:os.chmod(tmp,0o600)
        except OSError:pass
        tmp.replace(target)
        print('N8Vision host authorization code (expires in 10 minutes; one use):')
        print(code)
        print('Enter this code in Settings > Admin Credentials on the browser you want to promote.')
        return
    cfg_path=Path(__file__).with_name("data")/"n8vision_config.json"
    legacy_cfg_path=Path(__file__).with_name("n8vision_config.json")
    cfg={}
    try:
        read_path=cfg_path if cfg_path.exists() else legacy_cfg_path
        if read_path.exists(): cfg=json.loads(read_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[N8Vision] Config warning: {e}")
    from n8vision.instance import InstanceLock,running_url,duplicate_dialog,announce,forget
    url=f'http://127.0.0.1:{args.port}'
    lock=InstanceLock()
    deadline=time.monotonic()+(10 if args.instance_restart else 0)
    while True:
        existing=running_url(url)
        acquired=False if existing else lock.acquire()
        if acquired:break
        if args.instance_restart and time.monotonic()<deadline:
            time.sleep(.1);continue
        duplicate_dialog(existing or running_url(url));return
    missing=missing_modules(args.edition)
    if missing:
        lock.close();raise SystemExit(f'N8Vision {args.edition.title()} environment is incomplete: '+', '.join(missing)+f'. Run install-{args.edition.title()}.cmd.')
    os.environ['N8VISION_EDITION']=args.edition
    announce(url,args.edition)
    mode=args.grid_detail or cfg.get("grid_detail","hover")
    host=args.host or ("0.0.0.0" if bool(cfg.get("enable_lan",False)) else "127.0.0.1")
    if mode not in {"hover","diagnostic"}: mode="hover"
    os.environ["N8VISION_GRID_DETAIL"]=mode
    print(f"[N8Vision] Grid detail: {mode}")
    os.environ["N8VISION_BIND_HOST"]=host
    os.environ["N8VISION_PORT"]=str(args.port)
    print(f"[N8Vision] Network: {'LAN enabled' if host == '0.0.0.0' else 'local only'} ({host}:{args.port})")
    viewer_stop=threading.Event()
    if not args.no_browser:
        url=f"http://127.0.0.1:{args.port}"
        target=str(cfg.get('viewer_target','system') or 'system').strip()
        def open_viewer():
            try:
                if target.lower()=='system':webbrowser.open(url)
                else:subprocess.Popen([target,url])
            except Exception as e:
                print(f'[N8Vision] Viewer target failed ({target}): {e}; falling back to system default')
                webbrowser.open(url)
    try:
        import uvicorn
        server=uvicorn.Server(uvicorn.Config("n8vision.app:app",host=host,port=args.port,reload=False,access_log=False))
        if not args.no_browser:
            threading.Thread(target=open_when_ready,args=(server,url,open_viewer,viewer_stop),name='n8vision-browser-ready',daemon=True).start()
        server.run()
    finally:
        viewer_stop.set()
        forget();lock.close()

if __name__ == "__main__":
    main()
