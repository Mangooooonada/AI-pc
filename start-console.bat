@echo off
REM Terminal chat
cd /d "%~dp0"
title JARVIS - Console
if not exist ".venv" (
  echo   Run setup.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe main.py cli
pause
