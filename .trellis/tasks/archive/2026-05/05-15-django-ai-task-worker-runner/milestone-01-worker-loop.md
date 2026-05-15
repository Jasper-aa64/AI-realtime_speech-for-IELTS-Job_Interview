# Milestone 01: Django AI Worker Loop

## Goal

Make Django AI tasks process continuously without requiring a manual `run_ai_tasks`
command after every writing score submission.

## Scope

- Refactored the one-shot AI task batch execution into a reusable service module.
- Added a continuous Django management command for local/single-server worker
  execution.
- Preserved existing writing score billing, cancellation, fallback, and stale
  recovery contracts.
- Added tests for loop execution, idle loop output, stop-file shutdown, and
  stale recovery from the loop command.
- Documented the worker commands and updated backend quality specs.

## Changed Files

- `backend_django/apps/ai/worker.py`
- `backend_django/apps/ai/management/commands/run_ai_tasks.py`
- `backend_django/apps/ai/management/commands/run_ai_worker.py`
- `backend_django/apps/ai/tests.py`
- `backend_django/README.md`
- `.trellis/spec/backend/quality-guidelines.md`

## Design Decisions

- Keep `run_ai_tasks` backward-compatible as a one-shot JSON summary command.
- Put shared batch behavior in `apps.ai.worker.run_ai_task_batch(...)`, so later
  Celery/RQ integration can reuse the same lifecycle boundary.
- Add `run_ai_worker` as a management-command loop instead of introducing
  Redis/Celery in this milestone.
- Stop conditions are checked between batches only. Once a task is claimed as
  `running`, it must finish through the existing success/fallback/failure path
  so wallet reservations and user records stay coupled.
- `--max-loops` and zero sleep intervals make the loop deterministic in tests.
- `--stop-file` lets a process manager request graceful shutdown before the next
  batch.

## Validation Results

- `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py` passed.
- `node --check web/static/app.js` passed.
- `.venv-django/bin/python backend_django/manage.py check` passed.
- `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run` passed with no changes detected.
- `.venv-django/bin/python backend_django/manage.py test` passed: 79 tests.
- Targeted worker tests passed: 14 tests in `apps.ai.tests.AIWorkerCommandTests`.

## Known Issues

- This is still a single-process management-command worker, not a distributed
  queue. Process supervision, metrics, backpressure, and multi-worker tuning
  remain future work.
- Real AI provider SDK calls are still not connected; current default scoring
  path uses deterministic fallback unless an explicitly enabled mock success
  adapter is selected in tests/local config.
- Stop-file and signal handling stop the loop between batches only; they do not
  interrupt a claimed task mid-run by design.

## Rollback

- Remove `backend_django/apps/ai/worker.py`.
- Remove `backend_django/apps/ai/management/commands/run_ai_worker.py`.
- Restore `run_ai_tasks.py` to contain its previous inline batch logic.
- Remove the added worker-loop tests and README/spec additions.
- No database migration or destructive data change is involved.

## Next Stage

- Run the worker alongside the old frontend bridge during manual writing scoring
  verification.
- Add a lightweight local run recipe or process-manager script only after the
  command behavior is stable in daily use.
- Then move to the next data-backed migration slice: user/session/profile API,
  or start migrating writing report/history read APIs onto Django.
