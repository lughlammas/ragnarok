@echo off
setlocal
set PYTHONUTF8=1
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Rode install.bat primeiro.
  exit /b 1
)
if "%~1"=="" (
  "%~dp0.venv\Scripts\python.exe" -m ragnarok web
) else (
  "%~dp0.venv\Scripts\python.exe" -m ragnarok %*
)
