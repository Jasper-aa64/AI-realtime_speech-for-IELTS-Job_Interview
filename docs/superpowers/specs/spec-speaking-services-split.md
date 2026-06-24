# 规格：speaking/services.py 上帝文件拆分（行为不变）

> 给实现方（Codex）的目标规格。这是产品级第一阶段重构的下一个靶点。
> 用户负责 review + 验收；本规格只定**目标分层、边界、验收标准、收口条件**。
> 已在进行：`report_services.py`、`transcription.py` 已分出，`scoring.py` 进行中——本规格统一收口。

## 0. 最高约束（不可破坏）

1. **行为不变（behavior-preserving）**。这是重构，不是重写。
   - 评分逻辑、prompt 内容、Codex 调用、TTS、计费、attempt/turn 状态机、对外 API 行为**全部不变**。
   - 不改产品设计，不改 UI，不动前端。
2. **现有测试必须全绿，且不得修改测试**（除非纯粹是 import 路径跟随移动而调整，且需在 CHANGES 里逐条说明）。
   - 基准：`cd backend_django && python3 manage.py test`（当前 232 通过）。
3. **保留所有对外公开 import**。`services.py` 继续作为 facade，re-export 已移动的符号，使
   `from apps.speaking.services import X` 对所有现有调用方照常工作。
   - 实现前先 `grep -rn "speaking.services" backend_django/ --include=*.py` 确认调用面，逐个保住。
4. 不提交 `db.sqlite3`；不碰工作区已有的无关脏文件（writing/speaking tests、styles.css、
   ielts_agent_cli.py、evaluate_writing_prompt_search.py）。

## 1. 目标分层（services.py 拆成「facade + 纯函数模块 + 编排模块」）

按"副作用强弱"从纯到脏分层，**先拆纯的、后拆脏的**（纯函数无 DB/无线程/无 Codex runtime，最安全）：

| 模块 | 收纳内容 | 副作用 | 状态 |
|---|---|---|---|
| `scoring.py` | 纯评分/校准/习惯标签 helper：`clamp_band` `rounded_overall` `band_cap` `development_markers` `generic_template_score` `simple_grammar_ratio` `is_template_like_answer` `calibrate_realistic_score` `prompt_relevance` `cap_off_topic_score` `heuristic_score` `turn_habit_tags` `part_focus_text` `infer_primary_focus` 等 | 无 | 进行中 |
| `transcription.py` | 转写/文本清洗：JSON 抽取、codex 事件解析、markdown/spoken 文本清洗类 helper | 无/弱 | 已分出 |
| `report_services.py` | 报告生成、overall review、coaching 组装 | 中（调 AI/读 DB） | 已分出 |
| `question_bank.py`（可选） | `QuestionBank` 类及题库采样 | 弱（读数据文件） | 待定 |
| `services.py`（facade） | attempt/turn CRUD、runtime 编排、TTS/audio、计费对接、Codex runtime 调用 + **re-export 上面所有公开符号** | 强 | 终态保留 |

> 不要求一次拆到底。每个模块**独立成步**：移动 → 跑测试 → 绿 → 提交。一步一绿。

## 2. 拆分手法（每个模块统一流程）

1. 把目标函数/类**整体移动**到新模块（不改函数体逻辑，仅改必要的 import）。
2. 在 `services.py` 顶部 `from apps.speaking.<新模块> import (...)` re-export，保持 facade。
3. 跑 `python3 manage.py test apps.speaking` → 绿。
4. 跑 `python3 manage.py check` + 全量 `python3 manage.py test` → 绿。
5. 提交：`refactor: extract speaking <模块名>`（每模块一个 commit，便于 review/回滚）。

## 3. 边界（明确不做）

- 不动 `apps/ai`（provider adapter 已在实验2 重构过）。
- 不拆 C++ / WASM（已闭环）。
- 不动 `web/ielts_server.py`（已退役）。
- 不重写任何算法、不"顺手优化"评分逻辑——纯搬运。
- 不引入新依赖。
- 不拆 `app.js`（那是独立的下一个 goal）。

## 4. 收口条件（这个 goal 何时算完成）

- [ ] `speaking/services.py` 从 ~4400 行降到一个"facade + 编排"可维护规模（目标 ≤ ~2000 行；纯函数与报告已外移）。
- [ ] 至少 `scoring.py` / `transcription.py` / `report_services.py` 三个模块成形且职责清晰。
- [ ] 全量 `python3 manage.py test` 全绿，测试无逻辑改动。
- [ ] `python3 manage.py check` 通过。
- [ ] 所有 `from apps.speaking.services import X` 调用方零改动仍可用。
- [ ] 一份 `重构完成度报告`：拆分前后行数对比、各模块职责、re-export 清单、剩余债务（speaking runtime/TTS 是否还需进一步拆）。
- [ ] 每个模块独立 commit；不夹带无关脏文件。

## 5. 验收材料（交用户 review）

- 拆分前后 `wc -l` 对比。
- `git log --oneline` 显示分模块提交。
- 全量测试通过截图/输出。
- 重构完成度报告（剩余债务明确列出，供决定是否需要第三阶段）。
