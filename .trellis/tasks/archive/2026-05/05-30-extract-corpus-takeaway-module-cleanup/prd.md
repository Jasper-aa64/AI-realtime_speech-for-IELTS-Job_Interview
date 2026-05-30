# Extract Corpus Takeaway Module Cleanup

## Goal

Finish and commit the already-started `app.js` module extraction for corpus and Takeaway features without changing user-facing behavior.

## What I Already Know

- Current worktree contains a half-finished corpus/Takeaway extraction:
  - `web/static/corpus-takeaway.js`
  - `web/static/app.js` facade/controller wiring
  - `web/static/index.html` script include and cache bump
  - `backend_django/apps/common/views.py` MIME registration
  - `backend_django/config/urls.py` static route
- The worktree also contains unrelated WIP:
  - examiner audio playback stability changes in `web/static/app.js`
  - P1 corpus backend behavior changes in `backend_django/apps/speaking/corpus_services.py` and tests
  - local `db.sqlite3`
- This task must not mix those unrelated changes into the corpus/takeaway module commit.

## Requirements

- Keep behavior unchanged for:
  - corpus navigation
  - P1/P2 corpus editing
  - language Takeaway popup
  - Takeaway cards and hide/reveal behavior
  - writing Takeaway list
- Keep `app.js` facade functions so existing event handlers continue to resolve the same names.
- Serve `/corpus-takeaway.js` through Django static asset routing.
- Do not stage unrelated audio stability WIP, backend corpus behavior WIP, or `db.sqlite3`.

## Acceptance Criteria

- [x] `web/static/corpus-takeaway.js` syntax checks.
- [x] `web/static/app.js` syntax checks.
- [x] Django `manage.py check` passes.
- [x] `/corpus-takeaway.js` returns `200` and JavaScript content type when the local server is running.
- [x] Corpus/Takeaway app.js extraction is committed as `refactor: extract corpus & takeaway module`.
- [x] `app.js` line count is reported after commit.

## Out of Scope

- Fixing examiner audio playback stability.
- Changing corpus matching behavior.
- Phase 1 streaming latency measurement.
- Phase 2 realtime ASR.
