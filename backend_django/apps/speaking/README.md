# Speaking App Architecture

`apps.speaking.services` is still the compatibility facade for views and tests,
but new code should be split by responsibility instead of appended to the
facade.

Current split:

- `corpus_services.py`: IELTS question bank, P1/P2 corpus material, Takeaway,
  and translation helpers.
- `exceptions.py`: shared service exception types.
- `report_services.py`: report validity, history/detail/delete payloads, AI
  task summary payloads, and weak-item/replay-queue read models.
- `scoring_services.py`: pure score calibration, heuristic fallback scoring,
  relevance caps, transcript counters, and turn habit/focus tagging.
- `text_utils.py`: pure report/model-answer/coaching text cleanup helpers.
- `volcengine_asr.py`: ASR provider integration.
- `services.py`: compatibility facade and orchestration for attempts, reports,
  scoring, TTS, and runtime state transitions.

Next safe extraction targets:

1. `tts_services.py`: server TTS, fixed examiner warmup, and audio path lookup.
2. `runtime_services.py`: attempt start, turn upload/complete, abort, and score
   task creation.
3. `report_regeneration_services.py`: per-turn feedback retry/regenerate and
   full report regeneration helpers.

Refactor rule: preserve public imports from `services.py` until all views/tests
move to the narrower modules.
