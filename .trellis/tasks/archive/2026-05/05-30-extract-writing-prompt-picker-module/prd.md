# Extract Writing Prompt Picker Module

## Goal

将每日写作题库弹窗的渲染、筛选、切换 Task、随机换题逻辑从 `web/static/app.js` 抽到独立模块，作为 app.js 模块化第三刀。

## Requirements

- 保持题库弹窗行为和 UI 不变。
- 保持 Task 1/Task 2 切换、来源筛选、类型筛选、随机题、Task 1 图片 eager/lazy 策略不变。
- 新模块仍使用当前单页全局状态，不引入构建工具。
- Django 需要能直接托管新静态模块。
- `index.html` 需要加载新模块并 bump app.js 版本避免缓存。

## Acceptance Criteria

- [x] picker 渲染/筛选/随机逻辑移入 `web/static/writing-prompt-picker.js`。
- [x] `app.js` 只保留薄包装/调用，不再承载 picker 主要渲染函数。
- [x] `index.html` 加载新模块。
- [x] Django URL surface 包含 `/writing-prompt-picker.js`。
- [x] `node --check web/static/writing-prompt-picker.js` 通过。
- [x] `node --check web/static/app.js` 通过。

## Out of Scope

- 不改写作题库数据。
- 不改题库弹窗样式。
- 不改写作评分/报告逻辑。
- 不继续拆 app.js 下一刀。
