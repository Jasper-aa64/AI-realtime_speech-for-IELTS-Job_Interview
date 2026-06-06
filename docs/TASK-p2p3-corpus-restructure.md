# TASK — P2/P3 语料重构实现任务(给 Codex)

> 权威需求 = `docs/SPEC-p2p3-bank-corpus-restructure.md`。本文件只做**实现任务拆分 + 锚点 + 验收**。
> 角色:Codex 实现;用户验收;指挥不写生产代码。分 3 阶段,**严格按序**(后一阶段依赖前一阶段)。
> 每阶段结束:`manage.py check` + `makemigrations --check` + `apps.speaking` 测试必须绿;**禁止 git commit**(交用户)。

## 现状锚点(读这些再动手)
- 模型:`backend_django/apps/speaking/models.py` —— `P1CorpusEntry`(L127,逐题语料的范本)、`P2CorpusEntry`(L149,个人库 A,5 分类)。
- 视图:`backend_django/apps/speaking/views.py` —— `p1_corpus_view`(L104)、`p2_corpus_view`(L117)、`p2_corpus_detail_view`(L130)、`p3_view`(L411)、`p3_follow_up_view`(L419)。
- 路由:`backend_django/config/urls.py` —— `api/p1-corpus`(L65)、`api/p2-corpus[/<entry_id>]`(L66-67)、`api/p3/questions`(L60)、`api/p3/follow-up`(L61)。
- 题库种子:`data/ielts/part2/<season>_topics.json`(每题含 `title/bullets/rounding/p3_theme/p3_follow_ups`,当前 3 条/题)。
- P3 生成 prompt:`services.py` 内联 prompt 使用 `P3_MAIN_COUNT`(当前用户拍板 = 3);`data/ielts/prompts/p3_question_gen.md` 已标为废弃参考,不再被代码读取。
- 前端:`web/static/index.html`(P3 来源 L256-259、强度 L245-247;P2 库页面、peek 按钮)、`web/static/app.js`(P3 来源 L259-263 及 plan 逻辑)。
- **污染 bug 现场**:定位"编辑题库题卡 → 写进 `P2CorpusEntry`(个人库 A)"的代码路径,这是阶段 1 要切断的根。

---

## 阶段 1 · 后端:两套语料存储隔离(地基)
**目标:个人库 A 不动;题库 B 的正文/P3 追问落到新存储,按 `question_id` 跨考季复用;切断题卡→A 的污染。**

实现:
1. 新模型(仿 `P1CorpusEntry`,加 migration):
   - `P2BankCorpusEntry(user, question_id, question, corpus_text, last_ai_answer, metadata)`,`UniqueConstraint(user, question_id)`。
   - `P3BankFollowupCorpusEntry(user, p2_question_id, followup_id, followup_question, corpus_text, last_ai_answer, metadata)`,`UniqueConstraint(user, followup_id)`。
   - 索引参照 P1/P2 现有风格(`user, updated_at` 等)。
2. 服务 + 视图 + 路由(对齐 p1-corpus 风格):
   - `GET/PUT api/p2-bank-corpus/<question_id>` → 题库正文读写(写入 `P2BankCorpusEntry`)。
   - `GET api/p3-bank-corpus/<p2_question_id>` → 列该题所有 P3 追问(题面取自 json `p3_follow_ups`,**有几条返回几条,不补满 5**)+ 已存语料。
   - `GET/PUT api/p3-bank-corpus/item/<followup_id>` → 单条 P3 追问语料读写。
   - 鉴权 `require_user`、错误 `SpeakingError`/现有约定。
3. **切断污染**:题库题卡的任何编辑路径**只写新模型,绝不 create/update `P2CorpusEntry`**。`P2CorpusEntry` 只保留"用户手动新增/编辑个人库 A"的入口。
4. **跨考季复用**:正文/追问按 `question_id`/`followup_id` 命中,同题换考季仍返回旧语料。

测试(`apps/speaking/tests.py` 或新文件):
- 题库正文 upsert + 跨考季同 `question_id` 命中同一条。
- P3 追问列表条数 = json 实际(当前 3),不补满;单条语料 upsert。
- **隔离断言**:调用题库正文/P3 写入后,`P2CorpusEntry.objects.count()` 不增(A 未被污染)。
- 路由方法限定 + 未登录鉴权。

