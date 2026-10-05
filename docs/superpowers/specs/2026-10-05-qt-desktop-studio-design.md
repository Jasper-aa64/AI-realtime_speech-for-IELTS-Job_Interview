# Qt 桌面端：IELTS Studio + 模拟面试（设计 + 分阶段计划）

> 状态：决定已确认（§3），等用户审阅本文后写实施计划。
> 日期：2026-10-05 ・ 分支基线：`ui-polish`（网页 UI 统一设计语言已完成）

## 1. 目标

1. 软件回到 **Qt 桌面端**：本地进程直接采集/播放音频，做到真正的实时语音（全双工、可打断、低延迟）。网页版保留，作为「削弱版」（浏览器音频链路，延迟更高、无打断）。
2. 左上角品牌位变成 **模式切换器**：`IELTS Studio` ↔ `模拟面试`。动效参照 detail.design 左上角：点击品牌，按钮原地「长大」成一张浮层卡片（共享元素形变 + 弹簧曲线），卡片里列出两个选项；选中后卡片收回成品牌位，文字切换。
3. **模拟面试** 基本是雅思口语的改编版：同样的「出题 → 实时作答 → 追问 → 报告」流程，题目来源换成简历 / 岗位，报告维度换成面试维度。仓库里已有面试相关的 C++ 骨架（`interview_manager`、`dialog_session`、`realtime_client`、`audio_manager`、旧 `mainwindow`）。

非目标（这一期不做）：移动端；重写所有页面为原生控件；离线使用；自动更新；网页版的模拟面试。

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

## 3. 已确认决定（2026-10-05）

| # | 问题 | 结论 |
|---|------|------|
| D1 | 桌面端 UI 怎么做？ | **Qt 外壳 + QtWebEngine 承载现有网页 UI，实时音频走原生 C++**（见 §4）。 |
| D2 | 后端在哪？ | **云服务器（VPS）**。桌面端是客户端，加载服务器上的 SPA、调用服务器接口；服务器地址可配置，开发期连本机 `127.0.0.1:8767`。不内置 Python / Django。 |
| D2′ | 实时语音怎么连火山引擎？ | **客户端直连火山引擎，凭证由服务器下发**：登录后向服务器申请会话凭证，只放内存，不写进安装包和磁盘。火山若不支持临时凭证，退到「只对登录用户下发长期密钥」（自己和少数熟人用可接受）。 |
| D3 | 网页版有没有「模拟面试」？ | **只有桌面端有**。网页版左上角保持静态品牌位，不出切换器、不出面试入口。 |
| D4 | 面试题从哪来？ | **两种入口**：日常练习用通用面试题库；另有「定制面试」，上传简历 PDF + 岗位描述，由 LLM 生成题目。 |
| D5 | Qt 怎么装？ | **`brew install qt`**（Qt 6，自带 WebEngine / WebChannel / Multimedia）。 |

## 4. 方案对比（D1）

**A. Qt 外壳 + QtWebEngine + 原生音频桥（推荐）**
- 桌面窗口是 `QMainWindow`，中间一个 `QWebEngineView` 加载服务器提供的 SPA。
- 实时语音不用浏览器的 `getUserMedia`：C++ 用 PortAudio 采集 → VAD → `RealtimeClient` 直连火山引擎；识别文本 / AI 语音 / 状态通过 **QWebChannel** 推给页面，页面通过同一通道下指令（开始、停止、打断）。
- 优点：刚统一好的设计语言、报告、语料库、写作全部直接复用；只需新增一个「音频桥」和桌面专属能力。工作量可控（几周量级）。
- 缺点：包体大（WebEngine ≈ 150MB+）。

**B. Qt Quick（QML）原生重写全部页面**
- 体验最原生，动效（弹簧、形变）在 QML 里很顺手。
- 缺点：所有页面（练习、报告、语料库、写作、拼写…）要重写，等于再做一遍前端，数月量级；设计语言要在 QML 里重新实现一遍，两端会再次分叉。

