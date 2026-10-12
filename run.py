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
import uvicorn


def main():
    ap = argparse.ArgumentParser(description="N8Vision local visual file manager")
    ap.add_argument("--host", default=None, help="Override configured bind host")
    ap.add_argument("--port", type=int, default=8189)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--grid-detail", choices=["hover","diagnostic"], default=None, help="Grid observation display mode")
    ap.add_argument('--admin-code', action='store_true', help='Print one-time host authorization code (10 minutes), then exit')
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
    mode=args.grid_detail or cfg.get("grid_detail","hover")
    host=args.host or ("0.0.0.0" if bool(cfg.get("enable_lan",False)) else "127.0.0.1")
    if mode not in {"hover","diagnostic"}: mode="hover"
    os.environ["N8VISION_GRID_DETAIL"]=mode
    print(f"[N8Vision] Grid detail: {mode}")
    os.environ["N8VISION_BIND_HOST"]=host
    os.environ["N8VISION_PORT"]=str(args.port)
    print(f"[N8Vision] Network: {'LAN enabled' if host == '0.0.0.0' else 'local only'} ({host}:{args.port})")
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
        threading.Timer(0.8,open_viewer).start()
    uvicorn.run("n8vision.app:app", host=host, port=args.port, reload=False, access_log=False)

if __name__ == "__main__":
    main()
