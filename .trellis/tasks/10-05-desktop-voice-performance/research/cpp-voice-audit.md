# Research: original C++ voice engine and interview backend reuse

- Query: Can the original C++ realtime prototype be reused for a native desktop, low-latency interview product, and should the interview backend live in speaking?
- Scope: internal source audit; no paid provider calls, microphone session, code changes, or git operations.
- Date: 2026-10-05 (Asia/Shanghai).
- Repository: `/Users/mac/Documents/trading-study/AI-realtime_speech-for-IELTS-Job_Interview`.

## Findings

### Verdict

Keep C++ ownership of the voice engine. Qt remains suitable as the UI and event adapter; choosing it does not change the implementation language, and replacing PortAudio with Qt Multimedia is not inherently a latency improvement. Reuse the existing protocol examples, useful pure DSP helpers and interview domain ideas. Rebuild the session lifecycle, device/transport orchestration and bounded streaming path rather than linking the current `DialogSession` into the new desktop shell unchanged.

The original project contains an actual native streaming implementation, not just a concept. Its source sends PCM to a provider and plays returned audio. This audit establishes implementation presence, not a successful current end-to-end run. The new `desktop/` application has no native voice integration yet. The web runtime has a separate feature-gated streaming ASR path, with mocked integration tests, so “no realtime code exists” would also be inaccurate.

### Files found

| File | Role |
| --- | --- |
| `src/services/audio_manager.cpp` | PortAudio blocking capture/playback and device cleanup. |
| `src/services/realtime_client.cpp` | Synchronous Beast TLS/WebSocket operations and receive worker. |
| `src/common/protocol.cpp`, `include/common/protocol.h` | Provider binary framing, event/session fields, gzip, JSON/binary parsing. |
| `src/interview/dialog_session.cpp` | Native interview orchestration, microphone/playback workers, answer processing. |
| `src/interview/interview_manager.cpp` | Resume question generation, scoring, one follow-up per question, JSON report. |
| `src/services/llm_client.cpp` | Blocking curl LLM requests. |
| `src/ielts/realtime_speech_capture.cpp` | CLI realtime ASR capture with local recording and terminal fallback. |
| `src/ielts/audio_core.cpp`, `src/ielts/audio_core_wasm.cpp` | Pure DSP helpers and C ABI/WASM wrappers. |
| `src/ui/mainwindow.cpp` | Original Qt Widgets GUI; queued Qt callbacks. |
| `desktop/CMakeLists.txt`, `desktop/src/*` | New WebEngine desktop shell; separate target. |
| `backend_django/apps/speaking/{consumers,volcengine_asr}.py` | Django PCM uplink, ASR worker/provider relay. |
| `backend_django/apps/speaking/{models,report_services,audio_services,tts_services,scoring_services}.py` | IELTS persistence, reports, media and scoring. |
| `backend_django/apps/ai/{models,services,http_provider}.py` | Existing shared durable AI tasks, provider calls and accounting links. |

### What is connected today

- Root `CMakeLists.txt:20` builds the original CLI with audio, realtime and interview sources. `CMakeLists.txt:78` builds the original Widgets GUI with the same native path; `CMakeLists.txt:130` builds the IELTS CLI and realtime capture.
- New `desktop/CMakeLists.txt:7` uses Qt Widgets/WebEngine/Test. Its `studio_core` source list at line 10 includes browser/profile/navigation/settings code only. No PortAudio/Beast/audio engine source or WebChannel voice bridge is linked there. Microphone permission handling at `desktop/src/navigation_policy.cpp:28` is browser permission policy, not native capture.
- `web/static/realtime-pcm-uplink.js:45` gates server streaming behind the `realtime_pcm` URL parameter; normal absence of that parameter disables it. The fake/mock/simulate modes are explicit. `web/static/app.js:6443` also retains browser SpeechRecognition.
- `backend_django/apps/speaking/routing.py:8` exposes PCM/ping WebSockets; `consumers.py:152` connects PCM chunks to the provider; `volcengine_asr.py:318` performs actual server-side provider streaming. This is separate from the native C++ prototype and does not prove native interview dialogue works today.

### Concrete native faults and performance bottlenecks

