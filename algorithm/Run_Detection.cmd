@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Drag one RAW image onto this file, or run:
  echo Run_Detection.cmd "D:\path\image.raw"
  pause
  exit /b 2
)
"%~dp0.venv\Scripts\python.exe" "%~dp0main.py" --case unified-final --fresh --input "%~1"
set "detection_exit=%errorlevel%"
echo Detection finished with exit code %detection_exit%.
echo New results are saved under the outputs folder.
pause
exit /b %detection_exit%
