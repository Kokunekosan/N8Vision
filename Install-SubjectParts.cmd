@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Install N8Vision Full first, then run this optional model setup.
 pause
 exit /b 1
)
echo Optional subject reconstruction models
echo PartGLEE: about 0.8 GB weights plus shared CLIP resources.
echo LangHOPS: about 16 GB checkpoint plus shared resources; approved PaliGemma access required.
echo Both use the installed .venv. YOLO remains available.
choice /c GL /m "G = PartGLEE, L = LangHOPS"
if errorlevel 2 (
 ".venv\Scripts\python.exe" -m n8vision.subjectifier_setup --backend langhops
) else (
 ".venv\Scripts\python.exe" -m n8vision.subjectifier_setup --backend partglee
)
pause
