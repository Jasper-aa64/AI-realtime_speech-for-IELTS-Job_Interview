import json
import subprocess
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.conf import settings
from django.utils import timezone

from apps.speaking import corpus_services
from apps.speaking.models import (
    ExpressionReplacementEntry,
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

    def test_start_p1_high_counts_body_questions_and_followups_without_intro(self):
        from apps.speaking import services

        response = self.client.post(
            "/api/attempts/start",
            data={"mode": "p1", "p1_intensity": "high"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        turns = payload["turns"]
        body_questions = [
            turn
            for turn in turns
            if turn.get("prompt", {}).get("topic") != "intro"
            and turn.get("prompt", {}).get("role") != "follow_up"
        ]
        body_followups = [
            turn
            for turn in turns
            if turn.get("prompt", {}).get("topic") != "intro"
            and turn.get("prompt", {}).get("role") == "follow_up"
        ]
        intro_turns = [turn for turn in turns if turn.get("prompt", {}).get("topic") == "intro"]
        counted_turns = [turn for turn in turns if turn.get("counts_toward_total")]

        self.assertEqual(services.P1_HIGH_BODY_QUESTION_MIN, 5)
        self.assertEqual(services.P1_HIGH_BODY_QUESTION_MAX, 7)
        self.assertGreaterEqual(len(body_questions), 5)
        self.assertLessEqual(len(body_questions), 7)
        self.assertEqual(len(body_followups), len(body_questions))
        self.assertEqual(len(counted_turns), len(body_questions) + len(body_followups))
        self.assertTrue(all(not turn.get("counts_toward_total") for turn in intro_turns))
        self.assertTrue(all((turn.get("display_index") or 0) == 0 for turn in intro_turns))
        self.assertEqual([turn.get("display_index") for turn in counted_turns], list(range(1, len(counted_turns) + 1)))

        for body_turn in body_questions:
            body_index = turns.index(body_turn)
            self.assertLess(body_index + 1, len(turns))
            follow_up = turns[body_index + 1]
            self.assertEqual(follow_up.get("prompt", {}).get("role"), "follow_up")
            self.assertEqual(follow_up.get("prompt", {}).get("after_turn"), body_turn["id"])

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
        self.assertEqual(
            [item["type"] for item in payload["p3_plan"]["questions"]],
            ["change_trend", "comparison_concession", "problem_solution"],
        )

    def test_start_p3_draws_three_from_an_oversized_bank_card(self):
        """A card with more bank follow-ups drills one stable, identifiable round."""
        from apps.speaking import services as speaking_services

        followups = [
            "Why do people give gifts to others?",
            "Is it better to give practical gifts or surprising ones?",
            "Do people in your country spend too much on gifts?",
            "How has gift-giving changed compared with the past?",
            "Should children be taught to give gifts?",
            "Do men and women choose gifts differently?",
        ]
        cue = {
            "title": "Describe a time when someone gave you something you really wanted",
            "season": "2026-may-august",
            "p3_theme": "gifts_and_giving",
            "p3_follow_ups": followups,
        }
        bank = MagicMock()
        bank.p2 = [cue]
        bank.part2_for_scope.return_value = [cue]
        with patch.object(speaking_services, "get_question_bank", return_value=bank):
            response = self.client.post(
                "/api/attempts/start",
                data={"mode": "p3", "theme": "gifts_and_giving", "p3_intensity": "normal"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["p3_generation_backend"], "season_bank")
        plan_questions = [q["question"] for q in payload["p3_plan"]["questions"]]
        self.assertEqual(len(plan_questions), speaking_services.P3_MAIN_COUNT)
        self.assertTrue(set(plan_questions).issubset(set(followups)))
        expected_cue_id = speaking_services.p2_cue_id(cue)
        self.assertEqual(payload["p3_bank_cue_id"], expected_cue_id)
        self.assertEqual(payload["p3_bank_round_index"], 0)
        self.assertEqual(payload["p3_bank_round_count"], 2)
        attempt = SpeakingAttempt.objects.get(attempt_id=payload["id"])
        self.assertEqual(attempt.metadata["p3_bank_cue_id"], expected_cue_id)

    def test_p3_bank_rounds_cap_at_three_except_exactly_four(self):
        self.assertEqual(corpus_services.p3_bank_practice_rounds([1, 2, 3, 4]), [[1, 2, 3, 4]])
        self.assertEqual(corpus_services.p3_bank_practice_rounds([1, 2, 3, 4, 5]), [[1, 2, 3], [4, 5]])
        self.assertEqual(corpus_services.p3_bank_practice_rounds([1, 2, 3, 4, 5, 6, 7]), [[1, 2, 3], [4, 5, 6], [7]])

    def test_start_p3_selects_least_practised_bank_round_and_persists_identity(self):
        from apps.speaking import services as speaking_services

        cue_id = "p2cue:five-question-rounds"
        followups = [f"Fixed follow-up {index}?" for index in range(1, 6)]
        cue = {
            "cue_id": cue_id,
            "title": "Describe a useful gift",
            "season": "2026-may-august",
            "p3_theme": "gifts_and_giving",
            "p3_follow_ups": followups,
        }
        now = timezone.now()
        for index in range(3):
            SpeakingTrainingObservation.objects.create(
                observation_id=f"completed-first-bank-round-turn-{index}",
                user=self.user,
                legacy_attempt_id="completed-first-bank-round",
                legacy_turn_id=f"completed-first-bank-round-turn-{index}",
                question_id=corpus_services.p3_bank_followup_id(cue_id, followups[index], index),
                part="p3",
                question=followups[index],
                transcript="This is a completed answer.",
                relevance=Decimal("1.000"),
                observed_at=now + timedelta(seconds=index),
                next_due=now,
            )
        bank = MagicMock()
        bank.p2 = [cue]
        bank.part2_for_scope.return_value = [cue]

        with (
            patch.object(speaking_services, "get_question_bank", return_value=bank),
            patch.object(speaking_services, "_select_p3_followups", return_value=followups[:3]),
        ):
            response = self.client.post(
                "/api/attempts/start",
                data={
                    "mode": "p3",
                    "theme": cue["p3_theme"],
                    "p2_question_id": cue_id,
                    "p3_intensity": "normal",
                },
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["p3_plan"]["question_texts"], [followups[3], followups[4]])
        self.assertEqual(payload["p3_bank_cue_id"], cue_id)
        self.assertEqual(payload["p3_bank_round_index"], 1)
        self.assertEqual(payload["p3_bank_round_count"], 2)
        expected_ids = [
            corpus_services.p3_bank_followup_id(cue_id, followups[index], index)
            for index in (3, 4)
        ]
        self.assertEqual(payload["p3_bank_followup_ids"], expected_ids)
        attempt = SpeakingAttempt.objects.get(attempt_id=payload["id"])
        self.assertEqual(attempt.metadata["p3_bank_followup_ids"], expected_ids)

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
        from collections import Counter
        from apps.speaking import services
        # P1 body = 9-12 real topic questions, assembled from 2-3 topics (more topics
        # only when needed to reach the count or to split a big topic). Each selected
        # topic keeps its opener and its questions arrive in one contiguous run.
        body_topics = [
            t.get("prompt", {}).get("topic")
            for t in p1_turns
            if t.get("counts_toward_total", True) and t.get("prompt", {}).get("topic") != "intro"
        ]
        topic_counts = Counter(body_topics)
        # Body length stays in the configured window.
        self.assertGreaterEqual(len(body_topics), services.P1_BODY_QUESTION_MIN)
        self.assertLessEqual(len(body_topics), services.P1_BODY_QUESTION_MAX)
        # Two or three distinct topics — never one giant topic, never a fixed count.
        self.assertIn(len(topic_counts), (2, 3))
        # A big topic is split (<= P1_SPLIT_MAX); a whole small topic can contribute
        # all of its (sub-threshold) questions, so the ceiling is split_threshold - 1.
        self.assertLessEqual(max(topic_counts.values()), services.P1_SPLIT_THRESHOLD - 1)
        # Contiguous runs by topic: one switch per topic boundary.
        switches = sum(1 for a, b in zip(body_topics, body_topics[1:]) if a != b)
        self.assertEqual(switches, len(topic_counts) - 1)
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


class P3BankPracticeRoundTests(TestCase):
    def test_three_and_four_questions_stay_in_one_round(self):
        from apps.speaking import corpus_services

        build_rounds = getattr(corpus_services, "p3_bank_practice_rounds", None)
        self.assertIsNotNone(build_rounds)
        self.assertEqual(build_rounds(list(range(3))), [[0, 1, 2]])
        self.assertEqual(build_rounds(list(range(4))), [[0, 1, 2, 3]])

    def test_five_questions_split_without_repeating_bridge_question(self):
        from apps.speaking import corpus_services

        build_rounds = getattr(corpus_services, "p3_bank_practice_rounds", None)
        self.assertIsNotNone(build_rounds)
        self.assertEqual(build_rounds(list(range(5))), [[0, 1, 2], [3, 4]])

    def test_six_questions_split_into_two_stable_rounds(self):
        from apps.speaking import corpus_services

        build_rounds = getattr(corpus_services, "p3_bank_practice_rounds", None)
        self.assertIsNotNone(build_rounds)
        self.assertEqual(build_rounds(list(range(6))), [[0, 1, 2], [3, 4, 5]])

    def test_larger_banks_are_capped_at_three_question_rounds(self):
        from apps.speaking import corpus_services

        build_rounds = getattr(corpus_services, "p3_bank_practice_rounds", None)
        self.assertIsNotNone(build_rounds)
        self.assertEqual([len(items) for items in build_rounds(list(range(7)))], [3, 3, 1])
        self.assertEqual([len(items) for items in build_rounds(list(range(10)))], [3, 3, 3, 1])

    def test_replayed_p3_bank_observation_does_not_advance_coverage_count(self):
        from apps.speaking import corpus_services

        user = get_user_model().objects.create_user(username="p3-bank-replay-count", password="test-pass")
        cue_id = "p2cue:replay-count"
        question = "Why do cities need public parks?"
        followup_id = corpus_services.p3_bank_followup_id(cue_id, question, 0)
        replay_attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="p3-bank-replay-count",
            mode=SpeakingAttempt.Mode.P3,
            part="p3",
            status=SpeakingAttempt.Status.SCORED,
            metadata={"p3_bank_cue_id": cue_id, "p3_bank_replay": True},
        )
        SpeakingTrainingObservation.objects.create(
            observation_id="p3-bank-replay-count-q1",
            user=user,
            attempt=replay_attempt,
            legacy_attempt_id=replay_attempt.attempt_id,
            legacy_turn_id="t1",
            question_id=followup_id,
            part="p3",
            question=question,
            transcript="Parks give people a quiet place to exercise and relax.",
            relevance=Decimal("1.000"),
            observed_at=timezone.now(),
            next_due=timezone.now(),
        )

        self.assertEqual(
            corpus_services.p3_bank_practice_question_counts(user, cue_id, [question]),
            {followup_id: 0},
        )


class P1PracticeCountTests(TestCase):
    def test_ai_training_observation_keeps_count_after_report_is_deleted(self):
        from apps.speaking.turn_building_services import _question_practice_counts

        user = get_user_model().objects.create_user(username="p1-deleted-report-count", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="p1-deleted-report-count",
            mode=SpeakingAttempt.Mode.P1,
            part="p1",
            status=SpeakingAttempt.Status.SCORED,
        )
        turn = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="park-q1",
            sequence=1,
            part="p1",
            question="Did you like going to parks as a child?",
            transcript_cleaned="Yes, I often went there with my family.",
        )
        SpeakingReport.objects.create(user=user, attempt=attempt, report_payload={"status": "scored"})
        now = timezone.now()
        SpeakingTrainingObservation.objects.create(
            observation_id="p1-deleted-report-count-park-q1",
            user=user,
            attempt=attempt,
            turn=turn,
            legacy_attempt_id=attempt.attempt_id,
            legacy_turn_id=turn.turn_id,
            question_id="p1q:park-q1",
            part="p1",
            question=turn.question,
            transcript=turn.transcript_cleaned,
            relevance=Decimal("1.000"),
            observed_at=now,
            next_due=now,
        )

        attempt.delete()

        self.assertEqual(
            _question_practice_counts(user, "p1"),
            {"did you like going to parks as a child?": 1},
        )

    def test_split_topic_repeated_opener_advances_only_once_per_coverage_round(self):
        from apps.speaking.turn_building_services import (
            _p1_balanced_practice_counts,
            _p1_topic_practice_debt,
        )

        user = get_user_model().objects.create_user(username="p1-split-waterline", password="test-pass")
        questions = ["Topic opener"] + [f"Topic question {index}" for index in range(2, 9)]
        topics = {"large-topic": [{"topic": "large-topic", "question": question} for question in questions]}
        now = timezone.now()

        def observe(question, attempt_suffix, turn_suffix, offset):
            SpeakingTrainingObservation.objects.create(
                observation_id=f"p1-waterline-{attempt_suffix}-{turn_suffix}",
                user=user,
                legacy_attempt_id=f"attempt-{attempt_suffix}",
                legacy_turn_id=f"turn-{turn_suffix}",
                question_id=f"p1q:{turn_suffix}",
                part="p1",
                question=question,
                transcript="A completed answer.",
                relevance=Decimal("1.000"),
                observed_at=now + timedelta(seconds=offset),
                next_due=now,
            )

        observe(questions[0], "one", "opener-one", 1)
        observe(questions[1], "one", "q2", 2)
        observe(questions[2], "one", "q3", 3)
        observe(questions[0], "two", "opener-two", 4)
        observe(questions[1], "two", "q2-repeat", 5)
        observe(questions[3], "two", "q4", 6)
        observe(questions[4], "two", "q5", 7)

        counts = _p1_balanced_practice_counts(user, topics)

        self.assertEqual(counts["topic opener"], 1)
        self.assertEqual({counts[question.lower()] for question in questions[1:5]}, {1})
        self.assertNotIn(questions[5].lower(), counts)
        self.assertEqual(
            _p1_topic_practice_debt(user, topics)["large-topic"]["total_practice"],
            5,
        )

    def test_topic_combination_scores_questions_that_will_actually_be_selected(self):
        from apps.speaking.turn_building_services import select_p1_body_questions

        class FixedRng:
            def randint(self, _low, _high):
                return 9

            def random(self):
                return 0.5

        topics = {
            "overstated": [
                {"topic": "overstated", "question": f"Overstated {index}"}
                for index in range(8)
            ],
            "better": [
                {"topic": "better", "question": f"Better {index}"}
                for index in range(8)
            ],
            "common": [
                {"topic": "common", "question": f"Common {index}"}
                for index in range(6)
            ],
        }
        topic_debt = {
            "overstated": {"unpracticed": 7, "total_practice": 1, "last_ts": 1},
            "better": {"unpracticed": 6, "total_practice": 1, "last_ts": 1},
            "common": {"unpracticed": 6, "total_practice": 0, "last_ts": None},
        }
        counts = {
            "overstated 0": 1,
            "better 7": 1,
        }

        selected = select_p1_body_questions(
            topics,
            topic_debt,
            counts,
            body_min=9,
            body_max=9,
            rng=FixedRng(),
        )

        self.assertEqual({item["topic"] for item in selected}, {"better", "common"})

    def test_counts_only_answered_turns_with_completed_reports(self):
        from apps.speaking.turn_building_services import (
            _p1_topic_practice_counts,
            _p1_topic_practice_debt,
            _question_practice_counts,
        )

        user = get_user_model().objects.create_user(username="p1-practice-count-user", password="test-pass")
        question = "Do you often use public transport?"

        def add_attempt(status, transcript, *, with_report=False, suffix=""):
            attempt = SpeakingAttempt.objects.create(
                user=user,
                attempt_id=f"p1-count-{suffix}",
                mode=SpeakingAttempt.Mode.P1,
                part="p1",
                status=status,
            )
            SpeakingTurn.objects.create(
                user=user,
                attempt=attempt,
                turn_id=f"turn-{suffix}",
                sequence=1,
                part="p1",
                question=question,
                transcript_raw=transcript,
                transcript_cleaned=transcript,
            )
            if with_report:
                SpeakingReport.objects.create(user=user, attempt=attempt, report_payload={"status": "scored"})

        add_attempt(SpeakingAttempt.Status.STARTED, "I take the metro every day.", suffix="started")
        add_attempt(SpeakingAttempt.Status.ABORTED, "I usually take the bus.", suffix="aborted")
        add_attempt(SpeakingAttempt.Status.SCORED, "", with_report=True, suffix="empty")
        add_attempt(
            SpeakingAttempt.Status.SCORED,
            "Yes, I normally commute by metro.",
            with_report=True,
            suffix="completed",
        )

        topics = {
            "transport": [
                {"question": question},
                {"question": "Would you like to use public transport more often?"},
            ]
        }
        normalized = "do you often use public transport?"

        self.assertEqual(_question_practice_counts(user, "p1"), {normalized: 1})
        self.assertEqual(_p1_topic_practice_counts(user, topics), {"transport": 1})
        self.assertEqual(
            _p1_topic_practice_debt(user, topics)["transport"],
            {
                "unpracticed": 1,
                "total_practice": 1,
                "last_ts": SpeakingTurn.objects.get(turn_id="turn-completed").created_at.timestamp(),
            },
        )

    def test_per_topic_selection_exhausts_lower_counts_before_repeats(self):
        from apps.speaking.turn_building_services import _select_least_practiced_items

        items = [
            {"question": "Opener"},
            {"question": "Practised three times"},
            {"question": "Never practised"},
            {"question": "Practised once"},
        ]
        counts = {
            "opener": 20,
            "practised three times": 3,
            "never practised": 0,
            "practised once": 1,
        }
        with (
            patch("apps.speaking.turn_building_services.random.shuffle"),
            patch("apps.speaking.turn_building_services.random.choices", return_value=[0]),
        ):
            selected = _select_least_practiced_items(items, 3, counts, pin_first=True)

        self.assertEqual(
            [item["question"] for item in selected],
            ["Opener", "Never practised", "Practised once"],
        )

    def test_practice_debt_beats_random_target_length(self):
        from apps.speaking.turn_building_services import select_p1_body_questions

        class FixedRng:
            def randint(self, _low, _high):
                return 12

            def random(self):
                return 0.5

        topics = {
            "unseen-a": [{"topic": "unseen-a", "question": f"A{i}"} for i in range(5)],
            "unseen-b": [{"topic": "unseen-b", "question": f"B{i}"} for i in range(4)],
            "repeated-c": [{"topic": "repeated-c", "question": f"C{i}"} for i in range(6)],
            "repeated-d": [{"topic": "repeated-d", "question": f"D{i}"} for i in range(6)],
        }
        topic_debt = {
            "unseen-a": {"unpracticed": 5, "total_practice": 0, "last_ts": None},
            "unseen-b": {"unpracticed": 4, "total_practice": 0, "last_ts": None},
            "repeated-c": {"unpracticed": 0, "total_practice": 60, "last_ts": 100},
            "repeated-d": {"unpracticed": 0, "total_practice": 60, "last_ts": 100},
        }
        counts = {f"c{i}": 10 for i in range(6)} | {f"d{i}": 10 for i in range(6)}

        selected = select_p1_body_questions(topics, topic_debt, counts, rng=FixedRng())

        self.assertEqual({item["topic"] for item in selected}, {"unseen-a", "unseen-b"})


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
                "turns": [{"id": "t1", "status": turn_status, "question": "What is your full name?", "transcript_cleaned": "My full name is Jasper.", "band7_version": "My full name is Jasper Chen."}],
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
        items = {item["id"]: item for item in history.json()["items"]}
        self.assertEqual(items[valid.attempt_id]["report_status"], "ready")
        self.assertEqual(items["attempt-incomplete"]["report_status"], "unscored")
        self.assertNotIn("attempt-started", items)

        detail = self.client.get(f"/api/history/{valid.attempt_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["ielts_score"]["overall_band"], 5.5)
        self.assertEqual(detail.json()["turns"][0]["question"], "What is your full name?")

        invalid_detail = self.client.get("/api/history/attempt-incomplete")
        self.assertEqual(invalid_detail.status_code, 200)
        self.assertEqual(invalid_detail.json()["report_status"], "unscored")

    def create_failed_attempt(self, attempt_id="attempt-failed-1"):
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id=attempt_id,
            legacy_attempt_id=attempt_id,
            mode=SpeakingAttempt.Mode.P1,
            part="p1",
            title="Part 1 practice",
            status=SpeakingAttempt.Status.READY_TO_SCORE,
            english_name="Jasper",
            metadata={
                "report_generation_status": "failed",
                "analysis_status": "failed",
                "analysis_error": "AI analysis failed: exit status 1",
            },
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
            metadata={"transcript_status": "captured"},
        )
        return attempt

    def create_empty_failed_attempt(self, attempt_id="attempt-empty-failed"):
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id=attempt_id,
            legacy_attempt_id=attempt_id,
            mode=SpeakingAttempt.Mode.P2,
            part="p2",
            title="Part 2 practice",
            status=SpeakingAttempt.Status.READY_TO_SCORE,
            metadata={
                "report_generation_status": "failed",
                "analysis_status": "failed",
                "analysis_error": "Recording was not saved and no scoreable transcript was captured.",
            },
        )
        SpeakingTurn.objects.create(
            user=self.user,
            attempt=attempt,
            turn_id="t1",
            sequence=1,
            part="p2",
            question="Describe a city you visited.",
            metadata={"status": "completed", "transcript_status": "missing"},
        )
        return attempt

    def test_failed_analysis_surfaces_as_unscored_report(self):
        valid = self.create_scored_attempt()
        failed = self.create_failed_attempt()

        history = self.client.get("/api/history")
        self.assertEqual(history.status_code, 200)
        items = {item["id"]: item for item in history.json()["items"]}
        # The failed attempt must no longer vanish from history.
        self.assertIn(failed.attempt_id, items)
        self.assertEqual(items[failed.attempt_id]["report_status"], "failed")
        self.assertIsNone(items[failed.attempt_id]["overall_band"])
        self.assertEqual(items[valid.attempt_id]["report_status"], "ready")

        detail = self.client.get(f"/api/history/{failed.attempt_id}")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["report_status"], "failed")
        self.assertEqual(body["ielts_score"], {})
        self.assertTrue(body["report_error"])
        self.assertEqual(body["turns"][0]["question"], "What is your full name?")
        self.assertEqual(body["turns"][0]["transcript_cleaned"], "My full name is Jasper.")
        self.assertTrue(body["can_regenerate_report"])
        self.assertFalse(body["can_regenerate_transcript"])

    def test_failed_analysis_with_audio_exposes_transcription_recovery_only(self):
        failed = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id="attempt-failed-audio-only",
            legacy_attempt_id="attempt-failed-audio-only",
            mode=SpeakingAttempt.Mode.P2,
            part="p2",
            title="Part 2 practice",
            status=SpeakingAttempt.Status.READY_TO_SCORE,
            metadata={
                "report_generation_status": "failed",
                "analysis_status": "failed",
                "analysis_error": "Recording saved, but no scoreable transcript was captured.",
            },
        )
        SpeakingTurn.objects.create(
            user=self.user,
            attempt=failed,
            turn_id="t1",
            sequence=1,
            part="p2",
            question="Describe a city you visited.",
            audio_path="audio/attempt-failed-audio-only/t1.webm",
            metadata={"status": "completed", "transcript_status": "missing"},
        )

        history = self.client.get("/api/history")
        items = {item["id"]: item for item in history.json()["items"]}
        self.assertIn(failed.attempt_id, items)

        detail = self.client.get(f"/api/history/{failed.attempt_id}")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertFalse(body["can_regenerate_report"])
        self.assertTrue(body["can_regenerate_transcript"])
        self.assertEqual(body["turns"][0]["audio"]["url"], f"/api/audio/{failed.attempt_id}/t1/candidate")
        self.assertEqual(body["turns"][0]["transcript_status"], "missing")

    def test_failed_analysis_without_saved_audio_or_text_stays_out_of_history(self):
        empty = self.create_empty_failed_attempt()

        history = self.client.get("/api/history")
        items = {item["id"]: item for item in history.json()["items"]}
        self.assertIn(empty.attempt_id, items)
        self.assertEqual(items[empty.attempt_id]["report_status"], "failed")

        detail = self.client.get(f"/api/history/{empty.attempt_id}")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["report_status"], "failed")
        self.assertFalse(body["can_regenerate_report"])

    def test_completed_attempt_without_report_or_ai_task_is_visible_as_unscored(self):
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id="b34cd8f984354f288d47ddf82d0a48bd",
            legacy_attempt_id="b34cd8f984354f288d47ddf82d0a48bd",
            mode=SpeakingAttempt.Mode.P1,
            part="p1",
            title="Part 1 practice",
            status=SpeakingAttempt.Status.READY_TO_SCORE,
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
            audio_path="audio/b34cd8f984354f288d47ddf82d0a48bd/t1.webm",
            metadata={"status": "completed", "transcript_status": "captured"},
        )

        history = self.client.get("/api/history")
        self.assertEqual(history.status_code, 200)
        items = {item["id"]: item for item in history.json()["items"]}
        self.assertEqual(len([item for item in history.json()["items"] if item["id"] == attempt.attempt_id]), 1)
        self.assertEqual(items[attempt.attempt_id]["report_status"], "unscored")
        self.assertIsNone(items[attempt.attempt_id]["overall_band"])

        detail = self.client.get(f"/api/history/{attempt.attempt_id}")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["report_status"], "unscored")
        self.assertEqual(body["report_status"], items[attempt.attempt_id]["report_status"])
        self.assertTrue(body["can_regenerate_report"])
        self.assertEqual(body["turns"][0]["transcript_cleaned"], "My full name is Jasper.")
        self.assertEqual(body["turns"][0]["audio"]["url"], f"/api/audio/{attempt.attempt_id}/t1/candidate")

        # A second request is the refresh/re-login equivalent: no frontend cache
        # or task creation is needed to recover the same persisted state.
        refreshed = self.client.get(f"/api/history/{attempt.attempt_id}")
        self.assertEqual(refreshed.json()["report_status"], "unscored")
        self.assertEqual(SpeakingAttempt.objects.filter(attempt_id=attempt.attempt_id).count(), 1)

    def test_running_report_task_is_scoring_in_history_and_detail(self):
        attempt = self.create_stalled_attempt("attempt-running-report", task_status="running", age_seconds=5)

        history = self.client.get("/api/history")
        item = next(item for item in history.json()["items"] if item["id"] == attempt.attempt_id)
        self.assertEqual(item["report_status"], "scoring")
        self.assertEqual(item["ai_task"]["status"], "running")

        detail = self.client.get(f"/api/history/{attempt.attempt_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["report_status"], "scoring")
        self.assertEqual(detail.json()["ai_task"]["status"], "running")
        self.assertFalse(detail.json()["can_regenerate_report"])

    def test_insufficient_account_balance_is_failed_without_losing_source_data(self):
        from apps.ai.models import AITask

        attempt = self.create_stalled_attempt("attempt-balance-failure", task_status=AITask.Status.FAILED, age_seconds=5)
        task = AITask.objects.get(related_id=attempt.attempt_id)
        task.error_code = "speaking_report_failed"
        task.error_message = (
            'AI analysis failed: HTTP AI provider returned 403: '
            '{"error":{"message":"Insufficient account balance"}}'
        )
        task.save(update_fields=["error_code", "error_message", "updated_at"])

        history = self.client.get("/api/history")
        item = next(item for item in history.json()["items"] if item["id"] == attempt.attempt_id)
        self.assertEqual(item["report_status"], "failed")

        detail = self.client.get(f"/api/history/{attempt.attempt_id}")
        body = detail.json()
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(body["report_status"], "failed")
        self.assertIn("余额不足", body["report_error"])
        self.assertIn("重新生成", body["report_error"])
        self.assertTrue(body["can_regenerate_report"])
        self.assertEqual(body["turns"][0]["transcript_cleaned"], "My full name is Jasper.")
        self.assertTrue(SpeakingAttempt.objects.filter(pk=attempt.pk).exists())
        self.assertEqual(attempt.turns.count(), 1)

    def test_deleting_another_report_does_not_hide_unscored_attempt(self):
        from apps.ai.models import AITask

        kept = self.create_stalled_attempt("attempt-kept-unscored", task_status=None, age_seconds=5)
        task = AITask.objects.filter(related_id=kept.attempt_id, task_type="speaking_report").first()
        task.delete()
        removed = self.create_scored_attempt("attempt-removed-report")

        self.assertEqual(self.client.delete(f"/api/history/{removed.attempt_id}").status_code, 200)
        items = {item["id"]: item for item in self.client.get("/api/history").json()["items"]}
        self.assertIn(kept.attempt_id, items)
        self.assertNotIn(removed.attempt_id, items)

    def test_failed_history_detail_is_owner_scoped(self):
        failed = self.create_failed_attempt("attempt-owner-failed")
        other_user = get_user_model().objects.create_user(username="other-failed-reader", password="test-pass")
        self.client.logout()
        self.client.force_login(other_user)

        history = self.client.get("/api/history")
        self.assertNotIn(failed.attempt_id, [item["id"] for item in history.json()["items"]])

        detail = self.client.get(f"/api/history/{failed.attempt_id}")
        self.assertEqual(detail.status_code, 404)

    def test_scored_report_payload_backfills_audio_from_turn_when_payload_lacks_it(self):
        attempt = self.create_scored_attempt("attempt-audio-backfill")
        turn = attempt.turns.get(turn_id="t1")
        turn.audio_path = "audio/attempt-audio-backfill/t1.webm"
        turn.save(update_fields=["audio_path", "updated_at"])

        detail = self.client.get(f"/api/history/{attempt.attempt_id}")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["report_status"], "ready")
        self.assertEqual(body["turns"][0]["audio"]["url"], f"/api/audio/{attempt.attempt_id}/t1/candidate")

    def create_stalled_attempt(self, attempt_id="attempt-stalled-1", *, task_status=None, age_seconds=600):
        from apps.ai.models import AITask
        from apps.ai.services import create_ai_task

        if task_status is None:
            task_status = AITask.Status.PENDING
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id=attempt_id,
            legacy_attempt_id=attempt_id,
            mode=SpeakingAttempt.Mode.P1,
            part="p1",
            title="Part 1 practice",
            status=SpeakingAttempt.Status.READY_TO_SCORE,
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
            metadata={"transcript_status": "captured"},
        )
        task, _ = create_ai_task(
            user=self.user,
            task_type="speaking_report",
            idempotency_key=f"speaking_report:{attempt_id}",
            provider="codex",
            model="",
            related_type="speaking_attempt",
            related_id=attempt_id,
            call_id=f"speaking_report_{attempt_id}",
            prompt_version="speaking_report_v1",
            request_payload={},
            metadata={},
        )
        old = timezone.now() - timedelta(seconds=age_seconds)
        AITask.objects.filter(pk=task.pk).update(
            status=task_status, available_at=old, started_at=old, created_at=old
        )
        return attempt

    def test_stalled_pending_report_surfaces_as_unscored_when_worker_offline(self):
        # A report task stuck pending past the claim window (worker offline) must
        # not vanish or spin forever — it surfaces as a 未评分 card so the user can
        # re-generate, exactly like a terminally failed analysis.
        stalled = self.create_stalled_attempt()

        history = self.client.get("/api/history")
        self.assertEqual(history.status_code, 200)
        items = {item["id"]: item for item in history.json()["items"]}
        self.assertIn(stalled.attempt_id, items)
        self.assertEqual(items[stalled.attempt_id]["report_status"], "failed")
        self.assertIsNone(items[stalled.attempt_id]["overall_band"])

        detail = self.client.get(f"/api/history/{stalled.attempt_id}")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["report_status"], "failed")
        self.assertTrue(body["report_error"])
        self.assertEqual(body["turns"][0]["transcript_cleaned"], "My full name is Jasper.")

    def test_fresh_pending_report_surfaces_as_scoring_not_unscored(self):
        # A report queued seconds ago (worker about to claim it) must appear in
        # reports immediately as scoring, not vanish until it fails and not show
        # a premature regenerate button.
        fresh = self.create_stalled_attempt("attempt-fresh-pending", age_seconds=5)

        history = self.client.get("/api/history")
        items = {item["id"]: item for item in history.json()["items"]}
        self.assertIn(fresh.attempt_id, items)
        self.assertEqual(items[fresh.attempt_id]["report_status"], "scoring")
        self.assertIsNone(items[fresh.attempt_id]["overall_band"])
        self.assertEqual(items[fresh.attempt_id]["ai_task"]["status"], "pending")

        detail = self.client.get(f"/api/history/{fresh.attempt_id}")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["report_status"], "scoring")
        self.assertEqual(body["ielts_score"], {})
        self.assertFalse(body["can_regenerate_report"])
        self.assertEqual(body["ai_task"]["status"], "pending")
        self.assertEqual(body["turns"][0]["transcript_cleaned"], "My full name is Jasper.")

    def test_friendly_report_error_maps_no_available_accounts_to_quota(self):
        from apps.speaking.report_services import friendly_report_error

        raw = 'AI analysis failed: HTTP AI provider returned 503: {"error":{"message":"No available accounts: no available accounts"}}'
        self.assertEqual(
            friendly_report_error(raw),
            "AI 评分服务的额度已用尽，稍后额度恢复后点「重新生成报告」即可。",
        )

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
        for theme in ("career_choices_and_job_values", "movies_and_cinema_culture", "technology_and_communication"):
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

    def test_p1_corpus_save_allows_clearing_prepared_answer(self):
        library = self.client.get("/api/p1-corpus").json()
        first_question = library["topics"][0]["questions"][0]
        P1CorpusEntry.objects.create(
            user=self.user,
            question_id=first_question["question_id"],
            topic=first_question["topic"],
            question=first_question["question"],
            corpus_text="Old prepared answer.",
            last_ai_answer="Report-only reference.",
        )

        response = self.client.post(
            "/api/p1-corpus",
            data={
                "question_id": first_question["question_id"],
                "topic": first_question["topic"],
                "question": first_question["question"],
                "corpus_text": "",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["corpus_text"], "")
        entry = P1CorpusEntry.objects.get(user=self.user, question_id=first_question["question_id"])
        self.assertEqual(entry.corpus_text, "")
        self.assertEqual(entry.last_ai_answer, "")
        refreshed = self.client.get("/api/p1-corpus").json()
        refreshed_question = next(
            item
            for topic in refreshed["topics"]
            for item in topic["questions"]
            if item["question_id"] == first_question["question_id"]
        )
        self.assertEqual(refreshed_question["corpus_text"], "")

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

    def test_p2_corpus_progress_counts_only_completed_feedback_observations(self):
        cards = self.client.get("/api/p2-corpus").json()["current_part2_cards"]
        card = next(item for item in cards if len(item["p3_follow_ups"]) > 4)
        cue_id = card["cue_id"]
        round_count = card["practice_round_count"]
        followup_ids = [
            corpus_services.p3_bank_followup_id(cue_id, question, index)
            for index, question in enumerate(card["p3_follow_ups"])
        ]
        rounds = corpus_services.p3_bank_practice_rounds(list(range(len(followup_ids))))

        def add_attempt(status, round_index, suffix, *, with_report=False):
            attempt = SpeakingAttempt.objects.create(
                user=self.user,
                attempt_id=f"bank-progress-{suffix}",
                mode=SpeakingAttempt.Mode.P3,
                part="p3",
                status=status,
                metadata={
                    "p3_bank_cue_id": cue_id,
                    "p3_bank_round_index": round_index,
                    "p3_bank_round_count": round_count,
                },
            )
            if with_report:
                SpeakingReport.objects.create(user=self.user, attempt=attempt, report_payload={"status": "scored"})

        def add_observed_round(round_index, suffix):
            now = timezone.now()
            for offset, question_index in enumerate(rounds[round_index], start=1):
                SpeakingTrainingObservation.objects.create(
                    observation_id=f"bank-progress-observed-{suffix}-{offset}",
                    user=self.user,
                    legacy_attempt_id=f"bank-progress-observed-{suffix}",
                    legacy_turn_id=f"bank-progress-observed-turn-{suffix}-{offset}",
                    question_id=followup_ids[question_index],
                    part="p3",
                    question=card["p3_follow_ups"][question_index],
                    transcript="This is a completed answer.",
                    relevance=Decimal("1.000"),
                    observed_at=now + timedelta(seconds=offset),
                    next_due=now,
                )

        add_attempt(SpeakingAttempt.Status.STARTED, 0, "started")
        add_attempt(SpeakingAttempt.Status.ABORTED, 0, "aborted")
        add_attempt(SpeakingAttempt.Status.READY_TO_SCORE, 0, "ready")
        add_attempt(SpeakingAttempt.Status.SCORED, 0, "reportless")
        add_attempt(SpeakingAttempt.Status.SCORED, 1, "reported", with_report=True)

        updated = self.client.get("/api/p2-corpus").json()
        progress = next(item for item in updated["current_part2_cards"] if item["cue_id"] == cue_id)
        self.assertEqual(progress["practice_round_count"], round_count)
        self.assertEqual(progress["practice_completed_round_indexes"], [])
        self.assertEqual(progress["practice_completed_round_count"], 0)
        self.assertFalse(progress["practice_is_complete"])
        self.assertEqual(progress["practice_next_round_index"], 0)

        add_observed_round(1, "round-1")
        partly_done = self.client.get("/api/p2-corpus").json()
        progress = next(item for item in partly_done["current_part2_cards"] if item["cue_id"] == cue_id)
        self.assertEqual(progress["practice_completed_round_indexes"], [1])
        self.assertEqual(progress["practice_completed_round_count"], 1)
        self.assertEqual(progress["practice_next_round_index"], 0)

        add_observed_round(0, "round-0")
        completed = self.client.get("/api/p2-corpus").json()
        progress = next(item for item in completed["current_part2_cards"] if item["cue_id"] == cue_id)
        self.assertEqual(progress["practice_completed_round_indexes"], [0, 1])
        self.assertTrue(progress["practice_is_complete"])
        self.assertEqual(progress["practice_progress_state"], "complete")
        self.assertEqual(progress["practice_cycle"], 1)
        self.assertEqual(progress["practice_next_round_index"], 0)
        self.assertEqual(progress["practice_next_question_indexes"], [])

        add_observed_round(0, "round-0-cycle-2")
        repeated = self.client.get("/api/p2-corpus").json()
        progress = next(item for item in repeated["current_part2_cards"] if item["cue_id"] == cue_id)
        self.assertEqual(progress["practice_cycle"], 1)
        self.assertEqual(progress["practice_progress_state"], "complete")
        self.assertTrue(all(count == 1 for count in progress["practice_question_counts"].values()))

    def test_p2_corpus_p3_progress_uses_observations_after_report_delete(self):
        cards = self.client.get("/api/p2-corpus").json()["current_part2_cards"]
        card = next(item for item in cards if len(item["p3_follow_ups"]) > 4)
        cue_id = card["cue_id"]
        followup_id = corpus_services.p3_bank_followup_id(cue_id, card["p3_follow_ups"][0], 0)
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id="bank-progress-observed",
            mode=SpeakingAttempt.Mode.P3,
            part="p3",
            status=SpeakingAttempt.Status.SCORED,
            metadata={
                "p3_bank_cue_id": cue_id,
                "p3_bank_round_index": 0,
                "p3_bank_round_count": card["practice_round_count"],
                "p3_bank_followup_ids": [followup_id],
            },
        )
        turn = SpeakingTurn.objects.create(
            user=self.user,
            attempt=attempt,
            turn_id="bank-progress-observed-turn",
            sequence=1,
            part="p3",
            question=card["p3_follow_ups"][0],
            transcript_cleaned="This is a completed answer.",
            metadata={"prompt": {"p3_bank_followup_id": followup_id}},
        )
        report = SpeakingReport.objects.create(user=self.user, attempt=attempt, report_payload={"status": "scored"})
        now = timezone.now()
        SpeakingTrainingObservation.objects.create(
            observation_id="bank-progress-observed-turn",
            user=self.user,
            attempt=attempt,
            turn=turn,
            legacy_attempt_id=attempt.attempt_id,
            legacy_turn_id=turn.turn_id,
            question_id=followup_id,
            part="p3",
            question=turn.question,
            transcript=turn.transcript_cleaned,
            relevance=Decimal("1.000"),
            observed_at=now,
            next_due=now,
        )
        report.delete()

        updated = self.client.get("/api/p2-corpus").json()
        progress = next(item for item in updated["current_part2_cards"] if item["cue_id"] == cue_id)

        self.assertEqual(progress["practice_question_counts"][followup_id], 1)
        self.assertEqual(progress["practice_cycle"], 1)
        self.assertIn(0, progress["practice_current_cycle_question_indexes"])

    def test_p2_corpus_p3_overlap_bridge_does_not_advance_ahead_of_cycle(self):
        cards = self.client.get("/api/p2-corpus").json()["current_part2_cards"]
        card = next(item for item in cards if len(item["p3_follow_ups"]) == 5)
        cue_id = card["cue_id"]
        followup_ids = [
            corpus_services.p3_bank_followup_id(cue_id, question, index)
            for index, question in enumerate(card["p3_follow_ups"])
        ]
        now = timezone.now()
        practice_attempts = ["bank-overlap-a", "bank-overlap-a", "bank-overlap-a", "bank-overlap-b", "bank-overlap-b", "bank-overlap-b"]
        for offset, (index, practice_attempt_id) in enumerate(zip([0, 1, 2, 3, 4, 2], practice_attempts), start=1):
            SpeakingTrainingObservation.objects.create(
                observation_id=f"bank-overlap-{offset}",
                user=self.user,
                legacy_attempt_id=practice_attempt_id,
                legacy_turn_id=f"bank-overlap-turn-{offset}",
                question_id=followup_ids[index],
                part="p3",
                question=card["p3_follow_ups"][index],
                transcript="This is a completed answer.",
                relevance=Decimal("1.000"),
                observed_at=now + timedelta(seconds=offset),
                next_due=now,
            )

        updated = self.client.get("/api/p2-corpus").json()
        progress = next(item for item in updated["current_part2_cards"] if item["cue_id"] == cue_id)

        self.assertEqual(progress["practice_question_counts"], {followup_id: 1 for followup_id in followup_ids})
        self.assertEqual(progress["practice_cycle"], 1)
        self.assertEqual(progress["practice_progress_state"], "complete")
        self.assertEqual(progress["practice_next_round_index"], 0)

    def test_p2_corpus_returns_global_p3_bank_cycle_summary(self):
        topics = [
            {
                "cue_id": "p2cue:global-cycle-a",
                "title": "Describe a river",
                "category": "place",
                "p3_theme": "nature",
                "p3_follow_ups": [
                    "Why are rivers important?",
                    "How do people protect rivers?",
                    "Will rivers matter more in the future?",
                ],
            },
            {
                "cue_id": "p2cue:global-cycle-b",
                "title": "Describe a building",
                "category": "place",
                "p3_theme": "architecture",
                "p3_follow_ups": [
                    "Why do cities build tall buildings?",
                    "How do old and new buildings differ?",
                    "Should governments protect historic buildings?",
                ],
            },
        ]
        bank = MagicMock()
        bank.part2_for_scope.return_value = topics

        with patch("apps.speaking.corpus_services.get_question_bank", return_value=bank):
            initial = self.client.get("/api/p2-corpus").json()["p3_bank_practice_summary"]

        self.assertEqual(initial["total_card_count"], 2)
        self.assertEqual(initial["total_question_count"], 6)
        self.assertEqual(initial["completed_cycle"], 0)
        self.assertEqual(initial["practice_cycle"], 1)
        self.assertEqual(initial["current_cycle_done_count"], 0)

        now = timezone.now()
        for topic_index, topic in enumerate(topics):
            cue_id = topic["cue_id"]
            for question_index, question in enumerate(topic["p3_follow_ups"]):
                SpeakingTrainingObservation.objects.create(
                    observation_id=f"global-cycle-{topic_index}-{question_index}",
                    user=self.user,
                    legacy_attempt_id=f"global-cycle-attempt-{topic_index}",
                    legacy_turn_id=f"global-cycle-turn-{topic_index}-{question_index}",
                    question_id=corpus_services.p3_bank_followup_id(cue_id, question, question_index),
                    part="p3",
                    question=question,
                    transcript="This is a completed answer.",
                    relevance=Decimal("1.000"),
                    observed_at=now + timedelta(seconds=topic_index * 10 + question_index),
                    next_due=now,
                )

        with patch("apps.speaking.corpus_services.get_question_bank", return_value=bank):
            completed = self.client.get("/api/p2-corpus").json()["p3_bank_practice_summary"]

        self.assertEqual(completed["completed_cycle"], 1)
        self.assertEqual(completed["practice_cycle"], 2)
        self.assertEqual(completed["current_cycle_done_count"], 0)

    def test_p2_corpus_keeps_completed_card_in_global_cycle_until_whole_bank_is_done(self):
        topics = [
            {
                "cue_id": "p2cue:global-card-a",
                "title": "Describe a river",
                "category": "place",
                "p3_theme": "nature",
                "p3_follow_ups": [
                    "Why are rivers important?",
                    "How do people protect rivers?",
                    "Will rivers matter more in the future?",
                ],
            },
            {
                "cue_id": "p2cue:global-card-b",
                "title": "Describe a building",
                "category": "place",
                "p3_theme": "architecture",
                "p3_follow_ups": [
                    "Why do cities build tall buildings?",
                    "How do old and new buildings differ?",
                    "Should governments protect historic buildings?",
                ],
            },
        ]
        bank = MagicMock()
        bank.part2_for_scope.return_value = topics
        now = timezone.now()
        first_topic = topics[0]
        for question_index, question in enumerate(first_topic["p3_follow_ups"]):
            SpeakingTrainingObservation.objects.create(
                observation_id=f"global-card-a-{question_index}",
                user=self.user,
                legacy_attempt_id="global-card-a-attempt",
                legacy_turn_id=f"global-card-a-turn-{question_index}",
                question_id=corpus_services.p3_bank_followup_id(
                    first_topic["cue_id"],
                    question,
                    question_index,
                ),
                part="p3",
                question=question,
                transcript="This is a completed answer.",
                relevance=Decimal("1.000"),
                observed_at=now + timedelta(seconds=question_index),
                next_due=now,
            )

        with patch("apps.speaking.corpus_services.get_question_bank", return_value=bank):
            payload = self.client.get("/api/p2-corpus").json()

        first_card, second_card = payload["current_part2_cards"]
        self.assertEqual(payload["p3_bank_practice_summary"]["practice_cycle"], 1)
        self.assertEqual(first_card["practice_cycle"], 1)
        self.assertEqual(first_card["practice_progress_state"], "complete")
        self.assertEqual(first_card["practice_current_cycle_completed_count"], 3)
        self.assertEqual(second_card["practice_cycle"], 1)
        self.assertEqual(second_card["practice_progress_state"], "none")
        self.assertEqual(second_card["practice_current_cycle_completed_count"], 0)

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

    def test_p2_corpus_and_bank_entries_can_be_cleared(self):
        entry = P2CorpusEntry.objects.create(
            user=self.user,
            entry_id="clearable-p2-entry",
            category=P2CorpusEntry.Category.PERSON,
            title="Clearable P2 material",
            material_text="Prepared material to clear.",
        )

        response = self.client.post(
            "/api/p2-corpus",
            data={
                "entry_id": entry.entry_id,
                "category": entry.category,
                "title": entry.title,
                "material_text": "",
                "linked_question": entry.linked_question,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["material_text"], "")
        entry.refresh_from_db()
        self.assertEqual(entry.material_text, "")

        library = self.client.get("/api/p2-corpus").json()
        card = library["current_part2_cards"][0]
        self.client.put(
            f"/api/p2-bank-corpus/{card['cue_id']}",
            data={
                "question": card["linked_question"],
                "corpus_text": "Prepared bank material to clear.",
            },
            content_type="application/json",
        )
        clear_response = self.client.put(
            f"/api/p2-bank-corpus/{card['cue_id']}",
            data={
                "question": card["linked_question"],
                "corpus_text": "",
            },
            content_type="application/json",
        )
        self.assertEqual(clear_response.status_code, 200)
        self.assertEqual(clear_response.json()["corpus_text"], "")
        bank_entry = P2BankCorpusEntry.objects.get(user=self.user, question_id=card["cue_id"])
        self.assertEqual(bank_entry.corpus_text, "")

        updated = self.client.get("/api/p2-corpus").json()
        updated_card = next(item for item in updated["current_part2_cards"] if item["entry_id"] == card["entry_id"])
        self.assertFalse(updated_card["has_material"])
        self.assertEqual(updated_card["material_text"], "")

    def test_report_saved_status_normalizes_p2_bank_ids(self):
        library = self.client.get("/api/p2-corpus").json()
        card = library["current_part2_cards"][0]
        canonical_id = card["entry_id"]
        cue_id = card["cue_id"]

        self.client.put(
            f"/api/p2-bank-corpus/{canonical_id}",
            data={
                "question": card["linked_question"],
                "corpus_text": "A prepared P2 answer saved through the report entry.",
            },
            content_type="application/json",
        )

        response = self.client.post(
            "/api/corpus/saved-status",
            data={
                "targets": [
                    {"key": "canonical", "kind": "p2_bank", "questionId": canonical_id},
                    {"key": "cue", "kind": "p2_bank", "questionId": cue_id},
                ]
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        statuses = response.json()["statuses"]
        self.assertTrue(statuses["canonical"])
        self.assertTrue(statuses["cue"])

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

    def test_p3_bank_followup_corpus_bulk_save_is_atomic_and_returns_canonical_snapshot(self):
        library = self.client.get("/api/p2-corpus").json()
        card = next(item for item in library["current_part2_cards"] if len(item.get("p3_follow_ups") or []) >= 2)
        list_response = self.client.get(f"/api/p3-bank-corpus/{card['cue_id']}")
        self.assertEqual(list_response.status_code, 200)
        items = list_response.json()["items"]

        first_snapshot = [
            {
                "followup_id": item["followup_id"],
                "followup_question": item["followup_question"],
                "corpus_text": f"Prepared answer {index + 1}." if index < 2 else "",
            }
            for index, item in enumerate(items)
        ]
        save_response = self.client.put(
            f"/api/p3-bank-corpus/{card['cue_id']}",
            data={"items": first_snapshot, "source": "p3_bank_corpus_editor"},
            content_type="application/json",
        )
        self.assertEqual(save_response.status_code, 200)
        saved = save_response.json()
        self.assertEqual(saved["count"], len(items))
        self.assertEqual(saved["saved_count"], 2)
        self.assertEqual([item["corpus_text"] for item in saved["items"][:2]], ["Prepared answer 1.", "Prepared answer 2."])

        invalid_snapshot = [dict(item) for item in first_snapshot]
        invalid_snapshot[-1]["followup_id"] = "not-a-real-followup"
        invalid_snapshot[0]["corpus_text"] = "This must not be partially saved."
        invalid_response = self.client.put(
            f"/api/p3-bank-corpus/{card['cue_id']}",
            data={"items": invalid_snapshot, "source": "p3_bank_corpus_editor"},
            content_type="application/json",
        )
        self.assertEqual(invalid_response.status_code, 400)

        unchanged = self.client.get(f"/api/p3-bank-corpus/{card['cue_id']}").json()
        self.assertEqual(unchanged["saved_count"], 2)
        self.assertEqual(unchanged["items"][0]["corpus_text"], "Prepared answer 1.")

    def test_report_saved_status_uses_p2_corpus_p3_text_not_material_text(self):
        entry = P2CorpusEntry.objects.create(
            user=self.user,
            entry_id="p2:test-p3-only",
            category=P2CorpusEntry.Category.PERSON,
            title="A person I know",
            material_text="",
            linked_question="Describe a person you know.",
            metadata={"p3_follow_up_text": "For P3, I can discuss social trust."},
        )

        response = self.client.post(
            "/api/corpus/saved-status",
            data={
                "targets": [
                    {"key": "p3", "kind": "p2_corpus_p3", "entryId": entry.entry_id},
                    {"key": "body", "kind": "p2_bank", "questionId": entry.entry_id},
                ]
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        statuses = response.json()["statuses"]
        self.assertTrue(statuses["p3"])
        self.assertFalse(statuses["body"])

    def test_p2_bank_corpus_batch_returns_multiple_cards(self):
        cards = self.client.get("/api/p2-corpus").json()["current_part2_cards"]
        ids = [card["cue_id"] for card in cards[:3]]
        response = self.client.post(
            "/api/p2-bank-corpus/batch",
            data={"question_ids": ids},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(set(items.keys()), set(ids))
        for cue_id in ids:
            self.assertEqual(items[cue_id]["question_id"], cue_id)

    def test_p2_bank_corpus_batch_empty_returns_empty_items(self):
        response = self.client.post(
            "/api/p2-bank-corpus/batch",
            data={"question_ids": []},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], {})

    def test_p2_bank_corpus_batch_over_limit_returns_400(self):
        response = self.client.post(
            "/api/p2-bank-corpus/batch",
            data={"question_ids": [f"p2cue:{index}" for index in range(51)]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_p2_bank_corpus_batch_requires_login(self):
        self.client.logout()
        response = self.client.post(
            "/api/p2-bank-corpus/batch",
            data={"question_ids": []},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_p3_bank_corpus_batch_returns_multiple_cards(self):
        cards = self.client.get("/api/p2-corpus").json()["current_part2_cards"]
        ids = [card["cue_id"] for card in cards[:3]]
        response = self.client.post(
            "/api/p3-bank-corpus/batch",
            data={"question_ids": ids},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(set(items.keys()), set(ids))
        for cue_id in ids:
            self.assertEqual(items[cue_id]["p2_question_id"], cue_id)
            self.assertIn("items", items[cue_id])

    def test_p3_bank_corpus_batch_empty_returns_empty_items(self):
        response = self.client.post(
            "/api/p3-bank-corpus/batch",
            data={"question_ids": []},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], {})

    def test_p3_bank_corpus_batch_over_limit_returns_400(self):
        response = self.client.post(
            "/api/p3-bank-corpus/batch",
            data={"question_ids": [f"p2cue:{index}" for index in range(51)]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

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

    def test_takeaway_review_state_put_merges_newer_entry_records(self):
        first = {
            "__daily_batch": {"day": "2026-06-12", "ids": ["old"], "completedDay": "2026-06-12"},
            "shared": {"due": "2026-06-13", "last": "2026-06-12", "reps": 1},
            "old-only": {"due": "2026-06-13", "last": "2026-06-12", "reps": 2},
        }
        second = {
            "__daily_batch": {"day": "2026-06-13", "ids": ["new"], "completedDay": ""},
            "shared": {"due": "2026-06-14", "last": "2026-06-11", "reps": 9},
            "new-only": {"due": "2026-06-14", "last": "2026-06-13", "reps": 1},
        }
        self.client.post("/api/takeaway-review-state/language", data={"state": first}, content_type="application/json")

        response = self.client.post(
            "/api/takeaway-review-state/language",
            data={"state": second},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        merged = response.json()["review_state"]
        self.assertEqual(merged["__daily_batch"]["day"], "2026-06-13")
        self.assertEqual(merged["shared"]["last"], "2026-06-12")
        self.assertEqual(merged["shared"]["reps"], 1)
        self.assertIn("old-only", merged)
        self.assertIn("new-only", merged)

    def test_expression_replacement_entries_are_persisted_per_user(self):
        other_user = get_user_model().objects.create_user(username="other-expression-user", password="test-pass")
        ExpressionReplacementEntry.objects.create(
            user=other_user,
            kind="writing",
            item_id="custom:important",
            source="important",
            replacements="vital / crucial",
        )

        self.client.logout()
        response = self.client.get("/api/expression-replacements/writing")
        self.assertEqual(response.status_code, 401)
        self.client.force_login(self.user)

        response = self.client.put(
            "/api/expression-replacements/writing/custom:important",
            data=json.dumps({"source": "important", "replacements": "vital / crucial / essential"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item_id"], "custom:important")
        self.assertEqual(response.json()["replacements"], "vital / crucial / essential")

        response = self.client.get("/api/expression-replacements/writing")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "important")
        self.assertEqual(items[0]["replacements"], "vital / crucial / essential")
        self.assertEqual(ExpressionReplacementEntry.objects.filter(user=other_user).count(), 1)

        response = self.client.delete("/api/expression-replacements/writing/custom:important")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "item_id": "custom:important"})
        self.assertFalse(ExpressionReplacementEntry.objects.filter(user=self.user, item_id="custom:important").exists())

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

    def test_score_rejects_attempt_with_no_answers(self):
        # A dropped/empty turn no longer blocks the whole report (that left learners
        # stuck on an endless 重新分析 loop). Auto-completing empty turns means an
        # attempt where *nothing* was answered is now rejected for the real reason:
        # there is no transcript to score. A totally empty attempt should not be
        # presented as a recoverable report, because there is nothing to replay,
        # transcribe, or rescore.
        attempt, _turn1, _turn2 = self.create_attempt()
        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/score", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("no scoreable transcript", response.json()["error"])

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, SpeakingAttempt.Status.READY_TO_SCORE)
        self.assertEqual(attempt.metadata["analysis_status"], "failed")
        history = self.client.get("/api/history")
        history_items = {item["id"]: item for item in history.json()["items"]}
        self.assertEqual(history_items[attempt.attempt_id]["report_status"], "failed")

        detail = self.client.get(f"/api/history/{attempt.attempt_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["report_status"], "failed")

    def test_score_failure_with_audio_keeps_unscored_report_and_audio_recovery(self):
        attempt, turn1, _turn2 = self.create_attempt(attempt_id="runtime-audio-only")
        turn1.audio_path = "audio/runtime-audio-only/t1.webm"
        turn1.metadata = {**turn1.metadata, "status": "completed", "transcript_status": "missing"}
        turn1.save()

        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/score", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Recording saved", response.json()["error"])

        detail = self.client.get(f"/api/history/{attempt.attempt_id}")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["report_status"], "failed")
        self.assertFalse(body["can_regenerate_report"])
        self.assertTrue(body["can_regenerate_transcript"])
        first_turn = body["turns"][0]
        self.assertEqual(first_turn["audio"]["url"], f"/api/audio/{attempt.attempt_id}/t1/candidate")
        self.assertEqual(first_turn["transcript_status"], "missing")

    def test_score_retry_after_failed_metadata_requeues_when_transcript_exists(self):
        attempt, turn1, _turn2 = self.create_attempt(attempt_id="runtime-failed-retry")
        turn1.transcript_raw = "I study English every day because I want to speak more clearly."
        turn1.transcript_cleaned = turn1.transcript_raw
        turn1.metadata = {**turn1.metadata, "status": "completed", "transcript_status": "captured"}
        turn1.save()
        attempt.status = SpeakingAttempt.Status.READY_TO_SCORE
        attempt.metadata = {
            "analysis_status": "failed",
            "report_generation_status": "failed",
            "analysis_error": "previous AI failure",
        }
        attempt.save(update_fields=["status", "metadata", "updated_at"])

        before = self.client.get(f"/api/history/{attempt.attempt_id}")
        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.json()["report_status"], "failed")
        self.assertTrue(before.json()["can_regenerate_report"])

        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/score", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "analysis_pending")
        self.assertEqual(body["ai_task"]["related_id"], attempt.attempt_id)

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, SpeakingAttempt.Status.READY_TO_SCORE)
        self.assertEqual(attempt.metadata["analysis_status"], "queued")

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
        self.assertEqual(history.status_code, 200)
        items = {item["id"]: item for item in history.json()["items"]}
        self.assertIn(attempt.attempt_id, items)
        self.assertEqual(items[attempt.attempt_id]["report_status"], "scoring")
        self.assertEqual(items[attempt.attempt_id]["ai_task"]["status"], "pending")

        detail = self.client.get(f"/api/history/{attempt.attempt_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["report_status"], "scoring")
        self.assertFalse(detail.json()["can_regenerate_report"])

    def test_score_self_heals_dropped_turn_instead_of_blocking(self):
        # turn1 is answered, turn2 dropped (no transcript / never completed). The
        # report must still queue instead of failing the whole attempt with
        # "Complete all speaking turns" — and the dropped turn is auto-completed empty.
        attempt, turn1, turn2 = self.create_attempt()
        turn1.transcript_raw = "I study English every day so I can talk with classmates."
        turn1.transcript_cleaned = turn1.transcript_raw
        turn1.metadata = {**turn1.metadata, "status": "completed"}
        turn1.save()
        self.assertNotEqual(turn2.metadata.get("status"), "completed")

        response = self.client.post(f"/api/attempts/{attempt.attempt_id}/score", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "analysis_pending")

        turn2.refresh_from_db()
        self.assertEqual(turn2.metadata.get("status"), "completed")
        self.assertTrue(turn2.metadata.get("dropped_empty"))


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
                "turns": [{"id": "t1", "status": "completed", "transcript_cleaned": "My full name is Sam.", "band7_version": "My full name is Sam, and I usually go by Sam."}],
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
                score_with_codex("test transcript", "test question", "p1", "test_call", ai_source="codex_cli")
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
                score_with_codex("test transcript", "test question", "p1", "test_call", ai_source="codex_cli")
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
            result = score_with_codex(
                "test transcript",
                "test question",
                "p1",
                "test_call",
                ai_source="codex_cli",
            )
            self.assertEqual(result["backend"], "codex_cli")
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

        with patch("apps.speaking.services.run_codex", side_effect=fake_run_codex):
            result = score_with_codex(
                "Q1: Do you like buses?\nA: I like buses because they are cheap.",
                "Do you like buses?",
                "p1",
                "test_review_prompt",
                ai_source="codex_cli",
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
        self.assertEqual(
            [item["key"] for item in base["dimensions"]],
            ["abstract_extension", "reasoning", "comparison_concession", "specific_support"],
        )
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
            },
        }

        with patch(
            "apps.speaking.services.run_codex",
            return_value=(json.dumps(ai_payload, ensure_ascii=False), {"input_tokens": 10}),
        ) as run_codex:
            enriched = enrich_p3_discussion_skills_with_ai(
                attempt,
                base,
                {"overall_band": 6.0},
                {"primary_focus_text": "补展开"},
                "test_p3_skills",
                ai_source="codex_cli",
            )

        prompt = run_codex.call_args.args[0]
        self.assertIn("老师听完这次 Part 3 后给的一段复盘", prompt)
        self.assertIn("为什么这样会让 Part 3 更像讨论", prompt)
        self.assertIn("不要每次都写同一类", prompt)
        self.assertNotIn("follow_up_handling", prompt)
        self.assertNotIn("追问承接", prompt)
        self.assertEqual(enriched["generation_backend"], "codex_cli")
        self.assertEqual(enriched["summary"], ai_payload["summary"])
        self.assertEqual(enriched["next_drill"], ai_payload["next_drill"])
        enriched_status = {
            item["key"]: item["status"]
            for item in enriched["dimensions"]
        }
        self.assertEqual(enriched_status, original_status)
        self.assertEqual(enriched["dimensions"][0]["evidence"], "AI 证据：提到了 society，但还缺少 wider impact。")

    def test_p3_discussion_skills_reuses_score_payload_without_third_ai_call(self):
        from apps.accounts.models import CustomUser
        from apps.speaking.services import build_p3_discussion_skills, enrich_p3_discussion_skills_with_ai

        user = CustomUser.objects.create_user(username="p3-skills-score-payload", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="p3-skills-score-payload",
            mode="p3",
            part="p3",
            status=SpeakingAttempt.Status.SCORED,
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="p3-score-payload-turn",
            sequence=0,
            part="p3",
            question="Why is public transport important?",
            transcript_cleaned="It reduces traffic because many people can share one vehicle.",
            metadata={"status": "completed", "prompt": {"role": "main"}},
        )
        base = build_p3_discussion_skills(attempt)
        payload = {
            "summary": "The answer gives a clear reason but needs wider development.",
            "best_moment": "The traffic-reduction reason is direct.",
            "fix_next": "Add a social consequence.",
            "next_drill": ["State a view", "Give a reason", "Add an impact"],
            "dimensions": {
                item["key"]: {"evidence": "Specific evidence.", "next_action": "Develop this move."}
                for item in base["dimensions"]
            },
        }

        with patch("apps.speaking.services._report_provider_json") as report_provider:
            enriched = enrich_p3_discussion_skills_with_ai(
                attempt,
                base,
                {"overall_band": 6.0, "backend": "http_api", "model": "test-model"},
                {},
                "p3-score-payload",
                ai_payload=payload,
                allow_provider_call=False,
            )

        report_provider.assert_not_called()
        self.assertEqual(enriched["generation_status"], "ready")
        self.assertEqual(enriched["generation_backend"], "http_api")
        self.assertEqual(enriched["summary"], payload["summary"])

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
        from apps.accounts.models import UserProfile
        from apps.speaking.services import score_attempt_sync

        user, attempt, turn = self.create_ready_attempt()
        UserProfile.objects.create(user=user, report_ai_source="codex_cli")
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
        self.assertEqual(result["ielts_score"]["backend"], "codex_cli")
        self.assertEqual(result["ielts_score"]["generation_status"], "ready")
        self.assertEqual(result["ielts_score"]["overall_band"], 6.0)
        self.assertEqual(
            result["billing_usage"],
            {
                "input_tokens": 380,
                "cached_input_tokens": 0,
                "output_tokens": 220,
                "reasoning_output_tokens": 0,
            },
        )
        self.assertEqual(result["feedback_summary"], "Codex scored this exact speaking response.")
        self.assertEqual(result["overall_review"]["backend"], "codex_cli")
        self.assertEqual(result["overall_review"]["markdown"], score_payload["overall_review"]["markdown"])
        turn.refresh_from_db()
        self.assertEqual(turn.metadata["feedback_generation_backend"], "codex_cli")
        self.assertEqual(turn.metadata["feedback_generation_status"], "ready")
        self.assertEqual(turn.metadata["display_transcript_markdown"], "I study software engineering.")
        self.assertIn("software engineering", turn.metadata["band7_version"])
        self.assertEqual(turn.metadata["band7_source"], "codex_cli_report_batch")
        report = SpeakingReport.objects.get(attempt=attempt)
        self.assertEqual(report.report_payload["score_generation_backend"], "codex_cli")
        self.assertEqual(report.report_payload["report_generation_status"], "ready")
        self.assertEqual(report.report_payload["turns"][0]["feedback_generation_status"], "ready")
        self.assertIn("software engineering", report.report_payload["turns"][0]["band7_version"])
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, SpeakingAttempt.Status.SCORED)
        self.assertEqual(attempt.metadata["analysis_status"], "ready")
        self.assertEqual(attempt.metadata["analysis_backend"], "codex_cli")
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
            "turns": [{"id": turn.turn_id, "status": "completed", "band7_version": "My full name is Sam Chen."}],
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
        self.assertEqual(task.metadata["billing_policy"], "balance_gate_then_usage_settlement")

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

    def test_speaking_report_task_uses_profile_source_when_payload_omits_provider(self):
        from apps.accounts.models import UserProfile
        from apps.ai.models import AITask
        from apps.speaking.services import score_attempt

        user, attempt, _turn = self.create_ready_attempt(
            username="score-attempt-profile-source-user",
            attempt_id="score-attempt-profile-source",
        )
        UserProfile.objects.create(user=user, report_ai_source="claude")

        result = score_attempt(user, attempt.attempt_id, {})

        task = AITask.objects.get(task_id=result["ai_task"]["id"])
        self.assertEqual(task.provider, "codex")
        self.assertEqual(task.request_payload["requested_provider"], "claude")
        self.assertEqual(task.metadata["requested_provider"], "claude")

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

        self.assertIn("no scoreable transcript", str(ctx.exception))
        self.assertFalse(AITask.objects.filter(related_id=attempt.attempt_id, task_type="speaking_report").exists())
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, SpeakingAttempt.Status.READY_TO_SCORE)
        self.assertEqual(attempt.metadata["analysis_status"], "failed")

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

    def test_score_attempt_marks_analysis_failed_without_publishing_report_when_codex_fails(self):
        from apps.accounts.models import UserProfile
        from apps.speaking.services import SpeakingError, score_attempt_sync

        user, attempt, turn = self.create_ready_attempt(
            username="score-attempt-fallback-user",
            attempt_id="score-attempt-fallback-path",
        )
        UserProfile.objects.create(user=user, report_ai_source="codex_cli")

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

    def test_p3_model_answer_contract_is_shared_by_all_generation_paths(self):
        from apps.speaking.services import (
            build_turn_band7_with_codex,
            turn_feedback_batch_with_codex,
            turn_feedback_with_codex,
        )

        user = get_user_model().objects.create_user(username="p3-model-contract", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="p3-model-contract-attempt",
            mode="p3",
            part="p3",
            status=SpeakingAttempt.Status.READY_TO_SCORE,
        )
        turn = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="p3-model-contract-turn",
            sequence=0,
            part="p3",
            question="Are young people under more pressure today?",
            transcript_raw="I think they are because competition is stronger.",
            transcript_cleaned="I think they are because competition is stronger.",
            metadata={"status": "completed"},
        )
        single_payload = {
            "display_transcript": turn.transcript_cleaned,
            "display_transcript_markdown": turn.transcript_cleaned,
            "band7_version": "Well, I would say they are under more pressure today.",
            "ai_coaching": "观点明确，可以增加现实观察。\n\n语法错误纠正：无",
        }
        batch_payload = {"turns": [{"turn_id": turn.turn_id, **single_payload}]}

        captured_prompts = []
        with (
            override_settings(SPEAKING_REPORT_AI_CALL_MODE="codex"),
            patch(
                "apps.speaking.services.run_codex",
                return_value=("Well, I would say they are under more pressure today.", {"input_tokens": 10}),
            ) as standalone_run,
        ):
            build_turn_band7_with_codex(
                turn.question,
                turn.transcript_cleaned,
                "p3",
                "p3_contract_standalone",
            )
            captured_prompts.append(standalone_run.call_args.args[0])

        with patch(
            "apps.speaking.services.run_codex",
            return_value=(json.dumps(single_payload, ensure_ascii=False), {"input_tokens": 10}),
        ) as single_run:
            turn_feedback_with_codex(
                turn.question,
                turn.transcript_cleaned,
                "p3",
                "7",
                None,
                "p3_contract_single",
                ai_source="codex_cli",
            )
            captured_prompts.append(single_run.call_args.args[0])

        with patch(
            "apps.speaking.services.run_codex",
            return_value=(json.dumps(batch_payload, ensure_ascii=False), {"input_tokens": 10}),
        ) as batch_run:
            turn_feedback_batch_with_codex(
                [turn],
                attempt,
                "7",
                None,
                "p3_contract_batch",
                ai_source="codex_cli",
            )
            captured_prompts.append(batch_run.call_args.args[0])

        required_clauses = (
            "45-70 seconds",
            "natural conversation",
            "active listening",
            "personal lens",
            "China",
            "diplomatic",
            "Do not mechanically",
            "spoken English answer only",
            "**题目分析：**",
            "Question-type choice",
            "Listing Group A",
            "Category Group B",
            "Parallel explanation",
            "Two-camp contrast",
            "Hourglass",
            "**1. 接题（复述/改写题目本身）**",
            "**3.3 让步限定**",
            "**5. 自然收尾**",
            "3-5 reusable spoken expressions",
            "Why these choices matter",
        )
        for prompt in captured_prompts:
            for clause in required_clauses:
                self.assertIn(clause, prompt)
            self.assertNotIn("Bold 2-5", prompt)
            self.assertNotIn("bold on 2-5", prompt)

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

    def test_build_p3_turn_feedback_keeps_study_structure_out_of_tts(self):
        """P3 reports keep the study scaffold while model audio reads only the answer."""
        from apps.speaking.services import build_turn_feedback

        user = get_user_model().objects.create_user(username="p3-band7-structure-user", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="p3-band7-structure-attempt",
            mode="p3",
            part="p3",
            status=SpeakingAttempt.Status.STARTED,
        )
        turn = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="p3-structure-turn",
            sequence=0,
            part="p3",
            question="Why do many children find education boring?",
            transcript_raw="Maybe it is because classes repeat the same things.",
            metadata={"status": "completed"},
        )
        structured_answer = """**Q: Why do many children find education boring?**

**1. 接题（复述/改写题目本身）**
- That's an interesting one because I remember feeling that way myself.

**2. 观点**
- I'd say it **mostly comes down to how lessons are taught**.

**3.1 原因/背景**
- **Let me put it this way** — repetition can make curiosity disappear.

**3.2 现实观察**
- Practical classes were the ones I remembered.

**3.3 让步限定**
- **That said**, teachers often have packed curriculums.

**5. 自然收尾**
- So the delivery matters more than the subject itself.

*(≈70词/45-50秒)*"""
        generated = {
            "display_transcript": "Maybe it is because classes repeat the same things.",
            "band7_version": structured_answer,
            "ai_coaching": "这个回答需要更具体。\n\n语法错误纠正：无",
        }

        with patch("apps.speaking.services.volcengine_tts", return_value={"status": "pending"}) as mock_tts:
            feedback = build_turn_feedback(turn, attempt, generated_feedback=generated)

        self.assertIn("**Q: Why do many children", feedback["band7_markdown"])
        self.assertIn("**3.3 让步限定**", feedback["band7_markdown"])
        self.assertNotIn("Why do many children", feedback["band7_version"])
        self.assertNotIn("接题", feedback["band7_version"])
        self.assertNotIn("70词", feedback["band7_version"])
        self.assertIn("mostly comes down to how lessons are taught", feedback["band7_version"])
        self.assertEqual(mock_tts.call_args.args[0], feedback["band7_version"])

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

    def test_batch_turn_feedback_prompt_explains_asr_and_spoken_coaching_intent(self):
        from apps.speaking.services import turn_feedback_batch_with_codex

        user = get_user_model().objects.create_user(username="batch-prompt-intent", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="batch-prompt-intent-attempt",
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
            question="Do you prefer shopping online or in stores?",
            transcript_raw="I prefer shopping online because the price is more transparent.",
            transcript_cleaned="I prefer shopping online because the price is more transparent.",
            metadata={"status": "completed"},
        )
        payload = {
            "turns": [
                {
                    "turn_id": "t1",
                    "display_transcript": "I prefer shopping online because the price is more transparent.",
                    "display_transcript_markdown": "I prefer shopping online because the price is more transparent.",
                    "band7_version": "I prefer shopping online because **the prices are more transparent**.",
                    "ai_coaching": "回答方向清楚，可以补一个送货到家的结果。\n\n语法错误纠正：无",
                }
            ]
        }

        with patch("apps.speaking.services.run_codex", return_value=(json.dumps(payload), {"input_tokens": 100})) as mock_run:
            turn_feedback_batch_with_codex(
                [turn],
                attempt,
                "7",
                None,
                "batch_prompt_intent",
                ai_source="codex_cli",
            )

        prompt = mock_run.call_args.args[0]
        self.assertIn("a very modern, isolated way of living", prompt)
        self.assertIn("A fuller believable answer is more useful", prompt)
        self.assertIn("real speaking test has no capitals", prompt)
        self.assertIn("only coach the real learner errors", prompt)

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
            result = turn_feedback_batch_with_codex(
                [turn],
                attempt,
                "7",
                None,
                "batch_visible",
                ai_source="codex_cli",
            )

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

    def test_report_turn_feedback_generates_band7_for_empty_answer_without_coaching(self):
        from apps.speaking.services import generate_turn_feedback_for_report

        user = get_user_model().objects.create_user(username="report-empty-band7", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="report-empty-band7-attempt",
            mode="p1",
            part="p1",
            status=SpeakingAttempt.Status.READY_TO_SCORE,
        )
        turn = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t-empty",
            sequence=0,
            part="p1",
            question="Do you like rainy days?",
            transcript_raw="",
            transcript_cleaned="",
            metadata={"status": "completed", "dropped_empty": True},
        )
        generated = {
            "t-empty": {
                "display_transcript": "",
                "display_transcript_markdown": "",
                "band7_version": "Yes, I do, because rainy days make the city feel calmer and help me slow down.",
                "ai_coaching": "This should be ignored for an empty answer.",
                "generation_backend": "codex",
            }
        }

        with (
            patch("apps.speaking.services.turn_feedback_batch_with_codex", return_value=generated) as batch,
            patch("apps.speaking.services.volcengine_tts", return_value={"status": "pending"}),
        ):
            generate_turn_feedback_for_report(attempt, [turn], {}, "report_empty_band7")

        batch.assert_called_once()
        turn.refresh_from_db()
        self.assertIn("rainy days", turn.metadata["band7_version"])
        self.assertEqual(turn.metadata["display_transcript"], "")
        self.assertEqual(turn.metadata["display_transcript_markdown"], "")
        self.assertEqual(turn.metadata["ai_coaching"], "")
        self.assertEqual(turn.metadata["feedback_generation_status"], "ready")

    def test_report_cache_invalid_when_empty_turn_lacks_band7(self):
        from apps.speaking.report_services import report_is_valid

        user = get_user_model().objects.create_user(username="report-empty-cache", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="report-empty-cache-attempt",
            mode="p1",
            part="p1",
            status=SpeakingAttempt.Status.SCORED,
        )
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="t-empty",
            sequence=0,
            part="p1",
            question="Do you like rainy days?",
            transcript_raw="",
            transcript_cleaned="",
            metadata={"status": "completed", "dropped_empty": True},
        )
        SpeakingReport.objects.create(
            user=user,
            attempt=attempt,
            overall_band=6.0,
            fluency_coherence=6.0,
            lexical_resource=6.0,
            grammar_range_accuracy=6.0,
            report_payload={
                "turns": [
                    {
                        "id": "t-empty",
                        "part": "p1",
                        "status": "completed",
                        "question": "Do you like rainy days?",
                        "display_transcript": "",
                        "band7_version": "",
                        "ai_coaching": "",
                    }
                ]
            },
        )

        self.assertFalse(report_is_valid(attempt))

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
        from apps.accounts.models import CustomUser, UserProfile

        user = CustomUser.objects.create_user(username="test-regen-user", password="test-pass")
        UserProfile.objects.create(user=user, report_ai_source="codex_cli")
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

        # Mock codex to return valid Overall scores. Phase-1 per-turn feedback is
        # mocked as a success so the report-integrity gate (abort if phase-1 fails)
        # is satisfied; this test is specifically about the Overall regeneration
        # repairing all-zero scores, not about per-turn feedback internals.
        with patch("apps.speaking.services.run_codex") as mock_run, patch(
            "apps.speaking.services.generate_turn_feedback_for_report", return_value=None
        ):
            mock_run.return_value = (
                '{"fluency_coherence": 6.0, "lexical_resource": 6.0, "grammatical_range": 6.0, "feedback": "Good work"}',
                {"input_tokens": 100},
            )
            result = regenerate_attempt_report(user, "test-regen-attempt")

            self.assertTrue(result["ok"])
            # Should have real scores now
            self.assertGreater(result["attempt"]["ielts_score"]["overall_band"], 0)
            self.assertEqual(result["attempt"]["ielts_score"]["backend"], "codex_cli")

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
        """Both fixed intros are hidden from scoring; Work/Study also skips Band 7 and coaching."""
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
        self.assertFalse(turn_counts_for_scoring(work_turn))
        self.assertFalse(turn_needs_ai_coaching(work_turn))

        feedback = build_turn_feedback(
            work_turn,
            attempt,
            allow_codex=False,
            generated_feedback={
                "display_transcript": "I'm a university student majoring in software engineering, and I'm also doing an internship.",
                "band7_version": "This generated answer must be ignored for the fixed opener.",
                "ai_coaching": "",
            },
        )
        self.assertEqual(feedback["ai_coaching"], "")
        self.assertIn("university student", feedback["display_transcript"])
        self.assertEqual(feedback["band7_version"], "")
        self.assertEqual(feedback["feedback_generation_status"], "skipped")

    def test_p1_work_study_intro_is_omitted_from_batch_ai_call(self):
        from apps.accounts.models import CustomUser
        from apps.speaking.services import turn_feedback_batch_with_codex

        user = CustomUser.objects.create_user(username="test-work-study-batch-skip", password="test-pass")
        attempt = SpeakingAttempt.objects.create(user=user, attempt_id="test-work-study-batch-skip", mode="p1", part="p1")
        work_turn = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="work-study-intro",
            sequence=0,
            part="p1",
            question="Do you work or do you study?",
            transcript_raw="I'm a university student.",
            metadata={"status": "completed", "prompt": {"flow": "intro", "role": "work_study"}},
        )

        with patch("apps.speaking.services.run_codex") as run_codex:
            result = turn_feedback_batch_with_codex(
                [work_turn],
                attempt,
                "7",
                {},
                "work-study-intro-batch",
                ai_source="codex_cli",
            )

        self.assertEqual(result, {})
        run_codex.assert_not_called()

    def test_codex_cli_turn_feedback_uses_small_batches(self):
        from apps.accounts.models import CustomUser
        from apps.speaking.services import turn_feedback_batch_with_codex

        user = CustomUser.objects.create_user(username="test-codex-cli-batches", password="test-pass")
        attempt = SpeakingAttempt.objects.create(user=user, attempt_id="test-codex-cli-batches", mode="p1", part="p1")
        turns = [
            SpeakingTurn.objects.create(
                user=user,
                attempt=attempt,
                turn_id=f"batch-turn-{index}",
                sequence=index,
                part="p1",
                question=f"Question {index + 1}?",
                transcript_raw="",
                metadata={"status": "completed"},
            )
            for index in range(4)
        ]

        def codex_batch_result(prompt, _call_id, timeout=180):
            input_turns = json.loads(prompt.split("Input turns:\n", 1)[1].strip())
            payload = {
                "turns": [
                    {
                        "turn_id": item["turn_id"],
                        "display_transcript": "",
                        "display_transcript_markdown": "",
                        "band7_version": f"A direct model answer for {item['question']}",
                        "ai_coaching": "",
                    }
                    for item in input_turns
                ]
            }
            return json.dumps(payload), {"input_tokens": 10, "output_tokens": 5}

        with patch("apps.speaking.services.run_codex", side_effect=codex_batch_result) as run_codex:
            result = turn_feedback_batch_with_codex(
                turns,
                attempt,
                "7",
                {},
                "codex-cli-batch-test",
                ai_source="codex_cli",
            )

        self.assertEqual(len(result), 4)
        self.assertEqual(run_codex.call_count, 2)

    def test_http_turn_feedback_uses_expanded_output_budget(self):
        from apps.accounts.models import CustomUser
        from apps.speaking import services
        from apps.speaking.services import turn_feedback_batch_with_codex

        class CapturingHttpProvider:
            def __init__(self):
                self.calls = []

            def complete_chat(self, *args, **kwargs):
                self.calls.append(kwargs)
                input_turns = json.loads(args[0][1]["content"].split("Input turns:\n", 1)[1].strip())
                payload = {
                    "turns": [
                        {
                            "turn_id": item["turn_id"],
                            "display_transcript": item["candidate_transcript"],
                            "display_transcript_markdown": item["candidate_transcript"],
                            "band7_version": f"A direct model answer for {item['question']}",
                            "ai_coaching": "",
                        }
                        for item in input_turns
                    ]
                }

                class Result:
                    text = json.dumps(payload)
                    usage = {"input_tokens": 100, "output_tokens": 80}
                    model = "claude-sonnet-4-6"

                return Result()

        user = CustomUser.objects.create_user(username="test-http-feedback-budget", password="test-pass")
        attempt = SpeakingAttempt.objects.create(user=user, attempt_id="test-http-feedback-budget", mode="p1", part="p1")
        turns = [
            SpeakingTurn.objects.create(
                user=user,
                attempt=attempt,
                turn_id=f"http-budget-turn-{index}",
                sequence=index,
                part="p1",
                question=f"Question {index + 1}?",
                transcript_raw=f"Answer {index + 1}.",
                transcript_cleaned=f"Answer {index + 1}.",
                metadata={"status": "completed"},
            )
            for index in range(4)
        ]
        provider = CapturingHttpProvider()

        with patch("apps.speaking.services._speaking_http_provider", return_value=provider):
            result = turn_feedback_batch_with_codex(
                turns,
                attempt,
                "7",
                {},
                "http-feedback-budget-test",
                ai_source="claude",
            )

        self.assertEqual(len(result), 4)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(provider.calls[0]["max_tokens"], services.SPEAKING_TURN_FEEDBACK_HTTP_MAX_TOKENS)
        self.assertFalse(provider.calls[0]["stream"])

    def test_sonnet_turn_feedback_uses_one_nonstream_json_request_with_exact_turn_ids(self):
        from apps.accounts.models import CustomUser
        from apps.speaking.services import turn_feedback_batch_with_codex

        class CapturingHttpProvider:
            def __init__(self):
                self.messages = []
                self.kwargs = []

            def complete_chat(self, messages, **kwargs):
                self.messages.append(messages)
                self.kwargs.append(kwargs)
                input_turns = json.loads(messages[1]["content"].split("Input turns:\n", 1)[1].strip())
                payload = {
                    "turns": [
                        {
                            "turn_id": item["turn_id"],
                            "display_transcript": item["candidate_transcript"],
                            "display_transcript_markdown": item["candidate_transcript"],
                            "band7_version": f"A complete model answer for {item['question']}",
                            "ai_coaching": "",
                        }
                        for item in input_turns
                    ]
                }

                class Result:
                    text = json.dumps(payload)
                    usage = {"input_tokens": 100, "output_tokens": 80}
                    model = "claude-sonnet-4-6"

                return Result()

        user = CustomUser.objects.create_user(username="test-sonnet-single-report", password="test-pass")
        attempt = SpeakingAttempt.objects.create(user=user, attempt_id="test-sonnet-single-report", mode="p1", part="p1")
        turns = [
            SpeakingTurn.objects.create(
                user=user,
                attempt=attempt,
                turn_id=f"sonnet-turn-{index}",
                sequence=index,
                part="p1",
                question=f"Question {index + 1}?",
                transcript_raw=f"Answer {index + 1}.",
                transcript_cleaned=f"Answer {index + 1}.",
                metadata={"status": "completed"},
            )
            for index in range(14)
        ]
        provider = CapturingHttpProvider()

        with patch("apps.speaking.services._speaking_http_provider", return_value=provider):
            result = turn_feedback_batch_with_codex(
                turns,
                attempt,
                "7",
                {},
                "sonnet-single-report",
                ai_source="claude",
            )

        self.assertEqual(len(result), 14)
        self.assertEqual(len(provider.messages), 1)
        self.assertFalse(provider.kwargs[0]["stream"])
        self.assertEqual(provider.kwargs[0]["response_format"], {"type": "json_object"})
        self.assertIn(
            'Required turn IDs in exact order: ["sonnet-turn-0", "sonnet-turn-1", "sonnet-turn-2"',
            provider.messages[0][1]["content"],
        )
        self.assertIn("Large-batch output budget (mandatory):", provider.messages[0][1]["content"])

    def test_http_turn_feedback_failure_never_calls_codex(self):
        from apps.accounts.models import CustomUser
        from apps.speaking.services import turn_feedback_batch_with_codex

        class FailingHttpProvider:
            def complete_chat(self, *args, **kwargs):
                raise RuntimeError("relay unavailable")

        user = CustomUser.objects.create_user(username="test-http-codex-fallback-batches", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="test-http-codex-fallback-batches",
            mode="p1",
            part="p1",
        )
        turns = [
            SpeakingTurn.objects.create(
                user=user,
                attempt=attempt,
                turn_id=f"fallback-batch-turn-{index}",
                sequence=index,
                part="p1",
                question=f"Question {index + 1}?",
                transcript_raw="",
                metadata={"status": "completed"},
            )
            for index in range(4)
        ]

        with (
            patch("apps.speaking.services._speaking_http_provider", return_value=FailingHttpProvider()),
            patch("apps.speaking.services.run_codex") as run_codex,
        ):
            with self.assertRaisesRegex(RuntimeError, "relay unavailable"):
                turn_feedback_batch_with_codex(
                    turns,
                    attempt,
                    "7",
                    {},
                    "http-no-codex-fallback-batch-test",
                )

        run_codex.assert_not_called()

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
            "examiner_"
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

    @override_settings(
        AI_HTTP_BASE_URL="https://ai.example/v1",
        AI_HTTP_API_KEY="test-key",
        SPEAKING_FOLLOWUP_AI_CALL_MODE="chain",
        SPEAKING_FOLLOWUP_AI_MODEL="gpt-5.4-mini",
    )
    def test_streamed_p1_followup_fails_without_fallback_when_http_stream_fails(self):
        # Spec: follow-ups use the GPT/HTTP provider only. When it fails, the stream
        # must emit `failed` with an empty question (frontend shows "点击重录") and must
        # NOT fabricate a codex or canned follow-up dressed up as the AI's question.
        from apps.speaking.services import stream_follow_up_sse_events
        from apps.accounts.models import CustomUser

        class FailingStreamProvider:
            def stream_tokens(self, *args, **kwargs):
                raise RuntimeError("401 invalid token")

            def complete_chat(self, *args, **kwargs):
                raise RuntimeError("401 invalid token")

        user = CustomUser.objects.create_user(username="test-p1-sse-fallback-user", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="test-p1-sse-fallback-attempt",
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
            transcript_raw="I study software engineering and I am also doing an internship.",
            transcript_cleaned="I study software engineering and I am also doing an internship.",
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
            patch("apps.speaking.services._speaking_http_provider", return_value=FailingStreamProvider()),
            patch("apps.speaking.services.run_codex") as run_codex_mock,
            patch("apps.speaking.services._generate_streamed_follow_up_tts") as generate_tts,
        ):
            raw_events = list(stream_follow_up_sse_events(user, "test-p1-sse-fallback-attempt", "t2"))

        events = [
            json.loads(item.removeprefix("data: ").strip())
            for item in raw_events
            if item.startswith("data: ")
        ]
        self.assertTrue(any(event["event"] == "failed" for event in events))
        self.assertFalse(any(event["event"] == "question_complete" for event in events))
        run_codex_mock.assert_not_called()
        generate_tts.assert_not_called()
        failed_event = next(event for event in events if event["event"] == "failed")
        self.assertEqual(failed_event["backend"], "stream_failed")

        target_turn = SpeakingTurn.objects.get(attempt=attempt, turn_id="t2_followup")
        self.assertEqual(target_turn.question, "")
        self.assertEqual(target_turn.metadata["prompt"]["backend"], "stream_failed")
        self.assertEqual(target_turn.metadata["prompt"]["generation_status"], "failed")
