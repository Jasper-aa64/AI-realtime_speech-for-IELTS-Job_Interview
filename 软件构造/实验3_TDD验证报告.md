# 实验3：TDD 验证报告

## 最高原则

实验3不改变现有 IELTS Web 产品功能设计，只为已经完成的重构线补一层可重复执行的 TDD 验证：

```text
现有浏览器录音 / 上传 / 报告生成 = baseline
audio_core / WASM / AIProvider 重构 = 可验证的内部改进
测试脚本 = 防止重构回退的安全网
```

本实验覆盖 C++ 音频纯核、浏览器 WASM 预处理边界、Django AI provider 重构和后端 metrics 持久化，不修改 UI、API、数据库 schema 或业务流程。

## TDD 目标

本次 TDD 的目标不是追求测试数量，而是把最容易在重构中回退的契约固定下来：

1. C++ `audio_core` 抽核后，RMS、peak、VAD、静音裁剪、重采样行为稳定。
2. `libfvad` WebRTC VAD backend 可以初始化、识别合法静音帧，并拒绝非法配置。
3. 生成的 WASM 产物可构建，但不会进入 Git。
4. 浏览器端 metrics summary 只上传小型摘要，不泄露 raw PCM samples。
5. Django AI provider 重构后，`apps.ai` 回归测试仍通过。
6. speaking turn complete 可以持久化 sanitized audio preprocessing metrics。

## 测试对象

| 层级 | 文件 / 命令 | 覆盖内容 |
| --- | --- | --- |
| C++ native | `tests/audio_core_test.cpp` | `audio_core` 纯函数和 VAD backend |
| WASM build | `scripts/build_audio_core_wasm.sh` | Emscripten 构建、artifact ignore contract |
| Browser JS | `web/static/wasm/*.js` | demo / worklet / analyzer 语法边界 |
| JS unit | `scripts/test_wasm_audio_preprocessor_metrics.mjs` | metrics summary 行为 |
| Django backend | `python manage.py test apps.ai ...` | AI provider 回归、speaking metrics 持久化 |
| 一键入口 | `scripts/run_experiment3_tdd_validation.sh` | 串联全部检查，失败即停 |

## TDD 用例设计

### 1. C++ `audio_core` characterization tests

`tests/audio_core_test.cpp` 用固定样本锁定重构后的行为：

- 空输入 RMS / peak 返回 `0`。
- 固定高振幅 frame 被 RMS fallback 判断为 speech。
- 首尾静音 + 中间 speech 的样本被 `TrimSilence` 正确裁剪。
- `ResampleLinear` 可以把 16k 采样下采样为更少样本。
- 非法 sample rate、frame duration、threshold 抛出 `std::invalid_argument`。

这些测试的作用是先固定算法表现，再允许内部继续拆分、换 backend 或接 WASM。

### 2. `libfvad` backend tests

新增的 WebRTC VAD backend 测试覆盖：

- `VadBackend::RmsThreshold` 保持原 deterministic fallback 行为。
- `VadBackend::WebRtc` 可以初始化并把 16k / 20ms / 320 samples 静音帧识别为 silence。
- 44100 sample rate、40ms frame、aggressiveness=4、错误 frame size 都会被拒绝。

这确保开源库复用不是“只 vendor 文件”，而是真正接入并受测试保护。

### 3. Browser metrics summary tests

`scripts/test_wasm_audio_preprocessor_metrics.mjs` 直接测试：

- `enabled=false` 或空输入返回 `null`。
- `frameCount` / `speechFrameCount` 被规范化。
- `speech_ratio` / `silence_ratio` 按计数计算。
- RMS、peak、timestamp 保留为固定精度。
- `samples` 等 raw PCM 字段不会进入 summary。

这条测试是为了防止未来把大块音频 frame 误塞进 `turns/{id}/complete` payload。

### 4. Django regression tests

验证脚本复用已有 Django 测试：

```bash
python manage.py test \
  apps.ai \
  apps.speaking.tests.SpeakingRuntimeApiTests.test_turn_complete_persists_audio_preprocessing_metrics
```

它保护两件事：

- `apps.ai` provider adapter 重构后，公开行为仍然兼容。
- speaking 后端只持久化 sanitized metrics summary，不依赖生成的 WASM artifact。

## 一键验证脚本

实验3的统一入口是：

```bash
scripts/run_experiment3_tdd_validation.sh
```

脚本执行顺序：

1. 构建并运行 `audio_core_test`。
2. 运行 `scripts/build_audio_core_wasm.sh`。
3. 检查 `audio_core_wasm.js/.wasm` 被 `.gitignore` 忽略。
4. 对 WASM demo 和 preprocessor JS 做 `node --check`。
5. 运行 `scripts/test_wasm_audio_preprocessor_metrics.mjs`。
6. 运行 Django `apps.ai` 和 speaking metrics regression。

脚本使用 `set -euo pipefail`，任何一步失败都会立即退出。

## Red / Green / Refactor 过程

### Red

先暴露重构风险：

- WASM artifact 容易误提交。
- metrics summary 容易把 raw samples 一并传给后端。
- `libfvad` frame 长度和 sample rate 限制容易在 wrapper 层漏校验。
- AI provider 重构后可能破坏现有 `apps.ai` 测试。

### Green

补齐测试和一键脚本后，验证路径可以稳定通过：

```text
Experiment 3 TDD validation passed.
```

当前验证包括 C++、WASM、JS 和 Django 四层。

### Refactor

在测试保护下，后续可以继续做：

- `audio_core` 内部 backend 拆分。
- WASM analyzer 优化。
- realtime gateway 接入。
- `apps.ai` provider chain 进一步拆分。

只要 `run_experiment3_tdd_validation.sh` 仍然通过，就说明 baseline 行为没有被破坏。

## 防止的具体回退

| 可能回退 | 测试防线 |
| --- | --- |
| 把 generated WASM 文件提交进仓库 | `git check-ignore` |
| C 源和 C++ 源混用错误编译参数 | `scripts/build_audio_core_wasm.sh` |
| Worklet demo JS 语法损坏 | `node --check web/static/wasm/*.js` |
| raw samples 进入 API payload | `test_wasm_audio_preprocessor_metrics.mjs` |
| WebRTC VAD 接受错误 frame | `audio_core_test` |
| AI provider 重构破坏公开行为 | `manage.py test apps.ai` |
| 后端 metrics 持久化格式漂移 | speaking runtime regression |

## 验证结果

已执行：

```bash
scripts/run_experiment3_tdd_validation.sh
```

结果：

```text
Experiment 3 TDD validation passed.
```

## 结论

实验3把“重构是否安全”从人工判断变成了可重复运行的验证命令。它既保护了 C++/WASM 音频加速层，也保护了 Django AI provider 和 speaking metrics 的跨层契约，是后续实验4重构和实验5开源复用继续推进的安全网。
