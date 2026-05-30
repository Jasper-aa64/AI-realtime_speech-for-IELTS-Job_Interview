# Diagnose Speaking Dynamic TTS Playback Stalls

## Goal

修复本地口语练习中除第一段固定预热音频外，后续动态追问/题目音频播放卡顿的问题。

## Known Symptoms

- 第一段固定题目音频较顺，因为固定 TTS 已提前 warm。
- 后续 dynamic follow-up / examiner TTS 会在保存上一题后才生成、轮询、预热。
- 日志中疑似出现同一 `turn_id` 的 `/examiner-tts` 重复请求、同一 mp3 重复请求，以及录音阶段重复请求 WASM/audio worklet。

## Requirements

- 动态 TTS refresh/polling 对同一 turn 必须单例化。
- 同一 audio URL 不应重复预热。
- 已完成的 dynamic TTS 结果应缓存到 turn，后续渲染不再重复请求。
- 不改变题目流程和评分逻辑。
- 保持服务端 TTS 优先，不恢复 browser TTS。

## Acceptance Criteria

- [x] `node --check web/static/app.js` 通过。
- [x] `node --check web/static/wasm/audio_analyzer.js` 通过。
- [x] `node --check web/static/wasm/speaking_audio_preprocessor.js` 通过。
- [x] `manage.py check` 通过。
- [x] 本地 `/`、`/app.js`、`/wasm/audio_analyzer.js` smoke 加载正常。
- [x] 代码中同一 turn 的 dynamic examiner TTS 请求有 in-flight guard。
- [x] 同一 `audio_url` 播放时复用预加载 `Audio`，不再同时驱动 hidden `<audio>` 和 preload 双加载。

## Out of Scope

- 不改 AI 追问 prompt。
- 不改 TTS provider。
- 不改 WASM audio core 实现。
