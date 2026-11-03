@echo off
rem One collector run: ensure adb server, then run main.
rem PY / ADB / BOOT normally come from the parent watchdog (tools\resolve-env.ps1);
rem if this file is run directly, resolve them here instead of hardcoding a machine path.
rem NOTE: main.py writes logs\collector.log itself via FileHandler;
rem cmd only captures pre-logging crashes to collector-boot.out (no file contention).
if not "%PY%"=="" goto :have
for /f "usebackq delims=" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\tools\resolve-env.ps1"`) do set "%%i"
:have
if "%PY%"=="" (
  echo [run-once] python not resolved - set DSH_WX_PYTHON or "python" in collector\config.json 1>&2
  exit /b 3
)
if not "%ADB%"=="" "%ADB%" start-server >nul 2>&1
set PYTHONIOENCODING=utf-8
if "%BOOT%"=="" set "BOOT=%~dp0..\logs\collector-boot.out"
"%PY%" "%~dp0main.py" > "%BOOT%" 2>&1
exit /b %ERRORLEVEL%
