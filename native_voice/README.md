# Native C++ voice foundation

This independent C++17 project provides tested callback-safe buffering and
lifecycle primitives plus **software echo** and native device adapters. The
worker copies capture frames into playback. It does not implement recognition,
conversation, network transport, VAD, AEC, resampling, or ASR/LLM/TTS. It is not
connected to the desktop interview UI. Desktop microphone controls must stay
unavailable until that separate integration works.

The default executable and all automated tests use synthetic input. Building
Qt/PortAudio adapters does not initialize audio devices. Hardware executables
reject invocation before device initialization unless both explicit flags are
present. No real audio capture was run while implementing this foundation.

## Build and safe software verification

From the repository root:

```sh
cmake -S native_voice -B native_voice/build -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH=/opt/homebrew/opt/qt
cmake --build native_voice/build -j4
ctest --test-dir native_voice/build --output-on-failure
native_voice/build/native_voice_benchmark --seconds 5
```

Qt >=6.11 Multimedia and PortAudio (`pkg-config portaudio-2.0`) are optional.
Core-only builds need a C++17 compiler, CMake >=3.21 and Threads:

```sh
cmake -S native_voice -B native_voice/build-core \
  -DNATIVE_VOICE_QT=OFF -DNATIVE_VOICE_PORTAUDIO=OFF
cmake --build native_voice/build-core -j4
ctest --test-dir native_voice/build-core --output-on-failure
```

The adapters were compiled against installed Qt 6.11.2 and PortAudio 19.7.0.
Qt 6.11's native callbacks use `QSpan<const float>` / `QSpan<float>` on the
audio thread. This uses no 6.12 native-period APIs and no QIODevice audio
buffer. Both adapters request identical 48kHz mono float PCM by default and
reject incompatible defaults; no silent nearest-format conversion is selected
by this application. Native backend conversion can still occur below the API.
Hardware timings and device behavior have **not** been compared.

## Engine contract

- One non-reentrant capture callback owns the capture producer; one
  non-reentrant render callback owns the playback consumer. The owned worker
  is the other actor of each SPSC ring. Simultaneous capture/render is supported.
  Calling capture from two producers or render from two consumers is invalid.
- Interleaved float PCM supports mono/stereo, 8–192kHz and arbitrary complete
  frame counts, including zero and sizes that do not align with a 10ms block.
  The caller must provide valid buffers of `frames * channels` samples;
  optional render metadata holds `frames` entries. Null capture input means
  silence. Null nonempty output is rejected.
- Constructor allocates ring storage. Capture/render do no allocation,
  deallocation, blocking waits, mutexes, I/O, clocks, logging or thread wake
  primitives. Callback atomics are compile-time checked as always lock-free
  on the target. This is soft realtime; OS scheduling has no hard deadline
  guarantee. Telemetry is fixed-cost counters and caller-provided timestamps.
- `start`/`stop` are control-thread operations serialized by a lifecycle mutex;
  never invoke them from callbacks. `start` is idempotent while running.
  Failure to construct the worker leaves capture disabled. `stop` disables
  new work, cancels, waits for callbacks that saw running, joins the worker
  and only then resets rings. Repeated stop/restart is supported.
- Callbacks must finish/progress for control shutdown to finish. Polling sleeps
  only on the worker, default 100us (configurable 0–10ms); scheduling can extend
  this. There is no detached thread or a force-kill timeout. The adapter stops
  and destroys devices before stopping the engine. Destroy the engine only
  after external callers have stopped issuing callbacks; an object cannot
  protect itself from a call after destruction.
- `interrupt()` advances an atomic epoch without resetting live SPSC indexes.
  Capture tags the whole callback with its initial epoch; worker/render reject
  stale epochs. Render rechecks each complete frame, so interruption midway
  through a callback discards remaining stale frames. Already-written samples
  or samples handed to device/DAC cannot be recalled. No physical immediate
  silence claim is made.
- Stale drain work is capped to one playback ring capacity per render callback;
  remaining output is silence. Empty playback always fills silence and counts
  each missing frame. Full capture/playback discards frames and counts them;
  these metrics invalidate any claim of complete recording during pressure.
  A product bridge must surface/drop/fail explicitly, not silently ignore them.

## Buffer and instrumentation tradeoffs

Each ring uses individual `Frame` records (two sample slots plus epoch,
sequence and optional timestamp). This deliberately makes arbitrary callback
sizes and ownership easy to validate. It has per-frame atomic/copy overhead;
it is **not claimed optimal**. A measured next refinement is fixed 10ms blocks
with persistent partial-block cursors and batched publication, preserving
single-actor ownership, sample ordering and interruption semantics.

