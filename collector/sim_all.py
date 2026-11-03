# -*- coding: utf-8 -*-
"""sim_all.py — 离线习题单进程总入口（导入与引擎初始化只付一次）。

用法（语料用脱敏名，必须对示例配置跑，否则 runtime config.json 里的真名对不上）：
  $env:SIM_CONFIG = config.example.json 的绝对路径
  python sim_all.py
覆盖：T1-T3 唤醒/游标/引用定位（sim_scenarios，8 项）
     + E1-E10 时序压力：历史追答/重启去重/pending补救/竞态/回声/单行化（sim_extreme，17 项）。
全绿 = exit 0。改测试只为省时：断言合并、S8 类"等满超时"改提前返回。
"""
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import sim_scenarios as A  # noqa: E402
import sim_extreme as B    # noqa: E402

rc = 0
for name, mod in (("scenarios T1-T3", A), ("extreme E1-E10", B)):
    print(f"\n########## {name} ##########")
    try:
        r = asyncio.run(mod.main())
        rc |= int(r or 0)
    except SystemExit as e:
        rc |= int(e.code or 0)
sys.exit(rc)
