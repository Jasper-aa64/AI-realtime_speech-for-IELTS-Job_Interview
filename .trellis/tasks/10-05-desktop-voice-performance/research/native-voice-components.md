# Research: Native C++ low-latency voice components and authentication

- Query: Audit the suitability of mature native audio and WebSocket components for a measurable C++ full-duplex speech engine; verify whether Volcengine realtime dialogue documents temporary scoped desktop credentials.
- Scope: mixed; proposals only, no new voice implementation or measured performance claims.
- Date: 2026-10-05 (Asia/Shanghai).
- Repository: `/Users/mac/Documents/trading-study/AI-realtime_speech-for-IELTS-Job_Interview`.

## Findings

### Recommendation and why Qt is still C++

Keep Qt as the desktop shell and QWebChannel control adapter. Build a standalone C++ voice engine with clear device, DSP, transport, session and metrics boundaries. Qt Multimedia and Qt WebSockets are C++ libraries; choosing them does not change the application's language to another stack. The meaningful interview evidence is ownership of bounded buffering, threading, cancellation and measured tail latency, not avoiding a framework's name.

Do not rewrite everything into Qt merely to reduce dependency count. Conversely, do not infer that PortAudio beats Qt from the library names. Use the existing PortAudio dependency for the first callback backend and keep a Qt 6.11 callback backend as a credible measurement alternative. Select by actual hardware/OS measurements and maintenance cost. miniaudio is another credible candidate when simplifying cross-platform packaging matters; adding three device backends immediately is unnecessary.

### Files and code patterns found

| File | Evidence / relevance |
| --- | --- |
| `desktop/CMakeLists.txt:4` | Current standalone shell uses C++17; line 7 permits Qt >=6.8 and currently links Widgets, WebEngineWidgets and Test only. Multimedia/WebSockets are not integrated. A Qt callback implementation requires a 6.11 minimum or explicit compile-time fallback. |
| `src/services/audio_manager.cpp:53` | Existing PortAudio capture stream passes a null callback at line 60, using blocking I/O. Output does the same at lines 94–102. This is a wrapper choice, not a PortAudio limitation. |
| `src/services/audio_manager.cpp:125` | Every blocking read allocates a vector and calls `Pa_ReadStream`; lines 137–149 use blocking playback. These can be reference code but are not a callback-safe engine. |
| `src/services/audio_manager.cpp:49` | Existing comment records a Bluetooth/block-size issue: 3200 samples at 16k =200ms. This is historical repo evidence, not a fresh reproducible benchmark or proof of root cause. |
| `src/services/realtime_client.cpp:5` | Existing transport uses Boost.Beast and SSL. Detailed concurrency/cancellation findings belong to `cpp-voice-audit.md`; using Beast does not make the wrapper safe automatically. |
| `include/services/realtime_client.h:28` | Existing header illustrates provider endpoint and old App-ID/Access-Key headers; provider documentation must remain the authority for current protocol/auth. |
| `docs/reports/qt-desktop-mock-interview-handoff-2026-10-05.md` | Current handoff proposes forwarding a long-lived provider key if ephemeral credentials are unavailable. Replace this fallback with an authenticated server relay proposal. |

Related specs: `.trellis/spec/guides/cross-layer-thinking-guide.md` requires explicit formats/errors at every boundary; `.trellis/spec/frontend/wasm-audio-guidelines.md` keeps browser production recording independent of experimental audio and only sends small diagnostic summaries, not raw frame arrays, in ordinary report payloads. Native PCM belongs on the streaming media path, not on QWebChannel or report JSON.

### Device API comparison (primary documentation)

