# 手机侧联调准备（拿到备用机 / 用自己手机测试时照此办理）

> 这份是 [README.md](README.md) 第 8–9 步的**手机侧细则**：每条物理操作都配一条可验证的判据命令。
> 文中 `<项目目录>`＝你 clone 本仓库的位置，`<AstrBot目录>`＝AstrBot 工作目录，`<py>`＝你给采集器选定的那个 Python（独立进程，自己的 venv 也行；想省事就直接用 AstrBot 那个），`<工具目录>\platform-tools\adb.exe`＝你自己下载的 adb（见 README 第 8 步）。**不要把别人机器上的绝对路径照抄进来。**

## 0. 安全前提（务必先读）

- 手机微信**只登录小号**。退出大号（不是卸载、是退出登录）——否则脚本可能误读/误发你的大号，且所有聊天内容会进入本机日志。
- 你的**主力号要留在另一台设备上**，用来给小号发消息做测试；主力号不要出现在这台手机上。
- 出现任何异常：手机拔线即可物理断链；或在 `<项目目录>\` 根下建一个名为 `PAUSE` 的空文件（`dsh-wechat-phone\PAUSE`，**不是** collector 目录下），采集器立即停止一切输出，删除即恢复，**无需重启**。
- 🚫 **绝对不要在人正在打字回复时强杀采集器**（`taskkill` / 关窗口）。它会把没发完的引文草稿留在微信输入框里，下次开机就得手工清；而且游标/去重表落在 `collector\state.json`，硬杀可能造成旧消息重刷。要停就**先建 `PAUSE`，等这一轮日志安静下来再 Ctrl+C**。
- 行为风控由小号承担：保持低频（默认闸门：单会话≤4 条/分、全局≤20 条/时、日封顶 200 条、深夜静默——但**静默窗口取决于你 `config.json` 里的 `gate.quiet_hours`，两个数字相等即关闭静默**）。前两周只在家庭小群活动。

## 1. 手机开发者设置

1. 设置 → 关于手机 → 连点「版本号」7 次 → 开启开发者选项
2. 开发者选项 → 打开 **USB 调试**
3. （小米/华为等）额外打开 **USB 调试（安全设置）**——否则 `input tap` 会被拒；小米开它通常还需**登录厂商账号 + 插 SIM 卡 + 联网**，请提前弄好
4. 有「**权限监控**」「OOH 触控守护」类开关的机型先**关闭**，否则每次自动化点击都会弹窗拦停
5. **关闭锁屏密码（PIN/图案/指纹解锁进入）**，并把自动锁屏设为"永不"、开发者选项开「充电时不休屏」——采集器只会唤醒屏幕、**不会替你解锁**，一锁屏整条链路当场失明
6. 数据线连电脑，手机弹窗「允许 USB 调试」→ 勾选"一律允许"

## 2. 电脑侧确认

```powershell
& "<工具目录>\platform-tools\adb.exe" devices
```

出现设备号 + `device` 即成功（`unauthorized` 就重新插线并在手机上点允许；列表为空就检查数据线是否为数据线、厂商 USB 驱动、以及是否只给了"仅充电"权限）。

多台设备同时在线时，把设备号填进 `config.json` 的 `serial`。

判据（顺手确认屏幕可控）：

```powershell
& "<工具目录>\platform-tools\adb.exe" shell input tap 1 1     # 不报错＝手指可用
& "<工具目录>\platform-tools\adb.exe" shell wm size           # 报出分辨率，采集器按屏幕比例定位
```

## 3. 微信设置（小号登录后）

- 我 → 设置 → 新消息通知 → **通知显示消息详情：开**；系统通知设置里允许微信横幅/锁屏通知
- 设置 → 通用 → 「听文字消息」**关**；聊天 → 「回车键发送消息」**开**（采集器用回车交卷）
- 系统电池设置里把微信设为**不优化 / 允许后台活动**（国产 ROM 杀后台＝什么都读不到）
- 装**官方手机版微信**（别用 HD/平板版），版本保持当前稳定版即可；**不要开微信的自动更新**——大改版会让界面识别规则失效，届时按 README 附录 B 用 `dump-ui.py` 重新校准
- 想好它在群里的名字，填进 `config.json` 的 `bot_nicknames`；**同时在小号上给你的主力号设置备注名**——群里 @ 显示的是"你给对方起的备注"，这些写法要同时进 `bot_nicknames` 和 `wake_keywords`
- 把小号拉进要常驻的那个群，群名填进 `config.json` 的 `home_chat`（采集器**只守这一间**）

## 4. 中文输入（ADBKeyboard）

本仓库**不打包第三方 APK**（`.gitignore` 已排除 `assets/*.apk`），请从上游自取：

1. 上游仓库：https://github.com/senzhk/ADBKeyBoard → 下载 `ADBKeyBoard.apk`，建议存成 `<项目目录>\assets\ADBKeyboard.apk`（目录不存在就先建）
2. 装到手机：
   ```powershell
   & "<工具目录>\platform-tools\adb.exe" install -r "<项目目录>\assets\ADBKeyboard.apk"
   ```
3. **手机上手动启用**（首次无法自动化）：设置 → 系统和输入法 → 其他键盘/管理键盘 → 打开 ADBKeyboard，并同意"可能收集所有输入"的安全提示
4. 判据：
   ```powershell
   & "<工具目录>\platform-tools\adb.exe" shell ime list -s | Select-String adbkeyboard
   ```
   能列出 `com.android.adbkeyboard/.AdbIME` ＝ 就位
5. 之后每次启动采集器会自动 `ime set com.android.adbkeyboard/.AdbIME`（`config.json`：`"input_method": "adbkeyboard"`）；退出后系统输入法可能被改走，介意的话手动切回原输入法

> 只在纯英文环境下试跑，可把 `input_method` 改成 `ascii`（走 adb 直接键入，不需要 APK）。剪贴板方案（scrcpy 之类）作为后续备选，当前未实现。

## 5. 启动（顺序很重要）

```powershell
# 1) 先让 AstrBot 起来（含翻译插座）。用什么方式起就用你第 3 步那套，然后验端口：
Test-NetConnection 127.0.0.1 -Port 6199      # 期望 TcpTestSucceeded : True
# 2) 体检（A 电脑/AstrBot 侧 + B 手机侧，不插手机也能先查 A；AstrBot 没起时端口与 6185 两项必红）
cd <项目目录>\collector
<py> preflight.py
# 3) 上岗（首次建议前台跑，方便看日志）
<py> main.py
# 4) 手机保持亮屏、停在常驻会话里（采集器会自己把窗口带回 home_chat）
```

想先不接手机验一遍"大脑 ↔ 插座"：`<py> main.py --selftest`（不碰 adb，直接对桥发一帧等回复）。

## 6. 冒烟测试顺序（启动行 + 五个确保）

日志文件：`<项目目录>\logs\collector.log`。下面每一步都给了**期望出现的日志锚点**，对不上就是那一层断了，别跳着查。

| # | 动作 | 期望锚点 | 断在哪一层 |
|---|---|---|---|
| 1 | 启动采集器 | `bridge ws connected`；AstrBot 侧 `[wxb] collector connected` | 端口/token/白名单 |
| 2 | 在**常驻群**发「鲸鲸，你在吗」（含唤醒词） | `inbound -> bridge` | 屏幕识别 / 唤醒词 |
| 3 | 等 20–60 秒 | AstrBot 侧无报错、采集器 `replied:` 且手机真的打出气泡 | 模型水电 / 润色 / 输入发送 |
| 4 | 群里明确 `@鲸鲸 在吗` | 同上（`at=True`） | @ 判定（备注名不在词表） |
| 5 | 群里闲聊、**不含**唤醒词 | 无任何 `inbound`（沉默） | 正常，别当故障 |
| 6 | 建 `PAUSE` 再发唤醒词 | 无输出动作；删掉即恢复 | 急停链路 |

> ⚠️ **私聊不是独立通道**：当前实现是"单会话驻留"模式，采集器只读 `home_chat` 那一间、也只往那一间写。把 `home_chat` 设成某个私聊标题即可跑私聊，但消息是以群会话身份进管线，**要含唤醒词或被 @ 才会回**。旧文档里的"通知轮询 / uiautomator dump"通道已废弃，别再照着它排查。

## 7. 出问题先看什么（分层定位）

1. **完全没日志** → 进程没起来：`logs\collector-boot.out`（守护路线的启动期输出）+ 确认用的是哪个 `<py>`
2. **`no adb device`** → 第 2 节的设备/授权/线缆
3. **`unauthorized`／连不上 6199** → token 两边不一致，或 AstrBot 没起、平台没启用
4. **有 `inbound`、无 `replied:`** → 问题在 AstrBot 侧：6185 登录、第 4 步两个 provider 是否实测过、人格是否已设为默认、插件是否装了并启用
5. **有 `replied:`、手机上没气泡** → 输入法没启用／`input tap` 被厂商开关拦／锁屏了
6. **`reply throttled/dropped`** → 闸门限流（第 0 步），属正常保护
7. **`reply for 'xxx' ignored (home-only mode)`** → 回复目标是别的会话，被单会话规则丢弃：核对 `home_chat`

> 跑 `preflight.py` 会在 AstrBot 日志里留下一两条 `EOFError: connection closed while reading HTTP request line`——那是体检的端口探测敲了 6199 却没发 HTTP 请求，属正常噪音，不是链路故障（体检**不会**真连 WebSocket，避免把 AstrBot 排队的回复骗到探测连接上）。

要 7×24 常驻：仓库带 `start-collector-bg.bat` + `collector-watchdog.ps1`（命名互斥防双开；正常崩溃 15 秒重启，连续 3 次秒退会自动退避到 60 秒一轮）。**脚本里没有任何机器路径**：它们先调 `tools\resolve-env.ps1`，按「环境变量 `DSH_WX_PYTHON`/`DSH_WX_ADB` → `collector\config.json` 的 `python`/`adb_path` → 上一级目录的 `python\python.exe` 与 `tools\platform-tools\adb.exe` → PATH」的顺序找解释器和 adb；实在找不到会打 `python not resolved` 并退出（`run-once.cmd` 返回 3、watchdog 返回 4），此时用上面两个环境变量或 `config.json` 字段硬指定即可。想知道守护将用哪个解释器，直接跑 `powershell -File tools\resolve-env.ps1` 看 `PY=` 那行。

**停机纪律**：先建 `PAUSE`，等日志这一轮安静下来，再按 **watchdog → cmd 包装 → python** 的顺序停（反过来守护会把它重启回来）。手机没插时 `main.py` 会以 `no adb device` 退出、守护按上面的退避节奏重试，插上就自愈，不用人工干预。注意：**从某个终端里 `Start-Process` 起的守护，会随那个终端的进程树一起被回收**——要长期常驻就用「启动」文件夹快捷方式或任务计划程序拉起，别挂在会话窗口下。

**想前台调试就先停守护**：`main.py` 自带单实例锁（`Local\AstrBotWxCollectorMain`）。守护已经拉起一个采集器时，你再手敲 `python main.py` 会直接看到"已有采集器在跑"并退出——这是保护，不是故障：两个采集器会抢同一块屏幕，重复回复，还可能把半截引文草稿留在微信输入框里。`--selftest` 不受该锁限制，可以边跑守护边验桥路。

## 已知限制（诚实清单）

- 读屏**只靠 OCR**（`adb exec-out screencap` + RapidOCR），一轮约 0.5–1.5s，期间手机屏幕被占用，别同时玩手机；
- 只处理文字消息，图/语音/视频跳过；
- 免打扰/折叠的群消息不会主动扫（当前是单会话驻留模式）；
- 微信大版本更新可能改界面结构，届时用 `collector/dump-ui.py` 重采样本（截图）、校准 `collector/ocr_channel.py` 的版面规则；旧的 `wechat_ui.py`（uiautomator 解析）已随微信 8.0.7+ 失效，不再参与运行；
- 无线 adb 调试未验证，请用数据线。
