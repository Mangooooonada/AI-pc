@echo off
REM Hands-free voice mode in a console window
cd /d "%~dp0"
title JARVIS - Voice
if not exist ".venv" (
  echo   Run setup.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe main.py voice
pause
