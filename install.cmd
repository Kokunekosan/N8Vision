@echo off
cd /d "%~dp0"
py -3.14 install.py %*
if errorlevel 1 pause
