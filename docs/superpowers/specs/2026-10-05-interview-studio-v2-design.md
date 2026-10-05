# 模拟面试 v2 设计：对标雅思口语（语料 · 流程 · 面试官 · 百分制）

日期：2026-10-05　状态：用户已确认结构（"结构差不多对的，可以先执行"），第三节按推荐方案执行
前置：`2026-10-05-qt-desktop-studio-design.md`（桌面端、模式切换器）；现有 `apps.interview` 文字版 MVP。

## 1. 目标与边界

把模拟面试做成雅思口语的同构产品：

| 雅思口语 | 模拟面试 |
|---|---|
| Mock 完整模考 | **完整面试**：自我介绍 → 项目（每个项目：介绍 + 追问）→ 知识点 → 奖项 → 反问 |
| P1 题库 + 我的语料 | **知识点**：通用题库 + 按简历技术栈生成的题，每题「我的答法 / AI 参考」 |
| P2 题卡 + 素材 | **项目讲述**：每个项目一条讲述稿（AI 起草，用户改成自己的话） |
| P3 追问 | **项目追问**：面试官针对讲述追问，追问语料挂在项目下 |
| P2 特殊题 | **自我介绍**、**奖项（ACM/竞赛）**各一条讲述稿 |
| — | **JD**：岗位题 + **反问环节**语料 |
| 标准 / 高强度 | **标准模式 / 追问压力** |
| Band 报告 | **百分制报告**（含能力边界） |

作答方式：复用雅思录音链路（MediaRecorder 录音 → 上传 → 服务器火山 ASR 转写 → 文字可修改后提交），同时保留打字作答。面试官引擎与输入方式解耦，原生 C++ 实时语音完成后只替换输入层。

不做：音频发音评估；把 AI 估分当招聘结论；自动拉取公司信息。

## 2. 内容层

### 2.1 面试画像 `InterviewProfile`（每用户一份）

- `resume_text`、`resume_modules`（AI 拆块结果：`[{key, kind, title, summary}]`，kind ∈ self_intro / project / tech_stack / award）、`resume_updated_at`
- `jd_text`、`jd_summary`（AI 提炼：岗位方向、核心要求列表）、`jd_updated_at`
- 定制页顶部「简历 | JD」开关，二选一显示；两边独立上传、独立生成，都可以存在。

### 2.2 面试语料 `InterviewCorpusEntry`（一张表，按 kind 区分）

| kind | 来源 | question | corpus_text（我的答法） | ai_draft（AI 参考） |
|---|---|---|---|---|
| `self_intro` | 简历 | 「请做一下自我介绍」 | 用户改写 | AI 起草 |
| `project` | 简历，每项目一条 | 「介绍一下 X 项目」 | 讲述稿 | AI 起草 |
| `project_followup` | 简历/练习，挂 `parent`=项目 | 预判追问 | 用户答法 | AI 参考 |
| `knowledge` | 精选题库 / 简历技术栈 / 自定义 | 知识点题，`group`=大类 | 用户答法 | AI 参考（按需生成） |
| `award` | 简历（有才生成） | 「讲讲你的 ACM 经历」 | 讲述稿 | AI 起草 |
| `jd_question` | JD | 岗位相关题 | 用户答法 | AI 参考 |
| `reverse_question` | JD / 自定义 | 反问时要问的问题 | 想了解的点 | AI 建议 |

字段：`entry_id`（公开 id）、`kind`、`group`、`title`、`question`、`corpus_text`、`ai_draft`、`source`（curated / resume / jd / custom / practice）、`source_key`（精选题 id 或简历模块 key，用于重新生成时保留用户编辑）、`parent`、`order`、`metadata`。

