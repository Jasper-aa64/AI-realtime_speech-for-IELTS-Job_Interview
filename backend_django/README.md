# IELTS Django Backend

This directory contains the first Django migration milestone. It is a scaffold
and data-model layer only; it does not replace the current `web/` app yet.

## Owner

```text
name: TBD
email: TBD
```

## Local Setup

From the repository root:

```bash
python3 -m venv .venv-django
. .venv-django/bin/activate
pip install -r requirements/local.txt
python backend_django/manage.py check
python backend_django/manage.py migrate
python backend_django/manage.py import_legacy_data --reports-dir reports --dry-run
python backend_django/manage.py import_legacy_data --reports-dir reports
python backend_django/manage.py test
python backend_django/manage.py run_ai_tasks --limit 10
python backend_django/manage.py runserver 127.0.0.1:8767
```

Optional local AI worker flags:

```bash
AI_PROVIDER_MODE=local_safe
AI_DEFAULT_PROVIDER=codex
AI_ALLOW_MOCK_SUCCESS=0
AI_PROVIDER_ENABLE_CODEX=1
AI_PROVIDER_ENABLE_OPENAI=0
AI_PROVIDER_ENABLE_CLAUDE=0
```

No-secret rule:

- Do not store provider API keys in task payloads, milestone docs, logs, or test
  fixtures.
- The Django config keeps only placeholder secret env-var names such as
  `CODEX_API_KEY`, `OPENAI_API_KEY`, and `ANTHROPIC_API_KEY`.
- Leave those unset for current local runs; this milestone does not integrate a
  real SDK or require live credentials.

Health check:

```bash
curl http://127.0.0.1:8767/api/health/
```

## MVP API Surface

Accounts:

```text
POST /api/accounts/register/
POST /api/accounts/login/
POST /api/accounts/logout/
GET  /api/accounts/me/
PATCH /api/accounts/me/
```

AI tasks:

```text
POST /api/ai/tasks/
GET  /api/ai/tasks/{task_id}
POST /api/ai/tasks/{task_id}/cancel/
```

AI task records are the durable state boundary for slow report/scoring work.
Workers can be added later; callers should create tasks with an idempotency key,
then poll the task detail endpoint after refresh or reconnect. Clients can
cancel only their own pending tasks through the generic cancel endpoint.
Once a task is `running`, the cancel route returns `409` and the worker must
finish through the normal success/fallback/failure path so billing and result
persistence stay consistent. This is an anti-abuse and cost-integrity
boundary: once billable or provider work has started, the system must keep the
task and reservation coupled until the final result is written back to the
user-owned record. Wrong-owner and missing task IDs resolve as not found.

When `POST /api/ai/tasks/` includes `reserved_u`, the API creates a billable
task and reserves wallet balance up front. Later orchestration should settle
the reservation on success or release it on fallback, pending-task
cancellation, or final worker-lease failure.

Billing:

```text
GET  /api/billing/wallet/
POST /api/billing/recharge/
POST /api/billing/reservations/
POST /api/billing/reservations/release/
POST /api/billing/settle/
```

The billing service keeps the existing internal money unit: integer micro RMB.
It supports initial local grants, manual recharge, usage reservation, release,
usage capture, charge calculation, and idempotent settlement.

Writing:

```text
GET  /api/writing/summary
GET  /api/writing/prompts
POST /api/writing/prompts/random
POST /api/writing/entries
GET  /api/writing/entries/{entry_id}
POST /api/writing/entries/{entry_id}/score
POST /api/writing/entries/{entry_id}/score-task
```

`/score` keeps the current synchronous fallback-compatible behavior.
`/score-task` creates a refresh-safe billable AI task for later worker
execution and returns the same task on duplicate submits for the same answer.
It also accepts optional `provider` / `model` hints for local worker routing;
`provider=mock_success` selects a deterministic success adapter only when
`AI_ALLOW_MOCK_SUCCESS=1`. Otherwise it falls back safely and releases the
reservation like any other local fallback path. The default requested provider
comes from `AI_DEFAULT_PROVIDER` and still routes to the explicit fallback
adapter until a real provider integration is wired.
`GET /api/writing/entries/{entry_id}` includes the latest `ai_task` payload for
that entry, so the UI can recover task state after refresh and keep showing a
cancelled task without creating a `WritingScore`. If a task was cancelled while
still `pending`, late completion or fallback callbacks are ignored and do not
create score/profile rows.

