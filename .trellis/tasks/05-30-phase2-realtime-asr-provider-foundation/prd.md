# Phase 2 Realtime ASR Provider Foundation

## Goal

Build the first safe backend slice for Phase 2 realtime ASR: expose a secret-safe
VolcEngine readiness contract and factor the existing file-based ASR code into a
streaming PCM provider core that can be tested without browser or credential
dependencies.

## Scope

- Add a safe realtime ASR status payload that reports whether VolcEngine ASR is
  enabled/configured without exposing credentials.
- Add a provider-level PCM chunk streaming function that reuses the existing
  openspeech protocol implementation.
- Keep the existing batch `transcribe_audio()` behavior intact.
- Add owner-authenticated status endpoint for frontend/dev readiness checks.
- Add tests for config redaction and provider streaming behavior with a fake
  websocket.

## Out of Scope

- Browser audio streaming UI.
- ASGI/Channels/WebSocket server integration.
- Production deployment of a C++ realtime gateway.
- Any key or credential changes.

## Acceptance Criteria

- Existing batch ASR tests keep passing.
- New status endpoint never returns secret values.
- New streaming provider can emit interim/final events from fake ASR responses.
- `manage.py check` passes.
