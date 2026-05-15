# Django Migration Architecture Decisions

## Goal

Record the first-round architecture decisions for moving the IELTS app from the current standard-library Python web server and vanilla frontend toward a production-ready Django backend, while keeping the current app usable.

## Sources Consulted

* Django docs via Context7: custom user model must be configured with `AUTH_USER_MODEL` before migrations when starting a project.
* Celery docs via Context7: Redis can be used as a Celery result backend and Celery supports task retry semantics.
* Django Channels docs via Context7: ASGI plus Channels can route HTTP and WebSocket traffic, with Redis as the production channel layer.
* Local code inspection:
  * `web/ielts_server.py` currently owns legacy JSON reports, writing practice, wallet logic, and AI scoring flow.
  * `backend_django/` already contains accounts, speaking, writing, billing, ai, and common Django apps.
  * Existing C++ code has reusable protocol and realtime client pieces, but the current audio manager is local-device oriented and should not be treated as the online multi-user recording layer.

## Decisions

### 1. Django owns business state

Django is the system of record for:

* users and profiles;
* speaking attempts, turns, reports, and learner observations;
* writing prompts, entries, scores, and learner profiles;
* wallets, ledger entries, reservations, usage events, price snapshots, and payment orders;
* AI task state, provider calls, fallback state, and retry/error metadata.

Rationale: these are user-owned business records, need database indexes, permissions, admin visibility, and transaction boundaries.

### 2. Redis/Celery owns recoverable background execution

Long-running AI scoring, report generation, ASR cleanup, personalized feedback generation, and billing settlement should move behind persistent task records and a worker queue.

The Django database should keep durable `AITask` state. Redis/Celery should provide execution and retry. UI refresh must not lose report generation progress because the task state lives in the database.

### 3. Channels is reserved for live status and future realtime flows

Plain HTTP polling is enough for early score/report status. Django Channels should be introduced when live transcript/status updates, WebSocket progress, or realtime speaking sessions need first-class support.

Channels should not be added merely to make normal CRUD endpoints look modern.

### 4. C++ is not the product backend

C++ should not own:

* accounts, permissions, sessions, or user profile state;
* billing, wallet reservations, payment orders, or ledger entries;
* report persistence, writing history, speaking history, or admin workflows;
* frontend route state or browser microphone permissions.

C++ is valuable later as a speech processing service:

* audio packet normalization and buffering;
* VAD / endpoint detection;
* realtime ASR/TTS protocol adaptation;
* low-latency session event emission;
* CPU-heavy speech preprocessing.

Browser recording remains the online product's microphone entry point. Server-side C++ processes uploaded or streamed audio; it does not record a remote user's microphone directly.

### 5. Frontend migration is delayed behind API stability

The long-term frontend direction is Vue 3 + Vite, but the current vanilla frontend should remain untouched unless a milestone explicitly bridges it to Django APIs. Backend data ownership and long-task reliability come first.

## Risks

* Adding Celery too early can hide model/API defects behind worker complexity.
* Keeping old JSON reports and new Django rows in parallel can create inconsistent histories unless the bridge is explicit.
* C++ realtime service can become a second backend if it starts owning business state; this must be avoided.
* Existing dirty worktree contains many unrelated changes, so each milestone must document changed files and avoid reverting user work.

## Recommended First Implementation Target

Stabilize the existing `backend_django/` scaffold:

* ensure dependencies install in `.venv-django`;
* run `manage.py check`, `makemigrations --check --dry-run`, and `manage.py test`;
* fix model/migration/test defects;
* document current model/API coverage and next gap.
