from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings


DEFAULT_PROVIDER_MODE = "local_safe"
DEFAULT_REQUESTED_PROVIDER = "codex"
FALLBACK_PROVIDER = "fallback"
MOCK_SUCCESS_PROVIDER = "mock_success"

ADAPTER_KEY_FALLBACK = "fallback"
ADAPTER_KEY_MOCK_SUCCESS = "mock_success"
ADAPTER_KEY_UNSUPPORTED_TASK = "unsupported_task"

DEFAULT_PROVIDER_SECRET_ENV_NAMES = {
    "codex": ("CODEX_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "claude": ("ANTHROPIC_API_KEY",),
    MOCK_SUCCESS_PROVIDER: (),
    FALLBACK_PROVIDER: (),
}
PROVIDER_ENABLE_SETTING_NAMES = {
    "codex": "AI_PROVIDER_ENABLE_CODEX",
    "openai": "AI_PROVIDER_ENABLE_OPENAI",
    "claude": "AI_PROVIDER_ENABLE_CLAUDE",
}
FUTURE_REAL_PROVIDERS = frozenset(PROVIDER_ENABLE_SETTING_NAMES)


def normalize_provider_name(value: str | None) -> str:
    return str(value or "").strip().lower()


def _setting_text(name: str, default: str = "") -> str:
    return str(getattr(settings, name, default) or "").strip()


def _setting_bool(name: str, default: bool = False) -> bool:
    value = getattr(settings, name, default)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _secret_env_names() -> dict[str, tuple[str, ...]]:
    raw = getattr(settings, "AI_PROVIDER_SECRET_ENV_NAMES", DEFAULT_PROVIDER_SECRET_ENV_NAMES)
    secret_map: dict[str, tuple[str, ...]] = {}
    if isinstance(raw, dict):
        for provider, env_names in raw.items():
            names = env_names if isinstance(env_names, (list, tuple)) else [env_names]
            secret_map[normalize_provider_name(str(provider))] = tuple(
                sorted({str(name or "").strip() for name in names if str(name or "").strip()})
            )
    for provider, env_names in DEFAULT_PROVIDER_SECRET_ENV_NAMES.items():
        secret_map.setdefault(provider, tuple(env_names))
    return secret_map


@dataclass(frozen=True)
class AIProviderConfig:
    mode: str = DEFAULT_PROVIDER_MODE
    default_provider: str = DEFAULT_REQUESTED_PROVIDER
    allow_mock_success: bool = False
    enabled_providers: frozenset[str] = frozenset()
    provider_secret_env_names: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def is_known_provider(self, provider: str) -> bool:
        normalized = normalize_provider_name(provider)
        return normalized in FUTURE_REAL_PROVIDERS or normalized in {MOCK_SUCCESS_PROVIDER, FALLBACK_PROVIDER}

    def is_provider_enabled(self, provider: str) -> bool:
        normalized = normalize_provider_name(provider)
        if normalized == FALLBACK_PROVIDER:
            return True
        if normalized == MOCK_SUCCESS_PROVIDER:
            return self.allow_mock_success
        return normalized in self.enabled_providers

    def secret_env_names_for(self, provider: str) -> tuple[str, ...]:
        return self.provider_secret_env_names.get(normalize_provider_name(provider), ())


@dataclass(frozen=True)
class ProviderRoute:
    task_type: str
    requested_provider: str
    requested_model: str
    adapter_key: str
    effective_provider: str
    fallback_reason: str = ""
    error_code: str = ""
    config_mode: str = DEFAULT_PROVIDER_MODE


def load_provider_config() -> AIProviderConfig:
    enabled = {
        provider
        for provider, setting_name in PROVIDER_ENABLE_SETTING_NAMES.items()
        if _setting_bool(setting_name, default=(provider == DEFAULT_REQUESTED_PROVIDER))
    }
    default_provider = normalize_provider_name(_setting_text("AI_DEFAULT_PROVIDER", DEFAULT_REQUESTED_PROVIDER)) or DEFAULT_REQUESTED_PROVIDER
    return AIProviderConfig(
        mode=normalize_provider_name(_setting_text("AI_PROVIDER_MODE", DEFAULT_PROVIDER_MODE)) or DEFAULT_PROVIDER_MODE,
        default_provider=default_provider,
        allow_mock_success=_setting_bool("AI_ALLOW_MOCK_SUCCESS", default=False),
        enabled_providers=frozenset(enabled),
        provider_secret_env_names=_secret_env_names(),
    )


def default_provider_name(*, config: AIProviderConfig | None = None) -> str:
    return (config or load_provider_config()).default_provider


def resolve_provider_route(
    *,
    task_type: str,
    provider: str | None,
    model: str | None = "",
    config: AIProviderConfig | None = None,
) -> ProviderRoute:
    active_config = config or load_provider_config()
    normalized_task_type = str(task_type or "").strip().lower()
    requested_provider = normalize_provider_name(provider) or active_config.default_provider
    requested_model = str(model or "").strip()

    if normalized_task_type != "writing_score":
        return ProviderRoute(
            task_type=normalized_task_type,
            requested_provider=requested_provider,
            requested_model=requested_model,
            adapter_key=ADAPTER_KEY_UNSUPPORTED_TASK,
            effective_provider=FALLBACK_PROVIDER,
            fallback_reason=f"no provider runner registered for task_type={normalized_task_type or 'unknown'}",
            error_code="unsupported_task_type",
            config_mode=active_config.mode,
        )

    if requested_provider == MOCK_SUCCESS_PROVIDER:
        if active_config.allow_mock_success:
            return ProviderRoute(
                task_type=normalized_task_type,
                requested_provider=requested_provider,
                requested_model=requested_model,
                adapter_key=ADAPTER_KEY_MOCK_SUCCESS,
                effective_provider=MOCK_SUCCESS_PROVIDER,
                config_mode=active_config.mode,
            )
        return ProviderRoute(
            task_type=normalized_task_type,
            requested_provider=requested_provider,
            requested_model=requested_model,
            adapter_key=ADAPTER_KEY_FALLBACK,
            effective_provider=FALLBACK_PROVIDER,
            fallback_reason="mock success adapter is disabled by configuration; using local fallback",
            config_mode=active_config.mode,
        )

    if not active_config.is_known_provider(requested_provider):
        return ProviderRoute(
            task_type=normalized_task_type,
            requested_provider=requested_provider,
            requested_model=requested_model,
            adapter_key=ADAPTER_KEY_FALLBACK,
            effective_provider=FALLBACK_PROVIDER,
            fallback_reason="requested provider is not supported locally; using local fallback",
            config_mode=active_config.mode,
        )

    if not active_config.is_provider_enabled(requested_provider):
        return ProviderRoute(
            task_type=normalized_task_type,
            requested_provider=requested_provider,
            requested_model=requested_model,
            adapter_key=ADAPTER_KEY_FALLBACK,
            effective_provider=FALLBACK_PROVIDER,
            fallback_reason=f"{requested_provider} provider is disabled by configuration; using local fallback",
            config_mode=active_config.mode,
        )

    if requested_provider == active_config.default_provider:
        reason = "local fallback worker: real AI provider is not connected yet"
    else:
        reason = f"{requested_provider} provider adapter is not wired in {active_config.mode} mode; using local fallback"

    return ProviderRoute(
        task_type=normalized_task_type,
        requested_provider=requested_provider,
        requested_model=requested_model,
        adapter_key=ADAPTER_KEY_FALLBACK,
        effective_provider=FALLBACK_PROVIDER,
        fallback_reason=reason,
        config_mode=active_config.mode,
    )


__all__ = [
    "ADAPTER_KEY_FALLBACK",
    "ADAPTER_KEY_MOCK_SUCCESS",
    "ADAPTER_KEY_UNSUPPORTED_TASK",
    "AIProviderConfig",
    "DEFAULT_PROVIDER_MODE",
    "DEFAULT_REQUESTED_PROVIDER",
    "DEFAULT_PROVIDER_SECRET_ENV_NAMES",
    "FALLBACK_PROVIDER",
    "FUTURE_REAL_PROVIDERS",
    "MOCK_SUCCESS_PROVIDER",
    "PROVIDER_ENABLE_SETTING_NAMES",
    "ProviderRoute",
    "default_provider_name",
    "load_provider_config",
    "normalize_provider_name",
    "resolve_provider_route",
]
