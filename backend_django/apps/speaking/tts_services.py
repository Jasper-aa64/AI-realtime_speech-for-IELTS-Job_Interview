from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

from django.conf import settings


def tts_fallback(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    text = str(payload.get("text") or "").strip()
    if not text:
        return {"provider": "none", "status": "empty_text", "audio_url": None, "message": "No text to synthesize."}
    if payload.get("server_fallback") is True:
        role = str(payload.get("role") or "model")
        voice = str(payload.get("voice") or "en_female_sarah")
        cache_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()[:24]
        cache_key = str(payload.get("cache_key") or f"takeaway_{cache_hash}")
        return volcengine_tts(text, voice=voice, role=role, cache_key=cache_key)
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


def volcengine_tts(
    text: str,
    voice: str = "en_male_adam",
    role: str = "model",
    cache_key: str | None = None,
    *,
    retries: int = 0,
    timeout: float = 4.0,
) -> dict[str, Any]:
    """Generate TTS audio using VolcEngine API, with caching.

    The upstream is an unofficial endpoint that occasionally times out or throttles
    under a burst (e.g. synthesizing every band7 answer of a report at once), which
    used to leave a few turns with no audio and no retry. ``retries`` lets callers
    that care about completeness (the band7 model answers) try again before falling
    back; the default (0 retries, 4s) preserves the latency-sensitive examiner path.
    """
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
    cache_id = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    started = time.monotonic()

    if audio_path.exists():
        _log.info(
            "examiner_tts cache=hit role=%s cache_id=%s elapsed_ms=%d",
            safe_role,
            cache_id,
            int((time.monotonic() - started) * 1000),
        )
        return {
            "provider": "volcengine",
            "status": "cached",
            "audio_url": f"/api/tts-audio/{safe_role}/{audio_path.name}",
            "path": str(audio_path),
            "content_type": "audio/mpeg",
        }

    payload = json.dumps({"text": text, "speaker": voice, "language": "en"}).encode("utf-8")
    _log.info("examiner_tts cache=miss role=%s cache_id=%s", safe_role, cache_id)
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

    last_exc: Exception | None = None
    for attempt in range(max(0, retries) + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                data = json.loads(response.read().decode("utf-8"))
            encoded = data.get("audio", {}).get("data")
            if not encoded:
                raise ValueError(f"VolcEngine TTS returned no audio: {data}")  # noqa: TRY301
            audio_path.write_bytes(base64.b64decode(encoded))
            _log.info(
                "examiner_tts completed role=%s cache_id=%s elapsed_ms=%d",
                safe_role,
                cache_id,
                int((time.monotonic() - started) * 1000),
            )
            return {
                "provider": "volcengine",
                "status": "ready",
                "audio_url": f"/api/tts-audio/{safe_role}/{audio_path.name}",
                "path": str(audio_path),
                "content_type": "audio/mpeg",
            }
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < max(0, retries):
                time.sleep(0.4 * (attempt + 1))

    _log.warning(
        "examiner_tts failed role=%s cache_id=%s elapsed_ms=%d",
        safe_role,
        cache_id,
        int((time.monotonic() - started) * 1000),
    )
    return {
        "provider": "browser",
        "status": "fallback",
        "audio_url": None,
        "error": str(last_exc),
        "message": f"VolcEngine TTS unavailable; use browser fallback: {last_exc}",
    }


def tts_audio_path(role: str, filename: str) -> Path | None:
    safe_role = "examiner" if role == "examiner" else "model"
    safe_name = Path(str(filename or "")).name
    if not safe_name:
        return None
    path = Path(settings.MEDIA_ROOT) / "tts" / safe_role / safe_name
    return path if path.exists() else None


def stable_tts_audio_path(role: str, filename: str) -> tuple[Path | None, str]:
    """Return a browser-friendly playback file when a local transcoder is available."""
    source_path = tts_audio_path(role, filename)
    if not source_path:
        return None, "audio/mpeg"
    if source_path.suffix.lower() != ".mp3":
        return source_path, _audio_content_type(source_path)

    stable_path = source_path.with_suffix(".m4a")
    if stable_path.exists() and stable_path.stat().st_mtime >= source_path.stat().st_mtime:
        return stable_path, "audio/mp4"

    ffmpeg = shutil.which(str(getattr(settings, "VOLCENGINE_ASR_FFMPEG", "ffmpeg") or "ffmpeg")) or shutil.which("ffmpeg")
    if not ffmpeg:
        _log.warning(
            "tts_stable: ffmpeg not found — serving mp3 directly (no transcoder available). "
            "Install ffmpeg to enable m4a/AAC conversion for examiner audio."
        )
        return source_path, "audio/mpeg"

    try:
        subprocess.run(
            [
                ffmpeg,
                "-i", str(source_path),
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                "-y",
                str(stable_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("tts_stable: ffmpeg transcode failed (%s) — serving mp3 directly.", exc)
        return source_path, "audio/mpeg"

    if not stable_path.exists():
        _log.warning("tts_stable: ffmpeg ran but output missing — serving mp3 directly.")
        return source_path, "audio/mpeg"

    return stable_path, "audio/mp4"


def _audio_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".m4a":
        return "audio/mp4"
    if suffix == ".wav":
        return "audio/wav"
    return "audio/mpeg"
