# IELTS Speaking CLI Simulator — P1/P2/P3 重构为纯命令行模式

## Goal

把现有 C++ IELTS CLI 模拟器补全到可实际运行状态：
P1 从题库出题、P2 按键开始/计时/按键停止、P3 动态追问。
出题用 `claude` CLI，评分用 `codex` CLI，均已有调用骨架，需要修 Bug、补数据、打通 STT 分支。

## What I already know

* 核心架构全部存在：`Part1Session / Part2Session / Part3Session / Scorer / QuestionBank / RealtimeSpeechCapture`
* P1：已集成 `CaptureAnswerOrFallback`（Realtime STT → 终端回退），追问逻辑完整
* P2：`ShowCueCard → RunCountdown（可 Enter 跳过）→ RecordSpeech（Enter 停止）`，但 **ShowCueCard 后没有"按 Enter 开始准备"的等待点**，立刻进入 60s 倒计时
* P3：`GenerateQuestions` 用 `claude -p "$(cat ...)"` — **shell 展开路径不对，内容有 shell 注入风险**；回答采集是裸 `std::getline`，没用 Realtime STT；追问只有一句硬编码 "Why do you think that is the case?"
* Scorer：`codex --full-auto "$(cat ...)"` 同样有 shell 注入风险
* 工具路径：`claude` = `~/.local/bin/claude`，`codex` = `/opt/homebrew/bin/codex` ——两者都在
* 现有题库数据：`2025_autumn_*`，3 个 P1 topic 文件 + 1 个 P2 文件（占位题目），**无真实当季真题**

## Requirements

### R1 — 题库数据（当季真题种子）
* 新增 `data/ielts/part1/2026_spring_*.json` × 6 个 topic
  （home, daily_routine, technology, travel, food, hobbies）
* 新增 `data/ielts/part2/2026_spring_topics.json`（≥ 8 张 cue card）
* 格式沿用现有 JSON schema，不改 `QuestionBank` 代码

### R2 — P2 "按 Enter 开始"
* `Part2Session::Start()` 在 `ShowCueCard` 后增加一个显式等待：
  ```
  "Cue card displayed. Press [Enter] when you are ready to start your 1-minute preparation time."
  > (等待 Enter)
  ```
* 然后再调 `RunCountdown`

### R3 — P3 Realtime STT
* `Part3Session` 回答采集改用 `CaptureAnswerOrFallback`（与 P1 完全一致）
* 需要 include `ielts/realtime_speech_capture.h`

### R4 — P3 追问多样化
* 追问时通过 `claude -p` 生成上下文相关追问，prompt：
  ```
  "You are an IELTS examiner. The candidate gave a short/thin answer to the question below.
  Generate ONE natural follow-up probe question in one sentence.
  Question: {question}
  Candidate answer: {answer}"
  ```
* 失败时从 5 条固定 probes 中轮询兜底（不再只有一句）

### R5 — 修 codex/claude shell 命令安全问题
* 将 `$(cat ...)` 模式换成 **stdin 管道**（`popen` 写入 stdin）或 **`--input-file` 参数**（如 CLI 支持）
* 至少保证 transcript 中的单引号 / 换行不会破坏命令

### R6 — 验收标准
* `cmake --build build && ctest --test-dir build` 全绿
* `./build/IELTSSpeakingSimulator --help` 正常退出
* 手动跑 P2 能看到：显示 cue card → 等待 Enter → 倒计时 → 录音 → 评分输出

## Acceptance Criteria

* [ ] `data/ielts/part1/2026_spring_*.json` 存在，`QuestionBank` 能 load
* [ ] P2 在 cue card 后有"Press Enter"等待
* [ ] P3 使用 `CaptureAnswerOrFallback`，无直接 `std::getline`
* [ ] P3 追问有 ≥ 5 种 probe 兜底，主路径调 claude CLI
* [ ] `Scorer::RunCodex` 和 `Part3Session::GenerateQuestions` 不再用 `"$(cat ...)"`（改用管道或重定向安全方式）
* [ ] ctest 6/6 passed

## Definition of Done

* 所有修改能 `cmake --build` 无 error
* ctest 通过
* `data/ielts/` 下有真实题目（不全是占位符）

## Technical Approach

1. **数据层**：只加 JSON 文件，不改任何 C++ 代码
2. **P2 等待点**：`Part2Session::Start()` 加 6 行
3. **P3 STT**：`part3_session.cpp` 改 `std::getline` → `CaptureAnswerOrFallback`
4. **P3 追问**：新增 `GetFollowUpQuestion(question, answer)` 方法，调 claude CLI 返回单句
5. **Shell 安全**：两处 `popen` 命令改用 `echo <content> | claude ...` 或临时文件 + 重定向（`< file`）

## Out of Scope

* Qt UI 相关代码不动
* `dialog_session.cpp` 全量重构（仅借鉴追问逻辑）
* TTS 播报题目（当前 SafeSpeak 逻辑保持原样）
* 报告 PDF 导出

## Technical Notes

* `claude` 路径：`~/.local/bin/claude`，popen 时需展开 `$HOME`
* `codex` 路径：`/opt/homebrew/bin/codex`
* `CaptureAnswerOrFallback` 定义在 `src/ielts/part1_session.cpp` 的 anon namespace — P3 要用需移到 `realtime_speech_capture.h` 或提取成 free function
* 现有 `EnterPressed()` 用 `select()` + `STDIN_FILENO`，macOS 下有效
* codex 命令当前：`codex --model gpt-4o-mini --quiet --full-auto "$(cat ...)"` — `--full-auto` 在新版 codex CLI 可能已改名，需确认
