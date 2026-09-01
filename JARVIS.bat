@echo off
REM Launch the JARVIS desktop app
cd /d "%~dp0"
title JARVIS
if not exist ".venv" (
  echo   Run setup.bat first.
  pause
  exit /b 1
)
start "" .venv\Scripts\pythonw.exe main.py %*
