# Design: Speaking Session Scoring Audio Migration to Django

## Goal

Design a phased migration plan for moving the speaking practice session, attempt, turn, audio, scoring, and AI regeneration flows from `web/ielts_server.py` to Django. This task produces design documentation only—no implementation code.

## What I Already Know

### Old Server APIs (High Risk)

| API | Method | Description | Frontend Calls |
|-----|--------|-------------|----------------|
| `/api/session/start` | POST | Start practice session, return sample questions | Not directly |
| `/api/attempts/start` | POST | Create new attempt with turns | ✓ Line 535 |
| `/api/attempts/{id}/turns/{id}/audio` | POST | Upload candidate audio | ✓ Line 872 |
| `/api/attempts/{id}/turns/{id}/complete` | POST | Complete turn, trigger transcription/feedback | ✓ Line 881 |
| `/api/attempts/{id}/score` | POST | Score completed attempt, generate report | ✓ Lines 910, 1720 |
| `/api/attempts/{id}/abort` | POST | Abort attempt, cleanup | ✓ Line 2162 |
| `/api/attempts/{id}/turns/{id}/feedback/regenerate` | POST | Regenerate AI feedback for turn | ✓ Line 1833 |
| `/api/attempts/{id}/turns/{id}/transcript/regenerate` | POST | Regenerate transcript from audio | ✓ Line 1850 |
| `/api/score` | POST | Legacy generic scoring | Not called |
| `/api/tts` | POST | Generate TTS audio | Not called directly |
| `/api/p3/questions` | POST | Generate P3 questions from theme | Not called directly |
| `/api/p3/follow-up` | POST | Generate P3 follow-up questions | Not called directly |

### Django Existing Models

| Model | Coverage | Gaps |
|-------|----------|------|
| `SpeakingAttempt` | attempt_id, mode, part, status, candidate names | No turns embedded, no cue_card |
| `SpeakingTurn` | turn_id, sequence, question, transcript, audio_path | No feedback regeneration state |
| `SpeakingReport` | scores, feedback | Generated after scoring |
| `SpeakingTrainingObservation` | weak items tracking | Complete |
| `AITask` | async AI task tracking | Need to wire to attempts/turns |
| Billing models | wallet, reservations | Need to wire to attempts |

### Key Data Flows

**1. Start Attempt Flow**
```
POST /api/attempts/start
  → build_turns(state, attempt_id, mode, payload)
  → create attempt with turns array
  → ensure_examiner_tts (may call volcengine)
  → save_attempt to JSON file
  → return attempt object
```

**2. Upload Audio Flow**
```
POST /api/attempts/{id}/turns/{id}/audio (multipart)
  → validate content-type, size
  → save to audio_dir/{attempt_id}_{turn_id}.{ext}
  → update turn["audio"] = {path, content_type, url}
  → turn["status"] = "audio_uploaded"
  → save_attempt
```

**3. Complete Turn Flow**
```
POST /api/attempts/{id}/turns/{id}/complete
  → if audio exists: transcribe_and_assess_azure(audio_path)
  → clean_transcript, spoken_markdown
  → apply_p1_name_identity, insert_p1_identity_follow_up
  → if P2 complete and mock mode: append_p3_turns
  → next_turn = find next or None
  → if next_turn: ensure_examiner_tts(next_turn)
  → if no next_turn: status = "ready_to_score"
  → return {attempt, turn, next_turn}
```

**4. Score Attempt Flow**
```
POST /api/attempts/{id}/score
  → validate all turns completed
  → build transcript from all turns
  → score_with_codex OR heuristic_score fallback
  → build_turn_band7 for each turn
  → build_detailed_report
  → record training observations
  → status = "scored"
  → save_attempt
```

**5. Abort Flow**
```
POST /api/attempts/{id}/abort
  → validate not already scored
  → status = "aborted"
  → clear current_turn
  → save_attempt
  → NOTE: No billing release currently
```

**6. Regenerate Flows**
```
POST /api/attempts/{id}/turns/{id}/feedback/regenerate
  → build_turn_feedback (may call codex)

POST /api/attempts/{id}/turns/{id}/transcript/regenerate
  → transcribe_and_assess_azure(audio_path)
  → build_turn_feedback
```

### External Dependencies

| Dependency | Usage | Django Status |
|------------|-------|---------------|
| Azure Speech | Transcription + pronunciation assessment | Not integrated |
| Volcengine TTS | Examiner voice synthesis | Not integrated |
| Codex AI | Scoring, feedback generation, P3 generation | Fallback only |
| File storage | Audio files in `reports/audio/` | Not configured |
| Billing | Usage tracking via `BillingStore` | Integrated in Django |

## Assumptions

* Migration will use feature flags to toggle between old server and Django
* Audio files will continue to be stored on disk (not in database)
* AI provider integration remains fallback-only for now
* Frontend API paths will remain unchanged

## Migration Strategy

### Approach: Compatibility Wrapper + Feature Flag

**Phase 1: Read-through wrapper**
- Django creates endpoints that proxy to old server for mutation
- Allows testing Django routing without breaking flow

**Phase 2: Shadow write**
- Django handles mutation, also writes to old server
- Compare results for consistency

**Phase 3: Cutover**
- Feature flag enables Django-only path
- Old server remains as fallback

### Prerequisites for Full Migration

1. **AI Provider Integration**
   - Codex integration for scoring
   - Azure Speech integration for transcription
   - Volcengine TTS integration for examiner voice

2. **Audio Storage Strategy**
   - Define storage backend (local filesystem, S3, etc.)
   - Configure media URL handling
   - Migration path for existing audio files

3. **Billing Wiring**
   - Connect attempt lifecycle to billing reservations
   - Handle abort → release billing
   - Handle score → settle billing

