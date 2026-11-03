# dsh-wechat-phone · 让 AI 住进一台手机里的微信

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> ⚠️ **先读这条。** 微信是全国用户最多的聊天软件之一，屏幕对面很可能还有**不熟悉、也分不清"AI 机器人"的中老年长辈**。本项目是开源学习用品，只供大家学习交流：**严禁用来冒充任何真人身份，或实施欺骗、骚扰、营销群发等违法违纪行为。** 请让它以"明牌的机器人"身份说话——小号登场、人设公开、白名单内活动，并让群里的家人知道它是个 AI。这既是风控底线，也是对长辈最基本的尊重。

一句话说明白这个项目：**你有一个很聪明的大脑（大模型），但它没有手、没有嘴，碰不到微信**。微信官方也没给个人账号开"进群里聊天"的门。所以这个项目给它造了一具"手机身体"——一台挂着小号的安卓真机——让 AI 接管它的眼睛和手：看群友说话，用家人的口吻打字回复。

全程微信本体干干净净：**不破解、不注入、不改微信一根手指头**，AI 只是像人一样"操作"这台手机。

> ## 🤖 先看这条：活基本不用你干
>
> 完成第 1、2 步（**装好 DSH + 买好 API**）之后，下面第 3–9 步里**电脑端的操作几乎全部可以直接交给 DSH 去做**——装 AstrBot、配模型、建人格、装插件、装本项目、连手机调试、跑体检、起服务，一个都不用亲手敲命令。把本仓库地址（https://github.com/baisauce/dsh-wechat-phone ）甩给它说一句「按 README 第 3–9 步帮我部署」就行，出错了它也负责按附录 B 的坑表排查。
>
> 只有两类事必须你亲手：💰 **掏钱**（买 key，第 2 步）和 📱 **碰手机**（插数据线、连点版本号、允许调试、扫码登小号、把小号拉进群——第 8 步）。本项目的全部部署就是这么干出来的，连这份 README 都是。
>
> 📌 给读到这里的 AI 助手：本文件是人话版教程，**字面可执行的锚点（确切命令、字段名、日志判据）都写在步骤里**；手机侧另有更细的 [README-手机联调.md](README-手机联调.md)。两份若有冲突，以本文件的**当前实现口径**为准（第 8、9 步已按"单会话驻留 + 纯 OCR"重写）。动手前先跑第 9 步开头的离线自检。

## 先看这张对照表，后面所有名词都靠它

| 比喻 | 它其实是 | 干什么 |
|---|---|---|
| 🧠 大脑 | 大模型 API（DeepSeek / 千问订阅） | 唯一的活：把一句话想成得体的话 |
| 🦴 身体与神经系统 | AstrBot 框架 | 让大脑有耳朵、有嘴、有记性、能 24 小时值班 |
| 🎭 性格面具 | persona 人格 | 决定它是"谁"、怎么说话 |
| 📔 日记本和档案柜 | LivingMemory 插件 | 记住群里发生过的关系和事 |
| 💅 表达教练 | wanna_be_human 插件 | 把课本腔改写成日常口语（要花时间润色，所以回复慢） |
| 👀🤖 借给 AI 的眼睛和手 | collector 采集器（本仓库主体） | 盯着手机屏幕认字、替 AI 点按和打字 |
| 🔌 翻译插座 | 平台适配器插件 | 采集器的话和 AstrBot 的话语言不通，靠它互译 |
| 🚦 礼仪老师 | gate 限速闸门 | 管它"什么时候闭嘴、多久说一句" |
| 🔑 访客名单 | AstrBot 平台配置里的 `allowed_chats`（配合 `auto_accept=false`） | 名单外的群和人，它装死 |
| 🏠 常驻的那一间 | 采集器配置里的 `home_chat` | 采集器只守这一个微信会话标题，读它、也只往它写 |
| 🛑 电梯急停钮 | 项目根目录建 `PAUSE` 文件 | 出现任何不对劲，一秒让它全部闭嘴 |

> ⚠️ **访客名单填在哪，是新手最常搞混的一处。** 名单是**翻译插座（AstrBot 侧）**的规矩，字段叫 `allowed_chats`；采集器配置里那个长得像名单的 `watch_chats` **当前代码不读取**，填了不生效（详见第 7 步与附录 B）。真正的"只跟谁玩"要两处一起设：`home_chat` 定住哪一间，`allowed_chats` 定谁能进管线。

## 为什么非要一台真手机？

微信对个人号的态度是：**想和微信群聊？没有接口**。市面上的野路子（协议号、hook、注入客户端）等于让 AI 伪造一个假微信去骗腾讯——账号风险极大，也违背本项目底线。我们的路线是笨功夫但干净的路：让 AI 操作**一台真实的手机上的真实微信**，在腾讯眼里，手机屏幕前就是"一个人"。这台手机用**小号**登录——它扮演身体，所有风险由小号承担，和你的主力微信号彻底无关。

> 本项目还有一条贯穿始终的设计主线——**大脑只管说话，看屏幕和动手全交给固定代码**。为什么这么选、和另外两条路线差在哪，写在文末附录 D；赶时间可以先跳过。

---

# 新手安装指南（从零到第一条回复）

> 🤖 再次提醒：走到这里如果第 1、2 步已完成（DSH 装好、key 买好），**第 3 步起电脑端的操作全部可以甩给 DSH**，下面的步骤既是教程、也是给它的任务清单，各步的检查点（"怎么算装好了"）都写在正文里；只有第 8 步的手机物理操作必须亲自上手。

## 第 0 步：备料

| 需要什么 | 说明 |
|---|---|
| 一台 Windows PC | 什么都不用预先装——从第 3 步起，包工头 DSH 连 Python 都会自己弄好 |
| 一台安卓手机 | 备用机即可，能开 USB 调试；**必须能关掉锁屏密码**（见第 8 步） |
| 一个微信**小号** | 大号退出登录，只登小号——它是 AI 的"身体"，风险都算它的 |
| 一根数据线 | 采集器全程走 USB adb；**不支持无线调试**（未测试，别指望） |
| 你的主力号在**另一台设备**上 | 用来给小号发消息做测试。小号那台机器上不要登大号 |
| 一个能上 GitHub 与 PyPI 的网络 | 国内网络直连经常失败，备好代理或镜像源（第 3、6、9 步都要下载） |

