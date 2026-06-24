# IELTS Speaking Simulator — 实施计划

> 面向 Codex/Claude Code 的施工指南。每个 Phase 独立可测试，按顺序执行。

---

## 项目背景

本项目在现有 C++ 技术面试模拟器基础上，新增 IELTS 口语考试模拟功能。
核心基础设施（PortAudio 录音/播放、OpenAI Realtime STT/TTS、LLM curl client、状态机）**全部复用，不改动**。
新增一套 `ielts/` 命名空间的模块，以及 `main_ielts.cpp` 作为独立 CLI 入口。

---

## 目录结构（目标态）

```
project/
├── src/
│   ├── ielts/
│   │   ├── ielts_manager.cpp       # P1→P2→P3 主流程编排
│   │   ├── part1_session.cpp       # P1：题库 Q&A + 追问
│   │   ├── part2_session.cpp       # P2：Cue Card + 计时录音
│   │   ├── part3_session.cpp       # P3：话题讨论 + 追问
│   │   ├── question_bank.cpp       # 扫描/加载 data/ielts/**/*.json
│   │   └── scorer.cpp              # shell-out codex CLI 评分
│   └── main_ielts.cpp              # CLI 入口（独立于 main.cpp）
│
├── include/
│   └── ielts/
│       ├── ielts_manager.h
│       ├── part1_session.h
│       ├── part2_session.h
│       ├── part3_session.h
│       ├── question_bank.h
│       └── scorer.h
│
├── data/ielts/
│   ├── part1/
│   │   ├── 2025_autumn_family.json
│   │   ├── 2025_autumn_education.json
│   │   └── 2025_autumn_work_leisure.json
│   ├── part2/
│   │   └── 2025_autumn_topics.json
│   ├── part3/                      # 空目录（话题由 P2 topic 动态生成）
│   └── prompts/
│       ├── scorer_system.md        # IELTS 4 维评分 rubric（给 codex）
│       └── p3_question_gen.md      # P3 讨论题生成模板（给 claude）
│
└── docs/
    └── IELTS_SIMULATOR_PLAN.md     # 本文件
```

---

## Phase 1 — 题库 + QuestionBank 模块

**目标**：能从 JSON 文件加载题目，随机或顺序取题。

### 1.1 题库 JSON 格式

文件名规范：`{year}_{season}_{topic}.json`

```json
{
  "season": "2025-autumn",
  "part": 1,
  "topic": "family",
  "questions": [
    "Do you live with your family or on your own?",
    "How often do you spend time with your family?",
    "What activities do you enjoy doing with your family?",
    "Are you close to all members of your family?"
  ]
}
```

P2 格式（`part2/2025_autumn_topics.json`）：
```json
{
  "season": "2025-autumn",
  "part": 2,
  "topics": [
    {
      "title": "Describe a time you helped someone",
      "bullets": [
        "Who you helped",
        "What you did to help",
        "Why you helped them"
      ],
      "p3_theme": "helping_others"
    }
  ]
}
```

### 1.2 QuestionBank 接口

```cpp
// include/ielts/question_bank.h
namespace ielts {

struct P1Question {
    std::string topic;
    std::string question;
};

struct P2Topic {
    std::string title;
    std::vector<std::string> bullets;
    std::string p3_theme;  // 传给 P3
};

class QuestionBank {
public:
    // 扫描 data/ielts/part1/ 下所有 .json，加载题目
    void LoadPart1(const std::string& data_dir);
    // 扫描 data/ielts/part2/
    void LoadPart2(const std::string& data_dir);

    // 随机抽取 n 道 P1 题（可跨话题）
    std::vector<P1Question> SampleP1Questions(int n = 5) const;
    // 随机抽取一个 P2 话题
    P2Topic SampleP2Topic() const;

private:
    std::vector<P1Question> p1_questions_;
    std::vector<P2Topic>    p2_topics_;
};

} // namespace ielts
```

### 1.3 当季真题样本（占位，后续替换）

`data/ielts/part1/2025_autumn_family.json`：
- Do you live with your family?
- How much time do you spend with your family each week?
- What do you like to do together with your family?
- Did you have a large family when you were growing up?
- Is family important in your culture?

`data/ielts/part1/2025_autumn_education.json`：
- Where are you studying / where did you study?
- Do you enjoy your studies?
- What is your favourite subject?
- Do you prefer studying alone or with others?
- How do you feel about exams?

`data/ielts/part1/2025_autumn_work_leisure.json`：
- Do you work or are you a student?
- What do you do in your free time?
- Do you prefer indoor or outdoor activities?
- Have your hobbies changed as you've grown older?
- Is it important to have hobbies?

