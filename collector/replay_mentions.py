"""Replay @鲸鲸 mentions through the live AstrBot pipeline via the bridge WS.

Acts as a fake collector: sends inbound frames, collects outbound replies.
Uses a session name that is NOT the real group, so a real collector (if it
reconnects mid-run) will ignore the replies ("home-only mode").
"""

import asyncio
import json
import os
import sys
import time
import uuid

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
import bridge_cfg  # noqa: E402  (script dir is already on sys.path)

_cfg = bridge_cfg.load_config()
_token = bridge_cfg.resolve_token(_cfg)
if not _token:
    raise SystemExit("no bridge token: set bridge_token (or bridge_token_file) in collector/config.json")
URI = f"{_cfg.get('bridge_ws', 'ws://127.0.0.1:6199')}/?token={_token}"
GROUP = os.environ.get("REPLAY_GROUP", "示例家庭群（回放B）")

# synthetic fixtures: (sender, body) -- covers bare-@, question, alias mention, chat
MESSAGES = [
    ("测试者A", ""),                      # bare @, no text body
    ("测试者A", "在吗"),
    ("测试者B", "讲个笑话吧"),
    ("测试者C", "你是真人还是AI？"),
    ("测试者B", "今天吃什么"),
]

OUT = os.environ.get("REPLAY_OUT", os.path.join(HERE, "replay_result.json"))
PER_MSG_TIMEOUT = 180
QUIET_SECONDS = 8


async def main() -> int:
    results = []
    async with websockets.connect(URI, max_size=2_000_000) as ws:
        print("[replay] connected to bridge", flush=True)
        try:
            await ws.send(json.dumps({"t": "hello", "role": "replay-client"}))
        except Exception:
            pass

        for idx, (sender, body) in enumerate(MESSAGES, 1):
            mid = uuid.uuid4().hex
            text = f"@鲸鲸 {body}".strip() if body else "@鲸鲸"
            frame = {
                "t": "inbound",
                "msg_id": mid,
                "group": GROUP,
                "sender": sender,
                "text": text,
                "at": True,
                "kind": "group",
                "ts": int(time.time()),
            }
            t0 = time.time()
            await ws.send(json.dumps(frame, ensure_ascii=False))
            print(f"[replay] #{idx} -> [{sender}] {text}", flush=True)

            bubbles = []       # 本轮收到的所有 outbound send 帧（工具发送 + 最终回复）
            reply = None
            first_ts = None    # 第一条气泡到达时间（真实响应耗时，不含静默尾部）
            while time.time() - t0 < PER_MSG_TIMEOUT:
                wait = PER_MSG_TIMEOUT - (time.time() - t0)
                if bubbles:
                    wait = min(wait, QUIET_SECONDS)
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=wait)
                except asyncio.TimeoutError:
                    if bubbles:
                        break          # 已收到消息，静默 QUIET_SECONDS → 本轮结束
                    continue           # 还没收到，继续等
                try:
                    f = json.loads(raw)
                except Exception:
                    continue
                if f.get("t") != "send":
                    continue
                if first_ts is None:
                    first_ts = time.time()
                bubbles.append({
                    "text": f.get("text") or "",
                    "src_mid": f.get("src_mid"),
                    "target": (f.get("target") or {}).get("name"),
                })
                if f.get("src_mid") == mid:
                    reply = f.get("text") or ""
            quiet_tail = time.time() - t0 - (first_ts - t0 if first_ts else 0)
            elapsed = round((first_ts - t0) if first_ts else (time.time() - t0), 1)
            print(f"[replay] #{idx} <- {elapsed}s  bubbles={len(bubbles)} "
                  f"final={reply!r}", flush=True)
            for b in bubbles:
                print(f"           · {b['text'][:60]!r}", flush=True)
            results.append({
                "index": idx,
                "sender": sender,
                "message": text,
                "reply": reply,
                "bubbles": bubbles,
                "seconds": elapsed,
            })
            with open(OUT, "w", encoding="utf-8") as fh:
                json.dump(results, fh, ensure_ascii=False, indent=2)
            await asyncio.sleep(1)

    print("[replay] done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
