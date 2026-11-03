# -*- coding: utf-8 -*-
"""wechat_ui.py — parse uiautomator XML for the pieces the collector needs.

WeChat resource-ids are obfuscated and rotate between versions, so everything
here is structural (class + geometry + text), not id-based.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree import ElementTree


@dataclass
class Node:
    text: str
    desc: str
    cls: str
    left: int
    top: int
    right: int
    bottom: int
    scrollable: bool

    @property
    def cx(self) -> int:
        return (self.left + self.right) // 2

    @property
    def cy(self) -> int:
        return (self.top + self.bottom) // 2

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def parse(xml: str) -> list[Node]:
    nodes: list[Node] = []
    try:
        root = ElementTree.fromstring(xml.encode("utf-8", "ignore"))
    except ElementTree.ParseError:
        return nodes
    for el in root.iter("node"):
        b = _BOUNDS.match(el.get("bounds", ""))
        if not b:
            continue
        l, t, r, bo = map(int, b.groups())
        if r <= l or bo <= t:
            continue
        nodes.append(Node(
            text=(el.get("text") or "").strip(),
            desc=(el.get("content-desc") or "").strip(),
            cls=el.get("class") or "",
            left=l, top=t, right=r, bottom=bo,
            scrollable=el.get("scrollable") == "true",
        ))
    return nodes


def find_edit_text(nodes: list[Node]) -> Node | None:
    for n in nodes:
        if "EditText" in n.cls:
            return n
    return None


def find_conversation(nodes: list[Node], title: str) -> Node | None:
    """Home-list row whose first-line text equals the chat title."""
    best: Node | None = None
    for n in nodes:
        if n.text == title and n.width > 60:
            if best is None or n.left < best.left:  # prefer name over last-msg copy
                best = n
    if best is None:  # tolerate trailing badges like "17:05" glued into text
        for n in nodes:
            if n.text.startswith(title) and len(n.text) <= len(title) + 12:
                best = n
                break
    return best


_TIME_RE = re.compile(
    r"^(\d{1,2}:\d{2}|昨天 \d{1,2}:\d{2}|星期. \d{1,2}:\d{2}|\d{1,2}月\d{1,2}日.*|.+ \d{1,2}:\d{2})$"
)


def extract_messages(nodes: list[Node], screen_w: int) -> list[dict]:
    """Visible chat-window messages, oldest-first.

    Heuristic per WeChat layout:
      - message texts are TextViews inside the big scrollable container
      - own bubbles are right-aligned (center x > 62% of width)
      - group sender name is a short TextView directly above a left bubble
      - centered time separators are skipped
    """
    # container = scrollable node with the largest area
    containers = [n for n in nodes if n.scrollable and n.height > screen_w]
    if not containers:
        return []
    cont = max(containers, key=lambda n: n.width * n.height)

    in_zone = [
        n for n in nodes
        if "TextView" in n.cls and n.text and cont.left <= n.left and n.right <= cont.right + 40
        and cont.top <= n.top and n.bottom <= cont.bottom + 40
    ]
    in_zone.sort(key=lambda n: n.top)

    msgs: list[dict] = []
    pending_sender: str | None = None
    for n in in_zone:
        center = (n.left + n.right) / 2
        is_self = center > screen_w * 0.62
        is_time = bool(_TIME_RE.match(n.text)) and abs(center - screen_w / 2) < screen_w * 0.18
        is_system = ("撤回" in n.text or "加入了群聊" in n.text or "成为新群主" in n.text) and abs(center - screen_w / 2) < screen_w * 0.18
        if is_time or is_system:
            continue
        # short left-aligned label above a bubble = sender name
        if (not is_self) and n.width < screen_w * 0.45 and len(n.text) <= 24:
            nxt = next((m for m in in_zone if m.top > n.top and m.top - n.bottom < 8), None)
            if nxt is not None and nxt.height < 8:
                pass  # too tight to be a bubble; ignore label logic below
        if (not is_self) and n.height < 45 and len(n.text) <= 24:
            # candidate sender label; the real bubble follows within ~100px
            following = [m for m in in_zone if 0 < m.top - n.bottom < 100 and m.height >= 40]
            if following:
                pending_sender = n.text
                continue
        msgs.append({
            "text": n.text,
            "sender": None if is_self else (pending_sender or ""),
            "is_self": is_self,
            "y": n.top,
        })
        pending_sender = None
    return msgs


def is_home_list(nodes: list[Node]) -> bool:
    """Rough check: WeChat main tab list shows the 4 bottom tabs."""
    labels = {n.text for n in nodes if n.height < 60 and n.text}
    return {"微信", "通讯录"}.issubset(labels) or {"微信", "通讯录", "我"}.issubset(labels)


def unread_badges(nodes: list[Node]) -> dict[str, str]:
    """Chat title -> badge text, for diagnostics."""
    out: dict[str, str] = {}
    for n in nodes:
        if n.desc and "条未读" in n.desc:
            out[n.desc] = n.text
    return out