规则：
- 重新拆简历时按 `source_key` 匹配：已有条目只更新 `ai_draft`，**不覆盖 `corpus_text`**；消失的模块条目保留并标记 `metadata.orphaned`。
- 精选题的语料条目在用户第一次保存答法时创建（同 P1 语料 `question_id` 唯一）。
- 自定义题（手动加的题、AI 生成后改过的题）都是语料条目，`source=custom`。
- 练习中可「存为我的答法」：把本题回答写回对应条目的 `corpus_text`。

## 3. 练习流程

### 3.1 入口（侧栏，照雅思）

面试首页 · **完整面试**（大卡）+ 分段 **项目 / 知识点 / 反问**（同 P1/P2/P3 三格）· 面试报告 · 面试语料库 · 简历 / JD 定制。

### 3.2 场次计划（服务器生成 `plan`，阶段 stage）

- **完整面试**：`self_intro`(1) → `project`（简历里每个项目：讲述 1 题 + 追问，按强度）→ `knowledge`（4–6 题：简历技术栈题优先，不足用精选题补；有 JD 时 JD 题参与）→ `award`（简历里有才问，1 题）→ `reverse`（1–2 轮）。
- **项目**分段：选 1 个或全部项目，题卡式：「介绍一下 X」+ 建议 1 分钟准备、2 分钟讲述（可跳过准备），然后追问。
- **知识点**分段：按大类或勾选题目，P1 式连问（沿用现有题库页的勾选/随机）。
- **反问**分段：面试官说「你有什么想问我的吗？」，候选人提问，面试官回答（AI，基于 JD），再评价提问质量；可多轮。
- 没有简历时：完整面试和项目分段提示先上传简历；知识点和反问仍可用（反问没有 JD 时用通用岗位语境）。

### 3.3 作答

每题：题目卡（阶段标签 + 题目）→ 录音（复用雅思录音组件的约束/设备选择，MediaRecorder webm/opus）或打字 → 录音上传后服务器转写 → 显示转写稿，可修改 → 「提交回答」。可展开「我的答法」作参考；提交后可「存为我的答法」。

## 4. 面试官引擎

每次提交回答后，服务器调用 AI `next_step`：输入阶段、题目、回答、本主题已追问层数、强度、最近 3 轮对话、相关语料标题；输出：

```json
{"action": "follow_up | probe | next", "prompt": "…", "signal": "strong | adequate | weak", "evidence": "一句话依据", "boundary": "可选：暴露出的能力边界"}
```

- `follow_up`：答得好 → 追细节、追深度（为什么这样设计、量化结果、取舍）。
- `probe`：答得不好或含糊 → 降一级或换角度，确定候选人的边界（会什么、不会什么）以便打分。
- `next`：本主题已足够 → 进入计划中的下一题。
- 强度：**标准**每个主问题最多 1 层追问；**追问压力**最多 3 层（项目阶段最多 4 层），AI 返回 `next` 时提前结束。
- 硬上限与校验在服务器：超过层数强制 `next`；AI 失败 → 记录 `decision.status=failed` 并按计划进入下一题（不编造追问），前端提示「面试官暂时无法追问」。
- 反问阶段用 `reverse_reply`：回答候选人问题 + 一句话评价提问质量。
- 每轮 `signal/evidence/boundary` 存进 turn 的 `metadata.decision`，供报告使用。

## 5. 百分制报告

完成后 `score_report`（AI）：

| 维度 | 满分 |
|---|---|
| 技术深度（知识点 + 追问表现） | 30 |
| 项目表达（讲述结构、量化、个人贡献） | 25 |
| 逻辑与结构（先结论、STAR、取舍） | 20 |
| 岗位匹配（有 JD 时；无 JD 时并入技术深度） | 15 |
| 沟通与反问 | 10 |

输出总分、各维度分 + 依据、**能力边界**小结（来自各轮 boundary）、每题点评、下一步练习建议。服务器校验分数范围与合计。报告注明「AI 根据本次文字回答估计，不评估发音，也不代表招聘结果」。AI 失败时保留文字记录，可重试。

## 6. 界面

