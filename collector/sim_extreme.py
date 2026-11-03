# -*- coding: utf-8 -*-
"""sim_extreme.py — 时序/去重压力习题（12 场景 / 21 项检查）。

历史标签对照：E1=S8+S10+S23前态, E2=S9, E3=S13, E4=S16, E5=S17,
E6=S12+S18(引用家族), E7=S20(竞态), E8=S21(自聊回声), E9=S22(单行化),
E10=S23(pending补救), E11=引用间隔(隔一条即引用), E12=贴底最新气泡可读。
全部 adb+ws 模拟，无网络无真机。
语料为脱敏示例名：本机跑请用 SIM_CONFIG 指向 config.example.json（见 sim_all.py）。
"""
import asyncio
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import main as M  # noqa: E402

CFG_PATH = os.environ.get("SIM_CONFIG") or os.path.join(HERE, "config.json")
if not os.path.exists(CFG_PATH):
    CFG_PATH = os.path.join(HERE, "config.example.json")
cfg = json.load(open(CFG_PATH, encoding="utf-8-sig"))

PASS = FAIL = 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  [PASS] {name}")
    else:
        FAIL += 1; print(f"  [FAIL] {name}  {detail}")


class FakeAdb:
    def __init__(self, sim):
        self.sim = sim
        self.taps = []
    def screencap(self):
        return b""
    def swipe(self, x1, y1, x2, y2, dur=300):
        if y2 > y1:
            self.sim.page = min(self.sim.page + 1, len(self.sim.pages) - 1)  # scroll up
        else:
            self.sim.page = max(self.sim.page - 1, 0)                        # scroll down
    def tap(self, x, y):
        self.taps.append((x, y))
    def keyevent(self, c):
        pass
    def shell(self, cmd, timeout=None):
        return ""


class FakeWs:
    def __init__(self):
        self.sent = []
    async def send(self, s):
        self.sent.append(json.loads(s))


class SimCollector(M.Collector):
    """Collector with the screen seam backed by scripted pages (index 0 = bottom)."""
    def __init__(self, pages):
        self.pages = pages
        self.page = 0
        self.adb = FakeAdb(self)
        self.cfg = cfg
        self.home = M.norm_title(cfg.get("home_chat", "示例家庭群"))
        self.nicknames = [str(x) for x in cfg.get("bot_nicknames", ["小鲸"])]
        self.wake_kw = [str(x).lower() for x in cfg.get("wake_keywords", [])]
        self.poll = 0.05
        import gate as G
        self.gate = G.Gate(cfg, os.path.join(M.ROOT, "PAUSE-nonexistent"))
        self._ws = FakeWs()
        self._replies = asyncio.Queue()
        self._ui_lock = asyncio.Lock()
        self._cursor = ""
        self._seen = {}
        self._self_sent = set()
        self._reply_sent_ts = 0.0
        self._started = False
        self._quote_texts = []
        self._backlog = []
        self._history_answered = set()
        self._fp_answered = set()
        self._fp_recent = {}
        self._mid_fp = {}
        self._fp_inflight = {}
        self._batch_seq = 0
        self._self_full = []
        self._self_fps = set()
        self._recovery_done = True
        self._state_file = os.path.join(os.environ.get("TEMP", HERE), "sim_extreme_state.json")
        self._w, self._h = 1080, 2412
    def _screen_msgs_sync(self):
        return [dict(m) for m in self.pages[self.page]]


def mk(text, sender="某人", is_self=False):
    return {"text": text, "sender": sender, "is_self": is_self, "y": 0}


async def run_backlog_until(col, n_expected, timeout=12.0):
    """Drive backlog_worker until n replies were sent — returns EARLY, no full-timeout sleep."""
    async def auto_reply():
        while len(col._ws.sent) < n_expected:
            await asyncio.sleep(0.25)
            col._reply_sent_ts = time.time()   # pretend reply_worker typed it
    task = asyncio.ensure_future(asyncio.gather(col.backlog_worker(), auto_reply()))
    t0 = time.time()
    while len(col._ws.sent) < n_expected and time.time() - t0 < timeout:
        await asyncio.sleep(0.25)
    task.cancel()
    try:
        await task
    except BaseException:
        pass