> **小号从哪来**是新手第一个真正的坎：微信新号注册通常需要**另一个已实名账号辅助验证 + 本人手机号**，新设备登录还可能有二次验证。请把这台手机当作"一台独立的、只登小号的设备"来准备，别指望十分钟搞定注册。
>
> **电脑侧的隐形前置**：电脑不能睡眠（会掐断 adb 与 OCR）、 adb 工具链要下载（第 8 步给命令）、Python 由 DSH 自己搞定（第 9 步会讲清"到底用哪个 Python"）。

## 第 1 步：先装 DSH——你的包工头

后面的活不少：装 AstrBot、开端口、验证配置、连手机、排错。好消息是**这些全都可以不亲手做**——装一个 DSH（DeepSeek Harness），给它目标，它当手去操作电脑。本项目的完整开发历程（包括这份 README）就是在 DSH 会话里干出来的。

1. 从官方渠道获取 DSH 的 Windows 安装包，装好后打开是本机的网页操作台；
2. 在 DSH 里配好按月份额制的模型订阅（千问 Token Plan 类）——**这一步花完钱，你的包工头就已经能干活了，不必先买别的**；
3. 之后第 3 步起的每一步，都可以直接对它说："照这个仓库 README 的第 3–9 步帮我部署"。

> 给它放行文件写入与命令行执行（它要装东西、跑 adb）。如果你的 DSH 权限受限，第 3、9 步那些安装命令就得你自己敲——**这不影响链路本身**。

## 第 2 步：给"大脑"买口粮（聊天模型 API）

AstrBot 里那颗大脑每说一句话都要调用一个模型 API。两种买粮方式：

- **方式 A：DeepSeek 开放平台**——像点外卖：注册、充几十块、用多少扣多少（拿一个 `sk-` 开头的 key）。聊天量不大的家庭群，几十块能吃很久。
- **方式 B：千问 Token Plan 类套餐**——像食堂包月：固定月费随便吃。如果和第 1 步 DSH 用同款订阅，一份饭喂两个劳动力，最省。

> ⚠️ **唯一容易翻车的点：上面两种粮仓都不卖"图书管理员"。** 记忆插件需要一种叫 embedding 的向量化服务（把每句话编上索引号，日后才查得到），而对话套餐/对话模型 API **一般都不含**这个能力——DeepSeek 也没有 embedding 接口。所以要**单独**备一份便宜的按量 embedding key，例如阿里 DashScope（百炼）的 `text-embedding-v4` 模型。**两套钥匙，分开放**：一把管说话，一把管索引。

## 第 3 步：搭身体——让 DSH 装 AstrBot

这一步**不用你手动装**。打开 DSH 的网页操作台，新建一个会话，把下面这段话发给它（连同本仓库链接，或直接粘贴这份 README 全文）：

> 按这个仓库 README 的「第 3 步」帮我安装 AstrBot：Windows 系统，Python ≥ 3.10，WebUI（控制室）端口 6185。参考资料：官方文档 https://docs.astrbot.app/deploy/ 和 README 里给包工头的坑提示。装好告诉我登录用户名和初始密码。

给它的落地提示（下面三条：前两条是官方路线，第三条是作者机的便携目录做法，都是正路；选一条即可，**别去发明其它野路子**）：

- **官方 Windows 安装脚本**：`irm https://docs.astrbot.app/install.ps1 | iex`（脚本会装 uv + Python 3.12 + AstrBot）；注意**脚本装出来的实例不支持在 WebUI 里升级**，以后更新走 `uv tool upgrade astrbot --python 3.12`。
- **uv 方式**：`uv tool install astrbot --python 3.12`，然后在你想放数据的工作目录里执行 `astrbot init`，用 `astrbot run --port 6185` 启动。
- **第三种（作者机在用）**：一个自带 `python\python.exe` 的便携目录（嵌入式 Python），改 `python*._pth` 启用 `import site` 后 `pip install astrbot`。好处是完全不碰系统环境；坏处是升级要手动 `pip install -U astrbot`，且第 9 步的 `<py>` 就是它。

验收清单（三条都要有明确答复才算这步成了）：

1. 浏览器打开 `http://localhost:6185` **出现登录界面** = 装好了；
2. **登录凭据**：默认用户名是 `astrbot`，**密码是首次启动时随机生成并打印在启动日志里的初始密码**（旧版固定密码 `astrbot` 已废弃）。让它把那一行日志找出来给你；登录后会强制要求改密码，顺手把新密码存到你自己的密码管理器；忘了就 `astrbot run --reset-password`，新密码同样打印在日志里；
3. **常驻方式**：让 DSH 给你做一个"启动/停止"脚本，别让它把 AstrBot 开在你正在打字的那个终端里。

> 发给它的三条坑提示（我们全踩过，建议随任务一并贴上）：Windows 下给常驻程序写日志要用 `cmd.exe /c "... >> 文件 2>&1"` 包装，**别用 PowerShell 的 `>>`**（它会把干活的进程一起带走杀掉，而且写成 UTF-16）；守护脚本要加命名互斥防止开出两个分身抢同一个日志文件；如果它选择"嵌入式 Python"路线，要改 `python*._pth` 启用 `import site` 才装得进第三方包。
>
> ❌ **不要配 6195 端口。** 网上/AstrBot 配置里能看到的 6195/6194 是**企业微信/公众平台回调**用的默认端口，和本项目无关；本项目只用两个端口：`6185`（WebUI）和 `6199`（第 7 步的翻译插座）。

## 第 4 步：给大脑接上两路水电（配置模型）

控制室 → 模型提供商：

1. **对话模型**：填第 2 步的 key——DeepSeek 直接选内置提供商；包月套餐选 **OpenAI 兼容 API** 那种提供商，把服务商给的 `base_url`（形如 `https://.../v1`）和模型名一起填进去；**设为默认**——接上"说话能力"；
2. **embedding**：新建一个 **DashScope（阿里云百炼）**提供商，填那把单独的 key，**勾选/保存 embedding 能力并确认模型名是 `text-embedding-v4`**——接上"记性"。

