# 实验5：开源复用与 WASM 音频核方案

## 最高原则

现有 IELTS Web 产品功能设计不重做。C++ / WASM / 实时语音链路是增量加速层：

```text
现有浏览器录音与批处理评分 = baseline / fallback
audio_core.wasm             = 浏览器端轻量预处理
C++ realtime gateway        = 后续实时转写网关
```

本阶段只做选型和 demo scaffold，不接入正式 P1/P2/P3 练习流程。

## 选型结论

实验5的开源复用目标选 `libfvad`。当前代码已经将 `libfvad` vendor 到 `third_party/libfvad/`，并通过 `audio_core` 的 VAD backend 抽象接入。

`libfvad` 是基于 WebRTC VAD 引擎的独立 C 库。相比直接引入完整 WebRTC，它更适合当前项目：

- 只解决 VAD，不拖入完整音视频栈。
- C API 小，后续容易被 `audio_core` 包装。
- BSD-3-Clause license，适合课程报告说明和项目集成。
- 可以同时服务两条路径：浏览器 WASM 预处理、Linux realtime gateway 预处理。

## 候选对比

| 候选 | 作用 | 优点 | 风险 / 不选原因 | 结论 |
| --- | --- | --- | --- | --- |
| WebRTC VAD upstream | 语音活动检测 | 成熟、实时场景常用、BSD-style license | 完整 WebRTC tree 太大，直接引入会让作业和项目边界变重 | 不直接引入完整 tree |
| `libfvad` | 独立 WebRTC VAD | 小型 C 库、BSD-3、独立于完整 WebRTC | 后续需要 vendor 或子模块，并写 license 归档 | 选中 |
| SpeexDSP | DSP / resampler / noise processing | 音频处理能力更广 | 不是最直接的 VAD 目标，第一阶段会分散重点 | 后续可作为 resampler/noise 备选 |
| libsamplerate | 高质量采样率转换 | resampling 质量高，BSD-2 | 不解决 VAD；当前 `audio_core` 已有 deterministic linear baseline | 暂不作为实验5主复用点 |

## 当前 WASM Demo 边界

新增 demo 只验证一件事：已经抽出的 `ielts::audio` 纯 C++ 核可以通过 Emscripten 跑在浏览器里。构建脚本现在会同时编译 `audio_core` 和 `libfvad` 源码，使后续 browser-side WebRTC VAD demo 能在同一条路径上继续推进。

文件：

- `src/ielts/audio_core_wasm.cpp`：C ABI wrapper。
- `scripts/build_audio_core_wasm.sh`：Emscripten 构建脚本。
- `web/static/wasm/audio_core_demo.html`：独立 demo 页面。
- `web/static/wasm/audio_core_demo.js`：加载生成的 WASM module 并跑 smoke test。

生成文件不提交：

- `web/static/wasm/audio_core_wasm.js`
- `web/static/wasm/audio_core_wasm.wasm`

## 后续集成计划

1. 在浏览器 demo 中增加 WebRTC VAD smoke test，验证 10/20/30ms frame 输入。
2. 在 `audio_core` 继续保留 `VadBackend` 抽象：

   ```cpp
   class VadBackend {
   public:
       virtual ~VadBackend() = default;
       virtual bool IsSpeech(const int16_t* samples, int sample_count, int sample_rate) = 0;
   };
   ```

3. 保留现有 RMS-threshold VAD 作为 deterministic fallback。
4. WASM demo 先使用 mock PCM；产品集成单独立项，必须保证 baseline 可降级。

## 参考来源

- WebRTC upstream VAD wrapper: <https://chromium.googlesource.com/external/webrtc/trunk/webrtc/+/f54860e9ef0b68e182a01edc994626d21961bc4b/common_audio/vad/vad.cc>
- `libfvad`: <https://github.com/dpirch/libfvad>
- libsamplerate wrapper / license note: <https://pypi.org/project/samplerate/>