**C. 继续扩写旧 Qt Widgets 窗口**
- 只做面试；IELTS 部分仍在网页。体验割裂，Widgets 难做出现在的设计语言和动效。不推荐。

结论：选 A。以后如果某个页面需要更原生（例如面试实时对话页），可以单独用 QML 嵌入，不影响其他页面。

## 5. 架构（方案 A + 云服务器）

```
┌──────────── IELTSStudio.app (Qt 6) ────────────┐        ┌──────── VPS ────────┐
│ MainWindow                                     │ HTTPS  │ Nginx + Daphne      │
│  └─ QWebEngineView ──loads──────────────────────┼───────▶│ Django（账号/报告/  │
│        ▲  QWebChannel "native"                 │        │ 语料库/题库/面试）  │
│        │   - capabilities()                    │        │ AI worker           │
│        │   - startSession(kind, opts) / stop / │        │ POST /api/realtime/ │
│        │     interrupt                         │        │   credentials       │
│        │   - signals: partial, final,          │        └─────────────────────┘
│        │     aiSpeaking, level, error          │
│  NativeAudioBridge (QObject)                   │  WSS   ┌─────────────────────┐
│   ├─ AudioEngine    PortAudio 采集/播放 + VAD   │───────▶│ 火山引擎实时对话    │
│   ├─ RealtimeClient 直连火山（凭证来自服务器） │        └─────────────────────┘
│   └─ SessionDriver  IELTS / 面试会话脚本        │
│  Settings  服务器地址（默认生产地址，可改本机）│
└────────────────────────────────────────────────┘
```

- **页面侧检测**：`window.qt && qt.webChannelTransport` 存在 → 桌面模式，`app.js` 的录音入口改走 `native` 通道，并显示模式切换器；否则保持现有浏览器链路、不显示切换器。这层封装在新的 `web/static/native-bridge.js`，`app.js` 只改调用点。
- **登录态**：WebEngine 里正常登录，Cookie 存在 WebEngine 的持久化 profile 里；C++ 侧需要调接口（申请凭证、上传录音）时，由页面经通道把请求转交，或从 profile 的 cookie store 读会话 Cookie。阶段 2 选其一，倾向「页面代发」，C++ 不碰 Cookie。
- **实时凭证**：新接口 `POST /api/realtime/credentials`（需登录、限频），返回火山连接所需的 header 值与过期时间；C++ 只放内存，每次开始会话前申请。
- **数据**：会话结束后，桌面端把转写 / 音频 / 时间戳交给服务器现有接口生成报告（与网页端同一套报告与存储），不另造一套。

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
- 追问：由火山实时对话模型驱动，`SessionDriver` 负责下发系统提示词与题目脚本（`dialog_session` 的现有逻辑迁过来）。
- 报告：沿用口语报告的版式（统一设计语言），换维度与文案。

## 8. 错误处理

- 服务器连不上（断网 / 服务器宕机）：外壳显示原生错误页，提供「重试」和「更改服务器地址」。
- 凭证申请失败（未登录 / 限频 / 服务器未配置火山密钥）：桥返回 `error('credentials')`，页面提示并回退到浏览器音频链路。
- 麦克风权限被拒（macOS TCC）：桥返回 `error('mic-permission')`，页面引导去系统设置；`Info.plist` 带 `NSMicrophoneUsageDescription`。
- 实时连接断开：自动重连一次，失败则降级为「录完再转写」，页面提示。
- WebEngine 崩溃：外壳捕获 `renderProcessTerminated` 后重载页面，会话状态在 C++ 侧保留。

## 9. 测试

- C++：现有 `tests/*.cpp`（audio_core、config…）继续跑；新增 `NativeAudioBridge` 的信号/槽单测（用假音频源 + 假 RealtimeClient）。
- 网页：`node --test tests/*.test.js` 继续通过；新增 `native-bridge.js` 的单测（模拟 `qt.webChannelTransport`）。
- 后端：`manage.py test` 继续通过；凭证接口、面试题库 / 定制出题 / 面试报告接口加测试。
- 手动验收：桌面端完整走一遍 IELTS P1 实时练习 + 一场模拟面试；网页端回归。