这两项也可以在控制室网页上自己点，或者继续对 DSH 说一句「按 README 第 4 步配好两个 provider，并实测 embedding」。

> **改完提供商要重启 AstrBot**，不然插件读不到新登记的水电工。
>
> 检验记性的坑：有些记忆插件启动时只检查"有没有登记这个水电工"，**并不真的打个电话验证**——key 是错的它也显示成功。所以务必实测：让机器人记一件事，重启后再问它。它答得上来，档案柜才是真的通了电。
>
> ⚠️ **别把对话套餐的 key 拿来当 embedding 用**（纯对话套餐里没有向量模型，填上必然报错）；也别用带签名会轮换的临时 key 长期跑——**embedding 的 key 一旦失效，记忆会静默变瞎**，表面上一切正常。

## 第 5 步：戴上性格面具（建人格）

控制室 → 人格管理 → 新建：起个名字（下例叫 `小鲸`，群里别名 `鲸鲸`），把 system prompt 贴进去。

仓库备了张白纸面具 [templates/persona.example.txt](templates/persona.example.txt)：身份 / 语气 / 行为边界 / 示例对话四段，把里面的占位称呼叫成你自己的（谁是你"我爸"、哪个群是家），就是它的人格。然后**把这张面具设为默认人格**（人格管理里选为默认，或在你要它干活的会话上指定）——不戴面具之前，它只是个客服腔的模型。

必须替换的占位项就四类，别漏：

| 占位 | 换成 |
|---|---|
| 名字与别名 | 它在群里被叫到的**每一个**写法（这些还要抄进第 7、8 步的唤醒词/昵称） |
| "我爸"是谁 | 你（主人）在微信里的昵称/备注名 |
| 常驻的群 | 与采集器 `home_chat` **完全一致**的群名 |
| 输出格式硬规则 | **每条回复必须单行、不许换行**（微信里换行的气泡一眼机器味）；这条建议原样保留，别删 |

## 第 6 步：请日记本和表达教练（装两个插件）

控制室 → 插件市场，搜这两个**准确包名**（显示名可能不同，按包名搜最稳）：

1. **`astrbot_plugin_livingmemory`**（📔 日记本，显示名 LivingMemory）：聊天内容自动归档进向量库，下次谁再说话，先去档案柜翻相关旧事再开口。
2. **`astrbot_plugin_wanna_be_human`**（💅 表达教练，「好想成为人类啊」）：模型初稿往往像播音腔，它负责改写成人话——"收到，请问有什么可以帮您"变成"在呀，怎么这个点才想起我？"。

> 命令行等价操作（**先 cd 到 AstrBot 工作目录**——`astrbot plug` 拿**当前目录**当 AstrBot 根目录，跑错地方会报 `... is not a valid AstrBot root directory. Use 'astrbot init' to initialize`；也可以先 `$env:ASTRBOT_ROOT = "<AstrBot目录>"`。**GitHub 直连不畅时加 `--proxy`**）：
>
> ```powershell
> astrbot plug search livingmemory
> astrbot plug install astrbot_plugin_livingmemory
> astrbot plug install astrbot_plugin_wanna_be_human
> # 市场下载不动时：astrbot plug install astrbot_plugin_livingmemory --proxy https://gh-proxy.example.com/
> ```

装完这两件事必须确认，否则第 9 步会"能说话但没记性"：

- **LivingMemory**：插件设置里的 `provider_settings.embedding_provider_id` **留空即可**（自动挑第 4 步那个 embedding 提供商）；想指定就填它的 id。
- **wanna_be_human**：默认配置即生效，不用改。（嫌回复慢再看第 10 步，那两个参数就在这里。）

> 心理预期：教练润色要时间，这两件一加，**端到端一条回复要 20–60 秒**。家人聊天场景完全没问题；嫌慢看第 10 步。

## 第 7 步：装翻译插座（本项目适配器）

采集器（后面装）说的是"WebSocket 帧"，AstrBot 说的是"IM 消息"，中间插一个翻译插座——它就在本仓库里。

> **最省心的方式**：把这句直接发给 DSH——"克隆 https://github.com/baisauce/dsh-wechat-phone ，然后照它 README 的第 7–9 步帮我装好翻译插座、配好采集器并跑通冒烟测试"。以下为手动等价操作：

```powershell
git clone https://github.com/baisauce/dsh-wechat-phone
# 上一步失败（GitHub 直连不通）就改用镜像前缀，或让 DSH 下 zip 解压：
#   git clone https://gh-proxy.example.com/https://github.com/baisauce/dsh-wechat-phone
# 把适配器拷进 AstrBot 的插件目录（目录名不要改）
# <AstrBot工作目录> = 第 3 步跑 astrbot init 的那个目录（里面有 data\plugins 和 .astrbot 文件）
Copy-Item -Recurse dsh-wechat-phone\adapter\data-plugins\astrbot_wechat_phone_bridge `
  <AstrBot工作目录>\data\plugins\
