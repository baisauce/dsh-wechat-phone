@echo off
rem Silent collector watchdog launcher (single instance via mutex inside ps1)
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\Program Files\AstrBot\dsh-wechat-phone\collector-watchdog.ps1"
