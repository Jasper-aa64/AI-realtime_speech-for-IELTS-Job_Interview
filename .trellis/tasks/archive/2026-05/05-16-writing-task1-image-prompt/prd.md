# Writing Task 1 Image Prompt + TTS Fallback Fix

## Goal

**Primary**: 为 IELTS Writing Task 1 Academic 添加图表显示功能，让用户在答题时能看到题目配图（图表、流程图、地图等），符合真实 IELTS Task 1 考试场景。

**Secondary**: 修复口语练习 TTS fallback 逻辑，当服务端 TTS `audio_url` 为 `None` 时显示浏览器 TTS 按钮，而不是静默失败。

## What I Already Know

### Writing Task 1 Image

* **后端模型**（`backend_django/apps/writing/models.py:6-27`）：
  - `WritingPrompt` 模型当前字段：`prompt_id`, `task_type`, `title`, `category`, `prompt`, `source`, `is_active`
  - **无 `image_url` 字段**，需要添加
  - `prompt_payload()` 序列化函数（`services.py:68`）需要扩展返回 `image_url`

* **前端写作面板**（`web/static/index.html:173-222`）：
  - `.writing-prompt-card` 显示题目标题和正文
  - `#writingAnswer` textarea 用于答题
  - Task 1/Task 2 切换按钮

* **前端逻辑**（`web/static/app.js`）：
  - `loadWritingPrompts(taskType)` 调用 `/api/writing/prompts?task_type=...`
  - `random_prompt()` 调用 `/api/writing/prompts/random`

### TTS Fallback Issue

* **后端 TTS**（`backend_django/apps/speaking/services.py:411,771`）：
  - `start_interview()` 和 `submit_turn()` 返回 `examiner_tts: {provider, status, audio_url}`
  - 当 TTS pending 时 `audio_url` 为 `None`

* **前端 TTS**（`web/static/app.js:704-710,798-810`）：
  - `renderTurn()` 检查 `turn.examiner_tts?.audio_url` 存在才播放
  - 不存在时不显示 `#browserTtsFallback` 按钮，导致用户无法听到 prompt

## Requirements

### Writing Task 1 Image

* [x] 后端 `WritingPrompt` 模型添加 `image_url` 字段（CharField, blank=True）
* [x] 生成 Django migration
* [x] `prompt_payload()` 序列化函数返回 `image_url`
* [x] 前端 HTML 在 `.writing-prompt-card` 内添加图片容器
* [x] 前端 JS 渲染 Task 1 题目时显示图片（如果 `image_url` 存在）
* [x] Task 2 题目不显示图片区域
* [x] CSS 样式：图片自适应宽度，最大高度限制，移动端响应式
* [x] 图片加载失败时隐藏图片容器，不影响题目文字
* [x] `#writingAnswer` textarea 改为自动扩展高度，不使用内部滚动条
* [x] 答题区字体改为正常阅读字体（非等宽字体）

### TTS Fallback Fix

* [x] 前端 `renderTurn()` 检查 `audio_url` 为 `None` 或空时显示 `#browserTtsFallback` 按钮
* [x] 按钮点击时使用 `window.speechSynthesis` 朗读 `turn.examiner_prompt`
* [x] 保持现有 TTS 优先级：服务端 audio > 浏览器 TTS

## Acceptance Criteria

### Writing Task 1 Image

* [ ] Migration 生成并通过 `makemigrations --check`
* [ ] `/api/writing/prompts` 返回包含 `image_url` 字段
* [ ] Task 1 题目有 `image_url` 时图片正确显示
* [ ] Task 1 题目无 `image_url` 时不显示图片区域
* [ ] Task 2 题目不显示图片区域
* [ ] 图片加载失败时不影响页面布局
* [ ] 移动端图片不溢出屏幕
* [ ] `#writingAnswer` textarea 高度自动扩展，无内部滚动条
* [ ] 答题区字体为正常阅读字体

### TTS Fallback Fix

* [ ] 服务端 TTS `audio_url` 为 `None` 时显示浏览器 TTS 按钮
* [ ] 点击按钮能正常朗读 examiner prompt
* [ ] 服务端 TTS 可用时优先使用服务端音频

## Definition of Done

* Django migration 生成并执行
* 后端测试通过（`apps.writing.tests`, `apps.speaking.tests`）
* 前端 JS 语法检查通过
* 全量测试通过（147 tests）
* Django system check 通过
* Business commit + archive + journal

## Out of Scope

* 图片上传功能（题库管理）
* 图片缩放/全屏查看
* 图片编辑或标注
* TTS 语速/音色调整

## Technical Approach

### Backend Changes

1. **WritingPrompt model** (`backend_django/apps/writing/models.py`):
   ```python
   image_url = models.CharField(max_length=500, blank=True, default="")
   ```

2. **prompt_payload()** (`backend_django/apps/writing/services.py:68`):
   ```python
   return {
       "id": prompt.prompt_id,
       "task_type": prompt.task_type,
       "title": prompt.title,
       "category": prompt.category,
       "prompt": prompt.prompt,
       "image_url": prompt.image_url,  # NEW
   }
   ```

3. **Migration**: `python manage.py makemigrations apps.writing`

### Frontend Changes

1. **HTML** (`web/static/index.html`):
   - 在 `.writing-prompt-card` 内添加 `<div id="writingPromptImage" class="writing-prompt-image hidden"></div>`

2. **JS** (`web/static/app.js`):
   - `loadWritingPrompts()` 渲染题目时检查 `image_url`，动态插入 `<img>`
   - `renderTurn()` 检查 `audio_url` 为空时显示 `#browserTtsFallback`
   - `#browserTtsFallback` 点击事件使用 `speechSynthesis.speak()`

3. **CSS** (`web/static/styles.css`):
   ```css
   .writing-prompt-image {
     margin: 16px 0;
     max-width: 100%;
   }
   .writing-prompt-image img {
     max-width: 100%;
     max-height: 400px;
     object-fit: contain;
   }
   .writing-answer {
     resize: vertical;
     min-height: 200px;
     overflow-y: hidden;
     font-family: inherit; /* 不使用等宽字体 */
   }
   ```

## Implementation Plan

1. Backend: 添加 `image_url` 字段，生成 migration，更新 `prompt_payload()`
2. Frontend: 更新 HTML/CSS/JS 支持图片显示和 TTS fallback
3. 验证：运行全量测试，检查 migration
4. Commit: business commit → archive → journal