# 控制室 → 平台 页新建平台，类型选「微信群手机桥接」，填这六样：
#   ws_host=127.0.0.1          ← 默认是 0.0.0.0（整个局域网都能连），采集器就在本机，收到 127.0.0.1 更稳
#   ws_port=6199
#   token=<你自己编的一串长随机字符>      ← 第 9 步要用同一串，见下方"门禁卡闭环"
#   auto_accept=false                    ← 默认是 true＝来者不拒；关了它才真吃下面这份名单
#   allowed_chats=示例家庭群              ← 访客名单：群名或联系人备注名，多个就列多条
#   wake_keywords=小鲸,鲸鲸               ← 逗号分隔的**一个字符串**（不是数组）
# 重启 AstrBot，日志出现 [wxb] ws listening on 127.0.0.1:6199 = 插座就位
```

平台类型的内部 id 是 `wechat_phone_bridge`，在 AstrBot 列表里显示为「微信群手机桥接 (WeChat Phone Bridge)」——找名字时按这几个字任一个都能对上。

> 🔑 **门禁卡闭环（新手必踩，一次讲透）**：这个 token 有**两个存放点**，必须**逐字相同**：
>
> 1. AstrBot 侧：平台配置里的 `token` 字段（控制室手填）；
> 2. 采集器侧：`collector\config.json` 里的 `bridge_token`（直接填字符串）**或** `bridge_token_file`（填一个文件路径，文件内容就是那串 token）。
>
> AstrBot **不会**自动把 token 写成文件——所以走"文件"路线时你得自己创建那个文件（第 9 步有命令）。嫌麻烦就**只用 `bridge_token` 内联字段**，把 `bridge_token_file` 留空。
>
> ✅ **两边对不对得上，`preflight.py` 会替你查**：它会**只读**打开 AstrBot 的 `data\cmd_config.json`，找到 `type=wechat_phone_bridge` 那个平台条目（注意它的键是**扁平**的，`token`/`ws_port`/`auto_accept` 直接挂在条目上），然后核对四件事：① token 是否逐字一致（不一致直接红灯——留空更危险：适配器只在 token 非空时校验，留空＝门禁失效）；② `ws_host` 是不是还写 `0.0.0.0`（暴露到局域网）；③ `auto_accept` 是否还开着（开着＝名单形同虚设）；④ 采集器的 `wake_keywords` 有没有全部覆盖进 AstrBot 那份。AstrBot 不装在默认位置时，在 `config.json` 里把 `astrbot_config` 指到那个 `cmd_config.json` 即可。**全程不连 6199、不碰 AstrBot 进程**，所以不会把排队的回复骗走。

## 第 8 步：给身体做"开机体检"（手机准备）

> 这一步的每一项都物理发生在手机上，AI 帮不了你。更细的判据命令在 [README-手机联调.md](README-手机联调.md)。
> 下文尖括号都是**你自己的**路径占位：`<工具目录>`＝你放 platform-tools 的目录，`<AstrBot目录>`＝AstrBot 工作目录，`<py>`＝第 9 步说的那个 Python。**不要把作者机器上的绝对路径照抄进配置。**

1. **装 adb（先装这个，后面全靠它）**：下载 Google 官方 platform-tools → https://developer.android.com/tools/releases/platform-tools ，解压到 `<工具目录>`（得到 `<工具目录>\platform-tools\adb.exe`）。第 9 步要把它的路径填进 `adb_path`。
2. 手机：设置 → 关于手机 → 连点版本号 7 次 → 开发者选项 → **开 USB 调试**；国产 ROM 通常还要开 **USB 调试（安全设置）**（小米/华为：开它需要登录厂商账号、有的还要求插 SIM 并联网），否则 AI 的"手指"点不动屏幕；有「**权限监控**」开关的机型请先**关掉**，它会在每次 tap 时弹窗拦住自动化。
3. **关掉锁屏密码、自动锁屏设为永不**：采集器只会唤醒屏幕、**不会替你解锁**。带 PIN/图案锁的手机一锁屏，整条链路当场失明。
4. 连电脑，确认手已接上（把路径换成你自己的）：
   ```powershell
   & "<工具目录>\platform-tools\adb.exe" devices
   ```
   出现设备号 + `device` = 成功；`unauthorized` 就重插线并在手机弹窗点"允许"。多台设备时，把第 9 步配置里的 `serial` 填成这台设备的序列号。
5. **装 AI 专用键盘 ADBKeyboard**（本仓库**不打包**第三方 APK，需从上游自取）：仓库 https://github.com/senzhk/ADBKeyBoard ，下载其 `ADBKeyBoard.apk`。注意 clone 下来**没有** `assets\` 目录（被 `.gitignore` 忽略），先建再放、再安装：
   ```powershell
   New-Item -ItemType Directory -Force dsh-wechat-phone\assets | Out-Null
   # 把下载的 ADBKeyBoard.apk 放进 assets\（文件名随意，下文以 ADBKeyboard.apk 为例）
   & "<工具目录>\platform-tools\adb.exe" install -r "dsh-wechat-phone\assets\ADBKeyboard.apk"
   ```
   然后在手机上**手动启用**：设置 → 系统和输入法 → 其他键盘/管理键盘 → 打开 ADBKeyboard，并同意那个"可能收集所有输入"的警告。**首次启用无法自动化**；之后采集器启动时会自己把输入法切过去。
6. 装微信（官方手机版，**别用平板版/HD 版**，界面坐标规则不同）、**登小号**、把它的**群昵称**改成你在 `bot_nicknames` 里写的名字；同时**在小号上给你的主力号设置备注名**——群里 @ 时显示的是"你给对方起的备注"，唤醒词要覆盖它（`wake_keywords` 与 `bot_nicknames` 两边都要含这些写法，见附录 B）。
7. 微信里三个开关：通知显示消息详情 = **开**；「回车键发送消息」= **开**（它打字后按回车交卷）；设置 → 电池/应用启动管理里把微信设为**不优化/允许后台活动**（国产 ROM 会把微信后台杀掉，那样什么都读不到）。
8. 把小号拉进要常驻的那个群——它就是第 9 步配置里的 `home_chat`。

## 第 9 步：出厂——跑起来

**先搞清一件事：用哪个 Python。** 采集器是一个**独立进程**，它自己只需要 `websockets` / `rapidocr-onnxruntime` / `pillow` / `numpy` 这几个包；AstrBot 插件跑在 AstrBot 自己的进程里，用的 websockets 由 AstrBot 自带。所以**不必**和 AstrBot 共用同一个环境——共用只是省一次装依赖，分开反而更干净。三选一：

- **复用 AstrBot 的环境**：uv 工具装的解释器通常在 `%LOCALAPPDATA%\uv\tools\astrbot\Scripts\python.exe`——注意 `where.exe astrbot` 给出的是启动器 `astrbot.exe`，**不是**解释器，别直接当 `<py>`；嵌入式装的则是 `<AstrBot目录>\python\python.exe`（记得第 3 步那条 `._pth` 提示）。只是 uv 装的环境归 uv 管，往里塞第三方包不是好习惯（升级时可能被重建）。
- **最省事、最干净**：另建一个独立 venv（或装个系统 Python 3.10–3.12）专跑采集器，把 `requirements.txt` 装进它就行。
- 采集器不需要任何 AstrBot 的库，所以上面两种都成立。

> 省心一点：仓库自带的 `start-collector*.bat` / `collector-watchdog.ps1` 会调 `tools/resolve-env.ps1` 自动找解释器（`DSH_WX_PYTHON` → `config.json` 的 `python` → AstrBot 旁边的 `python\python.exe` → PATH）。你只要把 `config.json` 里的 `python` 填成你选定的那个 `<py>`，以后双击 bat 就不用再管路径。

下面命令里的 `<py>` 就是那个解释器；Windows 上**裸敲 `python` 很可能撞上微软商店的假 stub**，别用裸 `python`。

```powershell
cd dsh-wechat-phone\collector