| Candidate | Verified capabilities | Constraints / decision |
| --- | --- | --- |
| PortAudio v19 callback API | Capture/playback callback receives device buffers, frame count, callback time information and status flags. Official guidance forbids unbounded operations such as heap allocation, file/console I/O, mutexes and arbitrary PortAudio calls in the callback. | Already used in repo, good first controlled backend; use callback mode, preallocated buffers, explicit underflow/overflow counters. Requested low latency is not a hardware guarantee. |
| Qt 6.11 QAudioSource/QAudioSink callbacks | Both expose `start(Callback&&)` since 6.11. QAudioSource uses `QSpan<const SampleType>`; QAudioSink fills `QSpan<SampleType>`. They run on the soft-realtime audio thread and bypass QIODevice. Supported on CoreAudio, Windows, Linux PulseAudio/PipeWire and Android per docs. | Genuine native C++ low-latency candidate on the repo's stated Qt 6.11.2. Same no blocking/locking/allocation constraints. Callback size is backend-driven; `setBufferSize()` does not tune callback size. |
| Qt QIODevice mode | Application thread exchanges data with an audio-thread wait-free ringbuffer. Official 6.11 docs describe a default capacity of 250ms; `setBufferFrameCount()` exists since 6.10 and actual size must be checked after start. | Capacity is not fixed end-to-end latency; occupancy matters. Avoid unexamined defaults. Do not compare this mode against optimized PortAudio callback mode and call that a general Qt result. |
| miniaudio low-level device API | Asynchronous callback supports playback/capture/full duplex; device config chooses formats/sample rate. Device-native format can avoid automatic conversion overhead. Device structures are exposed, low-level API is separate from the high-level engine. | Callback cannot init/uninit/start/stop the device (deadlock). Same realtime restrictions still apply. Prefer low-level device API for voice; automatic conversion must be recorded so benchmarks remain comparable. No established speed advantage over PortAudio/Qt in this audit. |

Version warning: the unversioned Qt `qt-6` documentation currently serves **Qt 6.12**, including `setNativePeriodFrameCount()`/`nativePeriodFrameCount()` introduced in 6.12. These APIs must **not** be assumed present on installed 6.11.2. This comparison checked the explicit 6.11 QAudioSource docs. No Qt upgrade is requested. The QIODevice ringbuffer knob must not be described as a 6.11 native hardware-period knob.

PortAudio explicitly cautions that a nonzero fixed `framesPerBuffer` can add host-adaptation buffering; prefer backend-driven callback sizes plus a separate 10ms DSP rechunker unless a measured reason requires fixed callbacks. Do not equate a chosen frame count with hardware latency. In Qt 6.11 on Linux/Darwin, `QAudioSink::stop()` drains audio synchronously; `reset()` is the documented immediate buffer-discard operation. Device owner/control logic should handle interruption without blocking the audio callback.

