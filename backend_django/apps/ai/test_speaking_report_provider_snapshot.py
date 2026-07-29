from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.ai.models import AITask
from apps.ai.provider_adapters import CodexSpeakingReportAdapter
from apps.speaking.models import SpeakingAttempt, SpeakingTurn
from apps.speaking.services import generate_turn_feedback_for_report


class SpeakingReportProviderSnapshotTests(TestCase):
    def test_worker_passes_frozen_requested_provider_to_speaking_score(self):
        user = get_user_model().objects.create_user(username="snapshot-provider-user", password="test-pass")
        task = AITask.objects.create(
            user=user,
            task_id="snapshot-speaking-task",
            task_type="speaking_report",
            related_type="speaking_attempt",
            related_id="snapshot-attempt",
            request_payload={
                "attempt_id": "snapshot-attempt",
                "requested_provider": "gpt-5.6-luna",
                "requested_model": "",
            },
        )

        with patch(
            "apps.speaking.services.score_attempt_sync",
            return_value={"billing_usage": {}},
        ) as score_attempt_sync:
            CodexSpeakingReportAdapter()._execute_provider(task, task.request_payload)

        score_payload = score_attempt_sync.call_args.args[2]
        self.assertEqual(score_payload["ai_source"], "gpt-5.6-luna")

    def test_per_turn_feedback_uses_frozen_task_source_instead_of_profile_default(self):
        user = get_user_model().objects.create_user(username="frozen-turn-feedback", password="test-pass")
        UserProfile.objects.create(user=user, report_ai_source="gpt")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="frozen-turn-feedback-attempt",
            mode="p1",
            part="p1",
            status=SpeakingAttempt.Status.READY_TO_SCORE,
        )
        turn = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t1",
            sequence=0,
            part="p1",
            question="Do you work or study?",
            transcript_raw="I study software engineering.",
            transcript_cleaned="I study software engineering.",
            metadata={"status": "completed"},
        )
        generated = {
            "t1": {
                "display_transcript": "I study software engineering.",
                "band7_version": "I study software engineering because I enjoy solving practical problems.",
                "ai_coaching": "展开一个具体例子会让回答更完整。\n\n语法错误纠正：无",
                "generation_backend": "http_api",
            }
        }

        with patch("apps.speaking.services.turn_feedback_batch_with_codex", return_value=generated) as batch, patch(
            "apps.speaking.services.volcengine_tts", return_value={"status": "pending"}
        ):
            generate_turn_feedback_for_report(
                attempt,
                [turn],
                {},
                "frozen_turn_feedback",
                ai_source="gpt-5.6-luna",
            )

        self.assertEqual(batch.call_args.kwargs["ai_source"], "gpt-5.6-luna")
