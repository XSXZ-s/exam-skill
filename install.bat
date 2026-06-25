@echo off
setlocal
cd /d "%~dp0"

echo.
echo [Exam Skill] Setup
echo ----------------------------------------
echo This script creates .venv and installs dependencies.
echo First setup can take a long time.
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found.
  echo Please install Python 3.10 or newer and enable "Add python.exe to PATH".
  echo https://www.python.org/downloads/
  pause
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3.10 or newer is required.
  python --version
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
  )
) else (
  echo [1/4] Existing .venv found. Skipping creation.
)

echo [2/4] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] Failed to upgrade pip.
  pause
  exit /b 1
)

echo [3/4] Installing project dependencies...
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 (
  echo.
  echo [TIP] Default PyPI install failed. Try install_cn.bat if you need a China mirror.
  pause
  exit /b 1
)

echo [4/4] Preparing .env...
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example.
) else (
  echo Existing .env found. Skipping creation.
)

echo.
echo Setup finished.
echo Please fill LLM_API_KEY in .env before running analysis.
echo.
choice /c YN /m "Open .env now"
if errorlevel 2 goto end
notepad ".env"

:end
echo.
echo Run CLI mode with run_cli.bat.
echo Run API mode with run_api.bat.
pause
