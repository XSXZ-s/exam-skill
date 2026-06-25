@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv was not found.
  echo Please run install.bat first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m app.cli
echo.
pause