| Area | Source evidence | Consequence / required boundary |
| --- | --- | --- |
| Capture batching | `config/default_config.json:4` uses 3,200 input frames at 16 kHz (line 6). `audio_manager.cpp:125` allocates a vector and blocks for the full read. | 200 ms of audio per read before transmission; do not call the 10 ms sleep a 10 ms audio frame. At a uniform sample arrival time, batching alone contributes up to 200 ms, about 100 ms on average, before network delay. Prototype baseline should quantify this. |
| Drift/backpressure | `dialog_session.cpp:304` reads audio then `:314` synchronously writes the network; `:326` adds a 10 ms sleep. `realtime_speech_capture.cpp:197` does the same serialized capture/send and `:214` sleep. | Network stall stops capture consumption; nominal 200 ms read + write + sleep can fall behind device time and overflow. Separate device deadlines from network availability using bounded queues. |
| Playback batching | `config/default_config.json:11` uses 4,800 output frames at 24 kHz (line 13). `audio_manager.cpp:94` opens that buffer, and `:149` performs blocking writes. | 200 ms configured buffer size is a baseline setting, not evidence of measured 200 ms acoustic output delay; inspect actual device latency and queue residence. |
| Callback safety | Both `Pa_OpenStream` calls pass null callbacks (`audio_manager.cpp:60`, `:101`). | There is currently no real-time PortAudio callback whose safety can be claimed. For a callback rewrite, only fixed-cost copies and atomic counters belong there; allocation, logging, mutex waits, network and LLM work must remain outside. |
| Concurrent socket operations | `realtime_client.cpp:161`, `:190`, `:436`, `:444` all directly write the same `ws_`; `:205` reads on a receive worker. Mic thread sends at `dialog_session.cpp:314`, playback thread sends prompts via `:407` / `:480`, and stop callers perform close/control writes. | The application supplies no serialized ownership of writes or close and no protection for `ws_` lifetime. Atomic connected/running flags do not serialize stream access. Move to one I/O owner and an ordered write queue; verify the selected transport's concurrency contract in component research. |
| TLS | `realtime_client.cpp:41` loads trust roots but `:42` selects `verify_none`. | Peer certificate verification is disabled. Restore peer and hostname verification before a deployed native path; preserve a distinct test-only local-server configuration if needed. |
| Startup protocol | `realtime_client.cpp:125` marks connected before connection/session acceptance. `:396` parses connection response but only logs its event; `:422` sends StartSession without waiting for SessionStarted. `dialog_session.cpp:100` substitutes a fixed 100 ms sleep. | No ready-state contract or acknowledgement validation; connection rejection or delayed session readiness may be misreported as connected. Wait on explicit accepted/rejected states with deadlines. |
| Stop order | `dialog_session.cpp:134` joins mic/playback before closing transport or device; mic may be inside blocking socket write/read and playback may be inside device write or LLM call. `realtime_client.cpp:303` synchronously closes before joining receive thread. | Flags cannot interrupt blocked I/O. Shutdown has no overall deadline or explicit abort/cancellation sequence; joins can hang or race stream operations. Define cancellation, unblock operations, then join their owned workers. |
| Callback reentrancy | `dialog_session.cpp:291` calls Stop directly inside provider-end handling on the receive worker. `realtime_client.cpp:314` detaches its own thread on self-close and resets `ws_` at `:329`. | Cleanup re-enters receive handling and abandons owned-thread joining; destruction/restart can race the callback that is still unwinding. Post a stop request to the session owner instead. |
| Detached finalizer | `dialog_session.cpp:437` launches a detached lambda capturing `this`; `:443` reads `audio_queue.empty()` without its mutex and `:448` calls Stop after extra sleeps. | Concrete queue data race plus potential use-after-free if session is destroyed before the detached worker exits. Make finalization an owned, cancellable state transition; queue status must use the same synchronization as mutation. |
| Partial startup/destruction | `dialog_session.cpp:98` connects before audio opening. `:106` only then sets running; Stop at `:126` returns when not running. Members declared at `:24-50` are destroyed in reverse order, while the realtime callback captures `this` (`:92`). | An audio-open/startup failure leaves the receive callback active while Stop declines cleanup; member destruction can remove synchronization/state before the realtime client shuts down. Cleanup must apply to partially started states and unregister/join callbacks first. |
| Queue bounds | `dialog_session.cpp:48` declares an unbounded audio queue; receive pushes copied float vectors at `:188-192`, playback copies again at `:354`. | Provider bursts increase memory and latency without a cap. Express capacity in milliseconds, track residence time/high-water marks and choose an overflow policy. Clearing a queue cannot cancel a chunk already passed to a blocking device write. |
| Interruption | `dialog_session.cpp:308-312` replaces microphone input with silence during TTS; `:235-238` ignores USER_START_SPEAKING during TTS. | Existing behavior is half-duplex. The subsequent “barge-in” queue clear at `:240` cannot implement interruption while the interviewer is speaking. Full duplex needs continuous capture, echo handling, turn IDs, provider cancellation and stale-chunk rejection. |
| Critical-path LLM | Playback worker calls ProcessPendingAnswer at `dialog_session.cpp:381`, which performs synchronous RecordAnswer (`:412`), summary (`:429`) and prompt network calls. `llm_client.cpp:65` is a full blocking HTTP request, not a token/audio stream. | Scoring blocks the playback consumer and shutdown, and an extra provider text-query path at `realtime_client.cpp:175` wraps the prewritten text in another generative prompt. Move scoring/report work off the conversation path and measure ASR, first LLM token, first TTS chunk separately. |
| Answer/callback concurrency | `interview_manager.h:41` declares InterviewSession non-thread-safe; receiver reads question index at `dialog_session.cpp:263` while playback advances at `:417`. Callback field assignment at `:513` is unsynchronized, and pending_answer is a single slot at `:268`. | Session state should belong to one owner; final ASR segments should use stable turn/utterance IDs rather than overwriting the previous unconsumed segment. Dispatch callback changes safely and do not run user callbacks under engine locks. |
| State callback lock | `interview_state.cpp:36-38` invokes callback while holding callback_mutex. | A callback that clears/registers itself or re-enters a state change can deadlock. Copy callback under lock and dispatch outside it, with lifetime rules. The existing Qt UI does use queued UI updates (`mainwindow.cpp:40`, `:385`), a useful adapter pattern. |
| Signal handler | `src/main.cpp:51-54` performs iostream output and full Stop in a signal handler. | Stop involves allocation, locks, join, network and file writes, which are inappropriate in an asynchronous signal context. Handler should set a signal-safe flag or wake the owner. |
| Device contract | `audio_manager.cpp:39`, `:84` selects only default devices, `:45` hardcodes int16 input, `:90` hardcodes float32 output. No hotplug, negotiated format, clock drift or streaming resampler is present. `config.cpp:142-158` validates numerical bounds but not codec/rate/channel consistency. | Configured format fields cannot guarantee capture/playback/provider agreement. Match channel, endian, format and rate explicitly, detect device changes and use an external streaming resampler when conversion is needed. |

