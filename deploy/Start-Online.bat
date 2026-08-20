@echo off
setlocal EnableExtensions
title Chess Vision Harness - Go Online
cd /d "%~dp0.."
echo Starting localhost (if needed) and public Online...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0go-online.ps1" %*
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
  echo.
  echo Go Online failed with exit code %EXITCODE%.
  echo Leave this window open so you can read the error.
  pause
  exit /b %EXITCODE%
)
echo.
echo Done. Localhost: http://127.0.0.1:8765
echo Public site: https://chessvisionharness.pages.dev
echo You can close this window.
timeout /t 12 >nul
exit /b 0