# ① 装依赖（必须最先装：下面的离线自检本身要 import numpy/PIL/websockets）
<py> -m pip install -r requirements.txt
#    PyPI 直连慢/失败就换镜像：<py> -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# ② 零硬件离线自检（不插手机、不联网也能跑，24 项逻辑题，约 1 分钟）
#    必须指向"示例配置"跑，否则会用你机器上的真群名做断言
$env:SIM_CONFIG = (Resolve-Path .\config.example.json).Path
<py> sim_all.py            # 全绿(exit 0) 才继续；红了先按报错补齐缺的包，别急着连手机

# ③ 配置：抄一份示例配置来改
Copy-Item config.example.json config.json
notepad config.json        # 必改：adb_path、home_chat、bot_nicknames、wake_keywords、token 来源（见下）

# ④ token 闭环：二选一
#    A. 内联（推荐）：把你在 AstrBot 里填的那串写进 config.json 的 "bridge_token"
#    B. 走文件：手动建文件，内容就是那一串；再把 config.json 的 "bridge_token_file" 指向它
Set-Content -Path "<AstrBot目录>\logs\.bridge_token" -Value "<你在 AstrBot 平台配置里填的那串 token>" -Encoding ascii -NoNewline
#    → 然后在 config.json 里写："bridge_token_file": "<AstrBot目录>\\logs\\.bridge_token"

# ⑤ 体检：A 段（配置+门禁卡比对+端口+WebUI）不插手机也能跑；B 段才需要设备
<py> preflight.py          # 逐项体检：手机/桥端口/token 一致性/AstrBot 平台配置，红灯直接告诉你哪个插座没电

# ⑥ 上岗（前台跑，便于第一次看日志；Ctrl+C 停）
<py> main.py
```

配置字段速查（哪些必须动）：

| 字段 | 必填 | 说明 |
|---|---|---|
| `adb_path` | ✅ | 第 8 步那个 adb.exe 的绝对路径 |
| `python` | 建议填 | 跑采集器的解释器绝对路径；`tools/resolve-env.ps1` 优先用它（环境变量 `DSH_WX_PYTHON` 优先级更高） |
| `home_chat` | ✅ | 常驻的那一个微信会话标题（群名或联系人名）；采集器**只读它、只写它** |
| `bot_nicknames` | ✅ | 它在会话里可能被 @ 到的所有写法（含你给对方设的备注名） |
| `wake_keywords` | ✅ | 触发转发的关键词（采集器侧一份；AstrBot 侧还有一份，两处要一致） |
| `bridge_token` 或 `bridge_token_file` | ✅ 二选一 | 与 AstrBot 平台配置的 `token` 逐字一致 |
| `serial` | 多设备时必填 | `adb devices` 第一列 |
| `bridge_ws` | 默认即可 | `ws://127.0.0.1:6199` |
| `astrbot_config` | 选填 | AstrBot `data\cmd_config.json` 的路径；留空则按"仓库上一级\data\"猜。只给 preflight 做**只读**核对用 |
| `gate.*` | 默认即可 | 限速/静默/延迟；`quiet_hours` 两个数字**相等＝关闭夜间静默** |
| `input_method` | 默认即可 | `adbkeyboard`；全英文测试可用 `ascii` |

> 🛑 **`watch_chats` / `outbound_chats` / `notif_poll_s` 是早期"列表轮询 + 通知"架构留下的字段，当前代码不读取它们**——别拿它们当白名单（真白名单在第 7 步的 `allowed_chats` + 本步的 `home_chat`）。示例配置里已删掉这些误导性字段。

**冒烟测试**（五步对应五个"确保"；日志文件是 `dsh-wechat-phone\logs\collector.log`）：

1. 在**常驻群里**发一条含唤醒词的话（例如「鲸鲸，你在吗」）→ 采集器日志出现 `inbound -> bridge`（**耳朵通了**）；
2. 等 20–60s，看手机里真的打出回复气泡、日志出现 `replied:`（**嘴通了**）；
3. 群里明确 `@鲸鲸 在吗` → 回复（**听得懂点名**）；
4. 群里闲聊且不含唤醒词 → 沉默（**知道什么时候不该插嘴**）；
5. 项目根目录新建 `PAUSE` 空文件（`dsh-wechat-phone\PAUSE`，**不是** collector 目录下）再发唤醒词 → 零输出；删掉它立刻恢复，**不用重启**（**急停钮好使**）。

五个全过，收工。想先不碰手机验一遍大脑和插座，用 `<py> main.py --selftest`（不接 adb，直接对桥发一帧并等回复；前置：`config.json` 已建好、AstrBot 在跑、token 对得上）。

**要它 7×24 常驻**：`<py> main.py` 关窗即死。仓库里带了守护脚本 `collector-watchdog.ps1` + `start-collector-bg.bat`（命名互斥防双开；正常崩溃 15 秒后重启，若连续 3 次"秒退"（典型场景：手机没插线）自动退避成 60 秒一轮，免得刷屏）。它们**不写死任何机器路径**：启动时先跑 `tools/resolve-env.ps1`，按「环境变量 `DSH_WX_PYTHON` / `DSH_WX_ADB` → `collector\config.json` 的 `python` / `adb_path` → AstrBot 旁边的嵌入式 `python\python.exe` → PATH」的顺序找解释器和 adb；找不到会报 `python not resolved` 并退出（`run-once.cmd` 退出码 3、watchdog 4）。手机侧还要：充电时不休屏（开发者选项）、屏幕不锁。

## 第 10 步（可选）：flight simulator——不碰手机的排练场

