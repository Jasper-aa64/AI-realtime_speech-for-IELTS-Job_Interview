# Goal 规格：流式考官追问 Phase 1（SSE 逐字 + TTS pipeline）

> 给实现方（Codex）。用户负责 review + 验收；本规格定目标、范围、技术路线、验收标准、红线。
> 这是「真考官式追问」大 goal 的 Phase 1——不需要 realtime ASR，只改 LLM→前端 + TTS pipeline。
> Phase 2（realtime ASR）在本 Phase 稳定后独立推进。

## 0. 为什么做 + 预期效果

**现状**：用户停止说话 → 全黑盒等待约 4.66s → 考官文字和音频一起出现。
**目标**：用户停止说话 → 首字 < 1s 出现 → 追问文字逐字滚动 → 文字完整时考官音频同步响起。

体验从「等机器」变成「考官在思考并开口」。

## 1. 技术路线（已确认可行，基于代码现状）

- Django 已有 `asgi.py`，`StreamingHttpResponse` 在 WSGI 也可用。
- `HttpApiProvider.complete_chat()` 内部已 `stream=True`，但目前收集完再返回。
  **需要新增一个 `stream_tokens()` 生成器方法**，逐 chunk yield 给调用方。
- `quick_follow_up_runner`（services.py line 970）目前用 `complete_chat()`，改成消费流式生成器。
- 新增 SSE endpoint，frontend 用 `fetch` + `ReadableStream` 消费（不用 `EventSource`，因为要 POST）。
- TTS 触发：后端检测到完整问句（含 `?`）时，在 SSE 流里发 `{"event":"question_complete","text":"..."}` 事件，
  同时**后台异步触发 TTS 生成**；TTS 就绪后再发 `{"event":"tts_ready","audio_url":"..."}` 事件。
  前端收到 `question_complete` 立刻显示完整追问；收到 `tts_ready` 立刻播放。

## 2. 后端改动

### 2.1 `HttpApiProvider` 新增 `stream_tokens()` 生成器

```python
def stream_tokens(self, messages, *, temperature, max_tokens, timeout_seconds=None) -> Iterator[str]:
    """Yield text chunks as they arrive from the streaming API. Raises HttpApiProviderError on failure."""
    # 复用现有 urllib 逻辑，但 yield chunk 而非 accumulate
    # 每解析一个 SSE data 行，yield 其中的 delta.content（非空时）
```

### 2.2 新 SSE endpoint

```
GET /api/attempts/{attempt_id}/turns/{turn_id}/follow-up-stream
```

- 认证：登录用户，同现有 speaking views。
- 从 DB 读 turn（transcript、question、part、focus），校验合法性。
- 调用 `HttpApiProvider.stream_tokens()` 流式生成追问。
- 用 `StreamingHttpResponse(generator(), content_type="text/event-stream")` 返回，
  加 header `X-Accel-Buffering: no`、`Cache-Control: no-cache`。
- SSE 事件格式（每行 `data: <json>\n\n`）：

```
data: {"event":"chunk","text":"Can"}\n\n
data: {"event":"chunk","text":" you"}\n\n
data: {"event":"chunk","text":" elaborate"}\n\n
...
data: {"event":"question_complete","text":"Can you elaborate on that?"}\n\n
data: {"event":"tts_ready","audio_url":"/api/tts-audio/..."}\n\n   <- 异步等 TTS 就绪后发
data: {"event":"done"}\n\n
```

- TTS 触发：完整问句（检测到 `?` 或生成完毕）→ 后台线程调现有 `ensure_examiner_tts` 逻辑 →
  TTS 就绪后通过 queue/event 通知 SSE generator 发 `tts_ready` 事件。
  **不要等 TTS 才关闭 SSE 流**——发完 `question_complete` 后前端已可显示文字；
  `tts_ready` 可以在 `done` 之后延迟到达（但要在合理超时内，如 8s，否则发 `tts_timeout`）。

