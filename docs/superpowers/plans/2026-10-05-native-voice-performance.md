# 原生 C++ 实时语音：性能实验与实施切片（2026-10-05）

> 状态：研究后的建议计划；语音代码尚未实现，最终音频组件尚未批准。外观三档已由用户批准并实现；VPS 先不购买。
> 工作分支：本地 `ui-polish`，不要推送，不要提交现有 `backend_django/db.sqlite3` 改动。

## 1. 目标和边界

用户希望把实时语音做成能够在 C++/低延迟岗位面试中解释、测量和展示的技术作品。目标是可打断的持续采集/流式播放、可控缓冲、可取消生命周期，以及可复现的性能证据。Qt 负责桌面 UI 和控制适配；引擎由 C++ 拥有。使用成熟设备/网络/DSP 库，不自行重写操作系统驱动、TLS 或回声消除。

本计划不包含模式切换器、完整模拟面试产品、VPS 购买/部署或行业领先承诺。先耳机；外放 AEC 为后续独立切片。云端推理、endpointing 和网络 RTT 与本地 C++ 延迟分开统计。

## 2. 已有证据和复用边界

- [旧 C++ 审计](../../../.trellis/tasks/10-05-desktop-voice-performance/research/cpp-voice-audit.md)：原生路径确实存在，但输入阻塞块是 200 ms；单 socket 多处直接写，关闭/线程生命周期有缺陷，TTS 时发送静音并忽略开口事件，属于半双工。新 `desktop/` 尚未链接原生语音。
- [当前组件和鉴权研究](../../../.trellis/tasks/10-05-desktop-voice-performance/research/native-voice-components.md)：Qt 6.11 有软实时 callback API；PortAudio 也有成熟 callback。不得拿 Qt QIODevice 默认缓冲与 PortAudio callback 的不同配置宣称 Qt 更慢。
- 保留旧可执行目标作参考，不将 `DialogSession` 原样接入新桌面。复用协议测试 fixture、已验证的纯函数、简历出题/追问思路；逐边界重建。原 `audio_core` 的每帧创建 VAD、线性无状态重采样须另改为持续 stream 状态和合适的重采样部件。
- 当前 Django 有 gated realtime PCM/ASR 和 mocked ASR→追问→TTS 测试；它们不是已完成的原生全双工方案，也不是性能实测。

## 3. 候选组件和决定方法

| 边界 | 第一实验 | 对照/备选 | 决定依据 |
| --- | --- | --- | --- |
| 设备 I/O | PortAudio callback（已有依赖） | Qt 6.11 QAudioSource/QAudioSink callback；miniaudio 暂作包装备选 | 同一有线设备/格式/采样率/负载，实际 callback、环回、丢帧、CPU、打包成本 |
| 传输 | 单 owner 的异步 Beast/Asio 适配 | 单 QObject/event-loop owner 的 QWebSocket | 并发契约、写队列年龄、TLS、关闭上界、易维护性；无预设速度结论 |
| DSP | 有状态 VAD + 显式重分帧/重采样 | 外放时独立评估 WebRTC APM | 识别质量、双讲/残余回声、DSP 时间和样本时钟漂移 |
| 云端对话 | 验证供应商当前原生全双工 API，作为独立 baseline | 现有 ASR→LLM→TTS 链路 | 真实可打断、媒体/事件契约、鉴权、首音时间、费用和报告回传 |

Qt callback 后端需要 Qt >=6.11，当前工程最低允许 6.8，实施时选择明确提高最低版本或显式降级；不要调用 Qt 6.12 才有的 native-period API。最终组件根据实验记录和用户审阅选择，未批准前不重写整套产品。

[官方原生全双工接口](https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh) 使用 `wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue`、`X-Api-Key` 和独立协议；与旧 `/api/v3/realtime/dialogue` 分开。先验证独立 adapter 的 header、事件、会话状态、取消语义和媒体格式，不能只替换旧客户端的 URL。两条云端 baseline 的模型/策略差异必须记录，不能把换服务所得改善全算作 C++ 优化。

## 4. 引擎和线程契约（建议）

```text
Qt/QWebChannel 控制适配器 ──commands/events── Session owner
                                            │ epoch/state/cancel
设备 capture callback ──capture SPSC── DSP/packet worker
                                         │ bounded command queue
                                         ▼
                               单 transport I/O owner
                                         │ reply/audio
                                         ▼
                                decode/playout worker
                                         │ playback SPSC
                                         ▼
                                  output callback
```

