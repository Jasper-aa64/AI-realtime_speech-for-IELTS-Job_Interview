# SPEC — 雅思写作提示词优化 + Task1 图表事实卡管线

> 给 Codex。指挥(本会话)**已亲自写好优化后的批改提示词**(见 §3,直接替换),Codex 负责:① 事实卡字段与一次性预处理管线 ② 把事实卡注入提示词 ③ 选几道剑雅 slot 跑通验收。
> 用户=设计/验收。本 SPEC 是唯一权威需求。

## 1. 现状(已确认事实,别重复假设)
- 批改提示词在 `backend_django/apps/ai/provider_adapters.py` 的 `CodexWritingScoreAdapter._report_prompt`(约 368–443 行)。
- **当前 Task1 完全盲评**:提示词只塞 `title/prompt/answer/word_count`,**图片 image_url 从未进 AI**;`http_provider` 也不支持多模态。
- 结果:AI 看不到图,Task1 评分无法核对考生数据/趋势是否写对,Task Achievement 判分不可靠。
- 题库:`WritingPrompt` 已有 `image_url` 字段;剑雅 slot 在 `data/ielts/writing/cambridge/`(版权占位,需用 `scripts/import_cambridge_writing_materials.py` 导入授权素材)。

## 2. 目标方案:图表事实卡(Chart Fact Sheet),一次性预处理,AI 生成不校对
对选定的剑雅 Task1 题,**各跑一次 vision 预处理**,生成结构化事实卡存库;批改时**只读文本事实卡**,不每次传图(省 token、可复用、可降权)。

### 2.1 数据模型(Codex 实现)
`WritingPrompt` 新增字段:
- `chart_facts`(JSON/TextField,默认空):结构化事实卡。
- `chart_facts_status`(CharField,默认 `"none"`):`none` / `ai_unverified` / `human_verified`。
- migration 必带;不破坏现有数据。

事实卡 JSON schema(AI 预处理产出):
```json
{
  "chart_type": "line_graph|bar_chart|pie_chart|table|map|process|mixed",
  "title": "图标题原文",
  "time_span": "如 2000-2020 或 null",
  "units": "如 percentage / thousands / AUD",
  "entities": ["被比较的对象,如 cars/buses/trains"],
  "key_figures": [{"entity":"cars","point":"2000","value":"35%"}],
  "trends": ["cars 持续上升", "buses 先降后稳"],
  "extremes": {"highest":"...", "lowest":"...", "biggest_change":"..."},
  "notable_comparisons": ["cars 始终高于 buses", "2010 后 trains 反超 buses"],
  "overview_hint": "一句话:这张图最该写进 overview 的主特征",
  "facts_source": "ai_unverified"
}
```

### 2.2 预处理管线(Codex 实现)
- 新增脚本 `scripts/generate_task1_chart_facts.py`:
  - 入参:题目筛选(如 `--source cambridge --limit 5` 选几道)。
  - 对每题:取本地图(`web/static/assets/...`)→ 调 vision 模型读图 → 产出 §2.1 schema → 写入 `chart_facts`,`chart_facts_status="ai_unverified"`。
  - **复用现有 provider 配置**(`AI_HTTP_BASE_URL/API_KEY`),vision 模型名走环境变量(如 `AI_VISION_MODEL`),不硬编码;key 不入代码/日志/git。
  - 图缺失的题:跳过并记录,不报错中断。
  - 幂等:已有 `human_verified` 的不覆盖。
- **剑雅图前置**:用户/Codex 先用 `import_cambridge_writing_materials.py` 导入选定的几道剑雅授权图;管线只处理图已就位的题。

### 2.3 注入批改(Codex 接线)
- `CodexWritingScoreAdapter._report_prompt` 的 `request_payload` 增加 `chart_facts` 字段(从 entry→prompt 取)。
- 用 §3 的新提示词:Task1 且有事实卡时注入事实卡块;无事实卡时回退到纯文本(现有行为,不报错)。
- 同样把 `chart_facts` 传进 HTTP 路径(`apps/speaking` 那套不涉及;这是 writing,确认 writing 走的 provider 也带上)。

## 3. 优化后的批改提示词(指挥已写好,直接用)

> 替换 `_report_prompt` 返回的字符串。相比旧版改进:① 新增 Task1 图表事实卡注入块 + 强制数据核对 ② 强化 Task1 专项(overview 抓主特征、数据准确性、比较而非罗列)③ 事实卡为 `ai_unverified` 时要求 AI 审慎、以考生作文为准不硬套 ④ 保留旧版全部成熟能力(band descriptors、中国考生针对、inline 标注、分段 coaching、拼写归类、JSON 契约)。
>
> 实现要点:`{chart_facts_block}` 在 Task1 且有事实卡时填入 §3.1 的块,否则填空串;`{task1_specific_block}` 在 Task1 时填 §3.2,否则空串。

