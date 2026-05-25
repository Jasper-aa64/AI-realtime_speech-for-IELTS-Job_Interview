# P3 功能完善落地建议

日期：2026-05-25  
范围：IELTS Studio 口语 Part 3 训练、P2 报告衔接、P2 串题素材库里的相关 P3 追问

## 调研来源

- British Council 的 Part 3 说明：Part 3 会围绕 Part 2 话题继续追问，更偏抽象议题和双向讨论，时长约 4-5 分钟。参考：https://takeielts.britishcouncil.org/take-ielts/prepare/free-ielts-english-practice-tests/speaking/part-3
- IELTS Speaking Band Descriptors：高分回答需要连贯展开、灵活使用话语标记、词汇灵活度、复杂句和发音控制。参考：https://ielts.org/cdn/ielts-guides/ielts-speaking-band-descriptors.pdf
- IELTS Speaking Key Assessment Criteria：评分关注 Fluency and Coherence、Lexical Resource、Grammatical Range and Accuracy、Pronunciation；其中 Fluency/Coherence 明确看连续表达、逻辑衔接、讨论阶段标记和相关性。参考：https://ielts.org/cdn/ielts-guides/ielts-speaking-key-assessment-criteria.pdf
- 当前代码观察：P3 已有独立 topic 入口、Normal/High intensity、从 P2 报告生成 P3、从 P2 素材 metadata 读取 `p3_follow_up_text`、报告页按钮 `根据本次 P2 生成 P3 追问`。

## 当前 P3 的核心问题

1. 入口还不像一个完整训练系统  
   现在 P3 入口主要是 topic chips + intensity 开关。用户不知道这次练的是“抽象讨论、对比、原因、影响、未来趋势”里的哪一种能力。

2. 从 P2 到 P3 的流程太跳  
   P2 报告右上角按钮会直接进入 P3 并自动开始。用户没有机会预览问题、选择训练重点、确认是否使用 P2 回答或已链接素材。

3. High intensity 还不是真正的动态追问  
   后端现在会生成 5 个 main questions，高强度时插入 follow-up turn，但 follow-up 基本来自同一个 `plan.follow_up`，容易重复，不像考官根据上一题回答继续追。

4. P3 追问素材还是“文本块”，不是结构化训练资产  
   P2 素材库里的相关 P3 追问目前用 Markdown 存，但系统只抽取带问号的行。缺少题型、难度、用途、来源、是否已练习等信息。

5. 报告反馈没有足够 P3 专项  
   当前评分能识别 P3 回答太短、缺少原因/对比/例子，但报告没有形成“P3 讨论能力画像”：是否会抽象化、是否能比较群体、是否能提出反方、是否能讨论长期趋势。

6. P3 没有复练闭环  
   P1 有语料库，P2 有串题素材库，P3 现在缺一个“追问计划 / 错题复练 / 下次重点”的闭环。

## 产品目标

把 P3 从“随机出几个讨论题”升级成：

- 能从 P2 回答自然延伸；
- 能让用户在开始前看到并调整训练计划；
- 能在练习中根据回答动态追问；
- 能在报告中指出 P3 专项能力缺口；
- 能把 P3 追问沉淀回素材库和复练队列。

## 建议的信息架构

### 1. P3 训练入口

新增一个 P3 Launch Panel，替代现在单薄的 topic chips：

- 训练来源：
  - `按话题练`：从题库主题开始。
  - `根据最近 P2 报告练`：默认选最近一次 P2。
  - `根据已链接 P2 素材练`：使用 P2 素材库里的相关 P3 追问。
  - `自定义主题`：手动输入一个 theme。
- 训练目标：
  - 抽象讨论
  - 原因与影响
  - 对比与让步
  - 未来趋势
  - 政策 / 社会层面
- 强度：
  - Normal：5 个主问题。
  - High：5 个主问题 + 每题一个动态追问。
  - Drill：只练一个能力点，3-4 题快速循环。

### 2. P3 题目计划预览

用户点击开始前，先生成一个 P3 Plan Preview：

```json
{
  "source": "p2_report",
  "theme": "Describe a successful business person you admire",
  "focus": "comparison_and_impact",
  "questions": [
    {
      "id": "q1",
      "type": "opinion_justify",
      "question": "Why do some people admire business leaders more than artists or scientists?",
      "target_moves": ["clear position", "reason", "contrast"]
    }
  ]
}
```

界面能力：

- 可以重新生成整套问题。
- 可以删除某一道不想练的问题。
- 可以切换 Normal / High / Drill。
- 可以从 P2 素材库的 `相关 P3 追问` 一键导入。
- 点击开始后再进入录音流程。

### 3. 动态追问引擎

High intensity 不应该提前固定所有 follow-up。建议流程：

1. 主问题录完。
2. 后端根据该题问题 + 用户回答 + 训练目标生成一个 follow-up。
3. 如果 AI 失败，用按题型的 fallback 追问。
4. 追问 turn 写入 attempt metadata，并生成 TTS。

fallback 按题型区分：

- opinion：`What might be the opposite view?`
- cause/effect：`Which factor do you think matters most, and why?`
- comparison：`How is this different for younger and older people?`
- future：`What could change this situation in the next ten years?`
- policy：`Should the government be involved, or should individuals decide?`

### 4. P3 追问素材库

不要把 P3 追问混回 P2 串题素材编辑窗口，但可以在 P2 素材详情中提供独立入口：

