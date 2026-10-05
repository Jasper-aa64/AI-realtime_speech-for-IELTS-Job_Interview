# Qt 桌面端：IELTS Studio + 模拟面试（设计 + 分阶段计划）

> 状态：草案，等用户确认「待确认决定」后再动手。
> 日期：2026-10-05 ・ 分支基线：`ui-polish`（网页 UI 统一设计语言已完成）

## 1. 目标

1. 软件回到 **Qt 桌面端**：本地进程直接采集/播放音频，做到真正的实时语音（全双工、可打断、低延迟）。网页版保留，作为「削弱版」（浏览器音频链路，延迟更高、无打断）。
2. 左上角品牌位变成 **模式切换器**：`IELTS Studio` ↔ `模拟面试`。动效参照 detail.design 左上角：点击品牌，按钮原地「长大」成一张浮层卡片（共享元素形变 + 弹簧曲线），卡片里列出两个选项；选中后卡片收回成品牌位，文字切换。
3. **模拟面试** 基本是雅思口语的改编版：同样的「出题 → 实时作答 → 追问 → 报告」流程，题目来源换成简历 / 岗位，报告维度换成面试维度。仓库里已有面试相关的 C++ 骨架（`interview_manager`、`dialog_session`、`realtime_client`、`audio_manager`、旧 `mainwindow`）。

非目标（这一期不做）：移动端；重写所有页面为原生控件；多用户同步；自动更新。

## 2. 现状（已核对）

- **网页端**：Django（`backend_django`，SQLite，Channels WebSocket `apps/speaking/consumers.py`）+ 原生 JS SPA（`web/static`，`app.js` 1.7 万行，`styles.css` 4.5 万行）。新设计语言已统一。浏览器实时语音走 `realtime-pcm-uplink.js` → Django WebSocket → 火山引擎 ASR。
- **C++ 端**（约 6.4k 行）：
  - `services/realtime_client` — 火山引擎实时对话 WebSocket（Connect / SendAudioData / SendTextQuery / ResponseCallback）。
  - `services/audio_manager` + `ielts/audio_core`（PortAudio 采集，VAD）+ `ielts/realtime_speech_capture`。
  - `interview/interview_manager`（简历 PDF → 题目，追问判定）、`interview/dialog_session`、`services/llm_client`、`services/pdf_parser`（podofo）。
  - `ielts/part1/2/3_session`、`scorer`、`question_bank`（CLI 版雅思）。
  - `ui/mainwindow` + `ui/config_dialog`：旧的 Qt Widgets 面试窗口（文本区 + 进度条，样式简陋）。
  - CMake 已有 `CppInterviewSystemQt` 目标（Qt6/Qt5 Widgets，依赖从 vcpkg 取）。
- **本机环境**：`~/Qt` 只有 Qt Creator / Design Studio，**没有 Qt 6 开发套件**（无 `qmake`/`qt-cmake`，无 QtWebEngine）。需要先装。

## 3. 待确认决定（compact 后先问这些，一次一个）

| # | 问题 | 我的推荐 |
|---|------|----------|
| D1 | 桌面端 UI 怎么做？ | **A：Qt 外壳 + QtWebEngine 承载现有网页 UI，音频走原生 C++**（见 §4）。 |
| D2 | 桌面端的后端在哪？ | **随软件启动本地 Django 子进程**（数据放用户目录），设置里可改成连远端服务器。 |
| D3 | 网页版要不要也有「模拟面试」？ | 切换器两端都有；网页版的面试走浏览器音频（削弱版），入口标注「桌面端体验更好」。 |
| D4 | 面试题从哪来？ | 简历 PDF + 目标岗位描述 → LLM 生成题目（复用 `interview_manager` 的思路），外加通用行为面试题库。 |
| D5 | Qt 装哪个？ | Qt 6.8 LTS（官方安装器勾 WebEngine + Multimedia + WebChannel），或 `brew install qt`。需要你本人操作安装器/登录。 |

## 4. 方案对比（D1）

