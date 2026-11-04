# -*- coding: utf-8 -*-
"""ocr_channel.py — screenshot + RapidOCR reading path.

WeChat 8.0.7x actively blanks the uiautomator accessibility tree, so the
primary structural channel is dead on WeChat windows. This module reads the
same information from pixels instead. Coordinates are screen pixels.
"""
from __future__ import annotations

import io
import re
import time
from dataclasses import dataclass

import numpy as np
from PIL import Image

_ENGINE = None  # lazy singleton: RapidOCR init costs ~2s


@dataclass
class Line:
    cx: float
    cy: float
    text: str
    conf: float
    left: float = 0.0
    right: float = 0.0
    top: float = 0.0
    bottom: float = 0.0


def _engine():
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
    return _ENGINE


def ocr_png(png_bytes: bytes) -> list[Line]:
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    arr = np.asarray(img)[:, :, ::-1].copy()
    res, _ = _engine()(arr)
    lines: list[Line] = []
    for box, text, conf in res or []:
        text = str(text).strip()
        if not text or float(conf) < 0.6:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        lines.append(Line((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, text, float(conf),
                          min(xs), max(xs), min(ys), max(ys)))
    lines.sort(key=lambda l: l.cy)
    return lines


# ---- structural guesses ---------------------------------------------------
_TIME_RE = re.compile(
    r"^(\d{1,2}:\d{2}|昨天\s*\d{1,2}:\d{2}|星期[一二三四五六日]\s*\d{1,2}:\d{2}"
    r"|\d{1,2}月\d{1,2}日.*|\d{4}年\d{1,2}月\d{1,2}日.*)$"
)
_SENDER_PREFIX_RE = re.compile(r"^([^:：]{1,24})[:：](.+)$")

# WeChat stamps a chat with relative day labels ("Tue 18:32", "Yesterday 23:51",
# "昨天 09:12", "11月3日"). They are the ONLY age signal the OCR channel has, and
# without them a window parked hours in the past looks exactly like a live one:
# 2026-11-05 an accidental scroll back to Tuesday made the collector answer
# six-hour-old messages as if they had just arrived. Parsing the stamps turns
# "is this fresh?" into a fact the live path can check.
_WEEK_EN = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_WEEK_CN = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_TIME_LABEL_RES = (
    (re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日(?:.*?(\d{1,2}):(\d{2}))?$"), "ymd"),
    (re.compile(r"^(\d{1,2})月(\d{1,2})日(?:.*?(\d{1,2}):(\d{2}))?$"), "md"),
    (re.compile(r"^(?:昨天|yesterday)\s*(\d{1,2}):(\d{2})$", re.I), "yesterday"),
    (re.compile(r"^星期([一二三四五六日天])\s*(\d{1,2}):(\d{2})$"), "weekday"),
    (re.compile(r"^(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\s*(\d{1,2}):(\d{2})$", re.I),
     "weekday_en"),
    (re.compile(r"^(\d{1,2}):(\d{2})$"), "clock"),
)


def parse_time_label(text: str, now: float | None = None) -> float | None:
    """Approximate unix ts of a chat time separator, or None if it is not one.

    Deliberately forgiving: callers only ever ask "older than N hours?", so a
    wrong guess of +/-1 week on an odd OCR string is harmless, and a missed label
    just means 'age unknown' (the caller then treats the message as live).
    """
    t = (text or "").replace(" ", "").strip()
    if not t:
        return None
    now = time.time() if now is None else now
    base = time.localtime(now)
    midnight = now - (base.tm_hour * 3600 + base.tm_min * 60 + base.tm_sec)
    for rx, kind in _TIME_LABEL_RES:
        m = rx.match(t)
        if not m:
            continue
        g = m.groups()
        try:
            if kind == "ymd":
                return time.mktime((int(g[0]), int(g[1]), int(g[2]),
                                    int(g[3] or 0), int(g[4] or 0), 0, 0, 0, -1))
            if kind == "md":
                hh, mi = int(g[2] or 0), int(g[3] or 0)
                ts = time.mktime((base.tm_year, int(g[0]), int(g[1]), hh, mi, 0, 0, 0, -1))
                if ts > now + 86400:          # Jan 2 read on Dec 31: last year
                    ts = time.mktime((base.tm_year - 1, int(g[0]), int(g[1]),
                                      hh, mi, 0, 0, 0, -1))
                return ts
            if kind == "yesterday":
                return midnight - 86400 + int(g[0]) * 3600 + int(g[1]) * 60
            if kind in ("weekday", "weekday_en"):
                wd = _WEEK_CN.get(g[0], _WEEK_EN.get(g[0].lower()))
                if wd is None:
                    continue
                hh, mi = int(g[1]), int(g[2])
                return midnight - ((base.tm_wday - wd) % 7) * 86400 + hh * 3600 + mi * 60
            if kind == "clock":
                hh, mi = int(g[0]), int(g[1])
                ts = midnight + hh * 3600 + mi * 60
                if ts > now + 1800:            # a future clock time = yesterday's
                    ts -= 86400
                return ts
        except (ValueError, OverflowError):
            continue
    return None


def is_home(lines: list[Line], w: int, h: int) -> bool:
    labels = {l.text for l in lines if l.cy > h * 0.93}
    return ("微信" in labels or "通讯录" in labels)


def find_conversation_row(lines: list[Line], title: str, w: int) -> Line | None:
    """A list row whose name line equals/starts with title (left side, below top bar)."""
    best: Line | None = None
    for l in lines:
        if l.cy > 150 and l.cx < w * 0.62:
            t = l.text.replace(" ", "")
            if t == title or (t.startswith(title) and len(t) <= len(title) + 10):
                best = l
                break
    return best


def extract_chat_messages(lines: list[Line], w: int, h: int,
                          bot_names: list[str] | None = None) -> list[dict]:
    """Chat-window bubbles oldest-first, label-tracking state machine.

    Geometry alone cannot separate long left bubbles from short right ones
    (both can end at ~0.81w). Reliable signals instead:
      - group senders get a small-font name label above their FIRST bubble
      - left bubbles always START near the bubble's left padding (~0.19w)
      - own bubbles are right-aligned: text left edge pushed right (>0.24w)
      - continuation lines of a multi-line bubble sit <80px below the previous
    """
    # Bottom limit: WeChat pins the newest bubble just above the input bar, so a flat
    # 0.86h cut silently drops the one message that matters most (measured on a 1080x2412
    # phone: newest bubble at 0.90h, its sender label at 0.87h - both outside the window,
    # so the last message in a quiet group was never read at all). Take the deeper of
    # 0.86h and (h - 190): tall screens gain coverage, short ones keep the old behaviour,
    # and the 190px guard band keeps the input bar / an unsent draft out of the reading zone.
    body_bottom = max(h * 0.86, h - 190)
    body = sorted((l for l in lines if 200 < l.cy < body_bottom), key=lambda l: l.cy)
    raw: list[dict] = []
    pending_sender: str | None = None
    last_ts: float | None = None      # time separator directly above the next bubble
    now_ts = time.time()

    def age_of() -> float | None:
        """Seconds from this bubble's stamp to now; None when no stamp was seen."""
        return None if last_ts is None else max(0.0, now_ts - last_ts)

    i, n = 0, len(body)
    while i < n:
        l = body[i]
        s = l.text.strip()
        i += 1
        stamp = parse_time_label(s, now_ts)
        if stamp is not None:
            last_ts = stamp
            continue
        if (abs(l.cx / w - 0.5) < 0.10 and l.left > w * 0.30
                and l.right < w * 0.72 and len(s) <= 30):
            continue  # centered system note ("xx joined" etc.)
        nxt = next((x for x in body[i:] if 0 < x.cy - l.cy < 95), None)
        is_label = (l.bottom - l.top) < 46 and l.cx < w * 0.30 and len(s) <= 20
        if is_label:
            pending_sender = s if nxt is not None else None  # dangling label at bottom: drop
            continue
        # quote line inside a bubble ("name: quoted text", small font, indented,
        # sits right below the member's own text) -> append to that message
        mm = _SENDER_PREFIX_RE.match(s)
        if (raw and mm and (l.bottom - l.top) < 52 and l.left > w * 0.18
                and 0 < l.cy - raw[-1]["y"] < 120):
            raw[-1]["text"] += " " + s
            raw[-1]["y"] = l.cy
            continue
        m = _SENDER_PREFIX_RE.match(s)
        if m and l.left < w * 0.30 and len(m.group(1)) <= 24:
            raw.append({"text": m.group(2).strip(), "sender": m.group(1).strip(),
                        "is_self": False, "y": l.cy, "age_s": age_of()})
            pending_sender = None
            continue
        if pending_sender is not None:
            is_self = False                      # bubble directly under a name label
            sender = pending_sender
        elif raw and 0 < l.cy - raw[-1]["y"] < 80:
            is_self = raw[-1]["is_self"]         # continuation line of same bubble
            sender = raw[-1]["sender"] or ""     # inherit side AND sender for merging
        else:
            is_self = l.left > w * 0.24          # fresh bubble: left-margin decides side
            sender = ""
        raw.append({"text": s, "sender": None if is_self else sender,
                    "is_self": is_self, "y": l.cy, "age_s": age_of()})
        pending_sender = None
    # merge multi-line bubbles into single messages
    merged: list[dict] = []
    for m in raw:
        prev = merged[-1] if merged else None
        same_side = prev is not None and m["is_self"] == prev["is_self"]
        same_sender = prev is not None and (m["sender"] or "") == (prev["sender"] or "")
        close = prev is not None and 0 < m["y"] - prev["y"] < 80
        if prev is not None and same_side and same_sender and close:
            prev["text"] += m["text"]
            prev["y"] = m["y"]  # advance so a 3rd+ continuation line still chains
        else:
            merged.append(dict(m))
    # quote-artifact pass: a message "sent by" one of OUR nicknames that isn't
    # self is really a member quoting us (merge failed upstream). Merge into the
    # previous member bubble, or keep as an explicit quote-reply.
    if bot_names:
        fixed: list[dict] = []
        for m in merged:
            if not m["is_self"] and (m["sender"] or "") in bot_names:
                prev = fixed[-1] if fixed else None
                if prev is not None and not prev["is_self"] and 0 < m["y"] - prev["y"] < 150:
                    prev["text"] += f" {m['sender']}: {m['text']}"
                    prev["y"] = m["y"]
                else:
                    m = dict(m)
                    m["text"] = f"{m['sender']}: {m['text']}"
                    m["sender"] = "群友(引用我)"
                continue
            fixed.append(m)
        merged = fixed
    return merged


def chat_input_point(w: int, h: int) -> tuple[int, int]:
    """Center of the WeChat input bar. NEVER the far-left column (voice/keyboard
    toggle icon lives there; tapping it switches WeChat into hold-to-talk mode)."""
    return int(w * 0.40), h - 80


_TITLE_NORM_RE = re.compile(r"[（(]\s*\d+\s*[)）]\s*$")
LIST_HEADER_TEXTS = {"微信", "weixin", "wechat", "chats", "消息"}
NON_CHAT_HEADERS = {"通讯录", "联系人", "我", "discover", "发现", "设置", "settings",
                    "公众号", "服务", "widgets", "me"}


def top_title(lines: list[Line], w: int) -> str:
    """The centered title in the top bar (chat name / '微信' / section name)."""
    for l in lines:
        if l.cy < 215 and 0.25 * w < l.cx < 0.75 * w and len(l.text) <= 30:
            return l.text.replace(" ", "")
    return ""


def is_list_header(title: str) -> bool:
    return _TITLE_NORM_RE.sub("", title.lower()).strip() in LIST_HEADER_TEXTS


def is_non_chat_page(title: str) -> bool:
    return title.lower() in NON_CHAT_HEADERS


def list_rows(lines: list[Line], w: int, h: int) -> list[dict]:
    """Group conversation-list OCR lines into rows: {title, preview, time, y}.

    Layout per row: name line (left), time (right, same y), preview (below name).
    Unread badges are pure-digit short lines at the far left -> never a title.
    """
    cand = [l for l in lines if 230 < l.cy < h * 0.90]
    rows: list[dict] = []
    used: set[int] = set()
    for i, l in enumerate(cand):
        if i in used or l.cx > w * 0.62 or len(l.text) > 32:
            continue
        if _TIME_RE.match(l.text.strip()) or re.fullmatch(r"\d{1,4}", l.text):
            continue  # time separator or unread badge
        if l.cx < w * 0.20:
            continue  # badge zone on the left edge
        preview = ""
        when = ""
        j = i + 1
        while j < len(cand) and cand[j].cy - l.cy < 100:
            nx = cand[j]
            if nx.cx > w * 0.75 and abs(nx.cy - l.cy) < 45 and not preview:
                when = nx.text
                used.add(j)
            elif 20 < nx.cy - l.cy < 90 and nx.cx < w * 0.72 and not preview:
                preview = nx.text
                used.add(j)
            j += 1
        if preview:
            title = _TITLE_NORM_RE.sub("", l.text.replace(" ", ""))
            # unread red badge: a pure-digit line at the far left of this row
            badge = 0
            for b in cand:
                if (b is not l and re.fullmatch(r"\d{1,3}", b.text) and b.cx < w * 0.20
                        and abs(b.cy - l.cy) < 45):
                    try:
                        badge = int(b.text)
                    except ValueError:
                        pass
                    break
            rows.append({"title": title, "preview": preview, "time": when, "y": l.cy, "badge": badge})
    return rows
