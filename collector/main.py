# -*- coding: utf-8 -*-
"""main.py — WeChat ADB collector, RESIDENT-GROUP mode.

The phone lives inside one chat (home_chat, default "示例家庭群"). Loop:
  ensure screen is in that chat -> OCR -> cursor-diff new messages ->
  forward only @-mentions / wake-keyword hits to the AstrBot bridge ->
  reply_worker types answers back into the same window.

No list navigation, no row hunting, no scrolling backlog: the window is home.

Usage:
  python main.py                # normal run (device attached)
  python main.py --selftest     # protocol test against bridge, no adb
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import random
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from adb_client import Adb, AdbError  # noqa: E402
from gate import Gate  # noqa: E402
import ocr_channel as oc  # noqa: E402

try:
    import websockets
except ImportError:
    print("websockets missing: python -m pip install websockets")
    raise SystemExit(1)

log = logging.getLogger("collector")

_TITLE_NORM = re.compile(r"[（(]\d+[)）]\s*$")
_PUNCT_STRIP = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def norm_text(t: str) -> str:
    """OCR-stable key basis: drop punctuation/space noise (它对。/它对· -> same)."""
    return _PUNCT_STRIP.sub("", t)[:40]


def msg_key(chat: str, m: dict, prev_text: str = "") -> str:
    # context-aware: same sender+text at a different position (newer predecessor)
    # is a NEW occurrence (repeated "@鲸鲸"), while restart re-scans of the same
    # position still hash identically and stay deduped.
    raw = (f"{chat}|{m.get('sender','')}|{norm_text(m.get('text',''))}"
           f"|{norm_text(prev_text)[:16]}")
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def msg_fp(chat: str, m: dict) -> str:
    """OCR-jitter-stable fingerprint: head+tail of normalized text only.
    Line-split differences (multi-line bubbles, dropped quote lines) keep the
    same fingerprint, so one real message can never be answered twice."""
    t = norm_text(m.get("text", ""))
    tail = t[-8:] if len(t) > 22 else ""
    raw = f"{chat}|{t[:14]}|{tail}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def norm_title(t: str) -> str:
    return _TITLE_NORM.sub("", t.replace(" ", ""))


_SENT_END = "。！？!?～~…"
_PUNCT_KEEP = "。！？!?～~…，,、;；："


def flatten_reply(text: str) -> str:
    """Collapse LLM line breaks into ONE natural WeChat line.

    The persona tends to draft 'paragraphs' with \\n\\n; on a phone chat those
    breaks look machine-made (2026-11-03 feedback: no newlines inside a reply).
    Segments after sentence-final punctuation join directly, otherwise with a
    comma — everything stays one single line."""
    parts = [p.strip() for p in re.split(r"[ \t]*\n+[ \t]*", text) if p.strip()]
    if not parts:
        return ""
    out = parts[0]
    for p in parts[1:]:
        out += p if out[-1] in _PUNCT_KEEP else "，" + p
    return out


class Collector:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.adb = Adb(cfg["adb_path"], cfg.get("serial") or None)
        self.home = norm_title(cfg.get("home_chat", "示例家庭群"))
        self.nicknames = [str(x) for x in cfg.get("bot_nicknames", ["小鲸"])]
        self.wake_kw = [str(x).lower() for x in cfg.get("wake_keywords", [])]
        self.poll = float(cfg.get("list_poll_s", 5.0))
        self.gate = Gate(cfg, os.path.join(ROOT, "PAUSE"))
        bridge = cfg["bridge_ws"]
        tok_file = cfg.get("bridge_token_file")
        self.token = open(tok_file).read().strip() if tok_file and os.path.exists(tok_file) else cfg.get("bridge_token", "")
        self.bridge_url = f"{bridge}?token={self.token}" if self.token else bridge

        self._ws = None
        self._replies: asyncio.Queue = asyncio.Queue()
        self._ui_lock = asyncio.Lock()
        self._cursor: str = ""            # normalized newest-seen text in home chat
        self._seen: dict[str, float] = {}  # msgkey -> ts (TTL-pruned)
        self._self_sent: set[str] = set()
        self._reply_sent_ts = 0.0
        self._started = False
        self._quote_texts: list[str] = []   # @-messages forwarded in current batch
        self._backlog: list[dict] = []      # startup history @-mentions, answered one-by-one
        self._history_answered: set[str] = set()
        self._fp_answered: set[str] = set()   # OCR-stable fingerprints already answered
        self._fp_recent: dict[str, float] = {}  # fp -> last forward ts (15min window)
        self._mid_fp: dict[str, str] = {}    # sent msg_id -> fp (for answer marking)
        self._fp_inflight: dict[str, tuple] = {}  # fp -> (ts, batch): cross-path dup claim
        self._batch_seq = 0
        self._self_full: list[str] = []      # untruncated norms of my own bubbles
        self._self_fps: set[str] = set()     # fingerprints of self-side bubbles seen
        self._recovery_done = False
        self._state_file = os.path.join(HERE, "state.json")
        self._load_state()

    def _load_state(self) -> None:
        """Persist cursor/seen across restarts so a restart never re-forwards old @s."""
        try:
            st = json.load(open(self._state_file, encoding="utf-8"))
            self._cursor = st.get("cursor", "")
            self._seen = {k: v for k, v in (st.get("seen") or {}).items()
                          if time.time() - v < 86400}
            self._self_sent = set(st.get("self_sent") or [])
            self._fp_answered = set(st.get("fp_answered") or [])
            self._fp_recent = {k: v for k, v in (st.get("fp_recent") or {}).items()
                               if time.time() - v < 86400}
            self._history_answered = set(st.get("history_answered") or [])
            self._mid_fp = {k: v for k, v in (st.get("mid_fp") or {}).items()}
            self._self_full = list(st.get("self_full") or [])
            self._self_fps = set(st.get("self_fps") or [])
            self._started = bool(self._seen)
            if self._started:
                log.info("state restored: cursor=%r, %d seen", self._cursor[:20], len(self._seen))
        except FileNotFoundError:
            pass
        except Exception as e:
            log.warning("state load failed: %s", e)

    def _save_state(self) -> None:
        try:
            json.dump({"cursor": self._cursor, "seen": self._seen,
                       "self_sent": list(self._self_sent)[-100:],
                       "history_answered": list(self._history_answered)[-100:],
                       "fp_answered": list(self._fp_answered)[-200:],
                       "mid_fp": dict(list(self._mid_fp.items())[-60:]),
                       "self_full": self._self_full[-80:],
                       "self_fps": list(self._self_fps)[-150:],
                       "fp_recent": {k: v for k, v in sorted(
                           self._fp_recent.items(), key=lambda kv: -kv[1])[:200]}},
                      open(self._state_file + ".tmp", "w", encoding="utf-8"), ensure_ascii=False)
            os.replace(self._state_file + ".tmp", self._state_file)
        except Exception as e:
            log.warning("state save failed: %s", e)

    # ---- self memory ---------------------------------------------------------
    def _note_self(self, text: str) -> None:
        """Remember a self-side bubble so a later OCR misread (first line of a
        long reply re-seen as a left bubble from 'someone else') can be caught:
        the fragment is then matched as a SUBSTRING of our full text."""
        nf = _PUNCT_STRIP.sub("", text)
        if nf and nf not in self._self_full:
            self._self_full.append(nf)
            if len(self._self_full) > 120:
                self._self_full = self._self_full[-100:]
            self._self_fps.add(msg_fp(self.home, {"text": text}))

    def _is_my_text(self, text: str) -> bool:
        t = norm_text(text)
        if not t:
            return False
        if t in self._self_sent:
            return True
        if msg_fp(self.home, {"text": text}) in self._self_fps:
            return True
        if len(t) >= 5:
            for full in reversed(self._self_full[-60:]):
                if t in full:
                    return True
        return False

    # ---- wake rules --------------------------------------------------------
    _QUOTE_ECHO_RE = re.compile(r"\s([^\s:：@]{1,24})[:：]")

    def _own_text(self, text: str) -> str:
        """Strip the quoted-echo tail (' <someone>：<quoted old msg>') from a merged
        bubble: the echo is someone else's OLD text, its @/keywords must NOT count
        as a fresh call — quoting an already-answered @ used to double-trigger.
        Colon segments at the very start (member's own 'X：...' line) are kept;
        quotes of MY messages wake via _is_quoting_me on the full text."""
        for m in self._QUOTE_ECHO_RE.finditer(text):
            name = m.group(1)
            if any(n in name or name in n for n in self.nicknames):
                continue          # '鲸鲸: ...' segment — quoting me, wake allowed
            return text[:m.start()].strip()
        return text

    def _is_quoting_me(self, text: str) -> bool:
        """A member quoting one of MY messages: merged quote line contains
        '鲸鲸: ...' — semantically a reply to me, deserves an answer back."""
        t = text.replace("＠", "@")
        return any(f"{n}:" in t or f"{n}：" in t for n in self.nicknames)

    def _should_forward(self, text: str) -> bool:
        own = self._own_text(text).replace("＠", "@")
        if any(f"@{n}" in own for n in self.nicknames):
            return True
        if self._is_quoting_me(text):
            return True
        low = own.lower()
        return any(k in low for k in self.wake_kw)

    def _is_at(self, text: str) -> bool:
        own = self._own_text(text).replace("＠", "@")
        return (any(f"@{n}" in own for n in self.nicknames)
                or self._is_quoting_me(text))

    # ---- screen helpers ------------------------------------------------------
    def _in_home_sync(self) -> tuple[bool, list]:
        lines = oc.ocr_png(self.adb.screencap())
        title = norm_title(oc.top_title(lines, self._w))
        return (bool(title) and title == self.home), lines

    def _goto_home_sync(self) -> bool:
        """Return to the home chat WITHOUT ever BACKing out of WeChat:
        on the list page tap the row directly; only BACK from other chat pages."""
        for _ in range(5):
            ok, lines = self._in_home_sync()
            if ok:
                return True
            title = norm_title(oc.top_title(lines, self._w))
            if title and not oc.is_list_header(title) and not oc.is_non_chat_page(title):
                # some other chat page -> BACK lands on the list
                self.adb.keyevent(4)
                time.sleep(1.0)
                continue
            # list page (or unknown screen): find and tap our row by y
            row = next((r for r in oc.list_rows(lines, self._w, self._h)
                        if norm_title(r["title"]) == self.home), None)
            if row is None:
                log.info("home row not visible on list page")
                return False
            self.adb.tap(self._w // 2, int(row["y"]))
            time.sleep(1.5)
            ok, _ = self._in_home_sync()
            if ok:
                return True
            self.adb.keyevent(4)  # tapped wrong thing: one BACK lands on list (not out of app from a chat)
            time.sleep(0.8)
        return False

    # ---- message handling -----------------------------------------------------
    def _prune_seen(self):
        # 24h window, aligned with state.json persistence: the same message
        # (msg_key = text hash) is never re-forwarded across restarts.
        now = time.time()
        for k in [k for k, ts in self._seen.items() if now - ts > 86400]:
            del self._seen[k]
        if len(self._seen) > 1000:  # hard cap: keep newest
            newest = sorted(self._seen.items(), key=lambda kv: -kv[1])[:800]
            self._seen = dict(newest)

    # ---- screen capture seam + upward collection ---------------------------
    def _screen_msgs_sync(self) -> list[dict]:
        """One screen of messages; taps the unread pill first when the view is not at bottom."""
        lines = oc.ocr_png(self.adb.screencap())
        import re as _re
        pill = [l for l in lines
                if _re.search(r"(new messages|条新消息|条消息)", l.text)
                and l.cx > self._w * 0.70 and self._h * 0.45 < l.cy < self._h * 0.85]
        if pill:
            self.adb.tap(int(pill[0].cx), int(pill[0].cy))
            time.sleep(1.0)
            lines = oc.ocr_png(self.adb.screencap())
        return oc.extract_chat_messages(lines, self._w, self._h, bot_names=self.nicknames)

    def _collect_upward_sync(self, max_pages: int) -> list[dict]:
        """Scroll up collecting pages, then return to the bottom.

        Returns messages in chronological order: reverse at PAGE level only
        (oldest page first) while preserving top-to-bottom order WITHIN each
        page — reversing the flat list would scramble message order and make
        the cursor jump backwards, causing missed and duplicate forwards.
        """
        screens: list[list[dict]] = []
        seen_keys: set[str] = set()
        pages_scrolled = 0
        for page in range(max(1, max_pages)):
            msgs = self._screen_msgs_sync()
            # dedup ACROSS pages only; two identical texts on the SAME screen are
            # two real messages (member re-sent) and must both survive
            page_keys = {msg_key(self.home, m) for m in msgs}
            kept = [m for m in msgs if msg_key(self.home, m) not in seen_keys]
            seen_keys |= page_keys
            if kept:
                screens.append(kept)
            if page == 0 or kept:
                self.adb.swipe(self._w // 2, int(self._h * 0.32),
                               self._w // 2, int(self._h * 0.72), 450)
                pages_scrolled += 1
                time.sleep(0.6)
            else:
                break  # no new content: history exhausted
        # return to bottom
        for _ in range(pages_scrolled):
            self.adb.swipe(self._w // 2, int(self._h * 0.72),
                           self._w // 2, int(self._h * 0.32), 350)
            time.sleep(0.4)
        # screens[0] = newest (bottom) page; oldest first overall
        out: list[dict] = []
        for scr in reversed(screens):
            out.extend(scr)
        return out

    def _ensure_bottom_sync(self) -> bool:
        """One silent 'settle to bottom' probe, used ONLY on idle cycles.

        WeChat parks the chat wherever the last finger left it: if a human
        scrolled mid-history, every newer message (including @-mentions) sits
        BELOW the viewport and pure upward catch-up can never reach them
        (2026-11-03 '主人凶你啦' deadlock: cursor stayed visible inside a stale
        window, so 'after cursor' looked empty forever). Swipe once toward the
        newest, compare before/after signatures: unchanged = we were already at
        the bottom; changed = pull again next cycle until it stops moving.
        Cached for 30s so a settled screen is left completely alone."""
        now = time.time()
        if getattr(self, "_bottom_ok", False) and now - getattr(self, "_bottom_ts", 0.0) < 30:
            return True
        try:
            def sig() -> str:
                ls = oc.ocr_png(self.adb.screencap())
                return "|".join(sorted(l.text for l in ls if l.cy > self._h * 0.55)[:6])
            before = sig()
            self.adb.swipe(self._w // 2, int(self._h * 0.80),
                           self._w // 2, int(self._h * 0.30), 300)
            time.sleep(0.8)
            after = sig()
        except Exception:
            return False
        self._bottom_ts, self._bottom_ok = now, (before == after)
        return self._bottom_ok

    async def _handle_screen(self, lines: list) -> bool:
        """Cursor-diff; forward wake-rule hits. Returns True if anything forwarded."""
        msgs = oc.extract_chat_messages(lines, self._w, self._h)
        for m in msgs:
            if m["is_self"]:
                self._note_self(m["text"])
        others = [m for m in msgs if not m["is_self"] and not self._is_my_text(m["text"])]
        self._prune_seen()
        if not self._started:
            # startup: scan a few pages of history for unanswered @s
            self._started = True
            pages = int(self.cfg.get("history_pages", 3))
            if pages > 0:
                hist = await asyncio.to_thread(self._collect_upward_sync, pages)
                for m in hist:
                    if m["is_self"]:
                        self._note_self(m["text"])
                hist_others = [m for m in hist if not m["is_self"]
                               and not self._is_my_text(m["text"])]
                log.info("history scan: %d msgs across pages, %d from others", len(hist), len(hist_others))
                msgs = hist
                others = hist_others
            self._cursor = norm_text(others[-1]["text"]) if others else ""
            for m in msgs:
                self._seen[msg_key(self.home, m)] = time.time()
            log.info("home %r baseline: %d visible, cursor=%r", self.home, len(msgs), self._cursor[:20])
            hits = [m for m in others if self._is_at(m["text"])
                    and msg_key(self.home, m) not in getattr(self, "_history_answered", set())]
            if hits:
                log.info("history has %d unanswered @-mention(s), queueing one-by-one", len(hits))
                self._backlog.extend(hits)
                return True
            return False
        cur = self._cursor
        idx = -1
        if cur:  # empty cursor must NOT match norm-text-empty msgs (emoji-only bubbles)
            for i in range(len(others) - 1, -1, -1):
                if norm_text(others[i]["text"]) == cur:
                    idx = i
                    break
        catch = int(self.cfg.get("catchup_pages", 3))
        if idx < 0 and catch > 0:
            # cursor scrolled off (fast chatter): catch up by scanning upward
            log.info("cursor lost, catching up %d page(s) upward", catch)
            hist = await asyncio.to_thread(self._collect_upward_sync, catch)
            for m in hist:
                if m["is_self"]:
                    self._note_self(m["text"])
            hist_others = [m for m in hist if not m["is_self"]
                           and not self._is_my_text(m["text"])]
            if hist_others:
                others = hist_others
                msgs = hist
                # re-locate cursor inside the merged history
                idx = -1
                if cur:
                    for i in range(len(others) - 1, -1, -1):
                        if norm_text(others[i]["text"]) == cur:
                            idx = i
                            break
        fresh = others[idx + 1:] if idx >= 0 else others
        forwarded = False
        hits = []
        now = time.time()
        for j, m in enumerate(fresh):
            prev = fresh[j - 1] if j else (others[idx] if idx >= 0 else None)
            k = msg_key(self.home, m, prev["text"] if prev else "")
            fp = msg_fp(self.home, m)
            # Belt against the catch-up rewind storm: a fingerprint that was
            # ANSWERED never re-forwards, even via the position-first path.
            if fp in self._fp_answered:
                continue
            # Position is the primary dedup: everything AFTER the cursor is new,
            # even if identical text was seen before (same person re-sending).
            if idx < 0:
                if k in self._seen:
                    continue
                # OCR-jitter guard on re-scan: same REAL message (stable head+tail
                # fingerprint) answered or forwarded within 15min -> artifact
                if fp in self._fp_answered or now - self._fp_recent.get(fp, 0) < 900:
                    continue
            self._seen[k] = time.time()
            if not self._should_forward(m["text"]):
                continue  # cursor advances silently for non-trigger chatter
            hits.append((m, k, fp))
        # spread @-mentions beyond the bridge's debounce window (2s + adaptive)
        # so EACH gets its own answer with its own quote card, right sender
        forwarded = await self._forward_hits(hits, gate=False)
        if len(self._fp_recent) > 300:
            newest = sorted(self._fp_recent.items(), key=lambda kv: -kv[1])[:200]
            self._fp_recent = dict(newest)
        if others:
            cand = others[-1]
            # never REWIND the cursor onto an old answered message: a stale
            # mid-history viewport + upward catch-up used to reset the anchor
            # backwards every cycle (2026-11-03 parked-window amnesia loop)
            if idx >= 0 or msg_fp(self.home, cand) not in self._fp_answered:
                self._cursor = norm_text(cand["text"])
        self._save_state()
        return forwarded

    async def _forward_hits(self, hits: list[tuple[dict, str, str]],
                            batch: int | None = None, gate: bool = True) -> bool:
        """Send collected hits to the bridge, spaced beyond the debounce window so
        each mention gets its own answer with its own quote card.

        Cross-path dedup (gate=True, rescue paths — backlog/sweep): the stable fp
        is CLAIMED synchronously before the await, so no other gated path can also
        send the same physical message while this one is in flight (2026-11-03
        double-answer incident). The LIVE path calls with gate=False: identical
        text appearing AFTER the cursor is an intentional human re-send there —
        position, not fp, decides (S5/S16 semantics). Every call claims the fp,
        and the recovery cursor boundary keeps live and rescue from covering the
        same message, so turning the live gate off loses nothing."""
        if batch is None:
            batch = self._batch_seq
            self._batch_seq += 1
        now = time.time()
        self._fp_inflight = {k: v for k, v in self._fp_inflight.items()
                             if now - v[0] < 600}
        forwarded = False
        span = float(self.cfg.get("at_spread_s", 6.0))
        for n, (m, k, fp) in enumerate(hits):
            if self._ws is None:
                break
            prev = self._fp_inflight.get(fp)
            if gate and prev and prev[1] != batch and time.time() - prev[0] < 120:
                log.info("skip duplicate forward (other path claimed): %s", m["text"][:30])
                continue
            self._fp_inflight[fp] = (time.time(), batch)
            self._fp_recent[fp] = time.time()
            self._mid_fp[k] = fp
            payload = {
                "t": "inbound", "kind": "group", "group": self.home,
                "sender": m.get("sender") or "群友", "text": m["text"],
                "at": self._is_at(m["text"]), "msg_id": k, "ts": int(time.time()),
            }
            try:
                await self._ws.send(json.dumps(payload, ensure_ascii=False))
                forwarded = True
                if payload["at"]:
                    self._quote_texts.append(m["text"])
                log.info("inbound -> bridge: [%s] %s (at=%s)", payload["sender"], m["text"][:50], payload["at"])
            except Exception as e:
                self._fp_inflight.pop(fp, None)
                self._fp_recent.pop(fp, None)
                self._mid_fp.pop(k, None)
                log.warning("ws send failed: %s", e)
                break
            if n < len(hits) - 1:
                await asyncio.sleep(span)
        return forwarded

    # ---- loops --------------------------------------------------------------
    async def _startup_recovery(self) -> None:
        """One-time sweep after a state-restored start: queue @-mentions STRICTLY
        ABOVE the cursor that were forwarded but never answered (or missed).
        Anything at/below the cursor is the live path's job (fresh-after-cursor);
        queueing it here double-forwards within milliseconds (2026-11-03)."""
        try:
            pages = int(self.cfg.get("history_pages", 3))
            hist = await asyncio.to_thread(self._collect_upward_sync, pages)
            for m in hist:
                if m["is_self"]:
                    self._note_self(m["text"])
            recovered = 0
            now = time.time()
            idx = -1
            if self._cursor:
                for i in range(len(hist) - 1, -1, -1):
                    if norm_text(hist[i]["text"]) == self._cursor:
                        idx = i
                        break
            for j, m in enumerate(hist):
                if idx >= 0 and j > idx:
                    continue              # strictly after cursor: live path owns these
                if m["is_self"] or self._is_my_text(m["text"]):
                    continue
                if not self._is_at(m["text"]):
                    continue
                prev = hist[j - 1] if j else None
                k = msg_key(self.home, m, prev["text"] if prev else "")
                plain = msg_key(self.home, m)
                if k in self._history_answered or plain in self._history_answered:
                    continue
                pending = fp_mine = msg_fp(self.home, m) in set(self._mid_fp.values())
                if k in self._seen and k not in self._mid_fp and not fp_mine:
                    continue          # seen AND not a lost-reply pending item
                fp = msg_fp(self.home, m)
                if not pending:
                    if fp in self._fp_answered or now - self._fp_recent.get(fp, 0) < 900:
                        continue
                    p = self._fp_inflight.get(fp)
                    if p and now - p[0] < 120:
                        continue
                self._seen[k] = now
                self._backlog.append(m)
                recovered += 1
            if recovered:
                log.info("startup recovery: %d unanswered @-mention(s) queued", recovered)
            else:
                log.info("startup recovery: nothing missed")
        except Exception:
            log.exception("startup recovery")

    async def _periodic_sweep(self) -> None:
        """Every sweep_s (default 60s): scroll up and re-read history pages to
        catch @-mentions missed while the reply flow held the UI lock.
        Replying to already-answered messages is impossible here: a mention is
        skipped if its context key is in seen, or its stable fingerprint was
        answered or forwarded inside the dedup window."""
        try:
            hist = await asyncio.to_thread(self._collect_upward_sync,
                                           int(self.cfg.get("sweep_pages", 2)))
            if not hist:
                return
            now = time.time()
            for m in hist:
                if m["is_self"]:
                    self._note_self(m["text"])
            hits = []
            for j, m in enumerate(hist):
                if m["is_self"] or self._is_my_text(m["text"]):
                    continue
                if not self._is_at(m["text"]):
                    continue          # sweep only rescues mentions, not keyword chatter
                prev = hist[j - 1] if j else None
                k = msg_key(self.home, m, prev["text"] if prev else "")
                fp = msg_fp(self.home, m)
                if k in self._seen or k in self._history_answered:
                    continue
                plain = msg_key(self.home, m)
                if plain in self._history_answered or fp in self._fp_answered:
                    continue
                if now - self._fp_recent.get(fp, 0) < 900:
                    continue          # forwarded <15min ago: same real message re-read
                p = self._fp_inflight.get(fp)
                if p and now - p[0] < 120:
                    continue          # another path is sending it right now
                self._seen[k] = now
                hits.append((m, k, fp))
            if hits:
                log.info("periodic sweep: %d missed mention(s) rescued", len(hits))
                await self._forward_hits(hits)
                self._save_state()
        except Exception:
            log.exception("periodic sweep")

    async def poll_loop(self) -> None:
        self._w, self._h = await asyncio.to_thread(self.adb.screen_size)
        beat = 0
        sweep_beats = max(1, int(60.0 / max(self.poll, 0.5)))
        while True:
            try:
                await asyncio.sleep(self.poll)
                beat += 1
                if beat % 12 == 0:  # ~1/min heartbeat: alive vs stuck, at a glance
                    log.info("heartbeat: poll #%d, in-chat=%s", beat, self._started)
                if self.gate.paused():
                    continue
                focus = await asyncio.to_thread(self.adb.current_focus)
                if "com.tencent.mm" not in focus:
                    await asyncio.to_thread(self.adb.wake)
                    await asyncio.to_thread(
                        self.adb.shell,
                        "monkey -p com.tencent.mm -c android.intent.category.LAUNCHER 1",
                    )
                    await asyncio.sleep(3)
                    continue
                async with self._ui_lock:
                    ok, lines = await asyncio.to_thread(self._in_home_sync)
                    if not ok:
                        ok = await asyncio.to_thread(self._goto_home_sync)
                        if not ok:
                            log.debug("not in home chat, retry next cycle")
                            continue
                        _, lines = await asyncio.to_thread(self._in_home_sync)
                    if self._started and not self._recovery_done:
                        # state was restored from a previous run: sweep history
                        # pages once for @-mentions that were never answered
                        self._recovery_done = True
                        await self._startup_recovery()
                    forwarded = await self._handle_screen(lines)
                    if self._started and not forwarded:
                        # idle: make sure the viewport is not parked ABOVE the
                        # newest messages before concluding 'nothing to do'
                        if not await asyncio.to_thread(self._ensure_bottom_sync):
                            ok2, lines2 = await asyncio.to_thread(self._in_home_sync)
                            if ok2:
                                forwarded = await self._handle_screen(lines2)
                    if (self._started and not forwarded
                            and beat % sweep_beats == 0):
                        # every ~60s of quiet: scroll up and rescue mentions that
                        # arrived while a reply flow held the lock
                        await self._periodic_sweep()
                if forwarded:
                    # wait (lock released) for reply_worker to type the answer
                    start = time.time()
                    while time.time() - start < 40 and self._reply_sent_ts < start:
                        await asyncio.sleep(1)
            except AdbError as e:
                log.warning("poll adb error: %s", e)
                await asyncio.sleep(5)
            except Exception:
                log.exception("poll loop")

    async def ws_loop(self) -> None:
        backoff = 1.0
        while True:
            try:
                async with websockets.connect(self.bridge_url, max_size=2_000_000) as ws:
                    self._ws = ws
                    backoff = 1.0
                    log.info("bridge ws connected")
                    await ws.send(json.dumps({"t": "hello", "role": "collector-adb-home"}))
                    async for raw in ws:
                        try:
                            f = json.loads(raw)
                        except Exception:
                            continue
                        if f.get("t") == "send":
                            await self._replies.put(f)
            except Exception as e:
                self._ws = None
                log.warning("bridge ws down: %s (retry %ss)", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def reply_worker(self) -> None:
        while True:
            frame = await self._replies.get()
            try:
                target = frame.get("target") or {}
                name = norm_title(target.get("name") or "")
                text = flatten_reply((frame.get("text") or "").strip())
                if not text:
                    continue
                if name and name != self.home:
                    log.info("reply for %r ignored (home-only mode)", name)
                    continue
                sess = f"group:{self.home}"
                ok_wait = False
                for _ in range(60):
                    if self.gate.paused():
                        break
                    if self.gate.allow(sess):
                        ok_wait = True
                        break
                    await asyncio.sleep(2)
                if not ok_wait:
                    log.warning("reply throttled/dropped: %s", text[:40])
                    continue
                await asyncio.sleep(self.gate.think_delay())
                async with self._ui_lock:
                    ok = await asyncio.to_thread(self._deliver_in_home_sync,
                                                 text, frame.get("reply_to"))
                if ok:
                    self.gate.record_send(sess)
                    self._self_sent.add(norm_text(text))
                    self._note_self(text)
                    if len(self._self_sent) > 400:
                        self._self_sent = set(list(self._self_sent)[-200:])
                    src_mid = frame.get("src_mid")
                    if src_mid:
                        self._history_answered.add(src_mid)
                        fp = self._mid_fp.pop(src_mid, None)
                        if fp:
                            self._fp_answered.add(fp)
                    self._save_state()
                    self._reply_sent_ts = time.time()
                    log.info("replied: %s", text[:60])
                else:
                    log.warning("reply failed to deliver: %s", text[:40])
            except Exception:
                log.exception("reply worker")

    # ---- typing -------------------------------------------------------------
    def _locate_for_quote_sync(self, target_text: str):
        """Scroll up (max 3 pages) to find the message being answered.

        Returns (msgs_on_page, index, pages_up) or None (restored to bottom).
        """
        tnorm = norm_text(target_text)[:20]
        if not tnorm:
            return None
        # segmented matching: merged quote-lines make target longer than any
        # single OCR line; match on head segments instead of one long prefix
        segs = [tnorm[:8]]
        if len(tnorm) > 16:
            segs.append(tnorm[8:16])
        elif len(tnorm) > 8:
            segs.append(tnorm[-8:])

        def rank(mn: str) -> int:
            if mn == tnorm:
                return 0
            # short targets: exact only ("@鲸鲸" must not fuzzy-match longer msgs)
            if len(tnorm) >= 8 and any(s and s in mn for s in segs):
                return 1
            return -1

        pages_up = 0
        for page in range(4):
            msgs = self._screen_msgs_sync()
            best = (-1, -1)  # (rank, index): prefer exact(first), then fuzzy(last)
            for i, m in enumerate(msgs):
                r = rank(norm_text(m["text"]))
                if r == 0:
                    best = (0, i)
                    break
                if r == 1 and best[0] != 0:
                    best = (1, i)
            if best[1] >= 0:
                return msgs, best[1], page
            if page < 3:
                self.adb.swipe(self._w // 2, int(self._h * 0.32),
                               self._w // 2, int(self._h * 0.72), 450)
                pages_up += 1
                time.sleep(0.6)
        for _ in range(pages_up):  # restore bottom
            self.adb.swipe(self._w // 2, int(self._h * 0.72),
                           self._w // 2, int(self._h * 0.32), 350)
            time.sleep(0.4)
        return None

    def _quote_bubble_sync(self, target_text: str) -> bool:
        """Long-press the visible bubble matching target_text, tap 引用.
        WeChat auto-jumps back to the bottom with the quote card in the input."""
        tnorm = norm_text(target_text)[:20]
        lines = oc.ocr_png(self.adb.screencap())
        segs = [tnorm[:8]]
        if len(tnorm) > 16:
            segs.append(tnorm[8:16])
        elif len(tnorm) > 8:
            segs.append(tnorm[-8:])

        def rank(mn: str) -> int:
            if mn == tnorm:
                return 0
            if len(tnorm) >= 8 and any(s and s in mn for s in segs):
                return 1
            return -1

        bubbles = [l for l in lines if l.cy < self._h * 0.85]
        exact = [l for l in bubbles if rank(norm_text(l.text)) == 0]
        fuzzy = [l for l in bubbles if rank(norm_text(l.text)) == 1]
        pool = exact or fuzzy
        if not pool:
            log.info("quote target %r not matchable on screen, plain reply", target_text[:20])
            return False
        l = pool[0] if exact else pool[-1]
        self.adb.swipe(int(l.cx), int(l.cy), int(l.cx), int(l.cy), 800)
        time.sleep(1.0)
        menu = oc.ocr_png(self.adb.screencap())
        for item in menu:
            if item.text.strip().lower() in ("引用", "quote", "回复", "reply"):
                self.adb.tap(int(item.cx), int(item.cy))
                time.sleep(0.9)
                log.info("quoting target: %s", target_text[:30])
                return True
        log.info("quote menu item not found, dismissing")
        self.adb.keyevent(4)
        time.sleep(0.5)
        return False

    def _maybe_quote_sync(self, reply_to: str | None) -> None:
        """Gap rule: answer is a QUOTE when the answered message sits >=N newer
        msgs behind (or needs scrolling up to find). Otherwise plain reply."""
        if not reply_to:
            return
        need = int(self.cfg.get("quote_gap", 4))
        loc = self._locate_for_quote_sync(reply_to)
        if loc is None:
            log.info("quote target scrolled away unrecoverably, plain reply")
            return
        msgs, i, pages_up = loc
        gap = len(msgs) - 1 - i + pages_up * 6  # off-screen pages count as ~6 each
        if gap >= need:
            if self._quote_bubble_sync(reply_to):
                return
            log.info("quote action failed, falling back to plain reply")
        else:
            for _ in range(pages_up):  # close enough: go back to the bottom
                self.adb.swipe(self._w // 2, int(self._h * 0.72),
                               self._w // 2, int(self._h * 0.32), 350)
                time.sleep(0.6)

    def _quote_last_sync(self) -> bool:
        """Long-press the newest @-message and tap 引用 so the reply carries a quote card."""
        if not self._quote_texts:
            return False
        probe = self._quote_texts[-1][:10].replace(" ", "")
        lines = oc.ocr_png(self.adb.screencap())
        cand = [l for l in lines if probe in l.text.replace(" ", "") and l.cy < self._h * 0.85]
        if not cand:
            log.info("quote target not on screen, replying plain")
            return False
        l = cand[-1]
        # long-press the bubble (swipe with equal endpoints, 800ms)
        self.adb.swipe(int(l.cx), int(l.cy), int(l.cx), int(l.cy), 800)
        time.sleep(0.7)
        menu = oc.ocr_png(self.adb.screencap())
        for item in menu:
            if item.text.strip().lower() in ("引用", "quote", "回复", "reply"):
                self.adb.tap(int(item.cx), int(item.cy))
                time.sleep(0.6)
                log.info("quoting: %s", probe)
                return True
        log.info("quote menu item not found, dismissing")
        self.adb.keyevent(4)
        time.sleep(0.5)
        return False

    def _draft_ready(self) -> bool:
        """Ground truth that text is in the input box: ADBKeyboard shows its
        Send button only while a draft exists."""
        lines = oc.ocr_png(self.adb.screencap())
        return any(l.cy > self._h * 0.85 and l.text.strip().lower() in ("send", "发送")
                   for l in lines)

    def _ensure_text_mode_sync(self) -> None:
        """WeChat may sit in hold-to-talk mode; leftmost icon toggles back."""
        lines = oc.ocr_png(self.adb.screencap())
        if any(("hold to talk" in l.text.lower() or "按住" in l.text)
               and l.cy > self._h * 0.90 for l in lines):
            self.adb.tap(int(self._w * 0.06), self._h - 75)
            time.sleep(0.8)

    def _deliver_in_home_sync(self, text: str, reply_to: str | None = None) -> bool:
        ok, _ = self._in_home_sync()
        if not ok:
            if not self._goto_home_sync():
                return False
        # gap rule: quote the answered message when it's far behind the newest
        self._maybe_quote_sync(reply_to)
        self._quote_texts.clear()
        method = self.cfg.get("input_method", "adbkeyboard")
        delivered = False
        for attempt in range(2):
            self._ensure_text_mode_sync()
            px, py = oc.chat_input_point(self._w, self._h)
            self.adb.tap(px, py)
            time.sleep(0.5)
            chunks = [text[i:i + 200] for i in range(0, len(text), 200)]
            for i, chunk in enumerate(chunks):
                self.adb.input_text(chunk, method=method)
                if i < len(chunks) - 1:
                    time.sleep(random.uniform(0.3, 0.8))
            time.sleep(0.7)
            if self._draft_ready():
                delivered = True
                break
            log.warning("draft not visible after input (attempt %d)", attempt + 1)
        if not delivered:
            log.error("send aborted: text never reached the input box")
            return False
        time.sleep(min(self.gate.typing_delay(text), 3.0))
        sent = self._commit_send_sync(text)
        # close keyboard so the poll loop sees a clean chat screen
        try:
            self.adb.keyevent(4)
        except AdbError:
            pass
        time.sleep(0.5)
        return sent

    def _commit_send_sync(self, text: str) -> bool:
        """Send with ADBKeyboard: the floating Send button only exists while the
        input box has content, so its disappearance is the ground truth."""
        def send_visible() -> bool:
            lines = oc.ocr_png(self.adb.screencap())
            return any(l.cy > self._h * 0.85 and l.text.strip().lower() in ("send", "发送")
                       for l in lines)

        try:
            self.adb.shell("am broadcast -a ADB_EDITOR_CODE --ei i 3")
            time.sleep(0.8)
            if not send_visible():
                return True
        except AdbError:
            pass
        self.adb.keyevent(66)
        time.sleep(0.8)
        if not send_visible():
            return True
        lines = oc.ocr_png(self.adb.screencap())
        for l in lines:
            if l.cy > self._h * 0.85 and l.text.strip().lower() in ("send", "发送"):
                self.adb.tap(int(l.cx), int(l.cy))
                time.sleep(0.8)
                if not send_visible():
                    return True
        log.warning("send NOT confirmed (Send button still up): %s", text[:40])
        return False

    async def backlog_worker(self) -> None:
        """Answer startup-history @-mentions one-by-one: send, await reply, next.
        Sending itself goes through _forward_hits, so the shared fp claim makes it
        impossible for the live path to ALSO forward the same message (and vice
        versa) — the 00:37 double inbound(history)/inbound race is closed here."""
        while True:
            await asyncio.sleep(1.5)
            if not self._backlog or self.gate.paused():
                continue
            m = self._backlog.pop(0)
            k = msg_key(self.home, m)
            if k in self._history_answered:
                continue
            if self._is_my_text(m["text"]):
                continue
            if self._ws is None:
                self._backlog.insert(0, m)
                continue
            if not await self._forward_hits([(m, k, msg_fp(self.home, m))]):
                continue
            self._history_answered.add(k)
            self._save_state()
            # wait for this answer to be typed before feeding the next
            start = time.time()
            while time.time() - start < 60 and self._reply_sent_ts < start:
                await asyncio.sleep(1)
            await asyncio.sleep(2)

    async def run(self) -> None:
        if self.cfg.get("input_method") == "adbkeyboard":
            try:
                if "com.android.adbkeyboard" in self.adb.ime_list():
                    self.adb.ime_set("com.android.adbkeyboard/.AdbIME")
                    log.info("IME switched to ADBKeyboard")
                else:
                    log.warning("ADBKeyboard not installed; unicode input will fail")
            except AdbError as e:
                log.warning("IME setup skipped: %s", e)
        await asyncio.gather(self.ws_loop(), self.poll_loop(), self.reply_worker(),
                             self.backlog_worker())


async def selftest(cfg: dict) -> None:
    tok_file = cfg.get("bridge_token_file")
    tok = open(tok_file).read().strip() if tok_file and os.path.exists(tok_file) else cfg.get("bridge_token", "")
    async with websockets.connect(f"{cfg['bridge_ws']}?token={tok}", max_size=2_000_000) as ws:
        await ws.send(json.dumps({
            "t": "inbound", "kind": "group", "group": cfg.get("home_chat", "示例家庭群"),
            "sender": "主人", "text": "小鲸，链路自检", "at": True,
            "msg_id": f"selftest-{int(time.time())}", "ts": int(time.time()),
        }, ensure_ascii=False))
        print("selftest inbound sent, waiting reply 120s...")
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=120)
                f = json.loads(raw)
                if f.get("t") == "send":
                    print("REPLY OK:", f["text"][:120])
                    return
        except asyncio.TimeoutError:
            print("SELFTEST TIMEOUT")
            raise SystemExit(2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join(ROOT, "logs", "collector.log"), encoding="utf-8"),
        ],
    )
    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8-sig"))
    if args.selftest:
        asyncio.run(selftest(cfg))
        return
    col = Collector(cfg)
    if not col.adb.devices():
        raise SystemExit("no adb device (check cable / USB debugging)")
    asyncio.run(col.run())


if __name__ == "__main__":
    main()
