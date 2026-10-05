# Qt 桌面端：IELTS Studio + 模拟面试（设计 + 分阶段计划）

> 状态：阶段 0–1 已完成验收；外观三档已实现。阶段 2 已完成审计/建议计划，语音代码和最终组件选择尚未实施/批准。
> 更新：用户要保留 C++ 性能作品；VPS 推迟到本地效果验证。本次研究建议以 relay 替换历史 D2′ 的长期密钥下发退路；尚待阶段 2 方案审阅。
> 日期：2026-10-05 ・ 分支基线：`ui-polish`（网页 UI 统一设计语言已完成）

## 1. 目标

1. 软件回到 **Qt 桌面端**：本地进程直接采集/播放音频，做到真正的实时语音（全双工、可打断、低延迟）。网页版保留现有浏览器链路。原生路径的延迟/打断效果须同条件实测，不能预先保证快于网页。
2. 左上角品牌位变成 **模式切换器**：`IELTS Studio` ↔ `模拟面试`。动效参照 detail.design 左上角：点击品牌，按钮原地「长大」成一张浮层卡片（共享元素形变 + 弹簧曲线），卡片里列出两个选项；选中后卡片收回成品牌位，文字切换。
3. **模拟面试** 基本是雅思口语的改编版：同样的「出题 → 实时作答 → 追问 → 报告」流程，题目来源换成简历 / 岗位，报告维度换成面试维度。仓库里已有面试相关的 C++ 骨架（`interview_manager`、`dialog_session`、`realtime_client`、`audio_manager`、旧 `mainwindow`）。

非目标（这一期不做）：移动端；重写所有页面为原生控件；离线使用；自动更新；网页版的模拟面试。

## 2. 现状（已核对）

- **网页端**：Django（`backend_django`，SQLite，Channels WebSocket `apps/speaking/consumers.py`）+ 原生 JS SPA（`web/static`，`app.js` 1.7 万行，`styles.css` 4.5 万行）。新设计语言已统一。浏览器实时语音有 `realtime_pcm` 参数启用的实验路径：`realtime-pcm-uplink.js` → Django WebSocket → 火山引擎 ASR；正常未启用时不自动走它。
- **C++ 端**（约 6.4k 行）：
  - `services/realtime_client` — 火山引擎实时对话 WebSocket（Connect / SendAudioData / SendTextQuery / ResponseCallback）。
  - `services/audio_manager` + `ielts/audio_core`（PortAudio 采集，VAD）+ `ielts/realtime_speech_capture`。
  - `interview/interview_manager`（简历 PDF → 题目，追问判定）、`interview/dialog_session`、`services/llm_client`、`services/pdf_parser`（podofo）。
  - `ielts/part1/2/3_session`、`scorer`、`question_bank`（CLI 版雅思）。
  - `ui/mainwindow` + `ui/config_dialog`：旧的 Qt Widgets 面试窗口（文本区 + 进度条，样式简陋）。
  - CMake 已有 `CppInterviewSystemQt` 目标（Qt6/Qt5 Widgets，依赖从 vcpkg 取）。
- **当前桌面端**：`desktop/` 的独立 Qt 6 工程已验收，Qt 6.11.2 已安装；它仍未链接上述原生语音源文件或 voice bridge。
- **外观**：网页/桌面共享浅色、深色、跟随系统三档；新偏好优先，旧 `ielts-dark-mode=1/0` 保留手动选择，只有 system 跟随系统实时变化。
- **审计结论**：旧语音是 200 ms 阻塞采集的半双工原型，有并发 socket 写、关闭/线程生命周期缺陷；协议/构造测试不能证明端到端落地。详见阶段 2 计划与两份研究。

## 3. 已确认决定与本次建议（2026-10-05）

| # | 问题 | 结论 |
|---|------|------|
| D1 | 桌面端 UI 怎么做？ | **Qt 外壳 + QtWebEngine 承载现有网页 UI，实时音频走原生 C++**（见 §4）。 |
| D2 | 后端在哪？ | **云服务器（VPS）**。桌面端是客户端，加载服务器上的 SPA、调用服务器接口；服务器地址可配置，开发期连本机 `127.0.0.1:8767`。不内置 Python / Django。**用户决定先做完看效果，购买/部署 VPS 延后**。 |
| D2′ | 实时语音怎么连火山引擎？ | **本次审计建议替换历史长期密钥下发退路，尚待阶段 2 方案审阅**。所查官方旧端点有控制台 Access Token，但尚未确认短期/限定范围签发契约。当前建议认证、有界流式 relay，密钥留服务器；若供应商证实临时凭证再评估直连。此更新是研究建议，未实现。 |
| D3 | 网页版有没有「模拟面试」？ | **只有桌面端有**。网页版左上角保持静态品牌位，不出切换器、不出面试入口。 |
| D4 | 面试题从哪来？ | **两种入口**：日常练习用通用面试题库；另有「定制面试」，上传简历 PDF + 岗位描述，由 LLM 生成题目。 |
| D5 | Qt 怎么装？ | Qt 6.11.2 已装；UI 使用 Qt/WebEngine，语音保持独立 C++。callback 组件以 PortAudio vs Qt 6.11 同设备实验决定，不因减少依赖直接重写。 |
| D6 | 系统外观？ | 用户已批准并实现浅色 / 深色 / 跟随系统；保留旧手动偏好。 |
| D7 | 面试后端？ | 建议同一 Django 服务内独立 `apps.interview`；共享 AI/媒体基础设施和报告版式，保持面试 schema。尚未实施。 |

