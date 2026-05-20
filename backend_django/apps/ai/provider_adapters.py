from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.ai.models import AITask
from apps.ai.provider_config import (
    ADAPTER_KEY_CODEX_WRITING_SCORE,
    ADAPTER_KEY_FALLBACK,
    ADAPTER_KEY_MOCK_SUCCESS,
    FALLBACK_PROVIDER,
    MOCK_SUCCESS_PROVIDER,
    ProviderRoute,
    resolve_provider_route,
)
from apps.ai.orchestration import fail_billable_ai_task, fallback_billable_ai_task
from apps.ai.services import fail_ai_task
from apps.writing.services import WritingEntryDeleted, complete_score_task, fallback_score_task


DEFAULT_FALLBACK_REASON = "local fallback worker: real AI provider is not connected yet"
SUMMARY_STATUS_SKIPPED = "skipped"
CODEX_REASONING_EFFORT = "medium"


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


class BaseProviderAdapter:
    adapter_name = "base"

    def __init__(self, route: ProviderRoute | None = None):
        self.route = route

    def run(self, task: AITask) -> ProviderRunResult:
        raise NotImplementedError


class FallbackWritingScoreAdapter(BaseProviderAdapter):
    adapter_name = "writing_score_fallback"

    def run(self, task: AITask) -> ProviderRunResult:
        return ProviderRunResult.fallback(
            self.route.fallback_reason if self.route else DEFAULT_FALLBACK_REASON,
            metadata=_route_metadata(self.adapter_name, self.route),
        )


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


