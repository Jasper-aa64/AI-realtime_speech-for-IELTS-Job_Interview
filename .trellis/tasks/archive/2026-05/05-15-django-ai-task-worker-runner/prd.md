# Django AI task worker runner

## Goal

Add a manageable Django AI worker runner so durable AI tasks created by the writing frontend bridge can be processed continuously without a human manually invoking `run_ai_tasks` after every submission. This is a production-direction stepping stone before introducing Celery/Redis: keep the current database-backed task lifecycle, add a safe loop command, and preserve all billing/cancellation/recovery contracts.

## What I Already Know

* `backend_django/apps/ai/management/commands/run_ai_tasks.py` currently processes one bounded batch and exits.
* The one-shot command already supports `--limit`, `--worker-id`, and `--recover-stale-seconds`.
* AI task state is durable in `apps.ai.models.AITask`.
* Worker state transitions must go through `claim_ai_task`, provider adapters, and billing-aware orchestration helpers.
* Running AI work is not user-cancellable. Pending tasks can be cancelled; running tasks must finish/fallback/fail and persist the result.
* Writing frontend now creates `writing_score` tasks and polls entry detail. Without a worker loop, tasks remain pending until someone runs `run_ai_tasks`.
* This milestone should not introduce Celery/RQ/Redis, real provider SDK keys, or a public worker API.

## Assumptions

* MVP target is local/single-server operation, but the design should be service-manager friendly.
* A Django management command is enough for the next stage because it can be run under a terminal, PyCharm run config, Docker command, systemd, or supervisor later.
* The loop should be testable without sleeping indefinitely, so it needs `--max-loops` and small interval controls.
* Worker loops should produce machine-readable summaries so logs can be inspected later.

## Requirements

* Refactor one-shot worker execution into a reusable backend function.
* Keep existing `run_ai_tasks` behavior and JSON summary compatible.
* Add a continuous worker command, tentatively `run_ai_worker`, with:
  * `--limit`
  * `--worker-id`
  * `--recover-stale-seconds`
  * `--interval-seconds`
  * `--idle-interval-seconds`
  * `--max-loops` for tests and controlled local runs
  * optional `--stop-file` for external graceful shutdown
* The continuous worker must:
  * run bounded batches;
  * recover stale tasks before claiming when configured;
  * sleep between loops;
  * stop cleanly on SIGINT/SIGTERM;
  * emit one JSON summary per loop;
  * never bypass AI task lifecycle/billing services.
* Tests must prove:
  * one-shot command still processes pending writing score tasks;
  * continuous command can process pending tasks with `--max-loops`;
  * idle loops do not fail;
  * stop-file stops the loop;
  * stale recovery still works from the loop command.

## Acceptance Criteria

* [ ] `run_ai_tasks` still returns the previous summary shape.
* [ ] `run_ai_worker --max-loops 1` can process a pending writing score task.
* [ ] `run_ai_worker --max-loops 1` emits a valid JSON loop summary even when no tasks exist.
* [ ] `run_ai_worker --stop-file <path>` exits gracefully when the file exists.
* [ ] Worker code is service-layer reusable and not duplicated across management commands.
* [ ] Existing Django AI/writing/billing tests still pass.
* [ ] Documentation explains how to run the worker locally and under a future process manager.

## Definition of Done

* Tests added/updated for the worker runner.
* Django `check`, migration dry-run, and tests pass.
* Old Web syntax/compile checks remain green.
* README and milestone note updated.
* No real provider, SMS, WeChat, payment, Redis, or Celery credentials are introduced.

## Technical Approach

* Create `backend_django/apps/ai/worker.py` with `run_ai_task_batch(...)`.
* Make `run_ai_tasks` a thin command wrapper around `run_ai_task_batch(...)`.
* Add `backend_django/apps/ai/management/commands/run_ai_worker.py` for the loop.
* Keep JSON summaries simple:
  * one-shot command prints the batch summary exactly as before;
  * loop command prints JSON lines with loop metadata plus the batch summary.
* Keep signal handling command-local. Task lifecycle logic remains in services/orchestration/provider adapters.

## Decision (ADR-lite)

**Context**: The frontend now creates durable AI scoring tasks. Users should not have to wait for manual worker execution, but introducing Redis/Celery now would expand infrastructure and deployment scope.

**Decision**: Add a Django management worker loop as the next step. It is not the final distributed queue, but it makes the current architecture operational, testable, and easy to replace later.

**Consequences**:

* Pros: small scope, no new infrastructure, easy local verification, keeps database-backed lifecycle contracts intact.
* Cons: not a distributed queue; concurrent worker tuning, backpressure, metrics, and process supervision remain future work.
* Migration path: `run_ai_task_batch(...)` can later be called from Celery/RQ workers or an ASGI background supervisor.

## Out of Scope

* No Celery/RQ/Redis integration.
* No C++ speech service changes.
* No real provider SDK integration.
* No frontend cancel button.
* No speaking API migration.
* No deployment files for systemd/Docker compose unless directly needed for docs.

## Technical Notes

* Applicable specs:
  * `.trellis/spec/backend/database-guidelines.md`
  * `.trellis/spec/backend/error-handling.md`
  * `.trellis/spec/backend/quality-guidelines.md`
  * `.trellis/spec/guides/cross-layer-thinking-guide.md`
* Key files inspected:
  * `backend_django/apps/ai/management/commands/run_ai_tasks.py`
  * `backend_django/apps/ai/services.py`
  * `backend_django/apps/ai/provider_adapters.py`
  * `backend_django/apps/ai/tests.py`
  * `backend_django/README.md`