## 4. 方案对比（D1）

**A. Qt 外壳 + QtWebEngine + 原生音频桥（推荐）**
- 桌面窗口是 `QMainWindow`，中间一个 `QWebEngineView` 加载服务器提供的 SPA。
- 实时语音不用浏览器的 `getUserMedia`：独立 C++ 引擎用待实测决定的 callback 后端采集 → DSP/分帧 → 单 owner 的传输 adapter（当前建议经 relay）；AI 音频在原生侧播放，只有识别文本 / AI 播放状态 / 控制状态通过 **QWebChannel** 推给页面，页面通过同一通道下指令（开始、停止、打断）。
- 优点：刚统一好的设计语言、报告、语料库、写作全部直接复用；页面只增加控制适配和桌面能力；实时引擎须补齐取消、缓冲、设备/协议契约和实测，不能将旧原型当成即插即用组件。
- 缺点：包体大（WebEngine ≈ 150MB+）。

**B. Qt Quick（QML）原生重写全部页面**
- 体验最原生，动效（弹簧、形变）在 QML 里很顺手。
- 缺点：所有页面（练习、报告、语料库、写作、拼写…）要重写，等于再做一遍前端，数月量级；设计语言要在 QML 里重新实现一遍，两端会再次分叉。

**C. 继续扩写旧 Qt Widgets 窗口**
- 只做面试；IELTS 部分仍在网页。体验割裂，Widgets 难做出现在的设计语言和动效。不推荐。

结论：选 A。以后如果某个页面需要更原生（例如面试实时对话页），可以单独用 QML 嵌入，不影响其他页面。

## 5. 架构（方案 A + 云服务器）

```text
IELTSStudio.app (Qt 6)
  QWebEngineView ── HTTPS ── Django（账号 / IELTS / interview / AI worker）
       │ QWebChannel：控制、转写、状态；不传原始 PCM
  NativeAudioBridge（Qt adapter）
       │ commands / events
  独立 C++ voice engine
    device callback → bounded capture ring → DSP / packetizer
    单 transport owner → 认证、有界流式 relay → provider adapter
    decoder / playout owner → bounded playback ring → device callback
    session owner：state / cancel / turn epoch / metrics
```

这是阶段 2 的建议结构，尚未实现。详见 [性能实验与实施切片](../plans/2026-10-05-native-voice-performance.md)。

- **页面侧检测**：`window.qt && qt.webChannelTransport` → 原生控制桥/桌面能力，接口封装在未来 `native-bridge.js`。网页保持既有链路，不显示面试切换器。只有能力验证成功才启用原生录音入口。
- **设备层**：PortAudio callback 和 Qt 6.11 callback 是公平对照候选，Qt 同样是 C++。device callback 不阻塞/分配/等待锁/做网络或日志；各 ring 固定唯一 producer/consumer。单 transport owner 串行 write/close，owned worker 可取消并有界退出，打断通过 epoch 丢旧回复/音频。
- **鉴权**：现阶段建议 relay 验证登录、user/session/turn 归属、时长/费用/字节/并发预算，服务器 key 留服务器。短期应用 ticket 仅授权 relay；没有供应商签发/过期证据就不定义假的 provider expires_at。当前 PCM consumer 的队列/重启/授权需先硬化。
- **直连分支**：供应商若提供可验证的临时、限定权限凭证契约再评估。[新原生全双工 API](https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh) 的 `/api/v3/duplex/realtime/dialogue`、`X-Api-Key`、严格 20 ms pacing 作为独立 provider adapter 调查；不能替换旧 URL 却沿用旧 header/事件格式。
- **登录态**：profile 持久化继续保留。relay/native 登录传递方式在切片中明确，采用能验证 session/turn 归属的实现，不把 key 传到页面。退出按既有窗口→排空事件→profile 顺序。
- **数据/报告**：IELTS 使用现有录音/转写/报告契约；面试独立模型/schema，共享基础设施和版式。评分/报告工作不放音频线程。
- **测量**：10 ms device/DSP 处理块是实验配置，现有 provider 建议 20 ms 上行包。单调时间记录 capture→DSP→send→ASR→可观测的 LLM 首 token→TTS 首包→声输出；P50/P95/P99、CPU/内存、队列年龄和丢音，同时测打断后硬件残余。端到端 provider 未公开的 token/内部阶段标不可观测；云端与网络单列。

