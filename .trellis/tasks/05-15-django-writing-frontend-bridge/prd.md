# Django writing frontend bridge

## Goal

Move the existing vanilla Web "每日写作" flow toward the Django durable writing backend without breaking the old web server. The key behavior is that saved writing entries and AI scoring should become refresh-safe when the user is logged in to Django: scoring creates a durable `writing_score` AI task, the UI can poll/recover status after refresh, and completed/fallback results are appended to the user's writing record instead of being lost when the browser navigates away.

## What I Already Know

* The current old Web UI lives in `web/static/app.js`, `web/static/index.html`, and `web/static/styles.css`.
* The old web server still serves the app and has JSON-file writing endpoints under `/api/writing/*`.
* The old web server already has a Django proxy boundary:
  * account routes always proxy to Django;
  * writing routes proxy when `IELTS_DJANGO_PROXY_WRITE_FIRST=1` and the request has a Django `sessionid` cookie, or when `IELTS_DJANGO_FORCE_WRITING_PROXY=1`.
* The frontend still calls synchronous `POST /api/writing/entries/{id}/score` after save, so it does not use the durable Django `score-task` flow.
* Django writing endpoints already exist:
  * `GET /api/writing/summary`
  * `GET /api/writing/prompts`
  * `POST /api/writing/prompts/random`
  * `POST /api/writing/entries`
  * `GET /api/writing/entries/{entry_id}`
  * `POST /api/writing/entries/{entry_id}/score`
  * `POST /api/writing/entries/{entry_id}/score-task`
* Django AI task endpoints already exist:
  * `GET /api/ai/tasks/{task_id}`
  * `POST /api/ai/tasks/{task_id}/cancel/`
* Django worker boundary is `python backend_django/manage.py run_ai_tasks --limit N`.
* Product rule: once an AI task is `running`, user cancellation must fail with conflict and the worker must complete/fallback/fail and persist the result.
* Writing detail payload includes `ai_task`, `score`, `writing_profile`, `word_count`, `task_type`, `prompt_id`, and `entry_id`-compatible `id`.

## Assumptions

* The old web server remains the browser origin in this milestone.
* Logged-in Django users should use proxied Django writing data where possible.
* Logged-out or unavailable-Django sessions may continue using the old JSON writing fallback.
* This task does not introduce Vue or replace the old web server.
* This task does not connect a real provider, real SMS, WeChat, or payment credentials.
* Worker execution may be manual/local for now, but the frontend must not assume synchronous completion.

## Requirements

* Keep the existing writing UI layout and old speaking flows usable.
* Add frontend support for Django `score-task`:
  * save the entry first;
  * create/reuse a billable score task;
  * show a visible waiting state like the speaking analysis flow;
  * poll entry detail or task detail until terminal state or score appears;
  * switch to writing report after score/fallback is visible.
* Add refresh-safe recovery:
  * if an entry detail has `ai_task.status` of `pending` or `running`, show scoring-in-progress state;
  * poll again after reload/navigation instead of losing the result;
  * do not create a duplicate task for the same answer hash.
* Add user cancellation behavior only for pending tasks if exposed:
  * pending cancellation may call `/api/ai/tasks/{task_id}/cancel/`;
  * running cancellation must show the backend conflict and keep polling/recovery possible.
* Keep fallback behavior:
  * if the proxied Django writing API is unavailable and the old endpoint handles the request, the UI must still be usable;
  * synchronous old `/score` remains a fallback path, not the primary logged-in Django path.
* Make report rendering handle `pending`, `running`, `fallback`, `succeeded`, `failed`, and `cancelled` task states clearly.
* Keep the "写作报告" page visually aligned with the existing "口语报告" pattern: report tabs/rail above and full-width detail below.

## Acceptance Criteria

* [ ] Logged-in scoring uses `/api/writing/entries/{id}/score-task` and does not rely on synchronous `/score`.
* [ ] A visible scoring wait state appears while an AI task is pending/running.
* [ ] Refreshing or returning to the writing screen can recover an active score task from entry detail.
* [ ] A task that finishes with fallback/success renders a writing report with band, criteria, feedback markdown, profile, prompt, and answer.
* [ ] A pending-cancelled task leaves the entry saved but unscored and does not render fake AI output.
* [ ] Old writing fallback remains available when Django writing proxy is not active.
* [ ] `node --check web/static/app.js` passes.
* [ ] `python3 -m py_compile web/ielts_server.py tests/test_ielts_web_server.py` passes.
* [ ] Django checks/tests pass for affected apps.

## Definition of Done

* Tests added/updated for the frontend bridge and proxy behavior where practical.
* JS syntax check green.
* Python compile check green.
* Django `check`, migration dry-run, and tests green.
* A milestone note records files changed, bridge decisions, validation, known gaps, rollback, and next phase.

## Out of Scope

* No Vue migration.
* No real provider SDK integration.
* No real SMS, WeChat, or payment key integration.
* No C++ speech service changes.
* No destructive migration of old JSON writing reports.

## Technical Notes

* Applicable specs:
  * `.trellis/spec/backend/database-guidelines.md`
  * `.trellis/spec/backend/error-handling.md`
  * `.trellis/spec/backend/quality-guidelines.md`
  * `.trellis/spec/frontend/quality-guidelines.md`
  * `.trellis/spec/guides/cross-layer-thinking-guide.md`
* Data flow:
  * Browser UI -> old web origin `/api/writing/*`
  * old web server proxies logged-in writing requests to Django when `sessionid` is present
  * Django writing service saves entries and creates `AITask`
  * worker processes `AITask`
  * browser polls Django-proxied entry detail and renders persisted result
* Existing bridge contract is documented in `backend_django/README.md`, "Writing bridge flow for the later frontend handoff".
* Risk: current old server proxy only proxies `/api/writing/*`; frontend cancellation endpoint `/api/ai/tasks/{task_id}/cancel/` may need old-server proxy support if cancellation is implemented from the old origin.
