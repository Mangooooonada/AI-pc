@echo off
REM ==========================================================
REM  JARVIS - one-time setup for Windows
REM ==========================================================
cd /d "%~dp0"
title JARVIS Setup
color 0B

echo.
echo   ==========================================
echo     J A R V I S   -   C O M M A N D   C E N T E R
echo   ==========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo   [X] Python is not installed or not on PATH.
  echo       Install it from https://python.org/downloads
  echo       IMPORTANT: tick "Add Python to PATH" during install.
  echo.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo   Creating virtual environment...
  python -m venv .venv
)

echo   Installing packages ^(a minute or two^)...
call .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
call .venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo   [!] Some packages failed. Jarvis will still run with reduced features.
)

REM ── Edge WebView2 runtime: required for the native app window ────────
REM    Without it the app can only open in your browser ("the website").
set "WV2KEY=HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
reg query "%WV2KEY%" /v pv >nul 2>nul
if errorlevel 1 (
  echo   [!] Microsoft Edge WebView2 Runtime not found.
  echo       The desktop window needs it - trying to install it now...
  where winget >nul 2>nul
  if not errorlevel 1 (
    winget install --id Microsoft.EdgeWebView2Runtime -e --silent --accept-source-agreements --accept-package-agreements
  )
  reg query "%WV2KEY%" /v pv >nul 2>nul
  if errorlevel 1 (
    echo   [!] WebView2 still missing. Jarvis will run in your browser instead.
    echo       Install it manually: https://developer.microsoft.com/microsoft-edge/webview2
  ) else (
    echo   [OK] WebView2 Runtime installed - the native app window will work.
  )
) else (
  echo   [OK] Edge WebView2 Runtime found.
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo   Created .env  ^(open it later to add an API key - optional^)
)

REM ── Pre-compile bytecode so every launch doesn't crawl under AV scans ──
echo   Pre-compiling for faster startups ^(one-time^)...
call .venv\Scripts\python.exe -m compileall -q jarvis >nul 2>nul
call .venv\Scripts\python.exe -m compileall -q ".venv\Lib" >nul 2>nul
echo   [OK] Bytecode cached.

echo.
echo   Setup complete.
echo.
echo     JARVIS.bat            launch the desktop app
echo     start-voice.bat       hands-free voice mode
echo     build-exe.bat         build a standalone JARVIS.exe
echo.
pause
