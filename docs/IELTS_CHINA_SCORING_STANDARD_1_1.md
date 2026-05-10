# IELTS 中国口语评分标准与样本调研 v1.1

日期：2026-05-10

## 0. 研究定位

这份文档回答一个产品问题：我们的 IELTS 口语模拟系统如果面向中国考生，应该如何理解“符合中国的雅思评分标准”。

结论是：中国大陆 IELTS 口语考试不使用一套独立于官方 IELTS 的评分体系。产品应该使用全球统一的 IELTS Speaking rubric，再叠加中国官方材料、CSE 对接语境和中国学习者常见问题，形成本地化解释与 AI 辅导层。

## 1. 核心结论

1. **评分标准仍然是官方 IELTS Speaking 4 维标准。** 不能新增“中国版 Band”或独立换算公式。
2. **中国语境的差异主要在解释层。** 中国官方材料提供中文 band descriptor、CSE 对接结果和本地化备考说明，但不改变 IELTS 0-9 band 标准。
3. **AI 评分必须区分“官方分数”和“练习估分”。** 当前项目如果用 LLM 或启发式评分，应标注 scorer backend、是否缺音频、是否缺 transcript、是否 fallback。
4. **中国考生辅导应更重视证据。** 建议不能只说“多用高级词汇”，而要指出 transcript 中的具体问题：展开不足、重复、句式单一、衔接弱、发音不可评估等。
5. **现有样本库可支撑 MVP，但不能直接作为评分校准集。** 当前本地样本里 53/53 个历史 turn 缺 transcript，无法验证真实语言表现。

## 2. 官方 IELTS 口语基线

IELTS Speaking 的官方流程：

| 部分 | 官方考试含义 | 产品实现应对齐的重点 |
| --- | --- | --- |
| Part 1 | 身份确认和熟悉话题问答 | 不应固定成机械 10 题训练；应保留真实面试感 |
| Part 2 | Cue card，1 分钟准备，最长 2 分钟 long turn | 重点是连续表达、结构和细节展开 |
| Part 3 | 围绕 Part 2 主题做更抽象的双向讨论 | 重点是解释、比较、让步、推测和观点展开 |

官方评分维度：

| 维度 | 评分关注点 | AI 辅导应输出什么 |
| --- | --- | --- |
| Fluency and Coherence | 流利度、连贯性、停顿、重复、逻辑组织 | 指出答案是否能持续展开、是否有清晰结构 |
| Lexical Resource | 词汇灵活性、话题词、搭配、准确性 | 指出重复词、泛词和更自然的替代表达 |
| Grammatical Range and Accuracy | 句型范围、复杂结构、准确性 | 指出简单句堆叠、时态、从句和错误模式 |
| Pronunciation | 可理解度、音素、重音、节奏、语调 | 只有有音频分析时才给实测建议；否则标为未评估 |

总分口径：四项等权平均后，按官方规则取到最近的 0.5 band。产品不要使用“一律向上取整”的总分算法。

## 3. 中国语境下的评分解释

### 3.1 不是单独标准

中国官方 IELTS 站点提供了中文的口语评分标准说明，但中文版本是解释材料，不是独立评分标准。中文 PDF 明确说明英文版为准。

产品表述建议：

* 正确：`中国考生适用的 IELTS 口语评分解释`
* 正确：`基于官方 IELTS rubric，并结合中国英语能力等级量表语境解释`
* 避免：`中国 IELTS 专用评分标准`
* 避免：`中国版 Band 分数`

### 3.2 CSE 的作用

British Council China 说明 IELTS 已与中国英语能力等级量表（CSE）完成对接。这对产品有两个价值：

1. 报告可以补充“该 band 大致对应的能力描述”，帮助中国用户理解水平。
2. CSE 不能替代 IELTS band，也不能用来重算口语分。

推荐做法：在报告中加入一个“中文能力解释”区块，但不要影响主 band。

## 4. 样本调研

### 4.1 外部样本来源

| 样本类型 | 来源 | 用途 |
| --- | --- | --- |
| 官方流程样本 | IELTS Speaking format 和 official sample tasks | 校准 P1/P2/P3 流程与计时 |
| 官方评分样本 | IELTS scoring detail 和 Speaking band descriptors | 校准 4 维评分与总分计算 |
| 中国官方解释样本 | 中国官方口语评分标准 PDF | 生成中文解释层 |
| 中国本地标准映射 | British Council China CSE 对接页 | 给中国用户解释能力等级语境 |
| 中国大陆考生背景 | 2024-2025 中国大陆雅思成绩大数据报告 | 判断产品应重视口语训练与报告可读性 |
| 官方研究样本 | IELTS speaking features / pronunciation / lexical resource 研究 | 校准 AI feedback 应关注的语言证据 |

### 4.2 本项目样本

当前仓库样本统计：

| 样本 | 当前数量 | 判断 |
| --- | ---: | --- |
| Part 1 JSON 文件 | 9 | 可做话题池 |
| Part 1 问题数 | 60 | 足够支撑 MVP 练习 |
| Part 2 JSON 文件 | 2 | 文件数少，但 topic 总量可用 |
| Part 2 cue-card topics | 15 | 可支撑演示和基础训练 |
| 历史 attempt 文件 | 3 | 只适合检查报告结构 |
| 历史 turn 数 | 53 | 全部缺 transcript |
| 缺 transcript turn | 53/53 | 不能作为评分校准样本 |

