# Writing Task 1 Image Prompt

## Goal

为 IELTS Writing Task 1 Academic 添加图表显示功能，让用户在答题时能看到题目配图（图表、流程图、地图等），符合真实 IELTS Task 1 考试场景。

## What I Already Know

从代码审查发现：

* **当前写作面板结构**（`web/static/index.html:173-222`）：
  - Task 1/Task 2 切换按钮（`data-writing-task="task1_academic"` / `"task2"`）
  - 题目选择下拉框 + 随机换题按钮
  - 题目卡片显示区域（`.writing-prompt-card`）：包含 pill 标签、标题、正文
  - 答题文本框（`#writingAnswer`）
  - 右侧签到统计和评分结果区域

* **前端逻辑**（`web/static/app.js`）：
  - `loadWriting()` 加载写作面板（line 1367）
  - `loadWritingPrompts(taskType)` 加载题库（line 1385）
  - `state.writing.taskType` 存储当前任务类型（`"task1_academic"` 或 `"task2"`）
  - Task 1 显示为 "Task 1 Academic"，Task 2 显示为 "Task 2"（line 1364）

* **后端 API**（推测）：
  - 应该有 `/api/writing/prompts/` 或类似 endpoint 返回题库
  - 需要确认 Task 1 题目数据结构是否已包含图片字段

* **真实 IELTS Task 1 场景**：
  - Academic Task 1 要求描述图表（bar chart, line graph, pie chart, table, diagram, map, process）
  - 图表是题目核心，必须显示
  - 通常 150 字，20 分钟

## Assumptions (Temporary)

* 后端题库已有或可以添加图片 URL 字段（需验证）
* 图片存储在 `/media/writing/` 或类似路径
* Task 2 不需要图片（opinion essay）
* 图片格式为常见 web 格式（PNG/JPG/SVG）

## Open Questions

1. **后端题库结构** - Task 1 题目数据是否已包含图片字段？如果没有，字段名应该叫什么？
2. **图片存储位置** - 图片文件存放在哪里？URL 格式是什么？
3. **图片显示位置** - 图片应该显示在题目文字上方、下方，还是单独一列？
4. **图片尺寸** - 是否需要支持点击放大查看？
5. **降级处理** - 如果图片加载失败或不存在，如何处理？

## Requirements (Evolving)

* [ ] Task 1 题目卡片显示图片（如果题目包含图片 URL）
* [ ] 图片位置合理，不遮挡题目文字
* [ ] Task 2 不显示图片区域
* [ ] 图片加载失败时有降级处理（占位符或隐藏）

## Acceptance Criteria (Evolving)

* [ ] 切换到 Task 1 时，如果题目有图片，图片正确显示
* [ ] 切换到 Task 2 时，图片区域不显示
* [ ] 图片加载失败时不影响题目文字显示
* [ ] 移动端图片自适应宽度

## Definition of Done

* 前端代码更新（HTML/CSS/JS）
* 后端 API 调整（如需要）
* 测试 Task 1/Task 2 切换
* 测试图片加载成功/失败场景
* 移动端响应式验证

## Out of Scope (Explicit)

* 图片编辑或标注功能
* 图片上传功能（题库管理不在此任务范围）
* 图片缩放/全屏查看（可作为后续优化）

## Technical Notes

* 需要先检查后端 API 返回的题目数据结构
* 可能需要更新 Django model 添加 `image_url` 字段
* 前端需要在 `.writing-prompt-card` 内添加 `<img>` 元素
* CSS 需要处理图片容器样式和响应式布局
