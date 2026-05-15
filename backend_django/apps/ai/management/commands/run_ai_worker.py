import json
import signal
import time
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.ai.worker import run_ai_task_batch


class Command(BaseCommand):
    help = "Continuously run pending AI tasks. Intended for local/single-server process supervision before Celery integration."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--worker-id", default="local-ai-worker")
        parser.add_argument("--recover-stale-seconds", type=int, default=900)
        parser.add_argument("--interval-seconds", type=float, default=1.0)
        parser.add_argument("--idle-interval-seconds", type=float, default=2.5)
        parser.add_argument("--max-loops", type=int, default=0)
        parser.add_argument("--stop-file", default="")

    def handle(self, *args, **options):
        limit = max(1, int(options["limit"]))
        worker_id = str(options["worker_id"] or "local-ai-worker")
        recover_stale_seconds = max(0, int(options["recover_stale_seconds"] or 0))
        interval_seconds = max(0.0, float(options["interval_seconds"] or 0))
        idle_interval_seconds = max(0.0, float(options["idle_interval_seconds"] or 0))
        max_loops = max(0, int(options["max_loops"] or 0))
        stop_file = Path(str(options["stop_file"])).expanduser() if options["stop_file"] else None
        stop_requested = False

        def request_stop(_signum, _frame):
            nonlocal stop_requested
            stop_requested = True

        previous_sigint = signal.getsignal(signal.SIGINT)
        previous_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)
        loops = 0
        try:
            while True:
                if stop_requested or (stop_file and stop_file.exists()):
                    break
                loops += 1
                summary = run_ai_task_batch(
                    limit=limit,
                    worker_id=worker_id,
                    recover_stale_seconds=recover_stale_seconds,
                )
                loop_payload = {
                    "loop": loops,
                    "worker_id": worker_id,
                    "timestamp": timezone.now().isoformat(),
                    "summary": summary,
                }
                self.stdout.write(json.dumps(loop_payload, ensure_ascii=False, sort_keys=True))
                if max_loops and loops >= max_loops:
                    break
                sleep_seconds = interval_seconds if summary["claimed"] or summary["recovered"]["requeued"] or summary["recovered"]["failed"] else idle_interval_seconds
                if sleep_seconds:
                    time.sleep(sleep_seconds)
        finally:
            signal.signal(signal.SIGINT, previous_sigint)
            signal.signal(signal.SIGTERM, previous_sigterm)