done:check / makemigrations --check / apps.speaking 绿;A 计数隔离测试通过。

---

## 阶段 2 · 前端:P2 库页面两区拆分 + 题卡编辑
**目标:页面上"个人库 A"和"考季题库 B"明确分区;题卡「正文」「P3 追问」按钮接阶段 1 接口;编辑题卡后 A 区不出现新条目。**

实现(`web/static/index.html` + `app.js` + 复用 `styles.css`/`corpus-markdown-editor.js`):
1. **个人库 A 区**:只渲染 `P2CorpusEntry`(5 分类),保留「新增人物/地点/...」「P3 待填/已填」。**移除任何把题卡写进 A 的代码。**
2. **题库 B 区**:按考季列题卡,每卡两按钮:
   - 「正文」→ 弹窗编辑,走 `api/p2-bank-corpus/<question_id>`(类 P1 编辑语料弹窗,可复用 `p1CorpusDialog` 模式)。
   - 「P3 追问」→ 弹窗列出该题 P3 追问条目;每条点进去编辑,走 `api/p3-bank-corpus/item/<followup_id>`。
3. 两区视觉区隔清晰(标题/分组),用户一眼分清"我的素材" vs "考季题库"。
4. index.html 静态引用带 `?v=` 版本串刷新缓存。

done:本地起服务,编辑题卡正文/P3 后**个人库 A 区无新条目**;题卡正文/追问能存能读、刷新保留;换考季同题正文仍在。

---

## 阶段 3 · P3 练习:来源(3)/强度(2)收敛 + 报告提示
**目标:P3 来源只剩 3 个(默认神奇题库)、强度只剩 2 个;练习中提示与报告编辑语料按来源接对数据。**

> ✅ **当前状态核实(2026-06-06):阶段 3 主体已补齐,剩余按阶段 4 收口验证。**
> - ✅ 后端 `_normalize_p3_intensity` 已只收 `{normal, high}`(`services.py:810`,drill 已删)。
> - ✅ 后端 `_p3_source_type` 默认已是 `bank`(`services.py:815-827`)。
> - ✅ `P3_MAIN_COUNT = 3`(`services.py:693`,用户最新拍板)。
> - ✅ bank 走 `season_bank`:前端传 `p3_follow_ups` 数组即直接用、不 AI 生成(`services.py:1182-1197`)。
> - ✅ 前端来源收敛为 `bank`/`p2_report`/`custom`,强度收敛为 `normal`/`high`,默认 `bank`;`app.js` 已补 P2 题卡选择器、固定追问 payload、报告/黄色提示来源路由。
> - ✅ 后端收尾见 §3.B/阶段 4,bank 不再按 `P3_MAIN_COUNT` 强制截断。

### 3.A 前端(主体,`web/static/index.html` + `app.js`)
1. **训练强度**(`index.html:245-247`):删 `data-p3-intensity="drill"`(专项快练)按钮;只留 `normal`/`high`。清理 `app.js` 中 drill 相关文案(`349`、`8622` 等)。
2. **训练来源**(`index.html:256-259`、`app.js:40,260-263,1135` 及 plan 逻辑):
   - 删 `data-p3-source="topic"`(按话题练)、删 `data-p3-source="p2_corpus"`(根据 P2 素材)两个按钮。
   - 新增 `data-p3-source="bank"`(**根据神奇题库**,小字如"照搬题库该题的 P3 追问"),并设为 **default active**;`app.js:40` 默认 `p3SourceType` 由 `"topic"`→`"bank"`,`app.js:1135` 同步。
   - 保留 `p2_report`、`custom`。
3. **P2 题库题选择器**(替换"推荐话题"区,`index.html:262-265` `#p3BankPickerModal`/`#p3BankPickerList`):
   - bank 模式下,列出当前考季带固定 P3 追问的 P2 题卡;选中一道 → 取该题 `p3_follow_ups` 放进启动 payload。
   - 选题后,plan 调用传 `{ source: "bank", p3_follow_ups: [...该题追问...] }`(后端 `services.py:1182` 收 `p3_follow_ups` 即走 season_bank)。
   - `p2_report`/`custom` 不显示该选择器(沿用各自上下文/自定义输入框)。
