# Speaking report lifecycle decoupling

## Goal

Make a completed `SpeakingAttempt` durable and visible independently of AI report generation. The same attempt must move from `unscored` to `scoring`, `ready`, or `failed` without creating duplicate history cards or deleting the original turns, transcript, or audio.

## Requirements

- A completed attempt (`READY_TO_SCORE`, or an equivalent completed legacy record) must appear in `/api/history` even when it has no `SpeakingReport` and no `AITask`.
- `/api/history/<attempt_id>` must return the same persisted lifecycle state as the list endpoint instead of returning 404 for a completed reportless attempt.
- `pending` and `running` speaking report tasks map to `report_status=scoring`; the same attempt card/detail is reused and regeneration is disabled.
- A valid `SpeakingReport` maps to `report_status=ready` and retains the stored Band/report payload.
- Terminal AI failure, including 401, 403, insufficient account balance, timeout, `finish_reason=length`, and parsing failure, maps to `report_status=failed`; the attempt, turns, transcript, and audio remain available and retry remains manual.
- A completed reportless attempt with no task maps to `report_status=unscored`; it must remain visible after refresh, login refresh, and deletion of another report.
- Retry creates or reuses an AI task for the same attempt and must never create another Attempt or another history card.
- State is computed from backend-persisted Attempt, SpeakingTurn, SpeakingReport, and AITask data. Frontend memory/localStorage may affect polling presentation only, never list/detail visibility or lifecycle truth.
- No Band may be invented, changed, or copied during lifecycle repair.

## Acceptance Criteria

- [ ] Completed practice with no AI call appears immediately as `unscored` in history/detail.
- [ ] Existing real P1 attempt `b34cd8f984354f288d47ddf82d0a48bd` appears as one `unscored` record without creating a new row.
- [ ] Pending and running tasks remain `scoring` after refresh and re-login.
- [ ] Scoring state has no regenerate control.
- [ ] Success changes the same attempt to `ready` with its stored Band and report.
- [ ] 403 `Insufficient account balance` is shown as a concise balance-related failure, preserves source data, and exposes manual retry.
- [ ] 401, timeout, truncated output, and parse errors remain visible as failed states.
- [ ] Deleting another report does not affect this attempt.
- [ ] List and detail expose the same `report_status` for every lifecycle state.
- [ ] Backend and frontend regression tests cover the complete matrix and pass with fresh verification.

## Definition of Done

- Targeted Django tests and Node frontend tests added/updated.
- `manage.py check`, targeted speaking tests, `node --check`, and focused JS tests pass.
- Existing unrelated user changes remain untouched.
- No AI task is run or retried during verification; no service/tunnel is restarted.

## Technical Approach

Use a single backend state resolver in `report_services.py` based on persisted data. History and detail call the same resolver and payload builders. Keep the current schema and task idempotency model; no migration is needed. Add explicit `unscored` payloads and retain `failed` for terminal/synthetic failures. Normalize provider error messages at the report presentation boundary. Update `app.js` to render `unscored`, `scoring`, `failed`, and `ready` distinctly and to poll persisted task IDs after loading history.

## Decision (ADR-lite)

**Context:** The prior implementation filtered history by valid report, active task, failed metadata, or stalled task, so a completed attempt without an AI task disappeared.

**Decision:** Derive the lifecycle from Attempt completion plus the newest related report task, with `SpeakingReport` validity taking precedence. No new report row or frontend-only record is introduced.

**Consequences:** Old reportless completed attempts become visible automatically. Task and report rows remain the source of truth across refresh/login. Synthetic stalled-task presentation remains a failure surface, while the underlying persisted task is never silently retried.

## Out of Scope

- Starting or restarting the AI worker.
- Automatic retries or balance changes.
- Re-scoring existing reports or changing any Band.
- Restarting `cloudflared`, changing public URLs, or changing deployment services.

## Technical Notes

- Main backend files: `backend_django/apps/speaking/report_services.py`, `services.py`, `views.py`, `tests.py`.
- Main frontend file: `web/static/app.js`; focused static test: `tests/speaking-report-scoring-state.test.js`.
- Real-data evidence: recent user P1 Attempt `b34cd8f984354f288d47ddf82d0a48bd` is `ready_to_score` with 13 turns, no report, and no speaking task.
- Real failure evidence: task `aitask_9ddf2c834d69ba3d21d83399` is terminal failed with upstream 403 `Insufficient account balance`; its source Attempt/turns remain.
