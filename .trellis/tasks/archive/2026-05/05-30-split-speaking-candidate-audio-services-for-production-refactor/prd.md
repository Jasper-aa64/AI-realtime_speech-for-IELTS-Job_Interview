# Split Speaking Candidate Audio Services for Production Refactor

## Goal

Move candidate audio upload, lookup, and server-ASR handoff helpers out of `apps.speaking.services` into a focused audio service module while keeping existing views/tests import-compatible.

## Scope

In scope:
- Add `backend_django/apps/speaking/audio_services.py`.
- Move `MAX_AUDIO_BYTES`, `upload_turn_audio`, `transcribe_turn_audio_with_server_asr`, and `get_turn_audio_path`.
- Re-export moved functions through `services.py`.
- Preserve existing validation, metadata fields, media paths, and response shape.

Out of scope:
- Turn completion flow changes.
- ASR provider redesign.
- Audio preprocessor metrics refactor.
- Frontend upload changes.

## Acceptance Criteria

- Existing `apps.speaking.services` imports for audio helpers continue to work.
- Speaking tests pass.
- Full Django tests pass.
- No migrations are generated.
- Legacy server retirement validation still passes.