`data/ielts/part2/2025_autumn_topics.json`（3 个话题）：
- Describe a book you recently read
- Describe a time you helped a stranger
- Describe a place you would like to visit

---

## Phase 2 — Scorer 模块

**目标**：给定英文口语转写文本，返回 4 维 IELTS Band 分。

### 2.1 codex CLI 调用方式

```bash
codex --model gpt-4o-mini \
      --quiet \
      --full-auto \
      -i "$(cat data/ielts/prompts/scorer_system.md)" \
      "Please score the following IELTS speaking transcript:\n\n{transcript}"
```

期望输出（JSON）：
```json
{
  "fluency_coherence": 6.5,
  "lexical_resource": 6.0,
  "grammatical_range": 6.5,
  "pronunciation_estimate": 6.0,
  "overall_band": 6.5,
  "feedback": "Good use of cohesive devices. Try to vary vocabulary more..."
}
```

### 2.2 scorer_system.md（IELTS 评分 Prompt）

内容要点：
- 你是 IELTS 官方考官，按 IELTS Speaking 4 维标准评分
- 每维 0–9，步长 0.5
- 输出严格 JSON（无多余文字）
- Pronunciation 基于词汇多样性和句式复杂度估分（因无音频）
- 给出 50 字以内英文 feedback

### 2.3 Scorer 接口

```cpp
// include/ielts/scorer.h
namespace ielts {

struct IELTSScore {
    float fluency_coherence;
    float lexical_resource;
    float grammatical_range;
    float pronunciation_estimate;
    float overall_band;
    std::string feedback;
};

class Scorer {
public:
    explicit Scorer(const std::string& data_dir);  // 读取 prompts/scorer_system.md
    IELTSScore Score(const std::string& transcript);
private:
    std::string system_prompt_;
    std::string RunCodex(const std::string& prompt);  // popen() shell-out
};

} // namespace ielts
```

---

## Phase 3 — P1 Session

**目标**：走通 P1 完整流程。

### 流程状态机

```
kP1Start
  → (load questions) →
kP1QuestionAsked      [AI TTS 读题]
  → (user speaks) →
kP1ListeningAnswer    [RealtimeClient 录音+STT]
  → (transcript ready) →
kP1Evaluating         [可选：ShouldFollowUp?]
  → kP1FollowUp 或 kP1NextQuestion
  → (all questions done) →
kP1Done               [显示临时分数]
```

### Part1Session 接口

```cpp
// include/ielts/part1_session.h
namespace ielts {

class Part1Session {
public:
    Part1Session(QuestionBank& bank,
                 services::RealtimeClient& rt_client,
                 Scorer& scorer);

    void Start();               // 开始 P1，阻塞直到 P1 结束
    IELTSScore GetScore() const;
    std::string GetTranscript() const;  // 完整 P1 对话转写
};

} // namespace ielts
```

### 追问逻辑（复用自 interview_manager）

从 `InterviewSession::ShouldFollowUp()` 提取：
- transcript 词数 < 30 → 追问
- 回答未涉及关键词（why/because/because of） → 追问
- 追问模板：`"Could you tell me more about that?"` / `"Why do you feel that way?"`

---

## Phase 4 — P2 Session

**目标**：Cue Card 展示 + 60s 准备 + 2min 录音。

### CLI 显示

```
╔══════════════════════════════════════════╗
║  IELTS Speaking - Part 2                 ║
╠══════════════════════════════════════════╣
║  Describe a book you recently read.      ║
║                                          ║
║  You should say:                         ║
║   • What the book was about              ║
║   • Why you chose to read it             ║
║   • What you learned from it             ║
╚══════════════════════════════════════════╝

Preparation time: [▓▓▓▓▓▓▓▓░░] 42s remaining
Press ENTER to start speaking early...
```

```
Recording...  [▓▓▓▓▓▓░░░░░░░░░] 1:12 / 2:00
Press ENTER to stop early
```

### Part2Session 接口

```cpp
namespace ielts {

class Part2Session {
public:
    Part2Session(QuestionBank& bank,
                 services::RealtimeClient& rt_client,
                 Scorer& scorer);

    void Start();                   // 展示 Cue Card → 准备 → 录音
    IELTSScore GetScore() const;
    P2Topic GetTopic() const;       // P3 需要
    std::string GetTranscript() const;
};

} // namespace ielts
```

### 计时实现

- 用 `std::chrono` + 独立线程更新进度条
- `kbhit()` 检测 ENTER（macOS：`tcsetattr` raw mode）
- 超时自动停止

---

## Phase 5 — P3 Session

**目标**：基于 P2 话题生成 4–5 讨论题，模拟双向对话。

### P3 问题生成（调用 claude CLI）