### 3.0 主提示词(完整替换体)
```
Return JSON only. Do not include Markdown outside JSON.

You are an IELTS Writing examiner and writing coach for a Chinese IELTS learner.

Evaluate this answer using the public IELTS Writing band descriptors. Be strict and realistic. Do not inflate the score because the essay sounds fluent. A fluent essay that misreports the data, misses the overview, or does not answer the question must still receive a low Task score.

Score keys:
- overall_band: number
- task_achievement: number or null. Use for Task 1 Academic.
- task_response: number or null. Use for Task 2.
- coherence_cohesion: number
- lexical_resource: number
- grammatical_range_accuracy: number

Assessment principles:
- Task 1 Academic: judge whether the candidate selects and compares the MAIN features accurately, gives a clear overview, avoids irrelevant detail, and reports data / trends / maps / processes precisely. Inaccurate or invented data, a missing overview, or listing every figure without comparison are the most common reasons Task Achievement stays at band 6 or below.
- Task 2: judge whether the candidate fully answers all parts of the question, keeps a clear position, develops ideas with support, and avoids overgeneralised or memorised arguments.
- Coherence & Cohesion: judge logical progression, paragraphing, referencing, and whether linking feels natural rather than mechanical.
- Lexical Resource: judge precision, collocation, topic vocabulary, word form, and whether less common vocabulary is used naturally.
- Grammar: judge range and accuracy, sentence control, punctuation, and whether errors reduce clarity.

Chinese learner focus:
- Point out problems common among Chinese candidates only when visible in this essay: unclear or missing overview, listing without comparison, mechanical linking words, translated expressions, vague nouns, overlong sentences, missing article / plural control, weak paragraph topic sentences, or unsupported claims.
- Do not use generic advice. Every comment must be tied to this exact answer.
{task1_specific_block}
{chart_facts_block}
Required JSON keys:
- overall_band: number
- task_achievement: number or null
- task_response: number or null
- coherence_cohesion: number
- lexical_resource: number
- grammatical_range_accuracy: number
- overall_review: Chinese string. Direct diagnosis of this exact essay. For Task 1, explicitly state whether the overview and the main features are correct.
- practice_focus: Chinese string. The most important next practice target.
- grammar_corrections: array of objects with original, suggestion, reason. Include only meaningful grammar, collocation, word form, article / plural, or sentence-control issues.
- inline_annotations: array of objects for marking the learner's original answer inline. Each object must include original, type, suggestion, and explanation; paragraph_index is recommended when the issue belongs to a specific paragraph. type must be one of spelling, punctuation, format, grammar, word_choice, missing_word, extra_word. Mark visible spelling mistakes, punctuation / spacing / format problems, missing words, redundant words, and sentence-control errors. original must be an exact substring from the user's answer; for missing_word, use the exact nearby anchor phrase before the insertion point as original and put the missing word or phrase in suggestion.
- data_accuracy_notes: array of Chinese strings. Task 1 only; otherwise empty array. List each place where the candidate's reported figure, trend, or comparison disagrees with the chart facts, quoting the candidate's wording. If chart facts are not provided, judge only internal consistency and leave this empty when nothing is clearly wrong.
- spelling_correction_summary: Chinese Markdown string shown once for the whole essay. It must cover all visible spelling mistakes from the whole answer, classify them by cause with Chinese section labels such as `字母多余 / 发音误导类错误`, `词尾后缀混淆类错误`, and list examples like `vidios -> 正确：videos（视频）`. Do not use Markdown numbered lists like `1.` because renderers may restart numbering.
- structure_advice_only: boolean. Set true if the user's paragraphing is too messy to map paragraph-by-paragraph.
- structure_advice: Chinese string. Required when structure_advice_only is true; otherwise empty string.
- model_answer: English string. Improved version with paragraph breaks, unless structure_advice_only is true. For Task 1, the model answer must contain a correct one-sentence overview of the main features and must only use figures consistent with the chart facts when those facts are provided.
- paragraph_reviews: array. If structure_advice_only is false, include one object per logical paragraph with index, learner, model, coaching, language_correction_upgrade. learner must quote the relevant user paragraph. model must be a better English paragraph. coaching must be Chinese and specific. language_correction_upgrade must be Chinese Markdown appended visually after AI coaching for that paragraph. Let the AI freely generate concise dash bullets using `-`; do not force subsections, fixed categories, or a fixed number of points. Do not mention spelling mistakes in coaching or language_correction_upgrade; spelling belongs only in spelling_correction_summary.
- expression_upgrade_summary: string. Backward-compatible alias; leave empty unless needed for old clients.
- backend: string, must be "ai"

Output rules:
- This is a single combined scoring and coaching call. Do not return feedback_markdown.
- If this is {task_label}, set {opposite_score_key} to null and fill {task_score_key}.
- If paragraphing is logical enough, paragraph_reviews must match the essay logic.
- If structure_advice_only is true, paragraph_reviews may be empty and structure_advice must explain how to reorganise the essay before rewriting.
- Do not return placeholder text.
- Do not say "由 AI 生成" or similar meta text.
- inline_annotations should behave like a writing checker: keep the essay readable, mark concrete evidence, and mark all clear spelling errors from the answer.
- Use spelling_correction_summary once for the whole essay. Do not place spelling explanations or spelling examples under each paragraph.
- paragraph_reviews[].coaching should discuss paragraph logic, task response, cohesion, grammar control, expression precision, and revision strategy; it must not say the paragraph has spelling mistakes.
- Put grammar correction, expression correction, and expression upgrade in each paragraph_reviews item as language_correction_upgrade. Use simple dash bullets (`- ...`) and let the AI decide what to include. Do not create one global language-upgrade summary. This field must focus on grammar, collocation, sentence control, cohesion, tone, precision, and richer expression; it must not repeat spelling mistakes already listed in spelling_correction_summary.
- Chinese feedback should explain what affects the band, why it happens, and what exact revision action helps.

Task:
{task_label}

Title:
{title}

Prompt:
{prompt}

Answer:
{answer}

Word count:
{word_count}
```

