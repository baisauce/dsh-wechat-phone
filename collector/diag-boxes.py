# -*- coding: utf-8 -*-
"""diag-boxes.py — dump raw OCR line boxes to calibrate is_self geometry."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from adb_client import Adb  # noqa: E402
import ocr_channel as oc  # noqa: E402

cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8-sig"))
adb = Adb(cfg["adb_path"], cfg.get("serial") or None)
w, h = adb.screen_size()
lines = oc.ocr_png(adb.screencap())
for l in sorted(lines, key=lambda x: x.cy):
    cr = l.cx / w
    print(f"cx={l.cx:5.0f}({cr:.2f}w) left={l.left:5.0f}({l.right/w:.2f}R) top={l.top:4.0f} bot={l.bottom:4.0f} h={l.bottom-l.top:3.0f} | {l.text[:38]}")
