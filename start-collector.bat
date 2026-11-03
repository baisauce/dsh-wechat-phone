@echo off
rem WeChat ADB collector - single instance, hidden, logs to dsh-wechat-phone\logs\collector.log
setlocal
set PYTHONIOENCODING=utf-8
"D:\Program Files\AstrBot\python\python.exe" "D:\Program Files\AstrBot\dsh-wechat-phone\collector\main.py"
