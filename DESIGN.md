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