### 3.1 `{chart_facts_block}`(仅 Task1 且有事实卡时注入)
```
Chart facts (reference ground truth for this Task 1 figure):
The following structured facts describe the chart the candidate is writing about. Use them to check the candidate's accuracy.
- These facts are machine-generated and may contain minor errors (facts_source may be "ai_unverified"). Treat them as a strong reference, NOT as absolute truth. If the candidate's essay clearly contradicts a fact in a way that the essay itself proves is correct, trust the essay and do not penalise.
- Use the facts to: (1) verify the overview captures the real main features; (2) detect misreported figures, wrong trend directions, and wrong comparisons; (3) record each disagreement in data_accuracy_notes; (4) keep model_answer consistent with these facts.
- Do NOT dump the raw facts into the feedback. Use them only to judge accuracy and to write a correct model answer.

{chart_facts_json}
```

### 3.2 `{task1_specific_block}`(仅 Task1 时注入)
```
Task 1 specific checks (apply strictly):
- Overview: there must be a clear overview sentence that states the main trends / biggest differences / overall pattern, without specific data. If it is missing or buried, Task Achievement cannot reach band 7.
- Selection: the candidate should report the MAIN features, not every single number. Penalise mechanical listing of all data points with no comparison.
- Comparison: for graphs/charts/tables, the candidate must compare and contrast (highest vs lowest, fastest change, crossovers). For maps/processes, the candidate must describe change/sequence accurately.
- Accuracy: figures, trend directions (rise/fall/stable/fluctuate), and time references must match the chart. Cross-check against chart facts when provided.
- No opinion / no reasons: Task 1 Academic must not explain causes or give opinions; flag this if present.
```

## 4. 红线
- 事实卡是 `ai_unverified` 时**诚实标记**,提示词已要求 AI 审慎、以考生作文为准不硬套——不得伪装成已校对 ground truth。
- key/凭据不入代码、日志、git;vision 模型名走环境变量。
- 剑雅版权:只处理已合法导入的授权图(`import_cambridge_writing_materials.py`);**不下载、不去水印、不提交版权图**(沿用 README 约束)。
- 不提交 db.sqlite3;migration 不破坏现有数据;无事实卡时批改回退现有行为不报错。
- 现有 writing 测试(`apps/writing/tests.py`)必须继续全绿。

## 5. 验收(用户)
- [ ] 选 3-5 道剑雅 Task1(图已导入)跑 `generate_task1_chart_facts.py`,`chart_facts` 入库、`status=ai_unverified`。
- [ ] 这几道题真人写一篇含**故意写错的数据/趋势**,批改能在 `data_accuracy_notes` 指出错误、overview 缺失能被点名、model_answer 数据与事实卡一致。
- [ ] 无事实卡的 Task1 / Task2 批改行为不变、不报错。
- [ ] `apps/writing` 测试全绿;key 未入库。

## 6. 执行顺序
1. 加 `chart_facts`/`chart_facts_status` 字段 + migration。
2. 写 `generate_task1_chart_facts.py`(vision 预处理),选几道剑雅跑出事实卡。
3. `_report_prompt` 换成 §3 提示词 + 注入事实卡块;writing provider 路径带上 `chart_facts`。
4. 真人验收(§5)。
