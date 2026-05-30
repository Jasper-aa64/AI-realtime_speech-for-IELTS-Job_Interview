# Fix Second Fixed Examiner TTS Playback Stutter

## Goal

修复口语 P1 第二个固定 examiner 题目 `Do you work or do you study?` 播放时中途稳定卡顿的问题，保持固定 TTS 预热收益。

## Known Facts

- `What is your full name?` 播放正常。
- `Do you work or do you study?` 不是生成式追问，是固定 examiner TTS。
- 当前前端会预热固定 examiner 音频。
- `stopExaminerPlayback()` 会在每个 examiner 阶段开始时暂停并重置所有 preload cache 中的音频。

## Requirements

- 不改变题目流程、后端 TTS provider、追问逻辑或评分逻辑。
- 已预加载的非当前播放音频不能被普通 phase stop 打断。
- 退出练习、重置页面时仍然可以清理动态音频缓存。

## Acceptance Criteria

- [x] `node --check web/static/app.js` 通过。
- [x] `manage.py check` 通过。
- [x] 普通 `stopExaminerPlayback()` 只停止当前活动播放对象，不重置全部 preload cache。
- [x] `clearExaminerAudioPreloads()` 仍负责退出/重置时清理动态缓存。

## Out of Scope

- 不改 TTS 供应商。
- 不改 browser TTS fallback。
- 不改 WASM audio core。
