@echo off
REM Launch the Jarvis HUD dashboard
cd /d "%~dp0"
title Jarvis
if not exist ".venv" (
  echo  Run setup.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe main.py
pause