- **面试首页**：照雅思首页——左侧标题区、**中间轮播**（占位幻灯：完整面试 / 项目讲述 / 知识点 / 面试报告，图片位先用占位块）、右侧数据面板（场次、已答题、最近练习、语料待完善数）、下方 Practice paths。
- **练习页**：照雅思练习页——顶部「标准模式 / 追问压力」开关 + 「我的 X 语料」按钮；阶段进度条（自我介绍 · 项目 · 知识点 · 奖项 · 反问）；题目卡；录音按钮 + 转写区 + 打字切换；「面试官思考中…」状态。
- **面试语料库**：照「我的 P1 语料库」——分栏 项目 / 知识点 / 自我介绍与奖项 / JD 与反问；卡片列表；编辑弹窗左「我的答法」右「AI 参考」（可「采用」），项目卡下展开追问语料。
- **定制页**：顶部「简历 | JD」分段开关；简历：PDF/粘贴 → 拆分 → 模块预览（每块可改讲述稿、删除、补充）→ 写入语料；JD：粘贴 → 生成岗位题与反问 → 写入语料。
- 布局沿用当前规则：窗口不滚动，每页指定滚动区；只在桌面端出现（浏览器无入口）。

## 7. 数据与接口

新增/调整（全部在 `apps.interview`，需登录、CSRF、按用户隔离）：

- `GET/POST profile/resume/`（POST multipart：resume_text / resume_file → 拆分并写语料）、`POST profile/jd/`、`GET profile/`
- `GET corpus/?kind=`、`POST corpus/`（新建自定义）、`PATCH/DELETE corpus/<id>/`、`POST corpus/<id>/draft/`（按需生成 AI 参考）
- `POST sessions/`：`{part: full|project|knowledge|reverse, intensity: standard|pressure, project_keys?, category?, question_ids?}`；旧 `mode=general|custom` 继续兼容
- `POST sessions/<id>/turns/<tid>/audio/`（上传 → 转写，返回 transcript，不推进）
- `POST sessions/<id>/turns/<tid>/answer/`（提交文字 → 引擎决策 → 返回新状态）
- `POST sessions/<id>/turns/<tid>/save-corpus/`
- `POST sessions/<id>/report/`（百分制）
- 模型：`InterviewProfile`、`InterviewCorpusEntry`；`InterviewSession` 加 `part`、`intensity`、`plan`、`score`；`InterviewTurn` 加 `stage`、`corpus_entry_id`、`audio_path`、`answer_source`（typed / voice）。

## 8. 错误处理

- AI 不可用：拆简历/JD 失败给明确错误、保留已填内容；引擎失败按计划下一题；报告失败可重试。
- ASR 失败：提示重录或改打字，录音文件保留以便重试转写。
- 并发：沿用现有 lease（同一场次同一时刻只有一个 AI 请求）；重复提交同一回答幂等。
- 迁移只新增表和可空/默认字段；开发和验证使用独立 QA 数据库，**用户自己的 `db.sqlite3` 迁移前先询问**。

## 9. 测试

- 后端：画像拆分（mock provider）保留用户编辑；语料 CRUD 与隔离；计划生成（有/无简历、有/无 JD、阶段顺序）；引擎层数上限、AI 失败回退、非法输出；反问；音频上传转写（mock ASR）；报告分数校验。
- 前端：node 测试覆盖模式/阶段渲染、提交流程、引擎状态、语料编辑、定制开关；桌面端实机走一场完整面试（打字 + 一次录音转写）。

## 10. 分期执行

1. 后端：模型 + 语料 API + 画像拆分（简历 / JD）。
2. 后端：场次计划 + 面试官引擎 + 音频转写 + 百分制报告。
3. 前端：侧栏 / 首页轮播 / 语料库 / 定制页。
4. 前端：练习页（录音 + 引擎循环）/ 报告页。
5. 桌面端实机验收，更新交接文档。