def run_codex(prompt: str, call_id: str, timeout: int = 120) -> tuple[str, dict[str, Any] | None]:
    if os.environ.get("IELTS_WEB_DISABLE_CODEX") == "1":
        raise RuntimeError("codex disabled by IELTS_WEB_DISABLE_CODEX=1")

    codex = shutil.which("codex") or "/opt/homebrew/bin/codex"
    if not shutil.which(codex) and not Path(codex).exists():
        raise RuntimeError("codex CLI not found")

    config_args = ["-c", f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"']
    cwd = str(Path(settings.BASE_DIR).parent)
    last_error: RuntimeError | None = None
    for _attempt in range(2):
        try:
            result = subprocess.run(
                [codex, "exec", "--json", *config_args, "-"],
                input=prompt,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=True,
                cwd=cwd,
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
                capture_output=True,
                timeout=timeout,
                check=True,
                cwd=cwd,
            )
            output, usage, has_real_content = result.stdout, None, bool(result.stdout.strip())

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


class CodexWritingScoreAdapter(BaseProviderAdapter):
    adapter_name = "writing_score_codex"

    def run(self, task: AITask) -> ProviderRunResult:
        request_payload = task.request_payload if isinstance(task.request_payload, dict) else {}
        prompt = self._prompt(request_payload)
        try:
            output, usage = run_codex(prompt, f"writing_score_{task.task_id}", timeout=180)
            score = self._score_payload(extract_json_object(output), request_payload)
        except Exception as exc:
            return ProviderRunResult.fallback(
                f"Codex writing report generation failed: {exc}",
                metadata=_route_metadata(self.adapter_name, self.route),
            )
        return ProviderRunResult.success(
            {"score": score},
            usage=usage or {},
            metadata=_route_metadata(self.adapter_name, self.route),
        )

    def _prompt(self, request_payload: dict[str, Any]) -> str:
        task_type = str(request_payload.get("task_type") or "task2")
        task_label = "IELTS Writing Task 1 Academic" if task_type == "task1_academic" else "IELTS Writing Task 2"
        return f"""Return JSON only. Do not include Markdown outside JSON.

You are an IELTS writing examiner and coach. Analyze this submission like the speaking report: specific, based on the user's text, not generic.

Required JSON keys:
- overall_band: number
- task_response or task_achievement: number, choose task_achievement for Task 1 Academic and task_response for Task 2
- coherence_cohesion: number
- lexical_resource: number
- grammatical_range_accuracy: number
- feedback_markdown: string
- grammar_corrections: array of objects with original and suggestion
- overall_review: Chinese string, concrete overall review of this exact essay
- practice_focus: Chinese string, the next focused practice target
- model_answer: English string, improved version with paragraph breaks, unless structure_advice_only is true
- paragraph_reviews: array. If structure_advice_only is false, include one object per logical paragraph with index, learner, model, coaching. learner must quote the relevant user paragraph. model must be a better English paragraph. coaching must be Chinese and specific.
- structure_advice_only: boolean. Set true if the user's paragraphing is too messy to map paragraph-by-paragraph.
- structure_advice: Chinese string. Required when structure_advice_only is true; otherwise empty string.
- backend: string, must be "ai"

Do not use placeholder text. Do not say “暂无 AI 改写”. Do not use fixed generic advice. The paragraph split must follow the essay logic.

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

    def _score_payload(self, payload: dict[str, Any], request_payload: dict[str, Any]) -> dict[str, Any]:
        task_type = str(request_payload.get("task_type") or "").strip().lower()
        task_key = "task_achievement" if task_type == "task1_academic" else "task_response"
        required = ["overall_band", task_key, "coherence_cohesion", "lexical_resource", "grammatical_range_accuracy", "feedback_markdown", "overall_review", "practice_focus"]
        missing = [key for key in required if payload.get(key) in (None, "")]
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
            "feedback_markdown": str(payload.get("feedback_markdown") or ""),
            "grammar_corrections": payload.get("grammar_corrections") if isinstance(payload.get("grammar_corrections"), list) else [],
            "overall_review": str(payload.get("overall_review") or ""),
            "practice_focus": str(payload.get("practice_focus") or ""),
            "model_answer": str(payload.get("model_answer") or ""),
            "paragraph_reviews": payload.get("paragraph_reviews") if isinstance(payload.get("paragraph_reviews"), list) else [],
            "structure_advice_only": bool(payload.get("structure_advice_only")),
            "structure_advice": str(payload.get("structure_advice") or ""),
            "backend": "ai",
        }


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


def select_provider_adapter(task: AITask) -> BaseProviderAdapter:
    route = resolve_provider_route(
        task_type=task.task_type,
        provider=task.provider,
        model=task.model,
    )
    if route.adapter_key == ADAPTER_KEY_MOCK_SUCCESS:
        return MockSuccessWritingScoreAdapter(route)
    if route.adapter_key == ADAPTER_KEY_CODEX_WRITING_SCORE:
        return CodexWritingScoreAdapter(route)
    if route.adapter_key == ADAPTER_KEY_FALLBACK:
        return FallbackWritingScoreAdapter(route)
    return UnsupportedTaskAdapter(route)


def run_claimed_ai_task(task: AITask) -> ProviderRunResult:
    return select_provider_adapter(task).run(task)


def apply_provider_run_result(task: AITask, result: ProviderRunResult) -> AppliedProviderRunResult:
    if task.task_type == "writing_score":
        return _apply_writing_score_result(task, result)
    return _apply_terminal_failure_for_claimed_task(task, result, summary_status=SUMMARY_STATUS_SKIPPED)


def _apply_writing_score_result(task: AITask, result: ProviderRunResult) -> AppliedProviderRunResult:
    if result.outcome == ProviderRunOutcome.SUCCESS:
        payload = dict(result.result_payload or {})
        if result.usage:
            payload["usage"] = result.usage
        try:
            complete_score_task(task.task_id, payload)
        except WritingEntryDeleted:
            if task.billing_reservation_id:
                fallback_billable_ai_task(task.task_id, "Writing entry was deleted before scoring completed.", {"entry_id": task.related_id})
            return _refreshed_task_result(task, AITask.Status.FALLBACK)
        return _refreshed_task_result(task, AITask.Status.SUCCEEDED)
    if result.outcome == ProviderRunOutcome.FALLBACK:
        try:
            fallback_score_task(task.task_id, result.reason or DEFAULT_FALLBACK_REASON)
        except WritingEntryDeleted:
            if task.billing_reservation_id:
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
    "AppliedProviderRunResult",
    "DEFAULT_FALLBACK_REASON",
    "CodexWritingScoreAdapter",
    "FallbackWritingScoreAdapter",
    "MOCK_SUCCESS_PROVIDER",
    "MockSuccessWritingScoreAdapter",
    "ProviderRunOutcome",
    "ProviderRunResult",
    "SUMMARY_STATUS_SKIPPED",
    "UnsupportedTaskAdapter",
    "apply_provider_run_result",
    "run_claimed_ai_task",
    "select_provider_adapter",
]
