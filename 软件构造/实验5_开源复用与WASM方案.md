# 实验5：开源复用与 WASM 音频核方案

## 最高原则

现有 IELTS Web 产品功能设计不重做。C++ / WASM / 实时语音链路是增量加速层：

```text
现有浏览器录音与批处理评分 = baseline / fallback
audio_core.wasm             = 浏览器端轻量预处理
C++ realtime gateway        = 后续实时转写网关
```

本阶段只做开源库复用、C++ 纯核、WASM 构建和独立浏览器 demo，不接入正式 P1/P2/P3 练习流程。

## 选型结论

实验5的核心开源复用目标选 `libfvad`。当前代码已经将 `libfvad` vendor 到 `third_party/libfvad/`，并通过 `audio_core` 的 VAD backend 抽象接入。

`libfvad` 是基于 WebRTC VAD 引擎的独立 C 库。相比直接引入完整 WebRTC，它更适合当前项目：

- 只解决 VAD，不拖入完整音视频栈。
- C API 小，后续容易被 `audio_core` 包装。
- BSD-3-Clause license，适合课程报告说明和项目集成。
- 可以同时服务两条路径：浏览器 WASM 预处理、Linux realtime gateway 预处理。

后续在 P1 examiner TTS 播放稳定性治理中，又补充复用了 `howler.js`
作为浏览器端音频播放层。它不替代 `libfvad` 的实验核心地位，而是作为
第二个复用资源，解决浏览器短音频播放、preload、end/error 回调和
跨浏览器播放差异，避免继续维护项目内手写 `<audio>` 状态机。

## 候选对比

| 候选 | 作用 | 优点 | 风险 / 不选原因 | 结论 |
| --- | --- | --- | --- | --- |
| WebRTC VAD upstream | 语音活动检测 | 成熟、实时场景常用、BSD-style license | 完整 WebRTC tree 太大，直接引入会让作业和项目边界变重 | 不直接引入完整 tree |
| `libfvad` | 独立 WebRTC VAD | 小型 C 库、BSD-3、独立于完整 WebRTC | 后续需要 vendor 或子模块，并写 license 归档 | 选中 |
| `howler.js` | 浏览器音频播放 | 成熟 Web 音频库、支持 preload / onload / onplay / onend / onerror、MIT license | 只解决播放稳定性，不解决 VAD / WASM 计算 | 作为前端播放层补充复用 |
| SpeexDSP | DSP / resampler / noise processing | 音频处理能力更广 | 不是最直接的 VAD 目标，第一阶段会分散重点 | 后续可作为 resampler/noise 备选 |
| libsamplerate | 高质量采样率转换 | resampling 质量高，BSD-2 | 不解决 VAD；当前 `audio_core` 已有 deterministic linear baseline | 暂不作为实验5主复用点 |

## 当前 WASM Demo 边界与实际进度

新增 demo 验证两件事：

1. 已经抽出的 `ielts::audio` 纯 C++ 核可以通过 Emscripten 跑在浏览器里。
2. 浏览器 `AudioWorklet` 采集到的实时 frame 可以通过 analyzer 抽象切换到 `audio_core_wasm.js` 分析，而不是停留在 JavaScript mock。

构建脚本现在会同时编译 `audio_core` 和 `libfvad` 源码。`libfvad` 的 C 源文件以 C object 编译，`audio_core` / wrapper 以 C++17 编译，再统一链接成浏览器端 `audio_core_wasm.js/.wasm`。WASM wrapper 导出 `HEAP16`，并开启 C++ exception catching，使 invalid frame 等边界错误能返回 wrapper 错误码，而不是在浏览器里 abort。

文件：

- `src/ielts/audio_core_wasm.cpp`：C ABI wrapper。
- `scripts/build_audio_core_wasm.sh`：Emscripten 构建脚本。
- `web/static/wasm/audio_core_demo.html`：独立 demo 页面。
- `web/static/wasm/audio_core_demo.js`：加载生成的 WASM module 并跑 smoke test。
- `web/static/wasm/audio_worklet_demo.html`：独立 AudioWorklet frame demo。
- `web/static/wasm/audio_worklet_demo.js`：麦克风 frame 流与 analyzer 切换 UI。
- `web/static/wasm/audio_frame_processor.js`：只负责在 AudioWorklet 中采集 frame 并传回主线程。
- `web/static/wasm/audio_analyzer.js`：主线程 analyzer registry，包含 `Mock RMS` 和 `WASM audio_core` 两条路径。

