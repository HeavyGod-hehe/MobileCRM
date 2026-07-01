@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Phone Reseller CRM - Vendor License Key Generator

echo.
echo   Phone Reseller CRM - Vendor License Key Generator
echo   =================================================
echo.
echo   VENDOR ONLY - do not ship this file to customers.
echo.

if not exist "generate_key.py" (
  echo   ERROR: generate_key.py not found in this folder.
  echo   Run this file from the Source folder.
  echo.
  pause
  exit /b 1
)

if exist "venv\Scripts\python.exe" (
  set "PY=venv\Scripts\python.exe"
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo   ERROR: Python is not installed or not on PATH.
    echo   Install Python from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
  )
  set "PY=python"
)

:menu
echo.
echo   1 - Generate key for THIS computer
echo   2 - Generate key for a CUSTOMER Hardware ID
echo   Q - Quit
echo.
set "CHOICE="
set /p "CHOICE=Choose an option (1, 2, or Q): "

if /i "%CHOICE%"=="Q" goto done
if /i "%CHOICE%"=="1" goto this_machine
if /i "%CHOICE%"=="2" goto customer_id

echo   Invalid choice. Please enter 1, 2, or Q.
goto menu

:this_machine
echo.
echo   This computer:
echo   --------------
"%PY%" "%~dp0generate_key.py"
goto again

:customer_id
echo.
set "HWID="
set /p "HWID=Enter customer Hardware ID (16 hex characters): "

if "%HWID%"=="" (
  echo   No Hardware ID entered.
  goto again
)

echo.
echo   Customer license:
echo   -----------------
"%PY%" "%~dp0generate_key.py" %HWID%
goto again

:again
echo.
set "AGAIN="
set /p "AGAIN=Generate another key? (Y/N): "
if /i "%AGAIN%"=="Y" goto menu
if /i "%AGAIN%"=="YES" goto menu

:done
echo.
echo   Done.
echo.
pause
endlocal
