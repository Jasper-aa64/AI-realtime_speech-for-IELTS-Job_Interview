# Goal 规格：流式考官追问 Phase 2 —— realtime ASR 接入 + 首字延迟实测闭环

> 大 goal 第二阶段。给实现方（Codex）。用户负责 review + 验收 + ASR 端点细节。
> Phase 1（SSE 流式追问 + TTS pipeline）代码已闭环；本阶段在其上接 realtime ASR，
> 并补上 Phase 1 欠的「首字延迟实测」，让整条「真考官追问」链路端到端可验。
>
> **ASR 端点 URL / 鉴权 / 流式协议细节由用户与 Codex 实现时确定，本规格不写死。**
> 指挥只定目标、边界、验收。

## 背景（已是事实）

- Phase 1 已交付：`HttpApiProvider.stream_tokens()`、SSE endpoint
  `GET /api/attempts/{id}/turns/{turn_id}/follow-up-stream`、`stream_pending`、前端
  `fetch+ReadableStream` 消费、TTS pipeline、fallback 事件。commit `9f9cdfc/15a53d9/20aff63`。
- 当前链路仍是「录完上传 → ASR → LLM 追问(流式) → TTS」。Phase 2 把 ASR 段从
  「说完才有输入」升级为「边说边有输入」。
- C++ 工程里 `realtime_client.cpp` / `protocol.cpp` 是 openspeech 实时语音的现成参考。

## Phase 2 目标

1. **realtime ASR 接入**：把口语录音从「整段上传后转写」升级为「边说边转写」，转写文字
   实时回前端（边说边出字）。ASR 源 = openspeech（或用户实现时确定的端点），流式输出。
2. **端到端首字闭环**：用户停止说话 → 考官追问首字尽快出现（LLM 首 token → TTS 首段并行）。
3. **补 Phase 1 欠账**：实测「用户停说 → 追问首字出现」延迟（Chrome DevTools），并演示 fallback。

## 范围（建议分阶段，每段独立可验）

> ASR 集成是大工程，务必拆小步、每步独立可跑、可回滚。

- **2.1 ASR 通道打通**：浏览器采音 → 流式送 ASR → 实时转写文字回前端显示（边说边出字）。
  这一步只验「转写实时性」，先不接 LLM 追问。
- **2.2 链路串联**：实时转写 → 触发 Phase 1 的流式追问 SSE → TTS pipeline。整条打通。
- **2.3 首字延迟实测**：DevTools 量「停说→追问首字」端到端延迟，出数字 + 截图。
- **2.4 降级验证**：ASR 失败 → 回落到现有「录完上传批处理」流程，录音链路不中断。

## 红线 / 边界

- **baseline 不破**：现有「录完上传 → 报告」流程必须保留为 fallback；realtime 是叠加的加速层，
  失败必须无缝回落，绝不让口语主流程中断。
- **ASR key / 鉴权绝不进代码、日志、git**；全走环境变量。
- fallback / 降级必带明确标记，不伪造成功。
- 现有测试全绿，不为通过改测试逻辑。
- 不夹带工作区现有 WIP 脏文件；分步独立提交。
- 部署形态若引入常驻服务（C++ gateway / ASGI），需说明 Linux 部署方式，但**本 goal 不要求
  一次做到生产部署**——先本地端到端跑通。

## 验收标准（用户验收用）

- [ ] 边说边出字：浏览器实测，说话时转写文字实时滚动出现。
- [ ] 端到端首字延迟实测：DevTools 量「停说→追问首字」，给数字 + 截图（补 Phase 1 欠账）。
- [ ] 降级可演示：ASR 中断 → 回落批处理，录音不中断。
- [ ] 全量 `manage.py test` 全绿；`manage.py check` 通过。
- [ ] ASR 凭据走环境变量，未入库。
- [ ] 分步提交（2.1/2.2/2.3/2.4 各自 commit），CHANGES 记录每步结果 + 首字延迟数字。

## 不做

- 不做发音评测（音素级评分，独立 backlog）。
- 不做「能打断」全双工（考官打断学生）——本 goal 是「学生说完，考官秒接」，不是双向打断。
- 不要求生产级 Linux 部署一步到位（先本地端到端）。
