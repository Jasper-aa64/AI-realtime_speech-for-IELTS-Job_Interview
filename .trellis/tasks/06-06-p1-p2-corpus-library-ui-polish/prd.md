# P1/P2 Corpus Library UI Polish

## Goal

对 P1「短答语料库」和 P2「串题素材库」两个页面进行视觉/交互优化，
达到 Pro Max 级别观感——信息密度合理、层次清晰、操作可发现、视觉一致。

## What I Already Know

### 当前 P1 布局
- 头部 banner：`.p1-corpus-head` → kicker + h2 + description + stats pill
- 话题卡片 grid：`repeat(3, minmax(280px, 1fr))`，gap 16px
- 每卡：header(话题名 + 题数) + 内容区 + 底部操作

### 当前 P2 布局
- 头部 banner 同 P1 结构
- **分类卡片**（已改）：`repeat(3, minmax(0,1fr))`；5 分类 → 3+2 排列
  - 每分类卡：header(分类名 + 条数) + 素材行列表(title + P3状态) + 新增按钮
  - 最小高度 176px，素材行 minmax(70px, 1fr)
- **当季题卡** section：`repeat(auto-fit, minmax(340px, 1fr))`
  - 题卡有 kicker / title / cue lines / footer(正文 + P3 按钮)

### 刚刚修了
- `p2-corpus-dialog-card` 底部空白（多余 88px grid row 已删）
- P2 分类卡从 2 列改为 3 列

## Open Questions

1. 改动侧重哪一层？（见下方选项）

## Requirements (evolving)

- [x] P2 分类卡 3 列布局
- [x] P2 编辑弹窗底部空白消除
- [ ] 待确认的视觉/交互改进

## Acceptance Criteria (evolving)

- [ ] P1/P2 页面视觉一致、层次清晰
- [ ] `manage.py check` 通过（纯 CSS/JS 改动，无后端影响）
- [ ] Light/Dark 两个模式下都好看

## Out of Scope

- 功能性改动（新增 API、模型变更）
- 移动端专属布局（现有响应断点维持）

## Technical Notes

关键文件：
- `web/static/styles.css`（所有 P1/P2 corpus 样式，行 1199 / 4356-4940）
- `web/static/corpus-takeaway.js`（P2 分类卡 HTML 生成，renderP2CorpusTopics 函数，行 669）
- `web/static/index.html`（P1/P2 panel HTML，行 326-337 / 523-568）