Sources:
- [PortAudio API reference](https://portaudio.com/docs/v19-doxydocs/portaudio_8h.html).
- [PortAudio callback guidance](https://portaudio.com/docs/v19-doxydocs/writing_a_callback.html).
- [Qt 6.11 QAudioSource](https://doc.qt.io/qt-6.11/qaudiosource.html), [Qt 6.11 QAudioSink](https://doc.qt.io/qt-6.11/qaudiosink.html).
- [Qt 6.12 QAudioSource version warning](https://doc.qt.io/qt-6/qaudiosource.html).
- [miniaudio official manual](https://miniaud.io/docs/manual/index.html).

### Echo cancellation and DSP

PortAudio/miniaudio are device I/O libraries; neither is an acoustic echo canceller. Existing libfvad is speech activity detection, not AEC. For speakerphone duplex voice, evaluate **WebRTC Audio Processing Module (APM)** rather than inventing AEC. Its current official C++ header exposes echo cancellation, noise suppression and gain control. Capture goes to `ProcessStream`, actual render audio goes to `ProcessReverseStream`/the render-analysis path, near the hardware boundary. AEC also needs the render/capture timing delay via the documented stream-delay contract.

Current APM source describes approximately 10ms frames. Integer interfaces have native 8/16/32/48kHz rates; float interfaces accept a broader range (header states 8k–384kHz). Do not feed provider 24kHz playback blindly into an integer 16kHz AEC path. Define an internal device/DSP format (48k float is an experiment candidate), frame/rechunk and resample explicitly, then upload the provider-required 16k mono S16LE. Two 10ms DSP frames can become one recommended 20ms network packet.

The playback reference should represent what actually reaches the output chain, including mix/resample/gain and discarded interrupted audio, not all received/generated TTS. Device and TTS clocks can differ; track drift and actual playout position. APM stream setters must follow documented thread restrictions; do not call processing concurrently with stream setters. Initialize/control APM outside the device callback and run DSP in its bounded worker path unless callback-safety has been verified for a pinned configuration.

Tradeoff: APM brings integration/build and ongoing version maintenance, and DSP can affect pronunciation evaluation. Measure residual echo, double-talk/barge-in behavior and recognition quality. Headset mode can bypass unnecessary DSP. No claim that a VAD or AEC algorithm eliminates network/inference delay.

Source: [Current WebRTC APM public C++ header](https://webrtc.googlesource.com/src/+/refs/heads/main/api/audio/audio_processing.h). The former `modules/audio_processing/include/audio_processing.h` is now a forwarding header; pin a reviewed commit before implementation rather than depend on moving main.

### Transport comparison

**Boost.Beast** is useful for a standalone C++ engine because it leaves queuing, buffering/allocation strategy and backpressure to the caller. Official docs state a shared websocket stream is not thread safe; use an implicit/explicit Asio strand. One read and one write can be outstanding, but two concurrent writes (or reads) are invalid. Maintain one serialized writer queue; payload memory must outlive the operation; synchronize cancellation/close/state transitions through the owner executor. TLS certificate/hostname verification is required by the design, and has to be reviewed in the old wrapper.

**QWebSocket** remains a reasonable C++ alternative on a dedicated QObject/event-loop owner thread. It exposes `bytesToWrite()`/`bytesWritten`, limits on incoming frames/messages and a read-buffer size. `sendBinaryMessage` accepting data is not a cloud acknowledgement. `flush` is nonblocking and does not mean server received data. Bound the application's outgoing queue and monitor Qt's queued bytes; use a congestion timeout or explicit failure when a latency bound is exceeded. Do not hide congestion by endlessly accumulating PCM.

No benchmark here proves that one transport is faster. On 20ms speech packets over TLS, packet accumulation, endpointing, network and inference can dominate an API's local serialization overhead. Keep raw media off GUI/QWebChannel; send only control/status/coalesced meter and transcript updates there.

Sources: [Beast websocket notes](https://www.boost.org/doc/libs/latest/libs/beast/doc/html/beast/using_websocket/notes.html), [Qt 6.11 QWebSocket](https://doc.qt.io/qt-6.11/qwebsocket.html).

### Volcengine realtime authentication and media contract

Verified public source: [Official end-to-end realtime voice API](https://docs.volcengine.com/docs/DoubaoVoice/End-to-endreal-timespeechlargemodelAPIaccessdocument?lang=zh), page reports update 2026-09-28.

Documented endpoint remains `wss://openspeech.bytedance.com/api/v3/realtime/dialogue`. Required headers include `X-Api-App-ID`, `X-Api-Access-Key` (console Access Token), `X-Api-Resource-Id` (`volc.speech.dialog`) and a documented fixed `X-Api-App-Key`; `X-Api-Connect-Id` is optional tracing. Calling a value “Access Token” does not establish that it is short-lived, scoped, per-user or safely mintable by the application server. The inspected API page provides no mint endpoint, expiry/refresh contract, scoped ephemeral credential or STS handshake for this WebSocket.

**Conclusion: temporary/scoped auth for this exact endpoint is not confirmed by the checked public documentation.** This is not proof that the provider cannot support it privately. Ask provider/support for exact issuance API, duration, allowed resource/session scope, renewal and revocation, and validate a real handshake before choosing direct multi-user desktop access. Generic Volcengine IAM STS and RTC room tokens are different services; they cannot be substituted into this endpoint by analogy.

Until that confirmation, recommend authenticated **streaming server relay**: native client sends media to application's server, server owns provider key and forwards packets immediately. Application-issued expiring session ticket authorizes the relay only; it is not a provider credential. Keys remain server-side, even for small deployments. Local development can use a local relay with a developer-owned server environment key. Relay latency must be measured as a separate segment, and server location can be selected later; VPS purchase remains deferred. Do not implement `POST /api/realtime/credentials` returning the long-lived server key.

Media findings from the same official page: capture PCM is mono 16kHz int16 little-endian; recommended microphone upload is **20ms packets (=640 bytes)**. Device/DSP can process 10ms frames and aggregate two; do not shorten network packets without a provider compatibility experiment. Default output is Ogg Opus; PCM alternatives are 24k mono float/32bit (`pcm`) or S16LE (`pcm_s16le`). The packetizer and decoder must agree with StartSession format. ASRInfo event 450 signals first recognised speech for interruption; server endpointing is a distinct latency component. Local VAD can trigger local mute/interrupt sooner while session state must reject stale reply/session epochs.

**New separate full-duplex product:** [Official full-duplex realtime voice API](https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh) now documents `wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue` and new-console `X-Api-Key` authentication. It explicitly recommends 20ms input cadence (640 bytes for 16k/int16) and warns that too-fast/too-slow pacing can produce errors; microphone mute/unmute has explicit protocol events. This is an additional product/protocol candidate, **not** a drop-in URL replacement for the existing binary realtime wrapper. Evaluate English interview/IELTS quality, full-duplex interruption, current events/format, access/account support and measured latency before deciding between old endpoint and this newer one. The inspected page still does not document scoped ephemeral key issuance. A Web demo asking for a console API key is not evidence that a shared server key may be distributed to application users. The linked [API Key usage page](https://docs.volcengine.com/docs/DoubaoVoice/APIKeyUsage?lang=zh) scrape yielded insufficient substantive content to establish expiry or scoping; no conclusion is drawn from that page.

Separate possible product path: official RTC search results describe server-generated room/user Token auth and RTC integration with realtime voice. This may be an alternative architecture worth evaluating later, not confirmed temporary credentials for `/api/v3/realtime/dialogue`. Full RTC content was cluttered by navigation, so do not adopt it based on search snippets alone. References: [RTC Token auth](https://www.volcengine.com/docs/real_time_communication/AuthenticationusingToken), [RTC integration guide](https://docs.volcengine.com/docs/6348/1315561).

### Measurement and optimization plan (experimental, not achieved claims)

1. Establish old native baseline and an identical-device native callback loopback before comparing to the browser. Use the same wired device, OS, machine, sample rate, gain and workload; test Bluetooth separately. Cloud-path comparison must also match model, server endpointing, audio formats, prompts and network path.
2. Keep callbacks allocation/lock/logging/I/O-free. Copy only into preallocated bounded SPSC rings; fill silence and increment atomic underrun counters on missing playback. DSP/network/report logging run on separate workers. Overflow policy must be explicit: fail/degrade session with telemetry rather than silently lose syllables or grow latency without bound. Preallocated ring indexes need a valid ownership/concurrency protocol; “lock-free” alone is not a guarantee.
3. Record monotonic timestamps for capture hardware/callback, ring consumption, DSP completion, packet-ready/write, first ASR, end-of-speech/server-ended, first TTS receipt/decode, playback queue and actual DAC estimate/loopback onset. Synchronize/label server clock estimates; do not subtract unrelated clocks. Record reconnect/handshake separately from steady-state turns.
4. Report P50/P95/P99 plus sample counts, jitter, maximum queue age/depth, underruns/overruns/dropped frames, callback CPU/duration, engine CPU/memory and interruption residual sound. p99 needs enough independent samples and test duration; average alone is insufficient.
5. Initial hypotheses to test: 10ms DSP processing blocks; 20ms provider packet cadence; callback/worker scheduling and DSP p99 below the block budget with headroom; application capture/send backlog bounded initially at roughly 40–60ms; adaptive playback buffering initially 40–80ms on wired devices; local interruption-to-silence p95 under 100ms where device constraints allow. These are starting tuning ranges, not published guarantees or acceptance achieved today. Measure quality/dropouts alongside every latency reduction; update targets after baseline. Cloud response latency is separately observed, not assigned a false universal target.
6. Implement epoch-based interruption, flush pending old output, and account for hardware audio that cannot be recalled. Disconnect/network backpressure/credential expiry/device changes must terminate or recover without replaying stale audio. Stress CPU load, network stalls, jitter, repeated start/stop, long sessions and close during callbacks. Validate speakerphone echo/double talk before calling it duplex production quality.

The controllable performance work is callback safety, buffer age, copies/allocations, DSP, packet cadence and local playback interruption. WAN, provider endpointing/inference and server capacity are distinct external terms. A small deployment may outperform a named baseline for a stated scenario, but “industrial level” or “better than industry” requires a repeatable comparable workload and results; no such measurement has been performed in this task.

## Caveats / Not Found

- Context7 was attempted first as instructed: PortAudio resolution (2 attempts), Qt resolution then docs, Volcengine resolution then docs, miniaudio/WebRTC/Boost.Beast resolutions. Qt/Volcengine library resolution succeeded; all subsequent docs requests and other resolutions failed with **invalid or expired OAuth token**, not a quota error. No silent training-data fallback: authenticated Firecrawl official-source search/scrape supplied the evidence. Re-authenticate Context7 via `npx ctx7@latest login` before the next Context7 lookup. No question exceeded three Context7 commands.
- Firecrawl was authenticated and had concurrency 2. Only this research Markdown is persisted; no external code/dependencies installed, no provider requests made, no secrets read or copied, no source/spec/git edits.
- Installed Qt 6.11.2 is recorded in the handoff; actual native callback build and device behavior are not tested here. Current desktop CMake's >=6.8 condition cannot guarantee the 6.11 API on other hosts.
- Open-source backend APIs and current moving docs do not establish maintenance suitability for every deployment. Pin tested versions, review licenses/distribution, supported OS devices and build reproducibility at implementation time.
- No public temporary credential contract found for the exact realtime endpoint; provider clarification is still needed. Preserve that uncertainty in the handoff, while replacing unsafe long-lived key distribution with a relay proposal.