- 每条 SPSC 的 producer/consumer 固定且唯一：capture callback→DSP worker；playout worker→output callback。session 控制和网络 reply 不能直接写同一 SPSC；它们由 playout owner 串行处理。若某通道需要多写者，使用适合该所有权的有界队列，不能称作 SPSC。
- callback 只进行预分配缓冲交换/拷贝与固定成本计数，禁止堆分配、mutex 等待、日志、网络、文件或 LLM。输出不足填静音并计 underrun；输入溢出进入明确失败/降级策略，不能悄悄丢字并继续宣称录音完整。
- 所有缓冲按毫秒、字节和帧数约束；指标包括队列年龄/高水位。网络 owner 串行执行 write、cancel、close；异步 payload 生命周期直到操作完成。证书和 hostname 必须验证。
- session owner 维护 starting/ready/running/stopping/stopped/failed；成功 ACK 才 ready，startup 部分失败也清理。所有线程由 owner 管理，先取消/解除阻塞再 join，禁止 detached lambda 捕获 session this；明确每次 stop 的最大等待与终止结果。
- 每次会话、回合和打断有递增 epoch；解码、播放和 UI 消息校验 epoch。打断在 callback 消费边界切到新 epoch、跳过旧输出；producer 不与 consumer 随意并发重置环形缓冲游标。已交给硬件的声音无法仅靠清空软件队列收回，实际残余必须测量。
- 持续 capture 允许用户在 TTS 期间开口。先耳机降低回声；VAD 不等于 AEC。外放另接 WebRTC APM，使用实际渲染而非全部生成音频作参考，验证格式/延迟/漂移和 double-talk。
- GUI/QWebChannel 只发命令、转写、状态和合并后的电平；不传原始 PCM/每帧统计。评分/报告持久任务不运行在音频播放线程上；实时停止不改变已运行计费分析任务的既有取消规则。

## 5. 鉴权、媒体与 relay

