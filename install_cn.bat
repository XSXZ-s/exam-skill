@echo off
setlocal
cd /d "%~dp0"

echo.
echo [Exam Skill] Setup with Tsinghua PyPI mirror
echo ----------------------------------------

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found. Please install Python 3.10 or newer.
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
".venv\Scripts\python.exe" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
  echo [ERROR] Failed to upgrade pip.
  pause
  exit /b 1
)

echo [3/4] Installing project dependencies...
".venv\Scripts\python.exe" -m pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
  echo [ERROR] Failed to install dependencies.
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
echo Setup finished. Please fill LLM_API_KEY in .env.
choice /c YN /m "Open .env now"
if errorlevel 2 goto end
notepad ".env"

:end
pause
