from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from .exceptions import SpeakingError
from .models import SpeakingAttempt, SpeakingTurn
from .volcengine_asr import transcribe_audio as volcengine_transcribe_audio


MAX_AUDIO_BYTES = 25 * 1024 * 1024


def upload_turn_audio(user, attempt_id: str, turn_id: str, audio_file) -> dict[str, Any]:
    """Upload audio for a speaking turn."""
    attempt = SpeakingAttempt.objects.filter(user=user, attempt_id=attempt_id).first()
    if not attempt:
        raise SpeakingError("Attempt not found")
    if attempt.status == SpeakingAttempt.Status.ABORTED:
        raise SpeakingError("Aborted attempts cannot accept audio")

    turn = SpeakingTurn.objects.filter(attempt=attempt, turn_id=turn_id).first()
    if not turn:
        raise SpeakingError("Turn not found")

    content_type = getattr(audio_file, "content_type", "") or ""
    if not (content_type.startswith("audio/") or content_type == "application/octet-stream"):
        raise SpeakingError(f"Unsupported audio content type: {content_type}")

    audio_file.seek(0, 2)
    size = audio_file.tell()
    audio_file.seek(0)

    if size <= 0:
        raise SpeakingError("Audio upload is empty")
    if size > MAX_AUDIO_BYTES:
        raise SpeakingError("Audio upload exceeds 25 MB")

    extension = mimetypes.guess_extension(content_type) or ".webm"
    if extension == ".weba":
        extension = ".webm"

    media_root = Path(settings.MEDIA_ROOT)
    audio_dir = media_root / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{attempt_id}_{turn_id}{extension}"
    relative_path = f"audio/{filename}"
    full_path = media_root / relative_path

    with open(full_path, "wb") as dest:
        for chunk in audio_file.chunks():
            dest.write(chunk)

    turn.audio_path = relative_path
    turn.metadata["audio_content_type"] = content_type
    turn.metadata["audio_bytes"] = size
    turn.metadata["audio_uploaded_at"] = timezone.now().isoformat()
    turn.save(update_fields=["audio_path", "metadata"])

    return {
        "ok": True,
        "audio": {
            "path": str(full_path),
            "content_type": content_type,
            "bytes": size,
            "duration_seconds": None,
            "url": f"/api/audio/{attempt_id}/{turn_id}/candidate",
        },
    }


def transcribe_turn_audio_with_server_asr(turn: SpeakingTurn) -> dict[str, Any]:
    if not turn.audio_path:
        return {"ok": False, "status": "missing_audio", "transcript": "", "error": "No uploaded audio."}
    audio_path = Path(settings.MEDIA_ROOT) / turn.audio_path
    if not audio_path.exists():
        return {"ok": False, "status": "missing_audio", "transcript": "", "error": "Uploaded audio file not found."}
    return volcengine_transcribe_audio(audio_path)


def get_turn_audio_path(user, attempt_id: str, turn_id: str) -> Path | None:
    """Get the audio file path for a turn."""
    turn = (
        SpeakingTurn.objects
        .filter(attempt__user=user, attempt__attempt_id=attempt_id, turn_id=turn_id)
        .first()
    )
    if not turn or not turn.audio_path:
        return None
    return Path(settings.MEDIA_ROOT) / turn.audio_path