- **fallback**：若 `HttpApiProvider` 不可用/失败 → 发 `{"event":"fallback","text":"<完整追问>"}`，
  前端收到后走现有批处理路径。**绝不静默失败。**

### 2.3 `complete_turn` 保持不变

`turn_complete_view` / `complete_turn` 的现有逻辑**不动**——它仍处理录音上传、转写、保存、
基本追问（非流式路径）。流式追问是**额外的可选增强 endpoint**，不替换现有路径。
前端可以先调现有 `turn_complete` 完成核心保存，再调 `follow-up-stream` 获取流式追问。

## 3. 前端改动

### 3.1 追问显示区域

在考官追问显示区域加「逐字显示」动效：
- 收到第一个 `chunk` 事件 → 清除「考官正在思考...」状态，开始追加文字
- 收到 `question_complete` → 文字完整，停止滚动动效
- 收到 `tts_ready` → 立刻触发音频播放
- 收到 `fallback` → 静默切换为现有批处理显示逻辑（用户感知不到降级）
- 收到 `tts_timeout` / 连接中断 → 继续显示文字，音频标记为「暂时不可用」

### 3.2 实现方式

用 `fetch` + `response.body.getReader()` 消费 SSE（不用 `EventSource`，因为认证 header 无法用 EventSource 传）：

```js
const resp = await fetch(`/api/attempts/${attemptId}/turns/${turnId}/follow-up-stream`, {
  headers: { "X-CSRFToken": csrfToken }
});
const reader = resp.body.getReader();
// 逐 chunk 解析 SSE 行...
```

### 3.3 不改的部分

- 现有 `turn_complete_view` 调用不变
- 现有 TTS 播放逻辑（`examiner_tts.audio_url`）不变——流式路径的 `tts_ready` 复用同一套播放逻辑
- WASM 音频预处理逻辑不变
- P1 语料库、写作、报告等所有非口语路径不变

## 4. 验收标准

- [ ] 新 endpoint `/api/attempts/.../follow-up-stream` 返回 SSE，`Content-Type: text/event-stream`。
- [ ] 首个 `chunk` 事件在 LLM 首 token 到达后 < 200ms 内推出（可用 Chrome DevTools Network 确认）。
- [ ] 追问文字逐字出现，`question_complete` 时文字完整。
- [ ] `tts_ready` 事件到达时音频可播放（URL 有效，能触发 audio 播放）。
- [ ] `fallback` 路径可触发：断开 HTTP API key → endpoint 返回 `fallback` 事件，前端正常显示追问。
- [ ] `StreamingHttpResponse` 在 `manage.py runserver`（WSGI）下正常工作（不需要额外 ASGI 配置）。
- [ ] 全量 `python3 manage.py test` 全绿（现有测试不破坏）。
- [ ] 新增针对 `stream_tokens()` 的单元测试（mock HTTP response，验证 chunk yield 行为）。
- [ ] `git diff --check` 通过，无格式错误。
- [ ] 分步提交：`feat: add http provider stream_tokens generator` / `feat: add follow-up stream endpoint` /
  `feat: wire streaming follow-up in frontend`（各自独立可回滚）。

## 5. 红线

- **`turn_complete_view` 原有逻辑不动**——流式是增量路径，不是替换。批处理 fallback 必须可用。
- **API key 不进日志/代码**。
- **音频播放失败不能影响追问文字显示**——文字和音频是解耦的，TTS 失败只影响音频，不影响练习继续。
- 不改写作/口语报告/WASM 任何已闭环的逻辑。
- 不动 db.sqlite3，不夹带 app.js 模块化的改动（两条线分开）。

## 6. 与 Phase 2 的衔接

Phase 1 完成后，前端已有「接收流式追问、逐字显示、触发 TTS」的完整 pipeline。
Phase 2（realtime ASR）只需把「用户说完才触发」改成「ASR 实时输出 transcript → 立刻触发追问流」——
前端消费逻辑完全复用，改动集中在 ASR 接入侧。
