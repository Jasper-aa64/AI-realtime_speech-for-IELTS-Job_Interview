from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from apps.ai.models import AITask
from apps.ai.orchestration import fail_billable_ai_task
from apps.ai.services import fail_ai_task
from apps.writing.services import complete_score_task, fallback_score_task


DEFAULT_FALLBACK_REASON = "local fallback worker: real AI provider is not connected yet"
MOCK_SUCCESS_PROVIDER = "mock_success"
SUMMARY_STATUS_SKIPPED = "skipped"


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

    def run(self, task: AITask) -> ProviderRunResult:
        raise NotImplementedError


class FallbackWritingScoreAdapter(BaseProviderAdapter):
    adapter_name = "writing_score_fallback"

    def run(self, task: AITask) -> ProviderRunResult:
        return ProviderRunResult.fallback(
            DEFAULT_FALLBACK_REASON,
            metadata={"adapter": self.adapter_name},
        )


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
        score = self._score_payload(task_key=task_key, word_count=word_count, digest=digest)
        usage = self._usage_payload(word_count=word_count, digest=digest)
        return ProviderRunResult.success(
            {"score": score},
            usage=usage,
            metadata={"adapter": self.adapter_name},
        )

    def _score_payload(self, *, task_key: str, word_count: int, digest: str) -> dict[str, Any]:
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
        return {
            "overall_band": overall_band,
            task_key: task_score,
            "coherence_cohesion": coherence,
            "lexical_resource": lexical,
            "grammatical_range_accuracy": grammar,
            "feedback_markdown": feedback_markdown,
            "grammar_corrections": grammar_corrections,
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
            f"no provider runner registered for task_type={task.task_type}",
            error_code="unsupported_task_type",
            metadata={"adapter": self.adapter_name},
        )


def select_provider_adapter(task: AITask) -> BaseProviderAdapter:
    if task.task_type == "writing_score":
        if task.provider == MOCK_SUCCESS_PROVIDER:
            return MockSuccessWritingScoreAdapter()
        return FallbackWritingScoreAdapter()
    return UnsupportedTaskAdapter()


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
        complete_score_task(task.task_id, payload)
        return _refreshed_task_result(task, AITask.Status.SUCCEEDED)
    if result.outcome == ProviderRunOutcome.FALLBACK:
        fallback_score_task(task.task_id, result.reason or DEFAULT_FALLBACK_REASON)
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


__all__ = [
    "AppliedProviderRunResult",
    "DEFAULT_FALLBACK_REASON",
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