```bash
claude -p "$(envsubst < data/ielts/prompts/p3_question_gen.md)" \
       --allowedTools none \
       -- "P2 Topic: ${p2_topic}, Theme: ${p3_theme}"
```

`p3_question_gen.md` 模板：
```
Generate 5 IELTS Part 3 discussion questions for the following topic.
Questions should progress from concrete to abstract.
Output: JSON array of strings only.
```

### Part3Session 接口

```cpp
namespace ielts {

class Part3Session {
public:
    Part3Session(const P2Topic& topic,
                 services::RealtimeClient& rt_client,
                 Scorer& scorer);

    void Start();
    IELTSScore GetScore() const;
    std::string GetTranscript() const;
};

} // namespace ielts
```

---

## Phase 6 — IELTSManager + 报告 + CLI 入口

### IELTSManager 主流程

```cpp
// src/ielts/ielts_manager.cpp
void IELTSManager::RunFullExam() {
    // P1
    Part1Session p1(bank_, rt_client_, scorer_);
    p1.Start();

    // P2
    Part2Session p2(bank_, rt_client_, scorer_);
    p2.Start();

    // P3
    Part3Session p3(p2.GetTopic(), rt_client_, scorer_);
    p3.Start();

    // 综合报告
    GenerateReport(p1.GetScore(), p2.GetScore(), p3.GetScore());
}
```

### 报告 JSON 格式

```json
{
  "timestamp": "2025-10-07T14:30:00",
  "candidate": "User",
  "parts": {
    "part1": {
      "score": { "fluency_coherence": 6.5, "lexical_resource": 6.0, ... },
      "transcript": "..."
    },
    "part2": {
      "topic": "Describe a book...",
      "duration_seconds": 98,
      "score": { ... },
      "transcript": "..."
    },
    "part3": {
      "theme": "reading_habits",
      "score": { ... },
      "transcript": "..."
    }
  },
  "overall": {
    "band": 6.5,
    "feedback": "..."
  }
}
```

### main_ielts.cpp CLI 菜单

```
IELTS Speaking Simulator v1.0
================================
[1] Full Mock Exam (P1 + P2 + P3)
[2] Practice Part 1 only
[3] Practice Part 2 only
[4] Practice Part 3 only
[5] View last report
[q] Quit
```

### CMakeLists.txt 修改

新增编译目标 `IELTSSpeakingSimulator`：
- 源文件：`src/ielts/*.cpp` + `src/main_ielts.cpp`
- 复用：`src/common/*.cpp` + `src/services/*.cpp`（不含 `src/interview/` 和 Qt 相关）
- 链接：`PortAudio`、`libcurl`、`nlohmann_json`（与现有相同）

---

## Phase 7 — 题库扩充接口

**动态加载**：`QuestionBank::LoadPart1(dir)` 扫描目录下所有 `.json`，无需重新编译。

**添加新题步骤**：
1. 在 `data/ielts/part1/` 新建 `YYYY_season_topic.json`
2. 重启程序，自动加载

---

## 实施顺序（给 Codex 的任务拆分）

| 顺序 | 任务 | 关键文件 |
|------|------|---------|
| 1 | 题库 JSON + QuestionBank 实现 | `question_bank.h/cpp` + `data/ielts/part1/*.json` |
| 2 | Scorer + prompts | `scorer.h/cpp` + `data/ielts/prompts/scorer_system.md` |
| 3 | P1 Session（含追问） | `part1_session.h/cpp` |
| 4 | P2 Session（含计时 UI） | `part2_session.h/cpp` |
| 5 | P3 Session（含 claude CLI 出题） | `part3_session.h/cpp` + `p3_question_gen.md` |
| 6 | IELTSManager + 报告 | `ielts_manager.h/cpp` |
| 7 | main_ielts.cpp + CMakeLists 更新 | `main_ielts.cpp` + `CMakeLists.txt` |

---

## 关键约束

- **不改动**现有 `src/interview/`、`src/ui/`、`main.cpp`、`main_qt.cpp`
- 新增 `src/ielts/` 模块只 `#include` `common/` 和 `services/` 头文件
- shell-out（popen）用于 `codex` 和 `claude`，超时设为 30s
- 评分在用户说完之后异步调用，不阻塞录音流程
- 所有字符串 UTF-8，题目英文，日志中文

---

## 当季真题来源（占位说明）

> 以下为 2025 秋季当季真题样本（来源：IELTS 备考社区整理）。
> 用户后续会提供完整题库 JSON，直接替换 `data/ielts/part1/` 下文件即可。

目前内置话题：
- **Family** — 5 题
- **Education** — 5 题  
- **Work & Leisure** — 5 题
- **P2 Topics** — 3 个话题

---

*文件生成时间：2026-05-07 | 版本：v1.0*
