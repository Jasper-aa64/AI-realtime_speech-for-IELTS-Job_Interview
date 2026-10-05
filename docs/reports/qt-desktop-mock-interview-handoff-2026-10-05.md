# 交接：Qt 桌面端 + 模拟面试（2026-10-05）

## 可复制交接提示词

```text
项目：~/Documents/trading-study/AI-realtime_speech-for-IELTS-Job_Interview，分支 ui-polish（只在本地，不要推送；不要提交 backend_django/db.sqlite3）。

我们在把 IELTS Studio 做成 Qt 桌面端，并新增「模拟面试」模式（雅思口语的改编版）。先读：
1. docs/reports/qt-desktop-mock-interview-handoff-2026-10-05.md（本交接）
2. docs/superpowers/specs/2026-10-05-qt-desktop-studio-design.md（设计，§3 是已确认决定）
3. docs/superpowers/plans/2026-10-05-qt-desktop-shell.md（阶段 0–1 计划 + 末尾执行记录）
4. desktop/README.md（构建、运行、冒烟、调试）

阶段 0–1（桌面外壳）已完成并经用户验收。下一步按交接文档「接下来做什么」推进：
先为阶段 2（原生实时语音桥）写计划，第一件事是查清火山引擎实时对话是否支持临时凭证；
模式切换器（阶段 3）和模拟面试（阶段 4）各自单独写 spec 补充 + 计划，动手前要用户确认。
用中文和用户沟通。
```

## 一句话现状

桌面外壳能用了：`desktop/` 下独立的 Qt 6 工程，双击 `build-desktop/IELTS Studio.app` 打开，里面是服务器上的现有网页 UI（开发期连 `http://127.0.0.1:8767/`）。模拟面试、模式切换器、原生实时语音都还没开始写代码。

## 已确认的决定（设计文档 §3）

| # | 结论 |
|---|------|
| D1 | Qt 外壳 + QtWebEngine 承载现有网页 UI；实时语音走原生 C++，经 QWebChannel 和页面通信。 |
| D2 | 后端放云服务器（VPS）；桌面端只是客户端，不内置 Python/Django；服务器地址可配置。 |
| D2′ | 客户端直连火山引擎；连接凭证由服务器下发、只放内存。火山若不支持临时凭证 → 只对登录用户下发长期密钥并限频。 |
| D3 | **模拟面试和左上角切换器只在桌面端出现**；浏览器打开时保持静态品牌位，不出面试入口。 |
| D4 | 题源两种：日常练习用**通用面试题库**；「**定制面试**」= 上传简历 PDF + 岗位描述，LLM 出题。 |
| D5 | Qt 用 `brew install qt`（已装，6.11.2）。 |

## 已完成（阶段 0–1）

提交：`7d1e17f` … `8ef5e4a`（`git log --oneline -- desktop/`）。

- `desktop/src/server_settings.*`：服务器地址规范化 / 读写（QSettings `server/url`）。
- `desktop/src/navigation_policy.*`：同源判断；站外链接交给系统浏览器；麦克风 / 剪贴板只授权给服务器同源；哪些加载失败算「服务器不可达」。
- `desktop/src/error_page.*`：原生「连不上 IELTS Studio 服务器」页（重试 / 更改服务器地址…）。
- `desktop/src/studio_profile.*`：持久化 profile `IELTSStudio`（登录、localStorage 重启后保留）、下载到「下载」文件夹 + 状态栏提示、**隐藏 Web Speech API 的注入脚本**（见下方坑 1）。
- `desktop/src/studio_page.*`、`browser_window.*`、`main.cpp`：主窗口 / 弹窗、菜单（应用菜单里有 服务器地址… Cmd+,；视图 / 编辑 / 窗口）、渲染进程崩溃自动重载、`--server <url>`、`--smoke`。
- 测试：`ctest --test-dir build-desktop`（3 组 QtTest）；网页端 `node --test tests/*.test.js` 67/67。
- 用户验收：首页、登录持久、10 个页面、弹窗、下载、剪贴板、错误页 + 换服务器、外链、崩溃恢复、P1 录音（修复后）都通过。

