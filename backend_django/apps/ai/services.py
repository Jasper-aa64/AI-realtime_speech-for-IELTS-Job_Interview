import hashlib
import uuid
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import AITask


TERMINAL_STATUSES = {AITask.Status.SUCCEEDED, AITask.Status.FAILED, AITask.Status.FALLBACK, AITask.Status.CANCELLED}


class AITaskError(ValueError):
    pass


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def task_hash(*parts: Any) -> str:
    raw = ":".join(clean_text(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def generated_task_id(user, idempotency_key: str | None = None) -> str:
    if idempotency_key:
        return f"aitask_{task_hash(user.pk, idempotency_key)}"
    return f"aitask_{uuid.uuid4().hex[:24]}"


def task_payload(task: AITask) -> dict[str, Any]:
    return {
        "id": task.task_id,
        "task_type": task.task_type,
        "provider": task.provider,
        "model": task.model,
        "status": task.status,
        "progress_percent": task.progress_percent,
        "attempt_count": task.attempt_count,
        "max_attempts": task.max_attempts,
        "related_type": task.related_type,
        "related_id": task.related_id,
        "call_id": task.call_id,
        "prompt_version": task.prompt_version,
        "idempotency_key": task.idempotency_key,
        "request_payload": task.request_payload,
        "result_payload": task.result_payload,
        "error_code": task.error_code,
        "error_message": task.error_message,
        "fallback_reason": task.fallback_reason,
        "available_at": task.available_at.isoformat() if task.available_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "metadata": task.metadata,
        "billing": {
            "reservation_id": task.billing_reservation.reservation_id if task.billing_reservation_id else None,
            "usage_id": task.usage.usage_id if task.usage_id else None,
        },
    }


def get_ai_task(user, task_id: str) -> AITask:
    task_id = clean_text(task_id)
    task = AITask.objects.filter(user=user, task_id=task_id).first()
    if not task:
        raise AITaskError("AI task not found")
    return task


@transaction.atomic
def create_ai_task(
    *,
    user,
    task_type: str,
    idempotency_key: str = "",
    provider: str = "codex",
    model: str = "",
    related_type: str = "",
    related_id: str = "",
    call_id: str = "",
    prompt_version: str = "",
    request_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    max_attempts: int = 3,
    billing_reservation=None,
) -> tuple[AITask, bool]:
    task_type = clean_text(task_type)
    if not task_type:
        raise AITaskError("task_type is required")

    idempotency_key = clean_text(idempotency_key)
    if idempotency_key:
        existing = AITask.objects.select_for_update().filter(idempotency_key=idempotency_key).first()
        if existing:
            if existing.user_id != user.pk:
                raise AITaskError("idempotency_key already belongs to another user")
            return existing, False

    try:
        task = AITask.objects.create(
            user=user,
            task_id=generated_task_id(user, idempotency_key or None),
            idempotency_key=idempotency_key or None,
            task_type=task_type,
            provider=clean_text(provider) or "codex",
            model=clean_text(model),
            related_type=clean_text(related_type),
            related_id=clean_text(related_id),
            call_id=clean_text(call_id),
            prompt_version=clean_text(prompt_version),
            request_payload=request_payload or {},
            metadata=metadata or {},
            max_attempts=max(1, int(max_attempts or 1)),
            available_at=timezone.now(),
            billing_reservation=billing_reservation,
        )
    except IntegrityError:
        if not idempotency_key:
            raise
        existing = AITask.objects.select_for_update().filter(idempotency_key=idempotency_key).first()
        if not existing or existing.user_id != user.pk:
            raise AITaskError("Unable to create AI task") from None
        return existing, False
    return task, True


@transaction.atomic
def claim_ai_task(task_id: str, worker_id: str = "") -> AITask:
    now = timezone.now()
    task = AITask.objects.select_for_update().filter(task_id=clean_text(task_id)).first()
    if not task:
        raise AITaskError("AI task not found")
    if task.status != AITask.Status.PENDING:
        raise AITaskError(f"AI task is not claimable from status {task.status}")
    if task.available_at and task.available_at > now:
        raise AITaskError("AI task is not available yet")

    task.status = AITask.Status.RUNNING
    task.attempt_count += 1
    task.progress_percent = max(task.progress_percent, 1)
    task.started_at = now
    task.worker_id = clean_text(worker_id)
    task.error_code = ""
    task.error_message = ""
    task.save(
        update_fields=[
            "status",
            "attempt_count",
            "progress_percent",
            "started_at",
            "worker_id",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )
    return task


def stale_running_task_ids(stale_after_seconds: int, *, limit: int | None = None) -> list[str]:
    try:
        stale_after_seconds = int(stale_after_seconds)
    except (TypeError, ValueError) as exc:
        raise AITaskError("stale_after_seconds must be a positive integer") from exc
    if stale_after_seconds <= 0:
        raise AITaskError("stale_after_seconds must be a positive integer")

    cutoff = timezone.now() - timezone.timedelta(seconds=stale_after_seconds)
    queryset = (
        AITask.objects.filter(status=AITask.Status.RUNNING, started_at__isnull=False, started_at__lte=cutoff)
        .order_by("started_at", "created_at")
        .values_list("task_id", flat=True)
    )
    if limit is not None:
        queryset = queryset[: max(1, int(limit))]
    return list(queryset)


@transaction.atomic
def recover_running_ai_task(
    task_id: str,
    *,
    error_message: str = "worker lease expired",
    error_code: str = "worker_lease_expired",
    retry_delay_seconds: int = 0,
) -> AITask:
    task = AITask.objects.select_for_update().filter(task_id=clean_text(task_id)).first()
    if not task:
        raise AITaskError("AI task not found")
    if task.is_terminal or task.status != AITask.Status.RUNNING:
        return task

    task.error_code = clean_text(error_code)
    task.error_message = clean_text(error_message)
    if task.attempt_count < task.max_attempts:
        task.status = AITask.Status.PENDING
        task.available_at = timezone.now() + timezone.timedelta(seconds=max(0, int(retry_delay_seconds or 0)))
        task.progress_percent = 0
        task.started_at = None
        task.finished_at = None
        task.worker_id = ""
        task.save(
            update_fields=[
                "status",
                "available_at",
                "progress_percent",
                "started_at",
                "finished_at",
                "worker_id",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )
        return task

    task.status = AITask.Status.FAILED
    task.available_at = None
    task.finished_at = timezone.now()
    task.worker_id = ""
    task.save(
        update_fields=[
            "status",
            "available_at",
            "finished_at",
            "worker_id",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )
    return task


def recover_stale_running_ai_tasks(
    stale_after_seconds: int,
    *,
    limit: int | None = None,
    retry_delay_seconds: int = 0,
    error_message: str = "worker lease expired",
    error_code: str = "worker_lease_expired",
) -> list[AITask]:
    recovered = []
    for task_id in stale_running_task_ids(stale_after_seconds, limit=limit):
        recovered.append(
            recover_running_ai_task(
                task_id,
                error_message=error_message,
                error_code=error_code,
                retry_delay_seconds=retry_delay_seconds,
            )
        )
    return recovered


@transaction.atomic
def update_ai_task_progress(task_id: str, progress_percent: int, metadata: dict[str, Any] | None = None) -> AITask:
    task = AITask.objects.select_for_update().filter(task_id=clean_text(task_id)).first()
    if not task:
        raise AITaskError("AI task not found")
    if task.is_terminal:
        return task
    task.progress_percent = max(0, min(99, int(progress_percent)))
    if metadata:
        task.metadata = {**task.metadata, **metadata}
    task.save(update_fields=["progress_percent", "metadata", "updated_at"])
    return task


@transaction.atomic
def succeed_ai_task(task_id: str, result_payload: dict[str, Any] | None = None, usage=None) -> AITask:
    task = AITask.objects.select_for_update().filter(task_id=clean_text(task_id)).first()
    if not task:
        raise AITaskError("AI task not found")
    if task.is_terminal:
        return task
    task.status = AITask.Status.SUCCEEDED
    task.progress_percent = 100
    task.result_payload = result_payload or {}
    task.usage = usage
    task.finished_at = timezone.now()
    task.save(update_fields=["status", "progress_percent", "result_payload", "usage", "finished_at", "updated_at"])
    return task


@transaction.atomic
def fail_ai_task(
    task_id: str,
    error_message: str,
    *,
    error_code: str = "",
    retryable: bool = True,
    retry_delay_seconds: int = 60,
) -> AITask:
    task = AITask.objects.select_for_update().filter(task_id=clean_text(task_id)).first()
    if not task:
        raise AITaskError("AI task not found")
    if task.is_terminal:
        return task

    task.error_code = clean_text(error_code)
    task.error_message = clean_text(error_message)
    if retryable and task.attempt_count < task.max_attempts:
        task.status = AITask.Status.PENDING
        task.available_at = timezone.now() + timezone.timedelta(seconds=max(1, int(retry_delay_seconds or 1)))
        task.progress_percent = 0
        task.worker_id = ""
        task.save(update_fields=["status", "available_at", "progress_percent", "worker_id", "error_code", "error_message", "updated_at"])
        return task

    task.status = AITask.Status.FAILED
    task.finished_at = timezone.now()
    task.save(update_fields=["status", "finished_at", "error_code", "error_message", "updated_at"])
    return task


@transaction.atomic
def fallback_ai_task(task_id: str, fallback_reason: str, result_payload: dict[str, Any] | None = None) -> AITask:
    task = AITask.objects.select_for_update().filter(task_id=clean_text(task_id)).first()
    if not task:
        raise AITaskError("AI task not found")
    if task.is_terminal:
        return task
    task.status = AITask.Status.FALLBACK
    task.progress_percent = 100
    task.fallback_reason = clean_text(fallback_reason)
    task.result_payload = result_payload or {}
    task.finished_at = timezone.now()
    task.save(update_fields=["status", "progress_percent", "fallback_reason", "result_payload", "finished_at", "updated_at"])
    return task


@transaction.atomic
def cancel_ai_task(task_id: str, *, reason: str = "", error_code: str = "cancelled") -> AITask:
    task = AITask.objects.select_for_update().filter(task_id=clean_text(task_id)).first()
    if not task:
        raise AITaskError("AI task not found")
    if task.is_terminal:
        return task

    task.status = AITask.Status.CANCELLED
    task.available_at = None
    task.worker_id = ""
    task.error_code = clean_text(error_code) or "cancelled"
    task.error_message = clean_text(reason)
    task.finished_at = timezone.now()
    task.save(
        update_fields=[
            "status",
            "available_at",
            "worker_id",
            "error_code",
            "error_message",
            "finished_at",
            "updated_at",
        ]
    )
    return task