4. **文案**:把旧"5 个主问题…"提示改为与实际一致(`P3_MAIN_COUNT`,当前 3 题;bank 为题库实际条数)。
5. **练习中提示(黄色按钮)**:P3 练习过程补上 P1/P2 已有的提示按钮(SPEC §6b 缺口),复用 `peekP3CorpusBtn`,数据源按 §3.C 来源规则。

### 3.B 后端收尾(`services.py`)
1. **bank 不得补满/截断**:`build_p3_plan`(约 `1179`)对 `season_bank` 来源,问题数 = 传入 `p3_follow_ups` 实际条数,**跳过 1219-1220 的 fallback 补满**与 `[:question_count]` 截断(`1192`)。"有几条用几条"。仅 `p2_report`/`custom` 用 `P3_MAIN_COUNT`(当前 = 3,用户拍板)。
2. **清死代码**:`1179` 的 `P3_DRILL_COUNT if intensity=="drill"` 分支(intensity 已不会是 drill;`P3_DRILL_COUNT` 可能已未定义)→ 直接用 `P3_MAIN_COUNT`。`_p3_source_type` 里 `topic`/`p2_corpus` 旧分支前端下线后可保留兼容或清理(任选,别报错)。
3. **生成 prompt 文案**:`services.py` 内联 prompt 已用 `exactly {P3_MAIN_COUNT}`(现自动 = 3),无需再改。`data/ielts/prompts/p3_question_gen.md` 已标为弃用参考,不再被代码读取。

### 3.C 练习中提示 + 报告编辑语料(来源路由)
   - 来源 `bank` → 提示/报告编辑语料 = 该 P2 题的 P3 追问语料(`P3BankFollowupCorpusEntry`,阶段 1),交互类 P1。
   - 来源 `p2_report` → 提示 = 已链接个人素材 A(`P2CorpusEntry`)的 P3。
   - 来源 `custom` → 无特定语料提示(沿用通用 P3 辅导)。
   - 复用现有 `peekP3CorpusBtn`/`peekP2CorpusBtn` 钩子。

测试 + 自查:
- P3 来源接口/前端只暴露 3 个,默认 `bank`;`bank` 返回条数 = 题库实际。
- `p2_report`/`custom` 生成恰 `P3_MAIN_COUNT` 题(当前 3)。
- 强度仅 2 个;`high` 对每个回答追问。
- 提示数据源按来源正确切换(后端可加单测覆盖 `bank` 取 `P3BankFollowupCorpusEntry`、`p2_report` 取 A 的 P3)。

done:三来源/两强度全链路本地可走;check/test 绿。

---

## 阶段 4 · 收尾修正(2026-06-06 复核,给 Codex)
> 复核结论:UI 收敛层(来源 3/强度 2/56 题选择器/黄按钮)已到位。剩 3 处未达标,本阶段收口。
> ⚠️ **`P3_MAIN_COUNT=3` 是用户最新拍板,保持不动**;SPEC 已同步(原写 4 作废)。所有"生成 4 题"措辞按 `P3_MAIN_COUNT` 理解。

### 4.1 bank 上游截断(隐藏 bug)—— `services.py:1284`
- 现状:`build_p3_plan` 里 `cue_questions = [...][:question_count]`,`question_count=P3_MAIN_COUNT=3`。当前题库恰 3 条/题被掩盖,但题库该题 >3 条时 bank 会被砍。
- 改:**bank/season_bank 来源不走 `[:question_count]`**。把截断改成"仅非 bank 来源才切片",对齐下游 turn-builder `1688-1691` 已有的 `fixed_bank_questions` 逻辑。"有几条用几条"。
- 验:构造一道 4 条 `p3_follow_ups` 的 bank 题 → plan 返回 4 题、不被砍到 3;`p2_report`/`custom` 仍 = `P3_MAIN_COUNT`。