### Protocol and DSP reuse: worthwhile, with limits

- The binary parser already checks available bytes before reading sequence/event/session/connect/payload fields (`protocol.cpp:107-170`). The float conversion no longer copies a nonaligned byte count: `dialog_session.cpp:183-189` checks divisibility by sizeof(float) before copying. Do not report those as existing unchecked buffer overruns.
- Remaining parser gaps: version is read but not validated (`protocol.cpp:82`); header size zero/unsupported compression are not explicitly rejected; malformed JSON falls back to binary at `:195-197`, potentially treating a malformed ACK as audio. Gzip expansion doubles capacity without a decompressed-size ceiling (`:317-334`). The realtime client does not supply an explicit product message-size budget. Add typed parse errors and finite limits, fuzz with ASan/UBSan, and compare fixtures to current provider documentation.
- Request building has reserved capacity (`protocol.cpp:412`, `:448`) and sends uncompressed PCM (`:451-455`), useful baseline behavior. It still allocates/copies each frame; prefer a reusable envelope buffer outside device callback before considering sophisticated zero-copy changes.
- `audio_core.cpp:72-105` has pure RMS/peak helpers and threshold detection. Reuse their behavior/tests for diagnostics outside the device callback, with non-owning input spans if needed.
- WebRTC VAD is present via bundled libfvad, but `audio_core.cpp:114-126` creates/configures/frees a new VAD for every frame, resetting state and allocating. A streaming engine should keep one VAD state per stream off the device callback. VAD is not echo cancellation.
- `audio_core.cpp:179` is stateless linear interpolation with allocated output. It is useful for deterministic simple tests, not an anti-aliased, stateful production sample-rate conversion path. WASM wrappers copy input (`audio_core_wasm.cpp:14-24`); their existence does not mean current native streaming uses them.
- Original interview domain has reusable ideas: resume extraction/questions (`interview_manager.cpp:141-179`), scoring and follow-up (`:240-293`) and report structure. Do not copy its fallback score of 50 (`:280`) as a successful score. There is also a follow-up provenance bug: GetFollowUpQuestion clears followup_question at `:231`, while RecordAnswer decides whether an answer is a follow-up using that same field at `:251`, so it can record/evaluate the follow-up as the main question.