生成文件不提交：

- `web/static/wasm/audio_core_wasm.js`
- `web/static/wasm/audio_core_wasm.wasm`

已验证：

- `scripts/build_audio_core_wasm.sh` 可真实生成 WASM 产物。
- `audio_core_demo.html` 浏览器 smoke 显示 `WASM smoke test passed`。
- `audio_worklet_demo.html` 中 `WASM audio_core` 可选，切换后显示 `WASM audio_core analyzer is ready.`。
- `.wasm` 静态服务 MIME 为 `application/wasm`。
- 生成产物被 `.gitignore` 忽略，不进入仓库。

## 浏览器 TTS 播放复用：howler.js

P1 examiner TTS 曾经由项目内手写 `<audio>` 播放状态机维护。该实现需要同时处理
预加载、播放开始、播放结束、错误、停止、旧回调失效和题目切换，容易和 P1
业务状态机互相干扰。为避免继续手搓底层播放机制，当前前端引入：

- `web/static/vendor/howler.min.js`：vendored `howler.js` v2.2.4。
- `ExaminerAudioPlayer`：项目内小型 wrapper，只向业务层暴露 load / play /
  stop / unload 和 ready / play / end / error 事件。
- `/vendor/<path>` Django 静态路由：只服务 `web/static/vendor/` 下的文件，并
  拒绝路径穿越。

接入后的边界：

- P1/P3 examiner TTS 仍由 Django 后端生成，前端不保存任何 TTS secret。
- `/api/tts-audio/examiner/...` 播放前仍会转换到 `?stable=1`，优先走后端
  browser-friendly 音频路径。
- Howler 只负责浏览器播放引擎；IELTS turn 推进、follow-up 生成、realtime ASR
  和 WASM 预处理仍由原有业务层控制。

这部分复用体现的是“用成熟库替换不稳定自研底层能力”：项目保留自身业务状态机，
但不再把浏览器音频播放细节作为手写基础设施维护。

## 一键验收命令

```bash
scripts/run_experiment5_reuse_validation.sh
```

该脚本覆盖：

1. `third_party/libfvad/` 的 license、patent、author 和源码文件存在性。
2. `audio_core.cpp` 真实调用 `fvad_new`、`fvad_set_sample_rate`、`fvad_set_mode`、`fvad_process`。
3. CMake native 链路中存在 `fvad_vendor`，并与 `audio_core_test` 链接。
4. Emscripten WASM 构建脚本把 `libfvad` C 源和 `audio_core` C++ 源分阶段编译再链接。
5. 生成的 `audio_core_wasm.js/.wasm` 仍被 `.gitignore` 忽略。
6. demo JavaScript 语法检查通过。
7. 本地静态服务能以 `application/wasm` 返回 `.wasm` 文件。

## 后续集成计划

1. 在正式 P1/P2/P3 录音链路中增加 feature flag，默认关闭，允许开发环境切到 `WASM audio_core` 预处理。
2. 在 `audio_core` 继续保留 `VadBackend` 抽象：

   ```cpp
   class VadBackend {
   public:
       virtual ~VadBackend() = default;
       virtual bool IsSpeech(const int16_t* samples, int sample_count, int sample_rate) = 0;
   };
   ```

3. 保留现有 RMS-threshold VAD / `Mock RMS` 作为 deterministic fallback。
4. 产品集成单独立项，必须保证 baseline 可降级；任何 P1/P2/P3 正式流程接入都不能破坏现有浏览器录音与报告生成。

## 参考来源

- WebRTC upstream VAD wrapper: <https://chromium.googlesource.com/external/webrtc/trunk/webrtc/+/f54860e9ef0b68e182a01edc994626d21961bc4b/common_audio/vad/vad.cc>
- `libfvad`: <https://github.com/dpirch/libfvad>
- `howler.js`: <https://github.com/goldfire/howler.js>
- libsamplerate wrapper / license note: <https://pypi.org/project/samplerate/>
