# Remove incorrect browser TTS fallback from speaking turns

## Goal

回滚 commit `6ef8976` 中误加的浏览器 TTS fallback 逻辑，恢复原来的服务端 TTS 专用行为。

## Root Cause

在 `6ef8976` 中，我误以为 `audio_url: None` 是 TTS 失败，添加了浏览器 `speechSynthesis` fallback。实际上 `audio_url: None` 是正常的 pending 状态，应由后端 AI worker 异步生成音频，前端应静默等待或 polling 刷新，不应显示浏览器 TTS 按钮。

## Requirements

- 移除 `renderExaminerAudio()` 中的浏览器 TTS fallback 逻辑
- 恢复原来的行为：只在 `tts.audio_url` 存在时显示音频播放器，否则隐藏
- 保留 `#browserTtsFallback` 按钮的 HTML 结构（可能有其他用途），但不在 speaking turns 中使用
- 不影响 writing Task1 图片功能

## Acceptance Criteria

- [ ] `renderExaminerAudio()` 恢复到 `6ef8976^` 的逻辑
- [ ] Speaking turns 不显示浏览器 TTS 按钮
- [ ] 全量测试通过

## Out of Scope

- 后端 TTS 生成逻辑优化
- Polling 机制改进
