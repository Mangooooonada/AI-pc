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

echo   Building ^(this takes a few minutes^)...
call .venv\Scripts\python.exe -m PyInstaller jarvis.spec --noconfirm --clean

if exist "dist\JARVIS\JARVIS.exe" (
  echo.
  echo   Done.  dist\JARVIS\JARVIS.exe
  echo   Copy the whole dist\JARVIS folder anywhere you like.
  echo   Right-click JARVIS.exe -^> Send to -^> Desktop for a shortcut.
) else (
  echo   Build failed - check the output above.
)
echo.
pause
