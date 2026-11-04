# -*- coding: utf-8 -*-
"""apply_release_api_fix.py — idempotent post-update healer for the update check.

Symptom: opening the AstrBot Dashboard (检查更新) logs a scary ERROR traceback
    api.updates: Dashboard update operation failed: Failed to parse release information.
    ... httpx.ConnectTimeout ...

Cause: astrbot/core/updater.py hardcodes the release list to the official mirror
    https://api.soulter.top/releases
which serves ~360 KB and, from this machine, takes 25-45 s or stalls inside the TLS
handshake. httpx's 30 s timeout raises ConnectTimeout, zip_updater wraps it as
"Failed to parse release information.", the dashboard handler logs it with exc_info.
It only affects that one WebUI request - the message pipeline never calls it, so the
bot keeps replying normally.

Fix: let ASTRBOT_RELEASE_API override the release URL, so start-run.cmd can point the
check at https://api.github.com/repos/AstrBotDevs/AstrBot/releases (~0.6 s from here).
If the patch is wiped by `pip install -U astrbot`, the env var is simply ignored and
behaviour falls back to upstream - nothing breaks. Re-applied from update-astrbot.cmd,
safe to run any number of times.

Usage: python apply_release_api_fix.py [--url <release api>]   # --url only records the
                                                        # suggested value in the output.
"""
import io
import os
import sys

MARK = "RELEASE_API_FIX"
OLD_LINE = '        self._release_api = "https://api.soulter.top/releases"'
NEW_LINES = (
    "        # RELEASE_API_FIX: ASTRBOT_RELEASE_API overrides the flaky official mirror\n"
    "        self._release_api = (\n"
    "            os.environ.get(\"ASTRBOT_RELEASE_API\")\n"
    "            or \"https://api.soulter.top/releases\"\n"
    "        ).strip()\n"
)
DEFAULT_URL = "https://api.github.com/repos/AstrBotDevs/AstrBot/releases"


def locate_updater():
    """Find the installed astrbot/core/updater.py, without hardcoding the env."""
    candidates = []
    try:
        import astrbot  # noqa: F401

        pkg = os.path.dirname(os.path.abspath(astrbot.__file__))
        candidates.append(os.path.join(pkg, "core", "updater.py"))
    except Exception:
        pass
    candidates.append(
        r"D:\Program Files\AstrBot\python\Lib\site-packages\astrbot\core\updater.py"
    )
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def main():
    suggested = DEFAULT_URL
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--url" and i + 2 <= len(sys.argv[1:]):
            suggested = sys.argv[i + 2]

    path = locate_updater()
    if not path:
        print("apply_release_api_fix: astrbot/core/updater.py not found - skip")
        return 1

    text = io.open(path, encoding="utf-8").read()
    if MARK in text:
        print(f"apply_release_api_fix: already patched -> {path}")
    elif OLD_LINE in text:
        io.open(path, "w", encoding="utf-8").write(text.replace(OLD_LINE, NEW_LINES, 1))
        print(f"apply_release_api_fix: patched -> {path}")
    else:
        print(f"apply_release_api_fix: anchor line not found (upstream changed?) -> {path}")
        print("  leave as is; check the release URL manually after this upgrade.")
        return 1

    print("  set in the launcher: ASTRBOT_RELEASE_API=" + suggested)
    print("  restart AstrBot (stop-astrbot.bat / start-astrbot.bat) to take effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
