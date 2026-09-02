@echo off
REM JARVIS one-click launcher — silent by design: the console that runs this
REM file closes itself IMMEDIATELY, leaving exactly ONE window (the app).
cd /d "%~dp0"
if not exist ".venv" (
  echo.
  echo   Run setup.bat first.  This console stays open because something's wrong.
  pause
  exit /b 1
)
REM Relaunch through pythonw (no console ever), then exit our own window
REM before the app even finishes booting.
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py" %*
exit /b 0
