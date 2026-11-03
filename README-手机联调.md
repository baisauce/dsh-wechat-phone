# 手机侧联调准备（拿到备用机 / 用自己手机测试时照此办理）

## 0. 安全前提（务必先读）
- 手机微信**只登录小号**。退出大号（不是卸载、是退出登录）——否则脚本可能误读/误发你的大号，且所有聊天内容会进入本机日志。
- 出现任何异常：手机拔线即可物理断链；或在 `dsh-wechat-phone\` 下建一个名为 `PAUSE` 的空文件，采集器立即停止一切输出（入站仍记录）。
- 行为风控由小号承担：保持低频（默认闸门：单会话≤4条/分、全局≤20条/时、凌晨1:00-7:30静默）。前两周只在家庭小群活动。

## 1. 手机开发者设置
1. 设置 → 关于手机 → 连点「版本号」7 次 → 开启开发者选项
2. 开发者选项 → 打开 **USB 调试**
3. （小米/华为等）额外打开 **USB 调试（安全设置）**——否则 input tap 会被拒
4. 数据线连电脑，手机弹窗允许调试

## 2. 电脑侧确认
```powershell
& "D:\Program Files\AstrBot\tools\platform-tools\adb.exe" devices
```
出现设备号 + `device` 即成功（`unauthorized` 就重新插线并在手机上点允许）。

## 3. 微信设置（小号登录后）
- 我 → 设置 → 新消息通知 → **通知显示消息详情：开**（否则通知内容读不到，只能靠 UI 轮询兜底）
- 系统通知设置里允许微信横幅/锁屏通知
- 设置 → 通用 → **听文字消息保持关**；聊天 → 「回车键发送消息」确认为**开**（采集器用回车发送）
- 把小鲸（小号自己）的群昵称/备注想好，填进 config 的 `bot_nicknames`（用于识别 @）

## 4. 中文输入（二选一）
**方案 A：ADBKeyboard（已备好，无需下载）**
1. APK 位置：`D:\Program Files\AstrBot\dsh-wechat-phone\assets\ADBKeyboard.apk`（senzhk/ADBKeyBoard 官方仓库，17KB）
2. 装到手机：`& "D:\Program Files\AstrBot\tools\platform-tools\adb.exe" install -r "D:\Program Files\AstrBot\dsh-wechat-phone\assets\ADBKeyboard.apk"`
3. 手机设置 → 输入法 → 启用 ADBKeyboard（或安装后直接点通知栏切换）
4. 采集器启动时会自动 `ime set com.android.adbkeyboard/.AdbIME`（config: `"input_method": "adbkeyboard"`）

**方案 B：scrcpy 剪贴板（免 APK，复杂，后续我来实现）**
config 改 `"input_method": "ascii"` 仅当全英文测试用。

## 5. 启动
```powershell
# 1) AstrBot 应已在跑（start-astrbot.bat），确认桥端口
Test-NetConnection 127.0.0.1 -Port 6199
# 2) 启动采集器（新窗口）
& "D:\Program Files\AstrBot\dsh-wechat-phone\collector\..\start-collector.bat"
# 3) 手机保持亮屏解锁（开发者选项里可开「充电时不休屏」）
```

## 6. 冒烟测试顺序
1. 用**大号或朋友的号**给小号发一条私聊 → 3–8 秒内应看到采集器日志 `inbound -> bridge`
2. 等小鲸回完，看手机微信里是否真的发出了回复气泡
3. 把小号拉进一个测试群，群里发「小鲸，你在吗」→ 应触发唤醒词回复
4. 群发普通闲聊（无关键词）→ 应保持沉默
5. 建 `PAUSE` 文件 → 再发消息 → 不应有任何输出动作

## 已知限制（诚实清单）
- 消息发现靠通知轮询（2s）+ 进会话读屏，**未读折叠/免打扰群收不到通知** → 免打扰的群需要后续加「下拉列表扫描」兜底
- uiautomator dump 每次约 0.5–1.5s，读消息期间手机屏幕被占用，别同时用手机
- 图片/语音/视频消息 MVP 不读（只转发文本），日志会提示跳过
- 微信大版本更新可能改控件结构，届时按 collector.log 里的 dump 样本重新校准 wechat_ui.py 启发式
