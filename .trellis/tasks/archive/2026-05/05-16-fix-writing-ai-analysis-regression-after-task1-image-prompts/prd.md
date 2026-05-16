# Fix writing AI analysis regression after task1 image prompts

## Goal

恢复写作页 AI 分析/AI 评分与辅导完整功能，同时保留 Task1 图片展示与后端 image_url 数据结构扩展。

## Root Cause

1. `web/static/app.js` 的 textarea 自动扩展逻辑将编辑区高度无限拉伸，某些窗口尺寸下导致右侧 `writing-result-card`（包含 AI 评分按钮、inline wait、状态）被挤压到可视区外，用户感知为“AI 分析消失”。
2. 写作入口受登录保护（既有逻辑），未登录时直接跳登录，如果未明确提示也会被误判为写作 AI 功能失效。

## Requirements

- 保留 Task1 image_url 后端能力和前端渲染。
- 恢复并确保 AI 评分按钮、AI 评分任务创建、polling、报告渲染全链路可用。
- textarea 改为“外层页面滚动可达 + 控制最大扩展高度”，避免挤压右侧 AI 面板。
- 保持 Task2 无图。
- 不回滚整包 commit，只做最小回归修复。

## Acceptance Criteria

- [ ] Task1 有图时显示图片；无图时不报错。
- [ ] Task2 不显示图片区域。
- [ ] 写作页始终可见 AI 保存/评分控件。
- [ ] score-task 创建与 polling 正常。
- [ ] 写作报告列表/detail 仍正常。
- [ ] 全量测试与 check 通过。

## Out of Scope

- 图片上传系统
- 新增评分模型逻辑
