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
`GET /api/writing/entries/{entry_id}` includes the latest `ai_task` payload for
that entry, so the UI can recover task state after refresh and keep showing a
cancelled task without creating a `WritingScore`. If a task was cancelled while
still `pending`, late completion or fallback callbacks are ignored and do not
create score/profile rows.

Local worker boundary:

```text
python backend_django/manage.py run_ai_tasks --limit 10
python backend_django/manage.py run_ai_tasks --limit 10 --recover-stale-seconds 900
```

This command currently processes pending `writing_score` tasks with an explicit
fallback adapter. `--recover-stale-seconds` first requeues or terminal-fails
stale `running` tasks before claiming pending work, so a dead local worker does
not leave wallet reservations stranded. Once a worker claims a task, user
cancellation must not interrupt it; the command should finish and persist the
fallback/result normally, including writing the `WritingScore` and learner
profile update for the completed path. Pending billable cancellation and stale
terminal recovery both release reservations idempotently through the same
service/orchestration path.

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
