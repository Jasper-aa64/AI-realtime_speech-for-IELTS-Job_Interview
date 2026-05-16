# Complete Django Runtime Migration and Retire Old IELTS Server

## Goal

Migrate the project from "old web/ielts_server.py + Django hybrid runtime" to "Django is the sole backend runtime". This task consolidates all remaining speaking runtime endpoints into Django and prepares for old server deprecation.

## Dependency Audit

### Frontend API Calls (web/static/app.js)

| Path | Django Status | Notes |
|------|---------------|-------|
| `POST /api/accounts/register/` | ✅ Covered | |
| `POST /api/accounts/login/` | ✅ Covered | |
| `POST /api/accounts/logout/` | ✅ Covered | |
| `GET /api/accounts/me/` | ✅ Covered | |
| `POST /api/attempts/start` | ✅ Covered | |
| `POST /api/attempts/{id}/turns/{id}/audio` | ✅ Covered | |
| `POST /api/attempts/{id}/turns/{id}/complete` | ✅ Covered | |
| `POST /api/attempts/{id}/score` | ✅ Covered | |
| `POST /api/attempts/{id}/abort` | ✅ Covered | |
| `POST /api/attempts/{id}/turns/{id}/feedback/regenerate` | ❌ Missing | |
| `POST /api/attempts/{id}/turns/{id}/transcript/regenerate` | ❌ Missing | |
| `GET /api/audio/{id}/{id}/candidate` | ✅ Covered | |
| `GET /api/history` | ✅ Covered | |
| `GET /api/history/{id}` | ✅ Covered | |
| `DELETE /api/history/{id}` | ✅ Covered | |
| `GET /api/billing/wallet` | ✅ Covered | |
| `POST /api/billing/recharge` | ✅ Covered | |
| `GET /api/training/weak-items` | ✅ Covered | |
| `GET /api/training/replay-queue` | ✅ Covered | |
| `GET /api/question-bank/summary` | ✅ Covered | |
| `GET /api/writing/prompts` | ✅ Covered | |
| `GET /api/writing/summary` | ✅ Covered | |
| `GET /api/writing/reports` | ✅ Covered | |
| `GET /api/writing/entries` | ✅ Covered | |
| `POST /api/writing/entries` | ✅ Covered | |
| `GET /api/writing/entries/{id}` | ✅ Covered | |
| `POST /api/writing/entries/{id}/score` | ✅ Covered | |
| `POST /api/writing/entries/{id}/score-task` | ✅ Covered | |
| `GET /api/writing/prompts/random` | ✅ Covered | |

### Old Server Handlers Not in Django

| Handler | Frontend Dependency | Priority |
|---------|---------------------|----------|
| `handle_turn_feedback_regenerate` | Yes (line 1833) | High |
| `handle_turn_transcript_regenerate` | Yes (line 1850) | High |
| `handle_tts` | No direct call | Low |
| `handle_p3` | No direct call | Low |
| `handle_legacy_score` | No direct call | Deprecated |
| `/api/tts-audio/...` | No direct call | Low |
| `/api/audio/{id}/{id}/examiner` | No direct call | Low |

### Django Coverage Summary

- **Covered**: 28 endpoints
- **Missing**: 2 endpoints (feedback_regenerate, transcript_regenerate)
- **Deprecated/Low Priority**: 4 endpoints (tts, p3, legacy_score, examiner_audio)

## Requirements

### Missing Endpoints to Implement

1. **POST /api/attempts/{attempt_id}/turns/{turn_id}/feedback/regenerate** ✅ Done
   - Regenerate AI feedback for a turn
   - Fallback: deterministic feedback based on transcript
   - Return updated turn with feedback

2. **POST /api/attempts/{attempt_id}/turns/{turn_id}/transcript/regenerate** ✅ Done
   - Re-transcribe audio and regenerate feedback
   - Fallback: use existing transcript, regenerate feedback
   - Return updated turn

### Fallback Provider Behavior

All AI-dependent operations use deterministic fallbacks:
- No real Azure Speech calls
- No real Codex calls
- No real Volcengine TTS calls
- Fallback scoring/feedback from existing `services.py` functions

## Acceptance Criteria

* [x] `POST /api/attempts/{id}/turns/{id}/feedback/regenerate` implemented
* [x] `POST /api/attempts/{id}/turns/{id}/transcript/regenerate` implemented
* [x] All speaking tests pass (55 tests)
* [x] All Django tests pass (134 tests)
* [x] Frontend syntax check passes
* [ ] Manual smoke test: start -> audio -> complete -> score -> history -> delete
* [x] Old server marked deprecated

## Definition of Done

* [x] Django is the sole runtime backend
* [x] All frontend API calls work with Django
* [x] Tests pass
* [x] Old server files retained but marked deprecated

## Out of Scope (explicit)

* Real Azure Speech integration
* Real Codex integration
* Real Volcengine TTS integration
* Delete old server files
* Breaking changes to API contracts
* Frontend logic changes

## Technical Notes

### Files to Modify

- `backend_django/apps/speaking/services.py` - add regenerate functions
- `backend_django/apps/speaking/views.py` - add regenerate views
- `backend_django/config/urls.py` - add regenerate routes
- `backend_django/apps/speaking/tests.py` - add regenerate tests
- `web/ielts_server.py` - add deprecation note in docstring
- `backend_django/README.md` - update to reflect sole runtime status

### Key Existing Functions

- `complete_turn()` - already implemented
- `abort_attempt()` - already implemented
- `score_attempt()` - already implemented
- `_build_turn_feedback()` - exists, can reuse for regenerate

### Commit Plan

Single business commit:
```
feat: complete django runtime migration

- Add feedback_regenerate and transcript_regenerate endpoints
- Add fallback-only provider behavior for all AI operations
- Mark old ielts_server.py as deprecated
- Update README to reflect Django as sole runtime
```
