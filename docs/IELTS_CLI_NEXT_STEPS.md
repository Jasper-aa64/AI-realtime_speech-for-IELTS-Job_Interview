# IELTS Speaking CLI — 下一步施工计划

> 面向 Codex / Claude Code 的独立施工指南。每个 Phase 可独立执行，按顺序完成。
> 项目已有完整骨架（P1/P2/P3 Session + Scorer + QuestionBank），本文件只描述**缺口补全**。

---

## 现状快照（2026-05-08）

| 模块 | 状态 | 说明 |
|------|------|------|
| `Part1Session` | ✅ 完整 | Realtime STT + 追问逻辑完整 |
| `Part2Session` | ⚠️ 90% | 缺"按 Enter 开始"等待点 |
| `Part3Session` | ⚠️ 60% | 无 Realtime STT；追问只有 1 句硬编码；shell 命令有注入风险 |
| `Scorer` | ⚠️ 90% | codex 命令有 shell 注入风险 |
| 题库数据 | ⚠️ 占位 | 仅 2025_autumn 3 个 P1 + 1 个 P2，非真实真题 |
| `CaptureAnswerOrFallback` | ⚠️ 私有 | 定义在 part1_session.cpp anon namespace，P3 无法复用 |

---

## Phase 1 — 提取公共 STT 捕获函数

**目标**：让 P3 能用与 P1 完全相同的 STT 逻辑。

### 1.1 把 `CaptureAnswerOrFallback` 提升到头文件

文件：`include/ielts/realtime_speech_capture.h`

在已有的 `CaptureSpeechWithRealtime` / `RealtimeCaptureOptions` / `SpeechCaptureResult` 之后，新增：

```cpp
// Returns STT transcript (via Realtime) or falls back to terminal input.
// fallback_prompt: shown to user when STT is unavailable.
std::string CaptureAnswerOrFallback(
    interview::services::RealtimeClient& client,
    const std::string& fallback_prompt,
    int max_seconds = 75);
```

文件：`src/ielts/realtime_speech_capture.cpp`

实现（从 `part1_session.cpp` 的 anon namespace 搬过来，逻辑不变）：

```cpp
std::string CaptureAnswerOrFallback(
    interview::services::RealtimeClient& client,
    const std::string& fallback_prompt,
    int max_seconds)
{
    RealtimeCaptureOptions options;
    options.max_seconds = max_seconds;
    options.stop_on_first_final = true;
    options.allow_enter_stop = true;
    options.record_audio_without_realtime = false;
    options.status_label = "Listening";

    const auto capture = CaptureSpeechWithRealtime(client, options);
    if (capture.used_realtime_stt) {
        std::cout << "\033[2mTranscript:\033[0m " << capture.transcript << "\n";
        return capture.transcript;
    }
    if (!capture.fallback_reason.empty()) {
        // log warning but don't throw
    }
    std::cout << fallback_prompt << "\n> ";
    std::string answer;
    std::getline(std::cin, answer);
    return answer;
}
```

**注意**：`part1_session.cpp` 内部原有的 `CaptureAnswerOrFallback` anon 函数**保持不变**（不要删），这样不破坏 P1 编译。只是 P3 新增使用头文件版本。

---

## Phase 2 — P2：增加"按 Enter 开始准备"等待点

文件：`src/ielts/part2_session.cpp`

修改 `Part2Session::Start()`，在 `ShowCueCard` 与 `RunCountdown` 之间插入：

```cpp
void Part2Session::Start() {
    topic_ = bank_.SampleP2Topic();
    transcript_.clear();
    actual_duration_ = 0;

    ShowCueCard(topic_);
    SafeSpeak(rt_client_, "IELTS Speaking Part 2. " + topic_.title);

    // ---- NEW: wait for candidate to be ready ----
    std::cout << "\nPress [Enter] when you are ready to start your 1-minute preparation time...\n";
    {
        std::string discard;
        std::getline(std::cin, discard);
    }
    // ---- END NEW ----

    RunCountdown(prep_seconds_);
    RecordSpeech(speak_seconds_);
    score_ = scorer_.Score(transcript_);
}
```

---

## Phase 3 — P3：接入 Realtime STT + 多样追问

文件：`src/ielts/part3_session.cpp`

### 3.1 Include

新增：
```cpp
#include "ielts/realtime_speech_capture.h"
```

### 3.2 回答采集改 CaptureAnswerOrFallback

把 `Part3Session::Start()` 里的两处裸 `std::getline` 改为：

```cpp
// 主问题回答
const std::string answer = CaptureAnswerOrFallback(
    rt_client_, "Candidate answer transcript:");
transcript_ += "Examiner: " + question + "\nCandidate: " + answer + "\n";

// 追问回答
if (ShouldFollowUp(answer)) {
    const std::string follow_up = GetFollowUpQuestion(question, answer);
    std::cout << "\033[1;33mFollow-up:\033[0m " << follow_up << "\n";
    SafeSpeak(rt_client_, follow_up);
    const std::string fu_answer = CaptureAnswerOrFallback(
        rt_client_, "Follow-up answer transcript:");
    transcript_ += "Examiner: " + follow_up + "\nCandidate: " + fu_answer + "\n";
}
```