这说明项目已经有“练习题样本”，但还没有“真实答案样本”。如果要做严谨评分，需要补充带 transcript、音频、人工校准 band 的样本。

## 5. 对 AI 辅导的具体要求

### 5.1 Part 1

中国考生常见问题通常不是“不会回答”，而是回答过短、只有事实、缺自然扩展。

AI 辅导应输出：

* 直接回答是否清楚
* 是否补了 1 个理由或细节
* 是否使用自然口语，而不是背诵模板
* 是否有不必要的长停顿或重复

### 5.2 Part 2

Part 2 的核心不是背完整范文，而是在 2 分钟内组织一段可持续、可理解、有细节的 long turn。

AI 辅导应输出：

* cue card bullets 是否都覆盖
* 是否有时间、人物、地点、原因等具体信息
* 是否能从事实讲到感受或影响
* 是否有明显断裂或重复

### 5.3 Part 3

Part 3 需要更抽象的思考。中国考生常见问题是答案仍停留在个人经历，缺少概括、比较和推理。

AI 辅导应输出：

* 是否回答了抽象问题，而不是继续讲个人故事
* 是否有比较、原因、结果、让步或预测
* 是否能处理 follow-up 的追问压力
* 是否能用自然连接词组织观点

### 5.4 Pronunciation

如果没有真实音频分析，不能给用户“Pronunciation Band 7”这样的实测结论。

推荐状态：

* `not_assessed`：没有音频或未接入发音评测
* `estimated_from_audio`：有自动音频评测，但不是官方 examiner 分
* `human_calibrated`：有人工标注样本或人工复核

## 6. 对产品的改进计划

### P0：必须修

* 修正总分算法：四维平均后取最近 0.5，而不是永远向上取整。
* 报告中明确 `Pronunciation` 是否真实评测。
* 报告中显示 scoring backend：official-like LLM、heuristic fallback、audio unavailable 等。

### P1：提升真实性

* 将 Part 1 从固定 10 题改为更接近真实面试的若干熟悉话题问答。
* Part 2 增加 optional follow-up，不要只停在 cue card。
* Part 3 使用真实讨论逻辑：从 Part 2 主题延展，而不是固定高强度题数。
* 为每条 AI 建议绑定 transcript 证据。

### P2：建立中国考生样本库

* 每个 band 至少收集 5/6/7/8 四档样本。
* 每条样本包含：question、candidate answer、transcript、audio status、4 维评分、中文解释、Band 7 rewrite。
* 样本按问题类型分类：展开不足、词汇重复、句法单一、跑题、发音不可评估。
* 区分官方样题、训练样题、项目生成题，避免混成“真题”。

## 7. 给当前项目的落地口径

产品主张可以写成：

> 面向中国考生的 IELTS Speaking 模拟训练。评分解释基于官方 IELTS Speaking band descriptors，并结合中国英语能力等级量表语境进行中文化说明。

不要写成：

> 中国雅思官方评分系统。

当前项目下一步最合适的 MVP 不是继续堆题，而是先把评分解释和样本证据补严谨：

1. 分数计算对齐官方口径。
2. 反馈按 4 个 rubric 维度拆开。
3. 每条建议引用候选人答案证据。
4. 对中国考生提供中文解释，但保留英文 rubric 作为最终标准。

## 8. 参考来源

* [IELTS Academic format: Speaking](https://ielts.org/take-a-test/test-types/ielts-academic-test/ielts-academic-format-speaking)
* [IELTS scoring in detail](https://ielts.org/take-a-test/your-results/ielts-scoring-in-detail)
* [IELTS Speaking sample tasks PDF](https://cdn.ielts.org/Sample-tests/ielts-speaking-sample-tasks-2023.pdf)
* [中国官方口语评分标准 PDF](https://backoffice.ielts.chinaielts.org/api/assets/ielts-cms/26ab0d00-d846-44e9-ad76-253d064ce623/uobds-speakingfinal.pdf)
* [British Council China: CSE 对接结果](https://www.britishcouncil.cn/exams/cse/results)
* [2024-2025 中国大陆雅思成绩大数据报告](https://www.chinaielts.org/press-office/IELTS-%20Chinese-Mainland%20-Big-Data-Report-2024-2025)
* [IELTS research: speaking features and band descriptors](https://ielts.org/researchers/our-research/research-reports/the-relationship-between-speaking-features-and-band-descriptors-a-mixed-methods-study)
* [IELTS research: pronunciation and interlanguage phonology](https://ielts.org/researchers/our-research/research-reports/the-contribution-of-interlanguage-phonology-accommodation-to-inter-examiner-variation-in-the-rating-of-pronunciation-in-oral-proficiency-interviews)
* [IELTS research: lexical resource dimension](https://ielts.org/researchers/our-research/research-reports/an-investigation-of-the-lexical-dimension-of-the-ielts-speaking-test)
