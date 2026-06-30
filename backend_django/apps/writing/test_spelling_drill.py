import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.writing.models import SpellingDrillDailyBatch, SpellingDrillWord, WritingEntry, WritingPrompt, WritingScore
from apps.writing.spelling_services import (
    SRS_REVIEW_TIMEZONE,
    harvest_spelling_words,
    record_spelling_attempt,
    review_day_start,
    spelling_drill_library,
    update_spelling_word,
)


class SpellingDrillTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="spelling-user", password="test-pass")
        self.prompt = WritingPrompt.objects.create(
            prompt_id="spelling-task2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Technology",
            prompt="Some people think technology improves education. Discuss both views.",
        )

    def create_score(self, *, answer: str, analysis_payload: dict, user=None) -> WritingScore:
        entry = WritingEntry.objects.create(
            user=user or self.user,
            entry_id=uuid.uuid4().hex,
            prompt=self.prompt,
            task_type=self.prompt.task_type,
            practice_date=timezone.localdate(),
            title=self.prompt.title,
            prompt_text=self.prompt.prompt,
            answer=answer,
            word_count=len(answer.split()),
            status=WritingEntry.Status.SCORED,
            saved_at=timezone.now(),
        )
        return WritingScore.objects.create(
            user=entry.user,
            entry=entry,
            overall_band=6.0,
            source="ai",
            analysis_payload=analysis_payload,
            scored_at=timezone.now(),
        )

    def aware_at(self, year: int, month: int, day: int, hour: int, minute: int = 0):
        return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("UTC"))

    def review_local(self, value):
        return timezone.localtime(value, SRS_REVIEW_TIMEZONE)

    def test_harvest_collects_inline_and_summary_words(self):
        self.create_score(
            answer="I watched many vidios online. The classes were confortable.",
            analysis_payload={
                "inline_annotations": [
                    {
                        "type": "spelling",
                        "original": "confortable",
                        "suggestion": "comfortable",
                        "explanation": "应拼为 comfortable。",
                        "paragraph_index": 1,
                    }
                ],
                "spelling_correction_summary": "- vidios -> 正确：videos（视频）",
            },
        )

        changed = harvest_spelling_words(self.user)
        self.assertEqual(changed, 2)
        comfortable = SpellingDrillWord.objects.get(user=self.user, normalized="comfortable")
        videos = SpellingDrillWord.objects.get(user=self.user, normalized="videos")
        self.assertEqual(comfortable.wrong_forms, ["confortable"])
        self.assertEqual(comfortable.explanation, "应拼为 comfortable。")
        self.assertTrue(comfortable.examples[0]["snippet"])
        self.assertEqual(videos.chinese_gloss, "视频")

    def test_harvest_filters_phrases_noise_and_merges_wrong_forms(self):
        self.create_score(
            answer="I saw vidios and viedos in class.",
            analysis_payload={
                "inline_annotations": [
                    {"type": "spelling", "original": "bad phrase", "suggestion": "good phrase"},
                    {"type": "spelling", "original": "viedos", "suggestion": "videos"},
                    {"type": "word_choice", "original": "basic", "suggestion": "simple"},
                ],
                "spelling_correction_summary": "\n".join([
                    "- vidios -> 正确：videos（视频）",
                    "- 123 -> 正确：videos（视频）",
                    "- weak idea -> 正确：clear idea（表达）",
                ]),
            },
        )

        harvest_spelling_words(self.user)
        words = list(SpellingDrillWord.objects.filter(user=self.user))
        self.assertEqual(len(words), 1)
        word = words[0]
        self.assertEqual(word.normalized, "videos")
        self.assertCountEqual(word.wrong_forms, ["viedos", "vidios"])
        self.assertEqual(word.occurrence_count, 2)

    def test_harvest_is_idempotent_and_preserves_progress(self):
        self.create_score(
            answer="This app is confortable.",
            analysis_payload={
                "inline_annotations": [
                    {"type": "spelling", "original": "confortable", "suggestion": "comfortable"},
                ],
            },
        )

        harvest_spelling_words(self.user)
        word = SpellingDrillWord.objects.get(user=self.user, normalized="comfortable")
        word.current_streak = 3
        word.status = SpellingDrillWord.Status.MASTERED
        word.attempt_count = 5
        word.correct_count = 4
        word.save()

        changed = harvest_spelling_words(self.user)
        word.refresh_from_db()
        self.assertEqual(changed, 0)
        self.assertEqual(word.occurrence_count, 1)
        self.assertEqual(word.current_streak, 3)
        self.assertEqual(word.status, SpellingDrillWord.Status.MASTERED)
        self.assertEqual(word.attempt_count, 5)
        self.assertEqual(word.correct_count, 4)

    def test_attempt_srs_scheduling_correct_and_wrong(self):
        self.create_score(
            answer="This app is confortable.",
            analysis_payload={"inline_annotations": [{"type": "spelling", "original": "confortable", "suggestion": "comfortable", "explanation": "拼写错误"}]},
        )
        harvest_spelling_words(self.user)
        word = SpellingDrillWord.objects.get(user=self.user, normalized="comfortable")
        self.assertEqual(word.review_stage, 0)

        # Wrong attempt: stage resets to 0, lapses increments, and the word
        # returns on the next 04:00 review refresh, not 24 hours later.
        now = self.aware_at(2026, 6, 7, 10, 30)
        with patch("apps.writing.spelling_services.timezone.now", return_value=now):
            wrong = record_spelling_attempt(self.user, word.word_id, "comfortble")
        self.assertFalse(wrong["correct"])
        self.assertEqual(wrong["correct_spelling"], "comfortable")
        word.refresh_from_db()
        self.assertEqual(word.current_streak, 0)
        self.assertEqual(word.review_stage, 0)
        self.assertEqual(word.lapses, 1)
        self.assertEqual(wrong["next_due_human"], "明天")
        self.assertEqual(
            self.review_local(word.due_at),
            self.review_local(now).replace(hour=4, minute=0, second=0, microsecond=0) + timedelta(days=1),
        )
        self.assertIn("next_due_human", wrong)

        # Four correct answers → stage 4 → mastered
        for typed in [" Comfortable ", "comfortable", "COMFORTABLE", "comfortable"]:
            result = record_spelling_attempt(self.user, word.word_id, typed)
        word.refresh_from_db()
        self.assertTrue(result["correct"])
        self.assertEqual(word.review_stage, 4)
        self.assertEqual(word.status, SpellingDrillWord.Status.MASTERED)
        self.assertEqual(word.attempt_count, 5)  # 1 wrong + 4 correct
        self.assertEqual(word.correct_count, 4)
        self.assertIn("next_due_human", result)

    def test_blank_attempt_counts_as_wrong_answer(self):
        self.create_score(
            answer="This app is confortable.",
            analysis_payload={"inline_annotations": [{"type": "spelling", "original": "confortable", "suggestion": "comfortable"}]},
        )
        harvest_spelling_words(self.user)
        word = SpellingDrillWord.objects.get(user=self.user, normalized="comfortable")

        result = record_spelling_attempt(self.user, word.word_id, "")

        self.assertFalse(result["correct"])
        self.assertEqual(result["correct_spelling"], "comfortable")
        word.refresh_from_db()
        self.assertEqual(word.attempt_count, 1)
        self.assertEqual(word.correct_count, 0)
        self.assertEqual(word.current_streak, 0)
        self.assertEqual(word.lapses, 1)
        self.assertEqual(word.status, SpellingDrillWord.Status.ACTIVE)

    def test_wrong_attempt_before_four_am_returns_at_same_calendar_day_refresh(self):
        self.create_score(
            answer="This app is confortable.",
            analysis_payload={"inline_annotations": [{"type": "spelling", "original": "confortable", "suggestion": "comfortable"}]},
        )
        harvest_spelling_words(self.user)
        word = SpellingDrillWord.objects.get(user=self.user, normalized="comfortable")
        now = self.aware_at(2026, 6, 6, 19, 30)

        with patch("apps.writing.spelling_services.timezone.now", return_value=now):
            record_spelling_attempt(self.user, word.word_id, "comfortble")

        word.refresh_from_db()
        self.assertEqual(
            self.review_local(word.due_at),
            self.review_local(now).replace(hour=4, minute=0, second=0, microsecond=0),
        )

    def test_review_day_uses_china_four_am_not_utc_four_am(self):
        before_china_refresh = self.aware_at(2026, 6, 11, 19, 30)
        after_china_refresh = self.aware_at(2026, 6, 11, 20, 30)

        self.assertEqual(review_day_start(before_china_refresh).date().isoformat(), "2026-06-11")
        self.assertEqual(review_day_start(after_china_refresh).date().isoformat(), "2026-06-12")
        self.assertEqual(review_day_start(after_china_refresh).hour, 4)

    def test_due_scope_is_frozen_to_four_am_batch(self):
        now = self.aware_at(2026, 6, 7, 10, 30)
        with patch("apps.writing.spelling_services.timezone.now", return_value=now):
            self.create_score(
                answer="This app is confortable.",
                analysis_payload={"inline_annotations": [{"type": "spelling", "original": "confortable", "suggestion": "comfortable"}]},
            )
            harvest_spelling_words(self.user)
            today = spelling_drill_library(self.user, scope="due")

        self.assertEqual(today["count"], 0)
        word = SpellingDrillWord.objects.get(user=self.user, normalized="comfortable")
        self.assertGreater(timezone.localtime(word.due_at), timezone.localtime(now).replace(hour=4, minute=0, second=0, microsecond=0))

        next_batch = self.aware_at(2026, 6, 8, 4, 1)
        with patch("apps.writing.spelling_services.timezone.now", return_value=next_batch):
            tomorrow = spelling_drill_library(self.user, scope="due")
        self.assertEqual(tomorrow["count"], 1)
        self.assertEqual(tomorrow["items"][0]["correct_spelling"], "comfortable")

    def test_due_scope_freezes_existing_batch_and_excludes_same_day_harvest(self):
        now = self.aware_at(2026, 6, 7, 10, 30)
        with patch("apps.writing.spelling_services.timezone.now", return_value=now):
            old_word = SpellingDrillWord.objects.create(
                user=self.user,
                word_id="sp:old",
                correct_spelling="comfortable",
                normalized="comfortable",
                wrong_forms=["confortable"],
                first_seen_at=now - timedelta(days=3),
                last_seen_at=now - timedelta(days=3),
                due_at=now.replace(hour=4, minute=0, second=0, microsecond=0),
                status=SpellingDrillWord.Status.ACTIVE,
            )
            first = spelling_drill_library(self.user, scope="due")
            self.create_score(
                answer="I watched many vidios online.",
                analysis_payload={"spelling_correction_summary": "- vidios -> 正确：videos（视频）"},
            )
            harvest_spelling_words(self.user)
            second = spelling_drill_library(self.user, scope="due")

        self.assertEqual([item["word_id"] for item in first["items"]], [old_word.word_id])
        self.assertEqual([item["word_id"] for item in second["items"]], [old_word.word_id])
        self.assertEqual(second["stats"]["due"], 1)
        self.assertTrue(SpellingDrillWord.objects.filter(user=self.user, normalized="videos").exists())

        next_batch = self.aware_at(2026, 6, 8, 4, 1)
        with patch("apps.writing.spelling_services.timezone.now", return_value=next_batch):
            tomorrow = spelling_drill_library(self.user, scope="due")

        tomorrow_words = {item["correct_spelling"] for item in tomorrow["items"]}
        self.assertIn("videos", tomorrow_words)

    def test_attempt_removes_word_from_today_batch_without_second_wave(self):
        now = self.aware_at(2026, 6, 7, 10, 30)
        with patch("apps.writing.spelling_services.timezone.now", return_value=now):
            word = SpellingDrillWord.objects.create(
                user=self.user,
                word_id="sp:due",
                correct_spelling="comfortable",
                normalized="comfortable",
                wrong_forms=["confortable"],
                first_seen_at=now - timedelta(days=3),
                last_seen_at=now - timedelta(days=3),
                due_at=now.replace(hour=4, minute=0, second=0, microsecond=0),
                status=SpellingDrillWord.Status.ACTIVE,
            )
            before = spelling_drill_library(self.user, scope="due")
            result = record_spelling_attempt(self.user, word.word_id, "comfortble")
            after = spelling_drill_library(self.user, scope="due")

        self.assertEqual(before["stats"]["due"], 1)
        self.assertFalse(result["correct"])
        self.assertEqual(after["items"], [])
        self.assertEqual(after["stats"]["due"], 0)
        word.refresh_from_db()
        self.assertEqual(word.status, SpellingDrillWord.Status.ACTIVE)
        self.assertEqual(word.review_stage, 0)
        self.assertEqual(
            self.review_local(word.due_at),
            self.review_local(now).replace(hour=4, minute=0, second=0, microsecond=0) + timedelta(days=1),
        )
        batch = SpellingDrillDailyBatch.objects.get(user=self.user, review_day=now.date())
        self.assertEqual(batch.word_ids, [word.word_id])

    def test_empty_today_batch_reopens_when_due_words_exist_after_timezone_fix(self):
        now = self.aware_at(2026, 6, 11, 23, 30)
        word = SpellingDrillWord.objects.create(
            user=self.user,
            word_id="sp:late",
            correct_spelling="probability",
            normalized="probability",
            wrong_forms=["probablity"],
            first_seen_at=now - timedelta(days=3),
            last_seen_at=now - timedelta(days=3),
            due_at=now.replace(hour=4, minute=0, second=0, microsecond=0),
            status=SpellingDrillWord.Status.ACTIVE,
        )
        SpellingDrillDailyBatch.objects.create(user=self.user, review_day=review_day_start(now).date(), word_ids=[])

        with patch("apps.writing.spelling_services.timezone.now", return_value=now):
            library = spelling_drill_library(self.user, scope="due")

        self.assertEqual(library["stats"]["due"], 1)
        self.assertEqual(library["items"][0]["word_id"], word.word_id)
        batch = SpellingDrillDailyBatch.objects.get(user=self.user, review_day=review_day_start(now).date())
        self.assertEqual(batch.word_ids, [word.word_id])

    def test_mastered_words_follow_srs_and_lapse_back_to_active(self):
        self.create_score(
            answer="I watched vidios online.",
            analysis_payload={"spelling_correction_summary": "- vidios -> 正确：videos（视频）"},
        )
        harvest_spelling_words(self.user)
        word = SpellingDrillWord.objects.get(user=self.user, normalized="videos")
        word.status = SpellingDrillWord.Status.MASTERED
        word.review_stage = 4
        due_time = self.aware_at(2026, 6, 7, 4, 0)
        word.due_at = due_time
        word.metadata = {"mastered_review_level": 0}
        word.save(update_fields=["status", "review_stage", "due_at", "metadata", "updated_at"])

        review_time = self.aware_at(2026, 6, 7, 10, 30)
        with patch("apps.writing.spelling_services.timezone.now", return_value=review_time):
            library = spelling_drill_library(self.user, scope="due")
            correct = record_spelling_attempt(self.user, word.word_id, "videos")
        self.assertEqual(library["count"], 1)
        self.assertTrue(correct["correct"])
        word.refresh_from_db()
        self.assertEqual(word.status, SpellingDrillWord.Status.MASTERED)
        self.assertEqual(word.review_stage, 4)
        self.assertEqual(word.metadata["mastered_review_level"], 1)
        self.assertEqual(
            self.review_local(word.due_at),
            self.review_local(review_time).replace(hour=4, minute=0, second=0, microsecond=0) + timedelta(days=14),
        )

        with patch("apps.writing.spelling_services.timezone.now", return_value=review_time):
            wrong = record_spelling_attempt(self.user, word.word_id, "vidios")
        self.assertFalse(wrong["correct"])
        word.refresh_from_db()
        self.assertEqual(word.status, SpellingDrillWord.Status.ACTIVE)
        self.assertEqual(word.review_stage, 3)
        self.assertEqual(word.metadata["mastered_review_level"], 0)
        self.assertEqual(
            self.review_local(word.due_at),
            self.review_local(review_time).replace(hour=4, minute=0, second=0, microsecond=0) + timedelta(days=1),
        )

    def test_update_edit_gloss_reset_master_and_delete(self):
        self.create_score(
            answer="I watched vidios online.",
            analysis_payload={"spelling_correction_summary": "- vidios -> 正确：videos（视频）"},
        )
        harvest_spelling_words(self.user)
        word = SpellingDrillWord.objects.get(user=self.user, normalized="videos")

        update_spelling_word(self.user, word.word_id, {"action": "edit_gloss", "chinese_gloss": "影片"})
        harvest_spelling_words(self.user)
        word.refresh_from_db()
        self.assertEqual(word.chinese_gloss, "影片")
        self.assertTrue(word.metadata["gloss_edited"])

        update_spelling_word(self.user, word.word_id, {"action": "master"})
        word.refresh_from_db()
        self.assertEqual(word.status, SpellingDrillWord.Status.MASTERED)
        self.assertEqual(word.review_stage, 4)
        self.assertEqual(word.metadata["mastered_review_level"], 0)
        self.assertGreater(word.due_at, timezone.now())

        update_spelling_word(self.user, word.word_id, {"action": "reset"})
        word.refresh_from_db()
        self.assertEqual(word.status, SpellingDrillWord.Status.ACTIVE)
        self.assertEqual(word.current_streak, 0)

        client = Client()
        client.force_login(self.user)
        response = client.delete(f"/api/writing/spelling-words/{word.word_id}")
        self.assertEqual(response.status_code, 200)
        word.refresh_from_db()
        self.assertEqual(word.status, SpellingDrillWord.Status.DISMISSED)
        library = spelling_drill_library(self.user, scope="all")
        self.assertEqual(library["count"], 0)

    def test_api_auth_routes_and_owner_scope(self):
        self.create_score(
            answer="This app is confortable.",
            analysis_payload={"inline_annotations": [{"type": "spelling", "original": "confortable", "suggestion": "comfortable"}]},
        )
        anonymous = Client()
        self.assertEqual(anonymous.get("/api/writing/spelling-words").status_code, 401)

        client = Client()
        client.force_login(self.user)
        library_response = client.get("/api/writing/spelling-words?scope=active")
        self.assertEqual(library_response.status_code, 200)
        item = library_response.json()["items"][0]
        word_id = item["word_id"]

        attempt = client.post(
            f"/api/writing/spelling-words/{word_id}/attempt",
            data=json.dumps({"typed": "comfortable"}),
            content_type="application/json",
        )
        self.assertEqual(attempt.status_code, 200)
        self.assertTrue(attempt.json()["correct"])

        patch = client.patch(
            f"/api/writing/spelling-words/{word_id}",
            data=json.dumps({"action": "master"}),
            content_type="application/json",
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.json()["status"], SpellingDrillWord.Status.MASTERED)

        method_not_allowed = client.post(
            f"/api/writing/spelling-words/{word_id}",
            data=json.dumps({"action": "reset"}),
            content_type="application/json",
        )
        self.assertEqual(method_not_allowed.status_code, 405)

        other = get_user_model().objects.create_user(username="other-spelling", password="test-pass")
        other_client = Client()
        other_client.force_login(other)
        other_attempt = other_client.post(
            f"/api/writing/spelling-words/{word_id}/attempt",
            data=json.dumps({"typed": "comfortable"}),
            content_type="application/json",
        )
        self.assertEqual(other_attempt.status_code, 404)
