@echo off
rem WeChat ADB collector - foreground single run (console stays attached, easy to Ctrl+C).
rem No hardcoded machine paths: everything comes from tools\resolve-env.ps1.
rem Overrides: set DSH_WX_PYTHON / DSH_WX_ADB, or "python"/"adb_path" in collector\config.json.
setlocal
if not "%PY%"=="" goto :have
for /f "usebackq delims=" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\resolve-env.ps1"`) do set "%%i"
:have
if "%PY%"=="" (
  echo [start-collector] python not resolved - set DSH_WX_PYTHON or "python" in collector\config.json 1>&2
  exit /b 3
)
set PYTHONIOENCODING=utf-8
"%PY%" "%~dp0collector\main.py"
exit /b %ERRORLEVEL%
