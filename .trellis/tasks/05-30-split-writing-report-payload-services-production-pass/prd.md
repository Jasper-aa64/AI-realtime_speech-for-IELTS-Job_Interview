# Split Writing Report Payload Services Production Pass

## Goal

Continue the production refactor by reducing `backend_django/apps/writing/services.py` without changing user-facing writing behavior. This pass extracts writing report/list/detail payload helpers into a cohesive module while keeping `apps.writing.services` as the compatibility facade for existing views, tests, worker callbacks, and imports.

## Background

The project is now Django/web-static first. The old server is retired, and the remaining architecture debt is mostly large facade files. `writing/services.py` has already had prompt-bank logic extracted into `prompt_services.py`, but it still mixes report payload shaping, calendar summary queries, entry CRUD, AI task creation, score normalization, persistence, and learner-profile updates.

This pass intentionally targets the lower-risk read/payload side before touching score execution or worker lifecycle logic.

## Scope

- Add a focused writing report/payload service module.
- Move cohesive read/payload helpers out of `writing/services.py`.
- Preserve old public function names through `services.py`.
- Preserve API response shape and behavior.
- Avoid frontend changes.
- Avoid database migrations.
- Avoid scoring prompt/provider behavior changes.

## In Scope Candidate Functions

- `month_bounds`
- `report_limit`
- `report_status`
- spelling cleanup helpers used only for payload shaping
- `paragraph_reviews_payload`
- `score_payload`
- `task_summary_payload`
- `profile_snapshot`
- `writing_score_task_payload`
- `entry_payload`
- `compact_entry_payload`
- `report_entry_payload`
- `latest_writing_tasks_for_entries`
- `writing_summary`
- `writing_reports`

The implementation may leave a candidate in `services.py` if moving it would create a circular import or pull scoring/persistence behavior into the report module.

## Out of Scope

- `save_entry`, `get_entry`, `clone_entry_for_revision`, `delete_entry`
- `create_score_task`
- score normalization/persistence/fallback functions
- learner profile mutation
- AI task worker callback functions
- old `web/ielts_server.py`
- `web/static/app.js`

## Compatibility Requirements

- Existing imports from `apps.writing.services` must keep working.
- Existing tests should not need rewrites for import paths.
- The new module must not import from `services.py`.
- `services.py` may import/re-export from the new module.
- Existing dirty files outside this task must not be staged.

## Acceptance Criteria

- `services.py` is smaller and has clearer orchestration responsibility.
- A new cohesive writing report/payload module exists.
- Writing API payloads remain unchanged.
- Writing tests pass.
- Full Django tests pass.
- Django system check and migration dry-run pass.
- Legacy retirement validator still passes.
- No unrelated dirty files are staged or committed.

## Validation Plan

- `python3 -m py_compile backend_django/apps/writing/services.py backend_django/apps/writing/<new_module>.py`
- `cd backend_django && python3 manage.py test apps.writing.tests -v 1`
- `cd backend_django && python3 manage.py test -v 1`
- `cd backend_django && python3 manage.py check`
- `cd backend_django && python3 manage.py makemigrations --check --dry-run`
- `python3 scripts/validate_legacy_server_retirement.py`
- `git diff --check`