想改人格/换模型/调延迟，不必每条都上真群试。`<py> replay_mentions.py` 会造几个**假群**往插座里灌假消息，收集回复存成 JSON——采集器有个规矩：只把回复打进它的 `home_chat` 那个会话，所以假群的回复永远不会误发到真实群。**先排练，再上台。**

> ⚠️ **排练前必须先放行假群，否则一条回复都收不到。** 回放用的群名是 `示例家庭群（回放B）`（可用环境变量 `REPLAY_GROUP` 改），而第 7 步如果设了 `auto_accept=false`，适配器只认真在 `allowed_chats` 里的会话——假群不在名单里，消息会被**静默丢弃**。两个办法任选：① 把 `示例家庭群（回放B）` 加进 `allowed_chats`；② 排练期间临时把 `auto_accept` 设成 `true`，排完记得改回来。
>
> 前置：AstrBot 在跑、`config.json` 存在、token 对得上（内联 `bridge_token` 或 `bridge_token_file` 二选一都行）。

调延迟实测经验：回复的主要耗时在表达教练的"打字节奏"模拟，且群聊消息一律按"好久不见的冷客"计算，会白等 10–25 秒。在 **wanna_be_human 插件设置**里改这四个值即可：`time.rhythm_delay_cold_min` / `time.rhythm_delay_cold_max`（把 10/25 降到 3/8）、`typing.delay_max` 与 `typing.total_delay_cap`（总封顶从 90 降到 32 秒）。实测群回复从均值 31s 降到 15–28s。

---

## 附录 A：组件位置速查

| 位置 | 文件 | 职责（对照正文比喻） |
|---|---|---|
| PC | `collector/main.py` | 眼睛和手的主循环：认屏→去重→通报→打字 |
| PC | `collector/ocr_channel.py` | "看"的通道——**现行唯一读屏入口**（OCR 认字） |
| PC | `collector/wechat_ui.py`（旧 uiautomator 解析，**已不参与运行**） | 微信 8.0.7+ 后 uiautomator 失效，仅留作历史参考 |
| PC | `collector/gate.py` | 🚦 礼仪老师：限速、静默时段、随机延迟 |
| PC | `collector/adb_client.py` | 数据线两端的操作封装 |
| PC | `collector/requirements.txt` | 依赖清单（第 9 步用） |
| PC | `collector/preflight.py` `collector/dump-ui.py` | 体检（含与 AstrBot 平台配置的只读比对）/ 存样本（dump-ui 会存 XML+截图，截图可作 OCR 校准样本；XML 那路随 uiautomator 一起废了） |
| PC | `collector/bridge_cfg.py` | 读 `config.json` 与门禁卡的**唯一入口**（env → 文件 → 内联），附带只读解析 AstrBot 平台配置；所有一次性工具都走它 |
| PC | `collector/trigger.py` `collector/reply-now.py` `collector/rescue-send.py` | 手动触发 / 应急代答 / 补发救援 |
| PC | `collector/sim_all.py`（当前套件）`collector/sim_scenarios.py` `collector/sim_extreme.py` | 离线演习题（不联网不接手机也能验证逻辑） |
| PC | `start-collector.bat` `start-collector-bg.bat` `collector-watchdog.ps1` | 常驻与守护（**路径无关**，机器相关路径统一由 `tools/resolve-env.ps1` 解析） |
| PC | `tools/resolve-env.ps1` | 唯一的"找 python / 找 adb"入口：环境变量 → `config.json` → 常见布局 → PATH |
| PC | `logs/collector.log` `collector/state.json` | 运行日志 / 游标与去重表（含真实聊天，**永不提交**） |
| AstrBot | `adapter/data-plugins/astrbot_wechat_phone_bridge` | 🔌 翻译插座（WS 服务端 + 事件注册） |

## 附录 B：踩坑速查（都是真机换来的，给未来的你和你的 AI 助手）

