@echo off
rem Silent collector watchdog launcher (single instance via mutex inside the ps1).
rem Path-independent: resolves itself through %~dp0, no machine-specific literal here.
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0collector-watchdog.ps1"
