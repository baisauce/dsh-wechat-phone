# -*- coding: utf-8 -*-
"""sim_scenarios.py — 快速离线习题（3 场景 / 8 项检查）。

Feeds synthetic OCR results into the REAL Collector._handle_screen / wake rules
with adb+ws mocked. Covers:
  T1 启动基线：历史吸收、屏上未答@进 backlog、游标剥标点
  T2 唤醒规则一批：@/关键词/全角＠/大小写/无关闲聊不转/纯闲聊只推游标/quote簿记
  T3 引用定位：噪声中锁定目标气泡（排除输入区、取最新）

去重/复读/竞态/贴底等时序类在 sim_extreme.py；一把跑用 sim_all.py。
语料是脱敏示例名——本机 runtime config 是真名时必须用 SIM_CONFIG 指向
config.example.json（见 sim_all.py 头注释）。
"""
import asyncio
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import main as M  # noqa: E402
from ocr_channel import Line  # noqa: E402

# Config source: $SIM_CONFIG > config.json (runtime, real names) > config.example.json.
CFG_PATH = os.environ.get("SIM_CONFIG") or os.path.join(HERE, "config.json")
if not os.path.exists(CFG_PATH):
    CFG_PATH = os.path.join(HERE, "config.example.json")
cfg = json.load(open(CFG_PATH, encoding="utf-8-sig"))
# legacy suite tests cursor logic directly; history-scan & catch-up live in sim_extreme
cfg["history_pages"] = 0
cfg["catchup_pages"] = 0


class FakeAdb:
    def __init__(self):
        self.screencap_png = b""
    def screencap(self):
        return self.screencap_png
    def keyevent(self, c):
        pass
    def swipe(self, *a):
        pass
    def tap(self, *a):
        pass


class FakeWs:
    def __init__(self):
        self.sent = []
    async def send(self, s):
        self.sent.append(json.loads(s))


def mk_msg(text, sender="某人", is_self=False):
    return {"text": text, "sender": sender, "is_self": is_self, "y": 0}


def screen(msgs):
    """Logical msgs -> fake OCR Line objects. Line order: (cx,cy,text,conf,left,right,top,bottom)
    others: sender label x=250 (short, left) then bubble x=350; self: bubble right-aligned x=750."""
    lines = []
    y = 400
    for m in msgs:
        if not m["is_self"] and m["sender"]:
            lines.append(Line(250, y, m["sender"], 1.0, 200, 320, y - 20, y + 20))
            y += 60
        x = 750 if m["is_self"] else 350
        lines.append(Line(x, y, m["text"], 1.0, x - 100, x + 100, y - 25, y + 25))
        y += 110
    return lines


def new_col():
    col = M.Collector.__new__(M.Collector)
    col.cfg = cfg
    col.adb = FakeAdb()
    col.home = M.norm_title(cfg.get("home_chat", "示例家庭群"))
    col.nicknames = [str(x) for x in cfg.get("bot_nicknames", ["小鲸"])]
    col.wake_kw = [str(x).lower() for x in cfg.get("wake_keywords", [])]
    col.gate = M.Gate(cfg, os.path.join(M.ROOT, "PAUSE"))
    col._ws = FakeWs()
    col._replies = asyncio.Queue()
    col._ui_lock = asyncio.Lock()
    col._cursor = ""
    col._seen = {}
    col._self_sent = set()
    col._reply_sent_ts = 0.0
    col._started = False
    col._quote_texts = []
    col._backlog = []
    col._history_answered = set()
    col._fp_answered = set()
    col._fp_recent = {}
    col._mid_fp = {}
    col._fp_inflight = {}
    col._batch_seq = 0
    col._self_full = []
    col._self_fps = set()
    col._recovery_done = True
    col._state_file = os.path.join(os.environ.get("TEMP", HERE), "sim_state.json")
    col._w, col._h = 1080, 2412
    return col


PASS = FAIL = 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


async def main():
    print("T1: 启动基线——历史吸收，屏上未答@进 backlog，游标剥标点")
    col = new_col()
    await col._handle_screen(screen([mk_msg("随便抱，随便摸", "群友C"),
                                     mk_msg("不伸爪子", "群友C"),
                                     mk_msg("@鲸鲸 旧消息", "群友A")]))
    check("未答@进 backlog 队列(由 worker 逐条发)",
          len(col._ws.sent) == 0 and len(col._backlog) == 1
          and col._backlog[0]["text"] == "@鲸鲸 旧消息",
          f"sent={col._ws.sent} backlog={col._backlog}")
    check("cursor 落在最新他人消息(标点剥离)", col._cursor == "鲸鲸旧消息", col._cursor)

    print("T2: 唤醒规则一批——@/关键词/全角＠/大小写/无关/纯闲聊")
    col._ws.sent.clear()
    col._quote_texts.clear()
    base = [mk_msg("@鲸鲸我好累", "群友D"), mk_msg("今晚打不打工", "群友E"),
            mk_msg("@鲸鲸出来出来", "群友A"), mk_msg("deepseek又降价了", "群友F"),
            mk_msg("刚才那个表情包啥意思", "群友E"), mk_msg("@大鲸 给大伙讲个笑话", "家人C")]
    await col._handle_screen(screen(base))
    sent = col._ws.sent
    texts = [s["text"] for s in sent]
    check("唤醒 4 条命中且 at 标志正确(触发词命中入站)",
          len(sent) == 4 and [s["at"] for s in sent] == [True, True, False, True]
          and "deepseek又降价了" in texts, str([(s["text"], s["at"]) for s in sent]))
    check("无关消息未转发",
          "今晚打不打工" not in texts and "刚才那个表情包啥意思" not in texts)
    check("quote 簿记只收@消息且模式触发",
          col._quote_texts == ["@鲸鲸我好累", "@鲸鲸出来出来", "@大鲸 给大伙讲个笑话"],
          str(col._quote_texts))
    col._ws.sent.clear()
    await col._handle_screen(screen(base + [mk_msg("＠鲸鲸 在吗", "新人"),
                                            mk_msg("DeepSeek 真强", "路人"),
                                            mk_msg("通宵聊天呢", "群友E")]))
    sent = col._ws.sent
    check("全角＠与大小写触发词都唤醒",
          len(sent) == 2 and sent[0]["at"] is True
          and "DeepSeek 真强" in [s["text"] for s in sent], str(sent))
    check("纯闲聊只推进游标", col._cursor == "通宵聊天呢", col._cursor)

    print("T3: 引用定位——噪声中锁定目标气泡")
    col2 = new_col()
    col2._quote_texts = ["无关", "@鲸鲸出来出来"]
    lines = [
        Line(300, 500, "群友E: 今晚打不打工", 0.99, 200, 400, 480, 530),
        Line(300, 900, "@鲸鲸出来出来", 0.99, 200, 870, 420, 930),
        Line(300, 1100, "@鲸鲸出来出来的时候", 0.99, 200, 1070, 500, 1130),  # 干扰
        Line(700, 2300, "@鲸鲸出来出来", 0.99, 600, 2270, 800, 2330),        # 输入框(应排除)
    ]
    probe = col2._quote_texts[-1][:10].replace(" ", "")
    cand = [l for l in lines if probe in l.text.replace(" ", "") and l.cy < col2._h * 0.85]
    check("候选排除输入框区且取最新一条",
          len(cand) == 2 and max(cand, key=lambda l: l.cy).cy == 1100, str([l.cy for l in cand]))

    print(f"\n===== 常规场景结果: {PASS} passed, {FAIL} failed =====")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