- `串题素材`：仍然只编辑 P2 素材正文。
- `相关 P3 追问`：打开独立 Markdown 编辑窗口。
- 后续升级为结构化编辑：
  - 追问问题
  - 题型
  - 目标能力
  - 难度
  - 是否来自 P2 报告
  - 最近练习结果

第一阶段仍可继续用 `metadata.p3_follow_up_text`，不需要数据库迁移；等功能稳定后再考虑单独表。

### 5. P3 报告专项升级

报告中新增 `P3 Discussion Skills` 模块：

- 抽象化能力：是否从个人经历上升到社会/群体层面。
- 观点展开：是否有观点 + 原因 + 例子 / 对比。
- 追问承接：是否回应了 follow-up，而不是重复主问题答案。
- 语言灵活度：是否有让步、条件句、比较结构、概括表达。
- 节奏与长度：每题词数、停顿、是否过短。

建议报告输出：

- `P3 Skill Map`：5 个维度的分数或状态。
- `Best Answer Moment`：本次最好的一个回答片段。
- `Fix Next`：下一次只改一个最关键问题。
- `Generate Drill`：一键生成 3 道针对弱点的 P3 drill。

## 后端落地建议

### 新增服务函数

- `build_p3_plan(payload) -> dict`
  - 输入 source/theme/focus/intensity/p2_answer/p3_follow_up_text。
  - 输出结构化问题计划。

- `generate_p3_dynamic_follow_up(turn, transcript, focus) -> dict`
  - 输入当前主问题和用户回答。
  - 输出下一道 follow-up turn。

- `score_p3_discussion_skills(attempt) -> dict`
  - 在报告生成阶段补充 P3 专项分析。

### API 建议

短期：

- 复用 `/api/p3/questions`，让它返回结构化 plan，而不只是 `questions + follow_up`。
- 复用 `/api/p3/follow-up`，让它接收 `question_type`、`focus`、`previous_answer`。

中期：

- `POST /api/p3/plan`
- `POST /api/p3/follow-up`
- `POST /api/p3/drill`

### metadata 建议

先不用迁移，写入 attempt / turn metadata：

```json
{
  "p3_source": {
    "type": "p2_report",
    "p2_attempt_id": "...",
    "p2_corpus_entry_id": "...",
    "theme": "..."
  },
  "p3_plan": {
    "version": 1,
    "focus": "comparison_and_impact",
    "intensity": "high",
    "questions": []
  }
}
```

## 前端落地建议

### P3 页面

- 把当前 `p3TopicPanel` 改成三段：
  - 来源选择
  - 训练目标
  - 题目计划预览
- `Start Part 3 practice` 只有在 plan ready 后才可点。
- 从 P2 报告进入时，不自动开始，先展示：
  - P2 cue card title
  - 我的 P2 回答摘要
  - 已链接素材 / P3 追问来源
  - 生成的 P3 plan

### P2 报告入口

现在按钮文案建议从：

`根据本次 P2 生成 P3 追问`

改为：

`生成 P3 训练计划`

点击后进入 P3 plan preview，而不是直接录音。

### P2 素材库入口

保留当前两个独立窗口：

- 主行点击：编辑串题素材。
- P3 icon：编辑相关 P3 追问。

增加状态显示：

- `P3 已填`
- `待补 P3`
- 可选：最近练过 / 未练过

## 推荐实施顺序

### Phase 1：把 P3 从“直接开始”改成“训练计划”

文件：

- `web/static/index.html`
- `web/static/app.js`
- `web/static/styles.css`
- `backend_django/apps/speaking/services.py`
- `backend_django/apps/speaking/views.py`

验收：

- 从 P3 导航进入时，可以选择来源、目标、强度。
- 从 P2 报告进入时，先看到 plan preview，不自动开始。
- 生成失败时有 fallback plan。

### Phase 2：结构化 P3 plan

验收：

- 每道题都有 `type`、`target_moves`、`source`。
- UI 能显示题型标签。
- 用户可以删题、换题、重新生成。

### Phase 3：动态追问

验收：

- High intensity 下，每个 follow-up 根据上一题回答生成。
- AI 失败时按题型 fallback。
- TTS 状态和 turn metadata 正常保存。

### Phase 4：P3 报告专项

验收：

- 报告里出现 P3 Discussion Skills。
- 至少包含抽象化、观点展开、对比让步、回答长度、追问承接 5 个维度。
- 可以一键生成下一组 P3 drill。

### Phase 5：P3 复练闭环

验收：

- 报告弱点进入 replay queue。
- P2 素材库里的 P3 追问能标记最近练习表现。
- 用户能从 P3 页面直接选择“继续练上次薄弱点”。

## 风险和约束

- 不要一开始就加数据库表；先用 metadata 验证产品形态。
- 不要把 P3 追问重新塞回 P2 串题素材正文窗口；必须保持独立入口。
- 动态追问会增加 TTS 和 AI 调用成本，需要 fallback 和超时策略。
- P3 plan preview 需要避免“太像题库编辑器”，用户主要目标还是快速开始练习。

## 最小可行版本

最小版本只做 4 件事：

1. P3 从 P2 报告进入时先展示 plan preview，不自动开始。
2. `/api/p3/questions` 返回结构化问题类型。
3. High intensity 的 follow-up 改成每题基于上一题回答生成。
4. P3 报告新增一个简洁的 Discussion Skills 模块。

这四件事完成后，P3 就会从“附属功能”变成一个能解释、能练、能复盘的完整训练模块。
