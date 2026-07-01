@echo off
cd /d "%~dp0"
title Phone Reseller CRM
echo.
echo   Phone Reseller CRM
echo   ------------------
echo.

if not exist "venv\Scripts\python.exe" (
  echo   Creating virtual environment...
  python -m venv venv
)

call venv\Scripts\activate.bat

python -c "import flask" >nul 2>&1
if errorlevel 1 (
  echo   Installing dependencies...
  python -m pip install -r requirements.txt -q
)

echo   Starting server — browser opens at http://localhost:5050
echo   Keep this window open. Press Ctrl+C to stop.
echo.

python "%~dp0app.py"
echo.
pause
