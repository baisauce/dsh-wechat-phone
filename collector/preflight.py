# -*- coding: utf-8 -*-
"""preflight.py — one-shot health check before the first on-device test.

Run:  python preflight.py
Every line prints PASS/WARN/FAIL with a fix hint. Only check #8 touches the
screen (one tap at pixel 1,1); nothing here changes app data or messages.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from adb_client import Adb, AdbError  # noqa: E402

OK = "PASS"
WARN = "WARN"
FAIL = "FAIL"
results: list[tuple[str, str, str]] = []


def add(level: str, name: str, detail: str = "") -> None:
    results.append((level, name, detail))
    print(f"[{level:4}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8-sig"))
    adb_path = cfg["adb_path"]

    # 1. adb binary
    if os.path.exists(adb_path):
        add(OK, "adb.exe 存在", adb_path)
    else:
        add(FAIL, "adb.exe 缺失", "下载 Google platform-tools，把 adb.exe 的绝对路径填进 config.json 的 adb_path")
        return 1
    adb = Adb(adb_path, cfg.get("serial") or None)

    # 2. adb server + device
    try:
        devs = adb.devices()
    except AdbError as e:
        add(FAIL, "adb 无法启动/连接", str(e))
        return 1
    if not devs:
        add(FAIL, "无设备", "手机插线 → 开发者选项 → 允许 USB 调试")
        return 1
    add(OK, f"设备在线: {', '.join(devs)}")

    # 3. basic shell + screen
    try:
        w, h = adb.screen_size()
        add(OK, f"屏幕尺寸 {w}x{h}")
    except AdbError as e:
        add(FAIL, "shell 异常", str(e))
        return 1

    # 4. wechat installed & version
    try:
        ver = adb.shell("dumpsys package com.tencent.mm | grep versionName | head -1")
        add(OK if "versionName" in ver else FAIL, "微信已安装", ver.strip()[:60])
    except AdbError:
        add(FAIL, "读不到微信包信息", "确认小号设备装的是官方微信")

    # 5. uiautomator works
    try:
        xml = adb.dump_ui()
        add(OK if len(xml) > 500 else WARN, "uiautomator dump", f"{len(xml)} bytes")
    except AdbError as e:
        add(FAIL, "uiautomator 失败", str(e))

    # 6. notifications visible to adb
    try:
        notifs = adb.wechat_notifications()
        if notifs:
            add(OK, f"通知可读（当前 {len(notifs)} 条微信通知）", notifs[-1]["title"][:30])
        else:
            add(WARN, "当前无微信通知", "正常：给小号发条消息后再跑一次确认")
    except AdbError as e:
        add(FAIL, "dumpsys notification 异常", str(e))

    # 7. ADBKeyboard installed?
    try:
        imels = adb.ime_list()
        if "com.android.adbkeyboard" in imels:
            add(OK, "ADBKeyboard 已安装")
        else:
            add(WARN, "ADBKeyboard 未安装",
                "从上游 https://github.com/senzhk/ADBKeyBoard 下载 APK，"
                f"存到 {os.path.join(HERE, '..', 'assets', 'ADBKeyboard.apk')} 后 adb install -r，"
                "再在手机「其他键盘」里启用")
    except AdbError:
        add(WARN, "ime list 读取失败")

    # 8. tap permission (MIUI/OEM safety switch)
    try:
        adb.shell("input tap 1 1")
        add(OK, "input tap 可用（如为小米/华为，确认已开 USB 调试-安全设置）")
    except AdbError as e:
        add(FAIL, "input tap 被拒", "小米/华为需开启「USB调试(安全设置)」")

    # 9. bridge port + token
    s = socket.socket()
    try:
        s.settimeout(3)
        s.connect(("127.0.0.1", 6199))
        add(OK, "AstrBot 桥接 :6199 在听")
    except Exception:
        add(FAIL, "桥接端口不通", "先启动 AstrBot，并在「平台」页启用并保存「微信群手机桥接」")
    finally:
        s.close()
    # token 有两种放法：文件（优先）或内联；main.py 的取值顺序是 文件 → 内联
    tok_file = cfg.get("bridge_token_file", "")
    inline = str(cfg.get("bridge_token", "") or "")
    if tok_file and os.path.exists(tok_file):
        add(OK, f"桥接 token 文件 {tok_file}", "内容须与 AstrBot 平台配置逐字一致")
    elif inline:
        add(OK, "桥接 token（config.json 内联）", f"{len(inline)} 字符，须与 AstrBot 平台配置逐字一致")
    else:
        add(FAIL, "桥接 token 缺失",
            "在 config.json 填 bridge_token，或建 token 文件并把路径填进 bridge_token_file"
            "（AstrBot 不会自动生成这个文件）")

    # 10. AstrBot webui
    try:
        urllib.request.urlopen("http://127.0.0.1:6185/", timeout=5)
        add(OK, "AstrBot WebUI 在线")
    except Exception:
        add(FAIL, "AstrBot 未响应 6185", "启动 AstrBot（README 第 3 步的启动方式）")

    bad = [r for r in results if r[0] == FAIL]
    warn = [r for r in results if r[0] == WARN]
    print(f"\n=== {len(results)} 项: {len(results)-len(bad)-len(warn)} 通过 / {len(warn)} 警告 / {len(bad)} 失败 ===")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
