@echo off
REM Launch hands-free voice mode
cd /d "%~dp0"
title Jarvis - Voice
if not exist ".venv" (
  echo  Run setup.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe main.py voice
pause
