# Milestone 07 - Worker Lease Recovery and Cancellation

## Goal

Make Django AI tasks recoverable when a worker dies mid-run, and add an
explicit cancellation path for billable tasks so reserved wallet balance is not
left hanging.

## Scope

Included:

* add a terminal `cancelled` AI task status;
* recover stale `running` tasks whose lease age exceeds a caller-provided timeout;
* requeue stale tasks when attempts remain, or fail them when the retry budget is exhausted;
* release billable wallet reservations on cancellation and on terminal stale recovery;
* let `run_ai_tasks` optionally recover stale tasks before claiming pending work;
* add regression tests for stale recovery, cancellation safety, and worker recovery flow.

Excluded:

* no public cancel endpoint yet;
* no Celery/Redis worker integration yet;
* no live status push channel;
* no changes to legacy `web/` runtime behavior.

## Files Changed

* `backend_django/apps/ai/models.py`
* `backend_django/apps/ai/services.py`
* `backend_django/apps/ai/orchestration.py`
* `backend_django/apps/ai/management/commands/run_ai_tasks.py`
* `backend_django/apps/ai/tests.py`
* `backend_django/apps/ai/migrations/0003_aitask_cancelled_status.py`
* `backend_django/README.md`
* `.trellis/tasks/05-14-django-migration-architecture/milestone-07-worker-recovery-cancellation.md`

## Design Decisions

* `services.py` owns generic task-status transitions, including stale-running recovery and cancellation.
* `orchestration.py` remains the billing-aware layer and is the only place that releases wallet reservations for task lifecycle events.
* A dedicated `cancelled` status is clearer than overloading `failed`, because user intent and worker failure are different terminal outcomes.
* Worker lease recovery uses a timeout supplied by the caller rather than a hard-coded global constant, so local commands and later schedulers can tune it independently.
* Recovery requeues immediately by default, which lets a single `run_ai_tasks` invocation reclaim stale work and continue processing it in the same pass.
* `trellis-check` found and fixed a late callback billing bug: `succeed_billable_ai_task()` now returns unchanged for terminal tasks before settlement, so a cancelled, fallback, failed, or succeeded billable task cannot be charged by a late worker success callback.

## Verification Run

* `python3 -m py_compile ...` for changed Python files
  * Result: passed for `backend_django/manage.py`, `apps/ai/models.py`, `apps/ai/services.py`, `apps/ai/orchestration.py`, `apps/ai/management/commands/run_ai_tasks.py`, `apps/ai/tests.py`, and `apps/ai/migrations/0003_aitask_cancelled_status.py`
* `.venv-django/bin/python backend_django/manage.py test apps.ai -v 1`
  * Result: `Ran 53 tests ... OK`, including `test_cancelled_billable_task_ignores_late_success_callback`
* `.venv-django/bin/python backend_django/manage.py check`
  * Result: `System check identified no issues (0 silenced).`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
  * Result: `No changes detected`

## Known Gaps

* Cancellation is service-only for now; there is no authenticated HTTP endpoint yet.
* `run_ai_tasks` still only executes the fallback `writing_score` adapter.
* No background scheduler exists yet to invoke stale recovery automatically.
* There is still no real provider execution path, only fallback and completion hooks.

## Rollback / Compatibility Notes

The milestone is additive to the Django scaffold. Legacy `web/ielts_server.py`
and `web/static/*` remain untouched. Rolling back this milestone means removing
the new `cancelled` status migration and the recovery/cancellation helpers
before any dependent API or worker integrations are built on top.

## Next Recommended Milestone

Milestone 08 should expose authenticated task control and status coordination:

* add a task cancellation endpoint and ownership checks;
* decide whether the first polling bridge should stay on HTTP or move to Celery-backed execution;
* add periodic stale recovery so the local worker command is no longer the only recovery trigger.
