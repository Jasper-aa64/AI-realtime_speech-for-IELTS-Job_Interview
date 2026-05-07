# Scorer 多后端支持：codex exec / API key / 可扩展模型接口

## Goal

Scorer 当前写死 `codex exec --model gpt-4o-mini`，ChatGPT 账号不支持该 model 导致 400 报错。
需要支持两种模式并留好扩展接口：
- **codex_exec**：`codex exec`（无 key，ChatGPT 账号登录，用默认 model）
- **openai_api**：通过 `OPENAI_API_KEY` 环境变量 + 指定 model
- **claude**（预留接口，stub 即可）

## What I already know

- `scorer.cpp` 当前命令：`codex exec --model gpt-4o-mini --ask-for-approval never --sandbox read-only --color never --output-last-message <path> - < prompt.txt`
- 问题：`--model gpt-4o-mini` + ChatGPT 账号 → 400；`--output-last-message` / `--ask-for-approval` 等 flag 需要验证是否实际存在
- 验证可用命令：`echo "..." | codex exec`（无 model flag，默认 gpt-5.5，成功返回）
- codex 路径：`/opt/homebrew/bin/codex`
- claude 路径：`~/.local/bin/claude`
- 配置文件：`config/default_config.json`（已有 audio/ws/dialog/tts/asr/llm 段）
- 现有 `Scorer(const std::string& data_dir)` 构造函数，无 config 参数

## Requirements

### R1 — ScorerConfig 结构 + 后端枚举
在 `include/ielts/scorer.h` 新增：
```cpp
enum class ScorerBackend { kCodexExec, kOpenAIAPI, kClaude, kHeuristic };
struct ScorerConfig {
    ScorerBackend backend = ScorerBackend::kCodexExec;
    std::string   model;    // 留空 = 用各后端默认
    std::string   api_key;  // openai_api 模式用
};
```

### R2 — Scorer 构造函数接受 ScorerConfig
```cpp
explicit Scorer(const std::string& data_dir, ScorerConfig config = {});
```
默认值保持向后兼容（不传 config 则用 codex_exec）。

### R3 — codex_exec 后端（修 bug）
命令改为：
```bash
cat prompt.txt | /opt/homebrew/bin/codex exec 2>/dev/null
```
- 不传 `--model`（用账号默认 model）
- 不传 `--output-last-message`（直接从 stdout 提取 JSON）
- 如果 config.model 非空，追加 `-m <model>`

### R4 — openai_api 后端
用 `OPENAI_API_KEY` 环境变量：
```bash
OPENAI_API_KEY=<key> cat prompt.txt | /opt/homebrew/bin/codex exec -m <model> 2>/dev/null
```
- 若 config.api_key 非空，注入为环境变量（`putenv` 或 popen 前 `setenv`）
- 若 config.model 为空，默认 `gpt-4o`

### R5 — claude 后端（stub）
```bash
~/.local/bin/claude --print <prompt> 2>/dev/null
```
先实现，确保能编译通过，可以后续精调 prompt 格式。

### R6 — config.json 新增 scorer 段
```json
"scorer": {
  "backend": "codex_exec",
  "model": "",
  "api_key": ""
}
```
`IELTSManager` 或 `main_ielts.cpp` 读取后构造 `ScorerConfig` 传给 `Scorer`。

### R7 — 日志
每次 score 前打一条 INFO：`Scorer backend: codex_exec / openai_api / claude`

## Acceptance Criteria

* [ ] `config/default_config.json` 有 `scorer.backend = "codex_exec"`
* [ ] codex_exec 模式不传 `--model`，能从 stdout 提取 JSON
* [ ] openai_api 模式传 `OPENAI_API_KEY` + model
* [ ] claude 模式能编译通过（不报链接/语法错误）
* [ ] `cmake --build build` 无 error
* [ ] `ctest` 6/6 passed
* [ ] 手动跑 P2，评分日志显示 `Scorer backend: codex_exec` 且不报 `codex CLI exited with non-zero status`

## Definition of Done

* Build 通过，ctest 通过
* codex_exec 模式实际能拿到评分结果（JSON 解析成功）

## Technical Approach

1. `scorer.h`：加 `ScorerConfig` + `ScorerBackend`；构造函数加默认参数
2. `scorer.cpp`：`RunCodex()` 重命名为 `RunBackend()`，分发到 `RunCodexExec()` / `RunOpenAIAPI()` / `RunClaude()`
3. `config.cpp`：读取 `scorer` JSON 段，构造 `ScorerConfig`（optional，缺省 codex_exec）
4. `ielts_manager.cpp` 或 `main_ielts.cpp`：把 `ScorerConfig` 传给 `Scorer`
5. 更新 `config/default_config.json`

## Decision (ADR-lite)

**Context**: codex exec 与 API key 是两种不同认证路径；未来可能接入 claude 或本地模型。
**Decision**: 用 ScorerConfig + enum 分发，默认 codex_exec，config.json 可切换。
**Consequences**: 向后兼容（默认值不变）；新增后端只需加一个 RunXxx() 方法。

## Out of Scope

* claude 后端的 prompt 精调（stub 即可）
* 本地模型 / Ollama 支持
* 异步/并发评分