Writing bridge flow for the later frontend handoff:

1. `GET /api/writing/prompts` or `POST /api/writing/prompts/random` to choose a prompt.
2. `POST /api/writing/entries` to save the current draft and receive the durable `entry.id`, `prompt_id`, `task_type`, and `word_count`.
3. `POST /api/writing/entries/{entry_id}/score-task` to create or reuse the billable `writing_score` task for the current answer hash.
4. `GET /api/writing/entries/{entry_id}` to poll the bridge payload after refresh; it always returns the entry plus the latest related `ai_task`.
5. `POST /api/ai/tasks/{task_id}/cancel/` only while the task is still `pending`; cancelled-pending entries keep `score=null` on the detail payload.
6. `python backend_django/manage.py run_ai_tasks --limit N` claims the task, runs the provider adapter, and writes the terminal state.
7. `GET /api/writing/entries/{entry_id}` is the final read surface:
   - `ai_task.status=pending` or `cancelled` while no score exists yet;
   - `ai_task.status=fallback` with `score.backend=fallback` after local fallback scoring;
   - `ai_task.status=succeeded` with `score.backend=ai` after successful usage settlement.

Local worker boundary:

```text
python backend_django/manage.py run_ai_tasks --limit 10
python backend_django/manage.py run_ai_tasks --limit 10 --recover-stale-seconds 900
```

This command now runs claimed tasks through a small provider adapter boundary:

- `writing_score` with `provider=mock_success` uses a deterministic mock
  success adapter only when `AI_ALLOW_MOCK_SUCCESS=1`; otherwise it safely
  falls back through `fallback_score_task`.
- All normal `writing_score` requests still use the explicit fallback adapter
  and release the reservation through `fallback_score_task`.
- Unknown or disabled writing providers also fall back deterministically; they
  do not crash the batch or settle usage unexpectedly.
- Successful billable runs stamp `CodexUsageEvent` with durable provider/model
  columns plus audit metadata such as `task_id`, `task_type`, `prompt_version`,
  `related_id`, and writing prompt/entry identifiers when available.
- Unsupported claimed task types are reported as `skipped` in the batch summary
  but are terminal-failed in the database so they do not remain stuck in
  `running`; billable unsupported tasks release their reservation through the
  normal orchestration helper.

`--recover-stale-seconds` first requeues or terminal-fails stale `running`
tasks before claiming pending work, so a dead local worker does not leave
wallet reservations stranded. Once a worker claims a task, user cancellation
must not interrupt it; the command should finish and persist the fallback or
result normally, including writing the `WritingScore` and learner profile
update for the completed path. Pending billable cancellation, fallback,
unsupported terminal failure, and stale terminal recovery all release
reservations idempotently through the same service/orchestration path.

## Production Database Direction

Local development defaults to SQLite. Production should set:

```bash
DJANGO_DB_ENGINE=django.db.backends.mysql
DJANGO_DB_NAME=...
DJANGO_DB_USER=...
DJANGO_DB_PASSWORD=...
DJANGO_DB_HOST=...
DJANGO_DB_PORT=3306
```

## Migration Boundary

The existing web app remains under `web/` and still owns current product flows.
This Django project currently defines:

- account and profile models
- speaking attempt/report models
- speaking weak-item training observations
- writing prompt/entry/score models
- writing learner profile model
- billing wallet/ledger/usage/payment-order models
- legacy billing user import model
- AI task/fallback state model
- `/api/health/`

## Legacy Data Import

Database-bearing legacy data should be imported before API cutover:

```bash
python backend_django/manage.py import_legacy_data --reports-dir reports --dry-run
python backend_django/manage.py import_legacy_data --reports-dir reports
```

The command imports:

- `reports/billing/billing.sqlite3`
- `reports/training/training.sqlite3`
- `reports/attempts/*.json`
- `reports/writing/*.json`
- `reports/writing_profiles/*.json`
- `reports/billing/codex_jsonl/*.jsonl` as AI task metadata

Business API migration, real payment integration, queue workers, and Vue
migration are intentionally outside this milestone.