### Existing tests: presence is not performance or integration proof

| Tests | Actual source-backed coverage | Gaps |
| --- | --- | --- |
| `tests/protocol_test.cpp` | Many deterministic framing, combined flags, truncation, error, gzip/JSON/binary and round-trip fixtures (`:185`, `:347`, `:665`, `:1005`, `:1280`). | No production provider compatibility, TLS, I/O races, decompression bombs, fuzz campaigns or latency distribution proof. |
| `tests/services_test.cpp:12-95` | Construction/cleanup, callback registration, closing an unconnected client. | It explicitly does not invoke the callback (`:83`). No live connect/send/receive, device capture, backpressure, concurrent shutdown, interruption or restart. |
| `tests/interview_test.cpp:11-63` | Empty session getters/prompts, missing questions, empty summary/report, JSON file writing. | No resume generation/scoring/follow-up lifecycle, concurrent sessions or native dialogue completion. |
| `tests/audio_core_test.cpp:19-144` | RMS/silence trim, linear resample, config validation, VAD initialization and silence rejection. | No sustained VAD stream continuity, acoustic false-trigger evaluation, AEC, hardware/queue latency or callback deadlines. |
| `desktop/tests/*` | New shell settings/navigation/error pages (`desktop/CMakeLists.txt:42-44`). | No native voice target to validate yet. |
| Django `test_asgi_channels.py`, `test_realtime_asr.py`, `test_streaming_followups.py` | PCM aggregation/partial flush (`test_asgi_channels.py:44-65`), fake-provider interim/final/errors (`:102`, `:220`), mocked provider idle/partial disconnect (`test_realtime_asr.py:124-218`), ASR-to-follow-up-to-TTS (`test_streaming_followups.py:401`). | Fake/mock fixtures do not establish real provider latency, acoustic interruption or industrial readiness. No bounded queue/restart race coverage found in these targeted files. |

Tests were inspected, not run by this read-only researcher. No fresh pass count, hardware measurements, p95/p99 figures or “faster than industry” claims can be inferred from source or file names. Root CMake registers the native test targets; the new desktop target is independent and passing it would not validate old voice code.

### Django interview domain placement

Recommendation: add `apps.interview` within the existing Django service, with interview session/turn/report models, resume/job-description inputs, technical rubrics and question provenance. Share AI provider/task/account/media primitives through narrow interfaces; do not add an “interview” mode that forces technical interviewing through IELTS scoring/report schemas. This is an app boundary, not a new deployed microservice.

Evidence:

- Speaking is concretely IELTS-specific: P1/P2/P3/mock modes, target_band (`speaking/models.py:13-28`), IELTS report criteria (`:71-80`), band-based training observations (`:92-108`), mandatory Band 7 rewrite validation (`report_services.py:83-92`), ielts_score payload (`:108-116`) and explicit IELTS prompt guidance (`scoring_services.py:259-280`). A technical interview has different correctness/evidence/relevance rubrics and resume/JD provenance.
- Existing shared `AITask` already carries generic task_type, related_type/id, provider/model, prompt_version, lifecycle, request/result payload, billing reservation and usage (`ai/models.py:18-55`). Reuse that lifecycle and add interview-specific adapters/types rather than porting client-side synchronous curl scoring. Preserve the distinction between cancelling live speech and cancelling billed durable analysis: `ai/services.py:344-351` permits user cancellation only while pending.
- Media upload/ownership/limit behavior in `audio_services.py:18-63` is valuable but currently hard-wired to SpeakingAttempt/Turn. Extract proven primitives behind a narrow domain adapter when the second consumer is implemented; avoid a broad refactor beforehand. The report/history UI may reuse layout components while requiring an interview-specific payload contract.
- `tts_services.py:54` already has provider/cache behavior, but its docstring at `:65-69` explicitly identifies an unofficial endpoint. Treat it as compatibility infrastructure; official streaming TTS for the new realtime path needs its own verified provider adapter.

