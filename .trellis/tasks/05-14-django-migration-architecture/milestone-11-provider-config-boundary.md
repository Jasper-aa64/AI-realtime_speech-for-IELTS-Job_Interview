# Milestone 11 - Provider Config Boundary

## Goal

Add a safe provider-configuration boundary for Django AI task execution so
future real OpenAI/Codex/Claude adapters can be wired predictably, while
current local runs stay deterministic, fallback-first, and secret-safe.

## Scope

Included:

* add `apps.ai.provider_config` for safe provider-mode flags, default-provider
  resolution, future provider enable switches, and placeholder secret env-var
  names;
* route durable provider selection through that config helper instead of ad hoc
  string checks in the worker adapter path;
* keep `writing_score` default behavior fallback-only unless
  `AI_ALLOW_MOCK_SUCCESS` explicitly enables the deterministic mock-success
  adapter;
* make unknown or disabled writing providers fall back safely without usage
  settlement surprises;
* document the contract in backend README and backend spec notes.

Excluded:

* no real provider SDK, HTTP client, or secret loading;
* no legacy `web/ielts_server.py` or `web/static/*` edits;
* no schema changes or migrations;
* no billing usage provider/model propagation changes yet.

## Files Changed

* `backend_django/config/settings.py`
* `backend_django/apps/ai/provider_config.py`
* `backend_django/apps/ai/provider_adapters.py`
* `backend_django/apps/ai/services.py`
* `backend_django/apps/ai/orchestration.py`
* `backend_django/apps/ai/views.py`
* `backend_django/apps/ai/tests.py`
* `backend_django/apps/writing/services.py`
* `backend_django/README.md`
* `.trellis/spec/backend/database-guidelines.md`
* `.trellis/spec/backend/error-handling.md`
* `.trellis/spec/backend/quality-guidelines.md`
* `.trellis/spec/backend/logging-guidelines.md`
* `.trellis/tasks/05-14-django-migration-architecture/milestone-11-provider-config-boundary.md`

## Design Decisions

* `provider_config.py` is the single boundary for provider-mode policy:
  * `AI_PROVIDER_MODE` defaults to `local_safe`;
  * `AI_DEFAULT_PROVIDER` supplies the durable default provider string stored on
    newly created tasks;
  * `AI_ALLOW_MOCK_SUCCESS` is the explicit gate for the deterministic
    `mock_success` success path;
  * `AI_PROVIDER_ENABLE_*` flags describe future real-provider intent without
    requiring a live adapter today.
* Secret handling is name-only:
  * settings keep placeholder env-var names like `OPENAI_API_KEY`;
  * the worker never reads or persists actual secret values;
  * fallback reasons and worker summaries stay free of secret env contents.
* `writing_score` provider routing is hardened but still safe:
  * no provider or normal default provider -> explicit fallback adapter;
  * `provider=mock_success` + gate enabled -> deterministic success adapter;
  * `provider=mock_success` + gate disabled -> safe fallback, no settlement;
  * unknown or disabled writing providers -> safe fallback, no crash.
* Unsupported task types keep the Milestone 10 behavior:
  * batch summary item `status=skipped`;
  * durable task row terminal-failed with `error_code=unsupported_task_type`;
  * any reservation is released through the normal orchestration helper.
* Milestone 09 remains intact: once a task is `running`, user cancellation is
  still rejected and the worker finishes through the normal terminal path.

## Verification

Validated on 2026-05-15:

* `python3 -m py_compile backend_django/manage.py $(find backend_django/apps -maxdepth 4 -name '*.py' -print)`
  * Result: passed
* `.venv-django/bin/python backend_django/manage.py check`
  * Result: `System check identified no issues (0 silenced).`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run`
  * Result: `No changes detected`
* `.venv-django/bin/python backend_django/manage.py test apps.ai apps.writing -v 1`
  * Result: `Ran 55 tests ... OK`
* `.venv-django/bin/python backend_django/manage.py test -v 1`
  * Result: `Ran 74 tests ... OK`

## Known Gaps

* Real provider metadata still does not flow into `CodexUsageEvent`; billing
  settlement keeps the existing default capture metadata until a real adapter
  milestone lands.
* `AI_PROVIDER_ENABLE_*` flags currently shape safe routing decisions only.
  They do not activate a live provider client.
* The worker summary still reports only task-level status, not provider-route
  diagnostics. That keeps the surface small and secret-safe for now.

## Rollback

Rollback is code-only: remove `provider_config.py`, restore the previous direct
provider string checks, and revert the accompanying README/spec/test updates.
No schema or data migration rollback is required.

## Next Milestone

Add the first real provider-backed `writing_score` adapter behind this config
boundary, including provider/model metadata propagation into usage capture and
explicit retry-vs-terminal mapping for real provider responses.
