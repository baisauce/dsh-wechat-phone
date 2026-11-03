# -*- coding: utf-8 -*-
"""adb_client.py — thin, timeout-hardened wrapper over adb.exe for the WeChat collector.

Only official debug-channel calls: shell, uiautomator dump, input, dumpsys.
No injection, no hooks.
"""
from __future__ import annotations

import re
import subprocess
import time

NOTIF_PKG = "com.tencent.mm"


class AdbError(RuntimeError):
    pass


class Adb:
    def __init__(self, adb_path: str, serial: str | None = None, timeout: float = 15.0):
        self.adb = adb_path
        self.serial = serial
        self.timeout = timeout

    # ---- plumbing --------------------------------------------------------
    def _cmd(self, args: list[str]) -> list[str]:
        base = [self.adb]
        if self.serial:
            base += ["-s", self.serial]
        return base + args

    def _run(self, args: list[str], timeout: float | None = None) -> str:
        try:
            r = subprocess.run(
                self._cmd(args),
                capture_output=True,
                timeout=timeout or self.timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
        except subprocess.TimeoutExpired as e:
            raise AdbError(f"adb timeout: {' '.join(args[:3])}") from e
        out = r.stdout.decode("utf-8", "replace")
        err = r.stderr.decode("utf-8", "replace")
        if r.returncode != 0 and "error" in err.lower() and "daemon" not in err.lower():
            raise AdbError(f"adb error: {err.strip()[:200]}")
        return out

    def shell(self, cmd: str, timeout: float | None = None) -> str:
        return self._run(["shell", cmd], timeout=timeout)

    def version_ok(self) -> bool:
        try:
            return "version" in self._run(["get-state"], timeout=8) or True
        except AdbError:
            return False

    def devices(self) -> list[str]:
        out = self._run(["devices"])
        return [ln.split("\t")[0] for ln in out.splitlines()[1:] if "\tdevice" in ln]

    # ---- basic input -----------------------------------------------------
    def tap(self, x: int, y: int) -> None:
        self.shell(f"input tap {int(x)} {int(y)}")

    def swipe(self, x1, y1, x2, y2, dur_ms: int = 300) -> None:
        self.shell(f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(dur_ms)}")

    def keyevent(self, code: int | str) -> None:
        self.shell(f"input keyevent {code}")

    def screen_size(self) -> tuple[int, int]:
        out = self.shell("wm size")
        m = re.findall(r"(\d+)x(\d+)", out)
        if not m:
            raise AdbError(f"cannot parse screen size: {out[:100]}")
        w, h = map(int, m[-1])
        return w, h

    # ---- UI tree ---------------------------------------------------------
    def dump_ui(self, retries: int = 2) -> str:
        """Return current accessibility tree XML. uiautomator sometimes needs a retry."""
        for attempt in range(retries + 1):
            self.shell("rm -f /sdcard/_wxb_ui.xml", timeout=8)
            out = self.shell("uiautomator dump /sdcard/_wxb_ui.xml", timeout=20)
            if "dumped to" in out or "UI hierarchy" in out:
                xml = self.shell("cat /sdcard/_wxb_ui.xml", timeout=15)
                if xml.strip().startswith("<?xml") or "<hierarchy" in xml:
                    return xml
            time.sleep(0.8)
        raise AdbError("uiautomator dump failed after retries")

    def current_focus(self) -> str:
        out = self.shell("dumpsys window", timeout=20)
        m = re.search(r"mCurrentFocus=Window\{[^ ]* [^ ]* ([^\s}]+)", out)
        return m.group(1) if m else ""

    def is_screen_on(self) -> bool:
        out = self.shell("dumpsys power", timeout=20)
        return "mWakefulness=Awake" in out

    def wake(self) -> None:
        if not self.is_screen_on():
            self.keyevent(224)  # KEYCODE_WAKEUP
            time.sleep(1)

    # ---- screenshot ------------------------------------------------------
    def screencap(self) -> bytes:
        """Raw PNG bytes of the current screen via exec-out (no sdcard round-trip)."""
        base = [self.adb]
        if self.serial:
            base += ["-s", self.serial]
        r = subprocess.run(
            base + ["exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=self.timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if r.stdout[:2] != b"PK" and r.stdout[:4] != b"\x89PNG":
            raise AdbError("screencap returned non-image data")
        return r.stdout

    # ---- notifications ---------------------------------------------------
    def wechat_notifications(self) -> list[dict]:
        """Parse dumpsys notification for com.tencent.mm entries.

        Returns [{title, text, sub, when_ms}] newest-last.
        """
        try:
            out = self.shell("dumpsys notification --noredact", timeout=25)
        except AdbError:
            out = self.shell("dumpsys notification", timeout=25)
        items: list[dict] = []
        # records are separated by NotificationRecord blocks
        for block in re.split(r"NotificationRecord\(", out)[1:]:
            head = block[:400]
            if f"pkg={NOTIF_PKG}" not in head:
                continue
            rec = {"title": "", "text": "", "sub": "", "when_ms": 0}
            m = re.search(r"when=(\d{13})", head)
            if m:
                rec["when_ms"] = int(m.group(1))
            extras = re.search(r"extras: Bundle\[\{(.*?)\}\]", block[:4000], re.S)
            blob = extras.group(1) if extras else ""

            def field(name: str) -> str:
                mm = re.search(rf"android\.{name}='(.*?)'", blob)
                if mm:
                    return mm.group(1)
                mm = re.search(rf"android\.{name}=([^,\]]*)", blob)
                return mm.group(1).strip() if mm else ""

            rec["title"] = field("title")
            rec["text"] = field("text")
            rec["sub"] = field("subText")
            if rec["title"] or rec["text"]:
                items.append(rec)
        return items

    # ---- text input (pluggable) ------------------------------------------
    def input_text(self, text: str, method: str = "adbkeyboard") -> None:
        """Insert unicode text into the focused field."""
        if method == "adbkeyboard":
            safe = text.replace("'", "'\\''")
            self.shell(
                f"am broadcast -a ADB_INPUT_TEXT --es msg '{safe}'"
            )
        elif method == "ascii":
            esc = text.replace(" ", "%s").replace("&", "\\&").replace("<", "\\<").replace(">", "\\>")
            self.shell(f"input text '{esc}'")
        else:
            raise AdbError(f"unknown input method: {method}")

    def ime_set(self, ime_id: str) -> None:
        self.shell(f"ime set {ime_id}")

    def ime_list(self) -> str:
        return self.shell("ime list -s")