### 3.3 新增 `GetFollowUpQuestion` 方法

头文件 `include/ielts/part3_session.h` 中 private 区新增：

```cpp
std::string GetFollowUpQuestion(const std::string& question, const std::string& answer);
```

实现（`part3_session.cpp`）：

```cpp
std::string Part3Session::GetFollowUpQuestion(const std::string& question,
                                               const std::string& answer) {
    // 固定兜底池（轮询）
    static const std::vector<std::string> kFallbacks = {
        "Could you explain your reasoning in more detail?",
        "What makes you think that?",
        "Can you give a concrete example from your own experience?",
        "How does that compare to the situation in other countries?",
        "Do you think this will change in the future? Why?"
    };
    static int fallback_index = 0;

    // 主路径：claude CLI 生成上下文相关追问
    try {
        const std::string prompt =
            "You are an IELTS examiner. The candidate gave a short or thin answer.\n"
            "Generate ONE natural follow-up probe question in one sentence.\n"
            "Question: " + question + "\n"
            "Candidate answer: " + answer + "\n"
            "Output ONLY the question, no explanation.";

        const std::string claude_bin =
            std::filesystem::exists(std::filesystem::path(std::getenv("HOME") ? std::getenv("HOME") : "") / ".local/bin/claude")
            ? (std::filesystem::path(std::getenv("HOME")) / ".local/bin/claude").string()
            : "claude";

        // Write prompt to temp file, pass via stdin redirect (safer than shell substitution)
        const auto temp_path = std::filesystem::temp_directory_path() /
            ("ielts_followup_" + std::to_string(::getpid()) + ".txt");
        {
            std::ofstream out(temp_path);
            out << prompt;
        }
        const std::string cmd = claude_bin + " --allowedTools none -p " +
            ShellQuote(prompt.substr(0, 200)) +  // system prompt summary only
            " < " + ShellQuote(temp_path.string()) + " 2>/dev/null";

        // Simpler: pipe via echo-redirect pattern
        const std::string safe_cmd = claude_bin +
            " --allowedTools none --print " +
            ShellQuote(prompt) +
            " 2>/dev/null";

        std::array<char, 1024> buf{};
        std::string result;
        FILE* pipe = ::popen(safe_cmd.c_str(), "r");
        std::filesystem::remove(temp_path);
        if (!pipe) throw std::runtime_error("popen failed");
        while (fgets(buf.data(), static_cast<int>(buf.size()), pipe)) result += buf.data();
        ::pclose(pipe);

        // Trim whitespace
        while (!result.empty() && (result.back() == '\n' || result.back() == '\r' || result.back() == ' '))
            result.pop_back();
        if (!result.empty() && result.back() == '?') return result;
    } catch (...) {}

    const std::string fb = kFallbacks[fallback_index % kFallbacks.size()];
    ++fallback_index;
    return fb;
}
```

---

## Phase 4 — 修 Scorer shell 命令安全问题

文件：`src/ielts/scorer.cpp`

`Scorer::RunCodex` 当前命令：
```cpp
codex + " --model gpt-4o-mini --quiet --full-auto \"$(cat " + ShellQuote(temp_path) + ")\" 2>/dev/null"
```

问题：`"$(cat ...)"` 在双引号里，transcript 中的 `"` 或 `$` 会破坏 shell 解析。

修改为 stdin 重定向（文件已写入，用 `<` 传入）：

```cpp
std::string Scorer::RunCodex(const std::string& user_prompt) {
    const auto temp_path = std::filesystem::temp_directory_path() /
        ("ielts_scorer_" + std::to_string(::getpid()) + ".txt");
    {
        std::ofstream out(temp_path);
        if (!out) throw std::runtime_error("Failed to write Codex prompt");
        out << user_prompt;
    }

    const std::string codex_bin = std::filesystem::exists("/opt/homebrew/bin/codex")
        ? "/opt/homebrew/bin/codex" : "codex";

    // Use stdin redirect: codex reads from the temp file, no shell substitution needed
    const std::string command =
        codex_bin + " --model gpt-4o-mini --quiet --full-auto \"$(cat " +
        ShellQuote(temp_path.string()) + ")\" 2>/dev/null";
    // ↑ This is the EXISTING code. Replace with:
    // const std::string command =
    //     "cat " + ShellQuote(temp_path.string()) + " | " +
    //     codex_bin + " --model gpt-4o-mini --quiet --full-auto /dev/stdin 2>/dev/null";
    // OR if codex supports reading from a file argument:
    // codex_bin + " --model gpt-4o-mini --quiet --full-auto < " + ShellQuote(temp_path.string())

    // Safest approach — write a wrapper shell script to temp and execute it:
    const auto script_path = std::filesystem::temp_directory_path() /
        ("ielts_score_run_" + std::to_string(::getpid()) + ".sh");
    {
        std::ofstream sh(script_path);
        sh << "#!/bin/sh\n";
        sh << codex_bin << " --model gpt-4o-mini --quiet --full-auto \"$(cat "
           << ShellQuote(temp_path.string()) << ")\" 2>/dev/null\n";
    }
    ::chmod(script_path.c_str(), 0700);
    const std::string safe_cmd = "sh " + ShellQuote(script_path.string());

    std::array<char, 4096> buffer{};
    std::string result;
    FILE* pipe = ::popen(safe_cmd.c_str(), "r");
    if (!pipe) {
        std::filesystem::remove(temp_path);
        std::filesystem::remove(script_path);
        throw std::runtime_error("Failed to start codex CLI");
    }
    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe)) result += buffer.data();
    const int status = ::pclose(pipe);
    std::filesystem::remove(temp_path);
    std::filesystem::remove(script_path);

    if (status == -1 || !WIFEXITED(status) || WEXITSTATUS(status) != 0)
        throw std::runtime_error("codex CLI exited with non-zero status");
    if (result.empty())
        throw std::runtime_error("codex CLI returned empty output");
    return result;
}
```

