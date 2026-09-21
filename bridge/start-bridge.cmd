@echo off
REM ---------------------------------------------------------------
REM  Opel Bridge starten (Windows)
REM  Erster Start legt config.json samt Zufalls-Token an.
REM ---------------------------------------------------------------
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
  echo Python wurde nicht gefunden. Bitte von python.org installieren.
  pause
  exit /b 1
)

if not exist config.json (
  copy /y config.example.json config.json >nul
  echo config.json aus der Vorlage erstellt.
)

py -m opelbridge %*
pause
