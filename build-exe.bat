@echo off
REM ==========================================================
REM  Build a standalone JARVIS.exe (no Python needed to run)
REM ==========================================================
cd /d "%~dp0"
title JARVIS - Build

if not exist ".venv" (
  echo   Run setup.bat first.
  pause
  exit /b 1
)

echo   Installing PyInstaller...
call .venv\Scripts\python.exe -m pip install --quiet pyinstaller

set /p JVER=<VERSION
if not defined JVER set JVER=dev
echo   Version: %JVER%
echo   Building ^(this takes a few minutes^)...
call .venv\Scripts\python.exe -m PyInstaller jarvis.spec --noconfirm --clean

if exist "dist\JARVIS\JARVIS.exe" (
  echo.
  rename "dist\JARVIS\JARVIS.exe" "JARVIS-v%JVER%.exe"
  mkdir "dist\JARVIS-v%JVER%" 2>nul
  move "dist\JARVIS\*" "dist\JARVIS-v%JVER%\" >nul 2>nul
  rmdir "dist\JARVIS" 2>nul
  echo   Done.  dist\JARVIS-v%JVER%\JARVIS-v%JVER%.exe
  echo   Each build is version-named: old builds are NEVER overwritten.
  echo   Right-click JARVIS-v%JVER%.exe -^> Send to -^> Desktop.
) else (
  echo   Build failed - check the output above.
)
echo.
pause
