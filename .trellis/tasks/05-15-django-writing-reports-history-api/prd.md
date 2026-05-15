# Django writing reports history API

## Goal

Move the writing report list/read surface onto an explicit Django report API so
the old frontend no longer treats monthly writing summary data as the report
index. This keeps `每日写作` focused on calendar/check-in state and `写作报告`
focused on saved/scored writing records, while preserving refresh-safe AI task
polling.

## What I Already Know

* `POST /api/writing/entries/{entry_id}/score-task` now creates durable
  `writing_score` AI tasks.
* `run_ai_worker` can process queued writing score tasks continuously.
* `GET /api/writing/entries/{entry_id}` returns entry detail plus latest
  `ai_task`, `score`, answer, prompt, and writing profile.
* `GET /api/writing/summary` returns calendar state and also `recent_entries`.
* Old frontend `loadWritingReports()` currently calls `loadWritingSummary(false)`
  and then fetches details for `recent_entries`.
* This couples the report page to the monthly summary payload and only exposes
  the summary's recent-entry slice.

## Assumptions

* This stage should not migrate speaking reports or rebuild the frontend.
* This stage should not introduce pagination UI complexity beyond a bounded
  server-side `limit`.
* Writing reports should include both saved and scored entries, because saved
  entries count as writing history even without AI feedback.
* Existing entry detail and polling behavior should remain compatible.

## Requirements

* Add a dedicated authenticated API:
  * `GET /api/writing/reports`
  * optional query params:
    * `limit`, default `50`, max `100`;
    * `status=saved|scored`;
    * `task_type=task1_academic|task2`;
  * response shape:
    * `{"items": [<compact report item>], "count": N}`
* Report list items must be owner-scoped and ordered by newest activity first.
* Report list items must include enough metadata for the left report tabs
  without fetching details:
  * `id`, `practice_date`, `display_time`, `task_type`, `task_label`, `title`,
    `word_count`, `status`, `overall_band`, and latest `ai_task` summary when
    present.
* `GET /api/writing/entries/{entry_id}` remains the report detail API.
* Frontend `loadWritingReports()` should call `/api/writing/reports` instead of
  using `/api/writing/summary`.
* Frontend report rendering must still fetch detail for the selected reports so
  answer text, prompt, feedback markdown, grammar corrections, and profile
  state stay complete.
* Report polling must keep working when an entry has `ai_task.status=pending`
  or `running`.
* Calendar summary must keep its current behavior for `每日写作`.
* No real AI provider, payment, SMS, WeChat, Redis, Celery, or C++ changes.

## Acceptance Criteria

* [x] `GET /api/writing/reports` requires authentication.
* [x] `GET /api/writing/reports` returns only the authenticated user's writing
  entries.
* [x] `limit` is bounded and invalid limits fall back safely.
* [x] `status` and `task_type` filters work.
* [x] Report items include the latest related writing score `ai_task` state.
* [x] Frontend `写作报告` uses `/api/writing/reports`.
* [x] Existing summary/calendar behavior is unchanged.
* [x] Existing writing score polling and worker flow still pass tests.

## Definition of Done

* Backend tests added for report list auth, owner isolation, filters, limit, and
  `ai_task` list metadata.
* Frontend syntax check passes.
* Django check, migration dry-run, and tests pass.
* Old `web/ielts_server.py` py_compile check remains green.
* Milestone note documents scope, changed files, validation, rollback, and next
  stage.

## Out of Scope

* No new DB tables unless an index gap is discovered and justified.
* No pagination UI.
* No speaking report migration.
* No Vue migration.
* No real payment/provider integration.

## Technical Notes

* Candidate files:
  * `backend_django/apps/writing/services.py`
  * `backend_django/apps/writing/views.py`
  * `backend_django/apps/writing/tests.py`
  * `backend_django/config/urls.py`
  * `web/static/app.js`
  * `backend_django/README.md`
* Applicable specs:
  * `.trellis/spec/backend/database-guidelines.md`
  * `.trellis/spec/backend/error-handling.md`
  * `.trellis/spec/backend/quality-guidelines.md`
  * `.trellis/spec/frontend/component-guidelines.md`
  * `.trellis/spec/frontend/quality-guidelines.md`
  * `.trellis/spec/guides/cross-layer-thinking-guide.md`

## Technical Approach

* Add `writing_reports(user, payload/query)` service function that builds a
  bounded owner-scoped queryset with `select_related("prompt", "score")`.
* Reuse `compact_entry_payload(...)` for common tab fields, then add
  `ai_task=writing_score_task_payload(entry)` to each report item.
* Add `reports(request)` view and URL.
* Update frontend `loadWritingReports()` to call `/api/writing/reports` and pass
  `items` into existing detail rendering.
* Keep detail fetching in `renderWritingReports()` for complete report content.
