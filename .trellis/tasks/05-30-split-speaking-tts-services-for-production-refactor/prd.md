# Split Speaking TTS Services for Production Refactor

## Goal

Continue reducing `backend_django/apps/speaking/services.py` by extracting the low-level TTS provider and audio path helpers into a focused service module while preserving public import compatibility.

## Scope

In scope:
- Add `backend_django/apps/speaking/tts_services.py`.
- Move TTS fallback contract, cache URL lookup, VolcEngine TTS generation, and TTS media path lookup.
- Re-export the moved names through `services.py` so existing views and tests keep their import paths.
- Keep higher-level examiner turn orchestration in `services.py` for now so existing patch paths around `services.volcengine_tts` continue to work.

Out of scope:
- TTS provider redesign.
- Browser TTS behavior.
- Background thread changes.
- Prompt/report generation behavior.

## Acceptance Criteria

- Public imports from `apps.speaking.services` for `tts_fallback`, `volcengine_tts`, and `tts_audio_path` still work.
- `ensure_examiner_tts()` still calls the re-exported `volcengine_tts` symbol from `services.py`.
- Speaking tests continue to pass.
- Django check and legacy runtime validation continue to pass.

