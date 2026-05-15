# Milestone 10 - Provider Runner Adapter + Result Persistence Contract

## Goal

Replace the hard-coded fallback-only local worker branch with a small provider
runner boundary that can choose a deterministic adapter per claimed task and
then settle the result through the existing writing/billing lifecycle helpers.

## Scope

Included:

* add a dependency-free provider runner/adapter module under
  `backend_django/apps/ai/`;
* route claimed `run_ai_tasks` work through adapter selection plus a result
  application step instead of directly calling `fallback_score_task(...)`;
* preserve the Milestone 09 post-claim non-cancellable boundary;
* add a deterministic `mock_success` writing adapter alongside the existing
  fallback path;
* document the contract in the task note, backend README, and backend specs.

Excluded:

* no real provider SDKs or credentials;
* no Celery/Redis/background queue integration;
* no legacy `web/ielts_server.py` or `web/static/*` edits;
* no schema changes or new migrations.

## Files Changed

* `backend_django/apps/ai/provider_adapters.py`
* `backend_django/apps/ai/management/commands/run_ai_tasks.py`
* `backend_django/apps/ai/tests.py`
* `backend_django/apps/writing/services.py`
* `backend_django/apps/writing/tests.py`
* `backend_django/README.md`
* `.trellis/spec/backend/database-guidelines.md`
* `.trellis/spec/backend/error-handling.md`
* `.trellis/spec/backend/quality-guidelines.md`
* `.trellis/tasks/05-14-django-migration-architecture/milestone-10-provider-runner-adapter.md`

## Design Decisions

* The new worker boundary is split into two explicit steps:
  * `run_claimed_ai_task(task)` selects and runs an adapter based on durable
    task fields.
  * `apply_provider_run_result(task, result)` maps the adapter outcome onto the
    existing writing and billing lifecycle helpers.
* `ProviderRunResult` supports five outcomes:
  * `success`
  * `fallback`
  * `retryable_failure`
  * `terminal_failure`
  * `skipped`
* Adapter selection is intentionally simple and deterministic:
  * `writing_score` + `provider=mock_success` -> mock success adapter
  * other `writing_score` tasks -> explicit fallback adapter
  * all other task types -> unsupported adapter result
* Successful writing results still go only through
  `apps.writing.services.complete_score_task(...)`, so `WritingScore`,
  `WritingLearnerProfile`, wallet settlement, and usage linking stay in one
  place.
* Fallback writing results still go only through
  `apps.writing.services.fallback_score_task(...)`, so default score
  persistence and reservation release stay in one place.
* Failure summaries must reflect the task status after the lifecycle helper
  runs: retryable provider failures report `pending`, terminal provider
  failures report `failed`, and unsupported task types still use the special
  batch summary status `skipped`.
* Unsupported claimed tasks are reported as `skipped` in the worker summary for
  batch readability, but the claimed row is terminal-failed in the database
  with `error_code=unsupported_task_type`. This keeps the old surface-level
  worker summary behavior while preventing orphaned `running` rows.
* `create_score_task(...)` now accepts optional `provider` / `model` hints so
  local test flows can intentionally select `mock_success`.

## Verification

Validated on 2026-05-15:

* `python3 -m py_compile backend_django/manage.py $(find backend_django/apps -maxdepth 4 -name '*.py' -print)`
  * Result: passed
* `.venv-django/bin/python backend_django/manage.py check`
  * Result: `System check identified no issues (0 silenced).`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
  * Result: `No changes detected`
* `.venv-django/bin/python backend_django/manage.py test apps.ai apps.writing -v 1`
  * Result: `Ran 52 tests ... OK`
* `.venv-django/bin/python backend_django/manage.py test -v 1`
  * Result: `Ran 68 tests ... OK`

## Known Gaps

* `mock_success` is deterministic local scaffolding, not a real provider
  client. It exists to exercise the success settlement path without external
  credentials.
* Provider routing is still hard-coded to `writing_score`; other task types do
  not have success/fallback adapters yet.
* Usage capture still uses the existing billing service defaults for provider
  event metadata; this milestone only guarantees usage payload persistence and
  settlement idempotency.
* There is still no external worker queue or live progress channel.

## Rollback

This milestone does not change schema or public route shape. Rollback means
reverting the new adapter module, restoring the old direct fallback call in
`run_ai_tasks`, and removing the associated tests/docs if the project decides
to defer provider-runner abstraction.

## Next Milestone

Introduce the first real provider-backed adapter for `writing_score`, including
provider/model metadata propagation into captured usage records and explicit
retry vs terminal failure behavior from real provider responses.
