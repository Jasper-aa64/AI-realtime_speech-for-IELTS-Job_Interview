# Milestone 09 - Non-Cancellable Running AI Tasks

## Goal

Lock the user/API boundary for durable AI work: only `pending` AI tasks may be
cancelled. Once a worker has claimed a task and it is `running`, the cancel
path must reject the request, keep any billable reservation intact, and let the
worker finish and persist the result to the user record.

## Scope

Included:

* verify the current Django cancellation/orchestration code against the
  non-cancellable-running contract;
* add direct regression coverage that `cancel_owned_ai_task()` propagates the
  running-task conflict without releasing reservations;
* align README and backend spec docs with the anti-abuse/cost-integrity rule;
* update milestone documentation so Milestone 08 no longer implies that running
  tasks can be cancelled.

Excluded:

* no legacy `web/ielts_server.py` changes;
* no `web/static/*` changes;
* no new database migrations;
* no new provider integration beyond the existing fallback worker path.

## Files Changed

* `backend_django/apps/ai/tests.py`
* `backend_django/README.md`
* `.trellis/spec/backend/error-handling.md`
* `.trellis/spec/backend/database-guidelines.md`
* `.trellis/spec/backend/quality-guidelines.md`
* `.trellis/tasks/05-14-django-migration-architecture/milestone-08-ai-task-control-api.md`
* `.trellis/tasks/05-14-django-migration-architecture/milestone-09-non-cancellable-running-ai.md`

## Design Decisions

* `cancel_ai_task()` remains the single generic status transition and rejects
  any non-terminal, non-`pending` task with `AITaskConflictError`.
* `cancel_billable_ai_task()` and `cancel_owned_ai_task()` deliberately do not
  catch or downgrade that conflict. The view layer maps it to `409`, which
  keeps reservation release logic unreachable for claimed `running` work.
* Pending cancellation is still idempotent and safe: the task becomes
  `cancelled`, billable reservations release once, and late completion/fallback
  writers return without creating `WritingScore` or learner-profile rows.
* Post-claim cancel attempts are not treated as a worker skip case. The worker
  must continue through fallback/completion, persist the result, and only then
  release or settle billing through the normal terminal path.

## Verification

Validated on 2026-05-15:

* `python3 -m py_compile backend_django/manage.py $(find backend_django/apps -maxdepth 4 -name '*.py' -print)`
  * Result: passed
* `.venv-django/bin/python backend_django/manage.py check`
  * Result: `System check identified no issues (0 silenced).`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
  * Result: `No changes detected`
* `.venv-django/bin/python backend_django/manage.py test apps.ai apps.writing -v 1`
  * Result: `Ran 47 tests ... OK`
* `.venv-django/bin/python backend_django/manage.py test -v 1`
  * Result: `Ran 66 tests ... OK`

## Known Gaps

* `run_ai_tasks` still executes only the fallback `writing_score` adapter; the
  real provider success path is covered by service tests, not an end-to-end
  worker/provider integration.
* Re-submitting the same unchanged writing answer after a cancelled task still
  hits the existing idempotency key and returns the cancelled task. Restart
  semantics for unchanged answers remain a future product decision.
* Status updates are still poll-based; there is no push channel for task state.

## Rollback

This milestone does not change schema or public route shape. Rolling back means
reverting the regression test and documentation updates if the product decides
to reopen running-task cancellation in the future.

## Next Milestone

Add a real async provider execution path for `writing_score` so the
non-cancellable-running contract is exercised end-to-end with successful worker
completion, billing settlement, and persisted score/profile output.
