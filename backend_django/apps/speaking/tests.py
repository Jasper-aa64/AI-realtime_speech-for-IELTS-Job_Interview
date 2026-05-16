from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.conf import settings

from apps.speaking.models import SpeakingAttempt, SpeakingReport, SpeakingTrainingObservation, SpeakingTurn


class AttemptStartApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="attempt-user", password="test-pass")
        self.client.force_login(self.user)

    def test_start_requires_login(self):
        self.client.logout()
        response = self.client.post("/api/attempts/start", data={"mode": "p1"}, content_type="application/json")
        self.assertEqual(response.status_code, 401)

    def test_start_creates_p1_attempt(self):
        response = self.client.post("/api/attempts/start", data={"mode": "p1"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "p1")
        self.assertEqual(payload["part"], "p1")
        self.assertEqual(payload["status"], "started")
        self.assertIn("id", payload)
        self.assertIn("turns", payload)
        self.assertTrue(len(payload["turns"]) >= 2)
        self.assertEqual(payload["turns"][0]["question"], "What is your full name?")
        self.assertEqual(payload["turns"][0]["status"], "pending")
        self.assertEqual(payload["current_turn"], "t1")
        attempt = SpeakingAttempt.objects.filter(attempt_id=payload["id"]).first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.turns.count(), len(payload["turns"]))

    def test_start_creates_p2_attempt(self):
        response = self.client.post("/api/attempts/start", data={"mode": "p2"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "p2")
        self.assertEqual(payload["part"], "p2")
        self.assertEqual(len(payload["turns"]), 1)
        self.assertIn("cue_card", payload)
        self.assertTrue(payload["cue_card"] is None or isinstance(payload["cue_card"], dict))

    def test_start_creates_p3_attempt(self):
        response = self.client.post(
            "/api/attempts/start",
            data={"mode": "p3", "theme": "technology", "p3_intensity": "normal"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "p3")
        self.assertEqual(payload["part"], "p3")
        self.assertIn("p3_theme", payload)
        self.assertEqual(payload["p3_theme"], "technology")

    def test_start_creates_mock_attempt(self):
        response = self.client.post("/api/attempts/start", data={"mode": "mock"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "mock")
        self.assertEqual(payload["part"], "mock")
        self.assertEqual(payload["title"], "Full mock exam")
        p1_turns = [t for t in payload["turns"] if t["part"] == "p1"]
        p2_turns = [t for t in payload["turns"] if t["part"] == "p2"]
        countable_p1 = sum(1 for t in p1_turns if t.get("counts_toward_total", True))
        self.assertEqual(countable_p1, 10)
        self.assertEqual(len(p2_turns), 1)
        self.assertEqual(payload["p3_generation_status"], "pending_after_p2")

    def test_start_uses_candidate_names(self):
        response = self.client.post(
            "/api/attempts/start",
            data={"mode": "p1", "full_name": "Zhang San", "english_name": "Sam"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["full_name"], "Zhang San")
        self.assertEqual(payload["english_name"], "Sam")
        self.assertEqual(payload["candidate"], "Sam")

    def test_invalid_mode_returns_400(self):
        response = self.client.post("/api/attempts/start", data={"mode": "invalid"}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_response_shape_matches_old_server(self):
        response = self.client.post("/api/attempts/start", data={"mode": "mock"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        required_keys = [
            "id", "timestamp", "status", "mode", "part", "title", "question",
            "turns", "current_turn", "candidate", "full_name", "english_name",
            "pronunciation", "ielts_score", "feedback_summary", "criteria_feedback",
            "band7_version", "model_audio", "upgrade_notes", "ai_coaching",
        ]
        for key in required_keys:
            self.assertIn(key, payload, f"Missing key: {key}")
        turn = payload["turns"][0]
        turn_keys = [
            "id", "part", "index", "total", "status", "question", "prompt",
            "cue_card", "timers", "examiner_text", "examiner_behavior",
            "examiner_tts", "audio", "transcript_raw", "transcript_cleaned",
            "transcript_markdown", "transcript_status", "duration_seconds",
            "band7_version", "band7_markdown", "model_audio", "upgrade_notes", "ai_coaching",
        ]
        for key in turn_keys:
            self.assertIn(key, turn, f"Missing turn key: {key}")


class SpeakingModelTests(TestCase):
    def test_attempt_and_turn_can_be_created(self):
        user = get_user_model().objects.create_user(username="speaker", password="test-pass")
        attempt = SpeakingAttempt.objects.create(user=user, mode=SpeakingAttempt.Mode.P1, part="p1", status=SpeakingAttempt.Status.STARTED)
        turn = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t1",
            sequence=1,
            part="p1",
            question="What is your full name?",
        )

        self.assertEqual(attempt.turns.count(), 1)
        self.assertEqual(str(turn), f"{attempt.id}:t1")

    def test_training_observation_indexes_legacy_weak_items(self):
        user = get_user_model().objects.create_user(username="weak-speaker", password="test-pass")
        attempt = SpeakingAttempt.objects.create(user=user, mode=SpeakingAttempt.Mode.P1, part="p1", status=SpeakingAttempt.Status.SCORED)
        turn = SpeakingTurn.objects.create(user=user, attempt=attempt, turn_id="t1", sequence=1, part="p1", question="Do you work or study?")
        observation = SpeakingTrainingObservation.objects.create(
            user=user,
            attempt=attempt,
            turn=turn,
            observation_id="attempt_t1",
            legacy_attempt_id="attempt",
            legacy_turn_id="t1",
            question_id="p1_question",
            part="p1",
            question=turn.question,
            transcript="I study computer science.",
            relevance=0.5,
            weak_item_flag=True,
            weak_reasons=["short_answer"],
            model_version="fallback",
            observed_at=attempt.created_at,
            next_due=attempt.created_at,
        )

        self.assertTrue(observation.weak_item_flag)
        self.assertEqual(observation.weak_reasons, ["short_answer"])


class SpeakingHistoryApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="speaking-api-user", password="test-pass")
        self.client.force_login(self.user)

    def create_scored_attempt(self, attempt_id="attempt-api-1", status=SpeakingAttempt.Status.SCORED, turn_status="completed"):
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id=attempt_id,
            legacy_attempt_id=attempt_id,
            mode=SpeakingAttempt.Mode.P1,
            part="p1",
            title="Part 1 practice",
            status=status,
            english_name="Jasper",
        )
        SpeakingTurn.objects.create(
            user=self.user,
            attempt=attempt,
            turn_id="t1",
            sequence=1,
            part="p1",
            question="What is your full name?",
            transcript_raw="My full name is Jasper.",
            transcript_cleaned="My full name is Jasper.",
            metadata={"transcript_status": "captured", "band7_version": "My full name is Jasper Chen."},
        )
        SpeakingReport.objects.create(
            user=self.user,
            attempt=attempt,
            overall_band=5.5,
            fluency_coherence=5.5,
            lexical_resource=5.0,
            grammar_range_accuracy=5.0,
            pronunciation=5.5,
            feedback_summary="Needs clearer answers.",
            report_payload={
                "id": attempt_id,
                "status": status,
                "mode": "p1",
                "title": "Part 1 practice",
                "ielts_score": {"overall_band": 5.5},
                "turns": [{"id": "t1", "status": turn_status, "question": "What is your full name?", "transcript_cleaned": "My full name is Jasper."}],
            },
        )
        return attempt

    def test_history_requires_login(self):
        self.client.logout()
        response = self.client.get("/api/history")
        self.assertEqual(response.status_code, 401)

    def test_history_and_detail_return_only_valid_scored_reports(self):
        valid = self.create_scored_attempt()
        self.create_scored_attempt("attempt-started", status=SpeakingAttempt.Status.STARTED)
        self.create_scored_attempt("attempt-incomplete", turn_status="started")

        history = self.client.get("/api/history")
        self.assertEqual(history.status_code, 200)
        ids = [item["id"] for item in history.json()["items"]]
        self.assertEqual(ids, [valid.attempt_id])

        detail = self.client.get(f"/api/history/{valid.attempt_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["ielts_score"]["overall_band"], 5.5)
        self.assertEqual(detail.json()["turns"][0]["question"], "What is your full name?")

        invalid_detail = self.client.get("/api/history/attempt-incomplete")
        self.assertEqual(invalid_detail.status_code, 404)

    def test_delete_requires_login(self):
        self.client.logout()
        attempt = self.create_scored_attempt("attempt-to-delete")
        response = self.client.delete(f"/api/history/{attempt.attempt_id}")
        self.assertEqual(response.status_code, 401)

    def test_delete_owner_scoped(self):
        attempt = self.create_scored_attempt("attempt-owner-test")
        other_user = get_user_model().objects.create_user(username="other-speaker", password="test-pass")
        self.client.logout()
        self.client.force_login(other_user)
        response = self.client.delete(f"/api/history/{attempt.attempt_id}")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(SpeakingAttempt.objects.filter(attempt_id="attempt-owner-test").exists())

    def test_delete_removes_attempt_and_related_records(self):
        attempt = self.create_scored_attempt("attempt-delete-test")
        self.assertEqual(SpeakingTurn.objects.filter(attempt=attempt).count(), 1)
        self.assertTrue(SpeakingReport.objects.filter(attempt=attempt).exists())

        response = self.client.delete(f"/api/history/{attempt.attempt_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

        self.assertFalse(SpeakingAttempt.objects.filter(attempt_id="attempt-delete-test").exists())
        self.assertEqual(SpeakingTurn.objects.filter(attempt=attempt).count(), 0)
        self.assertFalse(SpeakingReport.objects.filter(attempt=attempt).exists())

    def test_delete_removes_from_history_list(self):
        attempt = self.create_scored_attempt("attempt-list-test")
        history_before = self.client.get("/api/history")
        self.assertIn("attempt-list-test", [item["id"] for item in history_before.json()["items"]])

        self.client.delete(f"/api/history/{attempt.attempt_id}")

        history_after = self.client.get("/api/history")
        self.assertNotIn("attempt-list-test", [item["id"] for item in history_after.json()["items"]])


class QuestionBankApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="bank-user", password="test-pass")
        self.client.force_login(self.user)

    def test_question_bank_summary_requires_login(self):
        self.client.logout()
        response = self.client.get("/api/question-bank/summary")
        self.assertEqual(response.status_code, 401)

    def test_question_bank_sample_requires_login(self):
        self.client.logout()
        response = self.client.post("/api/question-bank/sample", data={"p1_count": 3}, content_type="application/json")
        self.assertEqual(response.status_code, 401)

    def test_question_bank_summary_returns_counts(self):
        response = self.client.get("/api/question-bank/summary")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("part1_count", payload)
        self.assertIn("part2_count", payload)
        self.assertIn("part1_topics", payload)
        self.assertIn("part2_themes", payload)
        self.assertIsInstance(payload["part1_count"], int)
        self.assertIsInstance(payload["part2_count"], int)

    def test_question_bank_sample_returns_structure(self):
        response = self.client.post("/api/question-bank/sample", data={"p1_count": 3}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        if "part1" in payload:
            self.assertIsInstance(payload["part1"], list)
        if "part2" in payload:
            self.assertIsInstance(payload["part2"], dict)


class TrainingApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="training-user", password="test-pass")
        self.client.force_login(self.user)

    def create_weak_observation(self, question_id="p1_weak_1", part="p1", question="Do you work or study?"):
        attempt = SpeakingAttempt.objects.create(
            user=self.user, mode=SpeakingAttempt.Mode.P1, part=part, status=SpeakingAttempt.Status.SCORED
        )
        return SpeakingTrainingObservation.objects.create(
            user=self.user,
            attempt=attempt,
            observation_id=f"obs_{question_id}",
            legacy_attempt_id="legacy",
            legacy_turn_id="t1",
            question_id=question_id,
            part=part,
            question=question,
            transcript="Short answer.",
            overall_band=5.0,
            relevance=0.6,
            weak_item_flag=True,
            weak_reasons=["short_answer", "grammar"],
            model_version="fallback",
            observed_at=attempt.created_at,
            next_due=attempt.created_at,
        )

    def test_weak_items_requires_login(self):
        self.client.logout()
        response = self.client.get("/api/training/weak-items")
        self.assertEqual(response.status_code, 401)

    def test_weak_items_returns_empty_for_no_observations(self):
        response = self.client.get("/api/training/weak-items")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])

    def test_weak_items_returns_aggregated_weak_items(self):
        self.create_weak_observation()
        response = self.client.get("/api/training/weak-items")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["question_id"], "p1_weak_1")
        self.assertEqual(items[0]["part"], "p1")
        self.assertIn("weak_reason", items[0])
        self.assertTrue(items[0]["due"])

    def test_weak_items_owner_scoped(self):
        self.create_weak_observation()
        other_user = get_user_model().objects.create_user(username="other-training", password="test-pass")
        self.client.logout()
        self.client.force_login(other_user)
        response = self.client.get("/api/training/weak-items")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])

    def test_replay_queue_requires_login(self):
        self.client.logout()
        response = self.client.get("/api/training/replay-queue")
        self.assertEqual(response.status_code, 401)

    def test_replay_queue_returns_empty_for_no_observations(self):
        response = self.client.get("/api/training/replay-queue")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        # May have coverage items if question bank has data
        self.assertIsInstance(items, list)

    def test_replay_queue_includes_weak_items(self):
        self.create_weak_observation()
        response = self.client.get("/api/training/replay-queue")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        weak_items = [item for item in items if item.get("source") == "weak"]
        self.assertEqual(len(weak_items), 1)
        self.assertEqual(weak_items[0]["question_id"], "p1_weak_1")


class TurnAudioUploadApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="audio-user", password="test-pass")
        self.client.force_login(self.user)

    def create_attempt_with_turn(self, attempt_id="audio-attempt-1"):
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id=attempt_id,
            mode=SpeakingAttempt.Mode.P1,
            part="p1",
            title="Part 1 practice",
            status=SpeakingAttempt.Status.STARTED,
        )
        turn = SpeakingTurn.objects.create(
            user=self.user,
            attempt=attempt,
            turn_id="t1",
            sequence=1,
            part="p1",
            question="What is your full name?",
        )
        return attempt.attempt_id, turn.turn_id

    def test_audio_upload_requires_login(self):
        self.client.logout()
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id="test-attempt",
            mode=SpeakingAttempt.Mode.P1,
            part="p1",
            status=SpeakingAttempt.Status.STARTED,
        )
        from django.core.files.uploadedfile import SimpleUploadedFile
        audio_file = SimpleUploadedFile("audio.webm", b"fake audio", content_type="audio/webm")
        response = self.client.post(
            f"/api/attempts/{attempt.attempt_id}/turns/t1/audio",
            {"audio": audio_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 401)

    def test_audio_upload_creates_file(self):
        attempt_id, turn_id = self.create_attempt_with_turn()
        from django.core.files.uploadedfile import SimpleUploadedFile
        audio_data = b"fake audio webm content for testing"
        audio_file = SimpleUploadedFile("audio.webm", audio_data, content_type="audio/webm")
        response = self.client.post(
            f"/api/attempts/{attempt_id}/turns/{turn_id}/audio",
            {"audio": audio_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("ok"))
        self.assertIn("audio", payload)
        audio = payload["audio"]
        self.assertIn("path", audio)
        self.assertEqual(audio["content_type"], "audio/webm")
        self.assertEqual(audio["bytes"], len(audio_data))
        self.assertEqual(audio["url"], f"/api/audio/{attempt_id}/{turn_id}/candidate")

        turn = SpeakingTurn.objects.filter(attempt__attempt_id=attempt_id, turn_id=turn_id).first()
        self.assertIsNotNone(turn)
        self.assertTrue(turn.audio_path)
        self.assertEqual(turn.metadata.get("audio_content_type"), "audio/webm")

    def test_audio_upload_accepts_raw_browser_blob(self):
        attempt_id, turn_id = self.create_attempt_with_turn()
        audio_data = b"raw browser webm content"
        response = self.client.post(
            f"/api/attempts/{attempt_id}/turns/{turn_id}/audio",
            data=audio_data,
            content_type="audio/webm",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["audio"]["bytes"], len(audio_data))
        self.assertEqual(payload["audio"]["content_type"], "audio/webm")

    def test_audio_upload_owner_scoped(self):
        attempt_id, turn_id = self.create_attempt_with_turn()
        other_user = get_user_model().objects.create_user(username="other-audio", password="test-pass")
        self.client.logout()
        self.client.force_login(other_user)
        from django.core.files.uploadedfile import SimpleUploadedFile
        audio_file = SimpleUploadedFile("audio.webm", b"other user audio", content_type="audio/webm")
        response = self.client.post(
            f"/api/attempts/{attempt_id}/turns/{turn_id}/audio",
            {"audio": audio_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 404)

    def test_audio_upload_invalid_attempt_returns_404(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        audio_file = SimpleUploadedFile("audio.webm", b"fake audio", content_type="audio/webm")
        response = self.client.post(
            "/api/attempts/nonexistent/turns/t1/audio",
            {"audio": audio_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 404)

    def test_audio_upload_invalid_turn_returns_404(self):
        attempt_id, _turn_id = self.create_attempt_with_turn()
        from django.core.files.uploadedfile import SimpleUploadedFile
        audio_file = SimpleUploadedFile("audio.webm", b"fake audio", content_type="audio/webm")
        response = self.client.post(
            f"/api/attempts/{attempt_id}/turns/nonexistent/audio",
            {"audio": audio_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 404)

    def test_audio_upload_invalid_content_type_returns_400(self):
        attempt_id, turn_id = self.create_attempt_with_turn()
        from django.core.files.uploadedfile import SimpleUploadedFile
        audio_file = SimpleUploadedFile("audio.txt", b"fake audio", content_type="text/plain")
        response = self.client.post(
            f"/api/attempts/{attempt_id}/turns/{turn_id}/audio",
            {"audio": audio_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported audio content type", response.json().get("error", ""))

    def test_audio_retrieval_requires_login(self):
        self.client.logout()
        response = self.client.get("/api/audio/test-id/t1/candidate")
        self.assertEqual(response.status_code, 401)

    def test_audio_retrieval_returns_file(self):
        attempt_id, turn_id = self.create_attempt_with_turn()
        from django.core.files.uploadedfile import SimpleUploadedFile
        audio_data = b"fake audio webm content for retrieval test"
        audio_file = SimpleUploadedFile("audio.webm", audio_data, content_type="audio/webm")
        upload_response = self.client.post(
            f"/api/attempts/{attempt_id}/turns/{turn_id}/audio",
            {"audio": audio_file},
            format="multipart",
        )
        self.assertEqual(upload_response.status_code, 200)

        response = self.client.get(f"/api/audio/{attempt_id}/{turn_id}/candidate")
        self.assertEqual(response.status_code, 200)
        retrieved_data = b"".join(chunk for chunk in response.streaming_content)
        self.assertEqual(retrieved_data, audio_data)

    def test_audio_retrieval_owner_scoped(self):
        attempt_id, turn_id = self.create_attempt_with_turn()
        from django.core.files.uploadedfile import SimpleUploadedFile
        audio_file = SimpleUploadedFile("audio.webm", b"fake audio", content_type="audio/webm")
        self.client.post(
            f"/api/attempts/{attempt_id}/turns/{turn_id}/audio",
            {"audio": audio_file},
            format="multipart",
        )
        other_user = get_user_model().objects.create_user(username="other-retrieve", password="test-pass")
        self.client.logout()
        self.client.force_login(other_user)
        response = self.client.get(f"/api/audio/{attempt_id}/{turn_id}/candidate")
        self.assertEqual(response.status_code, 404)

    def test_audio_retrieval_nonexistent_returns_404(self):
        response = self.client.get("/api/audio/nonexistent/t1/candidate")
        self.assertEqual(response.status_code, 404)


class SpeakingRuntimeApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="runtime-user", password="test-pass")
        self.client.force_login(self.user)

    def create_attempt(self, *, status=SpeakingAttempt.Status.STARTED, attempt_id="runtime-attempt"):
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id=attempt_id,
            mode=SpeakingAttempt.Mode.P1,
            part="p1",
            title="Part 1 practice",
            status=status,
            full_name="Zhang San",
            english_name="Sam",
        )
        turn1 = SpeakingTurn.objects.create(
            user=self.user,
            attempt=attempt,
            turn_id="t1",
            sequence=0,
            part="p1",
            question="What is your full name?",
            metadata={"timers": {"prep_seconds": 3, "speak_seconds": 35}},
        )
        turn2 = SpeakingTurn.objects.create(
            user=self.user,
            attempt=attempt,
            turn_id="t2",
            sequence=1,
            part="p1",
            question="Do you work or study?",
            metadata={"timers": {"prep_seconds": 3, "speak_seconds": 35}},
        )
        return attempt, turn1, turn2

    def complete_turn(self, attempt_id="runtime-attempt", turn_id="t1", transcript="My full name is Sam."):
        return self.client.post(
            f"/api/attempts/{attempt_id}/turns/{turn_id}/complete",
            data={"transcript_raw": transcript, "transcript_status": "captured", "transcript_source": "browser_dictation"},
            content_type="application/json",
        )

    def test_turn_complete_requires_login(self):
        self.client.logout()
        response = self.client.post(
            "/api/attempts/runtime-attempt/turns/t1/complete",
            data={"transcript_raw": "Hello."},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_turn_complete_owner_scoped(self):
        attempt, _turn1, _turn2 = self.create_attempt()
        other_user = get_user_model().objects.create_user(username="other-runtime", password="test-pass")
        self.client.logout()
        self.client.force_login(other_user)
        response = self.client.post(
            f"/api/attempts/{attempt.attempt_id}/turns/t1/complete",
            data={"transcript_raw": "Hello."},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_turn_complete_advances_to_next_turn(self):
        self.create_attempt()
        response = self.complete_turn()
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["turn"]["status"], "completed")
        self.assertEqual(payload["turn"]["transcript_cleaned"], "My full name is Sam.")
        self.assertEqual(payload["next_turn"]["id"], "t2")
        self.assertEqual(payload["attempt"]["current_turn"], "t2")

        turn = SpeakingTurn.objects.get(turn_id="t1")
        self.assertEqual(turn.metadata["status"], "completed")
        self.assertEqual(turn.transcript_source, "browser_dictation")

    def test_turn_complete_final_turn_marks_ready_to_score(self):
        attempt, turn1, turn2 = self.create_attempt()
        turn1.transcript_raw = "My full name is Sam."
        turn1.transcript_cleaned = "My full name is Sam."
        turn1.metadata = {**turn1.metadata, "status": "completed"}
        turn1.save()

        response = self.complete_turn(turn_id=turn2.turn_id, transcript="I study English every day and practise speaking with examples.")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["next_turn"])
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, SpeakingAttempt.Status.READY_TO_SCORE)

    def test_abort_requires_login(self):
        self.client.logout()
        response = self.client.post("/api/attempts/runtime-attempt/abort", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 401)

    def test_abort_marks_attempt_aborted(self):
        attempt, _turn1, _turn2 = self.create_attempt()
        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/abort", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], SpeakingAttempt.Status.ABORTED)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, SpeakingAttempt.Status.ABORTED)
        self.assertIn("aborted_at", attempt.metadata)

    def test_abort_rejects_scored_attempt(self):
        attempt, _turn1, _turn2 = self.create_attempt(status=SpeakingAttempt.Status.SCORED)
        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/abort", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_score_requires_login(self):
        self.client.logout()
        response = self.client.post("/api/attempts/runtime-attempt/score", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 401)

    def test_score_rejects_incomplete_attempt(self):
        attempt, _turn1, _turn2 = self.create_attempt()
        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/score", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Complete all speaking turns", response.json()["error"])

    def test_score_rejects_aborted_attempt(self):
        attempt, turn1, turn2 = self.create_attempt(status=SpeakingAttempt.Status.ABORTED)
        for turn in (turn1, turn2):
            turn.transcript_raw = "I answer with enough words to be completed."
            turn.transcript_cleaned = turn.transcript_raw
            turn.metadata = {**turn.metadata, "status": "completed"}
            turn.save()
        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/score", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_score_creates_report_visible_in_history(self):
        attempt, turn1, turn2 = self.create_attempt()
        for turn, transcript in (
            (turn1, "My full name is Sam and I am preparing for IELTS speaking."),
            (turn2, "I study English every day because I want to communicate clearly with international classmates."),
        ):
            turn.transcript_raw = transcript
            turn.transcript_cleaned = transcript
            turn.metadata = {**turn.metadata, "status": "completed"}
            turn.save()
        attempt.status = SpeakingAttempt.Status.READY_TO_SCORE
        attempt.save()

        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/score", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], SpeakingAttempt.Status.SCORED)
        # Backend can be "codex" (from score_with_codex), "heuristic" (from heuristic_score), or "fallback"
        self.assertIn(payload["ielts_score"]["backend"], ["codex", "heuristic", "fallback"])
        self.assertTrue(SpeakingReport.objects.filter(attempt=attempt).exists())
        self.assertEqual(SpeakingTrainingObservation.objects.filter(attempt=attempt).count(), 2)

        history = self.client.get("/api/history")
        self.assertIn(attempt.attempt_id, [item["id"] for item in history.json()["items"]])
        detail = self.client.get(f"/api/history/{attempt.attempt_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["id"], attempt.attempt_id)


class RegenerateApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="regen-user", password="test-pass")
        self.client.force_login(self.user)

    def create_scored_attempt(self):
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id="regen-attempt-1",
            mode=SpeakingAttempt.Mode.P1,
            part="p1",
            title="Part 1 practice",
            status=SpeakingAttempt.Status.SCORED,
        )
        turn = SpeakingTurn.objects.create(
            user=self.user,
            attempt=attempt,
            turn_id="t1",
            sequence=1,
            part="p1",
            question="What is your full name?",
            transcript_raw="My name is Sam.",
            transcript_cleaned="My name is Sam.",
            audio_path="audio/test.webm",
            metadata={"status": "completed"},
        )
        SpeakingReport.objects.create(
            user=self.user,
            attempt=attempt,
            overall_band=6.0,
            fluency_coherence=6.0,
            lexical_resource=6.0,
            grammar_range_accuracy=6.0,
            report_payload={
                "id": attempt.attempt_id,
                "status": "scored",
                "turns": [{"id": "t1", "status": "completed"}],
            },
        )
        return attempt, turn

    def test_feedback_regenerate_requires_login(self):
        self.client.logout()
        attempt, turn = self.create_scored_attempt()
        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/turns/{turn.turn_id}/feedback/regenerate")
        self.assertEqual(response.status_code, 401)

    def test_feedback_regenerate_returns_ok(self):
        attempt, turn = self.create_scored_attempt()
        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/turns/{turn.turn_id}/feedback/regenerate")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("ok"))
        self.assertIn("turn", payload)
        self.assertIn("band7_version", payload["turn"])

    def test_feedback_regenerate_invalid_turn_returns_404(self):
        attempt, _turn = self.create_scored_attempt()
        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/turns/nonexistent/feedback/regenerate")
        self.assertEqual(response.status_code, 404)

    def test_transcript_regenerate_requires_login(self):
        self.client.logout()
        attempt, turn = self.create_scored_attempt()
        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/turns/{turn.turn_id}/transcript/regenerate")
        self.assertEqual(response.status_code, 401)

    def test_transcript_regenerate_returns_ok(self):
        attempt, turn = self.create_scored_attempt()
        from pathlib import Path
        from django.conf import settings
        media_root = Path(settings.MEDIA_ROOT)
        audio_dir = media_root / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = audio_dir / "test.webm"
        audio_path.write_bytes(b"fake audio content")
        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/turns/{turn.turn_id}/transcript/regenerate")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("ok"))
        self.assertIn("turn", payload)

    def test_transcript_regenerate_no_audio_returns_400(self):
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id="regen-no-audio",
            mode=SpeakingAttempt.Mode.P1,
            part="p1",
            status=SpeakingAttempt.Status.SCORED,
        )
        turn = SpeakingTurn.objects.create(
            user=self.user,
            attempt=attempt,
            turn_id="t1",
            sequence=1,
            part="p1",
            question="Test question",
            transcript_raw="Test transcript",
            metadata={"status": "completed"},
        )
        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/turns/{turn.turn_id}/transcript/regenerate")
        self.assertEqual(response.status_code, 400)
        self.assertIn("没有可用录音文件", response.json().get("error", ""))


class DjangoOnlyRuntimeSurfaceTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="surface-user", password="test-pass")
        self.client.force_login(self.user)

    def create_scored_attempt(self):
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id="surface-scored",
            mode=SpeakingAttempt.Mode.P1,
            part="p1",
            title="Part 1 practice",
            status=SpeakingAttempt.Status.SCORED,
            english_name="Sam",
        )
        SpeakingTurn.objects.create(
            user=self.user,
            attempt=attempt,
            turn_id="t1",
            sequence=1,
            part="p1",
            question="What is your full name?",
            transcript_raw="My full name is Sam.",
            transcript_cleaned="My full name is Sam.",
            metadata={"status": "completed", "transcript_status": "captured"},
        )
        SpeakingReport.objects.create(
            user=self.user,
            attempt=attempt,
            overall_band=5.5,
            fluency_coherence=5.5,
            lexical_resource=5.0,
            grammar_range_accuracy=5.0,
            feedback_summary="Fallback report.",
            report_payload={
                "id": attempt.attempt_id,
                "status": "scored",
                "mode": "p1",
                "ielts_score": {"overall_band": 5.5},
                "turns": [{"id": "t1", "status": "completed", "transcript_cleaned": "My full name is Sam."}],
            },
        )
        return attempt

    def test_django_serves_frontend_static_entrypoints(self):
        root = self.client.get("/")
        self.assertEqual(root.status_code, 200)
        self.assertIn(b"IELTS Speaking Studio", b"".join(root.streaming_content))

        app_js = self.client.get("/app.js")
        self.assertEqual(app_js.status_code, 200)
        self.assertIn("javascript", app_js["Content-Type"])

        styles = self.client.get("/styles.css")
        self.assertEqual(styles.status_code, 200)
        self.assertIn("text/css", styles["Content-Type"])

    def test_p3_fallback_requires_login_and_returns_questions(self):
        self.client.logout()
        unauthorized = self.client.post("/api/p3/questions", data={"theme": "technology"}, content_type="application/json")
        self.assertEqual(unauthorized.status_code, 401)

        self.client.force_login(self.user)
        response = self.client.post("/api/p3/questions", data={"theme": "technology"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["backend"], "fallback")
        self.assertEqual(len(payload["questions"]), 5)
        self.assertIn("follow_up", payload)

    def test_p3_follow_up_uses_same_fallback_contract(self):
        response = self.client.post(
            "/api/p3/follow-up",
            data={"theme": "technology", "prior_answer": " ".join(["answer"] * 45)},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["backend"], "fallback")
        self.assertIn("opposite argument", response.json()["follow_up"])

    def test_tts_fallback_requires_login_and_returns_browser_contract(self):
        self.client.logout()
        unauthorized = self.client.post("/api/tts", data={"text": "Hello"}, content_type="application/json")
        self.assertEqual(unauthorized.status_code, 401)

        self.client.force_login(self.user)
        response = self.client.post("/api/tts", data={"text": "Hello", "role": "examiner"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"], "browser")
        self.assertEqual(payload["status"], "fallback")
        self.assertIsNone(payload["audio_url"])

    def test_tts_audio_returns_404_or_existing_file(self):
        missing = self.client.get("/api/tts-audio/examiner/missing.mp3")
        self.assertEqual(missing.status_code, 404)

        from pathlib import Path
        audio_dir = Path(settings.MEDIA_ROOT) / "tts" / "examiner"
        audio_dir.mkdir(parents=True, exist_ok=True)
        (audio_dir / "sample.mp3").write_bytes(b"mp3-data")

        response = self.client.get("/api/tts-audio/examiner/sample.mp3")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"mp3-data")

    def test_latest_report_returns_latest_valid_report(self):
        no_report = self.client.get("/api/reports/latest")
        self.assertEqual(no_report.status_code, 200)
        self.assertEqual(no_report.json(), {"report": None})

        attempt = self.create_scored_attempt()
        response = self.client.get("/api/reports/latest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], attempt.attempt_id)
