> ⚠️ **历史初稿（2026-10-31），勿按此安装或开发。** 本设计中"手机端 Kotlin 采集 App + Accessibility 输入"与"AstrBot Open API 直连"两条路线后来都被推翻，实际定稿是 **PC 侧 Python 采集器（ADB+OCR）+ AstrBot 平台适配器插件**。文中 WS 消息协议思想仍有效但细节有出入——一切以 README 正文与附录 C/D 为准。保留本文仅供了解设计演进。

"""WeChat Phone Bridge — design notes & runtime contract.

Goal: 微信群全自动收发 for AstrBot, driven by a dedicated Android phone
       running the official WeChat app. NO client injection / NO hooks:
       - inbound : NotificationListenerService (user-granted) + Accessibility node reads
       - outbound: same accessibility layer types/pastes into the real UI
       All traffic stays on LAN; zero VPN / zero public network at runtime.

Components
----------
1. bridge/ (this folder)  Python service, runs on PC inside AstrBot's embedded python.
   - ws_server.py   WebSocket hub for the collector App (LAN only, token auth)
   - gate.py        humanization engine: per-session windows, daily caps, quiet hours,
                    jittered delays, "typing" simulation hints, drop policy
   - astrbot_api.py client for AstrBot Open API (/api/v1/auth/login, /api/v1/im/messages)
   - sessions.py    chat-title <-> session registry (which groups/people are enabled)
   - dedup.py       notification-id + content-hash dedup
   - main.py        wiring + watchdog-friendly single loop
2. adapter plugin (astrbot platform adapter, later step) OR direct Open-API mode:
   MVP uses Open-API send to UMO `wechat_group_bridge:GroupMessage:<group_key>`
   once our custom platform adapter exists, bridge switches to event injection
   so LivingMemory/persona pipeline treats it like any IM.
3. collector/ (Kotlin app source, later step) installed on the phone.

Wire protocol (JSON over WS, PC side is server on :6199):
  app -> pc  {t:"inbound", group, sender, text, ts, msg_id}
             {t:"reply_req", ...} not used; replies flow from AstrBot
             {t:"ack", msg_id, ok, err}
             {t:"state", screen:"chat|other|locked", typing:bool}
  pc  -> app  {t:"send", target:{kind:"group|user", name}, text, delay_ms, typing_hint}
             {t:"open_chat", name, kind}
             {t:"ping"}
Safety rails enforced in gate.py BEFORE anything reaches the phone.
"""
