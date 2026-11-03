# -*- coding: utf-8 -*-
"""diag-screen.py — parse the LIVE phone screen with the real pipeline, dump decisions."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import main as M  # noqa: E402
import ocr_channel as oc  # noqa: E402

cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8-sig"))
col = M.Collector(cfg)
w, h = col.adb.screen_size()
lines = oc.ocr_png(col.adb.screencap())
print(f"screen {w}x{h}, {len(lines)} OCR lines, top_title={oc.top_title(lines, w)!r}")
msgs = oc.extract_chat_messages(lines, w, h)
print(f"parsed {len(msgs)} msgs:")
for m in msgs:
    hit = col._should_forward(m["text"])
    at = col._is_at(m["text"])
    tag = "SELF" if m["is_self"] else (m["sender"] or "?")
    print(f"  [{'FWD' if hit else '   '}{'@' if at else ' '}] {tag}: {m['text'][:60]}")
