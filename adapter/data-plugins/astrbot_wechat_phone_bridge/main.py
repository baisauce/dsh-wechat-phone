"""WeChat Phone Bridge platform adapter for AstrBot.

Runs an asyncio WebSocket server (LAN only). The Android collector app pushes
inbound WeChat messages; replies produced by the normal AstrBot pipeline come
back through send_by_session and are queued to the phone (humanized delay is
applied on-device by the collector).

Config keys (platform_config, flat):
  ws_host           bind address, default 0.0.0.0 (LAN)
  ws_port           default 6199
  token             shared secret; collector must present it via ?token= query
  auto_accept       true -> every inbound message enters pipeline; false -> whitelist only
  allowed_chats     list of chat titles (group names / contact remarks)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain
from astrbot.api.star import Star
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember, MessageType
from astrbot.core.platform.platform import Platform
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.register import register_platform_adapter
from astrbot.core import logger


class WxBridgeMessageEvent(AstrMessageEvent):
    """Custom event: base send() only records metrics, real delivery needs platform hook."""

    def __init__(self, message_str, message_obj, platform_meta, session_id, platform) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.platform = platform

    async def send(self, message: MessageChain) -> None:
        try:
            sender_name = str(self.message_obj.sender.nickname or "")
        except Exception:
            sender_name = ""
        await self.platform.send_by_session(self.session, message,
                                            reply_to=self.message_obj.message_str,
                                            src_mid=str(self.message_obj.message_id or ""),
                                            reply_sender=sender_name)
        self._has_send_oper = True


class WechatPhoneBridgePlugin(Star):
    """Marker Star class: importing this module registers the platform adapter.

    The adapter itself (WechatPhoneBridgePlatform below) is what does the work;
    AstrBot requires every plugin to expose a Star subclass, even for
    adapter-only plugins.
    """

    def __init__(self, context) -> None:  # noqa: D401
        super().__init__(context)


@register_platform_adapter(
    "wechat_phone_bridge",
    "微信群手机桥接：局域网 WebSocket 对接安卓采集端（无障碍/通知，无注入无协议）",
    default_config_tmpl={
        "ws_host": "0.0.0.0",
        "ws_port": 6199,
        "token": "change-me-shared-secret",
        "auto_accept": True,
        "allowed_chats": [],
        "wake_keywords": "哦小鲸,deepseek,鲸鲸,小鲸,大鲸",
    },
    adapter_display_name="微信群手机桥接",
    support_streaming_message=False,
)
class WechatPhoneBridgePlatform(Platform):
    def __init__(self, config: dict, settings: dict, event_queue) -> None:
        super().__init__(config, event_queue)
        pc = config or {}
        self.host = str(pc.get("ws_host") or "0.0.0.0")
        self.port = int(pc.get("ws_port") or 6199)
        self.token = str(pc.get("token") or "")
        self.auto_accept = bool(pc.get("auto_accept", True))
        self.allowed = {str(x) for x in (pc.get("allowed_chats") or [])}
        raw_kw = pc.get("wake_keywords") or "哦小鲸,deepseek,鲸鲸,小鲸,大鲸"
        if isinstance(raw_kw, list):
            parts = [str(k) for k in raw_kw]
        else:
            parts = str(raw_kw).replace("，", ",").replace("、", ",").split(",")
        self.wake_keywords = [k.strip().lower() for k in parts if k.strip()]
        self._clients: set = set()
        self._outbox: list = []  # (ts, payload) while no collector is attached
        # durable msg_id dedup: survives AstrBot restarts so the same message
        # (stable text-hash id from the collector) is never re-injected as new
        self._seen_file = os.path.join(os.getcwd(), "data", "wxb_seen.json")
        st = self._load_seen()
        self._seen: dict[str, float] = st["seen"]
        self._answered: dict[str, float] = st["answered"]

    def _load_seen(self) -> dict:
        try:
            with open(self._seen_file, encoding="utf-8") as f:
                raw = json.load(f)
            now = time.time()
            if isinstance(raw, dict) and "seen" in raw:
                seen = {k: v for k, v in raw["seen"].items() if now - v < 86400}
                ansr = {k: v for k, v in raw.get("answered", {}).items() if now - v < 86400}
                return {"seen": seen, "answered": ansr}
            # legacy flat format {mid: ts}
            flat = {k: v for k, v in raw.items() if now - v < 86400} if isinstance(raw, dict) else {}
            return {"seen": flat, "answered": {}}
        except Exception:
            return {"seen": {}, "answered": {}}

    def _save_seen(self) -> None:
        try:
            seen = dict(sorted(self._seen.items(), key=lambda kv: -kv[1])[:500])
            ansr = dict(sorted(self._answered.items(), key=lambda kv: -kv[1])[:500])
            with open(self._seen_file + ".tmp", "w", encoding="utf-8") as f:
                json.dump({"seen": seen, "answered": ansr}, f)
            os.replace(self._seen_file + ".tmp", self._seen_file)
        except Exception:
            pass

    # ---- lifecycle -------------------------------------------------------
    def run(self):
        """Platform contract: return a coroutine object. Actual serving starts there."""
        return self._serve()

    async def _serve(self) -> None:
        try:
            from websockets.asyncio.server import serve
        except Exception:
            from websockets import serve  # type: ignore

        async def handler(ws):
            req = getattr(ws, "request", None)
            q = ""
            if req is not None:
                # websockets 15: Request.path carries the full request target incl. query
                path = str(getattr(req, "path", "") or "")
                url = getattr(req, "url", None)
                if "?" not in path and url is not None:
                    path = f"{getattr(url, 'path', '') or ''}?{getattr(url, 'query', '') or ''}"
                q = path.split("?", 1)[1] if "?" in path else ""
            elif hasattr(ws, "path"):
                p = str(ws.path or "")
                q = p.split("?", 1)[1] if "?" in p else ""
            tok = dict(p.split("=", 1) for p in q.split("&") if "=" in p).get("token", "")
            if self.token and tok != self.token:
                await ws.close(code=4401)
                return
            self._clients.add(ws)
            logger.info("[wxb] collector connected, clients=%d", len(self._clients))
            # flush anything that piled up while the collector was away (10-min TTL)
            now2 = time.time()
            pending = [p for (ts, p) in self._outbox if now2 - ts < 600]
            self._outbox.clear()
            for p in pending:
                try:
                    await ws.send(p)
                    logger.info("[wxb] flushed queued reply")
                except Exception:
                    break
            try:
                async for raw in ws:
                    await self._on_frame(raw)
            finally:
                self._clients.discard(ws)

        self._server = await serve(handler, self.host, self.port, max_size=2_000_000)
        logger.info("[wxb] ws listening on %s:%d", self.host, self.port)

    async def terminate(self) -> None:
        srv = getattr(self, "_server", None)
        if srv is not None:
            try:
                srv.close()
                await srv.wait_closed()
            except Exception:
                pass

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            id=str(self.config.get("id") or "wechat_phone_bridge"),
            name="wechat_phone_bridge",
            description="微信群手机桥接",
        )

    def create_event(self, message):
        return WxBridgeMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            platform=self,
        )

    # ---- inbound ---------------------------------------------------------
    async def _on_frame(self, raw) -> None:
        try:
            frame = json.loads(raw)
        except Exception:
            return
        t = frame.get("t")
        if t == "inbound":
            mid = str(frame.get("msg_id") or "")[:64] or uuid.uuid4().hex
            now = time.time()
            ans_ts = self._answered.get(mid)
            if ans_ts is not None and now - ans_ts < 86400:
                logger.info("[wxb] msg %s already answered, ignored", mid[:12])
                return
            seen_ts = self._seen.get(mid)
            if seen_ts is not None and now - seen_ts < 90:
                logger.info("[wxb] duplicate msg %s ignored (in-flight)", mid[:12])
                return
            # seen long ago but never answered (reply lost / crash mid-flight):
            # accept the resend so the mention gets its answer
            self._seen[mid] = now
            self._save_seen()
            group = str(frame.get("group") or "").strip()
            sender = str(frame.get("sender") or "").strip()
            text = str(frame.get("text") or "").strip()
            kind = str(frame.get("kind") or ("group" if group else "user"))
            chat_name = group or sender
            if not text:
                return
            if not self.auto_accept and chat_name not in self.allowed:
                return
            abm = AstrBotMessage()
            abm.self_id = self.meta().id
            abm.type = MessageType.GROUP_MESSAGE if kind == "group" else MessageType.FRIEND_MESSAGE
            abm.session_id = f"{kind}:{chat_name}"
            abm.sender = MessageMember(user_id=f"{chat_name}|{sender or 'unknown'}", nickname=sender or chat_name or "未知")
            abm.message_str = text
            abm.message = [Plain(text)]
            wake = bool(frame.get("at"))
            if not wake and abm.type == MessageType.GROUP_MESSAGE and self.wake_keywords:
                low = text.lower()
                if any(kw in low for kw in self.wake_keywords):
                    wake = True
                    logger.info("[wxb] keyword wake in group %s: %s", group, text[:40])
            if wake and abm.type == MessageType.GROUP_MESSAGE:
                # explicit @mention or name-drop -> mark as addressed so pipeline wakes
                try:
                    from astrbot.api.message_components import At
                    abm.message.insert(0, At(qq=abm.self_id, name=""))
                except Exception:
                    pass
            abm.message_id = mid
            abm.timestamp = int(frame.get("ts") or now)
            abm.raw_message = frame
            self.commit_event(self.create_event(abm))
        elif t == "ack":
            logger.debug("[wxb] ack %s ok=%s err=%s", frame.get("msg_id"), frame.get("ok"), frame.get("err"))

    # ---- outbound --------------------------------------------------------
    async def send_by_session(self, session: MessageSesion, message_chain: MessageChain,
                              reply_to: str | None = None, src_mid: str | None = None,
                              reply_sender: str | None = None) -> None:
        parts = []
        for comp in message_chain.chain:
            if isinstance(comp, Plain):
                parts.append(comp.text)
        body = "\n".join(p for p in parts if p and p.strip()).strip()
        if not body:
            return
        sid = str(session.session_id)
        kind, _, target = sid.partition(":")
        payload = {
            "t": "send",
            "target": {"kind": kind or "user", "name": target},
            "text": body[:1500],
            "msg_id": uuid.uuid4().hex,
            "reply_to": (reply_to or "")[:200] or None,
            "reply_sender": (reply_sender or "")[:30] or None,
            "src_mid": src_mid or None,
        }
        if src_mid:
            self._answered[src_mid] = time.time()
            self._save_seen()
        await self._broadcast(json.dumps(payload, ensure_ascii=False))

    async def _broadcast(self, data: str) -> None:
        if not self._clients:
            self._outbox.append((time.time(), data))
            if len(self._outbox) > 20:
                self._outbox = self._outbox[-20:]
            logger.info("[wxb] no collector attached, reply queued (%d pending)", len(self._outbox))
            return
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)
