# 交接：Qt 桌面端 + 模拟面试（2026-10-05）

## 可复制交接提示词

```text
项目：~/Documents/trading-study/AI-realtime_speech-for-IELTS-Job_Interview，分支 ui-polish（只在本地，不要推送；不要提交 backend_django/db.sqlite3）。

我们在把 IELTS Studio 做成 Qt 桌面端，并新增「模拟面试」模式（雅思口语的改编版）。先读：
1. docs/reports/qt-desktop-mock-interview-handoff-2026-10-05.md（本交接）
2. docs/superpowers/specs/2026-10-05-qt-desktop-studio-design.md（设计，§3 区分用户决定与本次建议）
3. docs/superpowers/plans/2026-10-05-qt-desktop-shell.md（阶段 0–1 计划 + 末尾执行记录）
4. docs/superpowers/plans/2026-10-05-native-voice-performance.md（阶段 2 的建议计划，尚未实现）
5. desktop/README.md（构建、运行、冒烟、调试）

阶段 0–1（桌面外壳）已完成并经用户验收；网页/桌面共享的浅色、深色、跟随系统三档已实现，保留旧手动偏好。
用户要以原生 C++ 低延迟语音作为技术作品；不因减少依赖就选 Qt，也不假定 Qt 比 PortAudio 慢。
阶段 2 已完成代码审计和组件/鉴权文档研究，写好了建议计划，语音引擎尚未实现、组件尚未最终批准。
先看两份研究（.trellis/tasks/10-05-desktop-voice-performance/research/），再按计划做同设备 Qt 6.11 callback 与 PortAudio callback 对照实验。
旧 C++ 是半双工原型，不能原样复用；优先独立 C++ 引擎、Qt 控制适配器、成熟音频/传输组件。
火山文档有控制台 Access Token，但未查到该端点短期/限定范围凭证的公开签发契约；先向供应商核实。
本次审计建议用登录鉴权、有界实时转发的服务器 relay 替换此前“服务器下发长期密钥”退路，待阶段 2 方案审阅；不下发服务器密钥，也不伪造 expires_at。
后端建议同一 Django 服务内新建 apps.interview，共享 AI/媒体基础设施和报告版式，保持独立面试模型与评分 schema。
VPS 先不买，完成本地效果验证再评估。
模式切换器（阶段 3）和模拟面试（阶段 4）各自单独写 spec 补充 + 计划，动手前要用户确认。
用中文和用户沟通。
```

## 一句话现状

桌面外壳、左上角模式切换器和**文字版模拟面试**已能用（2026-10-05 晚）：桌面端 `IELTS Studio ⇄ 模拟面试` 切换，面试模式有首页 / 通用题库（30 题、5 个方向）/ 简历定制 / 面试记录，答题、跳过、一次 AI 追问、结束、文字报告、AI 文字建议都走 `apps.interview`。浏览器版本不出现切换器和面试入口。**原生实时语音仍未接入**：`native_voice/` 只有经过测试的 C++ 缓冲/生命周期内核和设备适配器，桥接能力里 `native_audio` 明确为 false，面试页写明「当前支持文字作答」。

## 已确认决定与本次建议（设计文档 §3）

