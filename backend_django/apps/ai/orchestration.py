from typing import Any

from django.db import transaction

from apps.billing.models import CodexUsageEvent, WalletReservation
from apps.billing.services import BillingError, release_reservation, reserve_usage, settle_usage

from .models import AITask
from .services import (
    AITaskError,
    cancel_ai_task,
    clean_text,
    create_ai_task,
    fail_ai_task,
    fallback_ai_task,
    recover_running_ai_task,
    stale_running_task_ids,
    succeed_ai_task,
    task_hash,
)


class AIOrchestrationError(ValueError):
    pass


def _release_reserved_billable_task(task: AITask) -> AITask:
    fresh = AITask.objects.select_related("user", "billing_reservation").get(pk=task.pk)
    if fresh.billing_reservation and fresh.billing_reservation.status == WalletReservation.Status.RESERVED:
        release_reservation(fresh.user, fresh.call_id)
        fresh.refresh_from_db()
    return fresh


def generated_call_id(user, idempotency_key: str, task_type: str, related_type: str = "", related_id: str = "") -> str:
    seed = idempotency_key or f"{task_type}:{related_type}:{related_id}"
    return f"ai_{task_hash(user.pk, seed)}"


@transaction.atomic
def create_billable_ai_task(
    *,
    user,
    task_type: str,
    reserved_u: int,
    idempotency_key: str,
    provider: str = "codex",
    model: str = "",
    related_type: str = "",
    related_id: str = "",
    call_id: str = "",
    prompt_version: str = "",
    request_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    max_attempts: int = 3,
) -> tuple[AITask, bool]:
    idempotency_key = clean_text(idempotency_key)
    if not idempotency_key:
        raise AIOrchestrationError("idempotency_key is required for billable AI tasks")
    try:
        reserved_u = int(reserved_u)
    except (TypeError, ValueError) as exc:
        raise AIOrchestrationError("reserved_u must be a positive integer") from exc
    if reserved_u <= 0:
        raise AIOrchestrationError("reserved_u must be a positive integer")

    existing = AITask.objects.select_for_update().filter(idempotency_key=idempotency_key).first()
    if existing:
        if existing.user_id != user.pk:
            raise AIOrchestrationError("idempotency_key already belongs to another user")
        return existing, False

    call_id = clean_text(call_id) or generated_call_id(user, idempotency_key, task_type, related_type, related_id)
    try:
        reserve_usage(user, call_id, reserved_u)
    except BillingError as exc:
        raise AIOrchestrationError(str(exc)) from exc
    reservation = WalletReservation.objects.select_for_update().get(call_id=call_id)
    task, created = create_ai_task(
        user=user,
        task_type=task_type,
        idempotency_key=idempotency_key,
        provider=provider,
        model=model,
        related_type=related_type,
        related_id=related_id,
        call_id=call_id,
        prompt_version=prompt_version,
        request_payload=request_payload,
        metadata=metadata,
        max_attempts=max_attempts,
        billing_reservation=reservation,
    )
    return task, created


@transaction.atomic
def succeed_billable_ai_task(task_id: str, result_payload: dict[str, Any] | None, usage: dict[str, Any] | None) -> AITask:
    task = AITask.objects.select_for_update().select_related("user", "billing_reservation").filter(task_id=clean_text(task_id)).first()
    if not task:
        raise AIOrchestrationError("AI task not found")
    if task.user_id is None:
        raise AIOrchestrationError("AI task has no user")
    if task.is_terminal:
        return task
    try:
        settlement = settle_usage(task.user, task.call_id, usage)
    except BillingError as exc:
        raise AIOrchestrationError(str(exc)) from exc
    task = succeed_ai_task(task.task_id, {**(result_payload or {}), "billing": settlement})
    if settlement.get("usage_id"):
        task.usage = CodexUsageEvent.objects.filter(usage_id=settlement["usage_id"]).first()
        task.save(update_fields=["usage", "updated_at"])
    return task


@transaction.atomic
def fallback_billable_ai_task(task_id: str, fallback_reason: str, result_payload: dict[str, Any] | None = None) -> AITask:
    task = AITask.objects.select_for_update().select_related("user", "billing_reservation").filter(task_id=clean_text(task_id)).first()
    if not task:
        raise AIOrchestrationError("AI task not found")
    updated = fallback_ai_task(task.task_id, fallback_reason, result_payload)
    if updated.status == AITask.Status.FALLBACK:
        return _release_reserved_billable_task(updated)
    return updated


@transaction.atomic
def fail_billable_ai_task(
    task_id: str,
    error_message: str,
    *,
    error_code: str = "",
    retryable: bool = True,
    retry_delay_seconds: int = 60,
) -> AITask:
    task = AITask.objects.select_for_update().select_related("user", "billing_reservation").filter(task_id=clean_text(task_id)).first()
    if not task:
        raise AIOrchestrationError("AI task not found")
    updated = fail_ai_task(
        task.task_id,
        error_message,
        error_code=error_code,
        retryable=retryable,
        retry_delay_seconds=retry_delay_seconds,
    )
    if updated.status == AITask.Status.FAILED:
        return _release_reserved_billable_task(updated)
    return updated


@transaction.atomic
def cancel_billable_ai_task(task_id: str, reason: str = "", *, error_code: str = "cancelled") -> AITask:
    task = AITask.objects.select_for_update().select_related("user", "billing_reservation").filter(task_id=clean_text(task_id)).first()
    if not task:
        raise AIOrchestrationError("AI task not found")
    updated = cancel_ai_task(task.task_id, reason=reason, error_code=error_code)
    if updated.status == AITask.Status.CANCELLED:
        return _release_reserved_billable_task(updated)
    return updated


@transaction.atomic
def recover_stale_ai_tasks(
    stale_after_seconds: int,
    *,
    limit: int | None = None,
    retry_delay_seconds: int = 0,
    error_message: str = "worker lease expired",
    error_code: str = "worker_lease_expired",
) -> list[AITask]:
    recovered = []
    for task_id in stale_running_task_ids(stale_after_seconds, limit=limit):
        updated = recover_running_ai_task(
            task_id,
            error_message=error_message,
            error_code=error_code,
            retry_delay_seconds=retry_delay_seconds,
        )
        if updated.status == AITask.Status.FAILED:
            updated = _release_reserved_billable_task(updated)
        recovered.append(updated)
    return recovered
