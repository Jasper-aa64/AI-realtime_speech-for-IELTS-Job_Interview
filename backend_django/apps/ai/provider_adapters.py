from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.ai.cli_paths import resolve_claude_cli_path
from apps.ai.models import AITask
from apps.ai.http_provider import HttpApiProvider, HttpApiProviderError
from apps.ai.provider_config import (
    ADAPTER_KEY_CLAUDE_WRITING_SCORE,
    ADAPTER_KEY_CODEX_SPEAKING_REPORT,
    ADAPTER_KEY_CODEX_WRITING_SCORE,
    ADAPTER_KEY_FALLBACK,
    ADAPTER_KEY_HTTP_WRITING_SCORE,
    ADAPTER_KEY_MOCK_SUCCESS,
    FALLBACK_PROVIDER,
    MOCK_SUCCESS_PROVIDER,
    ProviderRoute,
    resolve_provider_route,
)
from apps.ai.orchestration import fail_billable_ai_task, fallback_billable_ai_task
from apps.ai.services import fail_ai_task, succeed_ai_task
from apps.writing.services import WritingEntryDeleted, complete_score_task, fallback_score_task


DEFAULT_FALLBACK_REASON = "local fallback worker: real AI provider is not connected yet"
SUMMARY_STATUS_SKIPPED = "skipped"
CODEX_REASONING_EFFORT = "medium"
RETRYABLE_PROVIDER_ERROR_CODES = {
    "http_api_provider_http_error",
    "http_api_provider_request_failed",
}
RETRYABLE_HTTP_PROVIDER_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