| # | 结论 |
|---|------|
| D1 | Qt 外壳 + QtWebEngine 承载现有网页 UI；实时语音走原生 C++，经 QWebChannel 和页面通信。 |
| D2 | 最终后端放云服务器（VPS）；桌面端不内置 Python/Django，地址可配置。**购买和部署推迟到本地效果验证之后**。 |
| D2′ | **本次审计建议替换历史“下发长期密钥”退路，待阶段 2 方案审阅**。短期、限定范围的供应商凭证尚未证实；现阶段建议已登录客户端通过有界流式服务器 relay 连接供应商，长期密钥留服务器。直连须先验证供应商凭证契约。此方案是研究建议，尚未实现。 |
| D3 | **模拟面试和左上角切换器只在桌面端出现**；浏览器打开时保持静态品牌位，不出面试入口。 |
| D4 | 题源两种：日常练习用**通用面试题库**；「**定制面试**」= 上传简历 PDF + 岗位描述，LLM 出题。 |
| D5 | Qt 已装，6.11.2；Qt 6.11 有原生音频 callback API，可与 PortAudio callback 公平实测。最终音频组件尚未选定。 |
| D6 | 已同意并实现浅色 / 深色 / 跟随系统；旧手动浅/深色选择保留，仅 system 模式响应系统变化。 |
| D7 | 语音保持 C++，性能目标通过可复现实验、尾延迟和稳定性数据验证；后端建议独立 `apps.interview`，共享基础设施。 |

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
5. **外观已更新为三档**：`ielts-appearance-mode` 保存 light/dark/system；旧 `ielts-dark-mode=1/0` 分别保留深色/浅色，新用户默认 system。首次绘制前应用外观，只有 system 模式响应实时系统变化。不要又退回单一手动开关。
6. Bash 里 `LANG` 为空，`pbpaste`/`pbcopy` 会把中文变成 `?`；碰剪贴板一律加 `LANG=en_US.UTF-8`，测试尽量别碰用户剪贴板。
7. 本地开发服务器（8767）若由 agent 后台启动，会被时长上限停掉；用户可以自己在终端跑：
   `set -a && . ./.env && set +a && .venv-django/bin/python backend_django/manage.py runserver 127.0.0.1:8767 --noreload`

## 接下来做什么（按顺序）

### 阶段 2 — 原生 C++ 实时语音（研究与计划完成，未实现）

详细执行切片和验收见 [原生语音性能计划](../superpowers/plans/2026-10-05-native-voice-performance.md)。证据见 [旧 C++ 审计](../../.trellis/tasks/10-05-desktop-voice-performance/research/cpp-voice-audit.md) 与 [组件/鉴权研究](../../.trellis/tasks/10-05-desktop-voice-performance/research/native-voice-components.md)。

