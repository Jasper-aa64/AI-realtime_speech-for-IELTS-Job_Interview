# Add Django attempts start endpoint

## Goal

Implement Django `POST /api/attempts/start` to create speaking practice attempts. This is Phase 1 of the speaking session migration—pure CRUD with no external dependencies. The endpoint creates `SpeakingAttempt` and initial `SpeakingTurn` records, returning a response shape compatible with the old server.

## What I Already Know

### Frontend Request (web/static/app.js:535-542)
```js
const attempt = await api("/api/attempts/start", {
  mode,                           // "p1" | "p2" | "p3" | "mock"
  candidate: names.englishName,   // e.g., "Jasper"
  full_name: names.fullName,      // e.g., "Li Hua"
  english_name: names.englishName,
  ...(mode === "p3" ? { p3_intensity: state.p3Intensity } : {}),
  ...(mode === "p3" && theme ? { theme } : {}),
});
```

### Old Server Response Shape (web/ielts_server.py:4260-4284)
```json
{
  "id": "abc123hex",
  "timestamp": "2026-05-16T10:00:00Z",
  "status": "started",
  "user_id": "user123",
  "mode": "mock",
  "part": "mock",
  "title": "Full mock exam",
  "question": "What is your full name?",
  "cue_card": {...},
  "turns": [
    {
      "id": "t1",
      "part": "p1",
      "question": "What is your full name?",
      "status": "pending",
      "counts_toward_total": true,
      "examiner_tts": {"provider": "volcengine", "status": "pending"}
    }
  ],
  "current_turn": "t1",
  "candidate": "Jasper",
  "full_name": "Li Hua",
  "english_name": "Jasper",
  "pronunciation": {"provider": "azure", "status": "pending"},
  "ielts_score": null,
  "feedback_summary": "",
  "criteria_feedback": {},
  "band7_version": "",
  "model_audio": null,
  "upgrade_notes": [],
  "ai_coaching": "",
  "p3_generation_status": "pending_after_p2",
  "p3_theme": "career_choices"
}
```

### Django Models Coverage

| Field | Model | Status |
|-------|-------|--------|
| `id` | `SpeakingAttempt.attempt_id` | ✓ |
| `mode` | `SpeakingAttempt.mode` | ✓ |
| `part` | `SpeakingAttempt.part` | ✓ |
| `status` | `SpeakingAttempt.status` | ✓ |
| `title` | `SpeakingAttempt.title` | ✓ |
| `full_name` | `SpeakingAttempt.full_name` | ✓ |
| `english_name` | `SpeakingAttempt.english_name` | ✓ |
| `turns` | `SpeakingTurn` via FK | ✓ |
| `cue_card` | Not in model | Need metadata JSON |
| `current_turn` | Not in model | Computed at runtime |
| `pronunciation` | Not in model | Default in response |
| `p3_*` fields | Not in model | Use metadata JSON |

### Turn Building Logic (web/ielts_server.py:2165-2199)

- **mode=mock**: P1 turns + P2 turn, P3 generated after P2 complete
- **mode=p1**: N P1 turns from question bank
- **mode=p2**: Single P2 turn from question bank
- **mode=p3**: P3 turns generated from theme

## Assumptions

* Question bank loading via `services.QuestionBank` already implemented
* TTS generation is NOT in scope—`examiner_tts.status` returns "pending"
* P3 questions are generated synchronously via fallback (no Codex)
* Frontend will continue to work with both old server and Django

## Requirements

### Endpoint
* `POST /api/attempts/start`
* Must be authenticated (401 for unauthenticated requests)
* Owner-scoped: attempt created for authenticated user

### Request Payload
* `mode`: "p1" | "p2" | "p3" | "mock" (required)
* `candidate`: string (optional, default from user profile)
* `full_name`: string (optional)
* `english_name`: string (optional)
* `p3_intensity`: "normal" | "high" (optional, for p3 mode)
* `theme`: string (optional, for p3 mode)