| 现象 | 为什么 | 怎么办 |
|---|---|---|
| 用系统工具读微信界面返回空白 | **微信 8.0.7+ 关了"提词器"**（反 uiautomator） | 采集器用 OCR"亲眼看屏幕"（RapidOCR 本地跑，置信度低于 0.6 的行丢弃）——**这也是当前唯一读屏方式，通知/列表通道已废弃** |
| 配置里填了 `watch_chats` 却照样不理人／照样理人 | 那是旧架构字段，**代码不读** | 白名单设在 AstrBot 平台配置：`auto_accept=false` + `allowed_chats`；采集器侧靠 `home_chat` 只守一间 |
| preflight"桥接 token"红灯 | AstrBot 不会自动写 token 文件 | 按第 7 步"门禁卡闭环"：用 `bridge_token` 内联，或自己 `Set-Content` 创建那个文件 |
| preflight 报"token 两侧不一致"／"AstrBot 侧 token 为空" | 一边填了没同步，或 AstrBot 侧留空 | 两边填同一串。注意**留空比填错更危险**：适配器只在 token 非空时校验，留空＝本机任何进程都能当采集器接进来 |
| 6185 能开、名单却拦不住人 | AstrBot 侧 `ws_host` 还是默认 `0.0.0.0`，6199 暴露给整个局域网 | 平台配置改 `ws_host=127.0.0.1`（采集器就在本机）；preflight 会 WARN 提醒 |
| 名单写了但谁都能触发它 | AstrBot 侧 `auto_accept=true`＝来者不拒，`allowed_chats` 直接被跳过 | 设 `auto_accept=false` 再把 `home_chat` 写进 `allowed_chats`；preflight 两项都会 WARN |
| 采集器连上 6199 但 AstrBot 说 `unauthorized`／无 `[wxb] collector connected` | 两边 token 不一致 | 逐字核对；注意别混入空格/换行（`Set-Content` 加 `-NoNewline`） |
| 打字能进框，但按回车不发送 | 微信输入框不认默认回车 | 三级敲门：编辑器动作→回车键→OCR 找到发送按钮直接点；每次敲完看一眼输入框空没空 |
| AI 回复自己，无限套娃 | 分不清气泡是我发的还是别人发的 | 靠位置：贴右缘=自己发的；再记一份"我说过的话"防漏 |
| 同一句话被回两遍 | OCR 断行每次略有不同 | 每句话盖"已处理"图章：只取头尾字符做指纹，断行再抖也认得 |
| 重进一个群后去重全失效 | 群标题上挂着成员数 `(12)`，变一次对不上 | 指纹前先把标题的计数抹掉 |
| 群里 @ 了它没反应 | 微信 @ 显示的是**你给对方设的备注名**，不是你设的群昵称 | 把 @ 里出现的所有写法同时加进 `bot_nicknames` 与 `wake_keywords`（两处都要） |
| 唤醒词有，但一句话都不转 | `wake_keywords` 只在**采集器 config** 那份生效时才转发 | 采集器和 AstrBot 各有一份唤醒词，**两份必须同步** |
| 半夜不回复 / 白天突然静默 | `quiet_hours` 两个数字决定静默窗口 | 想夜间静默就填 `[1, 7.5]`（01:00–07:30）；**两个数字相等＝关闭静默** |
| 手机锁屏后彻底失明 | 采集器只会亮屏，**不会解锁** | 关掉锁屏密码；开发者选项开「充电时不休屏」 |
| 电脑睡一觉链路就断 | 睡眠会掐断 adb 与截图 | 电源计划设成不睡眠（`powercfg` 或设置里改） |
| 国产 ROM 上什么都读不到 | 系统把微信后台杀了 | 电池设置里把微信设为"不优化/允许后台活动" |
| AstrBot 收了消息但回复凭空消失 | **框架基类的 `send()` 只记录不投递**（新手杀手） | 自定义平台必须自己实现事件类，覆写 `send()` 调 `platform.send_by_session`（本项目已实现） |
| 群里 @ 了它不醒（插件侧） | 唤醒判定要消息里带 @ 组件 | 把 @机器人 构造成消息的**第一个组件**（配合 `enable_at`，本项目已实现） |
| 回复又慢又"冷场感" | 表达教练把群客一律按冷客延迟 | cold 档 10/25→3/8、总封顶 90→32s（字段名见第 10 步） |
| 一键启动脚本说 `python not resolved` / 秒退 | 自动解析器没找到解释器 | 设环境变量 `DSH_WX_PYTHON`（和 `DSH_WX_ADB`），或把 `config.json` 的 `python` / `adb_path` 填成绝对路径；脚本本身已不写死路径 |
| `git clone` / 插件市场 / pip 卡死 | GitHub 与 PyPI 在部分网络直连不稳 | clone 加镜像前缀或下 zip；`astrbot plug install ... --proxy`；pip 换国内镜像 |
| 装完 ADBKeyboard 打字仍是英文/乱码 | 输入法没在系统里启用 | 手机设置里手动启用 ADBKeyboard（首次无法自动化），再重启采集器让它 `ime set` |

## 附录 C：安全三问（评估任何微信自动化都先过这三关）

1. **动没动客户端？** 零。官方微信原样跑，AI 只在外面操作手机，不注入、不 hook、不取任何凭据。
2. **说话有没有分寸？** 有。`collector/gate.py` 礼仪老师：单群 ≤4 条/分、全局 ≤20 条/时、日封顶、可配深夜静默、回复前随机酝酿 2–8 秒并按人类手速打字。
3. **谁能跟它说话？** 三层：**`home_chat` 单会话驻留**（采集器只读这一间、只往这一间写，其余会话根本不进视野）＋ **AstrBot 侧 `allowed_chats` 名单**（记得把 `auto_accept` 关掉，否则形同虚设）＋ 出站按名单过滤。不对劲就建 `PAUSE` 文件——电梯急停，全部输出立刻归零；小号是它的身体，也是风险的承担者。

## 已知限制（诚实清单）