**实际修改建议（最简）**：如果 `codex` CLI 支持 `--full-auto < file`，把整个命令换成：
```cpp
const std::string command =
    codex_bin + " --model gpt-4o-mini --quiet --full-auto < " +
    ShellQuote(temp_path.string()) + " 2>/dev/null";
```
先手动测试 `codex --model gpt-4o-mini --quiet --full-auto < /tmp/test.txt`，确认可行后使用。

---

## Phase 5 — 添加真实当季题库数据

### P1 题库（6 个 topic 文件）

路径：`data/ielts/part1/`

文件命名：`2026_spring_{topic}.json`，topic 为：
`home`, `daily_routine`, `technology`, `travel`, `food`, `hobbies`

格式（以 home 为例）：
```json
{
  "season": "2026-spring",
  "part": 1,
  "topic": "home",
  "questions": [
    "Do you live in a house or a flat?",
    "What do you like most about where you live?",
    "How long have you lived there?",
    "What would your ideal home look like?",
    "Do you think the area where you live will change much in the future?",
    "Is there anything you would like to change about your home?"
  ]
}
```

从以下来源取真题（参考 2025-2026 考季真题报告）：
- home / accommodation
- daily routine（早起/睡眠/习惯）
- technology（手机/AI/网络）
- travel（交通/城市/旅游）
- food（饮食/烹饪/外卖）
- hobbies（运动/音乐/阅读）

各 topic ≥ 6 题。

### P2 题库（≥ 8 张 cue card）

路径：`data/ielts/part2/2026_spring_topics.json`

格式：
```json
{
  "season": "2026-spring",
  "part": 2,
  "topics": [
    {
      "title": "Describe a skill you recently learned",
      "bullets": [
        "What the skill is",
        "How you learned it",
        "Why you decided to learn it"
      ],
      "rounding": "And explain how this skill has been useful to you.",
      "p3_theme": "skills_and_learning"
    }
  ]
}
```

建议 8 张 cue card 主题：
1. 最近学的技能
2. 令你印象深刻的建筑物
3. 你敬佩的人
4. 一次令你高兴的购物经历
5. 你想去的国家
6. 一首对你有意义的歌
7. 帮助过你的人
8. 一次成功的经历

---

## Phase 6 — 验收与测试

```bash
# 1. 构建
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)

# 2. 单元测试
ctest --test-dir build -V

# 3. 帮助验收
./build/IELTSSpeakingSimulator --help

# 4. 手动冒烟测试（P2）
./build/IELTSSpeakingSimulator --config-file config.json --data-dir data/ielts
# 选 [3] Practice Part 2 only
# 验证：显示 cue card → "Press [Enter]" 等待 → 倒计时 60s → 录音 120s → 评分
```

---

## 文件改动汇总

| 文件 | 动作 | Phase |
|------|------|-------|
| `include/ielts/realtime_speech_capture.h` | 新增 `CaptureAnswerOrFallback` 声明 | 1 |
| `src/ielts/realtime_speech_capture.cpp` | 新增 `CaptureAnswerOrFallback` 实现 | 1 |
| `src/ielts/part2_session.cpp` | `Start()` 加 Enter 等待 | 2 |
| `include/ielts/part3_session.h` | 新增 `GetFollowUpQuestion` 声明 | 3 |
| `src/ielts/part3_session.cpp` | 回答改 STT；追问改动态 claude | 3 |
| `src/ielts/scorer.cpp` | 修 shell 安全 | 4 |
| `data/ielts/part1/2026_spring_*.json` | 新增 ×6 | 5 |
| `data/ielts/part2/2026_spring_topics.json` | 新增 | 5 |

---

## 注意事项

1. `CaptureAnswerOrFallback` 提升后，`part1_session.cpp` 内的同名 anon 函数**不要删**，避免破坏已通过的 P1 代码。可后续再统一。
2. `claude` CLI 的 `--print` 或 `-p` flag 用法：`claude -p "system prompt" "user message"` —— 先 `claude --help` 确认当前版本语法。
3. `codex --full-auto` 在新版可能改名，先 `codex --help` 确认。
4. P3 追问 claude 命令超时可能导致卡顿，建议加 `timeout 10s claude ...` 前缀。