**A. Qt 外壳 + QtWebEngine + 原生音频桥（推荐）**
- 桌面窗口是 `QMainWindow`，中间一个 `QWebEngineView` 加载本地 Django 提供的 SPA。
- 实时语音不用浏览器的 `getUserMedia`：C++ 用 PortAudio 采集 → VAD → `RealtimeClient` 直连火山引擎；识别文本 / AI 语音 / 状态通过 **QWebChannel** 推给页面，页面通过同一通道下指令（开始、停止、打断）。
- 优点：刚统一好的设计语言、报告、语料库、写作全部直接复用；只需新增一个「音频桥」和桌面专属能力。工作量可控（几周量级）。
- 缺点：包体大（WebEngine ≈ 150MB+）；两套运行时（Python + Chromium）。

**B. Qt Quick（QML）原生重写全部页面**
- 体验最原生，动效（弹簧、形变）在 QML 里很顺手。
- 缺点：所有页面（练习、报告、语料库、写作、拼写…）要重写，等于再做一遍前端，数月量级；设计语言要在 QML 里重新实现一遍，两端会再次分叉。

**C. 继续扩写旧 Qt Widgets 窗口**
- 只做面试；IELTS 部分仍在网页。体验割裂，Widgets 难做出现在的设计语言和动效。不推荐。

结论：选 A。以后如果某个页面需要更原生（例如面试实时对话页），可以单独用 QML 嵌入，不影响其他页面。

## 5. 架构（方案 A）

```
┌──────────────── IELTSStudio.app (Qt 6) ────────────────┐
│ MainWindow                                              │
│  └─ QWebEngineView ──loads──▶ http://127.0.0.1:<port>/   │
│        ▲  QWebChannel "native"                          │
│        │   - capabilities() → {realtimeAudio, bargeIn}  │
│        │   - startSession(mode, opts) / stop / interrupt│
│        │   - signals: partial(text), final(text),       │
│        │     aiSpeaking(bool), level(rms), error(msg)   │
│  NativeAudioBridge (QObject)                            │
│   ├─ AudioEngine   (PortAudio 采集/播放, VAD, 回声抑制) │
│   ├─ RealtimeClient(火山引擎实时对话 WebSocket)         │
│   └─ SessionDriver (IELTS / 面试两种会话脚本)           │
│  BackendProcess (QProcess: 启动/守护本地 Django)        │
└─────────────────────────────────────────────────────────┘
```

- **页面侧检测**：`window.qt && qt.webChannelTransport` 存在 → 桌面模式，`app.js` 的录音入口改走 `native` 通道；否则保持现有浏览器链路。这层封装在一个新的 `web/static/native-bridge.js`，`app.js` 只改调用点。
- **数据**：会话结束后，桌面端把转写 / 音频文件 / 时间戳交给现有 Django 接口生成报告（与网页端同一套报告与存储），不另造一套。
- **配置与密钥**：沿用 `.env`；桌面端首次启动在用户目录生成配置，不把密钥打进包。

## 6. 模式切换器（两端共用，做在网页层）

- 位置：左上角品牌位（logo + 「IELTS Studio」）。
- 交互：点击 → 品牌按钮作为共享元素，宽高、圆角、背景用弹簧曲线形变成一张约 260px 的浮层卡；卡内两行：`IELTS Studio`（雅思口语与写作）/`模拟面试`（简历 · 岗位 · 实时追问），当前项带对勾；`Esc`、点外部收回；键盘 ↑↓ 选择、回车确认。
- 动效细节实现前用浏览器再去 detail.design 左上角逐帧看一次（时长、曲线、内容淡入顺序），按观察结果定参数；`prefers-reduced-motion` 时退化为淡入淡出。
- 切换结果：`body` 加 `mode-ielts` / `mode-interview`，侧栏菜单换成对应模式的入口；当前模式记在 localStorage（桌面端同步存到配置）。
- 面试模式侧栏（初稿）：首页 / 面试（新建 · 继续）/ 面试报告 / 简历与岗位 / 题库。

## 7. 模拟面试（雅思口语改编）

| 雅思口语 | 模拟面试 |
|----------|----------|
| P1 短问短答 | 开场与自我介绍、基础问题 |
| P2 题卡 1 分钟准备 + 2 分钟陈述 | 项目深挖：选一段经历，准备后完整陈述 |
| P3 深入讨论 + 追问压力 | 追问压力：针对回答连续追问（技术 / 行为） |
| 评分 FC/LR/GRA/P | 维度：表达清晰度、结构（STAR）、技术深度、岗位匹配 |
| 语料库 | 「我的故事库」：可复用的项目故事与回答 |

