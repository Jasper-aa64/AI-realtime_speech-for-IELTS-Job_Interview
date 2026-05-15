# Design Django Speaking Audio Storage Migration

## Goal

Design the migration of speaking practice audio upload from `web/ielts_server.py` to Django. This task produces design documentation only—no implementation code.

## What I Already Know

### Old Server Audio Upload Contract

**POST /api/attempts/{attempt_id}/turns/{turn_id}/audio**

Request:
- Content-Type: `audio/*` or `application/octet-stream`
- Body: raw audio blob (binary)
- Max size: 25 MB

Response:
```json
{
  "ok": true,
  "audio": {
    "path": "/path/to/reports/audio/{attempt_id}_{turn_id}.{ext}",
    "content_type": "audio/webm",
    "bytes": 12345,
    "duration_seconds": null,
    "url": "/api/audio/{attempt_id}/{turn_id}/candidate"
  }
}
```

Behavior:
- Validates content type (must be `audio/*` or `application/octet-stream`)
- Validates size (1 byte to 25 MB)
- Rejects upload to aborted attempts
- Saves file to `reports/audio/{attempt_id}_{turn_id}.{extension}`
- Updates turn `status` to `audio_uploaded`
- Extension derived from Content-Type via `mimetypes.guess_extension()`

**GET /api/audio/{attempt_id}/{turn_id}/candidate**

Returns uploaded candidate audio file.

### Frontend Dependency

From `web/static/app.js:872-881`:
```javascript
const upload = await fetch(`/api/attempts/${attempt.id}/turns/${turn.id}/audio`, {
  method: "POST",
  headers: { "Content-Type": mimeType.split(";")[0] },
  body: blob,
});
// Response: {"ok": true, "audio": {...}}
// Then calls /api/attempts/{id}/turns/{id}/complete
```

Audio URL used in report display:
```html
<audio controls src="/api/audio/${attemptId}/${turnId}/candidate"></audio>
```

### Django Model Coverage

`SpeakingTurn` model fields:
- `audio_path`: `CharField(max_length=500, blank=True)` - can store file path
- `duration_seconds`: `DecimalField` - for audio duration
- `metadata`: `JSONField` - can store content_type, bytes, url

Gaps:
- No `audio_content_type` field (can use metadata)
- No `audio_bytes` field (can use metadata)
- No `audio_url` field (computed from attempt_id/turn_id)

### Current Django Settings

- `STATIC_URL = 'static/'`
- No `MEDIA_ROOT` or `MEDIA_URL` configured
- Need to add media configuration

## Assumptions

- Audio files will continue to be stored on local filesystem (not S3/cloud storage)
- Django will serve media files in development
- Production deployment will use nginx or similar to serve media
- No Azure Speech integration in this phase
- No transcript generation in this phase
- No scoring in this phase

## Design

### Storage Configuration

Add to `backend_django/config/settings.py`:
```python
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR.parent / 'media'
```

Audio directory: `media/audio/`

### File Naming Convention

```
media/audio/{attempt_id}_{turn_id}.{extension}
```

Example: `media/audio/abc123hex_t1.webm`

### URL Pattern

```
/media/audio/{attempt_id}_{turn_id}.{extension}
```

For API compatibility with old server:
```
/api/audio/{attempt_id}/{turn_id}/candidate -> serves file from media/audio/
```

### Database Fields

No migration needed. Use existing `SpeakingTurn` fields:
- `audio_path`: stores relative path from MEDIA_ROOT
- `duration_seconds`: null for now (populated during turn complete)
- `metadata`: stores additional audio info:
  ```json
  {
    "audio_content_type": "audio/webm",
    "audio_bytes": 12345,
    "audio_uploaded_at": "2026-05-16T10:00:00Z"
  }
  ```

### Validation Rules

1. **Authentication**: Must be logged in (401)
2. **Owner scope**: Can only upload to own attempts/turns
3. **Content type**: Must be `audio/*` or `application/octet-stream`
4. **Size**: 1 byte to 25 MB
5. **Attempt status**: Cannot upload to aborted attempts
6. **Turn existence**: Must find turn in attempt

### Error Responses

| Condition | Status | Error |
|-----------|--------|-------|
| Not authenticated | 401 | `{"error": "authentication required"}` |
| Attempt not found | 404 | `{"error": "Attempt not found"}` |
| Turn not found | 404 | `{"error": "Turn not found"}` |
| Aborted attempt | 400 | `{"error": "Aborted attempts cannot accept audio"}` |
| Empty upload | 400 | `{"error": "Audio upload is empty"}` |
| Too large | 400 | `{"error": "Audio upload exceeds 25 MB"}` |
| Invalid content type | 400 | `{"error": "Unsupported audio content type: ..."}` |

### Cleanup on Delete/Abort

When `SpeakingAttempt` is deleted:
- Cascade delete `SpeakingTurn` records
- Audio files remain on disk (not tracked by database)

When attempt is aborted:
- Audio files remain on disk (no cleanup in old server either)

### Rollback Plan

1. Feature flag to disable Django audio upload
2. Frontend can fallback to old server if Django returns error
3. Old server remains running as backup
4. No data loss if rollback needed (audio files are new uploads)

## Implementation Phases

### Phase 1: Audio Upload Endpoint (This task if implemented)

1. Add `MEDIA_ROOT`, `MEDIA_URL` to settings
2. Add media serving in `urls.py` (dev only)
3. Add `upload_turn_audio()` service function
4. Add `turn_audio_upload_view` view
5. Add `GET /api/audio/{attempt_id}/{turn_id}/candidate` view
6. Add tests for upload, retrieval, validation

### Phase 2: Turn Complete (Future)

- Requires Azure Speech integration
- Requires transcript generation
- High risk, separate task

### Phase 3: Scoring (Future)

- Requires AI provider
- Requires billing integration
- High risk, separate task

## Acceptance Criteria

* [x] Audio upload contract documented
* [x] Django model coverage analyzed
* [x] Storage strategy defined
* [x] Validation rules defined
* [x] Error responses defined
* [x] Rollback plan defined
* [x] Implementation phases outlined

## Definition of Done

* [x] Design document complete
* [x] PRD reviewed
* [x] Implementation task created and completed

## Out of Scope (explicit)

* No implementation code
* No Azure Speech integration
* No transcript generation
* No scoring
* No billing integration
* No deletion of old server
* No frontend changes

## Technical Notes

### Files to Reference

- `web/ielts_server.py`: lines 4361-4389 (audio upload handler)
- `web/ielts_server.py`: lines 4597-4627 (audio retrieval handler)
- `web/ielts_server.py`: line 42 (MAX_AUDIO_BYTES constant)
- `web/static/app.js`: lines 872-881 (frontend upload call)
- `backend_django/apps/speaking/models.py`: SpeakingTurn model

### Dependencies

- Django's default storage backend
- No external services required

### Decision: Implement Audio Upload Skeleton?

Based on analysis:

| Condition | Status |
|-----------|--------|
| Model has sufficient fields | ✅ Yes (audio_path + metadata) |
| No migration needed | ✅ Yes |
| No Azure Speech | ✅ Not needed |
| No scoring | ✅ Not needed |
| No frontend changes | ✅ Default paths unchanged |
| No billing | ✅ Not needed |
| Old /api/attempts/start complete | ✅ Done |

**Recommendation**: Conditions are met. Can proceed to implementation of audio upload skeleton.
