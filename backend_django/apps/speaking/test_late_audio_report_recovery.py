from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.models import AITask

from .models import SpeakingAttempt, SpeakingReport, SpeakingTurn
from .services import create_speaking_report_task


class LateAudioReportRecoveryTests(TestCase):
    def test_score_request_recovers_late_audio_before_returning_cached_report(self):
        user = get_user_model().objects.create_user(username="late-audio-report-user", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="late-audio-report-attempt",
            mode="p3",
            part="p3",
            status=SpeakingAttempt.Status.SCORED,
            title="Part 3 discussion",
        )
        dropped = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t1",
            sequence=0,
            part="p3",
            question="Why do some videos become popular?",
            transcript_raw="",
            transcript_cleaned="",
            audio_path="audio/late-audio-report-attempt_t1.webm",
            metadata={
                "status": "completed",
                "dropped_empty": True,
                "audio_uploaded_at": "2026-08-02T06:05:03+00:00",
                "band7_version": "Old answer generated without the learner recording.",
                "band7_markdown": "Old answer generated without the learner recording.",
                "feedback_generation_backend": "http_api",
                "feedback_generation_status": "ready",
            },
        )
        answered = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t2",
            sequence=1,
            part="p3",
            question="What makes people share videos?",
            transcript_raw="People share videos when the story surprises them.",
            transcript_cleaned="People share videos when the story surprises them.",
            metadata={
                "status": "completed",
                "band7_version": "People often share videos that surprise them.",
                "band7_markdown": "People often share videos that surprise them.",
                "feedback_generation_backend": "http_api",
                "feedback_generation_status": "ready",
            },
        )
        SpeakingReport.objects.create(
            user=user,
            attempt=attempt,
            overall_band=4.5,
            fluency_coherence=4.0,
            lexical_resource=5.0,
            grammar_range_accuracy=4.0,
            report_payload={
                "id": attempt.attempt_id,
                "status": "scored",
                "turns": [
                    {"id": dropped.turn_id, "part": "p3", "status": "completed", "band7_version": "Old answer"},
                    {"id": answered.turn_id, "part": "p3", "status": "completed", "band7_version": "Existing answer"},
                ],
            },
        )
        with patch(
            "apps.speaking.services.transcribe_turn_audio_with_server_asr",
            return_value={
                "ok": True,
                "status": "ready",
                "provider": "volcengine_asr",
                "transcript": "Young people often share short videos because the content feels immediate and relatable.",
            },
        ) as transcribe:
            payload = create_speaking_report_task(user, attempt.attempt_id, {"provider": "gpt"})

        transcribe.assert_called_once_with(dropped)
        dropped.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(payload["status"], "analysis_pending")
        self.assertEqual(attempt.status, SpeakingAttempt.Status.READY_TO_SCORE)
        self.assertIn("Young people often share", dropped.transcript_cleaned)
        self.assertFalse(dropped.metadata.get("dropped_empty"))
        self.assertEqual(dropped.metadata.get("feedback_generation_status"), "pending")
        self.assertEqual(dropped.metadata.get("band7_version"), "")
        self.assertTrue(
            AITask.objects.filter(
                task_type="speaking_report",
                related_id=attempt.attempt_id,
                status=AITask.Status.PENDING,
            ).exists()
        )