### 4.2 P3 报告「编辑语料库」按钮缺失(主体)—— §6b
- 根因:报告行 `corpusButton` 走 `p1CorpusTargetForTurn`(`app.js:7435`),该函数 `turn.part!=="p1"` 直接 `return null` → **P3 报告永远没有编辑入口**。
- 还缺数据线索:P3 的 bank turn 当前 metadata 只有 `source`+`plan_question_id`("q1"…),**没带 `followup_id` / `p2_question_id` / `p2_corpus_entry_id`**,报告拿不到能定位语料的 key(`services.py:1696-1730`)。
- 实现(后端先铺线索,前端再接按钮):
  1. **后端透传**(`services.py` turn-builder ~`1696`):bank 主 turn 的 metadata 增补 `followup_id`、`p2_question_id`(来自前端传入的 bank 卡 `question_id` + 每条追问的稳定 `followup_id`,前端需在 `app.js:1697` 的 payload 里把 `p3_follow_ups` 升级为带 `followup_id` 的结构,或另传 `p3_bank_question_id` + `p3_followup_ids[]`)。`p2_report` 来源把已链接的 `p2_corpus_entry_id`(已在 `plan.source`,`1345`)透到 turn。
  2. **前端按来源路由**(`app.js`):新增 `p3CorpusTargetForTurn(turn, attempt)`,在 `turnReportRow`(`7464`)对 `turn.part==="p3"` 调它,产出"编辑语料库"按钮:
     - `source==="bank"/"season_bank"` → 复用题库 P3 编辑器 `openP2CorpusP3Editor`(`corpus-takeaway.js:1607`)/`api/p3-bank-corpus/item/<followup_id>`(`1842`),按 turn 的 `followup_id` 直接打开**同一条** `P3BankFollowupCorpusEntry`(与 P2 库页面题卡「P3 追问」同一份,不另建)。
     - `source==="p2_report"` 且该次 P2 报告**链接过素材**(turn 带 `p2_corpus_entry_id`)→ 复用素材卡右侧 P3 按钮路径(`data-p2-corpus-p3`,`corpus-takeaway.js:730`),编辑**同一** `P2CorpusEntry` 的 P3,不另建。
     - `source==="p2_report"` **未链接** / `source==="custom"` / 其它 → 按钮存在但点击**弹提示**("本次没有可编辑的语料库/未链接素材"),不报错、不静默。
- 验:bank 练完报告每行有「编辑语料库」→ 打开的正是该追问那条、与库页面同源;p2_report 链接素材时编辑的是素材卡那条;未链接/custom 弹提示。

### 4.3 黄色提示按钮数据源(部分实现,按 §6 收口)—— `corpus-takeaway.js:369-394`
- 现状:`openP3CorpusPeek` 只渲染 `state.p3PracticeSource.p3FollowUpText`(本次传入的追问**题面**),**没读用户保存的语料、不按来源区分**。
- 改:复用 4.2 铺好的 turn 线索,让黄按钮提示内容按 §6 切换数据源:
  - bank → 读该 `followup_id` 的 `P3BankFollowupCorpusEntry.corpus_text`(无则提示"这道题还没保存语料",同 P1 行为)。
  - p2_report 链接素材 → 读该 `P2CorpusEntry` 的 P3 语料。
  - custom / 未链接 → 维持通用(或隐藏按钮),不报错。
- 验:bank 模式黄按钮显示的是**已保存语料**而非题面;未保存时给"还没保存"提示。

### 红线沿用 + done
- 不写入个人库 A;不另建语料条目(报告按钮编辑的必须是库页面同一条);不引 CDN/不泄露 key;**禁止 git commit**。
- done:4.1 bank 不再被截断;4.2 三种来源的 P3 报告「编辑语料库」按 §6b 正确路由(含未链接弹提示);4.3 黄按钮读保存语料;`check`/`makemigrations --check` 绿,新增/改动逻辑有单测;`apps.speaking` 既有红测(AI provider routing)与本阶段无关、不在本阶段范围。

---

## 红线(全程)
- **题库编辑绝不写入个人库 A**(`P2CorpusEntry`);A 仅手动管理。
- A↔B 无搬运通道;个人库 A 模型 + 链接进 P2 报告 band7/辅导逻辑(上一轮接通)**不动**。
- 题库本体只读(json 种子);用户语料只进新模型。
- 复用 `UserOwnedModel`/P1 语料视图路由风格/`require_user`/`SpeakingError`;不另起炉灶。
- 加模型必 `makemigrations` 且 `--check` 干净;不引 CDN;不泄露 key;不在 URL 放敏感数据。
- **禁止 git commit**(交用户分阶段验收)。

## 开放点(实现前若仍未定,默认按右侧)
- 题库正文初值:默认**同 P1**(用户手填 + `last_ai_answer` 可空,不预生成)。
- P3 每题追问条数:默认沿用 json 现有(当前 3);若用户提供更全题库文档再补种子。
