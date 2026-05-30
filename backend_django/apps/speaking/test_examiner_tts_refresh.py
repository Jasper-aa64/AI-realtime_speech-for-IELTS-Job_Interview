from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.speaking.models import SpeakingAttempt, SpeakingTurn
from apps.speaking.services import complete_turn


class ExaminerTtsRefreshTests(TestCase):
    def test_examiner_tts_refresh_requires_owner_and_generates_pending_audio(self):
        owner = CustomUser.objects.create_user(username="tts-owner", password="pass")
        other = CustomUser.objects.create_user(username="tts-other", password="pass")
        attempt = SpeakingAttempt.objects.create(
            user=owner,
            attempt_id="tts-refresh-attempt",
            mode="p1",
            part="p1",
            status=SpeakingAttempt.Status.STARTED,
        )
        SpeakingTurn.objects.create(
            user=owner,
            attempt=attempt,
            turn_id="t2_followup",
            sequence=1,
            part="p1",
            question="How does your internship connect with your studies?",
            metadata={
                "examiner_text": "How does your internship connect with your studies?",
                "examiner_tts": {"provider": "volcengine", "status": "pending", "audio_url": None},
            },
        )

        self.client.force_login(other)
        denied = self.client.get("/api/attempts/tts-refresh-attempt/turns/t2_followup/examiner-tts")
        self.assertEqual(denied.status_code, 404)

        self.client.force_login(owner)
        with patch(
            "apps.speaking.services.volcengine_tts",
            return_value={
                "provider": "volcengine",
                "status": "ready",
                "audio_url": "/api/tts-audio/examiner/tts-refresh-attempt_t2_followup_examiner.mp3",
                "content_type": "audio/mpeg",
            },
        ) as mock_tts:
            response = self.client.get("/api/attempts/tts-refresh-attempt/turns/t2_followup/examiner-tts")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["examiner_tts"]["status"], "ready")
        self.assertEqual(
            payload["examiner_tts"]["audio_url"],
            "/api/tts-audio/examiner/tts-refresh-attempt_t2_followup_examiner.mp3",
        )
        mock_tts.assert_called_once_with(
            "How does your internship connect with your studies?",
            role="examiner",
            cache_key="tts-refresh-attempt_t2_followup_examiner",
        )
        turn = SpeakingTurn.objects.get(attempt=attempt, turn_id="t2_followup")
        self.assertEqual(turn.metadata["examiner_tts"]["status"], "ready")

    def test_p3_dynamic_follow_up_enqueues_server_tts_generation_after_commit(self):
        user = CustomUser.objects.create_user(username="p3-tts-user", password="pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="p3-tts-attempt",
            mode="p3",
            part="p3",
            status=SpeakingAttempt.Status.STARTED,
            metadata={"current_turn": "t1", "p3_focus": "cause_effect"},
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t1",
            sequence=0,
            part="p3",
            question="Why do people prefer online learning?",
            metadata={"prompt": {"role": "main", "question": "Why do people prefer online learning?", "question_type": "cause_effect"}},
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t2",
            sequence=1,
            part="p3",
            question="Could you give a specific example?",
            metadata={"prompt": {"role": "follow_up", "question_type": "cause_effect"}},
        )

        with (
            patch(
                "apps.speaking.services.quick_follow_up_runner_with_metadata",
                return_value={"follow_up": "How could this affect traditional schools?", "backend": "http_api", "status": "ready"},
            ),
            patch("apps.speaking.services.threading.Thread") as mock_thread,
            self.captureOnCommitCallbacks(execute=True),
        ):
            result = complete_turn(
                user,
                "p3-tts-attempt",
                "t1",
                {"transcript_raw": "Online learning is flexible, so students can study after work."},
            )

        self.assertEqual(result["next_turn"]["id"], "t2")
        self.assertEqual(result["next_turn"]["question"], "How could this affect traditional schools?")
        self.assertEqual(result["next_turn"]["examiner_tts"]["status"], "pending")
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
