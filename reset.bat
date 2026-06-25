@echo off
setlocal
cd /d "%~dp0"

echo This will reset local generated project state:
echo - .venv
echo - .cache
echo - chroma_db
echo.
echo It will NOT remove resources, output, .env, or source code.
echo.
choice /c YN /m "Confirm reset"
if errorlevel 2 exit /b 0

if exist ".venv" rmdir /s /q ".venv"
if exist ".cache" rmdir /s /q ".cache"
if exist "chroma_db" rmdir /s /q "chroma_db"

echo Reset finished.
echo Run install.bat again before using the project.
pause
