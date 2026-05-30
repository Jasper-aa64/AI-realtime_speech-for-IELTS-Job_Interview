# Split speaking corpus services production pass

## Goal

Continue the production refactor by moving the speaking question-bank, P1/P2
corpus, and Takeaway subdomain out of `apps.speaking.services` while preserving
the existing API surface and user behavior.

## Scope

- Extract question-bank, corpus, translation, and Takeaway helpers into a
  cohesive module.
- Keep `apps.speaking.services` as the compatibility facade for views/tests.
- Keep runtime attempt flow, scoring, TTS, and report generation behavior
  unchanged.
- Do not stage unrelated dirty files such as `backend_django/db.sqlite3`.

## Acceptance Criteria

- [x] Corpus/question-bank/Takeaway logic lives outside `services.py`.
- [x] Existing imports from `apps.speaking.services` still work.
- [x] Speaking tests pass.
- [x] Django system check passes.
- [x] Migration dry-run reports no changes.
- [x] No retired legacy server dependency is introduced.
