from pathlib import Path
import hashlib, subprocess, sys
root=Path(__file__).resolve().parent
req=root/'requirements-core.txt'; data=root/'data'; stamp=data/'core-requirements.sha256'
digest=hashlib.sha256(req.read_bytes()).hexdigest()
old=stamp.read_text(encoding='ascii').strip() if stamp.exists() else ''
if old==digest:
    raise SystemExit(0)
print('[N8Vision] Core requirements changed; reconciling the existing virtual environment...')
r=subprocess.run([sys.executable,'-m','pip','install','-r',str(req)])
if r.returncode:
    print('[N8Vision] Dependency reconciliation failed; requirements stamp was not advanced.')
    raise SystemExit(r.returncode)
data.mkdir(parents=True,exist_ok=True); stamp.write_text(digest,encoding='ascii')
print('[N8Vision] Core requirements are current.')