- **旧代码能借什么**：协议 fixture、RMS/peak 等纯函数、简历出题/追问的业务思路。音频设备和网络已有原生实现，但当前阻塞采集一块是 3,200/16,000 = **200 ms**；麦克风与提示词并发写同一 socket、TLS 未验证证书、脱离管理的结束线程捕获 this，停止先 join 再解除阻塞。播放 TTS 时发送静音并忽略开口事件，是半双工。新 `desktop/` 尚未链接这条语音链路；现有测试多为协议/构造/空会话测试，不能当作实时落地或工业性能证明。
- **建议结构**：独立 C++ 引擎拥有设备、DSP、网络、session 状态和指标；Qt/QWebChannel 只传控制、转写、合并后的电平和状态。音频 callback 不分配、不等待锁、不做网络/日志；预分配有界缓冲，每条 SPSC 明确唯一 producer/consumer，网络单 owner 串行 write/close；线程可取消并由 owner 回收。打断提升 turn epoch、丢旧音频，并测设备中尚未播完的声音。
- **组件实验**：先用已有 PortAudio 依赖做 callback 后端，与 **Qt 6.11 QAudioSource/QAudioSink callback** 在同一有线设备、格式、采样率、负载下 A/B。Qt 也是 C++，两者快慢由测量决定。miniaudio 是包装/跨平台备选；不一次引入三套后端。成熟库解决设备、传输、AEC 等部件，产品 session/取消契约仍需自己实现。
- **帧与指标**：设备/DSP 试验用 10 ms 块，供应商推荐 **20 ms/640 bytes、16 kHz mono S16LE** 上行包；不要把两种帧混为一谈。记录 capture → ring → DSP → packet/write → ASR → 可观测的 LLM 首 token → TTS 首包 → 播放队列 → 实际声输出的单调时钟数据；未公开的内部推理阶段标不可观测，不编造 token 时间；报告 P50/P95/P99、样本数、CPU、内存、队列年龄和 underrun/overrun。以初步捕获积压 40–60 ms、播放缓冲 40–80 ms、有线设备打断到静音 P95 <100 ms 为实验假设，未达到前不宣称工业标准或领先。
- **原生全双工云端 baseline**：另有[官方全双工实时语音接口](https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh)，端点 `/api/v3/duplex/realtime/dialogue`，使用 `X-Api-Key` 和独立协议，20 ms 包按真实时间节奏发送。先验证独立 adapter，与原 ASR→LLM→TTS 链路对照；不能只改旧客户端 URL。该 API 是否符合实际插话、费用和报告要求还未实测。
- **鉴权**：[火山官方实时语音接口](https://docs.volcengine.com/docs/DoubaoVoice/End-to-endreal-timespeechlargemodelAPIaccessdocument?lang=zh) 的 `X-Api-Access-Key` 是控制台 Access Token，未查到此 WebSocket 的临时签发/过期/资源范围文档，**不是已证实不支持**。向供应商核实；未确认前建议登录、session/turn 所有权校验、限并发/用量、有界队列的流式 relay。本地可先跑 relay，密钥在服务器环境；应用短期 relay ticket 不是火山临时凭证，不返回长期密钥或虚构过期时间。
- **先耳机后外放**：持续采集才有真正打断；本地 VAD 不是 AEC。耳机链路先验收，外放另评估 WebRTC APM，以实际播放音频作为回声参考，并验证双讲、时钟漂移和识别质量。
- **验收方向**：相同设备/供应商/提示词/网络的对照和长稳测试；快开快关、网络背压、鉴权过期、设备变更不僵死、不重播旧回合；转写/录音/报告继续正常。云端 endpointing、推理和 WAN 单独统计，不能保证整体响应必然低于网页版。

### 阶段 3 — 左上角模式切换器（只在桌面端）— **已实现**

已按 detail.design 实测参数实现（见 `.trellis/tasks/10-05-desktop-interview-mvp/research/mode-switcher-reference.md`）：品牌按钮位置不动，`#studioModeMenu` 作为 fixed 卡片从按钮矩形用弹簧（stiffness 300 / damping 30 → CSS `linear()` 500 ms）长到 272px 卡片，内容按最终宽度排好、由容器裁切，列表 200 ms 透明 + 4px 模糊淡入；关闭 380 ms 反向。平时品牌位与原 `.brand` 视觉一致，悬停/展开才出现 ⇕ 箭头。下面是原计划，留作对照：


- 动手前**用浏览器逐帧观察 https://detail.design/ 左上角**：品牌按钮原地形变成浮层卡（共享元素 + 弹簧曲线），参考文案是它的 Share Feedback 卡。记录时长、曲线、内容淡入顺序。
- 卡内两项：`IELTS Studio`（雅思口语与写作）/ `模拟面试`（题库练习 · 定制面试 · 实时追问），当前项带对勾；Esc / 点外部收回；↑↓ + 回车；`prefers-reduced-motion` 时只淡入淡出。
- 结果：`body` 加 `mode-ielts` / `mode-interview`，侧栏换成对应模式入口；模式存 localStorage。**只在检测到原生桥时渲染**，浏览器里看不到。
- 品牌位现状：`web/static/index.html` 的 `.brand`（logo `/assets/brand/studio-logo.svg`），样式在 `styles.css` 末尾「ONE DESIGN LANGUAGE」段之后（`.brand-mark` / `.brand span` 的 clamp 尺寸）。新规则沿用 `body:not(#_)` 提权写法和 `--ui-r` / `--ed-serif` 等 token。
- 用户的硬性 UI 偏好：P1/P2/P3 颜色只用在侧栏按钮；保留原练习布局、滑动开关和像素流动效果；图标按钮必须正方形（`docs/frontend-ui-conventions.md`）。

### 阶段 4 — 模拟面试（雅思口语改编）— **文字版已实现，语音与评分待做**

已实现：`apps.interview`（题库、定制出题、session/turn、追问、finish/abort、文字报告、AI 文字建议，21 个测试）+ `web/static/interview.js`（首页 hero + 设置面板 + Practice paths、题库多选浮条、简历定制三步、答题页进度轨、报告与记录，沿用首页的 mono kicker / 金线 / 衬线标题语言）。侧栏面试入口复用 `.nav-button` 样式。未做：「我的故事库」、P2 式「准备 + 陈述」、技术评分维度、语音作答。下面是原计划：


| 雅思口语 | 模拟面试 |
|----------|----------|
| P1 短问短答 | 开场与自我介绍、基础问题 |
| P2 题卡 1 分钟准备 + 2 分钟陈述 | 项目深挖：选一段经历，准备后完整陈述 |
| P3 深入讨论 + 追问压力 | 追问压力：针对回答连续追问（技术 / 行为） |
| 评分 FC / LR / GRA / P | 表达清晰度、结构（STAR）、技术深度、岗位匹配 |
| 语料库 | 「我的故事库」：可复用的项目故事与回答 |

- 面试模式侧栏（初稿）：首页 / 题库练习 / 定制面试（简历 + 岗位）/ 面试报告 / 我的故事库。
- 后端建议：在同一个 Django 服务内新增 `apps.interview`，不拆微服务。独立面试 session/turn/report、简历/岗位与技术评分 schema；共享 `apps/ai` 的 provider、AITask、计费/账号，以及可抽取的媒体存储和报告版式。`SpeakingReport` 的 Band 7/FC/LR/GRA/P 契约不适合直接套技术评分；不要强行新增 speaking 模式。题库按类别分组，首批题目用户审；定制面试在服务器解析 PDF 和生成题目。
- 可参考的旧 C++ 逻辑（只借思路，出题移植到 Python）：`src/interview/interview_manager.cpp`（`LoadQuestionsFromResume`、`GenerateDefaultQuestions`、`ShouldFollowUp` / `GetFollowUpQuestion`）、`src/interview/dialog_session.cpp`（实时对话中的追问，迁到 `SessionDriver`）、`src/services/pdf_parser.cpp`。
- 前端：面试首页、题库练习、简历与岗位上传、面试进行页（复用练习页布局）、面试报告页（复用口语报告版式）。
- 验收：题库练习和一份测试简历的定制面试各完整走一场并出报告。

### 并行 / 之后

- 阶段 5 — VPS 部署（**用户决定先做完看效果，本地验证前不买、不部署**）：Linux + Daphne + Nginx + HTTPS；AI worker 用 systemd；从办公室 Windows 机迁 `db.sqlite3` 与 `media/`；国内 VPS 要域名备案。
- 阶段 6 — `macdeployqt` 打包、签名 / 公证；`brew pin qt` 固定版本；补 app 图标。

## 下一步需要验证的选择

四项反馈已记录：外观同意并实现；语音保留 C++、以性能证据选成熟组件；后端给出独立 app 的建议；VPS 延后。不要重复询问这四项。

1. 按阶段 2 计划做 PortAudio callback 与 Qt 6.11 callback 的同设备实验后，审阅最终组件选择；用户尚未批准最终音频组件。
2. 核实火山临时/限定范围凭证的准确签发、续期、撤销与权限文档；未确认前用服务器 relay 建议作为计划基线。
3. 模式切换器和模拟面试的详细交互/题库/评分另行审阅，后端独立 app 仍是建议，尚未实施。

本交接更新不意味着原生实时语音已经上线，也不意味着已测得工业水准。当前任务的实际测试/提交结果以本次执行记录为准；上方阶段 0–1 的 67/67 等属于历史验收。

## 本次验证记录（2026-10-05）

- 网页测试：一次完整运行 66/68 文件通过，修复后对两项失败文件单独重跑 2/2 通过；不是修复后再次全量 68/68。
- 桌面 QtTest：3/3；桌面三档外观的可见布局已检查，未做物理 OS 深浅色切换验收。
- 原生语音尚未实施，未运行真实设备/provider 性能 benchmark。新引擎和面试 app 均不能标成已完成。

## 本次验证记录（2026-10-05 晚，Claude 接手 Codex 的未提交工作后）

- 网页 `node --test tests/*.test.js`：76/76（修了浏览器模式下面试模块仍请求题库接口的问题）。
- Django `manage.py test apps.interview`：21/21；桌面 `ctest --test-dir build-desktop`：4/4（含 `native_bridge_test`）；`native_voice` ctest 4/4，合成基准 3 s：capture→render P99 22.4 ms（软件环回，非设备/端到端延迟）。
- 实机 UI：独立 QA 服务 8768 + 独立 SQLite（Codex work 目录）+ `--test-profile`，CDP 截图检查：切换器逐帧（暂停 Web Animations 取 0/40/90/150/240/500 ms）、面试首页、题库、简历定制、答题、追问提示、报告（浅/深色）、记录、切回 IELTS、浏览器版无入口。
- 未做：真实麦克风/外放、AI 追问与 AI 建议的真实调用（会产生费用，只测了失败路径与接口）、PDF 解析的真实简历。
- **用户自己的 `db.sqlite3` 还没有 `interview_*` 表**：用 8767 正常跑之前需要 `manage.py migrate interview`（只新增表；按约定先问用户再迁移）。

## 面试 v2（2026-10-05 深夜，对标雅思口语）

设计：`docs/superpowers/specs/2026-10-05-interview-studio-v2-design.md`（用户确认结构后执行）。提交 `0e78371`（画像+语料）、`31f21db`（场次+面试官引擎+百分制）、`8743735`（前端）。

- **内容**：`InterviewProfile`（简历 / JD）+ `InterviewCorpusEntry`（自我介绍、项目讲述、项目追问、知识点、奖项、岗位题、反问；我的答法 + AI 参考）。重新拆分按 `source_key` 只刷新 AI 稿，不覆盖用户答法；简历里删掉的模块标记 orphaned。
- **流程**：完整面试 = 自我介绍 → 每个项目 → 知识点（简历技术栈 → JD → 精选题补足）→ 奖项 → 反问。分段：项目 / 知识点 / 反问。标准模式每题最多 1 层追问，追问压力 3 层（项目 4 层），服务器强制；AI 失败直接进入下一题。
- **作答**：MediaRecorder 录音 → `POST .../audio/` → 火山 ASR 转写 → 可修改后提交；也可打字。**当前 `.env` 里火山 ASR 是注释掉的，录音会转写失败并退回打字。**
- **报告**：五维百分制（30/25/20/15/10）+ 能力边界 + 下一步；完成后自动请求一次。
- **界面**：侧栏照 Mock + P1/P2/P3；首页带占位轮播；练习页复用雅思练习页类名；语料库照「P1 语料库」卡片；定制页「简历 | JD」开关。
- **验证**：后端 `manage.py test apps.interview` 40/40；网页 79/79；桌面 4/4。离屏 Qt 实例 + 无 AI 密钥的 8768 测试服务实机走完：开始 → 打字作答 → 面试官失败回退 → 看我的答法 / 存为我的答法 → 跳过 → 完成 → 报告（评分失败可重试）→ 语料库 / 编辑弹窗 / 定制页。
- **未做 / 待办**：面试官读题语音（TTS）；真实 AI 的追问与评分质量未实测（会产生费用）；用户自己的 `db.sqlite3` 需 `migrate interview`（先问用户）；完整 Django 测试有 12 个与本次无关的既有失败（AI worker 与两个静态资源路由，基线提交上同样失败）。


## 面试页面直接复用雅思样式（2026-10-06）

用户要求「样式从雅思搬，很多是同位体」。做法：面试页面直接输出雅思对应页面的结构和类名；雅思样式里按 id 写的规则，用 `scripts/alias_ielts_styles.py` 追加面试 id 的别名选择器（id 换 id，优先级不变；只出现在 `:has()` / `:not()` 里的不追加，避免影响雅思页面）。改了雅思样式后重新跑一遍这个脚本即可，重复跑不会重复添加。

| 面试页面 | 对应雅思页面 | 别名 |
| --- | --- | --- |
| 面试首页 | 首页 | `#homePanel` → `#interviewHome` |
| 面试语料库 + 编辑弹窗 | P1 语料库 | `#p1CorpusPanel` → `#interviewCorpus` |
| 面试报告 | 口语报告（横向报告栏 + 总分卡 + 总体点评 + 逐题表格） | `#historyPanel` / `#historyList` / `#detailPanel` → `#interviewReports` / `#interviewReportList` / `#interviewReportDetail` |
| 练习页 | P1 练习（开始前的选项用 P3 的启动面板样式） | `#practicePanel`、`#promptPane`、`#recordControl` 等 10 个 |
| 简历 / JD 定制 | 每日写作（Task 1/2 开关 = 简历/JD 开关） | `#writingPanel`、`#writingScoreBtn`、`#writingSaveBtn` |

提交：`ab8634d`（首页 / 语料库）、`8bc6be2`（报告）、`c5f0d8e`（练习）、`1deb9eb`（定制）、`d435426`（删掉 144 条不再使用的旧面试样式）。网页测试 79/79；离屏 Qt 实例逐页截图核对（含暗色），雅思写作页改动前后截图逐像素相同。
