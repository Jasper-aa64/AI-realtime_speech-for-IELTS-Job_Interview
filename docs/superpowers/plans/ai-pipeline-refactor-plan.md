# IELTS AI Pipeline 统一改造计划

创建日期：2026-05-10

## 1. 背景

当前 IELTS Speaking 练习链路已经具备 P1/P2/P3、报告、Band 7 spoken version、AI 辅导和评分等能力，但生成路径和 prompt 边界还不统一：

- 部分旧施工文档仍保留 Claude API/Claude CLI 的动态生成方案。
- AI 辅导存在规则模板或 fallback 过重的问题，不能稳定做到“基于本题、本次录音转写、Band 7 版本”的具体对比。
- 报告生成集中在最后阶段，用户完成考试后等待时间偏长。
- P1/P2/P3 的回答长度、题型目标、评分尺度和 Band 7 改写风格差异很大，不应继续用一套通用 prompt 覆盖所有场景。
- P1 当前存在偏低评分风险，短但合理的 Part 1 回答容易被当成“发展不足”而过度压分。

本文档作为后续统一改造入口，只记录需求、实施顺序和验收标准；不代表本次已经修改业务代码。

## 2. 编号需求

### R1. 统一移除 Claude 动态生成路径

后续动态 AI 生成默认全部改用 Codex CLI，不再使用 Claude API 或 Claude CLI。

范围包括但不限于：

- P3 动态出题/追问。
- scoring。
- model answer / Band 7 spoken version。
- AI guidance / AI 辅导。
- cleaned transcript。
- 弱项标签生成。

旧文档或旧代码中出现的 Claude 调用只能作为“待替换历史实现”处理，不能作为新功能默认路径。

### R2. Codex CLI reasoning effort 统一为 low

所有产品内后台 Codex CLI 生成任务统一采用 `reasoning effort = low`。

目标：

- 降低延迟。
- 控制 token 与 reasoning 成本。
- 让每题后台预生成适合在线考试流程。

如未来确实需要更高 reasoning effort，必须单独记录场景、成本影响和开关策略，不能散落在 prompt 调用点。

### R3. AI 辅导必须由 AI 生成，并做三方对比

报告中的 `AI 辅导` 不应再主要依赖固定规则模板。每题辅导必须基于以下输入做具体分析：

1. `question`
2. `Your recording transcript` 或 cleaned transcript
3. `Band 7 spoken version`

输出应回答：

- 这题用户原回答哪里影响分数。
- Band 7 版本具体改进了什么。
- 用户下一次同类题应该怎么说得更好。

AI 辅导可以有 deterministic fallback，但 fallback 只能作为失败兜底，不能成为正常路径的主要内容。

### R4. 支持边考试边后台预生成反馈

每题完成后立即启动后台生成任务，预生成以下 per-turn 数据：

- cleaned transcript
- Band 7 spoken version
- AI guidance / AI 辅导
- 弱项标签

考试结束时只做：

- 总分计算
- part scores 汇总
- report 拼装
- 必要的全局总结

目标是把耗时从“最后集中等待”拆到每题后的后台流程，减少最终报告等待时间。

### R5. 校准 P1 评分，避免短回答被过度压分

P1 的评分提示词/规则必须承认 Part 1 的真实考试特点：

- 回答可以短，但要直接、自然、完整。
- 3-5 句通常足够，多数题 3 句即可。
- 不应把 P1 当成 P2 长 turn 或 P3 抽象讨论评分。

评分应区分：

- 短但合理：直接回答、给出一点原因或例子、语言自然。
- 过短/无效：只有单词、明显离题、无法体现语言能力。
- 背诵堆砌：过长但不自然，不应因为长就高分。

### R6. Band 7 spoken version 按题型控制长度与风格

Band 7 spoken version 必须按 P1/P2/P3 分题型生成：

- P1：3-5 句，多数 3 句；自然口语、直接回答、轻量扩展。
- P2：long turn；结构完整，覆盖 cue card 要点，有连贯展开和细节。
- P3：更抽象的讨论；包含观点、理由、对比、趋势或社会层面的解释。

不能把 P2 长答案风格套到 P1，也不能把 P1 简短风格套到 P3。

### R7. P1/P2/P3 prompt 按题型拆分

以下 prompt 都必须按题型拆分，不再一套 prompt 套所有：

- model answer / Band 7 spoken version prompt
- scoring prompt
- AI guidance prompt

建议形成清晰目录或命名，例如：

- `p1_model_answer`
- `p2_model_answer`
- `p3_model_answer`
- `p1_scoring`
- `p2_scoring`
- `p3_scoring`
- `p1_ai_guidance`
- `p2_ai_guidance`
- `p3_ai_guidance`

每个 prompt 应明确输入字段、输出 JSON contract、长度约束、失败兜底策略和污染清理规则。

### R8. 文档与实施必须可统一验收

后续改造不应零散修补单个 prompt。应按本文档的实施顺序统一改，最终用验收清单确认：

- 生成路径统一。
- prompt 拆分完成。
- 每题后台预生成可用。
- P1 评分校准可验证。
- 报告等待时间下降。
- 报告内容对用户更具体。

## 3. 建议实现顺序

### Phase 1. 盘点并冻结 AI 调用入口

目标：找出所有 Claude/Codex/OpenAI/规则模板/fallback 相关调用点。

输出：

- AI 调用入口清单。
- Claude 待替换点清单。
- 当前 per-turn report 字段清单。
- 当前 fallback 模板清单。

验收重点：不允许遗漏 CLI、Web backend、报告生成、P3 动态题、历史报告兼容路径。

### Phase 2. 建立统一 Codex CLI 适配层

目标：所有后台动态生成都走同一个 Codex 调用封装。

要求：

