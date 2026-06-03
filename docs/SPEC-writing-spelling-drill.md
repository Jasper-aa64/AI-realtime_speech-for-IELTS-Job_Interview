# SPEC — 作文拼写错词库 + 重新拼写训练(Spelling Drill)

> 给 Codex 实现。指挥(本会话)定目标/边界/数据源/验收;不写生产代码。
> 角色:用户=设计/验收;Codex=实现。本 SPEC 是唯一权威需求来源。

## 0. 一句话目标
把用户**每篇作文批改里被判定为拼写错误的单词**自动汇成一个**拼写错词库**,并提供一个**重新拼写训练(背写)**的地方:逐词遮住正确拼写,让用户重新敲一遍,判对错、记掌握度,练到"已掌握"后退出。

## 1. 设计主线:复用现有批改产出,不另调 AI(重要)
**不新增任何 AI 调用。** 拼写错误数据在现有批改结果里已经齐了,直接采集即可——既省 token、结果确定、可离线复现,又正好契合实验5"复用"主题。两个现成数据源(都在 `WritingScore.analysis_payload`,见 `apps/writing/models.py` 第 69 行 `analysis_payload = JSONField`):

1. **首选 · 结构化**:`analysis_payload["inline_annotations"]` 里 `type == "spelling"` 的项。
   - 字段已规范化(见 `apps/writing/services.py` `normalize_inline_annotations`,312 行):`original`(写错的)、`suggestion`(正确的)、`explanation`(中文解释)、`paragraph_index`、`severity`。
   - 这是错词→对词的金矿,直接用。
2. **补充 · 文本**:`analysis_payload["spelling_correction_summary"]`(中文 Markdown,形如 `vidios -> 正确：videos（视频）`)。
   - 用现成工具解析,**别重写正则**:`apps/writing/report_services.py` 的 `looks_like_single_word_spelling_fix`(58 行)判断某行是不是"单词拼写订正",`spelling_terms_from_summary`(49 行)抽错词。
   - 从 `错词 -> 正确：对词（中文释义）` 里同时取:错词、对词、括号内中文释义(作为 gloss)。

> 两源**合并去重**:以"正确拼写小写"为唯一键。同一个对词的多个错拼形式聚进 `wrong_forms`。

## 2. 采集规则(harvest,幂等)
新建采集服务 `apps/writing/spelling_services.py`,`harvest_spelling_words(user) -> int`(返回新增/更新条数):
- 遍历该用户 `WritingScore.objects.filter(user=user)`(按 `created_at` 即可,见模型 index),读 `analysis_payload`。
- 从两个数据源抽 (wrong, correct, gloss, explanation, 来源 entry) 四元组。
- **只收"单词级"拼写订正**,过滤掉短语/多词:`correct`、`wrong` 必须都匹配 `^[A-Za-z][A-Za-z'\-]*$` 且长度 ≥ 2;`inline_annotations` 里 `original`/`suggestion` 含空格的(短语)**跳过**(短语属于表达升级,不是拼写背写)。
- **大小写/标点归一**:键用 `correct.lower()`;展示保留批改给出的原形(若全大写则转常规小写)。
- **upsert 到新模型**(见 §3),幂等:
  - 已存在的词:把新见到的 `wrong_forms`/来源 `source_refs`/示例并入(去重),`occurrence_count += 本轮新增次数`,更新 `gloss`(原为空才补,不覆盖用户已编辑的),刷新 `last_seen_at`。
  - **绝不因为重新采集而重置训练进度**(`attempt_count`/`correct_count`/`current_streak`/`status` 保持)。
- 触发时机(MVP):**打开错词库页面时按需采集**(GET 列表接口内部先 `harvest` 再返回)。不挂进评分管线,避免耦合;留 TODO 注释说明未来可在评分完成后增量采集。

