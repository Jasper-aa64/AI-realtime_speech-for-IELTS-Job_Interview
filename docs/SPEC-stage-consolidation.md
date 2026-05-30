# Goal 规格：阶段性收口（把所有半闭环线收干净 + 出重构完成度报告）

> 阶段性大 goal。给实现方（Codex）。用户负责 review + 验收。
> 目的：把当前散在多条线的"差最后一脚"统一收口，让"重构到哪了"有据可查、战线从乱变清。
> **不开新功能、不进攻新大文件**——这是一个"收尾 + 盘点"goal，不是"进攻"goal。

## 背景：当前半闭环清单（实读得出，已校正）

1. ~~退役脚本未接入总脚本~~ —— **已闭环**。`run_software_construction_deliverables_validation.sh`
   第 64 行已调用 `validate_legacy_server_retirement.py`。此线无需再动。
2. **追问提速 goal 待真实验收**：HTTP API provider 代码完成、246 测试绿，但未用真实
   `AI_HTTP_*` 端点跑 benchmark 证明"十几秒→秒级"（**这一步由用户配 key 完成，不在 Codex 范围**）。
3. **工作区 10 个脏文件混多类未收口**（见任务 1 分类）。
4. **`corpus_services.py` 存疑**：它是重构拆出的模块，却躺在脏区有未提交改动——
   可能是上一轮 speaking 拆分留的尾巴，也可能混了业务改动。**收口前必须查清归属。**

## 任务 1：脏文件分线收口（关键，别再混着放）

当前 10 个脏文件，**先查清 `corpus_services.py`，再分线提交，互不混**：

**先查清（存疑）**
- `backend_django/apps/speaking/corpus_services.py`（M）：
  `git diff` 看改了什么。若是 speaking 拆分的收尾（纯模块移动/import 修正）→ 归重构线提交；
  若混了业务逻辑改动 → 标记给用户，不替提。**先判定，再决定归 A 还是 B。**

**A. 重构线产物（应提交，归重构）**
- `docs/SPEC-http-api-provider-followup-latency.md`
- `docs/SPEC-legacy-server-retirement-validation.md`
- `docs/SPEC-speaking-services-split.md`
- `docs/SPEC-stage-consolidation.md`（本文件）
- `scripts/test_wasm_audio_preprocessor_metrics.mjs`（若存在）
- `corpus_services.py`（**仅当判定为纯拆分收尾**）
- → 提交：`docs: capture refactor stage specs`（代码类另起 commit）

**B. 业务 WIP 线（用户的功能开发，不归重构，需用户确认）**
- `web/static/app.js` / `index.html` / `styles.css`（七彩外观主题那条线）
- `backend_django/apps/speaking/tests.py` / `apps/writing/tests.py`
- `scripts/ielts_agent_cli.py`
- `scripts/evaluate_writing_prompt_search.py`（`??`）
- `data/ielts/part2/2026_may_august_topics.json`（题库数据改动）
- `corpus_services.py`（**若判定混了业务改动**）
- → **不要 Codex 替用户提交**。由用户决定这条业务线怎么提。Codex 只列清单，不动这些文件。

**C. 不提交**
- `backend_django/db.sqlite3`（本地测试库噪音；虽允许追踪但不该跟功能提交，保持现状不 stage）

> ⚠️ Codex 只处理 A 线提交 + 列出 B/C 清单给用户；**绝不替用户提交 B 线业务 WIP**。

## 任务 2：出《重构完成度报告》

新增 `软件构造/重构完成度报告.md`（或 `docs/`），写清"重构到哪了、还剩什么"：

**已完成（带证据）**
- apps/ai provider 结构化重构（实验2，Strategy/Adapter/责任链/Template）
- C++ audio_core 纯核抽取 + libfvad 开源 VAD + WASM 默认启用
- HttpApiProvider 追问提速（代码完成，**真实端点 benchmark 待用户验收**——如实标注）
- 旧 server 退役（标记+拦截+文档+验证脚本+已接入总验证脚本，完整闭环）
- writing/services.py 拆分（993→605 行，分出 report_services）
- speaking 拆分进行中（已分出 corpus/report/scoring/text_utils/audio/tts 六模块，services 4433→4021）

**剩余技术债（明确列出，按性价比排序）**
- `speaking/services.py` 仍 ~4021 行（runtime/TTS/Codex runtime 未拆）
- `web/static/app.js` 仍 ~8669 行（单文件 SPA，模块化未做）
- realtime gateway「能打断」（backlog，未启动）
- 发音评测（backlog，待查语音服务是否支持音素级评分）

**附基线数字表**（拆分前后行数对比，便于下阶段量化进展）。

## 验收标准（用户验收用）

- [ ] `corpus_services.py` 归属已判定（重构收尾→提交 / 业务→标记给用户）。
- [ ] A 线产物已提交；B 线业务 WIP 清单列出但未被 Codex 提交；C 线 db.sqlite3 未夹带。
- [ ] `bash scripts/run_software_construction_deliverables_validation.sh` 整体仍 exit 0（退役已接入，回归确认）。
- [ ] 《重构完成度报告》存在，已完成项有证据、剩余债务明确且排序。
- [ ] 全量 `python3 manage.py test` 仍全绿；`manage.py check` 通过。
- [ ] CHANGES.md：收口了哪些线、各线提交 hash、剩余债务摘要。

## 明确不做（边界）

- 不进攻 `speaking/services.py` / `app.js` 的新拆分（那是下一个 goal，本 goal 只盘点不动刀）。
- 不开 realtime/发音评测任何代码。
- 不替用户提交业务 WIP（B 线）。
- 不动 db.sqlite3。
- 追问提速的真实端点 benchmark 由用户做，Codex 不需要 key。
