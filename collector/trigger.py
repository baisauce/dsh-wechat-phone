# -*- coding: utf-8 -*-
"""trigger.py — one-shot manual flow: open a chat, forward its latest message to
the bridge, wait for Little Whale's reply, type it back into WeChat.

Usage: python trigger.py "示例家庭"
"""
import asyncio
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import websockets  # noqa: E402

from adb_client import Adb  # noqa: E402
import ocr_channel as oc  # noqa: E402
import hashlib  # noqa: E402


async def main() -> None:
    title_prefix = sys.argv[1] if len(sys.argv) > 1 else "示例家庭"
    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8-sig"))
    adb = Adb(cfg["adb_path"], cfg.get("serial") or None)
    w, h = adb.screen_size()
    tok = open(cfg["bridge_token_file"]).read().strip()

    # 1) navigate to the chat via list
    focus = adb.current_focus()
    if "LauncherUI" not in focus:
        adb.shell("monkey -p com.tencent.mm -c android.intent.category.LAUNCHER 1")
        time.sleep(3)
    lines = oc.ocr_png(adb.screencap())
    row = oc.find_conversation_row(lines, title_prefix, w)
    if row is None:
        print("FAIL: 列表里找不到会话，请让手机停在微信会话列表页")
        return
    title = row.text
    # strip trailing member count for the canonical title
    import re
    title = re.sub(r"[（(]\d+[)）]\s*$", "", title)
    print(f"opening chat: {title!r}")
    adb.tap(int(w * 0.5), int(row.cy))
    time.sleep(1.5)

    # 2) read messages
    lines = oc.ocr_png(adb.screencap())
    msgs = oc.extract_chat_messages(lines, w, h)
    others = [m for m in msgs if not m["is_self"]]
    print(f"visible msgs: {len(msgs)}, from others: {len(others)}")
    for m in others[-5:]:
        print("   ", m["sender"] or "?", ":", m["text"][:50])
    if not others:
        print("FAIL: 没读到他人消息")
        adb.keyevent(4)
        return
    target = others[-1]  # latest other message

    # 3) forward to bridge as inbound
    mid = hashlib.md5(f"{title}|{target}".encode()).hexdigest()[:16]
    async with websockets.connect(f"{cfg['bridge_ws']}?token={tok}", max_size=2_000_000) as ws:
        payload = {
            "t": "inbound", "kind": "group", "group": title,
            "sender": target["sender"] or "群友", "text": target["text"],
            "at": any(n in target["text"] for n in cfg.get("bot_nicknames", [])),
            "msg_id": mid, "ts": int(time.time()),
        }
        await ws.send(json.dumps(payload, ensure_ascii=False))
        print(f"\ninbound sent: [{payload['sender']}] {payload['text'][:60]} (at={payload['at']})")
        print("waiting bridge reply (120s)...")
        reply = None
        t0 = time.time()
        while time.time() - t0 < 120:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=120)
            except asyncio.TimeoutError:
                break
            f = json.loads(raw)
            if f.get("t") == "send":
                reply = f
                break
        if reply is None:
            print("FAIL: bridge 无回复")
            adb.keyevent(4)
            return
        print(f"\nbridge reply: {reply['text'][:120]}")

    # 4) type it back (we're already inside the chat)
    px, py = oc.chat_input_point(w, h)
    adb.tap(px, py)
    time.sleep(0.8)
    for chunk in [reply["text"][i:i + 200] for i in range(0, len(reply["text"]), 200)]:
        adb.input_text(chunk, method=cfg.get("input_method", "adbkeyboard"))
        time.sleep(0.4)
    time.sleep(1.0)
    adb.keyevent(66)  # ENTER
    time.sleep(1.0)
    print("sent! verifying...")
    lines = oc.ocr_png(adb.screencap())
    mine = [m for m in oc.extract_chat_messages(lines, w, h) if m["is_self"]]
    ok = any(reply["text"][:12].replace(" ", "") in m["text"].replace(" ", "") for m in mine[-3:])
    print("VERIFIED: 回复气泡出现在聊天页" if ok else "WARN: 截图未确认到气泡，请人工看一眼手机")


if __name__ == "__main__":
    asyncio.run(main())