## 6. 模式切换器（只在桌面端出现，代码做在网页层）

- 位置：左上角品牌位（logo + 「IELTS Studio」）。网页版（无原生桥）保持现在的静态品牌位。
- 交互：点击 → 品牌按钮作为共享元素，宽高、圆角、背景用弹簧曲线形变成一张约 260px 的浮层卡；卡内两行：`IELTS Studio`（雅思口语与写作）/`模拟面试`（题库练习 · 定制面试 · 实时追问），当前项带对勾；`Esc`、点外部收回；键盘 ↑↓ 选择、回车确认。
- 动效细节实现前用浏览器再去 detail.design 左上角逐帧看一次（时长、曲线、内容淡入顺序），按观察结果定参数；`prefers-reduced-motion` 时退化为淡入淡出。
- 切换结果：`body` 加 `mode-ielts` / `mode-interview`，侧栏菜单换成对应模式的入口；当前模式记在 localStorage。
- 面试模式侧栏（初稿）：首页 / 题库练习 / 定制面试（简历 + 岗位）/ 面试报告 / 我的故事库。

## 7. 模拟面试（雅思口语改编）

| 雅思口语 | 模拟面试 |
|----------|----------|
| P1 短问短答 | 开场与自我介绍、基础问题 |
| P2 题卡 1 分钟准备 + 2 分钟陈述 | 项目深挖：选一段经历，准备后完整陈述 |
| P3 深入讨论 + 追问压力 | 追问压力：针对回答连续追问（技术 / 行为） |
| 评分 FC/LR/GRA/P | 维度：表达清晰度、结构（STAR）、技术深度、岗位匹配 |
| 语料库 | 「我的故事库」：可复用的项目故事与回答 |

- **题库练习**（日常）：服务器上的通用面试题库（行为题 + 常见技术题，按类别分组），首批题目由我起草、你审，之后可在页面里增删。
- **定制面试**：上传简历 PDF + 粘贴岗位描述 → 服务器端解析 PDF、走现有 `apps/ai` 的 LLM 路由出题（`interview_manager` 的出题思路移植到 Python，密钥留在服务器）。
- 追问：session owner 负责题源、rubric、脚本和回合 epoch；评估供应商原生全双工与现有 ASR/LLM/TTS 两条路径，避免重复生成。旧 `dialog_session` 只借思路，不原样移植其阻塞/半双工流程。
- 后端建议同一 Django 服务新建 `apps.interview`，独立 Session/Turn/Report、resume/JD、question provenance 和技术评分；共享 `apps.ai` provider/AITask/计费及适合抽取的媒体接口。IELTS Band 7/FC/LR/GRA/P 不当成技术评分模型。
- 报告：沿用口语报告的版式（统一设计语言），换维度与文案。

## 8. 错误处理

- 服务器连不上（断网 / 服务器宕机）：外壳显示原生错误页，提供「重试」和「更改服务器地址」。
- relay 授权失败（未登录 / 超预算 / 未配置 provider）：桥返回明确鉴权错误，页面提示登录/重试；不得启用桌面已知会崩的 Web Speech API。录音后转写降级需显式提示并保留音频。
- 麦克风权限被拒（macOS TCC）：桥返回 `error('mic-permission')`，页面引导去系统设置；`Info.plist` 带 `NSMicrophoneUsageDescription`。
- 实时连接断开：结束旧 epoch 并有界回收；只在 session 契约允许且有明确重试次数时恢复，不自动重播旧音频。失败可显式降级为录完再转写。
- WebEngine 崩溃：现有外壳会重载；未来桥需明确 session 暂停/终止与重新绑定，不假定 UI 重载等于语音取消。

## 9. 测试

- C++：现有 `tests/*.cpp`（audio_core、config…）继续跑；新增 `NativeAudioBridge` 的信号/槽单测（用假音频源 + 假 RealtimeClient）。
- 网页：`node --test tests/*.test.js` 继续通过；新增 `native-bridge.js` 的单测（模拟 `qt.webChannelTransport`）。
- 后端：现有 Django 检查保持通过；relay 登录/归属/预算/背压/重启/过期与面试独立 schema 加契约测试。
- 性能：假设备/传输验证 owned lifecycle、epoch/backpressure，sanitizer 验证 race/lifetime；真实有线设备 + 同 provider 条件测尾分位数/声输出。旧构造/协议单测不足以代表全双工和工业水准。
- 手动验收：桌面端完整走一遍 IELTS P1 实时练习 + 一场模拟面试；网页端回归。

