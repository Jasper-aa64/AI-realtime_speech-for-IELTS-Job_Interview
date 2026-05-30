from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from .models import SpeakingAttempt, SpeakingTurn


class _StreamingProvider:
    def __init__(self, chunks: list[str]):
        self.chunks = chunks

    def stream_tokens(self, *args, **kwargs):
        yield from self.chunks


def _sse_payloads(response) -> list[dict]:
    body = b"".join(response.streaming_content).decode("utf-8")
    payloads = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block.startswith("data:"):
            continue
        payloads.append(json.loads(block.removeprefix("data:").strip()))
    return payloads


class StreamingFollowUpTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="stream-user", password="test-pass")
        self.client.force_login(self.user)

    def create_p3_attempt(self):
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id="stream-p3-attempt",
            mode=SpeakingAttempt.Mode.P3,
            part="p3",
            title="Part 3 practice",
            status=SpeakingAttempt.Status.STARTED,
            metadata={"p3_focus": "cause and effect", "current_turn": "t2_followup"},
        )
        main_turn = SpeakingTurn.objects.create(
            user=self.user,
            attempt=attempt,
            turn_id="t1",
            sequence=0,
            part="p3",
            question="Why do some people prefer online learning?",
            transcript_raw="Online learning is flexible because people can study after work.",
            transcript_cleaned="Online learning is flexible because people can study after work.",
            metadata={
                "status": "completed",
                "prompt": {
                    "role": "main",
                    "question": "Why do some people prefer online learning?",
                    "question_type": "cause_effect",
                },
            },
        )
        follow_up_turn = SpeakingTurn.objects.create(
            user=self.user,
            attempt=attempt,
            turn_id="t2_followup",
            sequence=1,
            part="p3",
            question="Could you give an example?",
            metadata={
                "prompt": {"role": "follow_up", "question_type": "cause_effect"},
                "examiner_tts": {"provider": "volcengine", "status": "pending", "audio_url": None},
            },
        )
        return attempt, main_turn, follow_up_turn

    def test_follow_up_stream_updates_turn_and_emits_tts_ready(self):
        _attempt, main_turn, follow_up_turn = self.create_p3_attempt()
        with (
            patch(
                "apps.speaking.services.HttpApiProvider",
                return_value=_StreamingProvider(["How could ", "this affect families in the future?"]),
            ),
            patch(
                "apps.speaking.services.volcengine_tts",
                return_value={
                    "provider": "volcengine",
                    "status": "ready",
                    "audio_url": "/api/tts-audio/examiner/stream-p3-attempt_t2_followup_examiner.mp3",
                    "content_type": "audio/mpeg",
                },
            ),
        ):
            response = self.client.get(
                f"/api/attempts/stream-p3-attempt/turns/{main_turn.turn_id}/follow-up-stream"
            )
            payloads = _sse_payloads(response)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response["Content-Type"])
        events = [payload["event"] for payload in payloads]
        self.assertIn("chunk", events)
        self.assertIn("question_complete", events)
        self.assertIn("tts_ready", events)
        follow_up_turn.refresh_from_db()
        self.assertEqual(follow_up_turn.question, "How could this affect families in the future?")
        self.assertEqual(follow_up_turn.metadata["prompt"]["backend"], "http_api_stream")
        self.assertEqual(follow_up_turn.metadata["examiner_tts"]["status"], "ready")

    def test_follow_up_stream_emits_fallback_when_http_provider_fails(self):
        _attempt, main_turn, follow_up_turn = self.create_p3_attempt()
        with patch("apps.speaking.services.HttpApiProvider", side_effect=RuntimeError("provider unavailable")):
            response = self.client.get(
                f"/api/attempts/stream-p3-attempt/turns/{main_turn.turn_id}/follow-up-stream"
            )
            payloads = _sse_payloads(response)

        self.assertEqual(response.status_code, 200)
        fallback = next(payload for payload in payloads if payload["event"] == "fallback")
        self.assertEqual(fallback["backend"], "fallback")
        follow_up_turn.refresh_from_db()
        self.assertEqual(follow_up_turn.metadata["prompt"]["backend"], "fallback")

    def test_turn_complete_stream_follow_up_marks_p1_follow_up_pending(self):
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id="stream-p1-attempt",
            mode=SpeakingAttempt.Mode.P1,
            part="p1",
            title="Part 1 practice",
            status=SpeakingAttempt.Status.STARTED,
            metadata={"current_turn": "t2"},
        )
        SpeakingTurn.objects.create(
            user=self.user,
            attempt=attempt,
            turn_id="t2",
            sequence=1,
            part="p1",
            question="Do you work or do you study?",
            metadata={
                "prompt": {
                    "topic": "intro",
                    "question": "Do you work or do you study?",
                    "flow": "intro",
                    "role": "work_study",
                    "counts_toward_total": True,
                },
                "display_index": 1,
            },
        )
        with patch("apps.speaking.services._generate_p1_identity_follow_up") as generate_follow_up:
            response = self.client.post(
                "/api/attempts/stream-p1-attempt/turns/t2/complete",
                data={
                    "transcript_raw": "I study software engineering and do an internship at a tech company.",
                    "stream_follow_up": True,
                },
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        generate_follow_up.assert_not_called()
        payload = response.json()
        self.assertEqual(payload["next_turn"]["prompt"]["backend"], "stream_pending")
        self.assertEqual(payload["next_turn"]["examiner_tts"]["status"], "pending")
