@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv was not found.
  echo Please run install.bat first.
  pause
  exit /b 1
)

echo Starting API server...
echo Browser URL: http://127.0.0.1:8000/
start "" /b powershell -NoProfile -Command "Start-Sleep -Seconds 5; Start-Process 'http://127.0.0.1:8000/'"
".venv\Scripts\python.exe" main.py
echo.
pause
