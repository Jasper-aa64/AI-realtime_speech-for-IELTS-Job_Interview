from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Q
from django.utils import timezone

from apps.ai.models import AITask
from apps.ai.orchestration import AIOrchestrationError, recover_stale_ai_tasks
from apps.ai.provider_adapters import SUMMARY_STATUS_SKIPPED, apply_provider_run_result, run_claimed_ai_task
from apps.ai.services import AITaskError, claim_ai_task
from apps.writing.services import WritingError


@dataclass(frozen=True)
class AIWorkerBatchOptions:
    limit: int = 10
    worker_id: str = "local-ai-worker"
    recover_stale_seconds: int = 0


def empty_worker_summary() -> dict[str, Any]:
    return {
        "recovered": {"requeued": 0, "failed": 0},
        "claimed": 0,
        "completed": 0,
        "failed": 0,
        "skipped": 0,
        "items": [],
    }


def pending_ai_tasks(limit: int) -> list[AITask]:
    now = timezone.now()
    return list(
        AITask.objects.filter(status=AITask.Status.PENDING)
        .filter(Q(available_at__isnull=True) | Q(available_at__lte=now))
        .order_by("created_at")[: max(1, int(limit))]
    )


def run_ai_task_batch(
    *,
    limit: int = 10,
    worker_id: str = "local-ai-worker",
    recover_stale_seconds: int = 0,
) -> dict[str, Any]:
    options = AIWorkerBatchOptions(
        limit=max(1, int(limit or 1)),
        worker_id=str(worker_id or "local-ai-worker"),
        recover_stale_seconds=max(0, int(recover_stale_seconds or 0)),
    )
    summary = empty_worker_summary()
    if options.recover_stale_seconds:
        recovered = recover_stale_ai_tasks(
            options.recover_stale_seconds,
            error_message=f"worker lease expired after {options.recover_stale_seconds}s",
        )
        for task in recovered:
            if task.status == AITask.Status.PENDING:
                summary["recovered"]["requeued"] += 1
            elif task.status == AITask.Status.FAILED:
                summary["recovered"]["failed"] += 1

    for task in pending_ai_tasks(options.limit):
        try:
            claimed = claim_ai_task(task.task_id, worker_id=options.worker_id)
            summary["claimed"] += 1
            run_result = run_claimed_ai_task(claimed)
            applied = apply_provider_run_result(claimed, run_result)
            item_status = applied.summary_status
            if item_status in {AITask.Status.SUCCEEDED, AITask.Status.FALLBACK}:
                summary["completed"] += 1
            elif item_status in {AITask.Status.CANCELLED, SUMMARY_STATUS_SKIPPED}:
                summary["skipped"] += 1
            else:
                summary["failed"] += 1
            item = {"task_id": claimed.task_id, "task_type": claimed.task_type, "status": item_status}
            if item_status not in {AITask.Status.SUCCEEDED, AITask.Status.FALLBACK, AITask.Status.CANCELLED, SUMMARY_STATUS_SKIPPED}:
                if applied.task.error_message:
                    item["error"] = applied.task.error_message
            summary["items"].append(item)
        except (AIOrchestrationError, AITaskError, WritingError, ValueError) as exc:
            latest = AITask.objects.filter(pk=task.pk).only("status").first()
            if latest and latest.status == AITask.Status.CANCELLED:
                summary["skipped"] += 1
                summary["items"].append({"task_id": task.task_id, "task_type": task.task_type, "status": AITask.Status.CANCELLED})
                continue
            summary["failed"] += 1
            summary["items"].append({"task_id": task.task_id, "task_type": task.task_type, "status": "error", "error": str(exc)})
    return summary
