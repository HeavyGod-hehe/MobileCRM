@echo off
REM Download Phone Reseller CRM for Windows into your Downloads folder.
REM Run this script from the repo root after cloning the branch.

setlocal
set "BRANCH=cursor/windows-customer-copy-97e7"
set "REPO=HeavyGod-hehe/MobileCRM"
set "DEST=%USERPROFILE%\Downloads\Customer Windows Copy"

echo.
echo   Phone Reseller CRM — Windows Setup
echo   ==================================
echo.

where gh >nul 2>&1
if errorlevel 1 (
  echo   GitHub CLI ^(gh^) is not installed.
  echo.
  echo   Manual steps:
  echo   1. Open: https://github.com/%REPO%/actions
  echo   2. Open the latest "Build Windows Customer Copy" run
  echo   3. Download the "Customer-Windows-Copy" artifact
  echo   4. Extract it to: %DEST%
  echo.
  pause
  exit /b 1
)

echo   Downloading Windows build artifact...
if exist "%DEST%" rmdir /s /q "%DEST%"
mkdir "%DEST%" 2>nul

for /f "delims=" %%i in ('gh run list --repo %REPO% --workflow "Build Windows Customer Copy" --branch %BRANCH% --limit 1 --json databaseId --jq ".[0].databaseId"') do set RUN_ID=%%i

if "%RUN_ID%"=="" (
  echo   No build found. Push the branch and wait for CI, then run again.
  pause
  exit /b 1
)

gh run download %RUN_ID% --repo %REPO% --name Customer-Windows-Copy --dir "%DEST%"

if errorlevel 1 (
  echo   Download failed. Check: https://github.com/%REPO%/actions/runs/%RUN_ID%
  pause
  exit /b 1
)

echo.
echo   Done! Customer copy installed at:
echo   %DEST%
echo.
echo   Double-click:  %DEST%\Phone Reseller CRM\Phone Reseller CRM.exe
echo.
pause