### Existing relay hardening needed before treating it as deployment-ready

- `consumers.py:118` uses queue.Queue with no capacity; binary messages are copied/queued and acknowledged without sample/frame-size budgets (`:63-74`). At `REALTIME_ASR_CHUNK_BYTES=3200` (`:14`) and advertised 16 kHz mono int16, the provider is batched in 100 ms chunks. `volcengine_asr.py:321`, `:366`, `:387` also allows 20 ms receive polling and a 20 ms artificial inter-chunk sleep. Benchmark and reduce each independently.
- `_stop_asr_thread` clears shared queue/thread references without joining (`consumers.py:122-125`), while old worker and new worker access the same self fields (`:132-167`). Old finally can clear a new stream; a consumer restart needs owned per-stream context, generation IDs and bounded termination.
- ASGI wraps AuthMiddlewareStack/AllowedHostsOriginValidator (`config/asgi.py:25-27`), but PCM consumer accepts immediately (`consumers.py:54`), does not reject anonymous users and does not validate ownership of attempt_id/turn_id (`:210-221`). PCM tests connect with no session (`test_asgi_channels.py:67-77`). An allowed origin is not user authorization or a provider quota. Native relay should authenticate and authorize session/turn ownership with admission/resource limits.
- Provider relay currently serializes chunk iteration, socket send and response polling (`volcengine_asr.py:370-388`). This is a useful compatibility starting point, not a proven full-duplex conversation engine.

### Recommended implementation sequence and measurement contract

1. Preserve original native prototype as a reference/benchmark target. Build a standalone C++ engine with explicit session owner, device backend, transport owner, bounded PCM rings and turn-generation IDs; connect it to Qt through a queued adapter. Choose mature components using the companion component/authentication research.
2. Start with 10/20 ms device-side processing blocks and separately tune provider packet cadence. This is an experiment, not a guaranteed service latency. Keep callback allocation/logging/locks/LLM work at zero; count overflow/underflow and queue delay.
3. Record monotonic stage timestamps for device capture -> input enqueue -> transport send -> provider interim/final -> LLM first token -> TTS first bytes -> playback enqueue -> device callback. Use a loopback/acoustic measurement for actual sound output; a “socket received” timestamp is insufficient.
4. Report median/p95/p99 local callback time, local queue residence, ASR interim delay, end-of-speech-to-first-audible-response, cancel-to-silence and memory/CPU. Compare same machine/device/provider/network, warm/cold sessions, repeated trials and identical utterances. Local C++ improvements must not be conflated with cloud model inference or internet RTT.
5. Validate silence/noise, long speech, TTS interruption, packet burst/slow network, disconnect/auth expiry, rapid start-stop/restart, startup failure and device change. Use sanitizer builds for native races/lifetimes and deterministic fake transports for cancellation/backpressure. Only then perform provider/hardware end-to-end tests and decide deployment.

## Related specs

- `.trellis/spec/backend/directory-structure.md`: independent native feature targets, explicit Django domain apps, thin API adapters.
- `.trellis/spec/backend/quality-guidelines.md`: Django-only production runtime, smaller cohesive helpers, HTTP-first latency-sensitive follow-ups, durable billed task cancellation rules.
- `.trellis/spec/frontend/wasm-audio-guidelines.md`: generated WASM is optional; diagnostics must preserve baseline flows and explicit fallback metadata.
- `.trellis/spec/guides/code-reuse-thinking-guide.md`: search existing behavior before adding duplicates; extract shared boundaries when justified.

## External references

None fetched for this internal source audit. Current component concurrency/authentication/API documentation belongs in `native-voice-components.md`. Findings about code paths are source-backed; proposed design boundaries and measurement steps are engineering recommendations, not measured performance results.

## Caveats / Not Found

- Did not start provider calls, microphone capture or original binaries; current credentials/service compatibility are unverified.
- Did not inspect or disclose secret values. Only numeric audio configuration fields were read from default config; source includes a legacy API-key-prefix log at `src/main.cpp:181`, which should be removed when that entry path is reused.
- No existing native device callback implementation, full-duplex interruption/AEC integration, native-to-new-desktop bridge, percentile latency suite or bounded end-to-end shutdown contract was found in the audited source.
- No industrial benchmark comparison is present; small deployment size alone does not establish superior latency or robustness.
- This audit does not implement or fix the reported faults; critical production hardening must be a separately scoped implementation task.
