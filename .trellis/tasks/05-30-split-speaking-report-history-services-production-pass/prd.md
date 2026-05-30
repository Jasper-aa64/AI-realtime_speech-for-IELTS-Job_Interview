# Split Speaking Report History Services Production Pass

## Goal

Continue the production refactor by reducing `backend_django/apps/speaking/services.py` without changing product behavior. This pass extracts speaking history/report/training-read helpers into a cohesive service module while keeping `services.py` as the compatibility facade for existing views, tests, and imports.

## Background

The old web server is retired and Django is the only production runtime. The remaining architecture debt is mostly large facade files. `speaking/services.py` is still too large after the corpus extraction, so the next low-risk split is report/history read behavior rather than runtime/TTS behavior.

## Scope

- Add a focused module for speaking report/history/training read services.
- Move cohesive, lower-risk functions out of `speaking/services.py`.
- Preserve old public import names through `services.py`.
- Do not change API payload shape, UI behavior, scoring behavior, Codex behavior, TTS behavior, or runtime attempt state transitions.
- Update local documentation if the module boundary changes.

## In Scope Candidate Functions

- report validity / report payload helpers
- history list/detail/delete helpers when safe
- training weak-items/replay-queue read helpers when safe
- task summary payload helpers when safe

## Out of Scope

- TTS generation and background TTS threads
- attempt start/audio/complete/score runtime orchestration
- Codex/AI prompt or provider behavior
- frontend UI changes
- database migrations
- old `web/ielts_server.py`

## Acceptance Criteria

- `services.py` is smaller and acts more clearly as a facade.
- New module has cohesive imports and no circular import with `services.py`.
- Existing speaking API/tests keep passing without test rewrites.
- Full Django tests keep passing.
- Legacy retirement validator still passes.
- No unrelated dirty files are staged.

## Validation Plan

- `python3 -m py_compile backend_django/apps/speaking/services.py backend_django/apps/speaking/<new_module>.py`
- `cd backend_django && python3 manage.py test apps.speaking.tests -v 1`
- `cd backend_django && python3 manage.py test -v 1`
- `cd backend_django && python3 manage.py check`
- `cd backend_django && python3 manage.py makemigrations --check --dry-run`
- `python3 scripts/validate_legacy_server_retirement.py`
- `git diff --check`
