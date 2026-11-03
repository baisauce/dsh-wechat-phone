# -*- coding: utf-8 -*-
"""apply_kb_fixes.py — idempotent post-update healer for the AstrBot stack.

Re-applies the DashScope batch-size fixes that upstream/plugin updates wipe out:
  1. wanna_be_human plugin: _KB_UPLOAD_BATCH_SIZE / KB_UPLOAD_BATCH_SIZE /
     upload_batch_size 16 -> 10 (DashScope text-embedding v3/v4 hard limit).
Run automatically from update-astrbot.cmd; safe to run any time, any number of times.
"""
import io
import os
import sys

PLUGINS = r"D:\Program Files\AstrBot\data\plugins"
MARK = "KB_BATCH_FIX"


def patch_file(path, pairs):
    if not os.path.exists(path):
        print(f"  skip (missing): {path}")
        return 0
    t = io.open(path, encoding="utf-8").read()
    n = 0
    for old, new in pairs:
        if old in t and MARK not in t:
            t = t.replace(old, new, 1)
            n += 1
    if n:
        io.open(path, "w", encoding="utf-8").write(t)
    return n


def main():
    total = 0
    # core-level root fix: make DashScope provider auto-chunk any batch >10
    src = r"D:\Program Files\AstrBot\python\Lib\site-packages\astrbot\core\provider\sources\dashscope_embedding_source.py"
    if os.path.exists(src):
        t = io.open(src, encoding="utf-8").read()
        old = "        if not text:\n            return []\n"
        new = (
            "        if not text:\n            return []\n"
            "        # KB_BATCH_FIX: DashScope text-embedding allows at most 10 items/request\n"
            "        if len(text) > 10:\n"
            "            out: list[list[float]] = []\n"
            "            for i in range(0, len(text), 10):\n"
            "                out.extend(await self.get_embeddings(text[i : i + 10]))\n"
            "            return out\n"
        )
        if old in t and MARK not in t:
            io.open(src, "w", encoding="utf-8").write(t.replace(old, new, 1))
            total += 1
            print("  dashscope source auto-chunk patched")
    base = os.path.join(PLUGINS, "astrbot_plugin_wanna_be_human")
    total += patch_file(os.path.join(base, "main.py"), [
        ("_KB_UPLOAD_BATCH_SIZE = 16",
         "_KB_UPLOAD_BATCH_SIZE = 10  # KB_BATCH_FIX: DashScope text-embedding limit"),
    ])
    total += patch_file(os.path.join(base, "services", "kb_service.py"), [
        ("    upload_batch_size: int = 16", "    upload_batch_size: int = 10  # KB_BATCH_FIX"),
        ("    KB_UPLOAD_BATCH_SIZE = 16", "    KB_UPLOAD_BATCH_SIZE = 10  # KB_BATCH_FIX"),
    ])
    print(f"apply_kb_fixes: {total} fix(es) applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