## 必须知道的坑（都已解决，别再踩）

1. **QtWebEngine 的语音识别会杀页面。** 它暴露 `webkitSpeechRecognition` 却没有语音服务，`start()` 让 Chromium 直接终止渲染进程（日志：`No binder found for interface media.mojom.SpeechRecognizer`）。现在由 profile 注入脚本把它藏掉，页面走「转写不可用」分支：录音照存，文字稿靠服务器 Realtime ASR。→ **模拟面试的实时转写必须走阶段 2 的原生链路，不能指望浏览器转写。**
2. **登录在快速退出时丢失。** Chromium 约 30 秒才把 Cookie 写盘；macOS 的 Quit 会直接 `exit()`。现在主窗口 `closeEvent` 拒绝关闭并让事件循环退出，`main()` 按「窗口 → 排空事件 → profile → 排空事件」顺序销毁。改退出逻辑时保持这个顺序。
3. **后台点不到网页内容。** 测桌面端页面要用 `QTWEBENGINE_REMOTE_DEBUGGING=9333` 启动，再用 Chrome DevTools 协议驱动（脚本示例思路：取 `http://127.0.0.1:9333/json/list` 的 websocket，`Runtime.evaluate` 带 `replMode: true`）。原生菜单 / 对话框用无障碍工具操作即可。
4. 冒烟测「不可达」用普通空闲端口（59999）；端口 9 之类会被 Chromium 以 `ERR_UNSAFE_PORT` 拒绝。
5. **深色模式不跟随系统是网页本身的设计**：网页从不使用 `prefers-color-scheme`，只有设置里的「深色外观」开关（`localStorage["ielts-dark-mode"]`）。是否加「跟随系统」三档选项，**待用户决定**。
6. Bash 里 `LANG` 为空，`pbpaste`/`pbcopy` 会把中文变成 `?`；碰剪贴板一律加 `LANG=en_US.UTF-8`，测试尽量别碰用户剪贴板。
7. 本地开发服务器（8767）若由 agent 后台启动，会被时长上限停掉；用户可以自己在终端跑：
   `set -a && . ./.env && set +a && .venv-django/bin/python backend_django/manage.py runserver 127.0.0.1:8767 --noreload`

## 接下来做什么（按顺序）

### 阶段 2 — 原生实时语音桥（模拟面试的前提）

1. **先查**：火山引擎实时对话（`wss://openspeech.bytedance.com/api/v3/realtime/dialogue`，现有 C++ 用 `X-Api-App-ID` / `X-Api-Access-Key` 头，见 `include/services/realtime_client.h`）是否支持临时 / STS 凭证。结论决定 `POST /api/realtime/credentials` 返回什么。
2. 服务器：新增凭证接口（需登录、限频）。
3. 桌面：`NativeAudioBridge`（QObject，经 QWebChannel 注册为 `native`）= `AudioEngine`（PortAudio 采集 / 播放 + `src/ielts/audio_core.cpp` 的 VAD，libfvad 已在 `third_party/`）+ `RealtimeClient`（复用 `src/services/realtime_client.cpp`）+ `SessionDriver`。
   - 注意：现有 C++ 依赖 vcpkg（boost-beast、portaudio、spdlog 等，根 `CMakeLists.txt`），而 `desktop/` 目前只依赖 Qt。要决定：把需要的依赖改用 brew 装进 `desktop/`，还是用 Qt 自带的 `QWebSocket` / `QAudioSource` 重写客户端（后者依赖更少，倾向于此，需和用户确认）。
4. 网页：新增 `web/static/native-bridge.js`（检测 `window.qt && qt.webChannelTransport`，封装 `capabilities()` / `startSession` / `stop` / `interrupt` 与 `partial` / `final` / `aiSpeaking` / `level` / `error` 信号），`app.js` 只改录音入口调用点。
5. 验收：桌面端 P1 实时练习可打断、延迟明显低于网页端，报告正常生成。

### 阶段 3 — 左上角模式切换器（只在桌面端）

