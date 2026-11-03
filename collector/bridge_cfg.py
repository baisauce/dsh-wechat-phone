# -*- coding: utf-8 -*-
"""bridge_cfg.py - single source of truth for reading the collector config + bridge token.

Every entry point (main.py, preflight.py, replay_*.py, trigger.py, reply-now.py,
debug-quote.py, _dup.py) must use these helpers, otherwise one config layout
breaks half the tools. Historically the one-shot tools did
`open(cfg["bridge_token_file"])`, which explodes now that inline tokens are the
recommended route (that key may be "").

Token precedence (identical everywhere):
    $BRIDGE_TOKEN  >  bridge_token_file (only if that file exists)  >  inline bridge_token

Never print a token: report lengths or match/no-match only.
"""
from __future__ import annotations

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CFG = os.path.join(HERE, "config.json")

_TITLE_COUNT = re.compile(r"[（(]\d+[)）]\s*$")


def norm_title(t: str) -> str:
    """Session title as the collector keys it: no spaces, no trailing member count.

    WeChat shows group titles with a live "(12)" suffix that changes whenever
    someone joins, so allowed_chats/home_chat must be compared after stripping it.
    """
    return _TITLE_COUNT.sub("", str(t or "").replace(" ", ""))


def load_config(path: str = "") -> dict:
    """Read config.json (utf-8-sig tolerated). Empty path -> collector/config.json."""
    return json.load(open(path or DEFAULT_CFG, encoding="utf-8-sig"))


def resolve_token(cfg: dict) -> str:
    """Bridge token, same order for every tool. '' means 'not configured'."""
    env = (os.environ.get("BRIDGE_TOKEN") or "").strip()
    if env:
        return env
    tok_file = (cfg.get("bridge_token_file") or "").strip()
    if tok_file and os.path.exists(tok_file):
        try:
            with open(tok_file, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""
    return str(cfg.get("bridge_token") or "").strip()


def token_source(cfg: dict) -> str:
    """Where the token came from - for logs/hints only, never the value."""
    if (os.environ.get("BRIDGE_TOKEN") or "").strip():
        return "env BRIDGE_TOKEN"
    tok_file = (cfg.get("bridge_token_file") or "").strip()
    if tok_file and os.path.exists(tok_file):
        return f"file {tok_file}"
    if str(cfg.get("bridge_token") or "").strip():
        return "inline bridge_token"
    return "MISSING"


def astrbot_platform_cfg(cfg: dict, platform_type: str = "wechat_phone_bridge") -> dict:
    """Read AstrBot's own platform entry for this adapter, WITHOUT touching AstrBot.

    AstrBot stores platform configs FLAT in data/cmd_config.json -> platform[]
    (keys like ws_port/token/auto_accept/allowed_chats sit next to id/type).
    Path order: config.json "astrbot_config" -> <repo parent>/data/cmd_config.json.
    Returns {} when nothing readable - callers must treat that as 'unknown', not 'bad'.
    """
    candidates = []
    explicit = (cfg.get("astrbot_config") or "").strip() if isinstance(cfg, dict) else ""
    if explicit:
        candidates.append(explicit)
    root = os.path.dirname(HERE)
    candidates.append(os.path.join(os.path.dirname(root), "data", "cmd_config.json"))
    for path in candidates:
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        for entry in (data.get("platform") or []):
            if isinstance(entry, dict) and entry.get("type") == platform_type:
                return entry
        return {}
    return {}
