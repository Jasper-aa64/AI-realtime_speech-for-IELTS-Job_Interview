# Complete speaking history API parity with DELETE endpoint

## Goal

Add Django DELETE endpoint for speaking history items to complete API parity with the old server. The READ APIs (list and detail) are already migrated; this task adds the missing DELETE capability and moves the frontend delete action off the old server.

## What I Already Know

**Django speaking APIs already exist**:
- `GET /api/history` - returns list of valid scored speaking reports (owner-scoped)
- `GET /api/history/{attempt_id}` - returns detail for a specific attempt
- Routes defined in `backend_django/config/urls.py` lines 21-22
- Service functions in `backend_django/apps/speaking/services.py`
- Tests in `backend_django/apps/speaking/tests.py`

**Frontend already uses Django APIs**:
- `web/static/app.js` line 1153: `const payload = await api("/api/history");`
- Line 1192: `const detail = await api(`/api/history/${button.dataset.attemptId}`);`
- `loadHistory()` and `renderHistoryList()` already call Django endpoints

**Speaking models are complete**:
- `SpeakingAttempt` - with status (STARTED, READY_TO_SCORE, SCORED, ABORTED)
- `SpeakingTurn` - individual question/response pairs
- `SpeakingReport` - scoring results and feedback
- `SpeakingTrainingObservation` - weak item tracking

**Old server (`web/ielts_server.py`) still has `/api/history` routes**:
- Lines 4071-4072: history list
- Lines 4102-4104: detail by attempt_id
- These appear to be fallback routes, but frontend prefers Django

## Current Gap Analysis

| Feature | Django | Old Server | Frontend Uses |
|---------|--------|------------|---------------|
| `/api/history` (list) | ✓ | ✓ | Django |
| `/api/history/{id}` (detail) | ✓ | ✓ | Django |
| `/api/history/{id}` (DELETE) | ✗ | ✓ | Old server (line 1244) |
| Question bank APIs | ✗ | ✓ | Old server |
| Training/weak items APIs | ✗ | ✓ | Old server |
| Session/attempt mutation APIs | ✗ | ✓ | Old server |

**Key finding**: Speaking reports READ API migration is already complete. The frontend uses Django for history list and detail.

**Missing**: DELETE endpoint for removing a history item.

## Assumptions

* The user may have intended to migrate other speaking-related APIs (question bank, training, session flow).
* The DELETE endpoint is the only gap in the reports API surface.
* This task should clarify scope: is it truly about reports (already done) or broader speaking migration?

## Current State (READ APIs complete)

**Django speaking APIs already exist**:
- `GET /api/history` - returns list of valid scored speaking reports (owner-scoped)
- `GET /api/history/{attempt_id}` - returns detail for a specific attempt
- Routes defined in `backend_django/config/urls.py` lines 21-22
- Service functions in `backend_django/apps/speaking/services.py`
- Tests in `backend_django/apps/speaking/tests.py`
- Frontend already uses Django endpoints for READ

**Gap**: DELETE endpoint missing in Django. Frontend calls old server (line 1244).

## Decision (ADR-lite)

**Context**: Speaking history READ APIs are complete. Frontend delete action still uses old server.

**Decision**: Add Django DELETE endpoint to complete API parity. Hard delete with cascade (matches old behavior).

**Consequences**: Unified API surface, old server can eventually be retired for history operations.

## Requirements

* Add `DELETE /api/history/{attempt_id}` to Django
* Must be owner-scoped: only the authenticated user can delete their own attempts
* Delete must cascade to related records (turns, report, training observations)
* Frontend must use Django DELETE endpoint instead of old server
* Existing GET endpoints must remain unchanged
* Return appropriate error codes: 401 for unauthenticated, 404 for not found/wrong owner

## Acceptance Criteria

* [x] `DELETE /api/history/{attempt_id}` returns 401 for unauthenticated requests
* [x] `DELETE /api/history/{attempt_id}` returns 404 for non-existent or wrong-owner attempts
* [x] `DELETE /api/history/{attempt_id}` succeeds for owner's attempt and returns `{"ok": true}`
* [x] After delete, `GET /api/history` no longer includes the deleted item
* [x] Related records (turns, report) are cascade deleted
* [x] Frontend delete button calls Django API
* [x] Frontend list refreshes after successful delete
* [x] Django tests cover auth, owner isolation, cascade, and list exclusion

## Definition of Done

* Backend tests added for DELETE endpoint (auth, owner isolation, cascade, list exclusion)
* Frontend JS syntax check passes
* Django check passes
* Manual smoke test: delete attempt, verify list updates

## Definition of Done

* TBD based on scope clarification

## Out of Scope (explicit)

* No changes to speaking flow/simulation (session start, turn recording, scoring)
* No changes to question bank APIs
* No changes to training/weak items APIs
* No C++ changes
* No writing changes

## Technical Notes

**Old server DELETE behavior** (lines 4135-4146):
- Hard deletes attempt file (`file_path.unlink()`)
- Clears `latest_report` if matches
- Returns `{"ok": True}` on success
- Returns 404 if not found

**Django model cascade relationships**:
- `SpeakingAttempt` delete cascades to:
  - `SpeakingTurn` (CASCADE) → deleted
  - `SpeakingReport` (CASCADE) → deleted
  - `SpeakingTrainingObservation` (SET_NULL) → orphaned, not deleted
- Training observations are analytics data; orphaned records are acceptable

**Frontend delete flow** (lines 1241-1250):
1. User confirms delete in modal
2. `fetch('/api/history/${attemptId}', {method: 'DELETE'})` - currently old server
3. Clear `activeHistoryId` if matches
4. `loadHistory(false)` to refresh list
5. No explicit success message; list refresh confirms deletion

**Implementation approach**:
1. Add `delete_attempt(user, attempt_id)` service function
2. Add `delete_view` in views.py
3. Add URL route
4. Update frontend to call Django endpoint
5. Add tests for auth, owner isolation, cascade
