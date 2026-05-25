# Prevent Speaking Coaching From Commenting On Non-Speaking Noise

## Goal

口语 AI 辅导必须只评价口语表达能力本身，不能点评大小写、标点、书面格式、ASR/转写噪声等与真实口语表现无关的问题。

## What I Already Know

- 用户报告案例：原始转写包含 `at University`，AI 的 `display_transcript` 已清理为 `at university`，但 `ai_coaching` 仍然点评“这里不需要大写”。
- 当前提示词已经要求基于 `display_transcript`，但模型仍可能回头引用 raw transcript 的噪声。
- `acceptable_coaching_markdown()` 目前只检查是否有语法纠错部分和是否泄露系统词，没有拦截“大小写/标点/书面格式”这类非口语点评。

## Requirements

- Speaking turn feedback prompt 明确加入反例：不要点评大小写、标点、书面格式、转写显示格式、ASR 噪声。
- Coaching 校验层拒绝包含明显非口语点评的 AI 输出。
- 回归测试覆盖 `at University` / 大小写点评案例。
- 不改变用户可见报告结构。

## Acceptance Criteria

- [x] `acceptable_coaching_markdown()` 拒绝点评大小写/标点/书面格式的 coaching。
- [x] `turn_feedback_with_codex()` 遇到这类 coaching 时失败，不把它保存为 codex 成功结果。
- [x] Batch turn feedback 同样复用该校验。
- [x] Existing speaking tests pass for the changed area.

## Out of Scope

- 不重写整个口语评分链路。
- 不改前端 UI。
- 不处理写作报告提示词。

## Technical Notes

- Main files: `backend_django/apps/speaking/services.py`, `backend_django/apps/speaking/tests.py`.
