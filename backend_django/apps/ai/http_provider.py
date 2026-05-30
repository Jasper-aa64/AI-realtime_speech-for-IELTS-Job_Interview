from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings


DEFAULT_HTTP_TIMEOUT_SECONDS = 8.0
DEFAULT_HTTP_TEMPERATURE = 0.2


class HttpApiProviderError(RuntimeError):
    def __init__(self, message: str, *, error_code: str = "http_api_provider_failed"):
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class HttpApiProviderConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS

    @property
    def endpoint(self) -> str:
        if self.base_url.rstrip("/").endswith("/chat/completions"):
            return self.base_url.rstrip("/")
        return f"{self.base_url.rstrip('/')}/chat/completions"


@dataclass(frozen=True)
class HttpApiProviderResult:
    text: str
    usage: dict[str, Any] | None = None
    elapsed_seconds: float = 0.0
    model: str = ""
    provider: str = "http_api"
    metadata: dict[str, Any] = field(default_factory=dict)


def _setting_or_env(name: str, default: str = "") -> str:
    value = getattr(settings, name, None)
    if value is None:
        value = os.environ.get(name, default)
    return str(value or "").strip()


def _float_setting_or_env(name: str, default: float) -> float:
    raw = _setting_or_env(name, "")
    if not raw:
        return default
    try:
        return max(0.5, float(raw))
    except (TypeError, ValueError):
        return default


def load_http_api_provider_config() -> HttpApiProviderConfig:
    base_url = _setting_or_env("AI_HTTP_BASE_URL")
    api_key = _setting_or_env("AI_HTTP_API_KEY")
    model = _setting_or_env("AI_HTTP_MODEL")
    timeout = _float_setting_or_env("AI_HTTP_TIMEOUT_SECONDS", DEFAULT_HTTP_TIMEOUT_SECONDS)
    missing = [
        name
        for name, value in (
            ("AI_HTTP_BASE_URL", base_url),
            ("AI_HTTP_API_KEY", api_key),
            ("AI_HTTP_MODEL", model),
        )
        if not value
    ]
    if missing:
        raise HttpApiProviderError(
            f"HTTP AI provider is not configured: missing {', '.join(missing)}",
            error_code="http_api_provider_not_configured",
        )
    return HttpApiProviderConfig(base_url=base_url, api_key=api_key, model=model, timeout_seconds=timeout)


def _safe_error_detail(value: str, limit: int = 240, extra_secrets: tuple[str, ...] = ()) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    for secret_value in extra_secrets:
        if secret_value:
            text = text.replace(secret_value, "[redacted]")
    for secret_name in ("AI_HTTP_API_KEY", "OPENAI_API_KEY"):
        secret_value = _setting_or_env(secret_name)
        if secret_value:
            text = text.replace(secret_value, "[redacted]")
    return text[:limit]


class HttpApiProvider:
    """OpenAI-compatible Chat Completions client for low-latency AI calls."""

    provider_name = "http_api"

    def __init__(self, config: HttpApiProviderConfig | None = None):
        self.config = config or load_http_api_provider_config()

    def complete_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = DEFAULT_HTTP_TEMPERATURE,
        max_tokens: int = 120,
        timeout_seconds: float | None = None,
        stream: bool = True,
    ) -> HttpApiProviderResult:
        started = time.monotonic()
        body = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max(1, int(max_tokens or 1)),
            "stream": bool(stream),
        }
        if stream:
            body["stream_options"] = {"include_usage": True}
        request = urllib.request.Request(
            self.config.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream" if stream else "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds or self.config.timeout_seconds) as response:
                if stream:
                    text, usage = self._parse_stream_response(response)
                else:
                    text, usage = self._parse_json_response(response.read())
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - best effort diagnostic only
                detail = str(exc)
            raise HttpApiProviderError(
                f"HTTP AI provider returned {exc.code}: {_safe_error_detail(detail, extra_secrets=(self.config.api_key,))}",
                error_code="http_api_provider_http_error",
            ) from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            raise HttpApiProviderError(
                f"HTTP AI provider request failed: {_safe_error_detail(str(exc), extra_secrets=(self.config.api_key,))}",
                error_code="http_api_provider_request_failed",
            ) from exc

        clean_text = str(text or "").strip()
        if not clean_text:
            raise HttpApiProviderError("HTTP AI provider returned empty output", error_code="http_api_provider_empty_output")
        return HttpApiProviderResult(
            text=clean_text,
            usage=usage,
            elapsed_seconds=time.monotonic() - started,
            model=self.config.model,
            metadata={"stream": bool(stream), "endpoint_configured": True},
        )

    @staticmethod
    def _parse_stream_response(response: Any) -> tuple[str, dict[str, Any] | None]:
        parts: list[str] = []
        usage: dict[str, Any] | None = None
        data_lines: list[str] = []

        def flush_event() -> bool:
            nonlocal usage
            if not data_lines:
                return False
            payload_text = "\n".join(data_lines).strip()
            data_lines.clear()
            if payload_text == "[DONE]":
                return True
            try:
                payload = json.loads(payload_text)
            except ValueError:
                return False
            if isinstance(payload.get("error"), dict):
                error = payload["error"]
                message = error.get("message") if isinstance(error.get("message"), str) else "stream error"
                raise HttpApiProviderError(
                    f"HTTP AI provider stream error: {_safe_error_detail(message)}",
                    error_code="http_api_provider_stream_error",
                )
            if isinstance(payload.get("usage"), dict):
                usage = payload["usage"]
            choices = payload.get("choices")
            if not isinstance(choices, list) or not choices:
                return False
            choice = choices[0] if isinstance(choices[0], dict) else {}
            finish_reason = choice.get("finish_reason")
            if finish_reason in {"length", "content_filter"}:
                raise HttpApiProviderError(
                    f"HTTP AI provider stopped with finish_reason={finish_reason}",
                    error_code="http_api_provider_finish_reason",
                )
            delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
            content = delta.get("content")
            if isinstance(content, str):
                parts.append(content)
            return False

        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
            for normalized_line in line.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
                event_line = normalized_line.rstrip("\n")
                if not event_line:
                    if flush_event():
                        return "".join(parts), usage
                    continue
                if event_line.startswith(":"):
                    continue
                if event_line.startswith("data:"):
                    data_lines.append(event_line[len("data:") :].lstrip())
        flush_event()
        return "".join(parts), usage

    @staticmethod
    def _parse_json_response(raw_body: bytes) -> tuple[str, dict[str, Any] | None]:
        try:
            payload = json.loads(raw_body.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise HttpApiProviderError("HTTP AI provider returned invalid JSON", error_code="http_api_provider_invalid_json") from exc
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return "", usage
        message = choices[0].get("message") if isinstance(choices[0], dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        return str(content or ""), usage


__all__ = [
    "HttpApiProvider",
    "HttpApiProviderConfig",
    "HttpApiProviderError",
    "HttpApiProviderResult",
    "load_http_api_provider_config",
]
