# -*- coding: utf-8 -*-
"""debug-quote.py — inject a synthetic @-mention into the bridge and watch the
gap-based quote reply flow."""
import asyncio
import json
import os
import sys
import time

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bridge_cfg  # noqa: E402

cfg = bridge_cfg.load_config()
tok = bridge_cfg.resolve_token(cfg)
if not tok:
    raise SystemExit("no bridge token: set bridge_token (or bridge_token_file) in collector/config.json")

async def main():
    async with websockets.connect(f"{cfg['bridge_ws']}?token={tok}", max_size=2_000_000) as ws:
        payload = {
            "t": "inbound", "kind": "group",
            "group": "示例家庭群",
            "sender": "测试者C",
            "text": "@鲸鲸 在吗",
            "at": True,
            "msg_id": f"dbgq-{int(time.time())}",
            "ts": int(time.time()),
        }
        await ws.send(json.dumps(payload, ensure_ascii=False))
        print("injected:", payload["text"], "from", payload["sender"])
        print("waiting send frame with reply_to (150s)...")
        t0 = time.time()
        while time.time() - t0 < 150:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=150)
            except asyncio.TimeoutError:
                break
            f = json.loads(raw)
            if f.get("t") == "send":
                print("SEND FRAME:", json.dumps({k: f.get(k) for k in ("text", "reply_to")},
                                                ensure_ascii=False))
                return
        print("TIMEOUT: no send frame")

asyncio.run(main())
