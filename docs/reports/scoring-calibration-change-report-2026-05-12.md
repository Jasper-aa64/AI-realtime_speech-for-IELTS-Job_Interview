# IELTS Speaking 评分校准改动汇报

日期：2026-05-12  
提交：`e806779 feat: calibrate IELTS speaking scoring`

## 背景

本次改动专注于优化 IELTS Speaking 的 AI 评分标准，让练习分数更接近真实口语考试体验，尤其避免国内考生常见场景下的虚高分：

- 答案听起来流利，但内容模板化。
- Part 2 过短，没有持续展开。
- Part 3 只有简单观点，没有原因、比较、例子或抽象讨论。
- 词汇重复，句式单一。
- 没有真实音频发音评估时，文本分数把总分抬得过高。

重要原则：没有新增“中国版雅思分”。系统仍然只使用官方 IELTS Speaking 四项标准，国内语境只作为练习评分的校准依据。

## 改动文件

- `data/ielts/prompts/scorer_system.md`
- `web/ielts_server.py`
- `tests/test_ielts_web_server.py`
- `.trellis/spec/backend/quality-guidelines.md`
- `.trellis/tasks/05-12-ielts-speaking-realistic-scoring-calibration/`

## 核心改动

### 1. 强化 AI 评分 Prompt

更新了 `scorer_system.md`，要求 Codex 按官方 IELTS Speaking rubric 打分，同时更谨慎处理：

- 短答案。
- 套话、模板化答案。
- 重复简单词汇。
- 离题或弱相关答案。
- Part 2 覆盖不足。
- Part 3 没有展开分析。

现在 prompt 明确要求：不能因为答案看起来流利就给 6.5 或 7.0；Band 7 必须有清楚展开、自然衔接、灵活词汇和较稳定的语法控制。

### 2. 增加后端确定性评分校准

在 `web/ielts_server.py` 中新增 `calibrate_realistic_score()`，用于在 Codex 或 fallback 分数生成之后再次校准，避免模型偶尔给出虚高分。

校准会检查：

- 词数。
- 展开标记，例如 `because`、`for example`、`however`。
- 模板化表达，例如 `it is very important`、`in modern society`。
- 词汇重复程度。
- 句式是否过于简单。
- Part 2 / Part 3 是否达到对应考试部分的表达要求。

### 3. Part 2 / Part 3 更严格

Part 2 现在要求更像真实长回合：

- 太短会被限制在较低区间。
- 没有 cue-card 展开，不能轻易上 6.5。
- 模板化但流利的答案会被压回 5.0-5.5 附近。

Part 3 现在要求更像真实讨论：

- 不能只有一句观点。
- 需要原因、例子、比较、结果或抽象分析。
- 没有讨论深度时，不能因为英文顺就给高分。

### 4. 发音缺失时不再虚构分数

如果没有真实音频发音评估：

- `pronunciation_estimate` 保持 `null`。
- 不从 transcript 猜发音。
- 总分会有保守上限，防止只靠 FC/LR/GRA 三项把 overall 拉高。

同时修正了一个边界：Part 1 的正常短答不会被过度压低。相关测试已经覆盖。

## 新增测试

新增或更新了测试，覆盖：

- 短而泛泛的 Part 2 不能拿高分。
- 模板化 Part 2 会被更严格限制。
- Part 3 没有展开时不能虚高。
- 没有发音评估时，`pronunciation_estimate` 仍然是 `null`。
- 文本很强但无发音时，总分保持保守。
- 正常 Part 1 短答不会被错误压低。
- Codex JSON 输出解析后仍会经过后端校准。

## 验证结果

已通过：

```bash
python -m py_compile web/ielts_server.py tests/test_ielts_web_server.py
python -m unittest tests.test_ielts_web_server
```

测试结果：33 个测试通过。

## 当前效果

评分会更接近真实 IELTS Speaking 练习估分：

- 5.5 / 6.0 会成为“能回答但展开、词汇、语法不稳定”的常见合理区间。
- 6.5+ 不再轻易给，需要明确证据。
- 7.0 需要明显的内容展开、自然衔接、词汇灵活度和语法控制。
- 没有真实发音评估时，总分不会被文本表现过度抬高。

## 剩余边界

- 目前校准主要基于 transcript 文本和已有音频评估状态；如果浏览器转写质量差，评分仍会受 transcript 质量影响。
- 真正稳定的 Pronunciation 分数仍依赖 Azure Speech 或后续接入更可靠的音频分析。
- 国内考区反馈只用于“练习校准”，不是官方地域扣分规则。