## 3. 数据模型(新增,需 migration)
`apps/writing/models.py` 新增 `SpellingDrillWord(UserOwnedModel)`(复用 `apps/common/models.py` 的 `UserOwnedModel`):

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| user | FK CustomUser | related_name="spelling_drill_words" |
| word_id | CharField(64) | 稳定 id = `correct.lower()` 的短 hash(给前端/详情路由用) |
| correct_spelling | CharField(120) | 正确拼写(展示原形) |
| normalized | CharField(120) | `correct.lower()`,唯一键的一部分 |
| wrong_forms | JSONField(list) | 用户写过的错拼形式,去重 |
| chinese_gloss | CharField(200, blank) | 中文释义,可空;来源:summary 括号 / 复用 `LOCAL_TAKEAWAY_WORD_TRANSLATIONS`(`apps/speaking/corpus_services.py`)查表兜底;查不到留空,**不许编造** |
| explanation | TextField(blank) | 批改给的中文错因解释(取最近一次非空) |
| examples | JSONField(list) | 最多 5 条:`{entry_id, snippet}`(错词所在句的短上下文) |
| occurrence_count | PositiveInt | 累计出现次数 |
| attempt_count | PositiveInt | 训练总次数 |
| correct_count | PositiveInt | 训练答对次数 |
| current_streak | PositiveInt | 当前连对 |
| status | CharField | `active` / `mastered`,默认 active |
| first_seen_at / last_seen_at | DateTime | 采集时间戳 |
| last_practiced_at | DateTime null | 最近训练时间 |
| source_refs | JSONField(list) | 来源 WritingEntry 的 entry_id 列表,去重 |
| metadata | JSONField(dict) | 预留(如用户手动编辑标记) |

约束/索引:
- `UniqueConstraint(fields=["user", "normalized"], name="unique_spelling_word_per_user")`。
- `Index(fields=["user", "status", "last_practiced_at"])`、`Index(fields=["user", "updated_at"])`。

## 4. 服务层(`apps/writing/spelling_services.py`)
- `harvest_spelling_words(user) -> int` —— §2。
- `spelling_drill_library(user, *, scope="active") -> dict` —— 先 harvest 再返回 `{"items": [...], "count": n, "stats": {...}}`。
  - `scope`:`active`(默认,未掌握)/`mastered`/`all`。
  - 每项 payload:`word_id, correct_spelling, wrong_forms, chinese_gloss, explanation, examples, occurrence_count, attempt_count, correct_count, current_streak, status, last_practiced_at`。
  - `stats`:`{total, active, mastered, accuracy}`(accuracy = correct_count/attempt_count,无尝试则 0)。
- `record_spelling_attempt(user, word_id, typed) -> dict` —— 训练判分:
  - 归一比较:`typed.strip().lower() == normalized`(忽略首尾空格、大小写)。
  - 对:`attempt_count++`、`correct_count++`、`current_streak++`、`last_practiced_at=now`;**`current_streak >= 4` 自动 `status="mastered"`**(MVP 掌握线)。
  - 错:`attempt_count++`、`current_streak=0`、`last_practiced_at=now`。
  - 返回:`{correct: bool, correct_spelling, current_streak, status, explanation}`(答错才回 `correct_spelling`+`explanation` 用于揭示;答对不回正确答案以免被看穿,前端已知道对)。
- `update_spelling_word(user, word_id, payload) -> dict` —— 用户手动操作:
  - `action=="master"` → status=mastered;`action=="reset"` → status=active 且 streak=0;`action=="edit_gloss"` → 改 `chinese_gloss`(标 `metadata.gloss_edited=true`,之后 harvest 不再覆盖)。
- `delete_spelling_word(user, word_id)` —— 从错词库移除(软移除即可:可加 `status="dismissed"` 或真删,选真删更简单)。

**复用现有约定**:错误抛 `WritingError`(`apps/writing/validation.py`),鉴权用现有 `require_user`,JSON 解析用现有 helper——照 `apps/speaking/corpus_services.py` 的 takeaway 系列写法对齐,别造新风格。

## 5. 视图 + 路由(`apps/writing/views.py` + `config/urls.py`)
对齐现有 takeaway 路由风格(见 `config/urls.py` 67-71):
- `GET  api/writing/spelling-words?scope=active|mastered|all` → `spelling_drill_library`
- `POST api/writing/spelling-words/<word_id>/attempt`(body `{typed}`)→ `record_spelling_attempt`
- `PATCH api/writing/spelling-words/<word_id>`(body `{action, ...}`)→ `update_spelling_word`
- `DELETE api/writing/spelling-words/<word_id>` → `delete_spelling_word`