- **一台手机一个常驻会话**：采集器守 `home_chat` 那一间；换群＝改配置重启。想同时守多个群需要自己扩展。
- **文字消息 only**：图/语音/视频目前"看了但不转述"；
- **私聊不是独立通道**：把 `home_chat` 设成某私聊标题可以跑私聊，但消息是以"群会话"的身份进管线，**需要含唤醒词或 @ 才回**；
- 微信大改版可能让"认字规则"失效，用 `collector/dump-ui.py` 重新截几张屏存进 `calibration\`，照着截图调 `collector/ocr_channel.py` 的版面规则即可（截图还留着，XML 那路已随 uiautomator 一起废弃）；
- 它看屏幕时手机屏幕被占用（一轮约 0.5–1.5s），别同时玩手机；
- 一条回复 15–60 秒——日记本翻档案 + 教练润色的时间，这是人设不是故障；
- 只支持 USB adb（无线调试未验证）；手机必须无锁屏、常亮、微信不被后台杀；
- 本质仍是用小号模拟真人，平台判定自动化的残余风险**不可归零**：低频起步、白名单收窄、随时急停。

## 附录 D：核心取舍与路线对照

### 核心取舍：大脑只管说话，别的一概不碰

GitHub 上有一类"让 AI 直接操作手机"的项目（如本附录下方的 dsh-phone-control）：每一步都让大模型亲自看屏幕、决定手指点哪里——相当于**让教授亲自去后厨炒每一盘菜**。能做，但每盘菜都花教授的脑子（token），还可能手抖放错盐（点错按钮）。

本项目反过来：**流水线各归各位**——看屏幕、认字、去重、点按、打字，全部交给固定代码（机器人手臂，不收费、不走神、半夜两点也稳定）；大脑只在"该说一句话了"的时刻被叫醒一次。

| | 教授亲自炒菜（模型驱动） | 流水线（本项目） |
|---|---|---|
| 成本 | 每条消息都要模型看屏+决策，token 随消息量线性烧 | 屏幕操作零成本，只为生成回复付一次模型钱 |
| 稳定 | 可能点错、格式漂移 | 行为确定、可离线彩排测试 |
| 说话质量 | 教授想着颠勺就没空想措辞 | 大脑专心当"会聊天的人" |

"说话质量"那一环也不用自己造：AstrBot 已经把身体装好了（接线、值班、记忆抽屉、人格面具插槽、插件市场），**本项目只补了最后一段：把"手机的眼睛和手"接上**。

### 三位"邻居"一表速览

三者都叫"桥"，过的却不是同一条河：

| | dsh-phone-control | dsh-wechat-bridge 系 | 本项目 dsh-wechat-phone |
|---|---|---|---|
| 一句话定位 | 给模型装上手机操作的手眼（通用 MCP 工具） | 把 PC 微信接进 DSH 会话 | 让手机小号的微信和 AI 常驻对聊 |
| 谁在看屏幕、谁在操作 | **模型**每步亲自看屏定坐标 | 程序（读本地库 + UIA 驱动 PC 窗口） | 程序（OCR 看屏 + ADB 操作手机） |
| 模型的位置 | 控制环 + 说话，全包 | 只说话，但每条消息重放完整 agent 上下文 | 只说话，且只为生成的回复调用一次 |
| token 成本 | 最高（看屏也烧） | 中（每消息一次完整回合） | 最低（屏幕操作零 token） |
| 用的谁的身份 | 你本人授权操作自己的手机 | **主号**，朋友以为"你本人在说话" | **小号**，明示机器人人设 |
| 人格/记忆/润色 | 无（看宿主） | 无（DSH 本色） | 性格面具 + 日记本 + 表达教练三件套 |
| 适合 | 没见过的 App 里走一次性流程 | 想让桌面微信替自己回话 | 家庭群 7×24 陪伴，无人值守 |

### 与 [teangtang1122/dsh-phone-control](https://github.com/teangtang1122/dsh-phone-control)

让大模型通过 MCP 工具操作安卓手机的服务。我们从它那里**继承**了三样纪律：观察与行动分离（任何动作后必须重新观察确认——固化成三级发送兜底的"每级截图验证输入区已清空"）；不猜坐标、目标确认后才点击；scrcpy 剪贴板输入留作我们的备选输入法方案。**分歧**在一个根本位置：它把模型放进控制环（每一步看屏幕决定点哪），我们把模型只留在语言位（见本节开头"核心取舍"）。各有所长——没见过的 App 里走一次性流程，选它的模型驱动更通用；天天重复的高频收发，本项目的代码驱动更省更稳。

### 与 [Yuuyuko-uu/dsh-wechat-bridge](https://github.com/Yuuyuko-uu/dsh-wechat-bridge) 系

DSH 生态里存在一批 dsh-wechat-bridge（上游 Yuuyuko-uu，MIT；如 [thawline 的修改版](https://github.com/thawline/dsh-wechat-bridge)及若干镜像；另有走官方 ClawBot/iLink 私聊通道的 `dsh-wx-bridge` 系）——和我们一样是把**个人微信**接进 AI，但"邻居"的解剖结构完全不同：

| | dsh-wechat-bridge 系 | 本项目（dsh-wechat-phone） |
|---|---|---|
| 用谁的微信 | **同一台 PC 上的微信 4.x 大号** | 手机上的**小号**（专用设备，和大号物理隔离） |
| 收消息 | 只读微信落盘的本地 SQLite 数据库 | OCR"亲眼看屏幕" + 会话列表轮询 diff，**不碰微信任何数据文件** |
| 发消息 | UIA + 剪贴板操纵 PC 微信窗口（会抢焦点） | ADB 操作手机（三级发送兜底） |
| 谁在说话 | 朋友收到的＝"**你本人**在说话"——AI 借用你的真人身份 | 小号 + 明示的机器人人设，**身份诚实** |
| 大脑 | 消息进 DSH 会话，每轮重放完整 agent 上下文（外人权限靠 tools.guard 硬闸拦截） | AstrBot 聊天管线 + 单次 completion，屏幕操作零 token |
| 人格/记忆/润色 | 无（DSH 本色出演） | 面具 + 日记本 + 表达教练三件套，正是本项目主菜 |
| 版本脆弱点 | 微信客户端一改本地库加密方案即失效 | 微信改版要重新校准界面识别（附样本工具） |

一句话各自定位：**他们替你省下"操作微信"的手，我们替你省下"账号和名声"的险**。两条路的痛点不在同一层——前者站在"读本地库 + 大号身份"的灰色区域上，后者站在"小号模拟真人"的行为风险上。选型前想清楚哪份风险你愿意扛；两边共用一个物理前提：都得多一台设备或一个专用环境，都劝你别拿主力号冒险。

**从这位邻居身上学到的（已列入待办）**：① 系统会话默认屏蔽名单（微信运动/微信团队/微信支付/订阅号消息/折叠的群聊，开箱即不进管线）；② **DRYRUN 彩排模式**——比 PAUSE 温和一档：照常记录"该发什么"，就是不打字上屏；③ **图片视觉描述**——看到 `[图片]` 气泡时截那块区域，交给视觉模型转述成一句话再进管线，别只"看图不转述"；④ **按天分群的聊天日记** markdown（没点名也全量留档，可审计可回溯）；⑤ **配置热加载**（改完 30 秒自动生效，不重启服务）。

## License / 致谢

- 🦴 身体：[AstrBot](https://github.com/AstrBotDevs/AstrBot)——平台接线、值班管线、模型水电、面具插槽、档案柜、插件市场全是现成的，本项目只接了"手机的眼睛和手"这一段。
- 👀 设计参考：[teangtang1122/dsh-phone-control](https://github.com/teangtang1122/dsh-phone-control)（观察-行动分离等思想从这里继承；路线对照见附录 D）。
- 👯 同生态的邻居：[Yuuyuko-uu/dsh-wechat-bridge](https://github.com/Yuuyuko-uu/dsh-wechat-bridge)（MIT）及其修改版们——PC 微信读本地库 + UIA 发送的另一条路线，对照见附录 D。
- ⌨️ 输入法：[senzhk/ADBKeyBoard](https://github.com/senzhk/ADBKeyBoard)（APK 请从上游自取，本仓库不打包）。
- 许可：[MIT](LICENSE)，全文见根目录 `LICENSE` 文件。按 MIT 的 "AS IS" 条款，本项目不承担任何使用后果——请遵守仓库顶部的使用红线。
- 永不提交：`collector/config.json`（真实群名/白名单/token）、`logs/`、`collector/state.json`（游标与去重表，含真实聊天）、`calibration/`（真实聊天截图）、`collector/replay_result*.json`、门禁卡 token、第三方 APK（`assets/*.apk`）——`.gitignore` 已固化，提 PR 前请自查 diff。
