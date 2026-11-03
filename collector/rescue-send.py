# -*- coding: utf-8 -*-
"""rescue-send.py — manual one-off: focus input via OCR bottom row, type, verify draft, tap Send."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from adb_client import Adb  # noqa: E402
import ocr_channel as oc  # noqa: E402

TEXT = sys.argv[1] if len(sys.argv) > 1 else "地址？要干啥用的"
cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8-sig"))
adb = Adb(cfg["adb_path"], cfg.get("serial") or None)
w, h = adb.screen_size()

def snap():
    return oc.ocr_png(adb.screencap())

def send_button(lines):
    return next((l for l in lines if l.cy > h * 0.85 and l.text.strip().lower() in ("send", "发送")), None)

# 1) 找底部输入行占位符并点击（OCR 驱动，不用固定坐标）
lines = snap()
bottom = [l for l in lines if l.cy > h * 0.90 and l.cx < w * 0.6 and len(l.text) < 12]
tx, ty = (int(bottom[-1].cx), int(bottom[-1].cy)) if bottom else (int(w * 0.4), h - 80)
print(f"tap input at ({tx},{ty})")
adb.tap(tx, ty)
time.sleep(1.2)

# 2) 输入
adb.input_text(TEXT, method=cfg.get("input_method", "adbkeyboard"))
time.sleep(1.0)
lines = snap()
sb = send_button(lines)
if sb is None:
    print("no Send button after input -> retry tap lower")
    adb.tap(int(w * 0.4), h - 60)
    time.sleep(1.0)
    adb.input_text(TEXT, method=cfg.get("input_method", "adbkeyboard"))
    time.sleep(1.0)
    lines = snap()
    sb = send_button(lines)
print("draft present, Send at:", (int(sb.cx), int(sb.cy)) if sb else None)

# 3) 点 Send
if sb is not None:
    adb.tap(int(sb.cx), int(sb.cy))
    time.sleep(1.2)
    gone = send_button(snap()) is None
    print("SENT" if gone else "STILL STUCK — check phone")
    adb.keyevent(4)
else:
    print("FAILED to get draft — inspect screen")
    for l in sorted(snap(), key=lambda x: x.cy)[-6:]:
        print(f"({l.cx:.0f},{l.cy:.0f}) {l.text[:40]}")
