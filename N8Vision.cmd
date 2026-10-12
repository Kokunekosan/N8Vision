@echo off
REM Keep model/download caches with N8Vision unless the user explicitly overrides them.
if not defined HF_HOME set "HF_HOME=%~dp0cache\huggingface"
if not defined HF_HUB_CACHE set "HF_HUB_CACHE=%HF_HOME%\hub"
if not defined TRANSFORMERS_CACHE set "TRANSFORMERS_CACHE=%HF_HOME%\transformers"

setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo N8Vision virtual environment not found.
  echo Run install.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" reconcile-core.py
if errorlevel 1 (
  echo N8Vision dependency reconciliation failed.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py
