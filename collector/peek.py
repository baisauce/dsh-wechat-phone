# -*- coding: utf-8 -*-
"""peek.py — quick screen state diagnosis: focus + OCR of current screen."""
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
print("focus:", adb.current_focus())
lines = oc.ocr_png(adb.screencap())
for l in lines:
    print(f"({l.cx:4.0f},{l.cy:4.0f}) {l.text[:50]}")
