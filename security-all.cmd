@echo off
setlocal
title EDQ Security Launcher

cd /d "%~dp0"

set "PAUSE_AFTER=1"
if /I "%~1"=="--no-pause" set "PAUSE_AFTER=0"

where npm >nul 2>&1
if errorlevel 1 (
  echo npm was not found on PATH.
  set "EXIT_CODE=1"
  goto :done
)

echo Running ShieldMyRepo doctor, scan, and doctor again...
call npm run security:all
set "EXIT_CODE=%ERRORLEVEL%"

:done
echo ==================================================
echo EDQ Security Launcher
echo ==================================================
echo.
if "%EXIT_CODE%"=="0" (
  echo Security flow completed successfully.
) else (
  echo Security flow failed with exit code %EXIT_CODE%.
)

if "%PAUSE_AFTER%"=="1" pause
exit /b %EXIT_CODE%
