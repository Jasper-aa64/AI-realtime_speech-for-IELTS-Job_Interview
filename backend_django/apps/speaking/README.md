# Speaking App Architecture

`apps.speaking.services` is still the compatibility facade for views and tests,
but new code should be split by responsibility instead of appended to the
facade.

Current split:

- `text_utils.py`: pure report/model-answer/coaching text cleanup helpers.
- `volcengine_asr.py`: ASR provider integration.
- `services.py`: compatibility facade and orchestration for attempts, reports,
  scoring, TTS, corpus, Takeaway, history, and training.

Next safe extraction targets:

1. `tts_services.py`: server TTS, fixed examiner warmup, and audio path lookup.
2. `runtime_services.py`: attempt start, turn upload/complete, abort, and score
   task creation.
3. `report_services.py`: history payloads, report payloads, per-turn feedback,
   and retry/regenerate helpers.

Refactor rule: preserve public imports from `services.py` until all views/tests
move to the narrower modules.
