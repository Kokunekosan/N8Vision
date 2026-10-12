@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYVER=3.14"
set "PY=.venv\Scripts\python.exe"
set "TORCH_INDEX=https://download.pytorch.org/whl/cu130"
set "ERAX_DIR=n8vision\models\ultralytics\bbox"
set "ERAX_FILE=%ERAX_DIR%\erax_nsfw_yolo11m.pt"
set "ERAX_URL=https://huggingface.co/erax-ai/EraX-NSFW-V1.0/resolve/83b8c11eb32bb54f73d8ca51b6b56ef4292e06fd/erax_nsfw_yolo11m.pt?download=true"

echo N8Vision unified installer

echo [1/7] Cleaning replaceable build debris...
for /d /r %%D in (__pycache__) do @if exist "%%D" rd /s /q "%%D" 2>nul
del /s /q *.pyc *.pyo 2>nul
if exist ".venv\pyvenv.cfg" (
  findstr /c:"version = %PYVER%" ".venv\pyvenv.cfg" >nul 2>nul || (
    echo Existing venv is not Python %PYVER%; rebuilding only the private environment.
    rd /s /q .venv
  )
)

if not exist "%PY%" (
  echo [2/7] Creating private Python %PYVER% environment...
  py -%PYVER% -m venv .venv
  if errorlevel 1 goto :fail_python
) else echo [2/7] Reusing private Python %PYVER% environment.

 echo [3/7] Updating installer tooling and core dependencies...
"%PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :fail
"%PY%" -m pip install --upgrade -r requirements-core.txt
if errorlevel 1 goto :fail

 echo [4/7] Installing pinned PyTorch 2.14.0...
where nvidia-smi >nul 2>nul
if errorlevel 1 goto :torch_cpu
nvidia-smi -L >nul 2>nul
if errorlevel 1 goto :torch_cpu
echo NVIDIA GPU detected: CUDA 13.0 wheel channel.
"%PY%" -m pip install --upgrade --index-url %TORCH_INDEX% torch==2.14.0 torchvision
if errorlevel 1 goto :fail_torch
goto :vision

:torch_cpu
echo No usable NVIDIA GPU detected: CPU-compatible PyTorch.
"%PY%" -m pip install --upgrade torch==2.14.0 torchvision
if errorlevel 1 goto :fail_torch

:vision
echo [5/7] Installing vision and classifier dependencies...
"%PY%" -m pip install --upgrade -r requirements-vision.txt -r requirements-classifiers.txt
if errorlevel 1 goto :fail

 echo [6/7] Installing managed detector weights...
if not exist "%ERAX_DIR%" mkdir "%ERAX_DIR%"
if not exist "%ERAX_FILE%" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '%ERAX_URL%' -OutFile '%ERAX_FILE%.part'; Move-Item -Force '%ERAX_FILE%.part' '%ERAX_FILE%'"
  if errorlevel 1 goto :fail_erax
) else echo EraX NSFW V1.0 already present.

 echo [7/7] Verifying pinned runtime...
"%PY%" -c "import torch; assert torch.__version__.split('+')[0]=='2.14.0', torch.__version__; import ultralytics, transformers; print('Torch:',torch.__version__); print('Torch CUDA build:',torch.version.cuda); print('CUDA available:',torch.cuda.is_available()); print('GPU:',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU fallback'); print('Ultralytics:',ultralytics.__version__)"
if errorlevel 1 goto :fail

 echo.
echo N8Vision installation complete.
echo EraX is managed in the default YOLO stack after YOLO-World.
echo Run N8Vision.cmd
pause
exit /b 0

:fail_python
echo.
echo Installation failed. Verify CPython %PYVER% is installed and available through py -%PYVER%.
pause
exit /b 1
:fail_torch
echo.
echo Pinned PyTorch 2.14.0 installation failed. N8Vision will not silently substitute another Torch version.
pause
exit /b 1
:fail_erax
del /q "%ERAX_FILE%.part" 2>nul
echo.
echo EraX managed-weight download failed. Re-run install.cmd when Hugging Face is reachable.
pause
exit /b 1
:fail
echo.
echo N8Vision installation failed. See the error above.
pause
exit /b 1