### Response Shape
* Must match old server response exactly
* `id`: UUID hex string
* `timestamp`: ISO 8601 string
* `status`: "started"
* `mode`, `part`, `title`, `question`: from build logic
* `turns`: array of turn objects with `id`, `part`, `question`, `status`, `examiner_tts`
* `current_turn`: first turn id
* `candidate`, `full_name`, `english_name`: from payload or defaults
* `pronunciation`: default `{"provider": "azure", "status": "pending"}`
* `ielts_score`: null
* `metadata` fields: `p3_generation_status`, `p3_theme` for mock/p3 modes

### Turn Creation
* Use `QuestionBank` to sample questions
* Create `SpeakingAttempt` record
* Create `SpeakingTurn` records linked to attempt
* Store cue_card and metadata in `SpeakingAttempt.metadata` JSON field

### Fallback Strategy
* Frontend uses Django by default
* If Django returns error, frontend could fallback to old server (optional)
* For MVP: No feature flag, direct cutover with error handling

## Acceptance Criteria

* [x] `POST /api/attempts/start` requires authentication
* [x] Request with valid mode creates SpeakingAttempt + SpeakingTurn records
* [x] Response shape matches old server exactly
* [x] `mode=mock` creates P1 + P2 turns with correct metadata
* [x] `mode=p1` creates N P1 turns
* [x] `mode=p2` creates single P2 turn with cue_card
* [x] `mode=p3` creates P3 turns from theme
* [x] Invalid mode returns 400 error
* [x] Turn sequence numbers are correct
* [x] Tests cover all modes, auth, and response shape

## Definition of Done

* [x] Django speaking tests pass (27 tests)
* [x] Frontend syntax check passes
* [ ] Manual smoke test: start attempt in each mode, verify response
* [x] Old server remains available as backup

## Out of Scope (explicit)

* Audio upload (`/api/attempts/{id}/turns/{id}/audio`)
* Turn completion (`/api/attempts/{id}/turns/{id}/complete`)
* Scoring (`/api/attempts/{id}/score`)
* Abort (`/api/attempts/{id}/abort`)
* TTS generation
* Real AI provider integration
* Billing integration
* C++ changes

## Technical Approach

### Service Function
Add to `backend_django/apps/speaking/services.py`:
```python
def start_attempt(user, payload: dict) -> dict:
    mode = normalize_mode(payload.get("mode", "p1"))
    attempt_id = uuid.uuid4().hex
    # Build turns based on mode using QuestionBank
    # Create SpeakingAttempt + SpeakingTurn records
    # Return response dict matching old server shape
```

### View
Add to `backend_django/apps/speaking/views.py`:
```python
@require_http_methods(["POST"])
def attempt_start_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    payload = json.loads(request.body)
    attempt = start_attempt(request.user, payload)
    return JsonResponse(attempt)
```

### URL
Add to `backend_django/config/urls.py`:
```python
path("api/attempts/start", speaking_views.attempt_start_view, name="attempts-start"),
```

### Turn Building
Reuse `QuestionBank` from existing services. Implement simplified turn creation:
- P1: Sample N questions from bank
- P2: Sample one cue card
- P3: Generate from theme via fallback function
- Mock: P1 + P2, mark P3 pending

## Technical Notes

### Files to Modify
- `backend_django/apps/speaking/services.py` - add `start_attempt()`, turn builders
- `backend_django/apps/speaking/views.py` - add `attempt_start_view`
- `backend_django/config/urls.py` - add route
- `backend_django/apps/speaking/tests.py` - add tests

### Key Dependencies
- `services.QuestionBank` - already implemented
- `uuid`, `json` - standard library
- No external API calls

### Reference
- Design doc: `.trellis/tasks/archive/2026-05/05-15-design-speaking-session-scoring-audio-migration-to-django/prd.md`
- Old server: `web/ielts_server.py` lines 4253-4288, 2165-2199
- Frontend: `web/static/app.js` lines 535-552