## Phased Migration Plan

### Phase 1: Attempt Lifecycle (Low Risk)

**Scope**: Create attempt, update status, abort
**Why low risk**: No audio, no AI provider calls, pure CRUD

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| 1.1 | Django `POST /api/attempts/start` | Creates attempt with turns, returns same shape as old server |
| 1.2 | Django `POST /api/attempts/{id}/abort` | Updates status, releases billing if reserved |
| 1.3 | Attempt state machine | Enforce valid transitions: started → audio_uploaded → completed → ready_to_score → scored/aborted |

**Blockers**: None

### Phase 2: Audio Upload (Medium Risk)

**Scope**: Upload candidate audio, store file, update turn
**Why medium risk**: File I/O, but no external API calls

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| 2.1 | Django `POST /api/attempts/{id}/turns/{id}/audio` | Multipart upload, save to media dir, update turn |
| 2.2 | Django `GET /api/audio/{id}/{id}/candidate` | Serve uploaded audio file |
| 2.3 | Audio cleanup on abort | Delete audio files when attempt aborted |

**Blockers**: Media storage configuration

### Phase 3: Turn Complete (High Risk)

**Scope**: Complete turn, trigger transcription, generate feedback
**Why high risk**: Requires Azure Speech integration

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| 3.1 | Django `POST /api/attempts/{id}/turns/{id}/complete` | Process turn, update status |
| 3.2 | Azure transcription integration | Call Azure API, parse result |
| 3.3 | AI task fallback path | Use AI task queue for transcription if direct call fails |
| 3.4 | P3 generation for mock mode | Generate P3 questions after P2 complete |

**Blockers**: Azure Speech credentials, AI task worker for transcription

### Phase 4: Scoring (High Risk)

**Scope**: Score completed attempt, generate report
**Why high risk**: Requires Codex integration, billing settlement

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| 4.1 | Django `POST /api/attempts/{id}/score` | Score attempt, create SpeakingReport |
| 4.2 | Billing integration | Reserve tokens before scoring, settle on completion |
| 4.3 | Training observation recording | Record weak items from scored attempt |
| 4.4 | Report generation | Build full report payload matching old server shape |

**Blockers**: Codex API credentials, billing integration validation

### Phase 5: Regeneration (High Risk)

**Scope**: Regenerate feedback, regenerate transcript
**Why high risk**: Requires AI provider, modifies existing data

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| 5.1 | Django `POST /api/attempts/{id}/turns/{id}/feedback/regenerate` | Regenerate via AI task |
| 5.2 | Django `POST /api/attempts/{id}/turns/{id}/transcript/regenerate` | Re-transcribe via Azure |
| 5.3 | Concurrency protection | Prevent simultaneous regeneration |

**Blockers**: Same as Phase 3 and 4

### Phase 6: TTS and P3 (Optional)

**Scope**: TTS generation, P3 question generation
**Why optional**: Frontend may not directly call these

| Task | Description | Acceptance Criteria |
|------|-------------|---------------------|
| 6.1 | Django `POST /api/tts` | Generate TTS via Volcengine |
| 6.2 | Django `POST /api/p3/questions` | Generate P3 questions via Codex |
| 6.3 | Examiner TTS preloading | Pre-generate examiner audio for turns |

**Blockers**: Volcengine credentials, may be deferred

## Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| User practice interrupted | Medium | High | Feature flag, instant rollback |
| Audio files lost | Low | High | Backup before migration, verify file preservation |
| Transcription fails | Medium | Medium | Fallback to browser dictation transcript |
| Scoring fails | Medium | High | Fallback to heuristic scoring, retry queue |
| Billing errors | Medium | High | Reconcile job, manual audit trail |
| Report/history inconsistency | Low | Medium | Shadow write comparison |
| Old data incompatible | Low | Medium | Migration script, validation tests |

## Acceptance Criteria

* [ ] Complete API contract documentation for all 12 endpoints
* [ ] Phased migration plan reviewed and approved
* [ ] Risk matrix reviewed
* [ ] Prerequisites identified with blockers
* [ ] First implementation task defined (Phase 1.1)

## Definition of Done

* Design document complete
* No implementation code in this task
* PRD reviewed by user
* Ready to create implementation tasks

## Out of Scope (explicit)

* No implementation code
* No C++ changes
* No deletion of old server
* No frontend logic changes
* No real AI provider integration
* No billing changes (documentation only)

## Technical Notes

### Files to Reference

- `web/ielts_server.py`: lines 4169-4623 (session/scoring handlers)
- `backend_django/apps/speaking/models.py`: existing models
- `backend_django/apps/speaking/services.py`: existing services
- `web/static/app.js`: lines 535, 872, 881, 910, 1720, 1833, 1850, 2162 (frontend calls)

### API Response Shape Examples

**POST /api/attempts/start response**:
```json
{
  "id": "abc123",
  "timestamp": "2026-05-15T10:00:00Z",
  "status": "started",
  "mode": "mock",
  "part": "p1",
  "turns": [{"id": "t1", "question": "...", "status": "pending"}],
  "current_turn": "t1",
  "candidate": "Jasper"
}
```

**POST /api/attempts/{id}/turns/{id}/complete response**:
```json
{
  "attempt": {...},
  "turn": {"id": "t1", "transcript_cleaned": "...", "status": "completed"},
  "next_turn": {"id": "t2", ...}
}
```

### Next Recommended Task

**Task 1.1: Django attempts/start endpoint**

Create `POST /api/attempts/start` in Django that:
- Accepts same payload as old server
- Creates SpeakingAttempt + SpeakingTurn records
- Returns same response shape
- Feature flag to toggle between Django and old server

This is the lowest-risk entry point for migration.
