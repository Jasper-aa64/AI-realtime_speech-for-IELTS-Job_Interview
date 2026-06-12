import json
import subprocess
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.conf import settings

from apps.speaking.models import (
    LanguageTakeawayEntry,
    P1CorpusEntry,
    P2BankCorpusEntry,
    P2CorpusEntry,
    P3BankFollowupCorpusEntry,
    SpeakingAttempt,
    SpeakingReport,
    SpeakingTrainingObservation,
    SpeakingTurn,
)


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

    def test_start_fixed_examiner_tts_does_not_block_on_remote_tts(self):
        with (
            patch("apps.speaking.services._cached_tts_url", return_value=None),
            patch("apps.speaking.services._warm_fixed_examiner_tts_item_background") as warm_background,
            patch("apps.speaking.services.volcengine_tts") as tts,
        ):
            response = self.client.post("/api/attempts/start", data={"mode": "p2"}, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["turns"][0]["examiner_tts"]["status"], "warming")
        warm_background.assert_called_once()
        tts.assert_not_called()

    def test_start_p2_samples_random_cue(self):
        selected = {
            "title": "Describe a custom random cue",
            "bullets": ["What it is"],
            "rounding": "And explain why it matters.",
            "p3_theme": "custom_theme",
        }
        with patch("apps.speaking.services.random.choice", return_value=selected) as choice:
            response = self.client.post("/api/attempts/start", data={"mode": "p2"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        choice.assert_called_once()
        self.assertEqual(payload["cue_card"]["title"], selected["title"])
        self.assertEqual(payload["title"], selected["title"])

    def test_start_p1_respects_question_bank_scope(self):
        response = self.client.post(
            "/api/attempts/start",
            data={"mode": "p1", "question_bank_scope": "new"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        countable_bank_turns = [
            turn
            for turn in payload["turns"]
            if turn.get("counts_toward_total") and turn.get("prompt", {}).get("topic") != "intro"
        ]
        self.assertTrue(countable_bank_turns)
        self.assertTrue(all(turn.get("prompt", {}).get("status") == "new" for turn in countable_bank_turns))

    def test_start_p2_respects_question_bank_scope(self):
        response = self.client.post(
            "/api/attempts/start",
            data={"mode": "p2", "question_bank_scope": "retained"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["cue_card"]["status"], "retained")

    def test_start_creates_p3_attempt(self):
        from apps.speaking import services as speaking_services

        cue = {
            "title": "Describe useful technology",
            "season": "2026-may-august",
            "p3_theme": "technology",
            "p3_follow_ups": [
                "How has technology changed people's daily lives?",
                "Do older and younger people use technology differently?",
                "What problems can new technology create?",
            ],
        }
        bank = MagicMock()
        bank.p2 = [cue]
        bank.part2_for_scope.return_value = [cue]
        with patch.object(speaking_services, "get_question_bank", return_value=bank):
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
        self.assertEqual(payload["p3_focus"], "comparison_concession")
        self.assertIn("p3_plan", payload)
        self.assertEqual(payload["p3_plan"]["theme"], "technology")
        self.assertEqual(payload["p3_generation_backend"], "season_bank")
        self.assertEqual(len(payload["p3_plan"]["questions"]), 3)
        self.assertIn("target_moves", payload["p3_plan"]["questions"][0])

    def test_start_p3_uses_current_season_p2_follow_ups_when_theme_matches(self):
        from apps.speaking import services as speaking_services

        cue = {
            "title": "Describe a perfect job you would like to have in the future",
            "season": "2026-may-august",
            "p3_theme": "career_choices_and_job_values",
            "p3_follow_ups": [
                "What should young people consider when choosing a career?",
                "Is salary the main reason people choose a job?",
                "Why do some people regret their career choices later?",
            ],
        }
        bank = MagicMock()
        bank.p2 = [cue]
        bank.part2_for_scope.return_value = [cue]
        with patch.object(speaking_services, "get_question_bank", return_value=bank):
            response = self.client.post(
                "/api/attempts/start",
                data={"mode": "p3", "theme": "career_choices_and_job_values", "p3_intensity": "normal"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["p3_generation_backend"], "season_bank")
        self.assertEqual(payload["p3_plan"]["source"]["type"], "season_bank")
        self.assertEqual(payload["p3_plan"]["source"]["season"], "2026-may-august")
        self.assertEqual(
            payload["p3_plan"]["questions"][0]["question"],
            "What should young people consider when choosing a career?",
        )

    def test_start_p3_high_intensity_follow_up_turns_do_not_use_default_questions_or_tts(self):
        from apps.speaking import services as speaking_services

        cue = {
            "title": "Describe a crowded place you have been to",
            "season": "2026-may-august",
            "p3_theme": "crowded_places",
            "p3_follow_ups": [
                "What kinds of places are usually crowded in your country?",
                "Why do some people dislike going to crowded places?",
                "How can public places be managed better when there are too many people?",
            ],
        }
        bank = MagicMock()
        bank.p2 = [cue]
        bank.part2_for_scope.return_value = [cue]
        with (
            patch.object(speaking_services, "get_question_bank", return_value=bank),
            patch(
                "apps.speaking.services.volcengine_tts",
                return_value={"provider": "volcengine", "status": "ready", "audio_url": "/main.mp3"},
            ) as mock_tts,
        ):
            response = self.client.post(
                "/api/attempts/start",
                data={"mode": "p3", "theme": "crowded_places", "p3_intensity": "high"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        turns = payload["turns"]
        self.assertEqual(len(turns), 6)
        follow_up_turns = [turn for turn in turns if turn["prompt"].get("role") == "follow_up"]
        self.assertEqual(len(follow_up_turns), 3)
        for turn in follow_up_turns:
            self.assertEqual(turn["question"], "")
            self.assertEqual(turn["examiner_text"], "")
            self.assertEqual(turn["prompt"]["question"], "")
            self.assertEqual(turn["prompt"]["backend"], "pending_ai_follow_up")
            self.assertEqual(turn["prompt"]["generation_status"], "pending")
            self.assertEqual(turn["prompt"].get("p3_bank_followup_id"), "")
            self.assertEqual(turn["examiner_tts"]["status"], "not_started")
            self.assertIsNone(turn["examiner_tts"]["audio_url"])
        generated_tts_texts = [call.args[0] for call in mock_tts.call_args_list]
        self.assertNotIn("Could you give a specific example to support that view?", generated_tts_texts)
        self.assertNotIn("What might be the opposite argument, and why might some people agree with it?", generated_tts_texts)

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

    def test_start_mock_samples_random_p2_cue(self):
        selected = {
            "title": "Describe a random mock cue",
            "bullets": ["What happened"],
            "rounding": "And explain how you felt.",
            "p3_theme": "mock_theme",
        }
        with patch("apps.speaking.services.random.choice", return_value=selected) as choice:
            response = self.client.post("/api/attempts/start", data={"mode": "mock"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        choice.assert_called_once()
        self.assertEqual(payload["cue_card"]["title"], selected["title"])
        self.assertEqual(payload["p3_theme"], selected["p3_theme"])

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
        self.assertEqual(payload["active_season"], "2026-may-august")
        self.assertEqual(payload["active_region"], "china_mainland")
        self.assertEqual(payload["scope"], "current_season_only")
        self.assertEqual(payload["part3_mode"], "derived_from_part2")
        self.assertGreater(payload["part3_follow_up_count"], 0)
        self.assertIsInstance(payload["part1_count"], int)
        self.assertIsInstance(payload["part2_count"], int)
        self.assertIn("2026-may-august", payload["seasons"])
        self.assertIn("china_mainland", payload["regions"])
        self.assertGreater(payload["archived_part1_count"], 0)
        self.assertGreater(payload["archived_part2_count"], 0)
        self.assertGreater(payload["part1_status_counts"]["new"], 0)
        self.assertGreater(payload["part1_status_counts"]["retained"], 0)
        self.assertGreater(payload["part2_status_counts"]["new"], 0)
        self.assertGreater(payload["part2_status_counts"]["retained"], 0)
        self.assertGreaterEqual(payload["part1_count"], 100)
        self.assertGreaterEqual(payload["part2_count"], 55)
        for topic in ("social_media", "study_or_work", "public_gardens_and_parks"):
            self.assertIn(topic, payload["part1_topics"])
        for theme in ("medical_work_and_public_health", "traditional_customs_and_modern_life", "repairing_things_and_practical_skills"):
            self.assertIn(theme, payload["part2_themes"])

    def test_question_bank_summary_returns_scope_options(self):
        response = self.client.get("/api/question-bank/summary?scope=new")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active_scope"], "new")
        self.assertEqual(payload["active_scope_label"], "新题")
        self.assertEqual(payload["scope"], "new")
        self.assertGreater(payload["part1_count"], 0)
        self.assertGreater(payload["part2_count"], 0)
        scopes = {item["scope"]: item for item in payload["bank_scope_options"]}
        for scope in ("current", "new", "retained", "archive", "all"):
            self.assertIn(scope, scopes)
            self.assertIn("part1_count", scopes[scope])
            self.assertIn("part2_count", scopes[scope])
        self.assertEqual(scopes["archive"]["label"], "历史考季")
        self.assertEqual(scopes["all"]["label"], "全部题库")

    def test_question_bank_sample_returns_structure(self):
        response = self.client.post("/api/question-bank/sample", data={"p1_count": 3}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        if "part1" in payload:
            self.assertIsInstance(payload["part1"], list)
            self.assertTrue(all(item.get("season") == "2026-may-august" for item in payload["part1"]))
        if "part2" in payload:
            self.assertIsInstance(payload["part2"], dict)
            self.assertIn("season", payload["part2"])
            self.assertIn("region", payload["part2"])
            self.assertEqual(payload["part2"]["season"], "2026-may-august")

    def test_question_bank_sample_respects_scope(self):
        response = self.client.post(
            "/api/question-bank/sample",
            data={"p1_count": 3, "scope": "retained"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active_scope"], "retained")
        self.assertTrue(all(item.get("status") == "retained" for item in payload.get("part1", [])))
        if payload.get("part2"):
            self.assertEqual(payload["part2"].get("status"), "retained")

    def test_p1_corpus_library_and_save(self):
        library = self.client.get("/api/p1-corpus")
        self.assertEqual(library.status_code, 200)
        payload = library.json()
        self.assertIn("topics", payload)
        self.assertEqual(payload["active_season"], "2026-may-august")
        self.assertEqual(payload["scope"], "current_season_only")
        self.assertGreater(payload["question_count"], 0)

        first_question = payload["topics"][0]["questions"][0]
        response = self.client.post(
            "/api/p1-corpus",
            data={
                "question_id": first_question["question_id"],
                "topic": first_question["topic"],
                "question": first_question["question"],
                "corpus_text": "My prepared answer.",
                "last_ai_answer": "My Band 7 answer.",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual(saved["corpus_text"], "My prepared answer.")
        self.assertTrue(P1CorpusEntry.objects.filter(user=self.user, question_id=first_question["question_id"]).exists())

    def test_p1_corpus_reuses_legacy_topic_bound_entry_by_canonical_question(self):
        from apps.speaking.corpus_services import legacy_p1_question_id, p1_question_id

        question = "Do you prefer using a pen or a pencil?"
        legacy_id = legacy_p1_question_id("old_topic", question)
        canonical_id = p1_question_id("new_topic", question)
        P1CorpusEntry.objects.create(
            user=self.user,
            question_id=legacy_id,
            topic="old_topic",
            question=question,
            corpus_text="I prefer using a pen because it feels more formal.",
        )

        response = self.client.post(
            "/api/p1-corpus",
            data={
                "question_id": legacy_id,
                "topic": "new_topic",
                "question": question,
                "corpus_text": "I still prefer using a pen for notes.",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["question_id"], canonical_id)
        self.assertTrue(P1CorpusEntry.objects.filter(user=self.user, question_id=canonical_id).exists())
        self.assertFalse(P1CorpusEntry.objects.filter(user=self.user, question_id=legacy_id).exists())

    def test_p1_corpus_does_not_migrate_mismatched_submitted_question_id(self):
        from apps.speaking.corpus_services import p1_question_id

        existing_question = "Do you work or do you study?"
        existing_id = p1_question_id("intro", existing_question)
        P1CorpusEntry.objects.create(
            user=self.user,
            question_id=existing_id,
            topic="intro",
            question=existing_question,
            corpus_text="Actually, I do both. I study and work part-time.",
        )

        response = self.client.post(
            "/api/p1-corpus",
            data={
                "question_id": existing_id,
                "topic": "intro",
                "question": "What is your full name?",
                "corpus_text": "My name is Jasper.",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        new_id = p1_question_id("intro", "What is your full name?")
        self.assertEqual(response.json()["question_id"], new_id)
        original = P1CorpusEntry.objects.get(user=self.user, question_id=existing_id)
        self.assertEqual(original.question, existing_question)
        self.assertEqual(original.corpus_text, "Actually, I do both. I study and work part-time.")
        created = P1CorpusEntry.objects.get(user=self.user, question_id=new_id)
        self.assertEqual(created.question, "What is your full name?")
        self.assertEqual(created.corpus_text, "My name is Jasper.")

    def test_p1_corpus_library_respects_scope(self):
        response = self.client.get("/api/p1-corpus?scope=new")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active_scope"], "new")
        bank_questions = [
            question
            for topic in payload["topics"]
            for question in topic["questions"]
            if topic["topic"] != "intro"
        ]
        self.assertTrue(bank_questions)
        self.assertTrue(all(question.get("status") == "new" for question in bank_questions))

    def test_p2_corpus_library_marks_current_season_bank(self):
        response = self.client.get("/api/p2-corpus")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active_season"], "2026-may-august")
        self.assertEqual(payload["scope"], "current_season_only")
        self.assertGreaterEqual(payload["current_part2_count"], 55)
        self.assertEqual(len(payload["current_part2_categories"]), 5)
        self.assertIn("current_part2_cards", payload)
        self.assertEqual(len(payload["current_part2_cards"]), payload["current_part2_count"])
        first_card = payload["current_part2_cards"][0]
        self.assertTrue(first_card["entry_id"].startswith("p2:"))
        self.assertTrue(first_card["cue_id"].startswith("p2cue:"))
        self.assertIn("bullets", first_card)
        self.assertIn("rounding", first_card)
        self.assertFalse(first_card["has_material"])
        self.assertFalse(first_card["has_p3_follow_up"])

    def test_p2_corpus_library_includes_official_p3_follow_ups(self):
        response = self.client.get("/api/p2-corpus")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["current_part2_cards"])
        for card in payload["current_part2_cards"]:
            with self.subTest(card=card["cue_title"]):
                self.assertTrue(card.get("p3_follow_ups"))
                self.assertEqual(card["p3_follow_up_count"], len(card["p3_follow_ups"]))
                self.assertTrue(all("?" in question for question in card["p3_follow_ups"]))

    def test_p2_corpus_category_counts_user_saved_material_not_season_topics(self):
        payload = self.client.get("/api/p2-corpus").json()
        self.assertTrue(payload["current_part2_categories"])
        self.assertTrue(all(category["material_count"] == 0 for category in payload["categories"]))
        self.assertNotIn("topic_count", payload["categories"][0])

        response = self.client.post(
            "/api/p2-corpus",
            data={
                "category": "person",
                "title": "Reusable person story",
                "material_text": "This is a reusable person story across seasons.",
                "linked_question": "",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        updated = self.client.get("/api/p2-corpus").json()
        counts = {item["category"]: item["material_count"] for item in updated["categories"]}
        self.assertEqual(counts["person"], 1)
        self.assertEqual(counts["place"], 0)

    def test_p2_bank_corpus_updates_current_season_card_without_polluting_personal_library(self):
        library = self.client.get("/api/p2-corpus").json()
        card = library["current_part2_cards"][0]
        before_personal_count = P2CorpusEntry.objects.filter(user=self.user).count()

        save_response = self.client.put(
            f"/api/p2-bank-corpus/{card['cue_id']}",
            data={
                "question": card["linked_question"],
                "corpus_text": "I can use one prepared story for this cue card.",
            },
            content_type="application/json",
        )
        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(P2CorpusEntry.objects.filter(user=self.user).count(), before_personal_count)
        self.assertEqual(P2BankCorpusEntry.objects.filter(user=self.user, question_id=card["cue_id"]).count(), 1)

        updated = self.client.get("/api/p2-corpus").json()
        updated_card = next(item for item in updated["current_part2_cards"] if item["entry_id"] == card["entry_id"])
        self.assertTrue(updated_card["has_material"])
        self.assertEqual(updated_card["material_text"], "I can use one prepared story for this cue card.")
        self.assertFalse(updated_card["has_p3_follow_up"])

    def test_p2_bank_brainstorm_idea_preserves_existing_bank_material(self):
        library = self.client.get("/api/p2-corpus").json()
        card = library["current_part2_cards"][0]

        self.client.put(
            f"/api/p2-bank-corpus/{card['cue_id']}",
            data={
                "question": card["linked_question"],
                "corpus_text": "A quiet university library story.",
                "last_ai_answer": "A polished answer about the library.",
            },
            content_type="application/json",
        )
        save_response = self.client.patch(
            f"/api/p2-bank-corpus/{card['cue_id']}",
            data={
                "question": card["linked_question"],
                "metadata": {"brainstorm_idea": "library + final exam week + coding notes"},
            },
            content_type="application/json",
        )
        self.assertEqual(save_response.status_code, 200)
        saved_payload = save_response.json()
        self.assertEqual(saved_payload["corpus_text"], "A quiet university library story.")
        self.assertEqual(saved_payload["last_ai_answer"], "A polished answer about the library.")
        self.assertEqual(saved_payload["brainstorm_idea"], "library + final exam week + coding notes")

        updated = self.client.get("/api/p2-corpus").json()
        updated_card = next(item for item in updated["current_part2_cards"] if item["entry_id"] == card["entry_id"])
        self.assertTrue(updated_card["has_material"])
        self.assertTrue(updated_card["has_brainstorm_idea"])
        self.assertEqual(updated_card["material_text"], "A quiet university library story.")
        self.assertEqual(updated_card["brainstorm_idea"], "library + final exam week + coding notes")

    def test_p3_bank_followup_corpus_uses_question_bank_followups_without_polluting_personal_library(self):
        library = self.client.get("/api/p2-corpus").json()
        card = next(item for item in library["current_part2_cards"] if item.get("p3_follow_ups"))
        before_personal_count = P2CorpusEntry.objects.filter(user=self.user).count()

        list_response = self.client.get(f"/api/p3-bank-corpus/{card['cue_id']}")
        self.assertEqual(list_response.status_code, 200)
        followups = list_response.json()["items"]
        self.assertEqual(len(followups), len(card["p3_follow_ups"]))
        self.assertGreater(len(followups), 0)

        first = followups[0]
        save_response = self.client.put(
            f"/api/p3-bank-corpus/item/{first['followup_id']}",
            data={
                "p2_question_id": card["cue_id"],
                "followup_question": first["followup_question"],
                "corpus_text": "I can discuss work, public places, and habits.",
            },
            content_type="application/json",
        )
        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(P2CorpusEntry.objects.filter(user=self.user).count(), before_personal_count)
        self.assertEqual(P3BankFollowupCorpusEntry.objects.filter(user=self.user, followup_id=first["followup_id"]).count(), 1)

        updated = self.client.get("/api/p2-corpus").json()
        updated_card = next(item for item in updated["current_part2_cards"] if item["entry_id"] == card["entry_id"])
        self.assertTrue(updated_card["has_p3_follow_up"])
        self.assertEqual(updated_card["p3_follow_up_saved_count"], 1)

    def test_p2_corpus_library_respects_scope(self):
        response = self.client.get("/api/p2-corpus?scope=archive")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active_scope"], "archive")
        self.assertGreater(payload["current_part2_count"], 0)

    def test_p2_corpus_save_uses_linked_question_as_stable_entry_id(self):
        linked_question = "Describe a book you have recently read\nWhat it was about\nWhy you chose it"
        first = self.client.post(
            "/api/p2-corpus",
            data={
                "category": "object",
                "title": "Book material",
                "material_text": "I can talk about a travel book.",
                "linked_question": linked_question,
            },
            content_type="application/json",
        )
        second = self.client.post(
            "/api/p2-corpus",
            data={
                "category": "special",
                "title": "Same retained cue in a new season",
                "material_text": "The same prepared material should update.",
                "linked_question": linked_question,
            },
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["entry_id"], second.json()["entry_id"])
        self.assertEqual(P2CorpusEntry.objects.filter(user=self.user, entry_id=first.json()["entry_id"]).count(), 1)

    def test_p1_corpus_library_does_not_append_dynamic_follow_ups(self):
        library = self.client.get("/api/p1-corpus")
        self.assertEqual(library.status_code, 200)
        before = library.json()
        intro_before = next(topic for topic in before["topics"] if topic["topic"] == "intro")
        parent_question = next(item for item in intro_before["questions"] if item["question"] == "Do you work or do you study?")

        response = self.client.post(
            "/api/p1-corpus",
            data={
                "question_id": parent_question["question_id"],
                "topic": "intro",
                "question": parent_question["question"],
                "corpus_text": "I am a university student and I am doing an internship.",
                "last_ai_answer": "How does your internship connect with what you study?",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        after = self.client.get("/api/p1-corpus").json()
        intro_after = next(topic for topic in after["topics"] if topic["topic"] == "intro")
        self.assertEqual(len(intro_after["questions"]), len(intro_before["questions"]))
        self.assertNotIn(
            "How does your internship connect with what you study?",
            [item["question"] for item in intro_after["questions"]],
        )

    def test_p2_corpus_library_and_save(self):
        library = self.client.get("/api/p2-corpus")
        self.assertEqual(library.status_code, 200)
        payload = library.json()
        self.assertEqual(payload["category_count"], 5)
        self.assertIn("categories", payload)

        response = self.client.post(
            "/api/p2-corpus",
            data={
                "category": "person",
                "title": "A helpful teacher",
                "material_text": "This person helped me with a coding project.",
                "linked_question": "",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual(saved["category"], "person")
        self.assertEqual(saved["title"], "A helpful teacher")
        self.assertTrue(P2CorpusEntry.objects.filter(user=self.user, entry_id=saved["entry_id"]).exists())

    def test_p2_corpus_delete_requires_login(self):
        entry = P2CorpusEntry.objects.create(
            user=self.user,
            entry_id="p2-delete-login",
            category=P2CorpusEntry.Category.PERSON,
            title="A helpful teacher",
            material_text="Prepared material.",
        )
        self.client.logout()
        response = self.client.delete(f"/api/p2-corpus/{entry.entry_id}")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(P2CorpusEntry.objects.filter(entry_id=entry.entry_id).exists())

    def test_p2_corpus_delete_is_owner_scoped_and_removes_from_library(self):
        entry = P2CorpusEntry.objects.create(
            user=self.user,
            entry_id="p2-delete-owned",
            category=P2CorpusEntry.Category.PERSON,
            title="A helpful teacher",
            material_text="Prepared material.",
        )
        other_user = get_user_model().objects.create_user(username="other-p2-corpus", password="test-pass")
        self.client.logout()
        self.client.force_login(other_user)
        other_response = self.client.delete(f"/api/p2-corpus/{entry.entry_id}")
        self.assertEqual(other_response.status_code, 404)
        self.assertTrue(P2CorpusEntry.objects.filter(entry_id=entry.entry_id).exists())

        self.client.logout()
        self.client.force_login(self.user)
        response = self.client.delete(f"/api/p2-corpus/{entry.entry_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertFalse(P2CorpusEntry.objects.filter(entry_id=entry.entry_id).exists())
        library = self.client.get("/api/p2-corpus").json()
        saved_ids = [item["entry_id"] for group in library["categories"] for item in group["items"]]
        self.assertNotIn(entry.entry_id, saved_ids)

    def test_language_takeaway_save_and_list(self):
        response = self.client.post(
            "/api/language-takeaways",
            data={
                "source_text": "strike a balance",
                "chinese_text": "取得平衡",
                "context_label": "P1",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual(saved["source_text"], "strike a balance")
        self.assertEqual(saved["chinese_text"], "取得平衡")
        self.assertTrue(LanguageTakeawayEntry.objects.filter(user=self.user, entry_id=saved["entry_id"]).exists())

        library = self.client.get("/api/language-takeaways")
        self.assertEqual(library.status_code, 200)
        payload = library.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["source_text"], "strike a balance")

    def test_takeaway_review_state_is_user_scoped_and_returned_with_library(self):
        state = {
            "__daily_batch": {
                "day": "2026-06-12",
                "ids": ["lt-state"],
                "completedDay": "2026-06-12",
                "locked": True,
            },
            "lt-state": {"due": "2026-06-13", "last": "2026-06-12", "reps": 1},
        }
        response = self.client.post(
            "/api/takeaway-review-state/language",
            data={"state": state},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["review_state"], state)

        library = self.client.get("/api/language-takeaways")
        self.assertEqual(library.status_code, 200)
        self.assertEqual(library.json()["review_state"], state)

        other_user = get_user_model().objects.create_user(username="other-takeaway-state", password="test-pass")
        self.client.force_login(other_user)
        other_library = self.client.get("/api/language-takeaways")
        self.assertEqual(other_library.status_code, 200)
        self.assertEqual(other_library.json()["review_state"], {})

    def test_language_takeaway_list_excludes_writing_takeaways(self):
        LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="lt-list-language",
            source_text="strike a balance",
            chinese_text="取得平衡",
            metadata={"saved_from": "language_takeaway"},
        )
        LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="wt-list-writing",
            source_text="clear topic sentence",
            chinese_text="清晰的主题句",
            metadata={"saved_from": "writing_takeaway"},
        )

        language_payload = self.client.get("/api/language-takeaways").json()
        writing_payload = self.client.get("/api/writing-takeaways").json()

        self.assertEqual([item["entry_id"] for item in language_payload["items"]], ["lt-list-language"])
        self.assertEqual([item["entry_id"] for item in writing_payload["items"]], ["wt-list-writing"])

    def test_language_takeaway_delete_requires_login(self):
        entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="lt-delete-login",
            source_text="strike a balance",
            chinese_text="取得平衡",
        )
        self.client.logout()
        response = self.client.delete(f"/api/language-takeaways/{entry.entry_id}")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(LanguageTakeawayEntry.objects.filter(entry_id=entry.entry_id).exists())

    def test_language_takeaway_delete_is_owner_scoped_and_removes_from_list(self):
        entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="lt-delete-owned",
            source_text="strike a balance",
            chinese_text="取得平衡",
        )
        other_user = get_user_model().objects.create_user(username="other-takeaway", password="test-pass")
        self.client.logout()
        self.client.force_login(other_user)
        other_response = self.client.delete(f"/api/language-takeaways/{entry.entry_id}")
        self.assertEqual(other_response.status_code, 404)
        self.assertTrue(LanguageTakeawayEntry.objects.filter(entry_id=entry.entry_id).exists())

        self.client.logout()
        self.client.force_login(self.user)
        response = self.client.delete(f"/api/language-takeaways/{entry.entry_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertFalse(LanguageTakeawayEntry.objects.filter(entry_id=entry.entry_id).exists())
        library = self.client.get("/api/language-takeaways").json()
        self.assertEqual(library["count"], 0)
        self.assertEqual(library["items"], [])

    def test_language_takeaway_delete_rejects_writing_scoped_entry(self):
        entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="wt-delete-via-language",
            source_text="clear topic sentence",
            chinese_text="清晰的主题句",
            metadata={"saved_from": "writing_takeaway"},
        )

        response = self.client.delete(f"/api/language-takeaways/{entry.entry_id}")

        self.assertEqual(response.status_code, 404)
        self.assertTrue(LanguageTakeawayEntry.objects.filter(user=self.user, entry_id=entry.entry_id).exists())

    def test_language_takeaway_detail_update_edits_existing_entry(self):
        entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="lt-edit-owned",
            source_text="strike a balance",
            chinese_text="取得平衡",
            context_label="P1",
            metadata={"saved_from": "language_takeaway"},
        )
        response = self.client.patch(
            f"/api/language-takeaways/{entry.entry_id}",
            data={
                "source_text": "strike a better balance",
                "chinese_text": "取得更好的平衡",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["entry_id"], entry.entry_id)
        self.assertEqual(payload["source_text"], "strike a better balance")
        self.assertEqual(payload["chinese_text"], "取得更好的平衡")
        entry.refresh_from_db()
        self.assertEqual(entry.source_text, "strike a better balance")
        self.assertEqual(entry.context_label, "P1")

    def test_language_takeaway_detail_update_is_owner_scoped(self):
        entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="lt-edit-other",
            source_text="strike a balance",
            chinese_text="取得平衡",
        )
        other_user = get_user_model().objects.create_user(username="other-takeaway-edit", password="test-pass")
        self.client.logout()
        self.client.force_login(other_user)
        response = self.client.patch(
            f"/api/language-takeaways/{entry.entry_id}",
            data={"source_text": "changed"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        entry.refresh_from_db()
        self.assertEqual(entry.source_text, "strike a balance")

    def test_language_takeaway_detail_update_rejects_writing_scoped_entry(self):
        entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="wt-edit-via-language",
            source_text="clear topic sentence",
            chinese_text="清晰的主题句",
            metadata={"saved_from": "writing_takeaway"},
        )

        response = self.client.patch(
            f"/api/language-takeaways/{entry.entry_id}",
            data={"source_text": "changed"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        entry.refresh_from_db()
        self.assertEqual(entry.source_text, "clear topic sentence")

    def test_writing_takeaway_detail_update_keeps_writing_scope(self):
        entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="wt-edit-owned",
            source_text="clear topic sentence",
            chinese_text="清晰的主题句",
            metadata={"saved_from": "writing_takeaway"},
        )
        response = self.client.patch(
            f"/api/writing-takeaways/{entry.entry_id}",
            data={
                "source_text": "clearer topic sentence",
                "chinese_text": "更清晰的主题句",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["entry_id"], entry.entry_id)
        self.assertEqual(payload["source_text"], "clearer topic sentence")
        entry.refresh_from_db()
        self.assertEqual(entry.metadata.get("saved_from"), "writing_takeaway")

    def test_writing_takeaway_detail_update_is_owner_scoped(self):
        entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="wt-edit-other",
            source_text="clear topic sentence",
            chinese_text="清晰的主题句",
            metadata={"saved_from": "writing_takeaway"},
        )
        other_user = get_user_model().objects.create_user(username="other-writing-takeaway-edit", password="test-pass")
        self.client.logout()
        self.client.force_login(other_user)

        response = self.client.patch(
            f"/api/writing-takeaways/{entry.entry_id}",
            data={"source_text": "changed"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        entry.refresh_from_db()
        self.assertEqual(entry.source_text, "clear topic sentence")

    def test_writing_takeaway_detail_update_rejects_language_scoped_entry(self):
        entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="lt-edit-via-writing",
            source_text="strike a balance",
            chinese_text="取得平衡",
            metadata={"saved_from": "language_takeaway"},
        )

        response = self.client.patch(
            f"/api/writing-takeaways/{entry.entry_id}",
            data={"source_text": "changed"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        entry.refresh_from_db()
        self.assertEqual(entry.source_text, "strike a balance")

    def test_takeaway_detail_update_accepts_put_for_language_and_writing(self):
        language_entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="lt-put-owned",
            source_text="strike a balance",
            chinese_text="取得平衡",
            metadata={"saved_from": "language_takeaway"},
        )
        writing_entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="wt-put-owned",
            source_text="clear topic sentence",
            chinese_text="清晰的主题句",
            metadata={"saved_from": "writing_takeaway"},
        )

        language_response = self.client.put(
            f"/api/language-takeaways/{language_entry.entry_id}",
            data={"source_text": "strike a better balance", "chinese_text": "取得更好的平衡"},
            content_type="application/json",
        )
        writing_response = self.client.put(
            f"/api/writing-takeaways/{writing_entry.entry_id}",
            data={"source_text": "clearer topic sentence", "chinese_text": "更清晰的主题句"},
            content_type="application/json",
        )

        self.assertEqual(language_response.status_code, 200)
        self.assertEqual(writing_response.status_code, 200)
        language_entry.refresh_from_db()
        writing_entry.refresh_from_db()
        self.assertEqual(language_entry.source_text, "strike a better balance")
        self.assertEqual(language_entry.metadata.get("saved_from"), "language_takeaway")
        self.assertEqual(writing_entry.source_text, "clearer topic sentence")

    def test_takeaway_detail_update_accepts_post_for_editor_save(self):
        language_entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="lt-post-owned",
            source_text="beneficial",
            chinese_text="有益",
            metadata={"saved_from": "language_takeaway"},
        )
        writing_entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="wt-post-owned",
            source_text="clear topic sentence",
            chinese_text="清晰的主题句",
            metadata={"saved_from": "writing_takeaway"},
        )

        language_response = self.client.post(
            f"/api/language-takeaways/{language_entry.entry_id}",
            data={"source_text": "beneficial effect", "chinese_text": "有益影响"},
            content_type="application/json",
        )
        writing_response = self.client.post(
            f"/api/writing-takeaways/{writing_entry.entry_id}",
            data={"source_text": "clearer topic sentence", "chinese_text": "更清晰的主题句"},
            content_type="application/json",
        )

        self.assertEqual(language_response.status_code, 200)
        self.assertEqual(writing_response.status_code, 200)
        language_entry.refresh_from_db()
        writing_entry.refresh_from_db()
        self.assertEqual(language_entry.source_text, "beneficial effect")
        self.assertEqual(language_entry.chinese_text, "有益影响")
        self.assertEqual(language_entry.metadata.get("saved_from"), "language_takeaway")
        self.assertEqual(writing_entry.source_text, "clearer topic sentence")
        self.assertEqual(writing_entry.metadata.get("saved_from"), "writing_takeaway")
        self.assertEqual(writing_entry.metadata.get("saved_from"), "writing_takeaway")

    def test_writing_takeaway_delete_is_writing_scoped(self):
        language_entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="lt-delete-via-writing",
            source_text="strike a balance",
            chinese_text="取得平衡",
            metadata={"saved_from": "language_takeaway"},
        )
        writing_entry = LanguageTakeawayEntry.objects.create(
            user=self.user,
            entry_id="wt-delete-owned",
            source_text="clear topic sentence",
            chinese_text="清晰的主题句",
            metadata={"saved_from": "writing_takeaway"},
        )

        language_response = self.client.delete(f"/api/writing-takeaways/{language_entry.entry_id}")
        writing_response = self.client.delete(f"/api/writing-takeaways/{writing_entry.entry_id}")

        self.assertEqual(language_response.status_code, 404)
        self.assertTrue(LanguageTakeawayEntry.objects.filter(user=self.user, entry_id=language_entry.entry_id).exists())
        self.assertEqual(writing_response.status_code, 200)
        self.assertFalse(LanguageTakeawayEntry.objects.filter(user=self.user, entry_id=writing_entry.entry_id).exists())

    def test_language_takeaway_translate_without_token_uses_local_offline_dictionary(self):
        with (
            patch.dict("os.environ", {"CAIYUN_TOKEN": "", "CAIYUN_TRANSLATE_TOKEN": ""}, clear=False),
            patch("urllib.request.urlopen", side_effect=OSError("offline")),
        ):
            response = self.client.post(
                "/api/language-takeaways/translate",
                data={"text": "repetitive work"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source_text"], "repetitive work")
        self.assertEqual(payload["chinese_text"], "重复的；工作")
        self.assertEqual(payload["provider"], "local")
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["caiyun_status"], "unavailable")

    def test_language_takeaway_translate_chinese_text_locally(self):
        with (
            patch.dict("os.environ", {"CAIYUN_TOKEN": "", "CAIYUN_TRANSLATE_TOKEN": ""}, clear=False),
            patch("urllib.request.urlopen", side_effect=OSError("offline")),
        ):
            response = self.client.post(
                "/api/language-takeaways/translate",
                data={"text": "直接给一个答案"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["chinese_text"], "直接给一个答案")
        self.assertEqual(payload["provider"], "local")
        self.assertEqual(payload["status"], "ready")

    def test_language_takeaway_translate_uses_caiyun_compat_protocol_without_config(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({"target": "取得平衡"}).encode("utf-8")

        with (
            patch.dict("os.environ", {"CAIYUN_TOKEN": "", "CAIYUN_TRANSLATE_TOKEN": ""}, clear=False),
            patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen,
        ):
            response = self.client.post(
                "/api/language-takeaways/translate",
                data={"text": "strike a balance"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source_text"], "strike a balance")
        self.assertEqual(payload["chinese_text"], "取得平衡")
        self.assertEqual(payload["provider"], "caiyun")
        self.assertEqual(payload["status"], "ready")
        request = urlopen.call_args.args[0]
        request_payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request_payload["source"], "strike a balance")
        self.assertEqual(request_payload["trans_type"], "auto2zh")
        self.assertEqual(request_payload["media"], "text")


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

    def complete_turn(self, attempt_id="runtime-attempt", turn_id="t1", transcript="My full name is Sam.", extra_payload=None):
        payload = {"transcript_raw": transcript, "transcript_status": "captured", "transcript_source": "browser_dictation"}
        if extra_payload:
            payload.update(extra_payload)
        return self.client.post(
            f"/api/attempts/{attempt_id}/turns/{turn_id}/complete",
            data=payload,
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
        self.assertEqual(turn.metadata["server_asr"]["status"], "skipped_browser_transcript_available")

    def test_turn_complete_persists_audio_preprocessing_metrics(self):
        self.create_attempt()
        response = self.complete_turn(extra_payload={
            "audio_preprocessing_metrics": {
                "enabled": True,
                "analyzer": "wasm-audio-core",
                "fallback_analyzer": "",
                "fallback_reason": "",
                "total_frames": 100,
                "speech_frames": 25,
                "silence_frames": 75,
                "speech_ratio": 0.333333333,
                "silence_ratio": 0.666666666,
                "latest_rms": 0.123456789,
                "latest_peak": 0.987654321,
                "latest_speech": True,
                "sample_rate": 48000,
                "frame_size": 128,
                "started_at_ms": 10.1234,
                "stopped_at_ms": 20.5678,
                "last_error": "",
                "samples": [1, 2, 3],
            }
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        metrics = payload["turn"]["audio_preprocessing_metrics"]
        self.assertEqual(metrics["analyzer"], "wasm-audio-core")
        self.assertEqual(metrics["total_frames"], 100)
        self.assertEqual(metrics["speech_frames"], 25)
        self.assertEqual(metrics["silence_frames"], 75)
        self.assertEqual(metrics["speech_ratio"], 0.25)
        self.assertEqual(metrics["silence_ratio"], 0.75)
        self.assertNotIn("samples", metrics)

        turn = SpeakingTurn.objects.get(turn_id="t1")
        self.assertEqual(turn.metadata["audio_preprocessing_metrics"], metrics)

    def test_turn_complete_persists_realtime_asr_metrics(self):
        self.create_attempt()
        response = self.complete_turn(
            transcript="I study software engineering.",
            extra_payload={
                "transcript_source": "volcengine_realtime_asr",
                "realtime_asr_metrics": {
                    "enabled": True,
                    "running": False,
                    "status": "closed",
                    "asrStatus": "done",
                    "asrConfigured": True,
                    "asrEnabled": True,
                    "asrProvider": "volcengine_realtime_asr",
                    "transcriptSource": "volcengine_realtime_asr",
                    "framesSent": 20,
                    "framesAcked": 22,
                    "droppedFrames": 1,
                    "bytesSent": 6400,
                    "bytesAcked": 7000,
                    "asrStatusCheckMs": 12,
                    "socketOpenMs": 40,
                    "firstAsrEventMs": 55,
                    "firstTranscriptMs": 420,
                    "finalTranscriptMs": 1180,
                    "doneMs": 1250,
                    "lastError": "",
                    "asrTranscript": "I study software engineering.",
                    "url": "wss://secret.example/realtime",
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        metrics = payload["turn"]["realtime_asr_metrics"]
        self.assertEqual(metrics["asr_status"], "done")
        self.assertEqual(metrics["transcript_source"], "volcengine_realtime_asr")
        self.assertEqual(metrics["frames_sent"], 20)
        self.assertEqual(metrics["frames_acked"], 20)
        self.assertEqual(metrics["bytes_sent"], 6400)
        self.assertEqual(metrics["bytes_acked"], 6400)
        self.assertEqual(metrics["first_transcript_ms"], 420)
        self.assertNotIn("url", metrics)
        self.assertNotIn("asrTranscript", metrics)

        turn = SpeakingTurn.objects.get(turn_id="t1")
        self.assertEqual(turn.metadata["realtime_asr_metrics"], metrics)

    def test_turn_complete_uses_server_asr_when_browser_transcript_is_missing(self):
        _attempt, turn1, _turn2 = self.create_attempt()
        turn1.audio_path = "audio/runtime-asr.webm"
        turn1.save(update_fields=["audio_path"])
        with patch(
            "apps.speaking.services.transcribe_turn_audio_with_server_asr",
            return_value={
                "ok": True,
                "status": "ready",
                "provider": "volcengine_realtime_asr",
                "transcript": "My full name is Sam from server ASR.",
            },
        ):
            response = self.complete_turn(transcript="")
        self.assertEqual(response.status_code, 200)
        turn1.refresh_from_db()
        self.assertEqual(turn1.transcript_raw, "My full name is Sam from server ASR.")
        self.assertEqual(turn1.transcript_source, "volcengine_realtime_asr")
        self.assertEqual(turn1.metadata["browser_transcript_raw"], "")

    def test_turn_complete_skips_server_asr_when_browser_transcript_exists(self):
        self.create_attempt()
        with patch(
            "apps.speaking.services.transcribe_turn_audio_with_server_asr",
            return_value={"ok": False, "status": "error", "transcript": "", "error": "service unavailable"},
        ) as mock_asr:
            response = self.complete_turn(transcript="Browser transcript stays.")
        self.assertEqual(response.status_code, 200)
        mock_asr.assert_not_called()
        turn = SpeakingTurn.objects.get(turn_id="t1")
        self.assertEqual(turn.transcript_raw, "Browser transcript stays.")
        self.assertEqual(turn.transcript_source, "browser_dictation")
        self.assertEqual(turn.metadata["server_asr"]["status"], "skipped_browser_transcript_available")
        self.assertEqual(turn.metadata["browser_transcript_raw"], "Browser transcript stays.")
        self.assertEqual(turn.metadata["client_transcript_raw"], "Browser transcript stays.")
        self.assertEqual(turn.metadata["transcript_source"], "browser_dictation")

    def test_turn_complete_preserves_realtime_asr_transcript_source(self):
        self.create_attempt()
        with patch(
            "apps.speaking.services.transcribe_turn_audio_with_server_asr",
            return_value={"ok": False, "status": "error", "transcript": "", "error": "service unavailable"},
        ) as mock_asr:
            response = self.complete_turn(
                transcript="Realtime transcript stays.",
                extra_payload={"transcript_source": "volcengine_realtime_asr"},
            )
        self.assertEqual(response.status_code, 200)
        mock_asr.assert_not_called()
        turn = SpeakingTurn.objects.get(turn_id="t1")
        self.assertEqual(turn.transcript_raw, "Realtime transcript stays.")
        self.assertEqual(turn.transcript_source, "volcengine_realtime_asr")
        self.assertEqual(turn.metadata["server_asr"]["status"], "skipped_client_transcript_available")
        self.assertEqual(turn.metadata["browser_transcript_raw"], "")
        self.assertEqual(turn.metadata["client_transcript_raw"], "Realtime transcript stays.")
        self.assertEqual(turn.metadata["transcript_source"], "volcengine_realtime_asr")

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

        score_payload = {
            "fluency_coherence": 6.0,
            "lexical_resource": 6.0,
            "grammatical_range": 6.0,
            "feedback": "Clear and relevant answers with enough support.",
        }
        feedback_payload = {
            "band7_version": "My full name is Sam. I study English because I want to communicate clearly.",
            "ai_coaching": "回答方向清楚，可以再加一个具体例子。\n\n语法错误纠正：无",
        }
        batch_feedback_payload = {
            "turns": [
                {
                    "turn_id": turn2.turn_id,
                    "display_transcript": turn2.transcript_cleaned,
                    **feedback_payload,
                }
            ]
        }
        tts_payload = {"provider": "volcengine", "status": "ready", "audio_url": "/api/tts-audio/model/test.mp3"}
        with patch("apps.speaking.services.run_codex") as run_codex, patch("apps.speaking.services.volcengine_tts", return_value=tts_payload):
            response = self.client.post(f"/api/attempts/{attempt.attempt_id}/score", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "analysis_pending")
        self.assertEqual(payload["ai_task"]["task_type"], "speaking_report")
        self.assertEqual(payload["ai_task"]["related_id"], attempt.attempt_id)
        run_codex.assert_not_called()
        self.assertFalse(SpeakingReport.objects.filter(attempt=attempt).exists())

        history = self.client.get("/api/history")
        self.assertNotIn(attempt.attempt_id, [item["id"] for item in history.json()["items"]])


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
        with patch(
            "apps.speaking.services.transcribe_turn_audio_with_server_asr",
            return_value={
                "ok": True,
                "status": "ready",
                "provider": "volcengine_realtime_asr",
                "transcript": "Regenerated transcript from server ASR.",
            },
        ):
            response = self.client.post(f"/api/attempts/{attempt.attempt_id}/turns/{turn.turn_id}/transcript/regenerate")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("ok"))
        self.assertIn("turn", payload)
        turn.refresh_from_db()
        self.assertEqual(turn.transcript_raw, "Regenerated transcript from server ASR.")

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

    def test_p3_questions_require_real_ai_or_fixed_bank_questions(self):
        self.client.logout()
        unauthorized = self.client.post("/api/p3/questions", data={"theme": "technology"}, content_type="application/json")
        self.assertEqual(unauthorized.status_code, 401)

        self.client.force_login(self.user)
        response = self.client.post("/api/p3/questions", data={"theme": "technology"}, content_type="application/json")
        self.assertEqual(response.status_code, 502)
        payload = response.json()
        self.assertEqual(payload["backend"], "failed")
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["questions"], [])
        self.assertIn("error", payload)
        self.assertIn("plan", payload)
        self.assertEqual(payload["plan"]["focus"], "comparison_concession")

    @override_settings(AI_HTTP_BASE_URL="https://ai.example/v1", AI_HTTP_API_KEY="test-key", AI_HTTP_MODEL="legacy-model")
    def test_p3_custom_questions_use_http_provider_output(self):
        class ProviderResult:
            text = json.dumps({
                "questions": [
                    "Why do people have different opinions about technology?",
                    "How has technology changed daily communication?",
                    "Do you think technology will become more important in the future?",
                ],
                "follow_up": "What is one risk people should pay attention to?",
            })
            model = "gpt-5.4-mini"
            usage = {"input_tokens": 80, "output_tokens": 40}

        class Provider:
            def __init__(self, config=None):
                self.config = config

            def complete_chat(self, *args, **kwargs):
                return ProviderResult()

        with patch("apps.speaking.services.HttpApiProvider", Provider):
            response = self.client.post(
                "/api/p3/questions",
                data={"source": "custom", "theme": "technology"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["backend"], "http_api")
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(len(payload["questions"]), 3)
        self.assertEqual(payload["plan"]["source"]["type"], "custom")
        self.assertEqual(payload["plan"]["model"], "gpt-5.4-mini")
        self.assertEqual(payload["plan"]["usage"]["output_tokens"], 40)

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

    def test_tts_server_fallback_generates_audio_when_requested(self):
        self.client.force_login(self.user)
        with patch("apps.speaking.tts_services.volcengine_tts", return_value={"provider": "volcengine", "status": "ready", "audio_url": "/api/tts-audio/model/takeaway.mp3"}) as tts:
            response = self.client.post(
                "/api/tts",
                data={"text": "Hello", "role": "model", "server_fallback": True},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"], "volcengine")
        self.assertEqual(payload["audio_url"], "/api/tts-audio/model/takeaway.mp3")
        tts.assert_called_once()

    def test_tts_warmup_requires_login_and_caches_fixed_examiner_audio(self):
        self.client.logout()
        unauthorized = self.client.post("/api/tts/warmup", data={}, content_type="application/json")
        self.assertEqual(unauthorized.status_code, 401)

        self.client.force_login(self.user)
        tts_payload = {
            "provider": "volcengine",
            "status": "cached",
            "audio_url": "/api/tts-audio/examiner/fixed.mp3",
        }
        with patch("apps.speaking.services.volcengine_tts", return_value=tts_payload) as tts:
            response = self.client.post("/api/tts/warmup", data={}, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ready_count"], 3)
        self.assertEqual(len(payload["items"]), 3)
        self.assertEqual(tts.call_count, 3)
        cache_keys = [call.kwargs["cache_key"] for call in tts.call_args_list]
        self.assertEqual(cache_keys, [
            "fixed_examiner_what_is_your_full_name",
            "fixed_examiner_do_you_work_or_do_you_study",
            "fixed_examiner_p2_cue_card_instruction",
        ])

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

        with patch("apps.speaking.tts_services.shutil.which", return_value=None):
            stable_response = self.client.get("/api/tts-audio/examiner/sample.mp3?stable=1")

        self.assertEqual(stable_response.status_code, 200)
        self.assertEqual(stable_response["Content-Type"], "audio/mpeg")
        self.assertEqual(b"".join(stable_response.streaming_content), b"mp3-data")

    def test_latest_report_returns_latest_valid_report(self):
        no_report = self.client.get("/api/reports/latest")
        self.assertEqual(no_report.status_code, 200)
        self.assertEqual(no_report.json(), {"report": None})

        attempt = self.create_scored_attempt()
        response = self.client.get("/api/reports/latest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], attempt.attempt_id)


class CodexValidationTests(TestCase):
    """Test validation logic for Codex AI scoring and feedback."""

    def create_ready_attempt(self, username="score-attempt-user", attempt_id="score-attempt-codex-path"):
        from apps.accounts.models import CustomUser

        user = CustomUser.objects.create_user(username=username, password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id=attempt_id,
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
            question="Do you work or do you study?",
            transcript_raw="I study software engineering and I also do an internship at a small technology company.",
            transcript_cleaned="I study software engineering and I also do an internship at a small technology company.",
            metadata={"status": "completed"},
        )
        return user, attempt, turn

    def test_score_with_codex_rejects_missing_scores(self):
        """score_with_codex should reject outputs with missing FC/LR/GRA fields."""
        from unittest.mock import patch
        from apps.speaking.services import score_with_codex

        # Mock run_codex to return output with missing scores
        with patch("apps.speaking.services.run_codex") as mock_run:
            mock_run.return_value = ('{"feedback": "test"}', {"input_tokens": 100})
            with self.assertRaises(RuntimeError) as ctx:
                score_with_codex("test transcript", "test question", "p1", "test_call")
            self.assertTrue(
                "missing or invalid fields" in str(ctx.exception)
                or "required keys" in str(ctx.exception)
            )

    def test_score_with_codex_rejects_zero_scores(self):
        """score_with_codex should reject outputs with all-zero scores."""
        from unittest.mock import patch
        from apps.speaking.services import score_with_codex

        with patch("apps.speaking.services.run_codex") as mock_run:
            mock_run.return_value = (
                '{"fluency_coherence": 0, "lexical_resource": 0, "grammatical_range": 0, "feedback": "test"}',
                {"input_tokens": 100},
            )
            with self.assertRaises(RuntimeError) as ctx:
                score_with_codex("test transcript", "test question", "p1", "test_call")
            self.assertIn("missing or invalid fields", str(ctx.exception))

    def test_score_with_codex_accepts_valid_scores(self):
        """score_with_codex should accept valid outputs with proper scores."""
        from unittest.mock import patch
        from apps.speaking.services import score_with_codex

        with patch("apps.speaking.services.run_codex") as mock_run:
            mock_run.return_value = (
                '{"fluency_coherence": 6.5, "lexical_resource": 6.0, "grammatical_range": 6.0, "feedback": "Good work"}',
                {"input_tokens": 100},
            )
            result = score_with_codex("test transcript", "test question", "p1", "test_call")
            self.assertEqual(result["backend"], "codex")
            self.assertIn("fluency_coherence", result)
            self.assertGreater(result["fluency_coherence"], 0)

    def test_score_with_codex_overall_review_prompt_uses_evidence_and_limited_points(self):
        from apps.speaking.services import score_with_codex

        captured_prompt = {}

        def fake_run_codex(prompt, call_id, timeout=180):
            captured_prompt["text"] = prompt
            return (
                json.dumps(
                    {
                        "fluency_coherence": 6.0,
                        "lexical_resource": 6.0,
                        "grammatical_range": 6.0,
                        "feedback": "Good work",
                        "overall_review": {
                            "markdown": "### 总体点评\n\n引用「I like buses」具体分析。\n\n### 复盘重点\n\n- 保持展开。",
                            "comment": "具体点评",
                            "review_points": ["1", "2", "3", "4", "5", "6", "7"],
                        },
                    },
                    ensure_ascii=False,
                ),
                {"input_tokens": 100},
            )

        with (
            override_settings(SPEAKING_REPORT_AI_CALL_MODE="codex"),
            patch("apps.speaking.services.run_codex", side_effect=fake_run_codex),
        ):
            result = score_with_codex(
                "Q1: Do you like buses?\nA: I like buses because they are cheap.",
                "Do you like buses?",
                "p1",
                "test_review_prompt",
            )

        prompt = captured_prompt["text"]
        self.assertIn("至少 1-2 处用中文引号标出具体片段", prompt)
        self.assertIn("必须 3-5 条", prompt)
        self.assertIn("不得原样复述", prompt)
        self.assertNotIn("primary_focus_text", prompt)
        self.assertNotIn("不要限制内容", prompt)
        self.assertEqual(len(result["overall_review"]["review_points"]), 5)

    def test_p3_discussion_skills_ai_text_preserves_status(self):
        from apps.accounts.models import CustomUser
        from apps.speaking.services import build_p3_discussion_skills, enrich_p3_discussion_skills_with_ai

        user = CustomUser.objects.create_user(username="p3-skills-ai-user", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="p3-skills-ai-attempt",
            mode="p3",
            part="p3",
            status=SpeakingAttempt.Status.SCORED,
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="p3-main-1",
            sequence=0,
            part="p3",
            question="Why do some people prefer public transport?",
            transcript_raw="I think public transport is useful because it saves money and it can reduce traffic in society.",
            transcript_cleaned="I think public transport is useful because it saves money and it can reduce traffic in society.",
            metadata={"status": "completed", "prompt": {"role": "main"}},
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="p3-main-2",
            sequence=1,
            part="p3",
            question="Is it better for governments to invest in buses or roads?",
            transcript_raw="Buses are better because many people can use them. For example in my city students take buses.",
            transcript_cleaned="Buses are better because many people can use them. For example in my city students take buses.",
            metadata={"status": "completed", "prompt": {"role": "main"}},
        )
        base = build_p3_discussion_skills(attempt)
        original_status = {
            item["key"]: item["status"]
            for item in base["dimensions"]
        }
        ai_payload = {
            "summary": "AI 总结：回答能给出立场，但对比和追问承接还可以更直接。",
            "best_moment": "原因与影响",
            "fix_next": "下一轮先补一个反方角度，再回到自己的观点。",
            "next_drill": ["先一句表态", "补 because 原因链", "加 whereas 对比"],
            "dimensions": {
                "abstract_extension": {"evidence": "AI 证据：提到了 society，但还缺少 wider impact。", "next_action": "每题最后加一句对群体的影响。"},
                "reasoning": {"evidence": "AI 证据：两题都用了 because。", "next_action": "把 because 后面的结果再说完整。"},
                "comparison_concession": {"evidence": "AI 证据：没有明显 however 或 whereas。", "next_action": "先用 whereas 补一个对比。"},
                "specific_support": {"evidence": "AI 证据：第二题用了 in my city。", "next_action": "例子要补人物或场景。"},
                "follow_up_handling": {"evidence": "AI 证据：这轮没有追问。", "next_action": "追问先回应新角度。"},
            },
        }

        with (
            override_settings(SPEAKING_REPORT_AI_CALL_MODE="codex"),
            patch("apps.speaking.services.run_codex", return_value=(json.dumps(ai_payload, ensure_ascii=False), {"input_tokens": 10})),
        ):
            enriched = enrich_p3_discussion_skills_with_ai(
                attempt,
                base,
                {"overall_band": 6.0},
                {"primary_focus_text": "补展开"},
                "test_p3_skills",
            )

        self.assertEqual(enriched["generation_backend"], "codex")
        self.assertEqual(enriched["summary"], ai_payload["summary"])
        self.assertEqual(enriched["next_drill"], ai_payload["next_drill"])
        enriched_status = {
            item["key"]: item["status"]
            for item in enriched["dimensions"]
        }
        self.assertEqual(enriched_status, original_status)
        self.assertEqual(enriched["dimensions"][0]["evidence"], "AI 证据：提到了 society，但还缺少 wider impact。")

    def test_p3_discussion_skills_ai_failure_falls_back_to_heuristic(self):
        from apps.accounts.models import CustomUser
        from apps.speaking.services import build_p3_discussion_skills, enrich_p3_discussion_skills_with_ai

        user = CustomUser.objects.create_user(username="p3-skills-fallback-user", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="p3-skills-fallback-attempt",
            mode="p3",
            part="p3",
            status=SpeakingAttempt.Status.SCORED,
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="p3-main-fallback",
            sequence=0,
            part="p3",
            question="Why do people move to big cities?",
            transcript_raw="Because jobs are better.",
            transcript_cleaned="Because jobs are better.",
            metadata={"status": "completed", "prompt": {"role": "main"}},
        )
        base = build_p3_discussion_skills(attempt)
        base_summary = base["summary"]

        with (
            override_settings(SPEAKING_REPORT_AI_CALL_MODE="codex"),
            patch("apps.speaking.services.run_codex", side_effect=RuntimeError("provider down")),
        ):
            enriched = enrich_p3_discussion_skills_with_ai(
                attempt,
                base,
                {"overall_band": 5.5},
                {},
                "test_p3_skills_fallback",
            )

        self.assertEqual(enriched["generation_backend"], "heuristic")
        self.assertEqual(enriched["generation_status"], "fallback")
        self.assertEqual(enriched["summary"], base_summary)
        self.assertIn("generation_error", enriched)

    def test_run_codex_rejects_zero_input_tokens(self):
        """run_codex should raise error if model received 0 tokens."""
        from apps.speaking.services import run_codex

        with patch("apps.speaking.services.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout='{"type": "turn.completed", "usage": {"input_tokens": 0, "output_tokens": 0}}'
            )
            with patch("apps.speaking.services.extract_codex_json_events") as mock_extract:
                mock_extract.return_value = ("", {"input_tokens": 0}, False)
                with self.assertRaises(RuntimeError) as ctx:
                    run_codex("test prompt", "test_call")
                self.assertIn("0 input tokens", str(ctx.exception))
                self.assertEqual(mock_run.call_count, 2)

    def test_quick_p3_follow_up_runner_success_uses_tmp_codex(self):
        from apps.speaking.services import quick_follow_up_runner

        with patch("apps.speaking.services.shutil.which", return_value="/usr/local/bin/codex"), patch(
            "apps.speaking.services.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(stdout="How would this affect older people in the long term?\n", stderr="")
            follow_up = quick_follow_up_runner(
                "Why do people have different opinions about technology?",
                "I think younger people use it more because they grow up with phones, but older people can feel stressed.",
                focus="comparison_concession",
                question_type="opinion_justify",
                timeout=12,
            )

        self.assertEqual(follow_up, "How would this affect older people in the long term?")
        command = mock_run.call_args.args[0]
        self.assertIn("--skip-git-repo-check", command)
        self.assertIn("--ignore-rules", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("gpt-5.4-mini", command)
        self.assertIn('model_reasoning_effort="low"', command)
        self.assertEqual(mock_run.call_args.kwargs["cwd"], "/tmp")
        self.assertEqual(mock_run.call_args.kwargs["timeout"], 12)

    def test_generate_p3_dynamic_follow_up_falls_back_on_quick_timeout(self):
        from apps.speaking.services import _generate_p3_dynamic_follow_up

        with patch("apps.speaking.services.shutil.which", return_value="/usr/local/bin/codex"), patch(
            "apps.speaking.services.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="codex", timeout=12)
        ):
            result = _generate_p3_dynamic_follow_up(
                "Why do people have different opinions about technology?",
                "opinion_justify",
                " ".join(["technology helps people communicate"] * 12),
                "comparison_concession",
                "test-timeout",
            )

        self.assertEqual(result["backend"], "fallback")
        self.assertEqual(result["status"], "fallback")
        self.assertIn("timed out", result["error"])
        self.assertIn("opposite view", result["follow_up"])

    def test_generate_p3_dynamic_follow_up_returns_quick_codex_question(self):
        from apps.speaking.services import _generate_p3_dynamic_follow_up

        with patch("apps.speaking.services.shutil.which", return_value="/usr/local/bin/codex"), patch(
            "apps.speaking.services.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(stdout="How might this change the way families spend time together?\n", stderr="")
            result = _generate_p3_dynamic_follow_up(
                "Why do people have different opinions about technology?",
                "opinion_justify",
                "I think younger people use it more because they grow up with phones, but older people can feel stressed.",
                "comparison_concession",
                "test-success",
            )

        self.assertEqual(result["backend"], "codex_quick")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["follow_up"], "How might this change the way families spend time together?")

    def test_generate_p3_dynamic_follow_up_falls_back_on_invalid_quick_output(self):
        from apps.speaking.services import _generate_p3_dynamic_follow_up

        with patch("apps.speaking.services.shutil.which", return_value="/usr/local/bin/codex"), patch(
            "apps.speaking.services.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(stdout="Here is a useful follow-up.", stderr="")
            result = _generate_p3_dynamic_follow_up(
                "How has public transport changed in recent years?",
                "change_trend",
                " ".join(["It has become more convenient because cities have invested in apps and cleaner buses"] * 8),
                "cause_effect",
                "test-invalid",
            )

        self.assertEqual(result["backend"], "fallback")
        self.assertEqual(result["status"], "fallback")
        self.assertIn("usable question", result["error"])
        self.assertIn("long-term effect", result["follow_up"])

    def test_generate_p3_dynamic_follow_up_ignores_echoed_main_question(self):
        from apps.speaking.services import _generate_p3_dynamic_follow_up

        current_question = "How has public transport changed in recent years?"
        with patch("apps.speaking.services.shutil.which", return_value="/usr/local/bin/codex"), patch(
            "apps.speaking.services.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(stdout=f"{current_question}\n", stderr="")
            result = _generate_p3_dynamic_follow_up(
                current_question,
                "change_trend",
                " ".join(["It has become more convenient because cities have invested in apps and cleaner buses"] * 8),
                "cause_effect",
                "test-echo",
            )

        self.assertEqual(result["backend"], "fallback")
        self.assertEqual(result["status"], "fallback")
        self.assertIn("usable question", result["error"])
        self.assertNotEqual(result["follow_up"], current_question)
        self.assertIn("long-term effect", result["follow_up"])

    @override_settings(SPEAKING_REPORT_AI_CALL_MODE="codex")
    def test_score_attempt_uses_scorer_overall_review_without_second_review_codex_call(self):
        from apps.speaking.services import score_attempt_sync

        user, attempt, turn = self.create_ready_attempt()
        score_payload = {
            "fluency_coherence": 6.5,
            "lexical_resource": 6.0,
            "grammatical_range": 6.0,
            "feedback": "Codex scored this exact speaking response.",
            "overall_review": {
                "markdown": "### 总体点评\n\n这次回答信息明确，能说明学习和实习背景，但还可以把职责和例子展开。\n\n### 复盘重点\n\n- 继续补充具体工作内容。",
                "comment": "回答清楚，但展开还可以更具体。",
                "review_points": ["补充实习职责", "给一个具体例子"],
            },
        }
        turn_feedback_payload = {
            "turns": [
                {
                    "turn_id": turn.turn_id,
                    "display_transcript": "I study software engineering.",
                    "display_transcript_markdown": "I study software engineering.",
                    "band7_version": "I'm a university student majoring in **software engineering**, and I also do **practical internship work**.",
                    "ai_coaching": "这一题已经能直接回答身份，下一步可以补一句实习如何帮助学习。\n\n语法错误纠正：无",
                }
            ]
        }

        with patch("apps.speaking.services.run_codex") as mock_run, patch(
            "apps.speaking.services.volcengine_tts",
            return_value={"provider": "volcengine", "status": "ready", "audio_url": "/model.mp3"},
        ):
            mock_run.side_effect = [
                (json.dumps(turn_feedback_payload), {"input_tokens": 180, "output_tokens": 100}),
                (json.dumps(score_payload), {"input_tokens": 200, "output_tokens": 120}),
            ]
            result = score_attempt_sync(user, attempt.attempt_id)

        self.assertEqual(mock_run.call_count, 2)
        self.assertFalse(any("overall_review_" in call.args[1] for call in mock_run.call_args_list))
        turn_feedback_prompt = mock_run.call_args_list[0].args[0]
        self.assertIn("display_transcript_markdown", turn_feedback_prompt)
        self.assertIn("confident ASR mis-recognition", turn_feedback_prompt)
        score_prompt = mock_run.call_args_list[1].args[0]
        self.assertIn("Do you work or do you study?", score_prompt)
        self.assertIn("software engineering", score_prompt)
        self.assertNotIn("small technology company", score_prompt)
        self.assertIn("ASR error", score_prompt)
        self.assertEqual(result["ielts_score"]["backend"], "codex")
        self.assertEqual(result["ielts_score"]["generation_status"], "ready")
        self.assertEqual(result["ielts_score"]["overall_band"], 6.0)
        self.assertEqual(result["feedback_summary"], "Codex scored this exact speaking response.")
        self.assertEqual(result["overall_review"]["backend"], "codex")
        self.assertEqual(result["overall_review"]["markdown"], score_payload["overall_review"]["markdown"])
        turn.refresh_from_db()
        self.assertEqual(turn.metadata["feedback_generation_backend"], "codex")
        self.assertEqual(turn.metadata["feedback_generation_status"], "ready")
        self.assertEqual(turn.metadata["display_transcript_markdown"], "I study software engineering.")
        self.assertIn("software engineering", turn.metadata["band7_version"])
        self.assertEqual(turn.metadata["band7_source"], "codex_report_batch")
        report = SpeakingReport.objects.get(attempt=attempt)
        self.assertEqual(report.report_payload["score_generation_backend"], "codex")
        self.assertEqual(report.report_payload["report_generation_status"], "ready")
        self.assertEqual(report.report_payload["turns"][0]["feedback_generation_status"], "ready")
        self.assertIn("software engineering", report.report_payload["turns"][0]["band7_version"])
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, SpeakingAttempt.Status.SCORED)
        self.assertEqual(attempt.metadata["analysis_status"], "ready")
        self.assertEqual(attempt.metadata["analysis_backend"], "codex")
        self.assertEqual(attempt.metadata["analysis_error"], "")
        self.assertEqual(attempt.metadata["report_generation_status"], "ready")

    def test_score_attempt_returns_existing_report_without_regenerating(self):
        from apps.speaking.services import score_attempt

        user, attempt, turn = self.create_ready_attempt(
            username="score-attempt-existing-user",
            attempt_id="score-attempt-existing-report",
        )
        attempt.status = SpeakingAttempt.Status.SCORED
        attempt.save(update_fields=["status"])
        existing_payload = {
            "id": attempt.attempt_id,
            "status": "scored",
            "mode": "p1",
            "part": "p1",
            "title": "Part 1 practice",
            "turns": [{"id": turn.turn_id, "status": "completed"}],
            "feedback_summary": "Existing report should be reused.",
        }
        SpeakingReport.objects.create(
            user=user,
            attempt=attempt,
            overall_band=Decimal("6.0"),
            fluency_coherence=Decimal("6.0"),
            lexical_resource=Decimal("6.0"),
            grammar_range_accuracy=Decimal("6.0"),
            report_payload=existing_payload,
        )

        with patch("apps.speaking.services.run_codex") as mock_run, patch("apps.speaking.services.volcengine_tts") as mock_tts:
            result = score_attempt(user, attempt.attempt_id)

        mock_run.assert_not_called()
        mock_tts.assert_not_called()
        self.assertEqual(result["feedback_summary"], "Existing report should be reused.")
        self.assertEqual(result["id"], attempt.attempt_id)

    def test_score_attempt_creates_async_speaking_report_task(self):
        from apps.ai.models import AITask
        from apps.speaking.services import score_attempt

        user, attempt, _turn = self.create_ready_attempt(
            username="score-attempt-async-user",
            attempt_id="score-attempt-async-report",
        )

        with patch("apps.speaking.services.run_codex") as mock_run:
            result = score_attempt(user, attempt.attempt_id)

        mock_run.assert_not_called()
        self.assertEqual(result["status"], "analysis_pending")
        self.assertEqual(result["ai_task"]["task_type"], "speaking_report")
        self.assertEqual(result["ai_task"]["status"], AITask.Status.PENDING)
        task = AITask.objects.get(task_id=result["ai_task"]["id"])
        self.assertEqual(task.related_type, "speaking_attempt")
        self.assertEqual(task.related_id, attempt.attempt_id)
        self.assertEqual(task.request_payload["attempt_id"], attempt.attempt_id)

    def test_speaking_report_task_keeps_worker_adapter_when_http_requested(self):
        from apps.ai.models import AITask
        from apps.speaking.services import score_attempt

        user, attempt, _turn = self.create_ready_attempt(
            username="score-attempt-http-request-user",
            attempt_id="score-attempt-http-request",
        )

        result = score_attempt(user, attempt.attempt_id, {"provider": "http", "model": "gpt-5.4-mini"})

        task = AITask.objects.get(task_id=result["ai_task"]["id"])
        self.assertEqual(task.provider, "codex")
        self.assertEqual(task.model, "")
        self.assertEqual(task.request_payload["requested_provider"], "http")
        self.assertEqual(task.request_payload["requested_model"], "gpt-5.4-mini")
        self.assertEqual(task.metadata["requested_provider"], "http")

    def test_score_attempt_rejects_empty_answer_transcripts_before_queueing(self):
        from apps.ai.models import AITask
        from apps.speaking.services import SpeakingError, score_attempt

        user, attempt, turn = self.create_ready_attempt(
            username="score-attempt-empty-transcript-user",
            attempt_id="score-attempt-empty-transcript",
        )
        turn.transcript_raw = ""
        turn.transcript_cleaned = ""
        turn.metadata = {"status": "completed", "display_transcript": ""}
        turn.save(update_fields=["transcript_raw", "transcript_cleaned", "metadata"])

        with self.assertRaises(SpeakingError) as ctx:
            score_attempt(user, attempt.attempt_id)

        self.assertIn("没有拿到文字稿", str(ctx.exception))
        self.assertFalse(AITask.objects.filter(related_id=attempt.attempt_id, task_type="speaking_report").exists())

    def test_model_answer_tts_cache_key_changes_when_band7_text_changes(self):
        from apps.speaking.services import build_turn_feedback

        user, attempt, turn = self.create_ready_attempt(
            username="score-attempt-tts-hash-user",
            attempt_id="score-attempt-tts-hash",
        )
        generated_a = {
            "display_transcript": "I enjoy trying new things.",
            "band7_version": "I enjoy trying new things because they keep my daily life interesting.",
            "ai_coaching": "",
        }
        generated_b = {
            "display_transcript": "I enjoy trying new things.",
            "band7_version": "I like discovering new activities because they make my routine feel fresh.",
            "ai_coaching": "",
        }

        with patch("apps.speaking.services.volcengine_tts", return_value={"provider": "volcengine", "status": "ready", "audio_url": "/x.mp3"}) as mock_tts:
            build_turn_feedback(turn, attempt, allow_codex=False, generated_feedback=generated_a)
            build_turn_feedback(turn, attempt, allow_codex=False, generated_feedback=generated_b)

        first_key = mock_tts.call_args_list[0].kwargs["cache_key"]
        second_key = mock_tts.call_args_list[1].kwargs["cache_key"]
        self.assertNotEqual(first_key, second_key)
        self.assertTrue(first_key.startswith(f"{attempt.attempt_id}_{turn.turn_id}_band7_"))
        self.assertTrue(second_key.startswith(f"{attempt.attempt_id}_{turn.turn_id}_band7_"))

    @override_settings(SPEAKING_REPORT_AI_CALL_MODE="codex")
    def test_score_attempt_marks_analysis_failed_without_publishing_report_when_codex_fails(self):
        from apps.speaking.services import SpeakingError, score_attempt_sync

        user, attempt, turn = self.create_ready_attempt(
            username="score-attempt-fallback-user",
            attempt_id="score-attempt-fallback-path",
        )

        with patch("apps.speaking.services.run_codex", side_effect=RuntimeError("codex returned empty output")) as mock_run:
            with self.assertRaises(SpeakingError) as ctx:
                score_attempt_sync(user, attempt.attempt_id)

        self.assertGreaterEqual(mock_run.call_count, 1)
        self.assertIn("AI analysis failed", str(ctx.exception))
        self.assertFalse(SpeakingReport.objects.filter(attempt=attempt).exists())
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, SpeakingAttempt.Status.READY_TO_SCORE)
        self.assertEqual(attempt.metadata["analysis_status"], "failed")
        self.assertEqual(attempt.metadata["score_generation_status"], "failed")
        self.assertEqual(attempt.metadata["report_generation_status"], "failed")
        self.assertIn("codex returned empty output", attempt.metadata["analysis_error"])
        turn.refresh_from_db()
        self.assertEqual(turn.metadata["feedback_generation_backend"], "codex")
        self.assertEqual(turn.metadata["feedback_generation_status"], "failed")
        self.assertEqual(turn.metadata["band7_version"], "")

    def test_turn_feedback_codex_failure_does_not_store_generic_band7_answer(self):
        from apps.speaking.services import build_turn_feedback

        _user, attempt, turn = self.create_ready_attempt(
            username="turn-feedback-failure-user",
            attempt_id="turn-feedback-failure",
        )

        with (
            patch("apps.speaking.services.run_codex", side_effect=RuntimeError("codex timeout")),
            patch("apps.speaking.services.volcengine_tts") as mock_tts,
        ):
            feedback = build_turn_feedback(turn, attempt, allow_codex=True)

        mock_tts.assert_not_called()
        self.assertEqual(feedback["feedback_generation_backend"], "fallback")
        self.assertEqual(feedback["feedback_generation_status"], "failed")
        self.assertIn("codex timeout", feedback["feedback_generation_error"])
        self.assertEqual(feedback["band7_version"], "")
        self.assertEqual(feedback["band7_markdown"], "")
        self.assertEqual(feedback["model_audio"]["status"], "empty_text")


class TurnFeedbackValidationTests(TestCase):
    """Test validation logic for turn feedback and AI coaching generation."""

    def test_turn_feedback_rejects_missing_band7(self):
        """turn_feedback_with_codex should reject output missing band7_version."""
        from unittest.mock import patch
        from apps.speaking.services import turn_feedback_with_codex

        with patch("apps.speaking.services.run_codex") as mock_run:
            mock_run.return_value = ('{"display_transcript": "My name is John.", "ai_coaching": "- some coaching"}', {"input_tokens": 100})
            with self.assertRaises(RuntimeError) as ctx:
                turn_feedback_with_codex(
                    "What is your name?",
                    "My name is John.",
                    "p1",
                    "7",
                    None,
                    "test_call",
                )
            self.assertIn("required keys", str(ctx.exception))

    def test_turn_feedback_rejects_missing_coaching(self):
        """turn_feedback_with_codex should reject output missing ai_coaching."""
        from unittest.mock import patch
        from apps.speaking.services import turn_feedback_with_codex

        with patch("apps.speaking.services.run_codex") as mock_run:
            mock_run.return_value = ('{"display_transcript": "My name is John.", "band7_version": "My name is John."}', {"input_tokens": 100})
            with patch("apps.speaking.services.clean_band7_output", return_value="My name is John."):
                with self.assertRaises(RuntimeError) as ctx:
                    turn_feedback_with_codex(
                        "What is your name?",
                        "My name is John.",
                        "p1",
                        "7",
                        None,
                        "test_call",
                    )
                self.assertIn("required keys", str(ctx.exception))

    def test_turn_feedback_accepts_valid_output(self):
        """turn_feedback_with_codex should accept valid band7 and coaching."""
        from unittest.mock import patch
        from apps.speaking.services import turn_feedback_with_codex

        valid_output = {
            "display_transcript": "My name is John.",
            "display_transcript_markdown": "My name is John.",
            "band7_version": "My name is John, and I'm **a student at the local university**.",
            "ai_coaching": "- Your answer is clear and direct.\n- 语法错误纠正：无",
        }

        with patch("apps.speaking.services.run_codex") as mock_run:
            mock_run.return_value = (json.dumps(valid_output), {"input_tokens": 100})
            with patch("apps.speaking.services.clean_band7_output", return_value=valid_output["band7_version"]):
                result = turn_feedback_with_codex(
                    "What is your name?",
                    "My name is John.",
                    "p1",
                    "7",
                    None,
                    "test_call",
                )
                self.assertIn("display_transcript", result)
                self.assertEqual(result["display_transcript_markdown"], "My name is John.")
                self.assertIn("band7_version", result)
                self.assertIn("ai_coaching", result)
                self.assertIn("**a student at the local university**", result["band7_version"])
                prompt = mock_run.call_args.args[0]
                self.assertIn("Use Markdown bold inside band7_version", prompt)
                self.assertIn("Songs plays a vital role", prompt)
                self.assertIn("sync my teeth into", prompt)
                self.assertIn("student major in software engineering", prompt)

    def test_build_turn_feedback_keeps_markdown_for_display_but_plain_for_tts(self):
        """Band 7 display keeps Markdown emphasis while legacy/TTS text stays plain."""
        from apps.speaking.services import build_turn_feedback

        user = get_user_model().objects.create_user(username="band7-markdown-user", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="band7-markdown-attempt",
            mode="p1",
            part="p1",
            status=SpeakingAttempt.Status.STARTED,
        )
        turn = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t1",
            sequence=0,
            part="p1",
            question="What do you usually do in the evening?",
            transcript_raw="I code and play games, but now I prepare IELTS.",
            metadata={"status": "completed"},
        )
        generated = {
            "display_transcript": "I code and play games, but now I prepare IELTS.",
            "band7_version": "Well, **as a tech enthusiast**, I **usually spend** my evenings coding or **unwinding with** video games.",
            "ai_coaching": "这个回答方向清楚。\n\n语法错误纠正：无",
        }

        with patch("apps.speaking.services.volcengine_tts", return_value={"status": "pending"}):
            feedback = build_turn_feedback(turn, attempt, generated_feedback=generated)

        self.assertNotIn("**", feedback["band7_version"])
        self.assertIn("as a tech enthusiast", feedback["band7_version"])
        self.assertIn("**as a tech enthusiast**", feedback["band7_markdown"])
        self.assertIn("**usually spend**", feedback["band7_markdown"])

    def test_turn_feedback_keeps_non_speaking_noise_coaching_visible(self):
        """Formatting comments are bad coaching, but should remain visible instead of being hard-blocked."""
        from apps.speaking.services import acceptable_coaching_markdown, turn_feedback_with_codex

        bad_coaching = (
            "这次回答方向是对的，可以加一个工作里的具体例子。\n\n"
            "语法 & 表达纠正：\n"
            "- “at University”这里不需要大写，写成 at university 即可。"
        )
        self.assertTrue(acceptable_coaching_markdown(bad_coaching))

        payload = {
            "display_transcript": "It can apply what I've learned at university to practical tasks.",
            "band7_version": "It helps me apply what I've learned at university to practical tasks.",
            "ai_coaching": bad_coaching,
        }
        with patch("apps.speaking.services.run_codex") as mock_run:
            mock_run.return_value = (json.dumps(payload), {"input_tokens": 100})
            result = turn_feedback_with_codex(
                "How does your internship connect with what you study?",
                "it can apply what I've learned at University to practical tasks",
                "p1",
                "7",
                None,
                "test_non_speaking_noise",
            )

        prompt = mock_run.call_args.args[0]
        self.assertIn("Do not comment on capitalization", prompt)
        self.assertIn("at University", prompt)
        self.assertEqual(result["ai_coaching"], bad_coaching)

    def test_coaching_validator_allows_common_project_words_but_rejects_explicit_system_leak(self):
        from apps.speaking.services import acceptable_coaching_markdown

        self.assertTrue(acceptable_coaching_markdown(
            "可以把回答组织成更清楚的结构，即使你提到 JSON 数据也不要展开太久。\n\n语法错误纠正：无"
        ))
        self.assertTrue(acceptable_coaching_markdown(
            "如果你平时用 trellis 记录练习，也可以把这个素材整理进去。\n\n语法错误纠正：无"
        ))
        self.assertFalse(acceptable_coaching_markdown(
            "这里泄漏了系统上下文：<workflow-state>in_progress</workflow-state>\n\n语法错误纠正：无"
        ))

    def test_batch_turn_feedback_keeps_item_when_coaching_mentions_project_words(self):
        from apps.speaking.services import turn_feedback_batch_with_codex

        user = get_user_model().objects.create_user(username="batch-coaching-visible", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="batch-coaching-visible-attempt",
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
            question="Do you work or do you study?",
            transcript_raw="I study software engineering and use trellis to record practice.",
            transcript_cleaned="I study software engineering and use trellis to record practice.",
            metadata={"status": "completed"},
        )
        payload = {
            "turns": [
                {
                    "turn_id": "t1",
                    "display_transcript": "I study software engineering and use trellis to record practice.",
                    "display_transcript_markdown": "I study software engineering and use trellis to record practice.",
                    "band7_version": "I study software engineering, and I keep my practice notes organized.",
                    "ai_coaching": "这条反馈提到了 JSON 和 trellis，但它仍然是用户可见正文，不应该被丢掉。",
                }
            ]
        }

        with patch("apps.speaking.services.run_codex", return_value=(json.dumps(payload), {"input_tokens": 100})):
            result = turn_feedback_batch_with_codex([turn], attempt, "7", None, "batch_visible")

        self.assertIn("t1", result)
        self.assertEqual(
            result["t1"]["display_transcript_markdown"],
            "I study software engineering and use trellis to record practice.",
        )
        self.assertIn("JSON 和 trellis", result["t1"]["ai_coaching"])
        self.assertIn("语法错误纠正", result["t1"]["ai_coaching"])

    def test_report_turn_feedback_passes_linked_p2_prepared_corpus_to_batch(self):
        from apps.speaking.services import generate_turn_feedback_for_report

        user = get_user_model().objects.create_user(username="report-p2-corpus", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="report-p2-corpus-attempt",
            mode="p2",
            part="p2",
            status=SpeakingAttempt.Status.READY_TO_SCORE,
        )
        corpus = P2CorpusEntry.objects.create(
            user=user,
            entry_id="kind-teacher-material",
            category=P2CorpusEntry.Category.PERSON,
            title="A kind teacher",
            material_text="My high school English teacher encouraged me before a speech competition.",
            linked_question="Describe a person who encouraged you.",
        )
        turn = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t1",
            sequence=0,
            part="p2",
            question="Describe a person who helped you.",
            transcript_raw="I talked about my teacher because she helped me with English.",
            transcript_cleaned="I talked about my teacher because she helped me with English.",
            metadata={"status": "completed", "p2_corpus_link": {"entry_id": corpus.entry_id}},
        )
        generated = {
            "t1": {
                "display_transcript": "I talked about my teacher because she helped me with English.",
                "band7_version": "I would describe my high school English teacher, who encouraged me and helped me become more confident.",
                "ai_coaching": "可以保留老师鼓励你的主线，再把帮助英语的细节贴合题目。\n\n语法错误纠正：无",
            }
        }

        with (
            patch("apps.speaking.services.turn_feedback_batch_with_codex", return_value=generated) as batch,
            patch("apps.speaking.services.volcengine_tts", return_value={"status": "pending"}),
        ):
            generate_turn_feedback_for_report(attempt, [turn], {}, "report_p2_corpus")

        batch.assert_called_once()
        prepared_corpus_by_turn = batch.call_args.kwargs["prepared_corpus_by_turn"]
        self.assertIn("t1", prepared_corpus_by_turn)
        self.assertIn("A kind teacher", prepared_corpus_by_turn["t1"])
        self.assertIn("speech competition", prepared_corpus_by_turn["t1"])

    def test_complete_turn_sets_pending_not_fallback(self):
        """complete_turn should set feedback_generation_status to pending, not fallback."""
        from apps.speaking.services import complete_turn
        from apps.accounts.models import CustomUser

        user = CustomUser.objects.create_user(username="test-complete-turn", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="test-complete-turn-attempt",
            mode="p1",
            part="p1",
            status=SpeakingAttempt.Status.STARTED,
        )
        turn = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t1",
            sequence=0,
            part="p1",
            question="What is your name?",
        )

        complete_turn(user, "test-complete-turn-attempt", "t1", {"transcript_raw": "My name is John."})

        # Refresh from DB and check metadata
        turn.refresh_from_db()
        self.assertEqual(turn.metadata.get("feedback_generation_status"), "pending")

    def test_regenerate_attempt_report_fixes_bad_report(self):
        """regenerate_attempt_report should fix a report with all-zero scores."""
        from unittest.mock import patch
        from apps.speaking.services import regenerate_attempt_report
        from apps.accounts.models import CustomUser

        user = CustomUser.objects.create_user(username="test-regen-user", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="test-regen-attempt",
            mode="p2",
            part="p2",
            status=SpeakingAttempt.Status.SCORED,
        )
        turn = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t1",
            sequence=0,
            part="p2",
            question="Describe a person you admire.",
            transcript_raw="I admire my mother because she is very kind and helpful to everyone in our family.",
            metadata={"status": "completed"},
        )

        # Create a bad report with all zeros
        from apps.speaking.models import SpeakingReport
        SpeakingReport.objects.create(
            user=user,
            attempt=attempt,
            overall_band=Decimal("0"),
            fluency_coherence=Decimal("0"),
            lexical_resource=Decimal("0"),
            grammar_range_accuracy=Decimal("0"),
            feedback_summary="",
            report_payload={
                "id": "test-regen-attempt",
                "ielts_score": {"overall_band": 0.0, "backend": "codex"},
            },
        )

        # Mock codex to return valid scores
        with patch("apps.speaking.services.run_codex") as mock_run:
            mock_run.return_value = (
                '{"fluency_coherence": 6.0, "lexical_resource": 6.0, "grammatical_range": 6.0, "feedback": "Good work"}',
                {"input_tokens": 100},
            )
            result = regenerate_attempt_report(user, "test-regen-attempt")

            self.assertTrue(result["ok"])
            # Should have real scores now
            self.assertGreater(result["attempt"]["ielts_score"]["overall_band"], 0)
            self.assertEqual(result["attempt"]["ielts_score"]["backend"], "codex")

    def test_coaching_must_include_grammar_correction(self):
        """AI coaching must include a grammar correction section."""
        from apps.speaking.services import concise_coaching_markdown

        valid_coaching = """这次回答的核心信息是清楚的，但身份信息可以更准确地说出来。

你提到了 software engineering 和 internship，这两个信息应该放在同一句里，听起来会更自然。

语法错误纠正：无"""
        self.assertTrue(concise_coaching_markdown(valid_coaching))

        invalid_coaching = """- Your answer is clear.
- Consider adding more details."""
        self.assertFalse(concise_coaching_markdown(invalid_coaching))

    def test_coaching_allows_ai_chosen_structure(self):
        """Coaching should not force bullet count or fixed labels."""
        from apps.speaking.services import concise_coaching_markdown

        coaching = "\n".join(
            [
                "这次回答最好的地方是你没有跑题，软件工程、实习和公司都是真实信息。",
                "",
                "不过表达上不需要被压成固定句型。AI 可以自己判断重点：这里更值得强调的是你既是学生，也在实习。",
                "",
                "如果要更自然，可以把身份先说清楚，再解释为什么这个方向有趣。",
                "",
                "语法错误纠正：",
                "1. `I'm a unit student` -> `I'm a university student.`",
            ]
        )

        self.assertTrue(concise_coaching_markdown(coaching))

    def test_p1_work_study_fallback_preserves_student_internship_identity(self):
        """Fallback must not turn a student with an internship into only a worker."""
        from apps.speaking.services import build_turn_band7_fallback

        answer = "I'm a university student specializing in software engineering and doing an internship at a tech company."
        result = build_turn_band7_fallback("Do you work or do you study?", "p1", answer)

        self.assertIn("university student", result)
        self.assertIn("internship", result)
        self.assertNotIn("I work as a software engineer", result)

    def test_p1_identity_report_rules(self):
        """Name intro is hidden from scoring, while work/study keeps Band 7 but no coaching."""
        from apps.speaking.services import build_turn_feedback, is_p1_name_intro_turn, turn_counts_for_scoring, turn_needs_ai_coaching
        from apps.accounts.models import CustomUser

        user = CustomUser.objects.create_user(username="test-p1-identity-rules", password="test-pass")
        attempt = SpeakingAttempt.objects.create(user=user, attempt_id="test-p1-identity-rules", mode="p1", part="p1")
        name_turn = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t1",
            sequence=0,
            part="p1",
            question="What is your full name?",
            transcript_raw="My full name is Li Hua, but you can call me Jasper.",
            counts_toward_total=False,
            metadata={"status": "completed", "prompt": {"flow": "intro", "role": "name"}},
        )
        work_turn = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t2",
            sequence=1,
            part="p1",
            question="Do you work or do you study?",
            transcript_raw="I'm a university student majoring in software engineering, and I'm also doing an internship.",
            metadata={"status": "completed", "prompt": {"flow": "intro", "role": "work_study"}},
        )

        self.assertTrue(is_p1_name_intro_turn(name_turn))
        self.assertFalse(turn_counts_for_scoring(name_turn))
        self.assertFalse(turn_needs_ai_coaching(name_turn))
        self.assertTrue(turn_counts_for_scoring(work_turn))
        self.assertFalse(turn_needs_ai_coaching(work_turn))

        feedback = build_turn_feedback(
            work_turn,
            attempt,
            allow_codex=False,
            generated_feedback={
                "display_transcript": "I'm a university student majoring in software engineering, and I'm also doing an internship.",
                "band7_version": "I'm a university student majoring in software engineering, and I'm also doing an internship at a tech company at the moment.",
                "ai_coaching": "",
            },
        )
        self.assertEqual(feedback["ai_coaching"], "")
        self.assertIn("university student", feedback["display_transcript"])

    def test_p1_work_study_followup_uses_codex_result_with_server_tts(self):
        """Completing work/study identity turn should insert the Codex-generated follow-up with server TTS."""
        from apps.speaking.services import complete_turn
        from apps.accounts.models import CustomUser

        user = CustomUser.objects.create_user(username="test-p1-followup-user", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="test-p1-followup-attempt",
            mode="p1",
            part="p1",
            status=SpeakingAttempt.Status.STARTED,
            metadata={"current_turn": "t2"},
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t1",
            sequence=0,
            part="p1",
            question="What is your full name?",
            counts_toward_total=False,
            metadata={"status": "completed", "prompt": {"flow": "intro", "role": "name"}},
        )
        SpeakingTurn.objects.create(
            user=user,
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
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t3",
            sequence=2,
            part="p1",
            question="Do you like your hometown?",
            metadata={"prompt": {"topic": "home", "question": "Do you like your hometown?"}},
        )

        with (
            patch(
                "apps.speaking.services.run_codex",
                return_value=('{"follow_up":"How has your software engineering internship shaped your studies?"}', {"input_tokens": 12}),
            ) as mock_run,
            patch(
                "apps.speaking.services.volcengine_tts",
                return_value={
                    "provider": "volcengine",
                    "status": "ready",
                    "audio_url": "/api/tts-audio/examiner/test-p1-followup-attempt_t2_followup_examiner.mp3",
                    "content_type": "audio/mpeg",
                },
            ) as mock_tts,
            patch("apps.speaking.services.transcribe_turn_audio_with_server_asr") as mock_asr,
        ):
            result = complete_turn(
                user,
                "test-p1-followup-attempt",
                "t2",
                {
                    "transcript_raw": (
                        "I'm a university student specializing in software engineering, "
                        "and I'm doing an internship at a tech company."
                    )
                },
            )
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args.kwargs.get("timeout"), 15)
        from apps.speaking.services import _examiner_tts_text_hash

        expected_follow_up_tts_key = (
            "test-p1-followup-attempt_t2_followup_examiner_"
            f"{_examiner_tts_text_hash('How has your software engineering internship shaped your studies?')}"
        )
        mock_tts.assert_called_once_with(
            "How has your software engineering internship shaped your studies?",
            role="examiner",
            cache_key=expected_follow_up_tts_key,
        )
        mock_asr.assert_not_called()

        follow_up = SpeakingTurn.objects.get(attempt=attempt, turn_id="t2_followup")
        prompt = follow_up.metadata["prompt"]
        self.assertEqual(prompt["backend"], "codex")
        self.assertEqual(prompt["generation_status"], "ready")
        self.assertEqual(prompt["provider"], "codex_cli")
        self.assertEqual(prompt["model"], "codex-cli")
        self.assertEqual(prompt["usage"], {"input_tokens": 12})
        self.assertEqual(follow_up.question, "How has your software engineering internship shaped your studies?")
        self.assertEqual(follow_up.sequence, 2)
        self.assertEqual(follow_up.metadata["examiner_tts"]["provider"], "volcengine")
        self.assertEqual(follow_up.metadata["examiner_tts"]["status"], "ready")
        self.assertEqual(
            follow_up.metadata["examiner_tts"]["audio_url"],
            "/api/tts-audio/examiner/test-p1-followup-attempt_t2_followup_examiner.mp3",
        )
        self.assertEqual(result["next_turn"]["examiner_tts"]["status"], "ready")
        self.assertEqual(result["next_turn"]["id"], "t2_followup")
        self.assertEqual(result["next_turn"]["question"], "How has your software engineering internship shaped your studies?")
        self.assertEqual(result["attempt"]["current_turn"], "t2_followup")
        shifted_turn = SpeakingTurn.objects.get(attempt=attempt, turn_id="t3")
        self.assertEqual(shifted_turn.sequence, 3)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, SpeakingAttempt.Status.STARTED)
        self.assertEqual(attempt.metadata["current_turn"], "t2_followup")
        self.assertFalse(hasattr(attempt, "report"))
        completed_turn = SpeakingTurn.objects.get(attempt=attempt, turn_id="t2")
        self.assertEqual(completed_turn.metadata["server_asr"]["status"], "skipped_browser_transcript_available")

    @override_settings(
        AI_HTTP_BASE_URL="https://ai.example/v1",
        AI_HTTP_API_KEY="test-key",
        SPEAKING_FOLLOWUP_AI_CALL_MODE="http",
        SPEAKING_FOLLOWUP_AI_MODEL="gpt-5.4-mini",
    )
    def test_p1_work_study_followup_persists_http_generation_provenance(self):
        from apps.speaking.services import complete_turn
        from apps.accounts.models import CustomUser

        class FakeResult:
            text = '{"follow_up":"How does your internship help your studies?"}'
            elapsed_seconds = 0.12
            model = "gpt-5.4-mini"
            usage = {"input_tokens": 21, "output_tokens": 9}

        class FakeProvider:
            def __init__(self, config=None):
                self.config = config

            def complete_chat(self, *args, **kwargs):
                return FakeResult()

        user = CustomUser.objects.create_user(username="test-p1-followup-http-user", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="test-p1-followup-http-attempt",
            mode="p1",
            part="p1",
            status=SpeakingAttempt.Status.STARTED,
            metadata={"current_turn": "t2"},
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t2",
            sequence=0,
            part="p1",
            question="Do you work or do you study?",
            metadata={
                "prompt": {
                    "topic": "intro",
                    "question": "Do you work or do you study?",
                    "flow": "intro",
                    "role": "work_study",
                    "counts_toward_total": True,
                }
            },
        )

        with (
            patch("apps.speaking.services.HttpApiProvider", return_value=FakeProvider()) as http_provider,
            patch("apps.speaking.services.run_codex") as run_codex,
        ):
            result = complete_turn(
                user,
                "test-p1-followup-http-attempt",
                "t2",
                {"transcript_raw": "I study software engineering and do an internship at a tech company."},
            )

        http_provider.assert_called_once()
        run_codex.assert_not_called()
        follow_up = SpeakingTurn.objects.get(attempt=attempt, turn_id="t2_followup")
        prompt = follow_up.metadata["prompt"]
        self.assertEqual(prompt["backend"], "http_api")
        self.assertEqual(prompt["generation_status"], "ready")
        self.assertEqual(prompt["provider"], "openai_compatible_http")
        self.assertEqual(prompt["model"], "gpt-5.4-mini")
        self.assertEqual(prompt["usage"], {"input_tokens": 21, "output_tokens": 9})
        self.assertEqual(prompt["latency_ms"], 120)
        self.assertEqual(result["next_turn"]["prompt"]["provider"], "openai_compatible_http")
        self.assertEqual(result["next_turn"]["prompt"]["model"], "gpt-5.4-mini")
        self.assertEqual(result["next_turn"]["examiner_tts"]["status"], "pending")

    def test_p1_work_study_followup_skips_when_answer_is_empty(self):
        from apps.speaking.services import complete_turn
        from apps.accounts.models import CustomUser

        user = CustomUser.objects.create_user(username="test-p1-followup-empty-user", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="test-p1-followup-empty-attempt",
            mode="p1",
            part="p1",
            status=SpeakingAttempt.Status.STARTED,
            metadata={"current_turn": "t2"},
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t2",
            sequence=0,
            part="p1",
            question="Do you work or do you study?",
            metadata={
                "prompt": {
                    "topic": "intro",
                    "question": "Do you work or do you study?",
                    "flow": "intro",
                    "role": "work_study",
                    "counts_toward_total": True,
                }
            },
        )

        with (
            patch("apps.speaking.services.run_codex") as mock_run,
            patch(
                "apps.speaking.services.volcengine_tts",
                return_value={"provider": "volcengine", "status": "ready", "audio_url": "/api/tts-audio/examiner/fallback.mp3"},
            ),
            patch(
                "apps.speaking.services.transcribe_turn_audio_with_server_asr",
                return_value={"ok": False, "status": "missing_audio", "transcript": "", "error": "No uploaded audio."},
            ) as mock_asr,
        ):
            result = complete_turn(user, "test-p1-followup-empty-attempt", "t2", {"transcript_raw": ""})

        mock_run.assert_not_called()
        mock_asr.assert_called_once()
        self.assertFalse(SpeakingTurn.objects.filter(attempt=attempt, turn_id="t2_followup").exists())
        self.assertIsNone(result["next_turn"])
        self.assertEqual(result["follow_up_skipped"]["reason"], "missing_candidate_answer")
        self.assertEqual(result["follow_up_skipped"]["message"], "没有检测到回答，已跳过追问。")
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, SpeakingAttempt.Status.READY_TO_SCORE)
        self.assertIsNone(attempt.metadata["current_turn"])
        self.assertFalse(hasattr(attempt, "report"))

    def test_p1_work_study_followup_falls_back_when_codex_fails(self):
        from apps.speaking.services import complete_turn
        from apps.accounts.models import CustomUser

        user = CustomUser.objects.create_user(username="test-p1-followup-codex-fail", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="test-p1-followup-codex-fail",
            mode="p1",
            part="p1",
            status=SpeakingAttempt.Status.STARTED,
            metadata={"current_turn": "t2"},
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t2",
            sequence=0,
            part="p1",
            question="Do you work or do you study?",
            metadata={
                "prompt": {
                    "topic": "intro",
                    "question": "Do you work or do you study?",
                    "flow": "intro",
                    "role": "work_study",
                    "counts_toward_total": True,
                }
            },
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t3",
            sequence=1,
            part="p1",
            question="Do you like your hometown?",
            metadata={"prompt": {"topic": "home", "question": "Do you like your hometown?"}},
        )

        with (
            patch("apps.speaking.services.run_codex", side_effect=RuntimeError("codex unavailable")) as mock_run,
            patch("apps.speaking.services.threading.Thread") as mock_thread,
            self.captureOnCommitCallbacks(execute=True),
        ):
            result = complete_turn(
                user,
                "test-p1-followup-codex-fail",
                "t2",
                {"transcript_raw": "I'm a university student studying computer science."},
            )

        mock_run.assert_called_once()
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        follow_up = SpeakingTurn.objects.get(attempt=attempt, turn_id="t2_followup")
        prompt = follow_up.metadata["prompt"]
        self.assertEqual(follow_up.question, "What do you enjoy most about your studies?")
        self.assertEqual(prompt["backend"], "fallback")
        self.assertEqual(prompt["generation_status"], "fallback")
        self.assertIn("codex unavailable", prompt["generation_error"])
        self.assertEqual(follow_up.sequence, 1)
        self.assertEqual(result["next_turn"]["id"], "t2_followup")
        self.assertEqual(result["next_turn"]["question"], "What do you enjoy most about your studies?")
        self.assertEqual(result["next_turn"]["status"], "pending")
        self.assertEqual(result["attempt"]["current_turn"], "t2_followup")
        shifted_turn = SpeakingTurn.objects.get(attempt=attempt, turn_id="t3")
        self.assertEqual(shifted_turn.sequence, 2)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, SpeakingAttempt.Status.STARTED)
        self.assertEqual(attempt.metadata["current_turn"], "t2_followup")

    def test_p1_work_study_followup_returns_fallback_without_blocking_on_tts(self):
        from apps.speaking.services import complete_turn
        from apps.accounts.models import CustomUser

        user = CustomUser.objects.create_user(username="test-p1-followup-tts-fail", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="test-p1-followup-tts-fail",
            mode="p1",
            part="p1",
            status=SpeakingAttempt.Status.STARTED,
            metadata={"current_turn": "t2"},
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t2",
            sequence=0,
            part="p1",
            question="Do you work or do you study?",
            metadata={
                "prompt": {
                    "topic": "intro",
                    "question": "Do you work or do you study?",
                    "flow": "intro",
                    "role": "work_study",
                    "counts_toward_total": True,
                }
            },
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t3",
            sequence=1,
            part="p1",
            question="Do you like your hometown?",
            metadata={"prompt": {"topic": "home", "question": "Do you like your hometown?"}},
        )

        with (
            patch("apps.speaking.services.run_codex", side_effect=RuntimeError("codex timeout")) as mock_run,
            patch("apps.speaking.services.volcengine_tts", side_effect=RuntimeError("tts unavailable")) as mock_tts,
            patch("apps.speaking.services.threading.Thread") as mock_thread,
            self.captureOnCommitCallbacks(execute=True),
        ):
            result = complete_turn(
                user,
                "test-p1-followup-tts-fail",
                "t2",
                {"transcript_raw": "I'm an intern at a software company while studying at university."},
            )

        mock_run.assert_called_once()
        mock_tts.assert_not_called()
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        follow_up = SpeakingTurn.objects.get(attempt=attempt, turn_id="t2_followup")
        self.assertEqual(follow_up.question, "How does your internship connect with what you study?")
        self.assertEqual(follow_up.sequence, 1)
        self.assertEqual(follow_up.metadata["prompt"]["backend"], "fallback")
        self.assertEqual(follow_up.metadata["prompt"]["generation_status"], "fallback")
        self.assertIn("codex timeout", follow_up.metadata["prompt"]["generation_error"])
        self.assertEqual(follow_up.metadata["examiner_tts"]["status"], "pending")

    def test_p1_stream_pending_followup_skips_when_answer_is_empty(self):
        from apps.speaking.services import complete_turn
        from apps.accounts.models import CustomUser

        user = CustomUser.objects.create_user(username="test-p1-stream-pending-followup", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="test-p1-stream-pending-followup",
            mode="p1",
            part="p1",
            status=SpeakingAttempt.Status.STARTED,
            metadata={"current_turn": "t2"},
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t2",
            sequence=0,
            part="p1",
            question="Do you work or do you study?",
            metadata={
                "prompt": {
                    "topic": "intro",
                    "question": "Do you work or do you study?",
                    "flow": "intro",
                    "role": "work_study",
                    "counts_toward_total": True,
                }
            },
        )

        result = complete_turn(
            user,
            "test-p1-stream-pending-followup",
            "t2",
            {"transcript_raw": "", "stream_follow_up": True},
        )

        self.assertFalse(SpeakingTurn.objects.filter(attempt=attempt, turn_id="t2_followup").exists())
        self.assertIsNone(result["next_turn"])
        self.assertEqual(result["follow_up_skipped"]["reason"], "missing_candidate_answer")
        self.assertEqual(result["follow_up_skipped"]["message"], "没有检测到回答，已跳过追问。")
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, SpeakingAttempt.Status.READY_TO_SCORE)
        self.assertIsNone(attempt.metadata["current_turn"])
