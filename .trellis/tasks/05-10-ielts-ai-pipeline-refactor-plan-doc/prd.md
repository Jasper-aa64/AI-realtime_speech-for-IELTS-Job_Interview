# IELTS AI pipeline refactor plan doc

## Goal

新增一份面向后续统一改造的中文需求/实施计划文档，记录 IELTS Speaking AI 生成、评分、Band 7 版本、AI 辅导与后台预生成链路的统一重构要求。

## Requirements

- 不修改业务代码，不提交 git commit。
- 先检查现有 `docs/` 与 `.trellis/tasks/` 中是否已有合适文档。
- 优先新增 `docs/IELTS_AI_PIPELINE_REFACTOR_PLAN.md`；若已有相近文档，再考虑更新相近文档。
- 文档必须包含：背景、编号需求、建议实现顺序、验收标准、风险/注意事项。
- 文档必须清晰记录用户提出的 8 条要求：
  - 不再使用 Claude API/Claude CLI，动态 AI 生成默认改用 Codex CLI。
  - Codex CLI reasoning effort 统一为 low。
  - AI 辅导必须由 AI 生成，并基于 question、Your recording transcript、Band 7 spoken version 做具体对比。
  - 支持每题完成后后台预生成 cleaned transcript、Band 7 spoken version、AI guidance、弱项标签。
  - 校准 P1 评分，避免对短但合理的 Part 1 答案过度压分。
  - Band 7 spoken version 按 P1/P2/P3 题型控制长度与风格。
  - P1/P2/P3 的 model answer、scoring、AI guidance prompt 按题型拆分。
  - 文档写成后续统一改造的实施计划/验收清单。

## Acceptance Criteria

- [ ] 已检查现有相关文档和任务 PRD。
- [ ] `docs/IELTS_AI_PIPELINE_REFACTOR_PLAN.md` 存在，且为中文。
- [ ] 文档结构简洁明确，包含背景、编号需求、建议实现顺序、验收标准、风险/注意事项。
- [ ] 文档没有要求继续使用 Claude 作为动态生成路径。
- [ ] 未修改业务代码，未提交 git commit。

## Out of Scope

- 本任务不实现 AI 调用链路、prompt 拆分、评分校准或前后端代码改造。
- 本任务不做外部文档调研。

## Technical Notes

- 已检查 `docs/IELTS_SCORING_ISSUES_AND_PROMPT_PLAN.md`、`docs/IELTS_CLI_NEXT_STEPS.md`、`.trellis/tasks/05-09-ielts-web-quick-correction-plan/prd.md`。
- 现有旧文档中仍有 Claude CLI 施工片段；新文档应作为后续统一替换的权威计划入口。