- 题目来源：简历 PDF（`pdf_parser`）+ 岗位描述 → LLM 出题；追问由实时对话模型驱动（`dialog_session` 的现有逻辑迁到 `SessionDriver`）。
- 报告：沿用口语报告的版式（统一设计语言），换维度与文案。

## 8. 错误处理

- 本地 Django 启动失败 / 端口被占：外壳显示原生错误页，提供「重试」「打开日志」。
- 麦克风权限被拒（macOS TCC）：桥返回 `error('mic-permission')`，页面引导去系统设置；`Info.plist` 带 `NSMicrophoneUsageDescription`。
- 实时连接断开：自动重连一次，失败则降级为「录完再转写」，页面提示。
- WebEngine 崩溃：外壳捕获 `renderProcessTerminated` 后重载页面，会话状态在 C++ 侧保留。

## 9. 测试

- C++：现有 `tests/*.cpp`（audio_core、config…）继续跑；新增 `NativeAudioBridge` 的信号/槽单测（用假音频源 + 假 RealtimeClient）。
- 网页：`node --test tests/*.test.js` 继续通过；新增 `native-bridge.js` 的单测（模拟 `qt.webChannelTransport`）。
- 后端：`manage.py test` 继续通过；面试报告接口加测试。
- 手动验收：桌面端完整走一遍 IELTS P1 实时练习 + 一场模拟面试；网页端回归。

## 10. 分阶段计划（每阶段可单独验收）

**阶段 0 — 环境（需要你操作）**
1. 安装 Qt 6.8 LTS（含 WebEngine、WebChannel、Multimedia）或 `brew install qt`。
2. 我验证 CMake 能找到 Qt6::WebEngineWidgets，旧目标 `CppInterviewSystemQt` 仍能编过。

**阶段 1 — 桌面外壳（能打开现有网页）**
1. 新目标 `IELTSStudioDesktop`：`MainWindow` + `QWebEngineView` + `BackendProcess`（启动本地 Django，等端口就绪后加载）。
2. 窗口标题栏 / 菜单 / 退出时关闭子进程；`Info.plist` 麦克风说明。
3. 验收：双击 app 打开，看到当前统一设计的首页，所有页面可用（音频暂走浏览器链路）。

**阶段 2 — 原生音频桥（真正实时）**
1. `NativeAudioBridge` + `QWebChannel` 注册；`native-bridge.js` 封装能力检测与调用。
2. `AudioEngine`：复用 `audio_core`（VAD）与 PortAudio；播放 AI 语音；支持打断（AI 说话时检测到用户开口即停播）。
3. 把 P1/P2/P3 练习的录音入口切到桥上（桌面模式），结束后照常调用 Django 生成报告。
4. 验收：桌面端 P1 实时练习延迟明显低于网页端，可打断；报告正常生成。

**阶段 3 — 模式切换器**
1. 先逐帧观察 detail.design 左上角动效，记录参数。
2. 实现切换浮层（网页层，两端共用）+ `mode-*` 状态 + 侧栏按模式切换。
3. 验收：动效顺滑（60fps），键盘可用，刷新后保持模式，深浅色都正常。

**阶段 4 — 模拟面试**
1. 后端：面试会话 / 报告的数据模型与接口（尽量复用口语报告的生命周期）。
2. 前端：面试首页、简历与岗位上传、面试进行页（复用练习页布局）、面试报告页（复用报告版式）。
3. 桌面端：`SessionDriver` 的面试脚本（开场 → 项目深挖 → 追问压力），实时对话由 `RealtimeClient` 驱动。
4. 验收：用一份测试简历完整走一场面试并出报告。

**阶段 5 — 打包**
1. `macdeployqt` 打包，内置 Python 运行时（或要求本机 Python，二选一，阶段 1 时定）。
2. 签名 / 公证（如需分发）。

## 11. 风险

- QtWebEngine 在 macOS 上的麦克风权限与沙箱：原生采集绕开了网页权限，但 app 本身仍需 TCC 授权。
- 内置 Python + Django 增大包体与启动时间；可在阶段 5 评估改成「连远端服务」的轻量包。
- 火山引擎实时对话的回声消除：外放时需要 AEC，否则会自我打断；先用耳机验收，AEC 作为后续项。
