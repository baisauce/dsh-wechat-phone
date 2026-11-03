# -*- coding: utf-8 -*-
"""reply-now.py — screen is already inside the target chat: read, forward newest
other-messages to the bridge, wait for the reply, type it back. Minimal path."""
import asyncio
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import websockets  # noqa: E402

from adb_client import Adb  # noqa: E402
import ocr_channel as oc  # noqa: E402
import bridge_cfg  # noqa: E402

cfg = bridge_cfg.load_config()
adb = Adb(cfg["adb_path"], cfg.get("serial") or None)
w, h = adb.screen_size()
tok = bridge_cfg.resolve_token(cfg)
if not tok:
    raise SystemExit("no bridge token: set bridge_token (or bridge_token_file) in collector/config.json")

lines = oc.ocr_png(adb.screencap())
msgs = oc.extract_chat_messages(lines, w, h)
others = [m for m in msgs if not m["is_self"]]
print(f"visible: {len(msgs)} msgs, others: {len(others)}")
for m in others[-4:]:
    print("   ", m["sender"] or "?", ":", m["text"][:48])
if not others:
    print("FAIL: no other messages on screen")
    raise SystemExit(1)

import re
_HOME = re.sub(r"[（(]\d+[)）]\s*$", "", str(cfg.get("home_chat", "示例家庭群")).replace(" ", ""))

async def run():
    async with websockets.connect(f"{cfg['bridge_ws']}?token={tok}", max_size=2_000_000) as ws:
        ts = int(time.time())
        for m in others[-3:]:
            mid = hashlib.md5(f"now|{m}".encode()).hexdigest()[:16]
            at = any(f"@{n}" in m["text"] for n in cfg.get("bot_nicknames", []))
            await ws.send(json.dumps({
                "t": "inbound", "kind": "group", "group": _HOME,
                "sender": m["sender"] or "群友", "text": m["text"],
                "at": at, "msg_id": mid, "ts": ts,
            }, ensure_ascii=False))
            print(f"inbound: [{m['sender']}] {m['text'][:40]} at={at}")
        print("waiting reply (150s)...")
        reply = None
        t0 = time.time()
        while time.time() - t0 < 150:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=150)
            except asyncio.TimeoutError:
                break
            f = json.loads(raw)
            if f.get("t") == "send":
                reply = f
                break
        if reply is None:
            print("FAIL: no bridge reply")
            raise SystemExit(2)
    print("REPLY:", reply["text"][:120])
    px, py = oc.chat_input_point(w, h)
    adb.tap(px, py)
    time.sleep(0.8)
    text = reply["text"]
    for chunk in [text[i:i + 200] for i in range(0, len(text), 200)]:
        adb.input_text(chunk, method=cfg.get("input_method", "adbkeyboard"))
        time.sleep(0.4)
    time.sleep(1.2)
    probe = text[:8].replace(" ", "")
    def in_input():
        ls = oc.ocr_png(adb.screencap())
        # input bar zone only (bottom ~5%); above it are chat bubbles
        return any(l.cy > h * 0.93 and probe in l.text.replace(" ", "") for l in ls)
    adb.shell("am broadcast -a ADB_EDITOR_CODE --ei i 3")
    time.sleep(1.2)
    if in_input():
        adb.keyevent(66)
        time.sleep(1.2)
    if in_input():
        ls = oc.ocr_png(adb.screencap())
        for l in ls:
            if l.cy > h * 0.85 and l.text.strip().lower() in ("send", "发送"):
                adb.tap(int(l.cx), int(l.cy))
                time.sleep(1.2)
                break
    print("SENT" if not in_input() else "WARN: still in input box, check phone")

asyncio.run(run())