[火山官方实时语音接口](https://docs.volcengine.com/docs/DoubaoVoice/End-to-endreal-timespeechlargemodelAPIaccessdocument?lang=zh) 已公开控制台 Access Token。所查旧端点没有找到短期/限定资源凭证的签发、过期、续期/撤销契约，不能将“未找到”写成“供应商不支持”，也不能将 Access Token 自动解释为 ephemeral token。新全双工 adapter 须按对应文档单独核实。

**本计划建议替换历史 D2′ 的“下发长期密钥”退路，尚待阶段 2 方案审阅**：未确认供应商可签发短期受限凭证前，建议应用服务器提供认证、有界、立即转发的流式 relay，供应商密钥留服务器。服务器发行的短期 session ticket 仅授权应用 relay；不伪造供应商 expires_at，不向客户端返回长期 provider key。直连仅在实际签发/握手/权限/撤销验证后重新评估。

relay 要拒绝匿名，验证 user/session/turn 归属，限制单用户并发、时长/字节/费用和包尺寸；有背压期限、会话 epoch 与终止回收。当前 Django PCM consumer 的无界 Queue、共享 self 上的 restart/线程清理和未要求登录须修正，不能当作生产 gateway 原样使用。本地先运行 Django/relay，不需要买 VPS；分别测 client→relay→provider 每段。

现有旧端点官方建议上行 16 kHz mono S16LE，20 ms =640 bytes；设备/DSP 试验使用 10 ms 块，重分帧聚合为 provider 包。实际硬件 callback 帧数可由 backend 决定，不能硬称其总是 10 ms。官方全双工端点要求 20 ms 包按真实时间发送；adapter 单独执行严格 pacing，不沿用积压后 burst 发送。下行显式协商 Ogg Opus/24 kHz float PCM/S16LE 对应格式，不盲目把所有字节当 float。

## 6. 指标和初始实验目标

| 记录阶段 | 验证意义 |
| --- | --- |
| capture callback/device timestamp→ring→DSP→packet ready→write | 本地采集、排队、重分帧与传输等待 |
| write→ASR interim/final，真实 end-of-speech→供应商 endpoint | 区分首个识别结果和停顿判断 |
| 可观测的 LLM first token→TTS first bytes→decode→playout queue | 生成服务和本地播放启动；端到端 provider 未暴露 token 时标 unavailable，不能编造 |
| output callback→device/DAC estimate→环回/声学 onset | 验证实际声音，不能用收到包替代 |
| interruption request→旧音频最后声输出 | 包括硬件缓冲残余的取消效果 |

所有同进程时间用单调时钟；跨进程/服务器时钟只在校准后关联，不能直接相减。端到端 provider 未公开 ASR/LLM 内部阶段时标不可观测，估计值单列，不能编造。记录冷启动/握手和 warm steady-state、失败/重试比例。每项报 P50/P95/P99、样本数与持续时长，CPU/内存、队列最大年龄、overrun/underrun/drop，不只报平均值。

初始假设：10 ms DSP 块、20 ms provider 包，callback/DSP P99 小于块预算且有余量；捕获/发送应用积压预算 40–60 ms，播放缓冲初试 40–80 ms；有线设备本地打断到静音 P95 <100 ms（若硬件支持）。这些都是调参起点，尚未测得；基线后调整，并同时看质量/丢音。不能为云端响应承诺统一数字，不能牺牲完整语音换低延迟。

A/B 固定同机器、OS、同一有线设备、采样率/格式、gain、声学输入、负载；云端对照固定 endpoint/model/prompt/网络/endpointing。Bluetooth 单独报告。以可重复 fixture、固定 utterance、环回/声学录音和足够长压力运行支持尾分位数；记录版本和配置使他人可复现。

## 7. 实施切片和验收

| 切片 | 可审阅交付 | 验收 |
| --- | --- | --- |
| 2A baseline 与接口 | 独立 voice_core 目标、fake device/transport、格式/state/epoch 契约、旧原型基线记录、供应商双链路协议调查 | 不接产品；partial startup/stop/restart fake 测试可重复，原 desktop/browser 行为保持 |
| 2B 同设备 callback 实验 | PortAudio 与 Qt 6.11 callback adapter、预分配 ring、同一 loopback fixture、CSV/JSON 指标报告 | owner/callback 无危险操作；两后端公平数据、underrun/CPU/尾延迟，提交组件建议供审阅 |
| 2C provider 与认证 relay | 单 I/O owner、协议 fixture/限长、认证/所有权/预算、bounded queue、真实 handshake 实验 | key 不下发；拒绝未授权/超预算；ACK 后 ready；断网/背压/关闭有界且无 stale replay |
| 2D 持续录音与打断 | epoch、持续 VAD/packetization、流式 decode/playout、本地及服务端取消 | 耳机下插话可复现；断网/取消/旧包晚到不会重播；实际 cancel-to-silence 和质量记录 |
| 2E desktop P1 集成 | NativeAudioBridge、native-bridge.js、有限状态 UI、完整转写/录音回传 | 桌面 P1 完整一轮和报告；web 回归；退出/profile 顺序不变；rapid stop/start 和渲染重载可恢复 |
| 2F 外放与长稳 | 若需要，再接 APM、设备变更、长会话/CPU/网络 stress | 双讲不误触发、AEC quality 和延迟数据；设备拔插/鉴权过期明确恢复或结束 |

合并每片前运行相关 native/desktop/browser/Django 检查。native 契约用 fake transport 验证；ASan/UBSan/TSan 分别检查内存、生命周期和线程；性能构建与 sanitizer 构建分开。现有构造/空会话单测继续保留，但不能代表真实设备/provider/full-duplex 验收。

## 8. 模拟面试后端建议

同一 Django 服务新建 `apps.interview`：独立 InterviewSession/Turn/Report、resume/JD/question provenance 和 technical rubric。复用 `apps.ai` provider/AITask/计费/账号以及证明需要后的媒体 primitives；报告复用版式组件。`apps.speaking` 的 IELTS band、Band 7、学习调度和 FC/LR/GRA/P 仍归 IELTS，不套面试 schema。不是新增微服务，不先大规模抽象现有 speaking services。

这是架构建议，面试实现和交互仍在阶段 4 审阅。VPS 在本地 P1/面试效果和成本验证之后再决定；此次不购置、不部署。

## 9. 尚待实验证实

- PortAudio 与 Qt 6.11 callback 的真实设备表现；最终库/版本、许可证和打包成本。
- 供应商原生全双工协议、独立鉴权和 session/cancel 行为；临时受限凭证能否实际申请和使用。
- 本地缓冲/取消目标是否在设备上可达；relay 增加的网络成本；AEC 质量。
- 当前计划未证明工业水准；有同条件实测结果后才能讨论相对哪个基线领先。
