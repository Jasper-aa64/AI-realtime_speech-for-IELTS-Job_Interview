import json

from django.core.management.base import BaseCommand

from apps.ai.worker import run_ai_task_batch


class Command(BaseCommand):
    help = "Run pending AI tasks once. This is a local worker boundary before Celery integration."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--worker-id", default="local-ai-worker")
        parser.add_argument("--recover-stale-seconds", type=int, default=0)

    def handle(self, *args, **options):
        summary = run_ai_task_batch(
            limit=options["limit"],
            worker_id=options["worker_id"],
            recover_stale_seconds=options["recover_stale_seconds"],
        )
        self.stdout.write(json.dumps(summary, ensure_ascii=False, sort_keys=True))
