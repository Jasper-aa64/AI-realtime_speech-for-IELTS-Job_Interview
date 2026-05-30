# Changes

## Phase 2.3 logic layer

- Extended `/ws/realtime/pcm/` to support explicit `start_asr` / `stop_asr` control events.
- The consumer now feeds binary PCM frames into the existing `stream_pcm_chunks()` provider through a background queue/thread, then forwards provider events back to the browser as `asr_started`, `asr_interim`, `asr_final`, `asr_done`, and `asr_error`.
- Existing PCM `pcm_ack` behavior remains intact.
- Frontend `?realtime_pcm=1` path now starts ASR after the PCM websocket opens and applies `asr_*` events to the live transcript state while keeping browser dictation and batch completion as fallback.

## Validation boundary

- Logic layer is covered with fake provider/websocket tests.
- Real openspeech/VolcEngine endpoint validation is pending user-provided ASR credentials and a real microphone smoke test.
- This task does not claim production realtime ASR quality yet.
