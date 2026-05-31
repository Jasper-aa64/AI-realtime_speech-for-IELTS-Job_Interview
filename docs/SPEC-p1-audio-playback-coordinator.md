# P1 语音撕裂 —— 精确根因 + 改法（指挥已定位到行）

> 给 Codex。**追问无语音已修复，现在只剩"语音撕裂/中间断一段"。**
> 指挥已读代码定位真正根因——**不是状态机竞态**（别再改 playbackId/transaction，那是错的层）。

## 真正根因：流式 TTS 用 readyState 3 抢跑，缓冲欠载

代码链（web/static/app.js）：
1. `resolveExaminerAudioPlaybackUrl()`（~1945）直接返回 `/api/tts-audio/examiner/...` 流式 TTS URL。
2. `prepareExaminerAudioElement()`（~1931）`audio.src = 流式URL; audio.load()`。
3. `playExaminerTurn` 里 `waitForAudioReady(audio, { targetReadyState: isFixedAudio ? 4 : 3 })`（~2360-2364）。
4. **第一题"What is your full name?"是 `FIXED_EXAMINER_AUDIO_URLS`（~2334）→ readyState 4（整段就绪）→ 不撕裂。**
5. **其他题是动态 TTS → readyState 3（HAVE_FUTURE_DATA，只要有一点未来数据就开播）→ 播放速度追上服务端 TTS 边生成边传的速度 → 缓冲断流 → 撕裂/中间断一段。**

**结论：动态 TTS 题用 readyState 3 开播 = 抢在音频生成完之前播，缓冲欠载导致撕裂。第一题固定音频用 readyState 4 等整段，所以唯独它流畅。**

这解释了全部现象：① 只有第一题不撕裂 ② Codex 改 transaction/playbackId 全无效（根本不是竞态）③ "中间断一段"正是缓冲欠载的典型表现。

## 改法（低风险，二选一，推荐 A）

### 方案 A（最简，推荐）：动态 TTS 也等整段就绪
- 把 `waitForAudioReady` 的 `targetReadyState` 对**所有**考官音频都用 **4**（HAVE_ENOUGH_DATA），
  不再区分 `isFixedAudio ? 4 : 3`。
- 配合：`waitForAudioReady` 的 timeout 对动态 TTS 给足够大值（动态 TTS 整段生成可能要几秒），
  超时后再降级播放（而不是一开始就 readyState 3 抢跑）。
- 这样播放只在整段音频缓冲就绪后开始，缓冲不会欠载，撕裂消失。

### 方案 B（更稳但稍重）：等服务端 TTS 整段生成完，给非流式 URL
- 让 `/api/tts-audio/examiner/` 在整段 TTS 生成完成后再返回完整音频（或前端先 fetch 成 blob、
  再 `URL.createObjectURL` 给 audio.src），彻底避免边生成边播。
- 代码里已有 `examinerAudioBlobUrls` / `clearExaminerAudioPreloads` 的 blob 机制痕迹（~1962），
  可复用：fetch 整段 → blob URL → audio.src，播放源是本地完整 blob，绝不欠载。

## 验收（演示底线，真人验）
- [ ] P1 第 2 题起每题考官语音**完整、连续、无撕裂、无中间断**。
- [ ] 第 1 题（固定音频）仍正常。
- [ ] 追问题（动态 TTS）也连续无撕裂。
- [ ] 起播延迟可接受（等整段就绪带来的延迟在 1-2s 内；若太久用方案 B 的 blob 预取）。
- [ ] `node --check web/static/app.js` 通过。
- [ ] **真麦克风真人跑完整 P1**（headless 假麦验不了音频播放体感）。

## 红线
- **不要再改 playbackId / playbackKey / transaction 状态机** —— 那不是撕裂的原因，改它纯属浪费且会引入"追问无语音"那类新 bug。
- 只动"音频何时开播 / 播放源是否完整"这一层（waitForAudioReady targetReadyState 或 blob 预取）。
- 不动 examiner-tts 后端协议（除非选方案 B 需要后端配合，那要单独说明）。
- 一刀做完即停，真人验，再报。

## 给 Codex 的话
你之前改 transaction 校验全无效，因为撕裂根本不是竞态——是流式音频 readyState 3 抢跑、缓冲欠载。
证据：唯独第一题（固定音频 readyState 4）不撕裂。把动态 TTS 也提到 readyState 4 / 或 blob 整段预取，撕裂就消失。先试方案 A 一行改动，真人验；不够再上方案 B。
