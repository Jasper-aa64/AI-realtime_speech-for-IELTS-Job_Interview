from __future__ import annotations

import base64
import json
import os
import re
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from django.conf import settings


def tts_fallback(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    text = str(payload.get("text") or "").strip()
    if not text:
        return {"provider": "none", "status": "empty_text", "audio_url": None, "message": "No text to synthesize."}
    return {
        "provider": "browser",
        "status": "fallback",
        "audio_url": None,
        "message": "Server TTS provider is not configured; use browser fallback.",
    }


def _safe_slug(value: str) -> str:
    """Convert string to safe filename slug."""
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")[:96] or "audio"


def cached_tts_url(role: str, cache_key: str) -> str | None:
    safe_role = "examiner" if role == "examiner" else "model"
    audio_path = Path(settings.MEDIA_ROOT) / "tts" / safe_role / f"{_safe_slug(cache_key)}.mp3"
    if not audio_path.exists():
        return None
    return f"/api/tts-audio/{safe_role}/{audio_path.name}"


def volcengine_tts(text: str, voice: str = "en_male_adam", role: str = "model", cache_key: str | None = None) -> dict[str, Any]:
    """Generate TTS audio using VolcEngine API, with caching."""
    text = text.strip()
    if not text:
        return {"provider": "none", "status": "empty_text", "audio_url": None, "message": "No text to synthesize."}

    if os.environ.get("IELTS_WEB_DISABLE_VOLCENGINE_TTS") == "1":
        return {"provider": "browser", "status": "fallback", "audio_url": None, "message": "VolcEngine TTS disabled; use browser fallback."}

    safe_role = "examiner" if role == "examiner" else "model"
    folder = Path(settings.MEDIA_ROOT) / "tts" / safe_role
    folder.mkdir(parents=True, exist_ok=True)

    key = _safe_slug(cache_key or f"{role}_{uuid.uuid4().hex}")
    audio_path = folder / f"{key}.mp3"

    if audio_path.exists():
        return {
            "provider": "volcengine",
            "status": "cached",
            "audio_url": f"/api/tts-audio/{safe_role}/{audio_path.name}",
            "path": str(audio_path),
            "content_type": "audio/mpeg",
        }

    payload = json.dumps({"text": text, "speaker": voice, "language": "en"}).encode("utf-8")
    request = urllib.request.Request(
        "https://translate.volcengine.com/crx/tts/v1/",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": "chrome-extension://klgfhbdadaspgppeadghjjemk",
            "User-Agent": "Mozilla/5.0",
            "Cookie": "hasUserBehavior=1",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=4) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
        encoded = data.get("audio", {}).get("data")
        if not encoded:
            raise ValueError(f"VolcEngine TTS returned no audio: {data}")  # noqa: TRY301
        audio_path.write_bytes(base64.b64decode(encoded))
        return {
            "provider": "volcengine",
            "status": "ready",
            "audio_url": f"/api/tts-audio/{safe_role}/{audio_path.name}",
            "path": str(audio_path),
            "content_type": "audio/mpeg",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "provider": "browser",
            "status": "fallback",
            "audio_url": None,
            "error": str(exc),
            "message": f"VolcEngine TTS unavailable; use browser fallback: {exc}",
        }


def tts_audio_path(role: str, filename: str) -> Path | None:
    safe_role = "examiner" if role == "examiner" else "model"
    safe_name = Path(str(filename or "")).name
    if not safe_name:
        return None
    path = Path(settings.MEDIA_ROOT) / "tts" / safe_role / safe_name
    return path if path.exists() else None