## 10. 分阶段计划（每阶段可单独验收）

**阶段 0 — 环境**
1. `brew install qt`（我来跑）。
2. 桌面端是独立 CMake 工程 `desktop/`（只依赖 Qt，不依赖 vcpkg），验证它能找到 `Qt6::WebEngineWidgets` 并跑通单测；根目录旧目标不动。

**阶段 1 — 桌面外壳（能打开现有网页）**
1. 新目标 `IELTSStudioDesktop`：`MainWindow` + `QWebEngineView`（持久化 profile）+ 设置里的服务器地址（开发期默认 `http://127.0.0.1:8767`）。
2. 菜单 / 连不上时的原生错误页；`Info.plist` 麦克风说明。
3. 验收：双击 app 打开，看到当前统一设计的首页，能登录，所有页面可用（音频暂走浏览器链路）。

**阶段 2 — 原生 C++ 实时语音（建议计划，未实施）**
1. 执行 [性能计划](../plans/2026-10-05-native-voice-performance.md) 的 2A baseline/协议调查和 2B PortAudio vs Qt 6.11 callback 同设备实验，审阅最终组件。
2. 2C 实现单 I/O owner 的 provider adapter 与认证有界 relay；核实供应商临时凭证，并独立调查新原生全双工端点。
3. 2D 持续采集/流式播放与 epoch 取消，先耳机验收实际 cancel-to-silence；不能将 VAD 当 AEC。
4. 2E 用 Qt/QWebChannel 控制 adapter 接 P1，转写/录音/报告契约保持；外放 AEC/长稳为 2F。
5. 验收：同条件基线、P50/P95/P99、CPU/内存/underrun、快开关/背压/设备变更/鉴权过期和报告完整；未测不宣称比网页快或工业领先。

**阶段 3 — 模式切换器（仅桌面端）**
1. 先逐帧观察 detail.design 左上角动效，记录参数。
2. 实现切换浮层（网页层，仅在检测到原生桥时渲染）+ `mode-*` 状态 + 侧栏按模式切换。
3. 验收：动效顺滑（60fps），键盘可用，刷新后保持模式，深浅色都正常；浏览器打开时看不到切换器。

**阶段 4 — 模拟面试**
1. 后端：面试题库、定制面试（PDF 解析 + LLM 出题）、独立 `apps.interview` 会话 / 报告模型与接口（共享 AI task/media/report layout，保持面试 schema）。
2. 前端：面试首页、题库练习、简历与岗位上传、面试进行页（复用练习页布局）、面试报告页（复用报告版式）。
3. 桌面端：`SessionDriver` 的面试脚本（开场 → 项目深挖 → 追问压力）。
4. 验收：题库练习和一份测试简历的定制面试各完整走一场并出报告。

**阶段 5 — 云服务器部署（用户决定本地效果验证之后再购买/部署）**
1. Linux + Daphne + Nginx + HTTPS（域名 + 证书）；AI worker 用 systemd 常驻。
2. 迁移数据：从办公室 Windows 机拷最新 `db.sqlite3` 与 `media/`；先沿用 SQLite，有并发问题再换 PostgreSQL。
3. 桌面端默认服务器地址改为生产域名。
4. 验收：网页版和桌面端都连 VPS 正常使用；Windows 机可下线。

**阶段 6 — 打包**
1. `macdeployqt` 打包（不含 Python，只有 Qt + WebEngine）。
2. 签名 / 公证（如需分发给别人）。

## 11. 风险

- 所查实时端点未确认公开临时受限凭证契约；本次建议以 relay 替换长期 key 下发，尚待阶段 2 方案审阅。不是已证实不支持，需向供应商核实准确服务/签发/范围/续期。
- 国内 VPS 的域名需要备案（数周）；备案期间可先用 IP + 自签证书或海外 VPS 过渡。
- relay 在实时媒体链路中增加网络/排队段，必须单独测量；未来选服务器位置。若验证 ephemeral 直连再做同条件比较，不能先假定哪条更快。
- QtWebEngine 在 macOS 上的麦克风权限：原生采集绕开了网页权限，但 app 本身仍需 TCC 授权。
- 回声消除：外放时需要 AEC，否则会自我打断；先用耳机验收，AEC 作为后续项。
- `brew` 的 Qt 会随 `brew upgrade` 滚动升级；打包分发前固定版本（`brew pin qt`）。
