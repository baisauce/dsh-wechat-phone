# -*- coding: utf-8 -*-
"""preflight.py — one-shot health check before the first on-device test.

Run:  python preflight.py
Two phases, printed in one report:
  A. 电脑/AstrBot 侧（插不插手机都能查）：config 字段、门禁卡与 AstrBot 平台配置只读比对、
     6199 端口、6185 WebUI
  B. 手机侧：设备/屏幕/微信/输入法/tap 权限（+ 两项历史遗留诊断，仅供参考不计失败）
Every line prints PASS/WARN/FAIL with a fix hint. Only phase B's tap check touches
the screen (one tap at pixel 1,1); nothing here changes app data or messages, and
phase A never opens a WS connection (a real connect would make AstrBot flush queued
replies into this probe and lose them).
"""
from __future__ import annotations

import os
import socket
import sys
import urllib.request

try:  # 控制台不是 UTF-8 时，别让中文报告变成乱码
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from adb_client import Adb, AdbError  # noqa: E402
import bridge_cfg  # noqa: E402

OK = "PASS"
WARN = "WARN"
FAIL = "FAIL"
results: list[tuple[str, str, str]] = []


def add(level: str, name: str, detail: str = "") -> None:
    results.append((level, name, detail))
    print(f"[{level:4}] {name}" + (f" — {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n—— {title} ——")


# ---------------------------------------------------------------- phase A: PC side
def check_pc(cfg: dict) -> None:
    # A1. config sanity - the fields main.py actually reads
    if not str(cfg.get("home_chat") or "").strip():
        add(FAIL, "home_chat 为空", "采集器不知道守哪一间会话：填微信群名或联系人备注名")
    else:
        add(OK, f"home_chat = {cfg.get('home_chat')}", "采集器只读这间、也只写这间")
    if not (cfg.get("bot_nicknames") or []):
        add(FAIL, "bot_nicknames 为空", "认不出哪些 @ 是在叫它：把被 @ 到的每种写法都列进来")
    else:
        add(OK, f"bot_nicknames {len(cfg['bot_nicknames'])} 个", "含对方备注名里的写法")
    if not (cfg.get("wake_keywords") or []):
        add(WARN, "wake_keywords 为空", "只有真 @ 才转发；日常点名式闲聊会全部沉默")
    im = str(cfg.get("input_method") or "adbkeyboard")
    add(OK if im in ("adbkeyboard", "ascii") else FAIL, f"input_method = {im}",
        "可选 adbkeyboard / ascii" if im not in ("adbkeyboard", "ascii") else "")

    # A2. adb binary (phone may not be attached yet - still worth knowing)
    adb_path = str(cfg.get("adb_path") or "")
    if adb_path and os.path.exists(adb_path):
        add(OK, "adb.exe 存在", adb_path)
    else:
        add(FAIL, "adb.exe 缺失/路径不对",
            "下载 Google platform-tools，把 adb.exe 的绝对路径填进 config.json 的 adb_path")

    # A3. bridge token + AstrBot platform cross-check (read-only, no connection)
    token = bridge_cfg.resolve_token(cfg)
    src = bridge_cfg.token_source(cfg)
    if not token:
        add(FAIL, "桥接 token 缺失",
            "在 config.json 填 bridge_token，或建 token 文件并把路径填进 bridge_token_file"
            "（AstrBot 不会自动生成这个文件）")
    else:
        add(OK, f"桥接 token 已配置（来源：{src}）", f"{len(token)} 字符")

    plat = bridge_cfg.astrbot_platform_cfg(cfg)
    if not plat:
        add(WARN, "未能读到 AstrBot 平台配置",
            "跳过两侧比对；AstrBot 不在默认位置时，在 config.json 设 astrbot_config "
            "指向 data\\cmd_config.json")
        return
    a_tok = str(plat.get("token") or "")
    if not a_tok:
        add(FAIL, "AstrBot 侧 token 为空",
            "适配器只在 token 非空时校验：留空＝门禁失效，本机任何进程都能挂上来")
    elif not token:
        add(FAIL, "AstrBot 侧 token 已设但采集器侧为空", "两边必须是同一串（逐字一致）")
    elif a_tok == token:
        add(OK, "token 两侧一致（已与 AstrBot 核对）", f"{len(token)} 字符")
    else:
        add(FAIL, "token 两侧不一致", "采集器连得上端口但会被插座拒收（close 4401）")

    # A4. platform hardening
    a_host = str(plat.get("ws_host") or "0.0.0.0")
    if a_host in ("127.0.0.1", "localhost", "::1"):
        add(OK, f"AstrBot 侧 ws_host={a_host}", "只监听本机")
    else:
        add(WARN, f"AstrBot 侧 ws_host={a_host}",
            "采集器就在本机：建议改 127.0.0.1，别把 6199 暴露到局域网")
    port = int(plat.get("ws_port") or 6199)
    cfg_ws = str(cfg.get("bridge_ws") or "")
    if cfg_ws and f":{port}" not in cfg_ws:
        add(FAIL, "采集器 bridge_ws 端口与 AstrBot 不一致", f"config 指 {cfg_ws}，AstrBot 在听 {port}")
    if bool(plat.get("auto_accept", True)):
        add(WARN, "AstrBot 侧 auto_accept=true", "来者不拒：allowed_chats 名单被跳过。改 false")
    allowed = [str(x) for x in (plat.get("allowed_chats") or [])]
    home = str(cfg.get("home_chat") or "")
    if not allowed:
        add(WARN, "allowed_chats 为空", "访客名单一条都没有：关了 auto_accept 会全部装死")
    elif home and not any(bridge_cfg.norm_title(a) == bridge_cfg.norm_title(home) for a in allowed):
        add(WARN, "home_chat 不在 allowed_chats 里",
            f"常驻的「{home}」不在名单中，回复会被管线丢弃")

    # A5. two wake-keyword lists must agree
    a_kw = plat.get("wake_keywords")
    if isinstance(a_kw, str):
        a_kw = [k for k in a_kw.replace("，", ",").replace("、", ",").split(",") if k.strip()]
    a_kw = {str(k).strip().lower() for k in (a_kw or []) if str(k).strip()}
    c_kw = {str(k).strip().lower() for k in (cfg.get("wake_keywords") or []) if str(k).strip()}
    missing = sorted(c_kw - a_kw)
    if not a_kw:
        add(WARN, "AstrBot 侧 wake_keywords 为空", "群聊里只有真 @ 才算被点名；把采集器那份同步过去")
    elif missing:
        add(WARN, "采集器有、AstrBot 没有的唤醒词",
            f"{len(missing)} 个（如「{missing[0]}」）：会转发但不算点名，可能不回")
    else:
        add(OK, "两侧 wake_keywords 已覆盖采集器那份", f"AstrBot {len(a_kw)} / 采集器 {len(c_kw)}")


def check_services(cfg: dict) -> None:
    # 从 bridge_ws 里取端口；"ws://127.0.0.1" 这种缺端口的写法不能让整份体检崩掉
    port = 6199
    tail = str(cfg.get("bridge_ws") or "").rsplit(":", 1)[-1].strip()
    if tail.isdigit():
        port = int(tail)
    if not (0 < port <= 65535):
        port = 6199
    s = socket.socket()
    try:
        s.settimeout(3)
        s.connect(("127.0.0.1", port))
        add(OK, f"AstrBot 桥接 :{port} 在听")
    except Exception:
        add(FAIL, f"桥接端口 {port} 不通", "先启动 AstrBot，并在「平台」页启用并保存「微信群手机桥接」")
    finally:
        s.close()
    try:
        urllib.request.urlopen("http://127.0.0.1:6185/", timeout=5)
        add(OK, "AstrBot WebUI 在线")
    except Exception:
        add(FAIL, "AstrBot 未响应 6185", "启动 AstrBot（README 第 3 步的启动方式）")


# ---------------------------------------------------------------- phase B: phone side
def check_phone(cfg: dict) -> None:
    adb_path = str(cfg.get("adb_path") or "")
    if not adb_path or not os.path.exists(adb_path):
        add(WARN, "跳过手机侧检查", "adb.exe 路径还没配好（见上面的 adb.exe 缺失）")
        return
    adb = Adb(adb_path, cfg.get("serial") or None)
    try:
        devs = adb.devices()
    except AdbError as e:
        add(FAIL, "adb 无法启动/连接", str(e))
        return
    if not devs:
        add(FAIL, "无设备", "手机插线 → 开发者选项 → 允许 USB 调试 → 弹窗点允许")
        return
    if len(devs) > 1 and not str(cfg.get("serial") or "").strip():
        add(FAIL, "多台设备但 serial 为空", f"在 config.json 填 serial：{', '.join(devs)}")
    add(OK, f"设备在线: {', '.join(devs)}")

    try:
        w, h = adb.screen_size()
        add(OK, f"屏幕尺寸 {w}x{h}", "采集器按屏幕比例取坐标，无最低分辨率要求但需竖屏手机微信")
    except AdbError as e:
        add(FAIL, "shell 异常", str(e))
        return

    try:
        ver = adb.shell("dumpsys package com.tencent.mm | grep versionName | head -1")
        add(OK if "versionName" in ver else FAIL, "微信已安装", ver.strip()[:60])
    except AdbError:
        add(FAIL, "读不到微信包信息", "确认小号设备装的是官方微信（手机版，非 HD/平板版）")

    if str(cfg.get("input_method") or "adbkeyboard") == "adbkeyboard":
        try:
            imels = adb.ime_list()
            if "com.android.adbkeyboard" in imels:
                add(OK, "ADBKeyboard 已安装")
            else:
                add(WARN, "ADBKeyboard 未安装",
                    "从上游 https://github.com/senzhk/ADBKeyBoard 下载 APK，"
                    f"存到 {os.path.normpath(os.path.join(HERE, '..', 'assets', 'ADBKeyboard.apk'))} "
                    "后 adb install -r，再在手机「其他键盘」里启用")
        except AdbError:
            add(WARN, "ime list 读取失败")

    try:
        adb.shell("input tap 1 1")
        add(OK, "input tap 可用（如为小米/华为，确认已开 USB 调试-安全设置）")
    except AdbError:
        add(FAIL, "input tap 被拒", "小米/华为需开启「USB调试(安全设置)」；有「权限监控」开关的先关掉")

    # 历史遗留诊断：不参与判定（国产 ROM 常屏蔽 dumpsys，判红会误导）
    try:
        xml = adb.dump_ui()
        add(OK, f"[历史遗留] uiautomator dump {len(xml)} bytes", "不参与判定：现行读屏为纯 OCR")
    except AdbError:
        add(WARN, "[历史遗留] uiautomator dump 失败", "不参与判定：现行读屏为纯 OCR")
    try:
        notifs = adb.wechat_notifications()
        if notifs:
            add(OK, f"[历史遗留] 通知可读（当前 {len(notifs)} 条）", notifs[-1]["title"][:30])
        else:
            add(OK, "[历史遗留] 当前无微信通知", "不参与判定：现行读屏为纯 OCR")
    except AdbError:
        add(WARN, "[历史遗留] dumpsys notification 读取失败", "不参与判定：现行读屏为纯 OCR")


def main() -> int:
    try:
        cfg = bridge_cfg.load_config()
    except FileNotFoundError:
        add(FAIL, "config.json 不存在", "先 Copy-Item config.example.json config.json 再按第 9 步改字段")
        print("\n=== 1 项: 0 通过 / 0 警告 / 1 失败 ===")
        return 1

    section("A. 电脑 / AstrBot 侧（不插手机也能查）")
    check_pc(cfg)
    check_services(cfg)

    section("B. 手机侧")
    check_phone(cfg)

    bad = [r for r in results if r[0] == FAIL]
    warn = [r for r in results if r[0] == WARN]
    print(f"\n=== {len(results)} 项: {len(results) - len(bad) - len(warn)} 通过 / "
          f"{len(warn)} 警告 / {len(bad)} 失败 ===")
    if bad:
        print("先修上面的 FAIL 再起 main.py；WARN 是安全/体验提醒，不阻塞启动。")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
