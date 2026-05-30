# Phase 2.1 ASGI Channels Ping WebSocket

## Goal

Introduce Channels/ASGI as an additive transport layer without changing any
business realtime ASR behavior yet.

## Scope

- Add Channels/Daphne dependency.
- Configure ASGI `ProtocolTypeRouter` so HTTP still goes to Django's existing
  ASGI app and WebSocket routes go through `AuthMiddlewareStack`.
- Add a minimal authenticated-safe ping WebSocket consumer for smoke tests.
- Add tests proving the ping WebSocket connects and echoes JSON.

## Out of Scope

- PCM upload.
- VolcEngine ASR streaming.
- Frontend realtime ASR UI.
- Any changes to current upload/batch speaking flow.

## Acceptance Criteria

- `python manage.py test apps.speaking.test_asgi_channels -v 1` passes.
- `python manage.py check` passes.
- Existing HTTP routes remain handled by Django ASGI application.
- No existing business WIP files are staged or committed.
