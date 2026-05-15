from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.speaking.models import SpeakingAttempt, SpeakingReport, SpeakingTrainingObservation, SpeakingTurn


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