## 10. 分阶段计划（每阶段可单独验收）

**阶段 0 — 环境**
1. `brew install qt`（我来跑）。
2. 桌面端是独立 CMake 工程 `desktop/`（只依赖 Qt，不依赖 vcpkg），验证它能找到 `Qt6::WebEngineWidgets` 并跑通单测；根目录旧目标不动。

**阶段 1 — 桌面外壳（能打开现有网页）**
1. 新目标 `IELTSStudioDesktop`：`MainWindow` + `QWebEngineView`（持久化 profile）+ 设置里的服务器地址（开发期默认 `http://127.0.0.1:8767`）。
2. 菜单 / 连不上时的原生错误页；`Info.plist` 麦克风说明。
3. 验收：双击 app 打开，看到当前统一设计的首页，能登录，所有页面可用（音频暂走浏览器链路）。

**阶段 2 — 原生音频桥（真正实时）**
1. 先查清火山实时对话是否支持临时凭证，定下凭证接口的返回内容；服务器加 `POST /api/realtime/credentials`。
2. `NativeAudioBridge` + `QWebChannel` 注册；`native-bridge.js` 封装能力检测与调用。
3. `AudioEngine`：复用 `audio_core`（VAD）与 PortAudio；播放 AI 语音；支持打断（AI 说话时检测到用户开口即停播）。
4. 把 P1/P2/P3 练习的录音入口切到桥上（桌面模式），结束后照常调服务器接口生成报告。
5. 验收：桌面端 P1 实时练习延迟明显低于网页端，可打断；报告正常生成。

**阶段 3 — 模式切换器（仅桌面端）**
1. 先逐帧观察 detail.design 左上角动效，记录参数。
2. 实现切换浮层（网页层，仅在检测到原生桥时渲染）+ `mode-*` 状态 + 侧栏按模式切换。
3. 验收：动效顺滑（60fps），键盘可用，刷新后保持模式，深浅色都正常；浏览器打开时看不到切换器。

**阶段 4 — 模拟面试**
1. 后端：面试题库、定制面试（PDF 解析 + LLM 出题）、面试会话 / 报告的数据模型与接口（尽量复用口语报告的生命周期）。
2. 前端：面试首页、题库练习、简历与岗位上传、面试进行页（复用练习页布局）、面试报告页（复用报告版式）。
3. 桌面端：`SessionDriver` 的面试脚本（开场 → 项目深挖 → 追问压力）。
4. 验收：题库练习和一份测试简历的定制面试各完整走一场并出报告。

**阶段 5 — 云服务器部署（可与阶段 1–4 并行，需要你先买 VPS）**
1. Linux + Daphne + Nginx + HTTPS（域名 + 证书）；AI worker 用 systemd 常驻。
2. 迁移数据：从办公室 Windows 机拷最新 `db.sqlite3` 与 `media/`；先沿用 SQLite，有并发问题再换 PostgreSQL。
3. 桌面端默认服务器地址改为生产域名。
4. 验收：网页版和桌面端都连 VPS 正常使用；Windows 机可下线。

**阶段 6 — 打包**
1. `macdeployqt` 打包（不含 Python，只有 Qt + WebEngine）。
2. 签名 / 公证（如需分发给别人）。

## 11. 风险

- 火山实时对话可能只支持长期 App ID / Access Key：那就退到「只对登录用户下发」，并在服务器端限频、记录用量。
- 国内 VPS 的域名需要备案（数周）；备案期间可先用 IP + 自签证书或海外 VPS 过渡。
- 客户端直连火山：延迟取决于你本机到火山的网络，与 VPS 无关；但凭证申请和报告上传会多一次到 VPS 的往返（不在实时链路上）。
- QtWebEngine 在 macOS 上的麦克风权限：原生采集绕开了网页权限，但 app 本身仍需 TCC 授权。
- 回声消除：外放时需要 AEC，否则会自我打断；先用耳机验收，AEC 作为后续项。
- `brew` 的 Qt 会随 `brew upgrade` 滚动升级；打包分发前固定版本（`brew pin qt`）。