class ProviderRunOutcome:
    SUCCESS = "success"
    FALLBACK = "fallback"
    RETRYABLE_FAILURE = "retryable_failure"
    TERMINAL_FAILURE = "terminal_failure"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ProviderRunResult:
    outcome: str
    result_payload: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    error_code: str = ""
    error_message: str = ""
    retry_delay_seconds: int = 60
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(
        cls,
        result_payload: dict[str, Any] | None = None,
        *,
        usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ProviderRunResult":
        return cls(
            outcome=ProviderRunOutcome.SUCCESS,
            result_payload=result_payload or {},
            usage=usage or {},
            metadata=metadata or {},
        )

    @classmethod
    def fallback(
        cls,
        reason: str,
        result_payload: dict[str, Any] | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> "ProviderRunResult":
        return cls(
            outcome=ProviderRunOutcome.FALLBACK,
            reason=str(reason or "").strip(),
            result_payload=result_payload or {},
            metadata=metadata or {},
        )

    @classmethod
    def retryable_failure(
        cls,
        error_message: str,
        *,
        error_code: str = "",
        retry_delay_seconds: int = 60,
        metadata: dict[str, Any] | None = None,
    ) -> "ProviderRunResult":
        return cls(
            outcome=ProviderRunOutcome.RETRYABLE_FAILURE,
            error_message=str(error_message or "").strip(),
            error_code=str(error_code or "").strip(),
            retry_delay_seconds=max(1, int(retry_delay_seconds or 1)),
            metadata=metadata or {},
        )

    @classmethod
    def terminal_failure(
        cls,
        error_message: str,
        *,
        error_code: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "ProviderRunResult":
        return cls(
            outcome=ProviderRunOutcome.TERMINAL_FAILURE,
            error_message=str(error_message or "").strip(),
            error_code=str(error_code or "").strip(),
            metadata=metadata or {},
        )

    @classmethod
    def skipped(
        cls,
        reason: str,
        *,
        error_code: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "ProviderRunResult":
        return cls(
            outcome=ProviderRunOutcome.SKIPPED,
            reason=str(reason or "").strip(),
            error_code=str(error_code or "").strip(),
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class AppliedProviderRunResult:
    task: AITask
    summary_status: str


class ProviderExecutionError(RuntimeError):
    def __init__(self, message: str, *, error_code: str = "provider_runner_failed"):
        super().__init__(message)
        self.error_code = error_code


class AIProvider:
    """Strategy interface for durable AI task providers."""

    adapter_name = "base"

    def run(self, task: AITask) -> ProviderRunResult:
        raise NotImplementedError


class BaseProviderAdapter(AIProvider):
    adapter_name = "base"

    def __init__(self, route: ProviderRoute | None = None):
        self.route = route


class FallbackWritingScoreAdapter(BaseProviderAdapter):
    adapter_name = "writing_score_fallback"

    def run(self, task: AITask) -> ProviderRunResult:
        return ProviderRunResult.fallback(
            self.route.fallback_reason if self.route else DEFAULT_FALLBACK_REASON,
            metadata=_route_metadata(self.adapter_name, self.route),
        )


def _run_subprocess_with_tree_kill(
    args: list[str],
    *,
    input: str | None = None,
    timeout: int,
    text: bool = True,
    encoding: str = "utf-8",
    errors: str = "replace",
    cwd: str | None = None,
    env: dict | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """subprocess.run replacement that kills the full process tree on Windows.

    On Windows, subprocess.run(timeout=...) can hang forever after proc.kill()
    because child processes (e.g. Node.js workers spawned by Claude/Codex CLI)
    keep the stdout/stderr pipes open. This helper uses taskkill /F /T to
    terminate the entire process tree, releasing the pipes before communicating.
    """
    input_bytes: bytes | None = None
    if input is not None:
        input_bytes = input.encode(encoding, errors=errors) if isinstance(input, str) else input

    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
    try:
        stdout_bytes, stderr_bytes = proc.communicate(input=input_bytes, timeout=timeout)
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            # /F = force, /T = include child tree, /PID = target by process id
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=10,
            )
        else:
            proc.kill()
        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout_bytes, stderr_bytes = b"", b""
        raise subprocess.TimeoutExpired(args, timeout, output=stdout_bytes, stderr=stderr_bytes)

    stdout = stdout_bytes.decode(encoding, errors=errors) if stdout_bytes else ""
    stderr = stderr_bytes.decode(encoding, errors=errors) if stderr_bytes else ""
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, args, stdout, stderr)
    return subprocess.CompletedProcess(args=args, returncode=proc.returncode, stdout=stdout, stderr=stderr)


def extract_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    raw = str(text or "")
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(raw[index:])
        except ValueError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("model output did not contain a JSON object")


def extract_codex_json_events(stdout: str) -> tuple[str, dict[str, Any] | None, bool]:
    events: list[dict[str, Any]] = []
    for line in str(stdout or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            event = json.loads(stripped)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)

    usage = None
    final_text = ""
    has_real_content = False
    for event in events:
        if isinstance(event.get("usage"), dict):
            usage = event["usage"]
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]

        if event.get("type") == "item.completed":
            item = event.get("item") if isinstance(event.get("item"), dict) else {}
            if item.get("type") == "agent_message":
                for content_item in item.get("content") or []:
                    if isinstance(content_item, dict) and content_item.get("type") == "text" and str(content_item.get("text") or "").strip():
                        final_text = str(content_item["text"])
                        has_real_content = True

        message = event.get("message") or event.get("item") or event.get("response")
        if isinstance(message, dict):
            content = message.get("content") or message.get("text")
            if isinstance(content, str) and content.strip():
                final_text = content
                has_real_content = True
            elif isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        value = part.get("text") or part.get("content")
                        if isinstance(value, str) and value.strip():
                            parts.append(value)
                    elif isinstance(part, str) and part.strip():
                        parts.append(part)
                if parts:
                    final_text = "\n".join(parts)
                    has_real_content = True
        elif isinstance(event.get("content"), str) and event["content"].strip():
            final_text = event["content"]
            has_real_content = True

    if not events:
        return str(stdout or ""), None, False
    return final_text or str(stdout or ""), usage, has_real_content


class CodexCliClient:
    """Adapter around the local Codex CLI JSON event stream."""

    def __init__(self, *, executable: str | None = None, cwd: str | None = None):
        self.executable = executable
        self.cwd = cwd

    def run(self, prompt: str, call_id: str, timeout: int = 120, max_attempts: int = 2) -> tuple[str, dict[str, Any] | None]:
        if os.environ.get("IELTS_WEB_DISABLE_CODEX") == "1":
            raise RuntimeError("codex disabled by IELTS_WEB_DISABLE_CODEX=1")

        codex = self.executable or shutil.which("codex") or "/opt/homebrew/bin/codex"
        if not shutil.which(codex) and not Path(codex).exists():
            raise RuntimeError("codex CLI not found")

        config_args = ["-c", f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"']
        cwd = self.cwd or str(Path(settings.BASE_DIR).parent)
        # Ensure node is findable: the AI worker may run with a minimal PATH
        # (/usr/bin:/bin only), but codex is a Node.js script whose shebang
        # needs 'node' on PATH.  Prepend homebrew + /usr/local/bin so
        # #!/usr/bin/env node resolves even without a full shell environment.
        _sub_env = os.environ.copy()
        _extra_paths = ["/opt/homebrew/bin", "/usr/local/bin"]
        _cur_path = _sub_env.get("PATH", "")
        _additions = ":".join(p for p in _extra_paths if p not in _cur_path.split(":"))
        if _additions:
            _sub_env["PATH"] = _additions + (":" + _cur_path if _cur_path else "")
        last_error: RuntimeError | None = None
        for _attempt in range(max(1, int(max_attempts or 1))):
            try:
                result = _run_subprocess_with_tree_kill(
                    [codex, "exec", "--json", *config_args, "-"],
                    input=prompt,
                    timeout=timeout,
                    check=True,
                    cwd=cwd,
                    env=_sub_env,
                )
                output, usage, has_real_content = extract_codex_json_events(result.stdout)
            except subprocess.TimeoutExpired:
                last_error = RuntimeError(f"codex timed out after {timeout}s for {call_id}")
                continue
            except Exception as exc:
                last_error = RuntimeError(f"codex failed for {call_id}: {exc}")
                continue

            if usage:
                input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
                if input_tokens == 0:
                    last_error = RuntimeError(f"codex returned 0 input tokens for {call_id}")
                    continue
            if not output or not output.strip():
                last_error = RuntimeError(f"codex returned empty output for {call_id}")
                continue
            if not has_real_content:
                last_error = RuntimeError(f"codex returned only event stream for {call_id}")
                continue
            return output, usage
        raise last_error or RuntimeError(f"codex returned no usable output for {call_id}")


_DEFAULT_CODEX_CLIENT = CodexCliClient()


def run_codex(prompt: str, call_id: str, timeout: int = 120, max_attempts: int = 2) -> tuple[str, dict[str, Any] | None]:
    return _DEFAULT_CODEX_CLIENT.run(prompt, call_id, timeout=timeout, max_attempts=max_attempts)


CLAUDE_CLI_QUOTA_PHRASES = ("limit reached", "quota", "rate limit", "overloaded", "capacity")


def _claude_usage_payload(raw_usage: dict[str, Any], *, model: str) -> dict[str, Any]:
    input_tokens = int(raw_usage.get("input_tokens") or 0)
    cache_creation_input_tokens = int(raw_usage.get("cache_creation_input_tokens") or 0)
    cache_read_input_tokens = int(raw_usage.get("cache_read_input_tokens") or 0)
    output_tokens = int(raw_usage.get("output_tokens") or 0)
    return {
        **raw_usage,
        "input_tokens": input_tokens + cache_creation_input_tokens + cache_read_input_tokens,
        "cached_input_tokens": cache_read_input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": raw_usage.get("total_cost_usd"),
        "provider": "claude",
        "model": model,
    }


class ClaudeCliClient:
    """Adapter around the local Claude Code CLI in headless JSON mode.

    Uses the machine's logged-in Claude session (subscription), so no
    ANTHROPIC_API_KEY is needed. The prompt is fed via stdin to sidestep
    command-line length limits on long writing prompts. On Windows the CLI
    resolves to claude.cmd / claude.exe via shutil.which.
    """

    def __init__(self, *, executable: str | None = None, model: str | None = None):
        self.executable = executable
        self.model = model or os.environ.get("CLAUDE_CLI_MODEL") or "sonnet"

    def run(self, prompt: str, call_id: str, timeout: int = 180, max_attempts: int = 2) -> tuple[str, dict[str, Any] | None]:
        if os.environ.get("IELTS_WEB_DISABLE_CLAUDE") == "1":
            raise RuntimeError("claude disabled by IELTS_WEB_DISABLE_CLAUDE=1")

        claude = resolve_claude_cli_path(self.executable)
        if not shutil.which(claude) and not Path(claude).exists():
            raise RuntimeError(f"claude CLI not found at {claude}")

        last_error: RuntimeError | None = None
        for _attempt in range(max(1, int(max_attempts or 1))):
            try:
                result = _run_subprocess_with_tree_kill(
                    [claude, "-p", "--output-format", "json", "--model", self.model],
                    input=prompt,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                last_error = RuntimeError(f"claude CLI timed out after {timeout}s for {call_id}")
                continue
            except Exception as exc:
                last_error = RuntimeError(f"claude CLI subprocess error for {call_id}: {exc}")
                continue

            raw_stdout = (result.stdout or "").strip()
            raw_stderr = (result.stderr or "").strip()

            combined_err = (raw_stderr + " " + raw_stdout).lower()
            if any(phrase in combined_err for phrase in CLAUDE_CLI_QUOTA_PHRASES):
                last_error = RuntimeError(
                    f"claude CLI quota exhausted for {call_id}: {raw_stderr[:200] or raw_stdout[:200]}"
                )
                continue

            try:
                parsed = json.loads(raw_stdout)
            except json.JSONDecodeError:
                if raw_stdout:
                    # Plain-text output (non-JSON) — still usable, no usage data.
                    return raw_stdout, None
                last_error = RuntimeError(
                    f"claude CLI returned empty output for {call_id}. stderr: {raw_stderr[:300]}"
                )
                continue

            api_error = parsed.get("api_error_status")
            if api_error:
                message = str(parsed.get("result") or api_error).strip()
                last_error = RuntimeError(f"Claude CLI error for {call_id}: {message}")
                continue
            if parsed.get("is_error"):
                message = str(parsed.get("result") or "Claude CLI reported an error").strip()
                last_error = RuntimeError(f"Claude CLI error for {call_id}: {message}")
                continue

            text = str(parsed.get("result") or "").strip()
            if not text:
                last_error = RuntimeError(f"claude CLI returned empty result for {call_id}")
                continue

            raw_usage = parsed.get("usage") or {}
            usage: dict[str, Any] | None = None
            if raw_usage:
                usage = _claude_usage_payload(
                    {**raw_usage, "total_cost_usd": parsed.get("total_cost_usd")},
                    model=self.model,
                )
            return text, usage

        raise last_error or RuntimeError(f"claude CLI returned no usable output for {call_id}")


_DEFAULT_CLAUDE_CLIENT = ClaudeCliClient()


def run_claude(prompt: str, call_id: str, timeout: int = 180, max_attempts: int = 2) -> tuple[str, dict[str, Any] | None]:
    return _DEFAULT_CLAUDE_CLIENT.run(prompt, call_id, timeout=timeout, max_attempts=max_attempts)


class AiTaskTemplate(BaseProviderAdapter):
    """Template Method for provider-backed durable AI task execution."""

    failure_error_code = "provider_runner_failed"

    def run(self, task: AITask) -> ProviderRunResult:
        request_payload = task.request_payload if isinstance(task.request_payload, dict) else {}
        try:
            provider_payload, usage = self._execute_provider(task, request_payload)
            result_payload = self._parse_payload(provider_payload, request_payload, task)
        except Exception as exc:
            return self._on_failure(exc, task, request_payload)
        return ProviderRunResult.success(
            result_payload,
            usage=usage or {},
            metadata=_route_metadata(self.adapter_name, self.route),
        )

    def _execute_provider(self, task: AITask, request_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        raise NotImplementedError

    def _parse_payload(
        self,
        provider_payload: dict[str, Any],
        request_payload: dict[str, Any],
        task: AITask,
    ) -> dict[str, Any]:
        return dict(provider_payload or {})

    def _on_failure(self, exc: Exception, task: AITask, request_payload: dict[str, Any]) -> ProviderRunResult:
        error_code = exc.error_code if isinstance(exc, ProviderExecutionError) else self.failure_error_code
        if self._is_retryable_failure(exc, error_code):
            return ProviderRunResult.retryable_failure(
                self._failure_message(exc),
                error_code=error_code,
                retry_delay_seconds=30,
                metadata=_route_metadata(self.adapter_name, self.route),
            )
        return ProviderRunResult.terminal_failure(
            self._failure_message(exc),
            error_code=error_code,
            metadata=_route_metadata(self.adapter_name, self.route),
        )

    def _failure_message(self, exc: Exception) -> str:
        return str(exc)

    def _is_retryable_failure(self, exc: Exception, error_code: str) -> bool:
        if error_code == "http_api_provider_http_error":
            status_code = getattr(exc, "status_code", None)
            return status_code in RETRYABLE_HTTP_PROVIDER_STATUS_CODES
        return error_code in RETRYABLE_PROVIDER_ERROR_CODES


class CodexWritingScoreAdapter(AiTaskTemplate):
    adapter_name = "writing_score_codex"
    failure_error_code = "codex_writing_score_failed"

    def _execute_provider(self, task: AITask, request_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        output, usage = run_codex(
            self._report_prompt(request_payload),
            f"writing_score_{task.task_id}_report",
            timeout=180,
            max_attempts=1,
        )
        return extract_json_object(output), usage

    def _parse_payload(
        self,
        provider_payload: dict[str, Any],
        request_payload: dict[str, Any],
        task: AITask,
    ) -> dict[str, Any]:
        return {"score": self._score_payload(provider_payload, request_payload)}

    def _failure_message(self, exc: Exception) -> str:
        return f"Codex writing report generation failed: {exc}"

    def _report_prompt(self, request_payload: dict[str, Any]) -> str:
        task_type = str(request_payload.get("task_type") or "task2")
        task_label = "IELTS Writing Task 1 Academic" if task_type == "task1_academic" else "IELTS Writing Task 2"
        task_score_key = "task_achievement" if task_type == "task1_academic" else "task_response"
        opposite_score_key = "task_response" if task_score_key == "task_achievement" else "task_achievement"
        task1_specific_block = self._task1_specific_block() if task_type == "task1_academic" else ""
        chart_facts_block = self._chart_facts_block(request_payload) if task_type == "task1_academic" else ""
        return f"""Return JSON only. Do not include Markdown outside JSON.

You are an IELTS Writing examiner and writing coach for a Chinese IELTS learner.

Evaluate this answer using the public IELTS Writing band descriptors. Be strict and realistic. Do not inflate the score because the essay sounds fluent. A fluent essay that misreports the data, misses the overview, or does not answer the question must still receive a low Task score.

Score keys:
- overall_band: number
- task_achievement: number or null. Use for Task 1 Academic.
- task_response: number or null. Use for Task 2.
- coherence_cohesion: number
- lexical_resource: number
- grammatical_range_accuracy: number

Assessment principles:
- Task 1 Academic: judge whether the candidate selects and compares the MAIN features accurately, gives a clear overview, avoids irrelevant detail, and reports data / trends / maps / processes precisely. Inaccurate or invented data, a missing overview, or listing every figure without comparison are the most common reasons Task Achievement stays at band 6 or below.
- Task 2: judge whether the candidate fully answers all parts of the question, keeps a clear position, develops ideas with support, and avoids overgeneralised or memorised arguments.
- Coherence & Cohesion: judge logical progression, paragraphing, referencing, and whether linking feels natural rather than mechanical.
- Lexical Resource: judge precision, collocation, topic vocabulary, word form, and whether less common vocabulary is used naturally.
- Grammar: judge range and accuracy, sentence control, punctuation, and whether errors reduce clarity.

Chinese learner focus:
- Point out problems common among Chinese candidates only when visible in this essay: unclear or missing overview, listing without comparison, mechanical linking words, translated expressions, vague nouns, overlong sentences, missing article / plural control, weak paragraph topic sentences, or unsupported claims.
- Do not use generic advice. Every comment must be tied to this exact answer.
{task1_specific_block}
{chart_facts_block}

Required JSON keys:
- overall_band: number
- task_achievement: number or null
- task_response: number or null
- coherence_cohesion: number
- lexical_resource: number
- grammatical_range_accuracy: number
- overall_review: Chinese string. Direct diagnosis of this exact essay. For Task 1, explicitly state whether the overview and the main features are correct.
- practice_focus: Chinese string. The most important next practice target.
- grammar_corrections: array of objects with original, suggestion, reason. Include only meaningful grammar, collocation, word form, article/plural, or sentence-control issues.
- inline_annotations: array of objects for marking the learner's original answer inline. Each object must include original, type, suggestion, and explanation; paragraph_index is recommended when the issue belongs to a specific paragraph. type must be one of spelling, punctuation, format, grammar, word_choice, missing_word, extra_word. Mark visible spelling mistakes, punctuation/spacing/format problems, missing words, redundant words, and sentence-control errors. original must be an exact substring from the user's answer; for missing_word, use the exact nearby anchor phrase before the insertion point as original and put the missing word or phrase in suggestion.
- data_accuracy_notes: array of Chinese strings. Task 1 only; otherwise empty array. List each place where the candidate's reported figure, trend, or comparison disagrees with the chart facts, quoting the candidate's wording. If chart facts are not provided, judge only internal consistency and leave this empty when nothing is clearly wrong.
- spelling_correction_summary: Chinese Markdown string shown once for the whole essay. It must cover all visible spelling mistakes from the whole answer, classify them by cause with Chinese section labels such as `字母多余 / 发音误导类错误`, `词尾后缀混淆类错误`, and list examples like `vidios -> 正确：videos（视频）`. Do not use Markdown numbered lists like `1.` because renderers may restart numbering.
- structure_advice_only: boolean. Set true if the user's paragraphing is too messy to map paragraph-by-paragraph.
- structure_advice: Chinese string. Required when structure_advice_only is true; otherwise empty string.
- model_answer: English string. Improved version with paragraph breaks, unless structure_advice_only is true. For Task 1, the model answer must contain a correct one-sentence overview of the main features and must only use figures consistent with the chart facts when those facts are provided.
- paragraph_reviews: array. If structure_advice_only is false, include one object per logical paragraph with index, learner, model, coaching, language_correction_upgrade. learner must quote the relevant user paragraph. model must be a better English paragraph. coaching must be Chinese and specific. language_correction_upgrade must be Chinese Markdown appended visually after AI coaching for that paragraph. Let the AI freely generate concise dash bullets using `-`; do not force subsections, fixed categories, or a fixed number of points. Do not mention spelling mistakes in coaching or language_correction_upgrade; spelling belongs only in spelling_correction_summary.
- expression_upgrade_summary: string. Backward-compatible alias; leave empty unless needed for old clients.
- backend: string, must be "ai"

Output rules:
- This is a single combined scoring and coaching call. Do not return feedback_markdown.
- If this is {task_label}, set {opposite_score_key} to null and fill {task_score_key}.
- If paragraphing is logical enough, paragraph_reviews must match the essay logic.
- If structure_advice_only is true, paragraph_reviews may be empty and structure_advice must explain how to reorganise the essay before rewriting.
- Do not return placeholder text.
- Do not say "由 AI 生成" or similar meta text.
- inline_annotations should behave like a writing checker: keep the essay readable, mark concrete evidence, and mark all clear spelling errors from the answer.
- Use spelling_correction_summary once for the whole essay. Do not place spelling explanations or spelling examples under each paragraph.
- paragraph_reviews[].coaching should discuss paragraph logic, task response, cohesion, grammar control, expression precision, and revision strategy; it must not say the paragraph has spelling mistakes.
- Put grammar correction, expression correction, and expression upgrade in each paragraph_reviews item as language_correction_upgrade. Use simple dash bullets (`- ...`) and let the AI decide what to include. Do not create one global language-upgrade summary. This field must focus on grammar, collocation, sentence control, cohesion, tone, precision, and richer expression; it must not repeat spelling mistakes already listed in spelling_correction_summary.
- Chinese feedback should explain what affects the band, why it happens, and what exact revision action helps.

Task:
{task_label}

Title:
{request_payload.get("title") or ""}

Prompt:
{request_payload.get("prompt") or ""}

Answer:
{request_payload.get("answer") or ""}

Word count:
{request_payload.get("word_count") or ""}
"""

    def _task1_specific_block(self) -> str:
        return """
Task 1 specific checks (apply strictly):
- Overview: there must be a clear overview sentence that states the main trends / biggest differences / overall pattern, without specific data. If it is missing or buried, Task Achievement cannot reach band 7.
- Selection: the candidate should report the MAIN features, not every single number. Penalise mechanical listing of all data points with no comparison.
- Comparison: for graphs/charts/tables, the candidate must compare and contrast (highest vs lowest, fastest change, crossovers). For maps/processes, the candidate must describe change/sequence accurately.
- Accuracy: figures, trend directions (rise/fall/stable/fluctuate), and time references must match the chart. Cross-check against chart facts when provided.
- No opinion / no reasons: Task 1 Academic must not explain causes or give opinions; flag this if present.
"""

    def _chart_facts_block(self, request_payload: dict[str, Any]) -> str:
        chart_facts = request_payload.get("chart_facts")
        if not isinstance(chart_facts, dict) or not chart_facts:
            return ""
        chart_facts_status = str(request_payload.get("chart_facts_status") or chart_facts.get("facts_source") or "ai_unverified").strip() or "ai_unverified"
        enriched = {**chart_facts, "facts_source": chart_facts.get("facts_source") or chart_facts_status}
        chart_facts_json = json.dumps(enriched, ensure_ascii=False, sort_keys=True, indent=2)
        return f"""
Chart facts (reference ground truth for this Task 1 figure):
The following structured facts describe the chart the candidate is writing about. Use them to check the candidate's accuracy.
- These facts are machine-generated and may contain minor errors (facts_source may be "ai_unverified"). Treat them as a strong reference, NOT as absolute truth. If the candidate's essay clearly contradicts a fact in a way that the essay itself proves is correct, trust the essay and do not penalise.
- Use the facts to: (1) verify the overview captures the real main features; (2) detect misreported figures, wrong trend directions, and wrong comparisons; (3) record each disagreement in data_accuracy_notes; (4) keep model_answer consistent with these facts.
- Do NOT dump the raw facts into the feedback. Use them only to judge accuracy and to write a correct model answer.

{chart_facts_json}
"""

    def _score_payload(self, payload: dict[str, Any], request_payload: dict[str, Any]) -> dict[str, Any]:
        task_type = str(request_payload.get("task_type") or "").strip().lower()
        task_key = "task_achievement" if task_type == "task1_academic" else "task_response"
        score_required = ["overall_band", task_key, "coherence_cohesion", "lexical_resource", "grammatical_range_accuracy"]
        review_required = ["overall_review", "practice_focus"]
        missing = [key for key in score_required if payload.get(key) in (None, "")]
        missing.extend(key for key in review_required if payload.get(key) in (None, ""))
        if missing:
            raise RuntimeError(f"Codex writing score missing fields: {', '.join(missing)}")
        if bool(payload.get("structure_advice_only")):
            if not str(payload.get("structure_advice") or "").strip():
                raise RuntimeError("Codex writing score missing structure_advice")
        elif not isinstance(payload.get("paragraph_reviews"), list) or not payload.get("paragraph_reviews"):
            raise RuntimeError("Codex writing score missing paragraph_reviews")
        return {
            "overall_band": float(payload["overall_band"]),
            task_key: float(payload[task_key]),
            "coherence_cohesion": float(payload["coherence_cohesion"]),
            "lexical_resource": float(payload["lexical_resource"]),
            "grammatical_range_accuracy": float(payload["grammatical_range_accuracy"]),
            "feedback_markdown": "",
            "grammar_corrections": payload.get("grammar_corrections") if isinstance(payload.get("grammar_corrections"), list) else [],
            "inline_annotations": payload.get("inline_annotations") if isinstance(payload.get("inline_annotations"), list) else [],
            "data_accuracy_notes": payload.get("data_accuracy_notes") if isinstance(payload.get("data_accuracy_notes"), list) else [],
            "spelling_correction_summary": str(payload.get("spelling_correction_summary") or ""),
            "expression_upgrade_summary": str(payload.get("expression_upgrade_summary") or ""),
            "overall_review": str(payload.get("overall_review") or ""),
            "practice_focus": str(payload.get("practice_focus") or ""),
            "model_answer": str(payload.get("model_answer") or ""),
            "paragraph_reviews": payload.get("paragraph_reviews") if isinstance(payload.get("paragraph_reviews"), list) else [],
            "structure_advice_only": bool(payload.get("structure_advice_only")),
            "structure_advice": str(payload.get("structure_advice") or ""),
            "backend": "ai",
        }

    def _combined_usage(self, *usage_items: dict[str, Any] | None) -> dict[str, Any]:
        combined: dict[str, Any] = {}
        for usage in usage_items:
            if not isinstance(usage, dict):
                continue
            for key, value in usage.items():
                if isinstance(value, (int, float)):
                    combined[key] = combined.get(key, 0) + value
                elif key not in combined:
                    combined[key] = value
        return combined


class HttpWritingScoreAdapter(CodexWritingScoreAdapter):
    adapter_name = "writing_score_http"
    failure_error_code = "http_writing_score_failed"

    def _execute_provider(self, task: AITask, request_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        try:
            result = HttpApiProvider().complete_chat(
                [
                    {
                        "role": "user",
                        "content": self._report_prompt(request_payload),
                    }
                ],
                temperature=0.2,
                max_tokens=5200,
                timeout_seconds=120,
                stream=True,
            )
        except HttpApiProviderError as exc:
            wrapped = ProviderExecutionError(str(exc), error_code=exc.error_code)
            wrapped.status_code = exc.status_code
            raise wrapped from exc
        return extract_json_object(result.text), result.usage or {}

    def _failure_message(self, exc: Exception) -> str:
        return f"HTTP writing report generation failed: {exc}"

    def run(self, task: AITask) -> ProviderRunResult:
        result = super().run(task)
        if result.outcome != ProviderRunOutcome.TERMINAL_FAILURE:
            return result
        # The configured HTTP/OpenAI-compatible provider failed in a non-retryable
        # way — most commonly an expired or invalid API key (HTTP 401, which is not
        # in the retryable status set). Rather than hard-failing the whole writing
        # request, fall back to the local Codex CLI, which is a real AI scorer (not a
        # canned stub). The returned result carries the Codex adapter's own backend
        # metadata, so the report is reported honestly as codex-generated and is never
        # disguised as the HTTP provider. If codex also fails, keep the original HTTP
        # error so the user sees the primary provider's failure.
        codex_result = CodexWritingScoreAdapter(self.route).run(task)
        if codex_result.outcome == ProviderRunOutcome.SUCCESS:
            return codex_result
        return result


class ClaudeWritingScoreAdapter(CodexWritingScoreAdapter):
    adapter_name = "writing_score_claude"
    failure_error_code = "claude_writing_score_failed"

    def _execute_provider(self, task: AITask, request_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        model = self.route.requested_model if self.route and self.route.requested_model else task.model
        output, usage = ClaudeCliClient(model=model or None).run(
            self._report_prompt(request_payload),
            task.call_id or task.task_id,
            timeout=180,
            max_attempts=2,
        )
        return extract_json_object(output), usage or {}

    def _failure_message(self, exc: Exception) -> str:
        return f"Claude writing report generation failed: {exc}"


class CodexSpeakingReportAdapter(AiTaskTemplate):
    adapter_name = "speaking_report_codex"
    failure_error_code = "speaking_report_failed"

    def _execute_provider(self, task: AITask, request_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        from apps.speaking.services import score_attempt_sync

        attempt_id = str(request_payload.get("attempt_id") or task.related_id or "").strip()
        if not attempt_id:
            raise ProviderExecutionError(
                "Speaking report task is missing attempt_id",
                error_code="missing_attempt_id",
            )
        attempt_payload = score_attempt_sync(task.user, attempt_id, request_payload)
        usage = attempt_payload.get("billing_usage") if isinstance(attempt_payload.get("billing_usage"), dict) else {}
        return {"attempt": attempt_payload}, usage


class MockSuccessWritingScoreAdapter(BaseProviderAdapter):
    adapter_name = "writing_score_mock_success"

    def run(self, task: AITask) -> ProviderRunResult:
        request_payload = task.request_payload if isinstance(task.request_payload, dict) else {}
        task_type = str(request_payload.get("task_type") or "").strip().lower()
        answer = str(request_payload.get("answer") or "").strip()
        try:
            word_count = max(0, int(request_payload.get("word_count") or 0))
        except (TypeError, ValueError):
            word_count = 0
        if not word_count and answer:
            word_count = len(answer.split())

        task_key = "task_achievement" if task_type == "task1_academic" else "task_response"
        digest = hashlib.sha1(
            f"{task.task_id}:{request_payload.get('answer_hash') or answer}:{word_count}".encode("utf-8")
        ).hexdigest()
        score = self._score_payload(task_key=task_key, word_count=word_count, digest=digest, answer=answer)
        usage = self._usage_payload(word_count=word_count, digest=digest)
        return ProviderRunResult.success(
            {"score": score},
            usage=usage,
            metadata=_route_metadata(self.adapter_name, self.route),
        )

    def _score_payload(self, *, task_key: str, word_count: int, digest: str, answer: str) -> dict[str, Any]:
        if word_count >= 260:
            base = 6.5
        elif word_count >= 180:
            base = 6.0
        elif word_count >= 120:
            base = 5.5
        else:
            base = 5.0
        variation = (int(digest[:2], 16) % 3) * 0.5
        overall_band = min(7.0, max(5.0, base + variation))
        task_score = max(5.0, overall_band - (0.5 if word_count < 160 else 0.0))
        coherence = max(5.0, overall_band - 0.5)
        lexical = max(5.0, overall_band - (0.5 if word_count < 140 else 0.0))
        grammar = max(5.0, overall_band - 0.5)
        grammar_corrections = []
        if word_count and word_count < 160:
            grammar_corrections.append(
                {
                    "original": "Ideas are present but not fully extended.",
                    "suggestion": "Extend each main point with one clear example or consequence.",
                }
            )
        feedback_markdown = "\n".join(
            [
                "### Mock provider score",
                "",
                f"- Estimated band: {overall_band:.1f}",
                "- Strength: the response stays on topic and keeps a readable structure.",
                "- Improvement: add one more specific example in each body paragraph to deepen support.",
                "- Language: vary sentence openings and keep checking article / plural agreement.",
            ]
        )
        paragraphs = [part.strip() for part in answer.split("\n\n") if part.strip()]
        paragraph_reviews = [
            {
                "index": index + 1,
                "learner": paragraph,
                "model": f"Mock AI rewrite for paragraph {index + 1}: {paragraph}",
                "coaching": f"Mock AI paragraph {index + 1} advice: clarify the main idea and support it with a concrete detail.",
                "language_correction_upgrade": "- Check article and plural agreement.\n- Replace vague wording with precise collocations.",
            }
            for index, paragraph in enumerate(paragraphs)
        ]
        return {
            "overall_band": overall_band,
            task_key: task_score,
            "coherence_cohesion": coherence,
            "lexical_resource": lexical,
            "grammatical_range_accuracy": grammar,
            "feedback_markdown": feedback_markdown,
            "grammar_corrections": grammar_corrections,
            "inline_annotations": [],
            "spelling_correction_summary": "Mock provider did not detect concrete spelling errors.",
            "expression_upgrade_summary": "",
            "overall_review": "Mock AI overall review based on the submitted paragraph structure.",
            "practice_focus": "Mock AI practice focus: improve paragraph-level development and transitions.",
            "model_answer": "\n\n".join(item["model"] for item in paragraph_reviews),
            "paragraph_reviews": paragraph_reviews,
            "structure_advice_only": False,
            "structure_advice": "",
            "backend": "ai",
        }

    def _usage_payload(self, *, word_count: int, digest: str) -> dict[str, int]:
        input_tokens = max(900, (word_count * 6) + 640)
        cached_input_tokens = min(input_tokens // 5, max(0, word_count))
        output_tokens = 220 + (int(digest[2:4], 16) % 80)
        reasoning_output_tokens = int(digest[4:6], 16) % 40
        return {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
            "reasoning_output_tokens": reasoning_output_tokens,
        }


class UnsupportedTaskAdapter(BaseProviderAdapter):
    adapter_name = "unsupported_task"

    def run(self, task: AITask) -> ProviderRunResult:
        return ProviderRunResult.skipped(
            self.route.fallback_reason if self.route else f"no provider runner registered for task_type={task.task_type}",
            error_code=self.route.error_code if self.route and self.route.error_code else "unsupported_task_type",
            metadata=_route_metadata(self.adapter_name, self.route),
        )


class ProviderChain(BaseProviderAdapter):
    adapter_name = "provider_chain"

    def __init__(self, providers: list[AIProvider], route: ProviderRoute | None = None):
        super().__init__(route)
        self.providers = list(providers)

    def run(self, task: AITask) -> ProviderRunResult:
        if not self.providers:
            return ProviderRunResult.skipped(
                f"no provider runner registered for task_type={task.task_type}",
                error_code="unsupported_task_type",
                metadata=_route_metadata(self.adapter_name, self.route),
            )
        last_result: ProviderRunResult | None = None
        for provider in self.providers:
            result = provider.run(task)
            last_result = result
            if result.outcome != ProviderRunOutcome.SKIPPED:
                return result
        return last_result or ProviderRunResult.skipped(
            f"no provider runner registered for task_type={task.task_type}",
            error_code="unsupported_task_type",
            metadata=_route_metadata(self.adapter_name, self.route),
        )


def select_provider_adapter(task: AITask) -> AIProvider:
    route = resolve_provider_route(
        task_type=task.task_type,
        provider=task.provider,
        model=task.model,
    )
    if route.adapter_key == ADAPTER_KEY_MOCK_SUCCESS:
        return ProviderChain([MockSuccessWritingScoreAdapter(route)], route)
    if route.adapter_key == ADAPTER_KEY_CODEX_WRITING_SCORE:
        return ProviderChain([CodexWritingScoreAdapter(route)], route)
    if route.adapter_key == ADAPTER_KEY_HTTP_WRITING_SCORE:
        return ProviderChain([HttpWritingScoreAdapter(route)], route)
    if route.adapter_key == ADAPTER_KEY_CLAUDE_WRITING_SCORE:
        return ProviderChain([ClaudeWritingScoreAdapter(route)], route)
    if route.adapter_key == ADAPTER_KEY_CODEX_SPEAKING_REPORT:
        return ProviderChain([CodexSpeakingReportAdapter(route)], route)
    if route.adapter_key == ADAPTER_KEY_FALLBACK:
        return ProviderChain([FallbackWritingScoreAdapter(route)], route)
    return ProviderChain([UnsupportedTaskAdapter(route)], route)


def run_claimed_ai_task(task: AITask) -> ProviderRunResult:
    return select_provider_adapter(task).run(task)


def apply_provider_run_result(task: AITask, result: ProviderRunResult) -> AppliedProviderRunResult:
    if task.task_type == "writing_score":
        return _apply_writing_score_result(task, result)
    if task.task_type == "speaking_report":
        return _apply_speaking_report_result(task, result)
    return _apply_terminal_failure_for_claimed_task(task, result, summary_status=SUMMARY_STATUS_SKIPPED)


def _apply_speaking_report_result(task: AITask, result: ProviderRunResult) -> AppliedProviderRunResult:
    if result.outcome == ProviderRunOutcome.SUCCESS:
        payload = dict(result.result_payload or {})
        succeed_ai_task(task.task_id, payload, None)
        return _refreshed_task_result(task, AITask.Status.SUCCEEDED)
    if result.outcome == ProviderRunOutcome.RETRYABLE_FAILURE:
        return _apply_failure_result(task, result, retryable=True)
    _mark_speaking_report_attempt_failed(task, result)
    return _apply_terminal_failure_for_claimed_task(task, result)


def _apply_writing_score_result(task: AITask, result: ProviderRunResult) -> AppliedProviderRunResult:
    if result.outcome == ProviderRunOutcome.SUCCESS:
        payload = dict(result.result_payload or {})
        if result.usage:
            payload["usage"] = result.usage
        try:
            complete_score_task(task.task_id, payload)
        except WritingEntryDeleted:
            fallback_billable_ai_task(task.task_id, "Writing entry was deleted before scoring completed.", {"entry_id": task.related_id})
            return _refreshed_task_result(task, AITask.Status.FALLBACK)
        return _refreshed_task_result(task, AITask.Status.SUCCEEDED)
    if result.outcome == ProviderRunOutcome.FALLBACK:
        try:
            fallback_score_task(task.task_id, result.reason or DEFAULT_FALLBACK_REASON)
        except WritingEntryDeleted:
            fallback_billable_ai_task(task.task_id, "Writing entry was deleted before scoring completed.", {"entry_id": task.related_id})
            return _refreshed_task_result(task, AITask.Status.FALLBACK)
        return _refreshed_task_result(task, AITask.Status.FALLBACK)
    if result.outcome == ProviderRunOutcome.SKIPPED:
        return _apply_terminal_failure_for_claimed_task(task, result, summary_status=SUMMARY_STATUS_SKIPPED)
    if result.outcome == ProviderRunOutcome.RETRYABLE_FAILURE:
        return _apply_failure_result(task, result, retryable=True)
    return _apply_terminal_failure_for_claimed_task(task, result)


def _apply_terminal_failure_for_claimed_task(
    task: AITask,
    result: ProviderRunResult,
    *,
    summary_status: str = AITask.Status.FAILED,
) -> AppliedProviderRunResult:
    return _apply_failure_result(task, result, retryable=False, summary_status=summary_status)


def _apply_failure_result(
    task: AITask,
    result: ProviderRunResult,
    *,
    retryable: bool,
    summary_status: str | None = None,
) -> AppliedProviderRunResult:
    error_message = result.error_message or result.reason or "provider runner failed"
    error_code = result.error_code or "provider_runner_failed"
    if task.billing_reservation_id:
        updated_task = fail_billable_ai_task(
            task.task_id,
            error_message,
            error_code=error_code,
            retryable=retryable,
            retry_delay_seconds=result.retry_delay_seconds,
        )
    else:
        updated_task = fail_ai_task(
            task.task_id,
            error_message,
            error_code=error_code,
            retryable=retryable,
            retry_delay_seconds=result.retry_delay_seconds,
        )
    return AppliedProviderRunResult(task=updated_task, summary_status=summary_status or updated_task.status)


def _refreshed_task_result(task: AITask, summary_status: str) -> AppliedProviderRunResult:
    task.refresh_from_db()
    return AppliedProviderRunResult(task=task, summary_status=summary_status)


def _mark_speaking_report_attempt_failed(task: AITask, result: ProviderRunResult) -> None:
    from apps.speaking.models import SpeakingAttempt
    from apps.speaking.services import mark_attempt_analysis_failed

    attempt = (
        SpeakingAttempt.objects.select_related("user")
        .filter(user=task.user, attempt_id=str(task.related_id or "").strip())
        .first()
    )
    if not attempt:
        return
    error = result.error_message or result.reason or "Speaking report generation failed"
    mark_attempt_analysis_failed(attempt, RuntimeError(error), task.call_id or task.task_id)


def _route_metadata(adapter_name: str, route: ProviderRoute | None) -> dict[str, Any]:
    metadata = {"adapter": adapter_name}
    if not route:
        return metadata
    return {
        **metadata,
        "requested_provider": route.requested_provider or FALLBACK_PROVIDER,
        "effective_provider": route.effective_provider or FALLBACK_PROVIDER,
        "provider_mode": route.config_mode,
    }


__all__ = [
    "AIProvider",
    "AiTaskTemplate",
    "AppliedProviderRunResult",
    "BaseProviderAdapter",
    "CodexCliClient",
    "CodexSpeakingReportAdapter",
    "DEFAULT_FALLBACK_REASON",
    "CodexWritingScoreAdapter",
    "FallbackWritingScoreAdapter",
    "MOCK_SUCCESS_PROVIDER",
    "MockSuccessWritingScoreAdapter",
    "ProviderChain",
    "ProviderExecutionError",
    "ProviderRunOutcome",
    "ProviderRunResult",
    "SUMMARY_STATUS_SKIPPED",
    "UnsupportedTaskAdapter",
    "apply_provider_run_result",
    "run_codex",
    "run_claimed_ai_task",
    "select_provider_adapter",
]
