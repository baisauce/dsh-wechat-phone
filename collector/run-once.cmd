@echo off
rem one collector run: ensure adb server, then run main.
rem NOTE: main.py writes logs\collector.log itself via FileHandler;
rem cmd only captures pre-logging crashes to collector-boot.out (no file contention).
"D:\Program Files\AstrBot\tools\platform-tools\adb.exe" start-server >nul 2>&1
set PYTHONIOENCODING=utf-8
"D:\Program Files\AstrBot\python\python.exe" "D:\Program Files\AstrBot\dsh-wechat-phone\collector\main.py" > "D:\Program Files\AstrBot\dsh-wechat-phone\logs\collector-boot.out" 2>&1
