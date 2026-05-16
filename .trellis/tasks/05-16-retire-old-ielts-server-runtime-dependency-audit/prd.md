# Retire old IELTS server runtime dependency audit

## Goal

Move the remaining low-provider-risk IELTS speaking runtime endpoints from the
old `web/ielts_server.py` runtime into Django, while preserving usability by
keeping the old server in place until all high-risk provider and frontend
cutover work is explicitly validated.

## What I Already Know

* Django already owns accounts, writing, billing, AI tasks, speaking history,
  question bank/training reads, `POST /api/attempts/start`, candidate audio
  upload, and candidate audio retrieval.
* Frontend runtime still calls:
  * `POST /api/attempts/{id}/turns/{turn_id}/complete`
  * `POST /api/attempts/{id}/score`
  * `POST /api/attempts/{id}/abort`
  * regenerate endpoints
  * `/api/tts`
  * `/api/p3/questions` and `/api/p3/follow-up`
* The old server currently still handles static frontend serving and only
  proxies a limited subset of Django paths. Deleting it is not safe in this
  task.
* The existing Django models can represent attempts, turns, reports, uploaded
  audio, and training observations without a migration for the fallback
  runtime endpoints.

## Requirements

* Produce a retirement dependency audit and readiness checklist.
* Add Django `POST /api/attempts/{attempt_id}/turns/{turn_id}/complete`.
  * Must be authenticated and owner-scoped.
  * Must reject aborted attempts.
  * First version must not require Azure Speech.
  * Must accept browser transcript fallback from the existing frontend payload.
  * Must update turn transcript/status metadata and attempt `current_turn`.
  * Must mark attempt `ready_to_score` when no next turn remains.
  * Must return `{"attempt": ..., "turn": ..., "next_turn": ...}` compatible
    with the frontend.
* Add Django `POST /api/attempts/{attempt_id}/abort`.
  * Must be authenticated and owner-scoped.
  * Must reject scored attempts.
  * Must be idempotent for already-aborted attempts.
  * Must not touch billing in this task.
* Add Django `POST /api/attempts/{attempt_id}/score`.
  * Must be authenticated and owner-scoped.
  * Must reject aborted and incomplete attempts.
  * Must use deterministic local fallback scoring, not real provider calls.
  * Must create/update `SpeakingReport` so `/api/history` and detail can read
    the scored attempt.
  * Must write basic `SpeakingTrainingObservation` rows from completed turns.
* Keep existing start/audio/history/question-bank/training contracts stable.
* Do not change frontend behavior or delete/freeze the old server in this task.

## Acceptance Criteria

* [x] Dependency audit documents Django-owned, old-only, and blocked endpoints.
* [x] `turn complete` requires authentication.
* [x] `turn complete` is owner-scoped and returns 404 for wrong owner/missing rows.
* [x] `turn complete` stores fallback/browser transcript and marks the turn completed.
* [x] `turn complete` advances `current_turn` or marks the attempt ready to score.
* [x] `abort` requires authentication, is owner-scoped, and marks attempts aborted.
* [x] `abort` rejects scored attempts.
* [x] `score` requires authentication and is owner-scoped.
* [x] `score` rejects aborted or incomplete attempts.
* [x] `score` creates a valid `SpeakingReport` visible through history/detail.
* [x] No real Azure/Codex/Volcengine/billing integration is added.
* [x] Full Django tests and JS syntax check pass.

## Definition of Done

* PRD and milestone note document scope, changed files, validation, rollback,
  and remaining blockers.
* Django speaking tests cover the new endpoints.
* Full Django tests pass.
* `manage.py check`, migration dry-run, and `node --check web/static/app.js`
  pass.
* Business commit, archive commit, and journal commit are created.

## Out of Scope

* Real Azure Speech transcription.
* Real Codex/OpenAI scoring.
* Volcengine TTS.
* Billing reservation/settlement changes.
* Regenerate endpoints.
* P3 AI generation endpoint migration.
* Frontend cutover or feature flag changes.
* Deleting, freezing, or deprecating `web/ielts_server.py`.

## Technical Notes

* Relevant files:
  * `backend_django/apps/speaking/services.py`
  * `backend_django/apps/speaking/views.py`
  * `backend_django/apps/speaking/tests.py`
  * `backend_django/config/urls.py`
* Existing frontend expects:
  * `complete` response: `attempt`, `turn`, `next_turn`
  * `score` response: full attempt/report payload renderable by
    `renderSummary()` and `renderDetail()`
  * `abort` response: attempt-shaped payload
* The old server proxy whitelist does not currently make old-server-hosted
  frontend traffic automatically use Django for speaking runtime endpoints.
  Final old server retirement must be a separate cutover task.
