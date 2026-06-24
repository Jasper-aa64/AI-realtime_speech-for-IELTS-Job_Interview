from __future__ import annotations

import sys
from typing import Any

from apps.ai.http_provider import HttpApiProvider, HttpApiProviderConfig

from .ai_config import (
    SPEAKING_AI_DEFAULT_HTTP_MODEL,
    _float_setting_or_env,
    _setting_or_env,
    speaking_ai_http_model,
)
from .runtime_utils import _safe_int
from .text_utils import clean_report_text


SPEAKING_CLAUDE_HTTP_DEFAULT_MODEL = "claude-sonnet-4-6"
SPEAKING_CLAUDE_HAIKU_HTTP_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
SPEAKING_CLAUDE_CLI_DEFAULT_MODEL = "sonnet"
SPEAKING_CLAUDE_CLI_HAIKU_MODEL = "haiku"

SPEAKING_CLAUDE_HTTP_SOURCES = frozenset({"claude", "claude_haiku"})
SPEAKING_CLAUDE_CLI_SOURCES = frozenset({"claude_cli", "claude_cli_haiku"})
SPEAKING_CODEX_CLI_SOURCES = frozenset({"codex_cli"})
SPEAKING_READY_AI_BACKENDS = frozenset({"codex", "codex_cli", "http_api", "claude_cli"})

# Reasoning-effort budget for the HTTP (sonnet) path. Thinking models are slow at
# full effort, so interactive calls (follow-ups) run "low"; only the heavier report
# generation gets "medium". Both overridable via env.
SPEAKING_HTTP_REASONING_EFFORT_DEFAULT = "low"
SPEAKING_HTTP_REPORT_REASONING_EFFORT = "medium"


def _reasoning_effort_for(kind: str) -> str:
    if str(kind or "").strip().lower() == "report":
        return _setting_or_env("AI_HTTP_REPORT_REASONING_EFFORT") or SPEAKING_HTTP_REPORT_REASONING_EFFORT
    return _setting_or_env("AI_HTTP_REASONING_EFFORT") or SPEAKING_HTTP_REASONING_EFFORT_DEFAULT


def _facade_attr(name: str, default: Any) -> Any:
    facade = sys.modules.get("apps.speaking.services")
    if facade is not None and hasattr(facade, name):
        return getattr(facade, name)
    return default


def _is_claude_http_source(ai_source: str) -> bool:
    return ai_source in SPEAKING_CLAUDE_HTTP_SOURCES


def _is_claude_cli_source(ai_source: str) -> bool:
    return ai_source in SPEAKING_CLAUDE_CLI_SOURCES


def _is_codex_cli_source(ai_source: str) -> bool:
    return ai_source in SPEAKING_CODEX_CLI_SOURCES


def _is_slow_cli_source(ai_source: str) -> bool:
    return _is_claude_cli_source(ai_source) or _is_codex_cli_source(ai_source)


def _claude_cli_model_for(ai_source: str) -> str:
    return SPEAKING_CLAUDE_CLI_HAIKU_MODEL if ai_source == "claude_cli_haiku" else SPEAKING_CLAUDE_CLI_DEFAULT_MODEL