- 默认 reasoning effort 为 low。
- 统一超时、错误、日志、usage 采集、污染清理。
- 每次调用记录 task type，例如 `p1_scoring`、`p2_model_answer`、`p3_ai_guidance`。
- 失败时返回可区分的错误状态，而不是静默生成模板内容。

### Phase 3. 拆分 P1/P2/P3 prompt 与输出 contract

目标：先建立稳定 contract，再替换调用。

每个题型至少拆分三类 prompt：

- scoring
- Band 7 spoken version / model answer
- AI guidance

输出字段建议：

- `cleaned_transcript`
- `band7_version`
- `ai_guidance`
- `weakness_tags`
- `score`
- `confidence`
- `input_quality`

### Phase 4. 改造 per-turn 后台预生成队列

目标：用户每完成一题，就在后台预生成该题反馈。

建议流程：

1. 保存原始 transcript 与音频状态。
2. 触发 cleaned transcript。
3. 触发 Band 7 spoken version。
4. 基于 question + transcript + Band 7 版本触发 AI guidance。
5. 生成弱项标签。
6. 将 per-turn 结果落库或写入 attempt 状态。

考试最后阶段只汇总已有 per-turn 结果；缺失项可补跑，但不能让全部生成集中在最后。

### Phase 5. 校准 P1 scoring

目标：让 P1 评分符合真实 Part 1 短问答特征。

建议用例：

- 3 句自然回答，应避免被判为严重发展不足。
- 1 句但完整回答，应给中等可接受分，而不是自动低分。
- 单词级回答、离题回答、机械背诵回答，应继续压分。
- P1 不应因没有 P2 式长段展开而被扣过重。

### Phase 6. 报告拼装与历史兼容

目标：报告优先读取 per-turn 预生成字段，兼容旧报告字段。

要求：

- `AI 辅导` 展示 AI 生成结果。
- 如果 AI guidance 缺失，明确 fallback 来源。
- 旧字段如 `upgrade_notes` 只能作为兼容 fallback。
- 报告中保留评分 caveat：没有真实音频分析时，pronunciation 只能是估计或不评估。

### Phase 7. 验证延迟、质量与失败兜底

目标：确认体验真的变快，且失败时不产生误导性报告。

建议记录：

- 每题后台任务耗时。
- 最终报告等待时间。
- Codex usage。
- 失败率与 fallback 触发原因。
- P1/P2/P3 各自样本质量。

## 4. 验收标准

- [ ] 代码和文档中不再把 Claude API/Claude CLI 作为动态 AI 默认生成路径。
- [ ] 所有产品内 Codex CLI 后台生成默认 reasoning effort 为 low。
- [ ] P1/P2/P3 的 scoring prompt 已拆分。
- [ ] P1/P2/P3 的 Band 7 spoken version prompt 已拆分。
- [ ] P1/P2/P3 的 AI guidance prompt 已拆分。
- [ ] AI 辅导正常路径由 AI 生成，且输入包含 question、用户 transcript、Band 7 spoken version。
- [ ] 每题完成后能后台生成 cleaned transcript、Band 7 spoken version、AI guidance、弱项标签。
- [ ] 最终报告阶段主要做总分、part scores、report 拼装，不再集中生成全部 per-turn 内容。
- [ ] P1 短但合理回答不会因为长度短被自动压到明显不合理低分。
- [ ] P1 Band 7 版本多数为 3 句，允许 3-5 句。
- [ ] P2 Band 7 版本是 long turn，覆盖 cue card 要点。
- [ ] P3 Band 7 版本体现抽象讨论、理由、对比或趋势。
- [ ] 报告中 `AI 辅导` 对每题给出具体差异，而不是重复模板。
- [ ] Codex 调用失败时报告能明确 fallback 或缺失状态，不假装 AI 已成功生成。
- [ ] 历史报告兼容旧字段，但新报告优先使用新 per-turn 字段。

## 5. 风险 / 注意事项

- **延迟与并发**：每题后台预生成会增加并发 Codex 调用，需要控制队列、超时和重试，避免多题同时完成后阻塞服务。
- **成本与 usage**：reasoning effort 统一 low 只能降低成本倾向，仍需结合 usage 采集和余额扣减方案做账务闭环。
- **评分一致性**：P1 校准不能变成“短回答全部高分”；仍要识别过短、离题、语法严重不足和背诵痕迹。
- **prompt 污染**：Band 7 版本和 AI guidance 必须清理 Trellis/session/workflow/system log、Markdown fence、非答案解释等污染内容。
- **音频限制**：没有真实音频分析时，Pronunciation 不应被包装成实测分数。
- **失败兜底透明**：规则 fallback 可以存在，但 UI/报告应能区分 AI 生成、fallback 生成、缺失。
- **旧报告兼容**：历史 attempt 可能只有 `upgrade_notes` 或旧 `band7_version` 字段，迁移时不能破坏历史查看。
- **题型边界**：P1/P2/P3 prompt 拆分后，调用方必须传入可靠 part/type 元数据，避免用错 prompt。

## 6. 与现有文档关系

- `docs/IELTS_SCORING_ISSUES_AND_PROMPT_PLAN.md`：保留为评分问题与 prompt 风险记录。
- `docs/IELTS_CLI_NEXT_STEPS.md`：其中 Claude 相关施工片段视为旧实现思路，后续应被 Codex CLI 方案替换。
- `docs/CODEX_TOKEN_BILLING_BALANCE_DEDUCTION_1_4.md`：可作为 usage 采集与余额扣减的配套方案。
- `.trellis/tasks/05-09-ielts-web-quick-correction-plan/prd.md`：包含报告字段和 AI 辅导的近线需求；本文档将其扩展为统一 AI pipeline 改造计划。
