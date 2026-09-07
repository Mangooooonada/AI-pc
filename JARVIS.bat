@echo off
setlocal
REM ==========================================================================
REM  JARVIS one-click launcher — THE ONLY THING YOU EVER DOUBLE-CLICK
REM
REM  * First run   : this same window runs the full setup inline, then the
REM                  app opens. No separate setup.bat, ever.
REM  * Updates     : if requirements.txt is newer than the setup stamp (you
REM                  pulled new code), dependencies top up quietly first.
REM  * Every run   : console relaunches pythonw and exits itself instantly —
REM                  one window, period.
REM ==========================================================================
cd /d "%~dp0"
set "PYW=%~dp0.venv\Scripts\pythonw.exe"
set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" goto :SETUP

REM ── pulled new code lately? top up deps only when the stamp is stale ──
"%PY%" -c "import os,sys,pathlib; r=pathlib.Path('requirements.txt'); s=pathlib.Path('.setup-ok'); sys.exit(0 if (s.exists() and s.stat().st_mtime>=r.stat().st_mtime) else 1)" >nul 2>nul
if not errorlevel 1 goto :LAUNCH
echo.
echo   New ingredients detected - topping up packages (one moment)...
"%PY%" -m pip install -r "%~dp0requirements.txt" --quiet --disable-pip-version-check
copy /y nul "%~dp0.setup-ok" >nul 2>nul
goto :LAUNCH

:SETUP
title JARVIS First-Run Setup
color 0B
echo.
echo   ==========================================
echo     J A R V I S   -   F I R S T   R U N
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

if not exist "%~dp0.venv" (
  echo   Creating virtual environment...
  python -m venv "%~dp0.venv"
)

echo   Installing packages ^(a minute or two, this window only^)...
call "%PY%" -m pip install --upgrade pip --quiet
call "%PY%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo.
  echo   [!] Some packages failed. Jarvis will still run with reduced features.
)

REM ── Edge WebView2 runtime: needed for the native app window ──
set "WV2KEY=HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
reg query "%WV2KEY%" /v pv >nul 2>nul
if errorlevel 1 (
  echo   [!] Microsoft Edge WebView2 Runtime not found - installing now...
  where winget >nul 2>nul
  if not errorlevel 1 (
    winget install --id Microsoft.EdgeWebView2Runtime -e --silent --accept-source-agreements --accept-package-agreements
  )
  reg query "%WV2KEY%" /v pv >nul 2>nul
  if errorlevel 1 (
    echo   [!] WebView2 still missing. Jarvis will run in your browser instead.
  ) else (
    echo   [OK] WebView2 Runtime installed.
  )
) else (
  echo   [OK] Edge WebView2 Runtime found.
)

if not exist "%~dp0.env" (
  copy "%~dp0.env.example" "%~dp0.env" >nul
  echo   Created .env  ^(add an API key later - optional^)
)

echo   Pre-compiling for faster startups ^(one-time^)...
call "%PY%" -m compileall -q jarvis >nul 2>nul
call "%PY%" -m compileall -q ".venv\Lib" >nul 2>nul
echo   [OK] Bytecode cached.

REM ── Defender exclusion: the real speedup ──
set "JARVIS_DIR=%CD%"
powershell -NoProfile -Command "try { if ((Get-MpPreference).ExclusionPath -contains '%JARVIS_DIR%') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 goto :STAMP
echo.
echo   [Tip] Windows Defender re-scans every Python file on every launch,
echo         which makes startup crawl. I can exclude THIS folder only
echo         ^(everything else stays fully protected^).
echo         An admin prompt will pop up - approve it to speed things up.
set /p ADDX=        Add the exclusion now? [Y/n]
if /i "%ADDX%"=="n" goto :STAMP
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-Command','Add-MpPreference -ExclusionPath ''%JARVIS_DIR%''; Add-MpPreference -ExclusionProcess ''%JARVIS_DIR%\.venv\Scripts\python.exe''; Add-MpPreference -ExclusionProcess ''%JARVIS_DIR%\.venv\Scripts\pythonw.exe'''"
powershell -NoProfile -Command "try { if ((Get-MpPreference).ExclusionPath -contains '%JARVIS_DIR%') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if errorlevel 1 (
  echo   [!] Couldn't confirm ^(declined?^). You can do it later in Settings.
) else (
  echo   [OK] Exclusion added - launches just got faster.
)
goto :STAMP

:STAMP
copy /y nul "%~dp0.setup-ok" >nul 2>nul
echo.
echo   Setup finished inside this window - launching Jarvis now...
echo.

:LAUNCH
if not exist "%PYW%" (
  echo.
  echo   [!] .venv looks broken. Delete the .venv folder and relaunch.
  pause
  exit /b 1
)
start "" "%PYW%" "%~dp0main.py" %*
exit /b 0
