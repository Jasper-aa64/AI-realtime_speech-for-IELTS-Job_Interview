"""CLI runtime helpers for speaking AI providers.

This module owns subprocess calls to Codex and Claude CLI. `services.py` imports
and re-exports these helpers to preserve the existing public import surface.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.ai.cli_paths import resolve_claude_cli_path
from .text_utils import extract_codex_json_events


CODEX_REASONING_EFFORT = "low"


def run_codex(prompt: str, call_id: str, timeout: int = 45) -> tuple[str, dict[str, Any] | None]:
    """Call codex CLI and return output and usage.

    The `-` argument is required to make codex exec read from stdin.
    Without it, the model receives 0 tokens and outputs only thread/turn events.

    Raises RuntimeError if the model did not actually process the prompt
    (detected by 0 input tokens, empty output, or event stream without real content).
    """
    if os.environ.get("IELTS_WEB_DISABLE_CODEX") == "1":
        raise RuntimeError("codex disabled by IELTS_WEB_DISABLE_CODEX=1")

    codex = shutil.which("codex") or "/opt/homebrew/bin/codex"
    if not shutil.which(codex) and not Path(codex).exists():
        raise RuntimeError("codex CLI not found")

    config_args = ["-c", f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"']
    codex_cwd = str(Path(settings.BASE_DIR).parent)
    last_error: RuntimeError | None = None
    for _attempt in range(2):
        try:
            result = subprocess.run(
                [codex, "exec", "--json", *config_args, "-"],
                input=prompt,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout,
                check=True,
                cwd=codex_cwd,
            )
            output, usage, has_real_content = extract_codex_json_events(result.stdout)
        except subprocess.TimeoutExpired:
            last_error = RuntimeError(f"codex timed out after {timeout}s for {call_id}")
            continue
        except Exception:
            result = subprocess.run(
                [codex, "exec", *config_args, "-"],
                input=prompt,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout,
                check=True,
                cwd=codex_cwd,
            )
            output, usage, has_real_content = result.stdout, None, bool(result.stdout.strip())

        if usage:
            input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
            if input_tokens == 0:
                last_error = RuntimeError(f"codex returned 0 input tokens for {call_id}: model did not process the prompt")
                continue

        if not output or not output.strip():
            last_error = RuntimeError(f"codex returned empty output for {call_id}")
            continue

        if not has_real_content:
            last_error = RuntimeError(f"codex returned only event stream without model output for {call_id}")
            continue

        return output, usage

    raise last_error or RuntimeError(f"codex returned no usable output for {call_id}")


CLAUDE_CLI_QUOTA_PHRASES = ("limit reached", "quota", "rate limit", "overloaded", "capacity")


def _claude_cli_usage_payload(raw_usage: dict[str, Any]) -> dict[str, Any]:
    input_tokens = int(raw_usage.get("input_tokens") or 0)
    cache_creation_input_tokens = int(raw_usage.get("cache_creation_input_tokens") or 0)
    cache_read_input_tokens = int(raw_usage.get("cache_read_input_tokens") or 0)
    output_tokens = int(raw_usage.get("output_tokens") or 0)
    return {
        **raw_usage,
        "input_tokens": input_tokens + cache_creation_input_tokens + cache_read_input_tokens,
        "cached_input_tokens": cache_read_input_tokens,
        "output_tokens": output_tokens,
        "provider": "claude_cli",
    }


class ClaudeCliQuotaError(RuntimeError):
    """Raised when Claude CLI reports quota/rate-limit exhaustion."""


def run_claude_cli(prompt: str, call_id: str, timeout: int = 180) -> tuple[str, dict[str, Any] | None]:
    """Call Claude CLI with -p and return (text_output, usage_dict).

    Uses --output-format json so we get structured output including api_error_status.
    Raises ClaudeCliQuotaError on detected quota exhaustion.
    Raises RuntimeError on other failures.
    """
    cli = resolve_claude_cli_path()
    if not (shutil.which(cli) or Path(cli).exists()):
        raise RuntimeError(f"claude CLI not found at {cli}")

    try:
        # Feed the prompt over stdin, NOT as a -p argv value. On Windows `claude`
        # resolves to claude.CMD (a batch wrapper); a long multi-line report prompt
        # passed as a command-line argument gets mangled/truncated by cmd.exe, so
        # Claude receives an empty/garbled message and replies "No speaking response
        # was included" -- which then fails JSON extraction and silently falls back to
        # codex. stdin sidesteps both the length limit and the argv mangling.
        result = subprocess.run(
            [cli, "-p", "--output-format", "json"],
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude CLI timed out after {timeout}s for {call_id}")
    except Exception as exc:
        raise RuntimeError(f"claude CLI subprocess error for {call_id}: {exc}") from exc

    raw_stdout = (result.stdout or "").strip()
    raw_stderr = (result.stderr or "").strip()

    combined_err = (raw_stderr + " " + raw_stdout).lower()
    if any(phrase in combined_err for phrase in CLAUDE_CLI_QUOTA_PHRASES):
        raise ClaudeCliQuotaError(
            f"Claude CLI quota exhausted for {call_id}: {raw_stderr[:200] or raw_stdout[:200]}"
        )

    try:
        parsed = json.loads(raw_stdout)
    except json.JSONDecodeError:
        if raw_stdout:
            return raw_stdout, None
        raise RuntimeError(
            f"claude CLI returned empty output for {call_id}. stderr: {raw_stderr[:300]}"
        )

    api_error = parsed.get("api_error_status")
    if api_error:
        err_str = str(api_error).lower()
        if any(phrase in err_str for phrase in CLAUDE_CLI_QUOTA_PHRASES):
            message = str(parsed.get("result") or api_error).strip()
            raise ClaudeCliQuotaError(f"Claude CLI quota exhausted for {call_id}: {message}")
        message = str(parsed.get("result") or api_error).strip()
        raise RuntimeError(f"Claude CLI error for {call_id}: {message}")

    if parsed.get("is_error"):
        message = str(parsed.get("result") or "Claude CLI reported an error").strip()
        raise RuntimeError(f"Claude CLI error for {call_id}: {message}")

    text = str(parsed.get("result") or "").strip()
    if not text:
        raise RuntimeError(f"Claude CLI returned empty result for {call_id}")

    raw_usage = parsed.get("usage") or {}
    usage: dict[str, Any] | None = None
    if raw_usage:
        usage = _claude_cli_usage_payload({**raw_usage, "total_cost_usd": parsed.get("total_cost_usd")})

    return text, usage
