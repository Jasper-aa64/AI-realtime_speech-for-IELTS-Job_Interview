# Split writing service boundaries production pass

## Goal

Continue the production refactor by reducing `backend_django/apps/writing/services.py`
without changing the writing API contract or frontend behavior.

## Scope

- Extract writing prompt catalog/search/sync behavior into a cohesive module.
- Keep `apps.writing.services` as a compatibility facade for existing imports.
- Do not change database schema, prompt JSON data, scoring behavior, or frontend UI.
- Do not stage unrelated dirty files such as `backend_django/db.sqlite3`.

## Acceptance Criteria

- [x] Prompt catalog/search helpers live outside `services.py`.
- [x] Existing imports from `apps.writing.services` still work.
- [x] Django writing tests pass.
- [x] Django system check passes.
- [x] Migration dry-run reports no changes.
- [x] No legacy server runtime dependency is introduced.
