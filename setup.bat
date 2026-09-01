@echo off
REM ============================================
REM  Jarvis - one-time setup for Windows
REM ============================================
cd /d "%~dp0"
title Jarvis Setup

echo.
echo  Setting up Jarvis...
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo  [X] Python is not installed.
  echo      Get it from https://python.org/downloads  ^(tick "Add Python to PATH"^)
  pause
  exit /b 1
)

if not exist ".venv" (
  echo  Creating virtual environment...
  python -m venv .venv
)

echo  Installing packages ^(this takes a minute^)...
call .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
call .venv\Scripts\python.exe -m pip install -r requirements.txt

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo  Created .env - open it to add an API key later ^(optional^).
)

echo.
echo  Setup complete. Double-click start-jarvis.bat to launch.
echo.
pause
