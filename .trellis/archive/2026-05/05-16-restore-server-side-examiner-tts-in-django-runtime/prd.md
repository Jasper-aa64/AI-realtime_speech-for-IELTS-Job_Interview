# Restore server side examiner TTS in Django runtime

## Goal

恢复旧 server 的服务端 TTS 行为，让 Django 在创建 attempt/turn 时生成 `examiner_tts.audio_url`，前端自然播放服务端音频。

## Root Cause

Django 后端没有迁移旧 server 的服务端 TTS 生成链路：
- 当前 Django `_create_turn()` 写死 `"examiner_tts": {"provider": "volcengine", "status": "pending", "audio_url": None}`
- 旧 server 有 `volcengine_tts()` 和 `ensure_examiner_tts()` 在 start attempt 和 next turn 时生成音频
- 旧 server 有 `/api/tts-audio/{role}/{filename}` 音频读取路由

## Requirements

### 1. 迁移 TTS 生成函数
从 `web/ielts_server.py` 迁移到 Django:
- `volcengine_tts()` - 调用 VolcEngine API 生成音频，缓存到 media/tts/examiner/
- `ensure_examiner_tts()` - 确保 turn 有 examiner_tts.audio_url
- 音频文件路径: `media/tts/examiner/{cache_key}.mp3`
- Cache key: `{attempt_id}_{turn_id}_examiner`

### 2. 接入 Django speaking runtime
在以下位置调用 TTS 生成:
- `POST /api/attempts/start` - 创建首个 turn 后生成 examiner TTS
- `POST /api/attempts/{id}/turns/{id}/complete` - 返回 next_turn 前生成 examiner TTS
- P2 cue card instruction 也要生成对应 examiner_text 的 TTS

### 3. 音频读取路由
确认或补齐:
- `GET /api/tts-audio/examiner/{filename}` - 读取 media/tts/examiner/{filename}
- `GET /api/tts-audio/model/{filename}` - 读取 media/tts/model/{filename} (如旧报告需要)

### 4. 缓存策略
- 相同 cache_key 复用已有音频文件
- 音频存到 `MEDIA_ROOT/tts/examiner/` 或 `MEDIA_ROOT/tts/model/`

### 5. 失败降级
- VolcEngine 请求失败时返回 `{"provider": "browser", "status": "fallback", "audio_url": None, "message": "..."}`
- 环境变量 `IELTS_WEB_DISABLE_VOLCENGINE_TTS=1` 时直接返回 browser fallback
- 不要伪装成正常服务端 TTS 成功

### 6. 前端保持不变
- 不修改前端音频播放逻辑
- 不添加浏览器 TTS fallback UI

## Acceptance Criteria

- [ ] start attempt 返回的 first turn 里 `examiner_tts.audio_url` 有值 (非 None)
- [ ] complete turn 返回的 next_turn 里 `examiner_tts.audio_url` 有值
- [ ] P2 cue card instruction 的 examiner_tts.audio_url 有值
- [ ] 音频 URL 格式: `/api/tts-audio/examiner/{filename}.mp3`
- [ ] 音频文件实际存在于 media/tts/examiner/
- [ ] 相同 cache_key 复用已有音频
- [ ] VolcEngine 不可用时 provider 为 "browser", audio_url 为 None
- [ ] 前端 examiner audio 元素能播放该 URL
- [ ] Speaking tests 通过
- [ ] Full Django tests 通过
- [ ] JS syntax check 通过

## Out of Scope

- 前端 UI 改动
- 浏览器 TTS fallback UI
- 其他 TTS provider (OpenAI, Azure)
