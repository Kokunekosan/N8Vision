"""Edition launcher; checks an existing server before opening another environment."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from n8vision.instance import running_url,duplicate_dialog
from n8vision.profiles import profile,default_edition

ROOT=Path(__file__).resolve().parent

def selected_edition():return default_edition(ROOT)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--edition',choices=['lite','blurred','full']);args,extra=ap.parse_known_args()
 existing=None if '--admin-code' in extra else running_url()
 if existing:duplicate_dialog(existing);return 0
 edition=args.edition or selected_edition();environment='.venv'
 python=ROOT/environment/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
 if not python.is_file():
  print(f'N8Vision {edition.title()} environment is not installed. Run install-{edition.title()}.cmd.');return 1
 return subprocess.call([str(python),str(ROOT/'run.py'),'--edition',edition,*extra])

if __name__=='__main__':raise SystemExit(main())