async def main():
    print("E1: 启动翻3页历史散落@ -> 逐条补答 -> 重启不重复 -> pending补救")
    pages = [
        [mk("网真够差的", "群友B"), mk("急得跳脚", "群友A")],
        [mk("@鲸鲸 帮我看看这个", "群友E"), mk("刚才那局真险", "群友C")],
        [mk("@鲸鲸 早安", "群友D"), mk("昨晚睡得好", "群友E")],
    ]
    col = SimCollector(pages)
    try:
        os.remove(col._state_file)
    except FileNotFoundError:
        pass
    await col._handle_screen([])
    check("backlog 按时序收集 2 条@",
          len(col._backlog) == 2 and col._backlog[0]["text"] == "@鲸鲸 早安", str(col._backlog))
    await run_backlog_until(col, 2)
    check("逐条转发2条并登记，屏幕回到底部",
          len(col._ws.sent) == 2 and len(col._history_answered) == 2 and col.page == 0,
          f"sent={len(col._ws.sent)} ans={len(col._history_answered)} page={col.page}")
    col2 = SimCollector(pages)
    col2._load_state()
    await col2._handle_screen([])
    check("重启恢复已答集合，不重复入队", len(col2._backlog) == 0, str(col2._backlog))
    colz = SimCollector([[mk("水", "甲"), mk("@鲸鲸 在吗", "乙"), mk("算了吧", "丙")]])
    colz._started = True
    colz._cursor = M.norm_text("算了吧")
    kz = M.msg_key(colz.home, mk("@鲸鲸 在吗", "乙"), "水")
    colz._seen[kz] = time.time()
    colz._mid_fp[kz] = M.msg_fp(colz.home, mk("@鲸鲸 在吗", "乙"))   # 已转发、回复丢失
    await colz._startup_recovery()
    check("pending漏答@被 recovery 重新入队",
          len(colz._backlog) == 1 and colz._backlog[0]["text"] == "@鲸鲸 在吗", str(colz._backlog))

    print("E2: 快速滚动顶出游标 -> 向上追采不漏不重")
    col3 = SimCollector([
        [mk("B@ 新消息一 @鲸鲸", "甲"), mk("插话", "乙"), mk("D@ 新消息二 @鲸鲸", "丙")],
        [mk("A 游标消息(旧)", "丁"), mk("更早", "戊")],
    ])
    col3._started = True
    col3._cursor = M.norm_text("A 游标消息(旧)")
    col3._seen = {}
    await col3._handle_screen([])
    texts = [s["text"] for s in col3._ws.sent]
    check("只转 B@/D@ 且游标A不重发",
          len(texts) == 2 and all(t.startswith(("B@", "D@")) for t in texts), str(texts))

    print("E3: bot回复插入上下文后重扫——同一条@不二次转发")
    col5 = SimCollector([[]])
    col5._started = True
    col5._cursor = M.norm_text("锚点消息")
    col5._seen = {}
    col5.pages = [[mk("锚点消息", "甲"), mk("@鲸鲸 在吗", "乙")]]
    await col5._handle_screen([])
    n1 = len(col5._ws.sent)
    col5.pages = [[mk("插话", "丙"), mk("在呢", None, True), mk("@鲸鲸 在吗", "乙")]]
    col5._cursor = "不存在的游标"
    await col5._handle_screen([])
    check("重扫 fp 拦住已转发@", n1 == 1 and len(col5._ws.sent) == 1, str(col5._ws.sent))

    print("E4: 同一人游标后连发同文本两次 -> 都是新消息，都答")
    col7 = SimCollector([[]])
    col7._started = True
    col7._cursor = M.norm_text("锚点")
    col7._seen = {}
    col7.pages = [[mk("锚点", "甲"), mk("@鲸鲸", "乙"), mk("别人插话", "丙"), mk("@鲸鲸", "乙")]]
    await col7._handle_screen([])
    check("游标后重复文本两次都转发（位置优先）", len(col7._ws.sent) == 2, str(col7._ws.sent))

    print("E5: 定时上滑巡检——只救漏网@，二次巡检零动作")
    col8 = SimCollector([[mk("旧@ 已答", "甲"), mk("插话", "乙"),
                         mk("@鲸鲸 救我", "丙"), mk("闲聊", "丁")]])
    col8._started = True
    col8._cursor = M.norm_text("锚点不在屏上")
    col8._seen = {M.msg_key("示例家庭群", mk("旧@ 已答", "甲"), ""): time.time()}
    col8._fp_answered = {M.msg_fp("示例家庭群", mk("旧@ 已答", "甲"))}
    await col8._periodic_sweep()
    check("巡检只救漏网@", [s["text"] for s in col8._ws.sent] == ["@鲸鲸 救我"], str(col8._ws.sent))
    col8._ws.sent.clear()
    await col8._periodic_sweep()
    check("第二次巡检无新动作", len(col8._ws.sent) == 0, str(col8._ws.sent))

    print("E6: 引用家族——引我=点名；引他人旧@回声=沉默")
    from ocr_channel import Line as L, extract_chat_messages
    parsed = extract_chat_messages([
        L(250, 400, "群友A", 1.0, 200, 320, 380, 420),
        L(350, 460, "哈哈哈哈她嘴好欠", 1.0, 250, 460, 435, 485),
        L(400, 520, "鲸鲸: 点完就跑是吧", 1.0, 280, 530, 500, 540),
        L(250, 700, "群友E", 1.0, 200, 300, 680, 720),
        L(350, 760, "笑死我了", 1.0, 250, 450, 735, 785),
    ], 1080, 2412)
    q = next((p for p in parsed if p["sender"] == "群友A"), None)
    check("引用行合并进气泡且不产生鲸鲸假消息",
          q is not None and "鲸鲸: 点完就跑是吧" in q["text"]
          and not any(p["sender"] == "鲸鲸" for p in parsed), str(parsed))
    col4 = SimCollector([[mk("占位", "甲")]])
    check("引用我的消息=点名转发；普通提及不算",
          col4._should_forward("哈哈哈哈她嘴好欠 鲸鲸: 点完就跑是吧")
          and col4._is_at("哈哈哈哈她嘴好欠 鲸鲸: 点完就跑是吧")
          and not col4._is_at("我感觉鲸鲸语气太冲了"))
    check("他人旧@回声段不唤醒，本人文本照常唤醒",
          not col4._should_forward("测试者D 测试者D：@鲸鲸 该叫我什么")
          and not col4._is_at("测试者D 测试者D：@鲸鲸 该叫我什么")
          and col4._should_forward("测试者D 鲸鲸你看看这个")
          and col4._should_forward("@鲸鲸 该叫我什么")
          and col4._should_forward("新消息：鲸鲸看看这个"))

    print("E7: backlog 与直发竞态——同 fp 只允许一条路径发")
    colb = SimCollector([[mk("占位", "甲")]])
    colb._started = True
    mdup = mk("@鲸鲸 重复检查", "乙")
    await colb._forward_hits([(mdup, M.msg_key(colb.home, mdup), M.msg_fp(colb.home, mdup))])
    n7 = len(colb._ws.sent)
    colb._backlog.append(mdup)
    task = asyncio.ensure_future(colb.backlog_worker())
    await asyncio.sleep(2.4)
    task.cancel()
    try:
        await task
    except BaseException:
        pass
    check("backlog 二次发送被 fp 先声明拦住", len(colb._ws.sent) == n7, str(colb._ws.sent))

    print("E8: 自己长回复首行被误读成他人气泡——片段命中 self 记忆")
    colw = SimCollector([[mk("占位", "甲")]])
    colw._started = True
    colw._seen = {}
    long_rep = "大鲸笑话是吧行有人问我这么胖怎么游得动我说我根本不游我漂着洋流带着我走"
    colw._self_sent.add(M.norm_text(long_rep))
    colw._note_self(long_rep)
    colw.pages = [[mk("大鲸笑话是吧，行。", "群友")]]
    colw._cursor = M.norm_text("不存在的锚")
    await colw._handle_screen([])
    check("含唤醒关键词的自聊片段不转发", len(colw._ws.sent) == 0, str(colw._ws.sent))

    print("E9: 回复单行化——换行折叠成标点连接")
    f = M.flatten_reply
    check("句号后直连/裸换行补逗号/多空行不残留/空输入归空",
          f("这个嘛……我爸呀。\n\n被你问得不好意思了") == "这个嘛……我爸呀。被你问得不好意思了"
          and f("在呢\n等你好久了") == "在呢，等你好久了"
          and f("A！\n\n\n\nB") == "A！B" and f("  \n ") == "")

    print("E10: 已答/刚转发的绝不重入队（pending 补救的反面）")
    coly = SimCollector([[mk("水", "甲"), mk("@鲸鲸 早就答过", "乙"), mk("算了吧", "丙")]])
    coly._started = True
    coly._cursor = M.norm_text("算了吧")
    kyy = M.msg_key(coly.home, mk("@鲸鲸 早就答过", "乙"), "水")
    fpy = M.msg_fp(coly.home, mk("@鲸鲸 早就答过", "乙"))
    coly._seen[kyy] = time.time()
    coly._fp_answered.add(fpy)
    coly._fp_recent[fpy] = time.time()
    await coly._startup_recovery()
    check("已答@不得重新入队", len(coly._backlog) == 0, str(coly._backlog))

    print("E11: 引用间隔——隔一条就要引用，紧挨着才裸回")
    quoted: list[str] = []
    cfgq = dict(cfg); cfgq["quote_gap"] = 1
    colq = SimCollector([[mk("@鲸鲸 帮我看看这个", "甲"), mk("我也想知道", "乙")]])
    colq.cfg = cfgq
    colq._quote_bubble_sync = lambda t: (quoted.append(t) or True)
    colq._maybe_quote_sync("@鲸鲸 帮我看看这个")
    check("被答消息后面多了 1 条 -> 引用", quoted == ["@鲸鲸 帮我看看这个"], str(quoted))
    quoted.clear()
    colq2 = SimCollector([[mk("@鲸鲸 帮我看看这个", "甲")]])
    colq2.cfg = cfgq
    colq2._quote_bubble_sync = lambda t: (quoted.append(t) or True)
    colq2._maybe_quote_sync("@鲸鲸 帮我看看这个")
    check("答的就是屏幕上最新一条 -> 裸回不引用", quoted == [], str(quoted))
    check("代码默认阈值＝1（不再要求隔满 4 条）", M.QUOTE_GAP_DEFAULT == 1, str(M.QUOTE_GAP_DEFAULT))

    print("E12: 贴底时最新气泡必须读得到（1080x2412 实测气泡中心 0.90h）")
    import ocr_channel as OC  # noqa: E402
    L = OC.Line
    scr = [L(210.0, 2093.0, "家人A", 0.99, 180.0, 240.0, 2073.0, 2113.0),
           L(509.0, 2172.0, "@鲸鲸 求求你别犯傻了", 0.97, 300.0, 720.0, 2140.0, 2204.0),
           L(64.0, 2337.0, "の", 0.94, 30.0, 100.0, 2310.0, 2364.0)]
    got = OC.extract_chat_messages(scr, 1080, 2412)
    check("0.90h 的最新气泡被读到并挂上发送者",
          any("求求你别犯傻了" in m["text"] for m in got)
          and any((m.get("sender") or "") == "家人A" for m in got), str(got))
    check("输入框那行(0.97h)不会被当成消息", all(m["text"] != "の" for m in got), str(got))

    print(f"\n===== 极端场景结果: {PASS} passed, {FAIL} failed =====")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
