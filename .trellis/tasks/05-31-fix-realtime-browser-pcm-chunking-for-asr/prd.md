# Fix Realtime Browser PCM Chunking for ASR

## Goal

Make browser realtime PCM frames produce VolcEngine ASR transcript events reliably.

## Problem

The validated CLI path sends VolcEngine realtime ASR audio in roughly 3200-byte PCM chunks. The browser AudioWorklet path sends much smaller frames through `/ws/realtime/pcm/`; the backend currently forwards each tiny frame to ASR immediately. Browser frames are acknowledged by the websocket transport, but VolcEngine does not emit transcript events consistently.

## Scope

- Aggregate browser PCM frames in `RealtimePcmUplinkConsumer` before yielding chunks to `stream_pcm_chunks`.
- Preserve per-frame `pcm_ack` metrics for transport diagnostics.
- Flush remaining buffered PCM when ASR stops.
- Add deterministic tests for chunk aggregation and existing fake ASR behavior.

## Out of Scope

- Frontend UI redesign.
- Provider credential changes.
- Realtime ASR protocol changes outside chunk sizing.
- Legacy server changes.

## Acceptance Criteria

- Browser-sized PCM frames are yielded to ASR as larger chunks matching the known-good provider path.
- Stop/close flushes the final partial chunk.
- Existing websocket ack behavior remains unchanged.
- Targeted speaking realtime tests pass.
- Real browser validation shows `asr_interim` or `asr_done` from realtime ASR after speaking.