def _speaking_http_provider(
    kind: str = "speaking",
    timeout_seconds: float | None = None,
    ai_source: str = "",
) -> Any:
    """Build the OpenAI-compatible HTTP provider for a speaking AI call."""
    if _is_claude_http_source(ai_source):
        base_url = _setting_or_env("SPEAKING_CLAUDE_HTTP_BASE_URL") or _setting_or_env("AI_HTTP_BASE_URL")
        api_key = _setting_or_env("SPEAKING_CLAUDE_HTTP_API_KEY")
        if ai_source == "claude_haiku":
            model = _setting_or_env("SPEAKING_CLAUDE_HAIKU_HTTP_MODEL") or SPEAKING_CLAUDE_HAIKU_HTTP_DEFAULT_MODEL
        else:
            model = _setting_or_env("SPEAKING_CLAUDE_HTTP_MODEL") or SPEAKING_CLAUDE_HTTP_DEFAULT_MODEL
        missing = [
            name
            for name, value in (("SPEAKING_CLAUDE_HTTP_BASE_URL", base_url), ("SPEAKING_CLAUDE_HTTP_API_KEY", api_key))
            if not value
        ]
        if missing:
            raise RuntimeError(f"Claude HTTP provider is not configured: missing {', '.join(missing)}")
    else:
        base_url = _setting_or_env("AI_HTTP_BASE_URL")
        api_key = _setting_or_env("AI_HTTP_API_KEY")
        model = speaking_ai_http_model(kind)
        missing = [name for name, value in (("AI_HTTP_BASE_URL", base_url), ("AI_HTTP_API_KEY", api_key)) if not value]
        if missing:
            raise RuntimeError(f"HTTP speaking AI provider is not configured: missing {', '.join(missing)}")
    timeout = timeout_seconds or _float_setting_or_env("AI_HTTP_TIMEOUT_SECONDS", 8.0)
    provider_cls = _facade_attr("HttpApiProvider", HttpApiProvider)
    config_cls = _facade_attr("HttpApiProviderConfig", HttpApiProviderConfig)
    return provider_cls(
        config_cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout,
            reasoning_effort=_reasoning_effort_for(kind),
        )
    )


def _raise_report_provider_chain_error(
    *,
    http_error: Exception | None = None,
    codex_error: Exception | None = None,
    claude_error: Exception | None = None,
    fallback_message: str,
) -> None:
    """Raise the most useful report-provider error instead of masking HTTP failures."""
    codex_text = str(codex_error or "")
    if http_error and ("codex CLI not found" in codex_text or not codex_error):
        raise RuntimeError(str(http_error)) from http_error
    if codex_error:
        raise RuntimeError(str(codex_error)) from codex_error
    if http_error:
        raise RuntimeError(str(http_error)) from http_error
    if claude_error:
        raise RuntimeError(str(claude_error)) from claude_error
    raise RuntimeError(fallback_message)


def _http_backend_name(stream: bool = False) -> str:
    return "http_api_stream" if stream else "http_api"


def _follow_up_generation_provenance(result: dict[str, Any]) -> dict[str, Any]:
    provenance: dict[str, Any] = {}
    for key in ("provider", "model"):
        # Provider/model are machine metadata, not user-facing model output. The
        # report sanitizer deliberately removes words such as "codex", which used
        # to erase valid provenance from follow-up turns after the module split.
        value = str(result.get(key) or "").strip()[:120]
        if value:
            provenance[key] = value
    usage = result.get("usage")
    if isinstance(usage, dict) and usage:
        provenance["usage"] = usage
    latency_ms = result.get("latency_ms")
    if latency_ms not in (None, ""):
        provenance["latency_ms"] = _safe_int(latency_ms)
    return provenance


__all__ = [
    "SPEAKING_AI_DEFAULT_HTTP_MODEL",
    "SPEAKING_CLAUDE_HTTP_DEFAULT_MODEL",
    "SPEAKING_CLAUDE_HAIKU_HTTP_DEFAULT_MODEL",
    "SPEAKING_CLAUDE_CLI_DEFAULT_MODEL",
    "SPEAKING_CLAUDE_CLI_HAIKU_MODEL",
    "SPEAKING_CLAUDE_HTTP_SOURCES",
    "SPEAKING_CLAUDE_CLI_SOURCES",
    "SPEAKING_CODEX_CLI_SOURCES",
    "SPEAKING_READY_AI_BACKENDS",
    "SPEAKING_HTTP_REASONING_EFFORT_DEFAULT",
    "SPEAKING_HTTP_REPORT_REASONING_EFFORT",
    "_reasoning_effort_for",
    "_is_claude_http_source",
    "_is_claude_cli_source",
    "_is_codex_cli_source",
    "_is_slow_cli_source",
    "_claude_cli_model_for",
    "_speaking_http_provider",
    "_raise_report_provider_chain_error",
    "_http_backend_name",
    "_follow_up_generation_provenance",
]
