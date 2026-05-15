# Add Django Turn Audio Upload Endpoint

## Goal

Implement Django `POST /api/attempts/{attempt_id}/turns/{turn_id}/audio` to upload candidate audio for speaking practice turns. This is Phase 2 of the speaking session migration—audio storage with no external dependencies (no Azure Speech, no scoring, no AI).

## What I Already Know

### Old Server Contract

From `web/ielts_server.py:4361-4389`:

**Request**:
- Method: POST
- Path: `/api/attempts/{attempt_id}/turns/{turn_id}/audio`
- Content-Type: `audio/*` or `application/octet-stream`
- Body: raw audio blob
- Max size: 25 MB

**Response**:
```json
{
  "ok": true,
  "audio": {
    "path": "/path/to/reports/audio/abc123_t1.webm",
    "content_type": "audio/webm",
    "bytes": 12345,
    "duration_seconds": null,
    "url": "/api/audio/abc123/t1/candidate"
  }
}
```

**Validation**:
- Content type must be `audio/*` or `application/octet-stream`
- Size must be 1 byte to 25 MB
- Attempt must not be aborted

### Django Model

`SpeakingTurn` has:
- `audio_path`: `CharField(max_length=500, blank=True)`
- `duration_seconds`: `DecimalField(null=True)`
- `metadata`: `JSONField(default=dict)`

### Frontend Call

From `web/static/app.js:872-881`:
```javascript
const upload = await fetch(`/api/attempts/${attempt.id}/turns/${turn.id}/audio`, {
  method: "POST",
  headers: { "Content-Type": mimeType.split(";")[0] },
  body: blob,
});
```

## Requirements

### Endpoint

* `POST /api/attempts/{attempt_id}/turns/{turn_id}/audio`
* Must be authenticated (401 for unauthenticated)
* Owner-scoped: can only upload to own attempts
* Multipart upload support

### Request Validation

* Content-Type: `audio/*` or `application/octet-stream`
* Content-Length: 1 byte to 25 MB
* Attempt exists and belongs to user
* Turn exists within attempt
* Attempt status is not `aborted`

### Response Shape

Must match old server:
```json
{
  "ok": true,
  "audio": {
    "path": "...",
    "content_type": "...",
    "bytes": 12345,
    "duration_seconds": null,
    "url": "/api/audio/{attempt_id}/{turn_id}/candidate"
  }
}
```

### Storage

* Save to `media/audio/{attempt_id}_{turn_id}.{extension}`
* Extension from Content-Type via `mimetypes.guess_extension()`
* Update `SpeakingTurn.audio_path` with relative path
* Store content_type and bytes in `metadata`

### Audio Retrieval Endpoint

* `GET /api/audio/{attempt_id}/{turn_id}/candidate`
* Must be authenticated (401)
* Owner-scoped
* Serves file from `media/audio/`

## Acceptance Criteria

* [x] `POST /api/attempts/{id}/turns/{id}/audio` requires authentication
* [x] Owner-scoped: cannot upload to others' attempts
* [x] Invalid attempt/turn returns 404
* [x] Aborted attempt returns 400
* [x] Valid upload saves file and updates turn
* [x] Response shape matches old server
* [x] `GET /api/audio/{id}/{id}/candidate` serves uploaded file
* [x] Tests cover auth, validation, upload, retrieval

## Definition of Done

* [x] Django speaking tests pass (37 tests)
* [x] Frontend syntax check passes
* [x] manage.py check passes
* [x] No pending migrations
* [x] Old server remains available as backup

## Out of Scope (explicit)

* Azure Speech / transcript generation
* Turn complete logic
* Scoring
* Billing
* Real AI provider integration
* Frontend changes
* C++ changes

## Technical Approach

### Settings

Add to `backend_django/config/settings.py`:
```python
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR.parent / 'media'
```

### URLs

Add to `backend_django/config/urls.py`:
```python
path("api/attempts/<str:attempt_id>/turns/<str:turn_id>/audio", speaking_views.turn_audio_upload_view, name="turn-audio-upload"),
path("api/audio/<str:attempt_id>/<str:turn_id>/candidate", speaking_views.turn_audio_candidate_view, name="turn-audio-candidate"),
```

Plus media serving in development:
```python
from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

### Service Function

Add to `backend_django/apps/speaking/services.py`:
```python
def upload_turn_audio(user, attempt_id: str, turn_id: str, audio_file) -> dict:
    # Validate attempt/turn ownership
    # Validate content type and size
    # Save file to media/audio/
    # Update turn.audio_path and metadata
    # Return audio dict
```

### View

Add to `backend_django/apps/speaking/views.py`:
```python
@require_http_methods(["POST"])
def turn_audio_upload_view(request, attempt_id: str, turn_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    # Handle upload via service
```

## Technical Notes

### Files to Modify

- `backend_django/config/settings.py` - add MEDIA_ROOT, MEDIA_URL
- `backend_django/config/urls.py` - add routes + media serving
- `backend_django/apps/speaking/services.py` - add upload_turn_audio()
- `backend_django/apps/speaking/views.py` - add views
- `backend_django/apps/speaking/tests.py` - add tests

### Constants

- MAX_AUDIO_BYTES = 25 * 1024 * 1024 (from old server)
