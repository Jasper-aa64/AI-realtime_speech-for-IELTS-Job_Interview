# Migrate speaking question bank and training APIs to Django

## Goal

Migrate the remaining speaking practice APIs (question bank and training observations) from `web/ielts_server.py` to Django, completing the speaking module API surface and reducing old server dependencies.

## What I Already Know

**Old server APIs to migrate**:
- `GET /api/question-bank/summary` - returns counts and topic lists
- `POST /api/question-bank/sample` - returns random P1 questions + P2 topic
- `GET /api/training/weak-items` - returns user's weak question observations
- `GET /api/training/replay-queue` - returns practice queue combining weak + coverage items

**Frontend usage** (web/static/app.js):
- Line 2509: `api("/api/training/weak-items")` - displays weak items in settings
- Line 2522: `api("/api/training/replay-queue")` - displays practice queue
- Line 2562: `api("/api/question-bank/summary")` - displays bank stats

**Django current state**:
- `SpeakingTrainingObservation` model exists with `weak_item_flag`, `weak_reasons`, `next_due`, etc.
- No question bank models or services
- No training API views
- Training data can be queried from Django model (no need for separate SQLite)

**Question bank data source**:
- `data/ielts/part1/*.json` - P1 questions with topic, season, questions array
- `data/ielts/part2/*.json` - P2 topics with title, bullets, rounding, p3_theme
- Loaded by `QuestionBank` class at server startup

**Training data model** (Django):
- `SpeakingTrainingObservation` has: `user`, `question_id`, `part`, `question`, `transcript`, `overall_band`, `weak_item_flag`, `weak_reasons`, `next_due`, `observed_at`
- Properly indexed for weak item queries

## Assumptions

* Question bank data can remain as JSON files (no need to import into DB)
* Training observations are already in Django via legacy import
* No real-time sync needed between old server and Django for training data

## Decision (ADR-lite)

**Context**: Question bank and training observation read APIs still use old server. Need to migrate to Django to reduce old server dependencies.

**Decision**: Migrate only 4 READ APIs in this task. Training mutation APIs (create/update) remain in old server for now.

**Consequences**: Minimal risk, frontend decouples from old server for read operations. Training writes handled in separate task to avoid touching session/scoring flow.

## Requirements

### API Path Compatibility (Intentional Decision)
* Keep old server paths (`/api/question-bank/*`, `/api/training/*`) instead of new `/api/speaking/*` prefix
* Rationale: Frontend already uses these paths via `api()` helper; Django intercepts them, avoiding frontend changes
* This maintains backward compatibility and reduces migration risk

### Question Bank APIs
* `GET /api/question-bank/summary` - return counts and topic/theme lists
* `POST /api/question-bank/sample` - return random sample for practice
* Questions loaded from `data/ielts/part1/*.json` and `data/ielts/part2/*.json`
* Response shape must match old server exactly for frontend compatibility

### Training APIs
* `GET /api/training/weak-items` - return user's weak items with aggregation
* `GET /api/training/replay-queue` - return practice queue (weak + coverage)
* All endpoints must be owner-scoped (user can only see their own training data)
* Filter by `weak_item_flag=True` and group by `question_id`
* Order by weak count, last seen, next due
* Response shape must match old server exactly

### Frontend Bridge
* No changes needed - `api()` helper routes to Django, paths unchanged

## Acceptance Criteria

* [x] `GET /api/question-bank/summary` returns correct counts and topics
* [x] `POST /api/question-bank/sample` returns valid random sample with P1 + P2
* [x] `GET /api/training/weak-items` returns only user's weak items
* [x] `GET /api/training/replay-queue` combines weak + coverage items
* [x] All endpoints require authentication (401 for unauthenticated)
* [x] Training endpoints are owner-scoped (user sees only their data)
* [x] Response shapes match old server exactly
* [x] Frontend calls new Django APIs (paths unchanged, no frontend changes needed)
* [x] Tests cover auth, owner isolation, empty state, response shape

## Definition of Done

* Backend tests added for all 4 endpoints (auth, owner isolation, empty state, response shape)
* Frontend syntax check passes: `node --check web/static/app.js`
* Django check passes: `python manage.py check`
* Django speaking tests pass: `python manage.py test apps.speaking.tests`
* Response shapes verified against old server handlers
* Manual smoke test: settings page displays weak items and bank summary

## Out of Scope (explicit)

* Training observation create/update/mutation APIs
* Speaking session flow (start, turn recording, scoring)
* Speaking report/history APIs (already migrated)
* Audio generation/playback APIs
* Question bank mutation (adding new questions)
* Writing module changes
* C++ changes
* Real AI provider integration
* Database model changes (use existing models)

## Technical Notes

**Files to create/modify**:
- `backend_django/apps/speaking/services.py` - add question bank and training services
- `backend_django/apps/speaking/views.py` - add 4 new views
- `backend_django/config/urls.py` - add new routes
- `web/static/app.js` - update API paths
- `backend_django/apps/speaking/tests.py` - add tests

**Question bank data path**:
- Configure via Django settings or environment variable
- Default: `data/ielts/` relative to project root

**Training aggregation logic** (from old server lines 520-541):
```sql
SELECT question_id, part, question, COUNT(*) AS attempts,
       MAX(observed_at) AS last_seen,
       MIN(next_due) AS next_due,
       AVG(overall_band) AS avg_band,
       AVG(relevance) AS avg_relevance,
       SUM(weak_item_flag) AS weak_count
FROM training_observations
WHERE user_id = ?
GROUP BY question_id, part, question
HAVING weak_count > 0
ORDER BY weak_count DESC, last_seen DESC, next_due ASC
```

Can be replicated with Django ORM aggregation.
