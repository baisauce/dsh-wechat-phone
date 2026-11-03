# -*- coding: utf-8 -*-
"""dump-ui.py — save a labelled screenshot sample for OCR-layout calibration.

用法：先在手机上停到对应页面，再：
  python dump-ui.py home        # 微信会话列表页
  python dump-ui.py chat        # 某个群/私聊聊天页
  python dump-ui.py chat-group  # 群聊页（带发送者昵称样本）
输出会存到 calibration/（*.xml 是 uiautomator 快照，微信 8.0.7+ 后已失效，仅存档；
*.png 是截图，用来对照调 ocr_channel.py 的版面规则）。
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from adb_client import Adb  # noqa: E402

def main() -> None:
    label = (sys.argv[1] if len(sys.argv) > 1 else "sample").replace("/", "_")
    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8-sig"))
    adb = Adb(cfg["adb_path"], cfg.get("serial") or None)
    out_dir = os.path.join(HERE, "..", "calibration")
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    xml = adb.dump_ui()
    w, h = adb.screen_size()
    focus = adb.current_focus()
    xml_path = os.path.join(out_dir, f"{label}-{stamp}.xml")
    open(xml_path, "w", encoding="utf-8").write(xml)
    try:
        png = adb.shell("screencap -p /sdcard/_wxb_cap.png")  # noqa
        adb._run(["pull", "/sdcard/_wxb_cap.png", os.path.join(out_dir, f"{label}-{stamp}.png")])
        png_path = "png saved"
    except Exception as e:
        png_path = f"png skipped: {e}"
    print(f"saved: {xml_path}")
    print(f"screen: {w}x{h} focus: {focus} | {png_path}")
    print("把 xml（和 png 截图）发给开发者即可校准消息解析")

if __name__ == "__main__":
    main()
