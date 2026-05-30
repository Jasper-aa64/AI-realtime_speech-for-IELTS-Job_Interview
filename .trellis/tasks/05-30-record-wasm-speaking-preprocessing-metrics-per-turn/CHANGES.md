# Changes

## Implemented

- Added per-turn WASM preprocessing diagnostics.
- `web/static/wasm/speaking_audio_preprocessor.js` now exports `summarizeSpeakingAudioPreprocessingMetrics()`.
- `web/static/app.js` waits for the preprocessor stop summary before building the `/turns/{id}/complete` payload.
- Completion payloads now include `audio_preprocessing_metrics` only when the developer flag produced diagnostics.
- `backend_django/apps/speaking/services.py` sanitizes and stores the optional metrics in `SpeakingTurn.metadata`.
- Existing turn payloads expose `audio_preprocessing_metrics` when present.
- Added a Django regression test proving metrics are sanitized, persisted, and stripped of raw samples.

## Preserved

- Feature flag remains off by default.
- Uploaded `MediaRecorder` blob is unchanged.
- Browser dictation payload remains unchanged.
- No report UI changes.
- No database migration.
- Generated WASM artifacts remain ignored.

## Validation

- `node --check web/static/app.js`
- `node --check web/static/wasm/speaking_audio_preprocessor.js`
- `python3 -m py_compile backend_django/apps/speaking/services.py backend_django/apps/speaking/tests.py`
- `.venv-django/bin/python backend_django/manage.py test apps.speaking.tests.SpeakingRuntimeApiTests.test_turn_complete_persists_audio_preprocessing_metrics -v 2`
- `.venv-django/bin/python backend_django/manage.py test apps.speaking.tests -v 1`
- `scripts/build_audio_core_wasm.sh`
- `git check-ignore -v web/static/wasm/audio_core_wasm.js web/static/wasm/audio_core_wasm.wasm`
- Browser fake-mic smoke with WASM artifacts: summary includes analyzer, frame count, ratios, sample rate, frame size, and no raw samples.
- Browser fake-mic smoke with blocked WASM artifact: summary falls back to `mock-rms`, includes fallback reason, and no raw samples.
