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

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo   Created .env  ^(open it later to add an API key - optional^)
)

echo.
echo   Setup complete.
echo.
echo     JARVIS.bat            launch the desktop app
echo     start-voice.bat       hands-free voice mode
echo     build-exe.bat         build a standalone JARVIS.exe
echo.
pause
