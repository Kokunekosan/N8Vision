@echo off
cd /d "%~dp0"
py -3.14 install.py --edition lite %*
if errorlevel 1 pause
