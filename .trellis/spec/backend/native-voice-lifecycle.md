# Native Voice Callback and Lifecycle Contracts

## Scenario / scope

Applies to standalone `native_voice/` C++17 foundation and future native device
integration. The current owned worker is **software echo**, not a recognition,
network, DSP, AEC or conversation service. It is not linked into the desktop
product. No hardware recording or provider call belongs in automated tests.

## Signatures

- `Engine(Format{sample_rate, channels}, capacity_frames, worker_poll, max_backlog)`
- Control thread: `start()`, `stop()`; `interrupt()` only changes an atomic epoch.
- Capture owner: `capture(const float*, frames, optional_monotonic_timestamp_ns)`.
- Render owner: `render(float*, frames, optional_Metadata_array)`.
- `metrics()` exposes cumulative atomic counters; `preallocated_audio_bytes()`
  exposes ring storage bounds, not process RSS or all harness memory.
- Default `native_voice_benchmark` is paced synthetic data; hardware executables
  require both `--hardware --i-understand-microphone` before initialization.

## Contracts

1. One non-reentrant capture producer, one owned worker, one non-reentrant
   playback consumer. Simultaneous capture/render is supported. Control/network
   actors do not become additional SPSC producers or reset ring indexes live.
2. Mono/stereo interleaved float PCM; arbitrary complete callback frame counts
   and persistent FIFO ordering. Callers supply correctly sized buffers.
   Null capture data is silence, empty playback fills silence. Invalid nonempty
   output is rejected. Future packet format conversion must be explicit.
3. Device callbacks never allocate/free, block, wait on mutexes, log, do I/O,
   query clocks, or call start/stop/device APIs. Callback index/stat/gate atomics
   must be always lock-free on the compiled target. Construction/control may
   allocate. This is soft realtime, not a hard OS scheduling guarantee.
4. Stop closes the running gate, cancels, waits for active callbacks, joins the
   owned worker and then resets rings. Devices stop/destroy callbacks before
   engine destruction. No detached threads; never use stop from a callback.
   Callback progress and externally valid object lifetime are preconditions.
5. Interrupt increments epoch. Capture's old callback remainder remains tagged
   old; worker/render discard it. Output checks epoch per complete frame, with
   stale draining bounded to one ring capacity per callback. Software cannot
   retract samples already handed to the audio backend/DAC.
6. Buffers have explicit frame/byte bounds. Default 4096-frame rings are 85.33ms
   each at 48k, not an achieved latency. The echo path's default 40ms sample-age
   cutoff advances only while capture sequences advance; it is not a monotonic
   wall-clock deadline when capture pauses. Overrun/underrun/age/stale counts
   are visible. Product integration must surface failure/drop policy.
7. Frame-based metadata/atomic publication is correctness-first, not claimed
   faster than chunk buffering. A future 10ms chunk design must retain partial
   callbacks and epoch ownership. No Qt-vs-PortAudio result without controlled
   device measurements. Qt6.11 callback API is valid; Qt6.12 period API is not
   assumed available on 6.11.2.
8. Future capture→DSP/transport and provider-TTS→decode/playback must be distinct
   paths; synthetic echo is not provider response audio. Introduce monotonic
   wall-clock queue-age bounds, independent reply/session epochs and a single
   playback ingress owner. Keep raw PCM off QWebChannel and report payloads.

## Validation / error matrix

| Condition | Required behavior |
| --- | --- |
| Ring full | Count rejected frames; no unbounded queue growth |
| Render empty/stopped | Fill caller's output with silence |
| Old epoch after interrupt | Discard, never reset live indexes concurrently |
| Worker creation failure | Remain capture-disabled and allow retry |
| Rapid stop/start | Quiesce/join before storage reset; no stale replay |
| Wrong hardware format | Reject rather than silently changing application format |
| Hardware executable without both flags | Exit before device initialization |
| Synthetic latency result | Label capture-call to software-render-return, not DAC/cloud |

## Good / base / bad cases

- Good: synthetic stereo input survives arbitrary 73→17+56 frame callback
  boundaries, interruption drops old remainder, restart resumes with a new epoch.
- Base: missing Qt/PortAudio builds the independent core/tests only.
- Bad: report a synthetic echo percentile as native ASR or device latency;
  use an echo sequence-age policy for unrelated provider output without redesign;
  stop a device from its callback; push render audio from multiple threads.

## Required tests / evidence

Ring wrap/full/empty; two-thread ordered transfer; arbitrary/stereo callbacks;
callback allocation check; partial-output stale cancellation; pressured bounded
storage and age discard; simultaneous capture/render/interrupt with rapid
restart; hardware opt-in rejection. Run release and separate ASan/UBSan/TSan
core builds where supported. Store observed synthetic distributions, counts,
jitter, CPU, stop timing and bounds; never fabricate provider stages or physical
benchmarks. No microphone in tests, sanitizer runs or agent unattended work.

## Wrong vs correct

```cpp
// Wrong: other actors reset a consumer cursor or allocate on the callback.
// Correct: atomically advance epoch, let each ring owner discard stale frames,
// then quiesce callbacks + join the owned worker before reset on stop.
```
