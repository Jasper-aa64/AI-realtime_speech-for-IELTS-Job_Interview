# IELTS Speaking Simulator — 雅思口语考试模拟系统

## Goal

将现有 C++ 技术面试模拟器改造为 IELTS 口语考试模拟系统。
复用已有音频采集/播放、Realtime STT、LLM 评分客户端等基础设施，
新增三段式考试流程（P1/P2/P3）、题库管理、IELTS 标准评分，以及可动态扩充的当季真题题库。

问题生成：调用 `claude` CLI（Claude Code）non-interactive 模式。
评分：调用 `codex` CLI（OpenAI Codex CLI）按 IELTS 4 维评分标准评分。

---

## Requirements

### P1 — 个人话题问答 (Interview / Familiar Topics)

- 从 JSON 题库随机或顺序抽取 4–6 题
- 每题：AI 语音读题 → 用户口语回答（RealtimeClient STT）→ AI 追问（≤1次）→ 进入下题
- 题库支持按话题分类（家庭、学习、工作、爱好等）
- 可在运行时动态加载新题库 JSON 文件

### P2 — 个人陈述 (Long Turn)

- 显示 Cue Card（话题 + 3 个 bullet points）
- **准备阶段**：倒计时 60 秒，用户可随时按 Enter 跳过
- **陈述阶段**：开始计时（目标 2 min），按 Enter 或自动 2 min 结束录音
- 录音完整保存为 WAV，STT 转文字存入 session 记录
- P2 topic 传递给 P3

### P3 — 双向讨论 (Discussion)

- 基于 P2 话题，AI 提出 4–5 个深度讨论问题
- 每题支持 AI 追问（复用 `InterviewSession::ShouldFollowUp` 逻辑）
- 追问逻辑：若回答偏短/模糊，AI 自动追问一次

### 评分系统

- 每段结束后调用 `codex` CLI 对转写文本评分
- 4 维评分：Fluency & Coherence / Lexical Resource / Grammatical Range & Accuracy / Pronunciation (估分)
- 每维 0–9 分（0.5 步），整体 Band = 四维均值，向上取整到最近 0.5
- 输出 JSON 格式评分报告 + 文字反馈

### CLI 界面

- 纯终端（无需 Qt GUI），彩色输出（ANSI escape codes）
- 主菜单：[1] 完整模拟考 [2] 单独练习 P1/P2/P3 [3] 查看历史报告 [q] 退出
- P2 计时进度条实时显示

### 题库格式 (JSON)

```json
{
  "season": "2025-autumn",
  "part": 1,
  "topic": "family",
  "questions": [
    "Do you live with your family or on your own?",
    "How often do you spend time with your family?",
    "What do you enjoy doing together as a family?"
  ]
}
```

---

## Acceptance Criteria

- [ ] P1：能从题库随机抽题，完整走通一轮（4 题含追问）
- [ ] P2：倒计时 + 计时器正常，录音正常结束
- [ ] P3：AI 根据 P2 话题生成并提问 4 题
- [ ] 评分：调用 codex CLI 返回 4 维 Band 分及文字建议
- [ ] 报告：保存 JSON 报告到 `reports/ielts_YYYYMMDD_HHMMSS.json`
- [ ] 题库：可在 `data/ielts/part1/` 目录下新增 JSON 文件，下次启动自动加载

---

## Definition of Done

- 可在 macOS 终端完整跑通 P1+P2+P3 一轮
- 评分报告正确生成
- 新增 `data/ielts/` 下有当季真题示例（≥3 个话题）
- README 更新 IELTS 用法说明

---

## Technical Approach

### 复用层（零改动或极少改动）

| 组件 | 文件 | 复用方式 |
|------|------|----------|
| PortAudio 音频录制/播放 | `services/audio_manager` | 直接复用 |
| OpenAI Realtime STT | `services/realtime_client` | 直接复用 |
| LLM API Client (curl) | `services/llm_client` | 复用，换 system prompt |
| 状态机模式 | `common/interview_state` | 扩展新增 IELTS 状态 |
| 追问决策逻辑 | `interview/interview_manager` | 提取 `ShouldFollowUp()` |
| Logger / Config | `common/` | 直接复用 |

### 新增层

```
src/ielts/
  ielts_manager.cpp        # 主控：P1→P2→P3 流程编排
  part1_session.cpp        # P1：题库驱动 Q&A
  part2_session.cpp        # P2：Cue Card + 计时录音
  part3_session.cpp        # P3：话题追问
  question_bank.cpp        # 扫描加载 data/ielts/**/*.json
  scorer.cpp               # 调用 codex CLI 评分，解析输出

include/ielts/
  (对应 .h 文件)

data/ielts/
  part1/
    2025_autumn_family.json
    2025_autumn_education.json
    2025_autumn_work.json
  part2/
    2025_autumn_topics.json
  part3/          # 空目录，话题由 P2 动态传入
  prompts/
    scorer_system.md       # codex 评分 system prompt（含 IELTS 4 维 rubric）
    p3_question_gen.md     # claude 生成 P3 讨论题的 prompt

src/main_ielts.cpp         # 新的 CLI 入口
```

### CLI 调用约定

```bash
# 问题生成（P3 讨论题）
claude -p "$(cat data/ielts/prompts/p3_question_gen.md)" \
       --allowedTools none \
       -- "Topic: Urbanization and rural life"

# 评分
codex --model gpt-4o-mini \
      --system "$(cat data/ielts/prompts/scorer_system.md)" \
      "Transcript: [user's text]"
```

---

## Decision (ADR-lite)

**Context**: 需选择 LLM 调用方式（直接 API curl vs. CLI shell-out）

**Decision**: 
- **问题生成** 用 `claude -p` CLI（轻量、context 隔离、无需额外 API key 管理）
- **评分** 用 `codex` CLI（已有 OpenAI key 配置，4 维 rubric 用 gpt-4o-mini 足够）
- **STT** 继续用 RealtimeClient（已有稳定的 WebSocket 流式转写）
- **TTS**（读题）继续用 RealtimeClient 的 TTS 能力

**Consequences**: 
- shell-out 增加约 0.5–2s 延迟（可接受，评分在答题结束后异步进行）
- 需要在评分前将 transcript 清洗成纯文本

---

## Out of Scope

- 发音分（Pronunciation）当前为估分（基于词汇多样性 proxy），不做真正音频分析
- 多用户/账号系统
- 云端数据同步
- 移动端
- 中文界面（考试全程英文）

---

## Open Questions

（已解决）

- [x] CLI vs GUI → CLI 模式（`main_ielts.cpp`）
- [x] 评分 API → codex CLI (`codex-cli 0.128.0`)
- [x] 问题生成 → claude CLI (`claude 2.1.132`)
- [ ] **题库来源**：用户将提供真题，当前用占位真题。Codex 实现时等待用户更新。

---

## Technical Notes

- PortAudio: `include/services/audio_manager.h` — 16kHz int16 input, 24kHz float32 output
- Realtime WS: `include/services/realtime_client.h` — 已有 STT + TTS 双向流
- LLMClient: curl-based, OpenAI-compatible, `include/services/llm_client.h`
- 状态机: 单例 `InterviewStateMachine::Instance()` — 需扩展 IELTS 状态
- 追问: `InterviewSession::ShouldFollowUp()` + `GetFollowUpQuestion()` 可直接提取
- codex CLI: `/opt/homebrew/bin/codex` v0.128.0
- claude CLI: `~/.local/bin/claude` v2.1.132 (Claude Code)
- 现有报告格式参考: `interview_report_*.json` 根目录下有多份样本
