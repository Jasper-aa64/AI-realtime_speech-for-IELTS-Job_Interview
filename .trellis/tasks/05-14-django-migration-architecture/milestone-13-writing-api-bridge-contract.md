# Milestone 13 - Writing API Bridge Contract

## Goal

Lock the Django writing entry detail payload into an explicit bridge contract
for the later frontend handoff so refresh-safe polling, cancellation, fallback,
and success states all expose the same stable identifiers.

## Scope

Included:

* formalize the expected `GET /api/writing/entries/{entry_id}` detail payload
  through integration tests;
* cover pending, cancelled-pending, fallback, and succeeded score-task states;
* document the bridge flow in backend README and backend spec guidance.

Excluded:

* no legacy frontend migration in this milestone;
* no route shape changes to the writing API;
* no serializer/framework refactor for the existing dict-based response layer;
* no new billing or provider behavior beyond what the current task lifecycle
  already returns.

## Files Changed

* `backend_django/apps/writing/tests.py`
* `backend_django/README.md`
* `.trellis/spec/backend/quality-guidelines.md`

## Design Decisions

* The existing entry detail response remains the bridge surface. Instead of
  introducing a second status endpoint, the frontend can reload a single entry
  resource and always receive the latest related `ai_task` plus any score.
* Contract assertions are centralized in the test helper
  `assert_entry_detail_contract(...)` so all lifecycle states must keep the
  same core identifiers:
  * top-level `id`
  * top-level `prompt_id`
  * top-level `task_type`
  * top-level `word_count`
  * top-level `score`
  * top-level `ai_task`
* `ai_task.request_payload` must retain `entry_id`, `prompt_id`, and writing
  `task_type`. The client should not need to infer these identifiers from other
  state after a refresh.
* Status transitions keep stable entry identity while changing only the task
  lifecycle and score surface:
  * `pending` / `cancelled` -> `score=null`
  * `fallback` -> `score.backend=fallback`
  * `succeeded` -> `score.backend=ai`

## Verification

Close-out rerun passed on 2026-05-15 and is recorded in
`milestone-14-closeout-audit.md`:

* `python3 -m py_compile backend_django/manage.py $(find backend_django/apps -maxdepth 4 -name '*.py' -print)` -> passed
* `.venv-django/bin/python backend_django/manage.py check` -> `System check identified no issues (0 silenced).`
* `.venv-django/bin/python backend_django/manage.py makemigrations --check --dry-run` -> `No changes detected`
* `.venv-django/bin/python backend_django/manage.py test apps.ai apps.writing apps.billing -v 1` -> `Ran 65 tests ... OK`

Relevant coverage in this milestone:

* `backend_django/apps/writing/tests.py`
  * pending detail contract after score-task creation
  * cancelled-pending detail contract after task cancellation
  * succeeded detail contract after successful completion + billing settlement
  * fallback detail contract after local fallback scoring

## Known Gaps

* The bridge contract is still expressed through response dictionaries and
  integration tests; it is not yet codified through serializers or OpenAPI
  schemas.
* The old frontend still does not call this Django entry detail endpoint. This
  milestone only freezes the server contract for a later bridge phase.
* The bridge currently models only the latest related `writing_score` task for
  the entry, not a full task history.

## Rollback

Rollback is documentation/test only:

* remove the bridge-contract assertions from `backend_django/apps/writing/tests.py`;
* revert the README/spec notes describing the entry detail handoff;
* keep the production route behavior unchanged if the project decides to defer
  the frontend handoff contract.

## Next Recommendation

When the project is ready to bridge the old writing UI or a future Vue client,
use `GET /api/writing/entries/{entry_id}` as the canonical refresh-safe polling
surface instead of inventing parallel task-tracking state in the browser.