Default ring capacity is 4096 frames each, **85.33ms at 48kHz**, with 262,144
bytes total audio/metadata storage on the tested ABI. Capacity is not actual
latency: occupancy and scheduling matter. The software echo path additionally
discards frames more than a configurable **40ms of sample age** behind the
latest captured sequence, including dropped capture attempts. This prevents
large backlog catch-up while capture continues. Sample age is not wall-clock
age: after capture pauses, sequence-based age stops advancing. Future transport
ingress must add monotonic wall-clock queue deadlines and independent playback
timestamps; current hardware callback timestamps remain unavailable (zero).

The paced software harness uses repeatable constant samples and callback sizes
127/256/97/480 at nominal 48kHz. Its scheduling and outcomes vary with OS load.
Arrays and telemetry are allocated before callback measurement and have a
bounded sample count (`--seconds` restricted to 0.05–30). It records caller
capture timestamps, software render-return timestamps, P50/P95/P99, maximum,
sample counts, callback duration, scheduler lateness, process CPU, observed
stop duration and frame discards/underruns. One callback timestamp covers all
its samples; correlated per-frame measurements do not imply independent
observations. Final draining can legitimately increase maximum latency.

These are **capture-call → software-render-return** observations. They omit
physical capture, native backend latency, DAC/acoustic output, network,
endpointing and inference. CPU includes the software harness/worker. Only the
two fixed audio rings are represented by `preallocated_audio_bytes`; bounded
harness telemetry is reported separately. No industrial performance or Qt vs
PortAudio speed conclusion follows from these synthetic results. Read the
[saved software report](reports/software-benchmark-2026-10-05.md).

## Sanitizers and meaningful tests

```sh
cmake -S native_voice -B native_voice/build-asan -DCMAKE_BUILD_TYPE=Debug \
  -DNATIVE_VOICE_QT=OFF -DNATIVE_VOICE_PORTAUDIO=OFF \
  -DNATIVE_VOICE_SANITIZER=address,undefined
cmake --build native_voice/build-asan -j4
ctest --test-dir native_voice/build-asan --output-on-failure
cmake -S native_voice -B native_voice/build-tsan -DCMAKE_BUILD_TYPE=Debug \
  -DNATIVE_VOICE_QT=OFF -DNATIVE_VOICE_PORTAUDIO=OFF \
  -DNATIVE_VOICE_SANITIZER=thread
cmake --build native_voice/build-tsan -j4
ctest --test-dir native_voice/build-tsan --output-on-failure
```

Tests cover exact full/empty capacity and repeated wrap, 250,000 ordered
two-thread frames, stereo/partial callbacks and metadata, callback allocation
checks, stale partial-output interruption, repeated/rapid lifecycle while both
callbacks run, pressure/discards, sample-age cutoff and hardware opt-in guards.
Sanitizer builds are separate from release performance results.

## Explicit hardware experiment (manual, with headphones)

Only when the user is present and deliberately chooses a five-second mic-to-
headphones echo experiment:

```sh
native_voice/build/native_voice_qt_hardware --hardware --i-understand-microphone
native_voice/build/native_voice_portaudio_hardware --hardware --i-understand-microphone
```

These commands open the default input and output devices, transmit no audio,
write no recording and print frame counters. PortAudio uses a full-duplex
callback with backend-driven frame counts. Qt uses separate capture/output
callbacks; the asynchronous backend may differ. `QtDevice::stop` discards output
with `reset`; PortAudio uses abort before close. Compare measured device/DAC
latency only after adding explicit timing/loopback instrumentation and fixing
the same physical devices, format, load and configuration in both runs.

## Next integration boundary

Replace the echo worker with separate capture→DSP/packetizer→authenticated
transport and provider-TTS→decode/resample→bounded playback paths. Each playback
producer must be a single owner; never let network/control threads push into
the same SPSC. Session/turn epochs and wall-clock backlog limits must cover
late provider replies, not only echo capture. Provider input pacing (currently
recommended/required 20ms in the studied APIs) is separate from device/DSP
10ms processing. Keys stay on the server/relay; no provider code, credentials,
or paid calls exist in this foundation. AEC/VAD and reports remain future work.

Primary API references: [Qt 6.11 capture](https://doc.qt.io/qt-6.11/qaudiosource.html),
[Qt 6.11 playback](https://doc.qt.io/qt-6.11/qaudiosink.html),
[PortAudio callback constraints](https://portaudio.com/docs/v19-doxydocs/writing_a_callback.html),
[PortAudio API](https://portaudio.com/docs/v19-doxydocs/portaudio_8h.html).