- 动手前**用浏览器逐帧观察 https://detail.design/ 左上角**：品牌按钮原地形变成浮层卡（共享元素 + 弹簧曲线），参考文案是它的 Share Feedback 卡。记录时长、曲线、内容淡入顺序。
- 卡内两项：`IELTS Studio`（雅思口语与写作）/ `模拟面试`（题库练习 · 定制面试 · 实时追问），当前项带对勾；Esc / 点外部收回；↑↓ + 回车；`prefers-reduced-motion` 时只淡入淡出。
- 结果：`body` 加 `mode-ielts` / `mode-interview`，侧栏换成对应模式入口；模式存 localStorage。**只在检测到原生桥时渲染**，浏览器里看不到。
- 品牌位现状：`web/static/index.html` 的 `.brand`（logo `/assets/brand/studio-logo.svg`），样式在 `styles.css` 末尾「ONE DESIGN LANGUAGE」段之后（`.brand-mark` / `.brand span` 的 clamp 尺寸）。新规则沿用 `body:not(#_)` 提权写法和 `--ui-r` / `--ed-serif` 等 token。
- 用户的硬性 UI 偏好：P1/P2/P3 颜色只用在侧栏按钮；保留原练习布局、滑动开关和像素流动效果；图标按钮必须正方形（`docs/frontend-ui-conventions.md`）。

### 阶段 4 — 模拟面试（雅思口语改编）

| 雅思口语 | 模拟面试 |
|----------|----------|
| P1 短问短答 | 开场与自我介绍、基础问题 |
| P2 题卡 1 分钟准备 + 2 分钟陈述 | 项目深挖：选一段经历，准备后完整陈述 |
| P3 深入讨论 + 追问压力 | 追问压力：针对回答连续追问（技术 / 行为） |
| 评分 FC / LR / GRA / P | 表达清晰度、结构（STAR）、技术深度、岗位匹配 |
| 语料库 | 「我的故事库」：可复用的项目故事与回答 |

- 面试模式侧栏（初稿）：首页 / 题库练习 / 定制面试（简历 + 岗位）/ 面试报告 / 我的故事库。
- 后端（Django，新 app 或放进 `apps/speaking` 旁边，需定）：通用题库模型（类别分组，首批题目由 agent 起草、用户审）；定制面试 = 服务器端解析 PDF + 走现有 `apps/ai` 的 LLM 路由出题（密钥留在服务器）；面试会话 / 报告尽量复用 `apps/speaking` 的 `SpeakingAttempt` / `SpeakingTurn` / `SpeakingReport` 生命周期与报告版式。
- 可参考的旧 C++ 逻辑（只借思路，出题移植到 Python）：`src/interview/interview_manager.cpp`（`LoadQuestionsFromResume`、`GenerateDefaultQuestions`、`ShouldFollowUp` / `GetFollowUpQuestion`）、`src/interview/dialog_session.cpp`（实时对话中的追问，迁到 `SessionDriver`）、`src/services/pdf_parser.cpp`。
- 前端：面试首页、题库练习、简历与岗位上传、面试进行页（复用练习页布局）、面试报告页（复用口语报告版式）。
- 验收：题库练习和一份测试简历的定制面试各完整走一场并出报告。

### 并行 / 之后

- 阶段 5 — VPS 部署（需要用户先买服务器）：Linux + Daphne + Nginx + HTTPS；AI worker 用 systemd；从办公室 Windows 机迁 `db.sqlite3` 与 `media/`；国内 VPS 要域名备案。
- 阶段 6 — `macdeployqt` 打包、签名 / 公证；`brew pin qt` 固定版本；补 app 图标。

## 待用户决定

1. 深色模式要不要加「跟随系统」（浅色 / 深色 / 跟随系统，网页版和桌面版同时生效）。
2. 阶段 2 的音频 / WebSocket 依赖：复用 vcpkg 的旧 C++，还是在 `desktop/` 里用 Qt 自带模块重写客户端。
3. 模拟面试后端放新 Django app 还是并入 `apps/speaking`。
4. 何时购买 VPS（决定阶段 5 何时开始、桌面端默认服务器地址何时换成生产域名）。
