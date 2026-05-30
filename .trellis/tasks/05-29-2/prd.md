# 实验2 设计模式与接口设计（仅设计，不实现）

> 任务类型：**纯设计任务**。产出 = 接口设计 + 类图 + PRD + 实现计划。
> **不改任何业务代码，不进入代码实现。** 后续实现由用户确认后再单独开任务。
> 角色：用户负责设计决策、指挥、最终验收；本任务只产出设计制品。

## 0. 最高原则：现有浏览器产品是 baseline，不推倒重来

**定位一句话**：在现有 IELTS Web 产品基础上，通过抽象 `AIProvider` / `ASRProvider` /
`FallbackPipeline` / `AudioProcessor` 等接口，引入可扩展的实时语音与音频预处理能力。
**现有浏览器交互和批处理流程保持不变**，新链路作为增量优化和降级可选路径接入。

```text
当前成熟功能 = baseline（不改产品设计）
C++ / WASM / 实时链路 = acceleration layer（增量增强）
旧批处理流程 = fallback（实时失败即回落）
```

**baseline（保留、不重写、不改产品逻辑）**：
P1/P2/P3/Mock 练习流程、每日写作、写作报告、口语报告、语料库、Takeaway、
账号/钱包/题库弹窗、现有浏览器录音 + 上传 + 报告生成流程。

**具体原则**：
1. 不大改功能设计——不重新设计 P1/P2/P3/写作/报告的产品逻辑。
2. 不替换现有浏览器流程——现在能跑的录音/上传/报告流程继续保留。
3. C++ 只进入性能瓶颈点——优先只碰音频预处理、实时转写网关、协议层。
4. 所有新链路都要可降级——实时失败就回到现有批处理。
5. 作业叙事写「重构与扩展」，不是「重做一个系统」——在成熟系统上引入可扩展架构。

> 这条原则不动摇本任务的接口/类图设计，只是明确：这些抽象是**叠加在现有产品之上的
> 加速层与可选实时能力**，而非替换现有功能。下文所有「设计」均在此前提下理解。

## 1. 背景

在**保留现有成熟浏览器产品功能设计不变**的前提下，把 IELTS Web 产品「MVP + 补丁」的
内部实现重构为职责清晰、可测试、可部署的架构，并把 6000+ 行 C++/Qt 面试系统的能力
作为**增量加速层**（音频预处理 / 实时转写 / 协议层）叠加进来。
总纲见 `软件构造/重构总体架构.md`，模式细节见 `软件构造/实验2_设计文档.md`。

实验2 对应课程「利用模式设计进行类设计并编程实现」，本仓库将其**拆为两步**：
- 本任务（05-29-2）：只做设计——接口、类图、PRD、实现计划。
- 后续任务（待用户确认后建）：按本设计落地 Python 侧可运行重构 + C++ 接口头文件。

## 2. 范围（严格限定）

### Python 侧（`backend_django/apps/ai/`，本任务只设计不实现）
- `AIProvider`：Strategy 接口（`run(task) -> ProviderRunResult`）。
- `ASRProvider`：Strategy 接口（可切换 ASR 源；设计层，与 C++ 呼应）。
- `FallbackPipeline`：责任链（主 provider 失败 → 备 → 明确标记 fallback；实时 → 批处理兜底）。
- `ReportPipeline`：Template Method（评分/报告流程骨架 + 钩子）。
- 配套：`HttpApiProvider`（修延迟，流式直连）、`CodexProvider`、`MockSuccessProvider`、
  `FallbackProvider`、`ProviderChain`、`ProviderRunResult`、`ProviderRoute` 的设计定位。

### C++ 侧（`src/` + `include/`，本任务只设计接口与类图）
- `AudioProcessor`：纯算法核接口（VAD/裁剪/重采样/归一化/质检，无 IO）。
- `RealtimeGateway`：Adapter（适配 openspeech 二进制协议）。
- `ProtocolAdapter`：二进制帧编解码接口（复用 `protocol.cpp` 设计）。
- 说明 `Scorer` 的现成 `ScorerBackend` 多后端是 C++ 里现成的 Strategy 实例（跨语言呼应）。

### 设计要覆盖的四个模式
Strategy / Adapter / Chain of Responsibility / Template Method —— 每个给出意图、现状坏味道、
重构后类结构、类图。Python 与 C++ 双侧体现「同一模式、两种语言」。

## 3. 明确不做（边界）

- 不改 `apps/ai/*.py`、`apps/speaking/services.py`、`apps/writing/services.py` 等业务代码。
- 不写 C++ 实现，只产出头文件级接口与类图。
- 不动 `apps/ai/tests.py`（测试属实验3）。
- 不扩展 `web/ielts_server.py`（已 deprecated）。
- 不做 audio_core 抽核实现（属实验4）、不做 WASM/开源库集成（属实验5）。

## 4. 交付物（本任务完成的定义）

1. `软件构造/实验2_设计文档.md`（已存在，作为主设计稿，按需补 ASRProvider/ReportPipeline/ProtocolAdapter）。
2. 类图：Python 侧 + C++ 侧（PlantUML 文本或等价，可直接进实验报告）。
3. 实现计划：后续实现任务的步骤拆解（与本 PRD §6 实现路径对齐）。
4. 本 PRD（任务边界与验收标准）。

## 5. 长期目标（上下文，不在本任务实现）

C++ 路线：`audio_core 抽核 → WASM(Emscripten) → realtime gateway → Django 双链路`。
第一锤最终是 audio_core 抽核，但**本步只立设计任务，不抽核**。
实验5 必须集成真开源库（WebRTC VAD / SpeexDSP / libsamplerate），工具链不算复用。

## 6. 实现路径（供后续任务参考，本任务不执行）

① audio_core 抽核 → ② GTest → ③ WASM demo → ④ realtime gateway → ⑤ Django realtime/fallback 双链路。
报告顺序 2→3→4→5；实现允许实验2 抽象与实验4 的 C++ 抽核轻度并行。

## 7. 红线与卫生

- follow-up / 报告必须真调用 AI；fallback 必带 metadata 标记，不得伪装 AI 成功；不加内容拦截器。
- `backend_django/db.sqlite3`：**用户确认这是测试用户库，允许被 git 追踪**（保持现状，不 `git rm --cached`）。MEMORY 里「不提交 db.sqlite3」的旧约束以此为准更新。
- 不随意 reset/checkout；不为 Web bug 改 C++（除架构明确要求）。
- 远程：`jasper` → https://github.com/Jasper-aa64/AI_Project.git（非 origin）。

## 8. 验收标准

- [ ] 四个模式的设计在文档中完整、可对照现有代码（before/after 真实）。
- [ ] Python 侧四个抽象（AIProvider/ASRProvider/FallbackPipeline/ReportPipeline）接口签名明确。
- [ ] C++ 侧三个接口（AudioProcessor/RealtimeGateway/ProtocolAdapter）头文件级定义 + 类图。
- [ ] 实现计划可直接转成后续实现任务。
- [ ] 全程零业务代码改动；现有测试不受影响。
