import json

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.ai.models import AITask
from apps.ai.orchestration import recover_stale_ai_tasks
from apps.ai.services import AITaskError, claim_ai_task
from apps.writing.services import WritingError, fallback_score_task


class Command(BaseCommand):
    help = "Run pending AI tasks once. This is a local worker boundary before Celery integration."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--worker-id", default="local-ai-worker")
        parser.add_argument("--recover-stale-seconds", type=int, default=0)

    def handle(self, *args, **options):
        limit = max(1, int(options["limit"]))
        worker_id = str(options["worker_id"] or "local-ai-worker")
        recover_stale_seconds = max(0, int(options["recover_stale_seconds"] or 0))
        summary = {
            "recovered": {"requeued": 0, "failed": 0},
            "claimed": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "items": [],
        }
        if recover_stale_seconds:
            recovered = recover_stale_ai_tasks(recover_stale_seconds, error_message=f"worker lease expired after {recover_stale_seconds}s")
            for task in recovered:
                if task.status == AITask.Status.PENDING:
                    summary["recovered"]["requeued"] += 1
                elif task.status == AITask.Status.FAILED:
                    summary["recovered"]["failed"] += 1
        now = timezone.now()
        tasks = list(
            AITask.objects.filter(status=AITask.Status.PENDING)
            .filter(Q(available_at__isnull=True) | Q(available_at__lte=now))
            .order_by("created_at")[:limit]
        )
        for task in tasks:
            try:
                claimed = claim_ai_task(task.task_id, worker_id=worker_id)
                summary["claimed"] += 1
                if claimed.task_type == "writing_score":
                    result = fallback_score_task(claimed.task_id, "local fallback worker: real AI provider is not connected yet")
                    final_status = (
                        (result.get("ai_task") or {}).get("status")
                        if isinstance(result, dict)
                        else None
                    ) or AITask.Status.FALLBACK
                    if final_status == AITask.Status.CANCELLED:
                        summary["skipped"] += 1
                    else:
                        summary["completed"] += 1
                    summary["items"].append({"task_id": claimed.task_id, "task_type": claimed.task_type, "status": final_status})
                else:
                    summary["skipped"] += 1
                    summary["items"].append({"task_id": claimed.task_id, "task_type": claimed.task_type, "status": "skipped"})
            except (AITaskError, WritingError, ValueError) as exc:
                latest = AITask.objects.filter(pk=task.pk).only("status").first()
                if latest and latest.status == AITask.Status.CANCELLED:
                    summary["skipped"] += 1
                    summary["items"].append({"task_id": task.task_id, "task_type": task.task_type, "status": AITask.Status.CANCELLED})
                    continue
                summary["failed"] += 1
                summary["items"].append({"task_id": task.task_id, "task_type": task.task_type, "status": "error", "error": str(exc)})
        self.stdout.write(json.dumps(summary, ensure_ascii=False, sort_keys=True))