用 `@require_http_methods` + `require_user`,与 `writing_takeaway_detail_view` 一致(刚加过 POST 支持,参考它)。

## 6. 前端(SPA)
- **新增** `web/static/spelling-drill.js`,在 `config/urls.py`(参考 19 行 `corpus-takeaway.js` 注册)+ `web/static/index.html`(带 `?v=` 版本串)注册,**复用** `styles.css` 现有语料卡类(`.p2-seasonal-card` 等),不另造一套视觉。
- 入口:放进现有"语料库 / 写作"区域,新增一个 **「拼写错词训练」** 面板(与 takeaway 并列)。
- **错词库视图**:卡片列表,每卡显示正确拼写、你写过的错拼(`wrong_forms`)、中文释义(有则显)、出现次数、掌握进度(streak/已掌握徽标)。支持切 `active/mastered/all`。
- **背写训练视图**(核心):
  1. 逐词出题,**遮住正确拼写**,显示提示:中文释义(若有)+「你之前写成:<wrong_form>」+ 一个输入框。
  2. 用户敲入 → 调 attempt 接口判分。
  3. 对:绿勾、streak+1,自动下一词;连对到 4 自动标"已掌握"并提示。
  4. 错:红叉、揭示正确拼写 + 中文错因解释,可「再试一次」。
  5. 可选「提示」按钮:露首字母 / 显示字母数(纯前端,不消耗判分次数)。
  6. 每卡有「标记已掌握」「移出错词库」操作(调 PATCH/DELETE)。
- 文案中文,与全站一致;无新依赖、不引 CDN。

## 7. 测试(必须,放 `apps/writing/tests.py` 或新 `test_spelling.py`)
- 采集:`inline_annotations[type=spelling]` 进库;`spelling_correction_summary` 的 `x -> 正确：y（中文）` 被解析、gloss 入库。
- 去重:同一对词多种错拼合并到一条,`wrong_forms` 去重。
- 过滤:短语(含空格)/非字母 token 不进库。
- 幂等:重复 harvest 不重复建条、不重置 streak/status。
- 判分:大小写/空格归一后判对;答对 streak++、连对4 自动 mastered;答错 streak 归零并回正确答案+解释。
- 手动操作:master/reset/edit_gloss(edit 后 harvest 不覆盖)/delete。
- 接口:四个路由方法限定与鉴权(未登录 401/403,沿用现有断言风格)。

## 8. 红线
- **不新增 AI 调用**;数据全部来自现有 `analysis_payload`。
- **中文释义查不到就留空,绝不编造**;gloss 兜底只能查 `LOCAL_TAKEAWAY_WORD_TRANSLATIONS` 这种确定词表。
- **不改动评分/批改管线行为**,只读 `analysis_payload`;不动 `inline_annotations`/`spelling_correction_summary` 的生成逻辑。
- 复用现有 `UserOwnedModel`/`WritingError`/`require_user`/takeaway 代码风格,别另起炉灶。
- 不泄露 key;不在 URL 放敏感数据。前端无新外部依赖、不引 CDN。
- 加了模型就要 `makemigrations`,且 `makemigrations --check` 干净。

## 9. 验收(用户)
- [ ] 有过拼写错误的作文用户,打开页面能看到错词库自动汇出(错词+正确拼写+中文释义[有则])。
- [ ] 背写训练:遮词→输入→判对错;答错揭示正确拼写与解释;连对到掌握线自动「已掌握」。
- [ ] 可手动标已掌握 / 移出 / 切换 active|mastered|all。
- [ ] 重开页面再采集,进度不丢、不重复建条。
- [ ] 无短语/噪声词混入;无编造中文释义。
- [ ] `manage.py check`、`makemigrations --check`、`apps.writing` 全测通过。

## 10. 实现顺序建议
1. 模型 + migration。
2. `spelling_services.py`:harvest → library → attempt → update/delete。
3. 视图 + 路由(对齐 takeaway)。
4. 测试(§7)。
5. 前端 `spelling-drill.js` + 注册 + 复用语料卡样式。
6. 自查 §8/§9 后交用户验收。
