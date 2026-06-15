"""Speaking AI provider configuration helpers."""

from __future__ import annotations

import os
import re

from django.conf import settings

SPEAKING_AI_DEFAULT_HTTP_MODEL = "gpt-5.4-mini"
SPEAKING_AI_CALL_MODE_CHAIN = "chain"
SPEAKING_AI_CALL_MODE_HTTP = "http"
SPEAKING_AI_CALL_MODE_CODEX = "codex"
SPEAKING_AI_CALL_MODE_FALLBACK = "fallback"
SPEAKING_AI_CALL_MODES = {
    SPEAKING_AI_CALL_MODE_CHAIN,
    SPEAKING_AI_CALL_MODE_HTTP,
    SPEAKING_AI_CALL_MODE_CODEX,
    SPEAKING_AI_CALL_MODE_FALLBACK,
}


def _setting_or_env(name: str, default: str = "") -> str:
    value = getattr(settings, name, None)
    if value is None:
        value = os.environ.get(name, default)
    return str(value or "").strip()


def _strip_inline_comment(value: str) -> str:
    """Drop a trailing ``# ...`` inline comment from a single-token .env value.

    Applied only to model-name reads. Secrets and URLs may legitimately contain
    ``#`` and must never be truncated by the generic reader.
    """
    text = str(value or "").strip()
    if "#" in text:
        text = text.split("#", 1)[0].strip()
    return text


def _float_setting_or_env(name: str, default: float) -> float:
    raw = _setting_or_env(name, "")
    if not raw:
        return default
    try:
        return max(0.5, float(raw))
    except (TypeError, ValueError):
        return default


def _speaking_ai_kind_key(kind: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(kind or "speaking").upper()).strip("_") or "SPEAKING"


def speaking_ai_call_mode(kind: str = "speaking") -> str:
    """Return the configurable speaking AI route."""
    key = _speaking_ai_kind_key(kind)
    raw = (
        _setting_or_env(f"SPEAKING_{key}_AI_CALL_MODE")
        or _setting_or_env("SPEAKING_AI_CALL_MODE")
        or SPEAKING_AI_CALL_MODE_CHAIN
    ).lower()
    return raw if raw in SPEAKING_AI_CALL_MODES else SPEAKING_AI_CALL_MODE_CHAIN


def speaking_ai_http_model(kind: str = "speaking") -> str:
    key = _speaking_ai_kind_key(kind)
    return _strip_inline_comment(
        _setting_or_env(f"SPEAKING_{key}_AI_MODEL")
        or _setting_or_env("SPEAKING_AI_MODEL")
        or _setting_or_env("AI_HTTP_PREFERRED_MODEL")
    ) or SPEAKING_AI_DEFAULT_HTTP_MODEL


def _mode_allows_http(kind: str) -> bool:
    return speaking_ai_call_mode(kind) in {SPEAKING_AI_CALL_MODE_CHAIN, SPEAKING_AI_CALL_MODE_HTTP}


def _mode_allows_codex(kind: str) -> bool:
    return speaking_ai_call_mode(kind) in {SPEAKING_AI_CALL_MODE_CHAIN, SPEAKING_AI_CALL_MODE_CODEX}


def _mode_is_fallback_only(kind: str) -> bool:
    return speaking_ai_call_mode(kind) == SPEAKING_AI_CALL_MODE_FALLBACK
