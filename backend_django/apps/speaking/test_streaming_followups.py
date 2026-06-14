from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from .models import SpeakingAttempt, SpeakingTurn


class _StreamingProvider:
    def __init__(self, chunks: list[str], usage: dict | None = None):
        self.chunks = chunks
        self.usage = usage or {}

    def stream_tokens(self, *args, **kwargs):
        on_usage = kwargs.get("on_usage")
        if on_usage and self.usage:
            on_usage(self.usage)
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


@override_settings(
    AI_HTTP_BASE_URL="https://ai.example/v1",
    AI_HTTP_API_KEY="test-key",
    AI_HTTP_MODEL="legacy-model",
    SPEAKING_AI_MODEL="",
    SPEAKING_FOLLOWUP_AI_MODEL="gpt-5.4-mini",
)
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
                return_value=_StreamingProvider(
                    ["How could ", "this affect families in the future?"],
                    usage={"input_tokens": 18, "output_tokens": 8},
                ),
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
        self.assertEqual(follow_up_turn.metadata["prompt"]["provider"], "openai_compatible_http")
        self.assertEqual(follow_up_turn.metadata["prompt"]["model"], "gpt-5.4-mini")
        self.assertEqual(follow_up_turn.metadata["prompt"]["usage"], {"input_tokens": 18, "output_tokens": 8})
        self.assertIn("latency_ms", follow_up_turn.metadata["prompt"])
        self.assertEqual(follow_up_turn.metadata["examiner_tts"]["status"], "ready")

    def test_follow_up_stream_uses_claude_cli_when_account_source_is_claude(self):
        # When the account AI source is Claude, the follow-up must come from the
        # Claude CLI one-shot — never the HTTP relay (which may be down). Regression
        # for "用 Claude 时 P1/P3 追问生成失败".
        from apps.accounts.models import UserProfile

        UserProfile.objects.update_or_create(
            user=self.user, defaults={"report_ai_source": "claude_cli"}
        )
        _attempt, main_turn, follow_up_turn = self.create_p3_attempt()
        with (
            patch("apps.speaking.services.HttpApiProvider") as http_provider,
            patch(
                "apps.speaking.services.run_claude_cli",
                return_value=("How could this change family routines in the future?", {"input_tokens": 12}),
            ) as claude_cli,
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
        http_provider.assert_not_called()
        claude_cli.assert_called_once()
        events = [payload["event"] for payload in payloads]
        self.assertIn("question_complete", events)
        self.assertIn("tts_ready", events)
        follow_up_turn.refresh_from_db()
        self.assertEqual(
            follow_up_turn.question, "How could this change family routines in the future?"
        )
        self.assertEqual(follow_up_turn.metadata["prompt"]["backend"], "claude_cli_stream")
        self.assertEqual(follow_up_turn.metadata["prompt"]["provider"], "claude_cli")

    def test_p3_follow_up_stream_emits_failed_without_fallback_when_http_provider_fails(self):
        # Spec: follow-ups use the GPT/HTTP provider only. If it fails we surface an
        # empty failed turn (frontend shows "点击重录") — never a canned or codex
        # fallback question dressed up as the AI's follow-up.
        _attempt, main_turn, follow_up_turn = self.create_p3_attempt()
        with (
            patch("apps.speaking.services.HttpApiProvider", side_effect=RuntimeError("provider unavailable")),
            patch("apps.speaking.services._generate_streamed_follow_up_tts") as generate_tts,
        ):
            response = self.client.get(
                f"/api/attempts/stream-p3-attempt/turns/{main_turn.turn_id}/follow-up-stream"
            )
            payloads = _sse_payloads(response)

        self.assertEqual(response.status_code, 200)
        generate_tts.assert_not_called()
        failed = next(payload for payload in payloads if payload["event"] == "failed")
        self.assertEqual(failed["backend"], "stream_failed")
        self.assertNotIn("fallback", [payload["event"] for payload in payloads])
        self.assertNotIn("tts_ready", [payload["event"] for payload in payloads])
        follow_up_turn.refresh_from_db()
        self.assertEqual(follow_up_turn.question, "")
        self.assertEqual(follow_up_turn.metadata["prompt"]["backend"], "stream_failed")
        self.assertEqual(follow_up_turn.metadata["prompt"]["generation_status"], "failed")

    def test_p3_follow_up_stream_missing_transcript_stays_failed_without_hardcoded_question(self):
        _attempt, main_turn, follow_up_turn = self.create_p3_attempt()
        main_turn.transcript_raw = ""
        main_turn.transcript_cleaned = ""
        main_turn.save(update_fields=["transcript_raw", "transcript_cleaned"])

        with (
            patch("apps.speaking.services.HttpApiProvider") as provider,
            patch("apps.speaking.services._generate_streamed_follow_up_tts") as generate_tts,
        ):
            response = self.client.get(
                f"/api/attempts/stream-p3-attempt/turns/{main_turn.turn_id}/follow-up-stream"
            )
            payloads = _sse_payloads(response)

        self.assertEqual(response.status_code, 200)
        provider.assert_not_called()
        generate_tts.assert_not_called()
        failed = next(payload for payload in payloads if payload["event"] == "failed")
        self.assertEqual(failed["backend"], "stream_failed")
        self.assertIn("missing_transcript", failed["error"])
        self.assertNotIn("fallback", [payload["event"] for payload in payloads])
        self.assertNotIn("tts_ready", [payload["event"] for payload in payloads])
        follow_up_turn.refresh_from_db()
        self.assertEqual(follow_up_turn.question, "")
        self.assertEqual(follow_up_turn.metadata["prompt"]["backend"], "stream_failed")
        self.assertEqual(follow_up_turn.metadata["prompt"]["generation_status"], "failed")

    def test_turn_complete_stream_follow_up_marks_p3_follow_up_pending_without_template_question(self):
        _attempt, main_turn, follow_up_turn = self.create_p3_attempt()
        response = self.client.post(
            f"/api/attempts/stream-p3-attempt/turns/{main_turn.turn_id}/complete",
            data={
                "transcript_raw": "Online learning is flexible because people can study after work.",
                "stream_follow_up": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["next_turn"]["id"], follow_up_turn.turn_id)
        self.assertEqual(payload["next_turn"]["question"], "Generating follow-up question...")
        self.assertEqual(payload["next_turn"]["examiner_text"], "Generating follow-up question...")
        self.assertEqual(payload["next_turn"]["prompt"]["question"], "Generating follow-up question...")
        self.assertEqual(payload["next_turn"]["prompt"]["backend"], "stream_pending")
        self.assertEqual(payload["next_turn"]["prompt"]["generation_status"], "pending")
        self.assertEqual(
            payload["next_turn"]["prompt"]["fallback_question"],
            "Could you develop that answer with one reason and one specific example?",
        )
        self.assertEqual(payload["next_turn"]["examiner_tts"]["status"], "pending")
        self.assertIsNone(payload["next_turn"]["examiner_tts"]["audio_url"])

        follow_up_turn.refresh_from_db()
        self.assertEqual(follow_up_turn.question, "Generating follow-up question...")
        self.assertEqual(follow_up_turn.metadata["examiner_text"], "Generating follow-up question...")
        self.assertEqual(follow_up_turn.metadata["prompt"]["question"], "Generating follow-up question...")
        self.assertEqual(
            follow_up_turn.metadata["prompt"]["fallback_question"],
            "Could you develop that answer with one reason and one specific example?",
        )

    def test_turn_complete_empty_p3_main_requires_rerecord_without_follow_up(self):
        _attempt, main_turn, follow_up_turn = self.create_p3_attempt()
        # Reset the main turn so the answer being submitted is genuinely empty.
        main_turn.transcript_raw = ""
        main_turn.transcript_cleaned = ""
        main_turn.metadata = {**main_turn.metadata, "status": "pending"}
        main_turn.save(update_fields=["transcript_raw", "transcript_cleaned", "metadata"])

        with patch("apps.speaking.services.transcribe_turn_audio_with_server_asr", return_value={"ok": False, "status": "missing_audio", "transcript": "", "error": "no audio"}):
            response = self.client.post(
                f"/api/attempts/stream-p3-attempt/turns/{main_turn.turn_id}/complete",
                data={"transcript_raw": "", "stream_follow_up": True},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["re_record_required"])
        self.assertEqual(payload["re_record_reason"], "empty_answer")
        # Points back at the main question, reopened for recording.
        self.assertEqual(payload["next_turn"]["id"], main_turn.turn_id)
        self.assertEqual(payload["next_turn"]["status"], "pending")
        # The follow-up turn must NOT have been seeded into stream_pending.
        follow_up_turn.refresh_from_db()
        self.assertNotEqual(follow_up_turn.metadata.get("prompt", {}).get("backend"), "stream_pending")
        # Attempt is kept active and current on the main turn.
        _attempt.refresh_from_db()
        self.assertEqual(_attempt.status, SpeakingAttempt.Status.STARTED)
        self.assertEqual(_attempt.metadata.get("current_turn"), main_turn.turn_id)

    def test_turn_complete_empty_p3_main_proceeds_when_no_follow_up_follows(self):
        # A 3-main P3 set (no follow_up turns) must NOT trap an empty main in a
        # re-record loop — there is no follow-up to dead-end. The empty main
        # proceeds to the next main and the session can reach scoring.
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id="three-main-p3-attempt",
            mode=SpeakingAttempt.Mode.P3,
            part="p3",
            title="Part 3 practice",
            status=SpeakingAttempt.Status.STARTED,
            metadata={"current_turn": "m1"},
        )
        for seq, turn_id, question in (
            (0, "m1", "What kinds of places are suitable for reflection?"),
            (1, "m2", "Why do some people find it difficult to relax?"),
            (2, "m3", "Should cities provide more quiet public spaces?"),
        ):
            SpeakingTurn.objects.create(
                user=self.user,
                attempt=attempt,
                turn_id=turn_id,
                sequence=seq,
                part="p3",
                question=question,
                metadata={"prompt": {"role": "main", "question": question}},
            )

        with patch("apps.speaking.services.transcribe_turn_audio_with_server_asr", return_value={"ok": False, "status": "missing_audio", "transcript": "", "error": "no audio"}):
            response = self.client.post(
                "/api/attempts/three-main-p3-attempt/turns/m1/complete",
                data={"transcript_raw": ""},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        # No re-record: the empty main advances to the next main question.
        self.assertNotIn("re_record_required", payload)
        self.assertIsNotNone(payload["next_turn"])
        self.assertEqual(payload["next_turn"]["id"], "m2")
        attempt.refresh_from_db()
        self.assertEqual(attempt.metadata.get("current_turn"), "m2")

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
                    "transcript_source": "volcengine_realtime_asr",
                    "realtime_asr_metrics": {
                        "enabled": True,
                        "status": "closed",
                        "asrStatus": "done",
                        "asrConfigured": True,
                        "asrEnabled": True,
                        "asrProvider": "volcengine_realtime_asr",
                        "transcriptSource": "volcengine_realtime_asr",
                        "framesSent": 12,
                        "framesAcked": 12,
                        "bytesSent": 3840,
                        "bytesAcked": 3840,
                        "firstTranscriptMs": 360,
                        "finalTranscriptMs": 980,
                    },
                    "stream_follow_up": True,
                },
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        generate_follow_up.assert_not_called()
        payload = response.json()
        self.assertEqual(payload["turn"]["transcript_source"], "volcengine_realtime_asr")
        self.assertEqual(payload["turn"]["realtime_asr_metrics"]["asr_status"], "done")
        self.assertEqual(payload["turn"]["realtime_asr_metrics"]["first_transcript_ms"], 360)
        self.assertEqual(payload["next_turn"]["prompt"]["backend"], "stream_pending")
        self.assertEqual(payload["next_turn"]["examiner_tts"]["status"], "pending")

    def test_realtime_asr_complete_then_streams_p1_follow_up_and_tts(self):
        SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id="stream-p1-e2e-attempt",
            mode=SpeakingAttempt.Mode.P1,
            part="p1",
            title="Part 1 practice",
            status=SpeakingAttempt.Status.STARTED,
            metadata={"current_turn": "t2"},
        )
        SpeakingTurn.objects.create(
            user=self.user,
            attempt=SpeakingAttempt.objects.get(attempt_id="stream-p1-e2e-attempt"),
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

        complete_response = self.client.post(
            "/api/attempts/stream-p1-e2e-attempt/turns/t2/complete",
            data={
                "transcript_raw": "I study software engineering and do an internship at a tech company.",
                "transcript_source": "volcengine_realtime_asr",
                "realtime_asr_metrics": {
                    "enabled": True,
                    "status": "closed",
                    "asrStatus": "done",
                    "asrConfigured": True,
                    "asrEnabled": True,
                    "asrProvider": "volcengine_realtime_asr",
                    "transcriptSource": "volcengine_realtime_asr",
                    "framesSent": 4,
                    "framesAcked": 4,
                    "bytesSent": 1280,
                    "bytesAcked": 1280,
                    "firstTranscriptMs": 320,
                    "finalTranscriptMs": 860,
                    "doneMs": 920,
                },
                "stream_follow_up": True,
            },
            content_type="application/json",
        )
        self.assertEqual(complete_response.status_code, 200)
        complete_payload = complete_response.json()
        self.assertEqual(complete_payload["turn"]["transcript_source"], "volcengine_realtime_asr")
        self.assertEqual(complete_payload["next_turn"]["prompt"]["backend"], "stream_pending")

        with (
            patch(
                "apps.speaking.services.HttpApiProvider",
                return_value=_StreamingProvider(
                    ["How does ", "your internship help your studies?"],
                    usage={"input_tokens": 16, "output_tokens": 7},
                ),
            ),
            patch(
                "apps.speaking.services.volcengine_tts",
                return_value={
                    "provider": "volcengine",
                    "status": "ready",
                    "audio_url": "/api/tts-audio/examiner/stream-p1-e2e-attempt_t2_followup_examiner.mp3",
                    "content_type": "audio/mpeg",
                },
            ),
        ):
            stream_response = self.client.get(
                "/api/attempts/stream-p1-e2e-attempt/turns/t2/follow-up-stream"
            )
            payloads = _sse_payloads(stream_response)

        self.assertEqual(stream_response.status_code, 200)
        events = [payload["event"] for payload in payloads]
        self.assertIn("chunk", events)
        self.assertIn("question_complete", events)
        self.assertIn("tts_ready", events)
        follow_up = SpeakingTurn.objects.get(attempt__attempt_id="stream-p1-e2e-attempt", turn_id="t2_followup")
        self.assertEqual(follow_up.question, "How does your internship help your studies?")
        self.assertEqual(follow_up.metadata["prompt"]["backend"], "http_api_stream")
        self.assertEqual(follow_up.metadata["prompt"]["provider"], "openai_compatible_http")
        self.assertEqual(follow_up.metadata["prompt"]["model"], "gpt-5.4-mini")
        self.assertEqual(follow_up.metadata["prompt"]["usage"], {"input_tokens": 16, "output_tokens": 7})
        self.assertIn("latency_ms", follow_up.metadata["prompt"])
        self.assertEqual(follow_up.metadata["examiner_tts"]["status"], "ready")

    def test_p1_follow_up_stream_empty_answer_is_rejected_without_fallback_question(self):
        SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id="stream-p1-failure-attempt",
            mode=SpeakingAttempt.Mode.P1,
            part="p1",
            title="Part 1 practice",
            status=SpeakingAttempt.Status.STARTED,
            metadata={"current_turn": "t2"},
        )
        SpeakingTurn.objects.create(
            user=self.user,
            attempt=SpeakingAttempt.objects.get(attempt_id="stream-p1-failure-attempt"),
            turn_id="t2",
            sequence=1,
            part="p1",
            question="Do you work or do you study?",
            transcript_raw="",
            transcript_cleaned="",
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
        with (
            patch("apps.speaking.services.HttpApiProvider", side_effect=RuntimeError("provider unavailable")),
            patch("apps.speaking.services._generate_streamed_follow_up_tts") as generate_tts,
        ):
            response = self.client.get(
                "/api/attempts/stream-p1-failure-attempt/turns/t2/follow-up-stream"
            )

        self.assertEqual(response.status_code, 400)
        generate_tts.assert_not_called()
        self.assertIn("No answer was detected", response.json()["error"])
        self.assertFalse(
            SpeakingTurn.objects.filter(attempt__attempt_id="stream-p1-failure-attempt", turn_id="t2_followup").exists()
        )
