# -*- coding: utf-8 -*-
"""gate.py — humanization & safety gate. All send decisions pass through here.

Enforced BEFORE anything reaches the phone:
  - quiet hours (silence window, e.g. 01:00-07:30)
  - per-session sliding window (rate + min interval)
  - global hourly / daily caps
  - jittered "read + think + type" delay
  - PAUSE kill switch (touch dsh-wechat-phone/PAUSE to halt all output instantly)
"""
from __future__ import annotations

import os
import random
import time
from collections import deque
from datetime import datetime


class Gate:
    def __init__(self, cfg: dict, pause_file: str):
        g = cfg.get("gate", {})
        self.session_window = float(g.get("session_window_s", 60))
        self.session_max = int(g.get("session_max", 4))
        self.session_min_gap = float(g.get("session_min_gap_s", 3))
        self.hourly_max = int(g.get("hourly_max", 20))
        self.daily_max = int(g.get("daily_max", 200))
        q = g.get("quiet_hours", [1, 7.5])
        self.quiet_from = float(q[0])
        self.quiet_to = float(q[1])
        self.delay_min = float(g.get("delay_min_s", 2.0))
        self.delay_max = float(g.get("delay_max_s", 8.0))
        self.cps_min = float(g.get("typing_cps_min", 4))   # chars per second, human range
        self.cps_max = float(g.get("typing_cps_max", 9))
        self.pause_file = pause_file

        self._sess: dict[str, deque] = {}
        self._sess_last: dict[str, float] = {}
        self._hour: deque = deque()
        self._day_key, self._day_count = self._today(), 0

    @staticmethod
    def _today() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    # ---- checks ----------------------------------------------------------
    def paused(self) -> bool:
        return os.path.exists(self.pause_file)

    def in_quiet(self) -> bool:
        h = datetime.now().hour + datetime.now().minute / 60
        a, b = self.quiet_from, self.quiet_to
        if a == b:
            return False
        return (a < b and a <= h < b) or (a > b and (h >= a or h < b))

    def allow(self, session: str) -> bool:
        now = time.time()
        if self.paused() or self.in_quiet():
            return False
        dq = self._sess.setdefault(session, deque())
        while dq and now - dq[0] > self.session_window:
            dq.popleft()
        if len(dq) >= self.session_max:
            return False
        if now - self._sess_last.get(session, 0) < self.session_min_gap:
            return False
        while self._hour and now - self._hour[0] > 3600:
            self._hour.popleft()
        if len(self._hour) >= self.hourly_max:
            return False
        if self._day_key != self._today():
            self._day_key, self._day_count = self._today(), 0
        if self._day_count >= self.daily_max:
            return False
        return True

    # ---- accounting ------------------------------------------------------
    def record_send(self, session: str) -> None:
        now = time.time()
        self._sess.setdefault(session, deque()).append(now)
        self._sess_last[session] = now
        self._hour.append(now)
        self._day_count += 1

    def think_delay(self) -> float:
        """Random pause before replying (read + think)."""
        return random.uniform(self.delay_min, self.delay_max)

    def typing_delay(self, text: str) -> float:
        """Simulated typing time by length, jittered."""
        cps = random.uniform(self.cps_min, self.cps_max)
        return min(len(text) / cps, 12.0) + random.uniform(0.2, 1.2)
