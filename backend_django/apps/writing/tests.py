import json
import time
import uuid
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.ai.models import AITask
from apps.ai.orchestration import cancel_billable_ai_task
from apps.ai.services import claim_ai_task
from apps.billing.models import TokenWallet, WalletLedgerEntry
from apps.billing.services import DEFAULT_INITIAL_GRANT_U
from apps.writing.models import WritingEntry, WritingFrameTemplate, WritingLearnerProfile, WritingPrompt, WritingScore
from apps.writing.services import WRITING_TASK_LABELS, WritingError, complete_score_task, fallback_score_task, ielts_overall_band


def paragraph_answer(*parts: str) -> str:
    return "\n\n".join(parts)


class IeltsOverallBandTests(TestCase):
    def test_overall_is_average_of_four_criteria_rounded_half_up(self):
        # The real "Clean Water" case: TR7.5 / CC8 / LR8 / GRA8 averages to 7.875,
        # which must round UP to 8.0 (was incorrectly stored as 7.5).
        self.assertEqual(ielts_overall_band(7.5, 8.0, 8.0, 8.0), 8.0)
        # Uniform scores stay put.
        self.assertEqual(ielts_overall_band(6.0, 6.0, 6.0, 6.0), 6.0)
        # .25 average rounds up to .5 鈥?Python's banker's round() would wrongly
        # give 7.0 here, so this guards the half-up rule.
        self.assertEqual(ielts_overall_band(7.5, 7.5, 7.0, 7.0), 7.5)  # mean 7.25
        # .75 average rounds up to the next whole band.
        self.assertEqual(ielts_overall_band(8.0, 8.0, 7.5, 7.5), 8.0)  # mean 7.75
        # Below the midpoint rounds down.
        self.assertEqual(ielts_overall_band(6.5, 6.5, 6.5, 7.0), 6.5)  # mean 6.625


def ai_score_payload(*, paragraph_reviews: list[dict] | None = None, **overrides):
    payload = {
        "overall_band": 6.0,
        "task_response": 6.0,
        "coherence_cohesion": 6.0,
        "lexical_resource": 6.0,
        "grammatical_range_accuracy": 6.0,
        "feedback_markdown": "- Clear position with room for more examples.",
        "grammar_corrections": [],
        "inline_annotations": [],
        "spelling_correction_summary": "No obvious spelling errors.",
        "expression_upgrade_summary": "- Use more precise academic collocations.",
        "overall_review": "AI overall review generated from the essay logic.",
        "practice_focus": "AI practice focus generated from the weakest paragraph-level issue.",
        "model_answer": "AI rewrite paragraph one.\n\nAI rewrite paragraph two.",
        "paragraph_reviews": paragraph_reviews
        or [
            {
                "index": 1,
                "learner": "Online learning can be useful because students can review lessons at any time.",
                "model": "AI rewrite paragraph one.",
                "coaching": "AI explains how this paragraph works logically.",
                "language_correction_upgrade": "- Check article use in this paragraph.",
            },
            {
                "index": 2,
                "learner": "However, classrooms still provide direct support and immediate interaction.",
                "model": "AI rewrite paragraph two.",
                "coaching": "AI explains how this paragraph should develop the contrast.",
            },
        ],
        "structure_advice_only": False,
        "structure_advice": "",
        "backend": "ai",
    }
    payload.update(overrides)
    return payload


class WritingModelTests(TestCase):
    def test_entry_and_score_can_be_created(self):
        user = get_user_model().objects.create_user(username="writer", password="test-pass")
        prompt = WritingPrompt.objects.create(
            prompt_id="task2-test",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Technology and education",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = WritingEntry.objects.create(
            user=user,
            prompt=prompt,
            task_type=WritingPrompt.TaskType.TASK2,
            practice_date=timezone.localdate(),
            title=prompt.title,
            prompt_text=prompt.prompt,
            answer="Technology can make education more flexible.",
            word_count=7,
        )
        score = WritingScore.objects.create(user=user, entry=entry, overall_band=6.0, source="fallback")

        self.assertEqual(entry.status, WritingEntry.Status.SAVED)
        self.assertEqual(score.entry, entry)

    def test_writing_learner_profile_can_store_personalization_state(self):
        user = get_user_model().objects.create_user(username="profile-writer", password="test-pass")
        profile = WritingLearnerProfile.objects.create(
            user=user,
            total_scored=2,
            task_counts={"task2": 2},
            average_overall_band=5.25,
            tag_counts={"under_length": 1, "grammar_accuracy": 2},
            primary_focus="grammar_accuracy",
            primary_focus_text="Sentence structure and grammar accuracy are the current focus.",
            recent_evidence=["Task 2 路 Band 5.0 路 120 words"],
        )

        self.assertEqual(profile.total_scored, 2)
        self.assertEqual(profile.tag_counts["grammar_accuracy"], 2)


class WritingApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="writing-api-user", password="test-pass")
        self.client.force_login(self.user)

    def create_prompt(
        self,
        *,
        prompt_id: str,
        task_type: str,
        title: str,
        prompt: str,
        image_url: str = "",
        category: str = "",
        source_book: int | None = None,
        source_test: int | None = None,
        source_question: int | None = None,
        source: str = "local_seed",
    ) -> WritingPrompt:
        return WritingPrompt.objects.create(
            prompt_id=prompt_id,
            task_type=task_type,
            title=title,
            prompt=prompt,
            image_url=image_url,
            category=category,
            source_book=source_book,
            source_test=source_test,
            source_question=source_question,
            source=source,
        )

    def create_entry(
        self,
        *,
        user=None,
        prompt: WritingPrompt,
        answer: str,
        status: str = WritingEntry.Status.SAVED,
        practice_date=None,
        title: str | None = None,
        overall_band: float | None = None,
        updated_at=None,
    ) -> WritingEntry:
        entry = WritingEntry.objects.create(
            user=user or self.user,
            entry_id=uuid.uuid4().hex,
            prompt=prompt,
            task_type=prompt.task_type,
            practice_date=practice_date or timezone.localdate(),
            title=title or prompt.title,
            prompt_text=prompt.prompt,
            answer=answer,
            word_count=len(answer.split()),
            status=status,
            saved_at=timezone.now(),
            metadata={"category": prompt.category},
        )
        if overall_band is not None:
            WritingScore.objects.create(
                user=entry.user,
                entry=entry,
                overall_band=overall_band,
                task_response=overall_band,
                coherence_cohesion=overall_band,
                lexical_resource=overall_band,
                grammar_range_accuracy=overall_band,
                feedback_markdown="- Stored score.",
                source="ai",
            )
        if updated_at is not None:
            WritingEntry.objects.filter(pk=entry.pk).update(updated_at=updated_at)
            entry.refresh_from_db()
        return entry

    def test_writing_frames_are_persisted_per_user(self):
        other_user = get_user_model().objects.create_user(username="other-frame-user", password="test-pass")
        WritingFrameTemplate.objects.create(
            user=other_user,
            frame_key="task2:agree_disagree",
            template_text="Other user's frame",
        )

        response = self.client.put(
            "/api/writing/frames",
            data=json.dumps({
                "frame_key": "task2:agree_disagree",
                "template_text": "My custom public-cloud frame",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["template_text"], "My custom public-cloud frame")

        response = self.client.get("/api/writing/frames")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["frame_key"], "task2:agree_disagree")
        self.assertEqual(items[0]["template_text"], "My custom public-cloud frame")
        self.assertTrue(items[0]["updated_at"])
        self.assertEqual(WritingFrameTemplate.objects.filter(user=other_user).count(), 1)

    def assert_entry_detail_contract(
        self,
        detail: dict,
        *,
        entry_id: str,
        prompt_id: str,
        task_type: str,
        word_count: int,
        ai_task_status: str,
        score_backend: str | None = None,
    ) -> None:
        self.assertEqual(detail["id"], entry_id)
        self.assertEqual(detail["prompt_id"], prompt_id)
        self.assertEqual(detail["task_type"], task_type)
        self.assertEqual(detail["word_count"], word_count)
        self.assertIsNotNone(detail["ai_task"])
        self.assertEqual(detail["ai_task"]["task_type"], "writing_score")
        self.assertEqual(detail["ai_task"]["status"], ai_task_status)
        self.assertEqual(detail["ai_task"]["related_type"], "writing_entry")
        self.assertEqual(detail["ai_task"]["related_id"], entry_id)
        self.assertEqual(detail["ai_task"]["request_payload"]["entry_id"], entry_id)
        self.assertEqual(detail["ai_task"]["request_payload"]["prompt_id"], prompt_id)
        self.assertEqual(detail["ai_task"]["request_payload"]["task_type"], task_type)
        if score_backend is None:
            self.assertIsNone(detail["score"])
            return
        self.assertIsNotNone(detail["score"])
        self.assertEqual(detail["score"]["backend"], score_backend)

    def test_writing_api_requires_login(self):
        self.client.logout()
        response = self.client.get("/api/writing/summary")
        self.assertEqual(response.status_code, 401)

    def test_writing_reports_requires_login(self):
        self.client.logout()
        response = self.client.get("/api/writing/reports")
        self.assertEqual(response.status_code, 401)

    def test_delete_writing_entry_requires_login(self):
        prompt = self.create_prompt(
            prompt_id="task2-delete-login",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Delete login prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(prompt=prompt, answer="Paragraph one.\n\nParagraph two.")
        self.client.logout()
        response = self.client.delete(f"/api/writing/entries/{entry.entry_id}")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(WritingEntry.objects.filter(entry_id=entry.entry_id).exists())

    def test_delete_writing_entry_is_owner_scoped(self):
        prompt = self.create_prompt(
            prompt_id="task2-delete-owner",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Delete owner prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(prompt=prompt, answer="Paragraph one.\n\nParagraph two.")
        other_user = get_user_model().objects.create_user(username="other-writing-delete", password="test-pass")
        self.client.logout()
        self.client.force_login(other_user)
        response = self.client.delete(f"/api/writing/entries/{entry.entry_id}")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(WritingEntry.objects.filter(entry_id=entry.entry_id).exists())

    def test_delete_writing_entry_removes_score_and_report_item(self):
        prompt = self.create_prompt(
            prompt_id="task2-delete-scored",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Delete scored prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer="Paragraph one.\n\nParagraph two.",
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )
        self.assertTrue(WritingScore.objects.filter(entry=entry).exists())
        before = self.client.get("/api/writing/reports").json()
        self.assertIn(entry.entry_id, [item["id"] for item in before["items"]])

        response = self.client.delete(f"/api/writing/entries/{entry.entry_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertFalse(WritingEntry.objects.filter(entry_id=entry.entry_id).exists())
        self.assertFalse(WritingScore.objects.filter(entry_id=entry.pk).exists())
        after = self.client.get("/api/writing/reports").json()
        self.assertNotIn(entry.entry_id, [item["id"] for item in after["items"]])

    def test_delete_writing_entry_cancels_pending_score_task(self):
        prompt = self.create_prompt(
            prompt_id="task2-delete-pending-task",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Delete pending task prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(prompt=prompt, answer="Paragraph one.\n\nParagraph two.")
        created = self.client.post(
            f"/api/writing/entries/{entry.entry_id}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        ).json()["task"]

        response = self.client.delete(f"/api/writing/entries/{entry.entry_id}")
        self.assertEqual(response.status_code, 200)
        task = AITask.objects.get(task_id=created["id"])
        self.assertEqual(task.status, AITask.Status.CANCELLED)
        self.assertEqual(task.error_code, "writing_entry_deleted")
        self.assertFalse(WritingEntry.objects.filter(entry_id=entry.entry_id).exists())

    def test_clone_scored_entry_for_revision_keeps_original_report(self):
        prompt = self.create_prompt(
            prompt_id="task2-clone-scored",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Clone scored prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Original paragraph one.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )

        response = self.client.post(f"/api/writing/entries/{entry.entry_id}/clone", content_type="application/json")

        self.assertEqual(response.status_code, 201)
        clone = response.json()
        self.assertNotEqual(clone["id"], entry.entry_id)
        self.assertEqual(clone["status"], WritingEntry.Status.SAVED)
        self.assertIsNone(clone["score"])
        self.assertEqual(clone["answer"], entry.answer)
        self.assertEqual(clone["prompt_id"], prompt.prompt_id)
        self.assertEqual(WritingScore.objects.filter(entry=entry).count(), 1)
        self.assertFalse(WritingScore.objects.filter(entry__entry_id=clone["id"]).exists())

    def test_clone_unscored_saved_entry_is_rejected_without_new_revision(self):
        prompt = self.create_prompt(
            prompt_id="task2-clone-unscored-saved",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Clone unscored saved prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Draft paragraph one.", "Draft paragraph two."),
            status=WritingEntry.Status.SAVED,
        )

        response = self.client.post(f"/api/writing/entries/{entry.entry_id}/clone", content_type="application/json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Only scored writing entries", response.json()["message"])
        self.assertEqual(WritingEntry.objects.filter(user=self.user, prompt=prompt).count(), 1)

    def test_clone_entry_with_scored_status_but_no_score_is_rejected(self):
        prompt = self.create_prompt(
            prompt_id="task2-clone-scored-status-without-score",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Clone scored status without score prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Draft paragraph one.", "Draft paragraph two."),
            status=WritingEntry.Status.SCORED,
        )

        response = self.client.post(f"/api/writing/entries/{entry.entry_id}/clone", content_type="application/json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Only scored writing entries", response.json()["message"])
        self.assertEqual(WritingEntry.objects.filter(user=self.user, prompt=prompt).count(), 1)

    def test_saving_changed_scored_entry_without_preserve_clears_report(self):
        prompt = self.create_prompt(
            prompt_id="task2-save-scored-revision",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Save scored revision prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Original paragraph one.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": entry.entry_id,
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer("Revised paragraph one.", "Revised paragraph two."),
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual(saved["id"], entry.entry_id)
        self.assertEqual(saved["status"], WritingEntry.Status.SAVED)
        self.assertIsNone(saved["score"])
        self.assertEqual(saved["answer"], "Revised paragraph one.\n\nRevised paragraph two.")
        entry.refresh_from_db()
        self.assertEqual(entry.answer, "Revised paragraph one.\n\nRevised paragraph two.")
        self.assertEqual(entry.status, WritingEntry.Status.SAVED)
        self.assertFalse(WritingScore.objects.filter(entry=entry).exists())

    def test_report_inline_save_can_preserve_existing_score(self):
        prompt = self.create_prompt(
            prompt_id="task2-save-scored-preserve",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Save scored preserve prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Original paragraph one.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": entry.entry_id,
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer("Edited paragraph one.", "Original paragraph two."),
                "preserve_score": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual(saved["id"], entry.entry_id)
        self.assertEqual(saved["status"], WritingEntry.Status.SCORED)
        self.assertIsNotNone(saved["score"])
        self.assertEqual(saved["answer"], "Edited paragraph one.\n\nOriginal paragraph two.")
        entry.refresh_from_db()
        self.assertEqual(entry.answer, "Edited paragraph one.\n\nOriginal paragraph two.")
        self.assertTrue(WritingScore.objects.filter(entry=entry, overall_band=6.0).exists())

    def test_save_same_prompt_without_id_reuses_existing_scored_report(self):
        prompt = self.create_prompt(
            prompt_id="task2-save-scored-same-prompt-no-id",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Save scored same prompt without id",
            prompt="Some people think competition is more important than cooperation. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Original paragraph one.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=7.5,
        )

        response = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer("Edited paragraph one.", "Original paragraph two."),
                "preserve_score": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual(saved["id"], entry.entry_id)
        self.assertEqual(saved["status"], WritingEntry.Status.SCORED)
        self.assertEqual(saved["score"]["overall_band"], 7.5)
        self.assertEqual(WritingEntry.objects.filter(user=self.user, prompt=prompt).count(), 1)
        entry.refresh_from_db()
        self.assertEqual(entry.answer, "Edited paragraph one.\n\nOriginal paragraph two.")

    def test_preserve_score_with_saved_duplicate_id_updates_scored_report(self):
        prompt = self.create_prompt(
            prompt_id="task2-save-scored-from-saved-duplicate-id",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Save scored from saved duplicate id",
            prompt="Some people think competition is more important than cooperation. Discuss both views.",
        )
        scored_entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Original paragraph one.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=7.5,
        )
        saved_duplicate = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Duplicate paragraph one.", "Duplicate paragraph two."),
            status=WritingEntry.Status.SAVED,
        )

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": saved_duplicate.entry_id,
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer("Fixed paragraph one.", "Original paragraph two."),
                "preserve_score": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual(saved["id"], scored_entry.entry_id)
        self.assertEqual(saved["status"], WritingEntry.Status.SCORED)
        self.assertEqual(saved["score"]["overall_band"], 7.5)
        scored_entry.refresh_from_db()
        saved_duplicate.refresh_from_db()
        self.assertEqual(scored_entry.answer, "Fixed paragraph one.\n\nOriginal paragraph two.")
        self.assertEqual(saved_duplicate.answer, "Duplicate paragraph one.\n\nDuplicate paragraph two.")

    def test_preserve_score_with_same_cambridge_source_updates_scored_report(self):
        scored_prompt = self.create_prompt(
            prompt_id="task2-save-source-scored",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Competition and cooperation scored prompt",
            prompt="Some people think competition is more important than cooperation. Discuss both views.",
            source_book=19,
            source_test=1,
            source_question=2,
        )
        duplicate_prompt = self.create_prompt(
            prompt_id="task2-save-source-duplicate",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Competition and cooperation duplicate prompt",
            prompt="Some people think competition is more important than cooperation. Discuss both views and give your opinion.",
            source_book=19,
            source_test=1,
            source_question=2,
        )
        scored_entry = self.create_entry(
            prompt=scored_prompt,
            answer=paragraph_answer("Original paragraph one.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=7.5,
        )
        saved_duplicate = self.create_entry(
            prompt=duplicate_prompt,
            answer=paragraph_answer("Duplicate paragraph one.", "Duplicate paragraph two."),
            status=WritingEntry.Status.SAVED,
        )

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": saved_duplicate.entry_id,
                "task_type": "task2",
                "prompt_id": duplicate_prompt.prompt_id,
                "prompt": duplicate_prompt.prompt,
                "answer": paragraph_answer("Fixed paragraph one.", "Original paragraph two."),
                "preserve_score": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], scored_entry.entry_id)
        self.assertEqual(payload["status"], WritingEntry.Status.SCORED)
        scored_entry.refresh_from_db()
        saved_duplicate.refresh_from_db()
        self.assertEqual(scored_entry.answer, "Fixed paragraph one.\n\nOriginal paragraph two.")
        self.assertEqual(saved_duplicate.answer, "Duplicate paragraph one.\n\nDuplicate paragraph two.")

    def test_preserved_report_keeps_reviews_for_edited_paragraph(self):
        prompt = self.create_prompt(
            prompt_id="task2-save-scored-clear-annotations",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Save scored clear annotations prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("The city has an increacing demand.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )
        score = WritingScore.objects.get(entry=entry)
        score.analysis_payload = {
            "analysis_backend": "ai",
            "inline_annotations": [
                {"paragraph_index": 1, "original": "increacing", "type": "spelling", "suggestion": "increasing", "explanation": "Spelling."},
                {"paragraph_index": 2, "original": "Original", "type": "word_choice", "suggestion": "Initial", "explanation": "Style."},
            ],
            "paragraph_reviews": [
                {"index": 1, "learner": "The city has an increacing demand.", "model": "Old model one.", "coaching": "Old coaching one.", "language_correction_upgrade": "Old upgrade."},
                {"index": 2, "learner": "Original paragraph two.", "model": "Old model two.", "coaching": "Old coaching two.", "language_correction_upgrade": ""},
            ],
        }
        score.save(update_fields=["analysis_payload", "updated_at"])

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": entry.entry_id,
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer("The city has an increasing demand.", "Original paragraph two."),
                "preserve_score": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], WritingEntry.Status.SCORED)
        annotations = payload["score"]["inline_annotations"]
        self.assertEqual([item["paragraph_index"] for item in annotations], [2])
        first_review = payload["score"]["paragraph_reviews"][0]
        self.assertEqual(first_review["learner"], "The city has an increasing demand.")
        self.assertEqual(first_review["model"], "Old model one.")
        self.assertEqual(first_review["coaching"], "Old coaching one.")
        self.assertEqual(first_review["language_correction_upgrade"], "Old upgrade.")

    def test_preserved_report_drops_only_the_edited_sentences_annotations(self):
        # Sentence-level invalidation: editing one sentence drops THAT sentence's
        # annotations; a different, untouched sentence in the same paragraph keeps its
        # annotation. Here the first sentence is fixed (increacing鈫抜ncreasing) so its
        # annotation goes, while "poor roads" in the untouched second sentence survives.
        prompt = self.create_prompt(
            prompt_id="task2-save-scored-keep-nearby-annotations",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Save scored keep nearby annotations prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("The city has an increacing demand. Roads here are poor roads.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )
        score = WritingScore.objects.get(entry=entry)
        score.analysis_payload = {
            "analysis_backend": "ai",
            "inline_annotations": [
                {"paragraph_index": 1, "original": "increacing", "type": "spelling", "suggestion": "increasing", "explanation": "Spelling."},
                {"paragraph_index": 1, "original": "poor roads", "type": "word_choice", "suggestion": "weak transport links", "explanation": "More precise."},
                {"paragraph_index": 2, "original": "Original", "type": "word_choice", "suggestion": "Initial", "explanation": "Style."},
            ],
            "paragraph_reviews": [
                {"index": 1, "learner": "The city has an increacing demand. Roads here are poor roads.", "model": "Old model one.", "coaching": "Old coaching one.", "language_correction_upgrade": "Old upgrade."},
                {"index": 2, "learner": "Original paragraph two.", "model": "Old model two.", "coaching": "Old coaching two.", "language_correction_upgrade": ""},
            ],
        }
        score.save(update_fields=["analysis_payload", "updated_at"])

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": entry.entry_id,
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer("The city has an increasing demand. Roads here are poor roads.", "Original paragraph two."),
                "preserve_score": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        annotations = response.json()["score"]["inline_annotations"]
        self.assertEqual([(item["paragraph_index"], item["original"]) for item in annotations], [(1, "poor roads"), (2, "Original")])

    def test_preserved_report_fix_single_word_keeps_nearby_annotations_in_same_sentence(self):
        prompt = self.create_prompt(
            prompt_id="task2-save-scored-fix-word-keeps-nearby",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Save scored fix word keeps nearby prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("The city has an increacing demand and poor roads.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )
        score = WritingScore.objects.get(entry=entry)
        score.analysis_payload = {
            "analysis_backend": "ai",
            "inline_annotations": [
                {"paragraph_index": 1, "original": "increacing", "type": "spelling", "suggestion": "increasing", "explanation": "Spelling."},
                {"paragraph_index": 1, "original": "poor roads", "type": "word_choice", "suggestion": "weak transport links", "explanation": "More precise."},
                {"paragraph_index": 2, "original": "Original", "type": "word_choice", "suggestion": "Initial", "explanation": "Style."},
            ],
            "paragraph_reviews": [
                {"index": 1, "learner": "The city has an increacing demand and poor roads.", "model": "Old model one.", "coaching": "Old coaching one.", "language_correction_upgrade": ""},
                {"index": 2, "learner": "Original paragraph two.", "model": "Old model two.", "coaching": "Old coaching two.", "language_correction_upgrade": ""},
            ],
        }
        score.save(update_fields=["analysis_payload", "updated_at"])

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": entry.entry_id,
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer("The city has an increasing demand and poor roads.", "Original paragraph two."),
                "preserve_score": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        annotations = response.json()["score"]["inline_annotations"]
        self.assertEqual([(item["paragraph_index"], item["original"]) for item in annotations], [(1, "poor roads"), (2, "Original")])

    def test_preserved_report_fix_later_repeated_word_keeps_nearby_annotations(self):
        prompt = self.create_prompt(
            prompt_id="task2-save-scored-fix-later-word",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Save scored fix later repeated word prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("The increacing trend is clear. The city has an increacing demand and poor roads.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )
        score = WritingScore.objects.get(entry=entry)
        score.analysis_payload = {
            "analysis_backend": "ai",
            "inline_annotations": [
                {"paragraph_index": 1, "original": "increacing", "type": "spelling", "suggestion": "increasing", "explanation": "Spelling."},
                {"paragraph_index": 1, "original": "poor roads", "type": "word_choice", "suggestion": "weak transport links", "explanation": "More precise."},
                {"paragraph_index": 2, "original": "Original", "type": "word_choice", "suggestion": "Initial", "explanation": "Style."},
            ],
            "paragraph_reviews": [
                {"index": 1, "learner": "The increacing trend is clear. The city has an increacing demand and poor roads.", "model": "Old model one.", "coaching": "Old coaching one.", "language_correction_upgrade": ""},
                {"index": 2, "learner": "Original paragraph two.", "model": "Old model two.", "coaching": "Old coaching two.", "language_correction_upgrade": ""},
            ],
        }
        score.save(update_fields=["analysis_payload", "updated_at"])

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": entry.entry_id,
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer("The increacing trend is clear. The city has an increasing demand and poor roads.", "Original paragraph two."),
                "preserve_score": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        annotations = response.json()["score"]["inline_annotations"]
        self.assertEqual([(item["paragraph_index"], item["original"]) for item in annotations], [(1, "poor roads"), (2, "Original")])

    def test_preserved_report_drops_edited_sentence_annotation_when_failed_task_exists(self):
        prompt = self.create_prompt(
            prompt_id="task2-save-scored-clear-annotation-with-failed-task",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Save scored clear annotation with failed task",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        previous = paragraph_answer(
            "In conclusion, while there are valid arguments on both sides, I still hold the belief that the continuity of workflow is essential for sustaining high productivity, which ensure that a two-day weekend yields more valuable and enduring results for society.",
            "Original paragraph two.",
        )
        revised = paragraph_answer(
            "In conclusion, while there are valid arguments on both sides, I still hold the belief that the continuity of workflow is essential for sustaining high productivity, which ensures that a two-day weekend yields more valuable and enduring results for society.",
            "Original paragraph two.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=previous,
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )
        score = WritingScore.objects.get(entry=entry)
        score.analysis_payload = {
            "analysis_backend": "ai",
            "inline_annotations": [
                {"paragraph_index": 1, "original": "which ensure", "type": "grammar", "suggestion": "which ensures", "explanation": "Subject-verb agreement."},
                {"paragraph_index": 1, "original": "high productivity", "type": "word_choice", "suggestion": "strong productivity", "explanation": "Collocation."},
                {"paragraph_index": 2, "original": "Original", "type": "word_choice", "suggestion": "Initial", "explanation": "Style."},
            ],
            "paragraph_reviews": [
                {"index": 1, "learner": previous.split("\n\n")[0], "model": "Old model one.", "coaching": "Old coaching one.", "language_correction_upgrade": ""},
                {"index": 2, "learner": "Original paragraph two.", "model": "Old model two.", "coaching": "Old coaching two.", "language_correction_upgrade": ""},
            ],
        }
        score.save(update_fields=["analysis_payload", "updated_at"])
        AITask.objects.create(
            user=self.user,
            task_id=f"aitask_{uuid.uuid4().hex[:24]}",
            task_type="writing_score",
            status=AITask.Status.FAILED,
            related_type="writing_entry",
            related_id=entry.entry_id,
            error_code="provider_failed",
            error_message="provider failed",
        )

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": entry.entry_id,
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": revised,
                "preserve_score": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        annotations = response.json()["score"]["inline_annotations"]
        self.assertEqual([(item["paragraph_index"], item["original"]) for item in annotations], [(1, "high productivity"), (2, "Original")])

    def test_preserved_report_remaps_annotation_when_sentence_is_split_to_new_paragraph(self):
        prompt = self.create_prompt(
            prompt_id="task2-save-scored-remap-split",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Save scored remap split prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("First sentence stays. Second sentence keeps this phrase.", "Final paragraph."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )
        score = WritingScore.objects.get(entry=entry)
        score.analysis_payload = {
            "analysis_backend": "ai",
            "inline_annotations": [
                {"paragraph_index": 1, "original": "Second sentence keeps this phrase", "type": "grammar", "suggestion": "", "explanation": "Sentence control."},
                {"paragraph_index": 2, "original": "Final", "type": "word_choice", "suggestion": "Last", "explanation": "Style."},
            ],
            "paragraph_reviews": [
                {"index": 1, "learner": "First sentence stays. Second sentence keeps this phrase.", "model": "Old model one.", "coaching": "Old coaching one.", "language_correction_upgrade": ""},
                {"index": 2, "learner": "Final paragraph.", "model": "Old model two.", "coaching": "Old coaching two.", "language_correction_upgrade": ""},
            ],
        }
        score.save(update_fields=["analysis_payload", "updated_at"])

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": entry.entry_id,
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer("First sentence stays.", "Second sentence keeps this phrase.", "Final paragraph."),
                "preserve_score": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        annotations = response.json()["score"]["inline_annotations"]
        self.assertIn("Second sentence keeps this phrase", [item["original"] for item in annotations if item["paragraph_index"] == 2])
        self.assertIn("Final", [item["original"] for item in annotations if item["paragraph_index"] == 3])

    def test_delete_writing_report_keeps_entry_answer(self):
        prompt = self.create_prompt(
            prompt_id="task2-delete-report-only",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Delete report only prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Original paragraph one.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )

        response = self.client.delete(f"/api/writing/entries/{entry.entry_id}/report")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], entry.entry_id)
        self.assertEqual(payload["status"], WritingEntry.Status.SAVED)
        self.assertIsNone(payload["score"])
        self.assertEqual(payload["answer"], "Original paragraph one.\n\nOriginal paragraph two.")
        entry.refresh_from_db()
        self.assertEqual(entry.answer, "Original paragraph one.\n\nOriginal paragraph two.")
        self.assertFalse(WritingScore.objects.filter(entry=entry).exists())
        # Deleting the report releases the pinned report time so a future report
        # starts fresh, but the maintained essay itself is kept.
        self.assertNotIn("report_created_at", entry.metadata or {})

    def test_entry_for_prompt_returns_maintained_essay(self):
        prompt = self.create_prompt(
            prompt_id="task2-entry-for-prompt",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Entry for prompt",
            prompt="Some people think a shorter working week benefits society. Discuss.",
        )
        self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("My maintained essay paragraph one.", "Paragraph two."),
            status=WritingEntry.Status.SAVED,
        )

        response = self.client.get(
            "/api/writing/entry-for-prompt",
            data={"task_type": "task2", "prompt_id": prompt.prompt_id},
        )

        self.assertEqual(response.status_code, 200)
        entry = response.json()["entry"]
        self.assertIsNotNone(entry)
        self.assertEqual(entry["answer"], "My maintained essay paragraph one.\n\nParagraph two.")

    def test_entry_for_prompt_prefers_scored_essay_over_newer_empty_duplicate(self):
        prompt = self.create_prompt(
            prompt_id="task2-entry-for-prompt-scored-over-empty",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Entry for prompt scored over empty",
            prompt="Some people think a shorter working week benefits society. Discuss.",
        )
        scored = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("The maintained scored essay.", "It should reopen for this prompt."),
            status=WritingEntry.Status.SCORED,
            overall_band=7.0,
            updated_at=timezone.now() - timezone.timedelta(minutes=5),
        )
        self.create_entry(
            prompt=prompt,
            answer="",
            status=WritingEntry.Status.SAVED,
            updated_at=timezone.now(),
        )

        response = self.client.get(
            "/api/writing/entry-for-prompt",
            data={"task_type": "task2", "prompt_id": prompt.prompt_id},
        )

        self.assertEqual(response.status_code, 200)
        entry = response.json()["entry"]
        self.assertEqual(entry["id"], scored.entry_id)
        self.assertEqual(entry["answer"], scored.answer)

    def test_save_same_prompt_without_id_reuses_existing_saved_entry(self):
        prompt = self.create_prompt(
            prompt_id="task2-save-existing-saved-no-id",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Save existing saved prompt",
            prompt="Some people think a shorter working week benefits society. Discuss.",
        )
        existing = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Old maintained essay.", "Second paragraph."),
            status=WritingEntry.Status.SAVED,
        )

        response = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer("New maintained essay.", "Second paragraph."),
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], existing.entry_id)
        self.assertEqual(payload["answer"], "New maintained essay.\n\nSecond paragraph.")
        self.assertEqual(WritingEntry.objects.filter(user=self.user, prompt=prompt).count(), 1)

    def test_save_existing_entry_can_clear_answer_to_empty(self):
        prompt = self.create_prompt(
            prompt_id="task2-save-existing-clear-empty",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Save existing clear empty prompt",
            prompt="Some people think a shorter working week benefits society. Discuss.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Draft to delete.", "Second paragraph."),
            status=WritingEntry.Status.SAVED,
        )

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": entry.entry_id,
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": "",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], entry.entry_id)
        self.assertEqual(payload["answer"], "")
        self.assertEqual(payload["word_count"], 0)

    def test_entry_for_prompt_returns_none_when_unanswered(self):
        prompt = self.create_prompt(
            prompt_id="task2-entry-for-prompt-empty",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Entry for prompt empty",
            prompt="Some people think competition is healthy. Discuss both views.",
        )

        response = self.client.get(
            "/api/writing/entry-for-prompt",
            data={"task_type": "task2", "prompt_id": prompt.prompt_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["entry"])

    def test_failed_refresh_task_does_not_hide_existing_report_score(self):
        prompt = self.create_prompt(
            prompt_id="task2-failed-task-keeps-score-visible",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Failed task keeps score visible",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Original paragraph one.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=7.5,
        )
        AITask.objects.create(
            user=self.user,
            task_id=f"aitask_{uuid.uuid4().hex[:24]}",
            task_type="writing_score",
            status=AITask.Status.FAILED,
            related_type="writing_entry",
            related_id=entry.entry_id,
            error_code="provider_failed",
            error_message="provider failed",
        )

        response = self.client.get(f"/api/writing/entries/{entry.entry_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNotNone(payload["score"])
        self.assertEqual(payload["score"]["overall_band"], 7.5)

    def test_saving_changed_entry_with_scored_status_but_no_score_updates_original(self):
        prompt = self.create_prompt(
            prompt_id="task2-save-scored-status-without-score",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Save scored status without score prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Original paragraph one.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
        )

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": entry.entry_id,
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer("Revised paragraph one.", "Revised paragraph two."),
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual(saved["id"], entry.entry_id)
        self.assertEqual(saved["status"], WritingEntry.Status.SAVED)
        self.assertEqual(saved["answer"], "Revised paragraph one.\n\nRevised paragraph two.")
        self.assertEqual(WritingEntry.objects.filter(user=self.user, prompt=prompt).count(), 1)

    def test_deleted_writing_entry_terminalizes_running_score_task_on_apply(self):
        prompt = self.create_prompt(
            prompt_id="task2-delete-running-task",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Delete running task prompt",
            prompt="Some people think technology improves education. Discuss both views.",
        )
        entry = self.create_entry(prompt=prompt, answer="Paragraph one.\n\nParagraph two.")
        created = self.client.post(
            f"/api/writing/entries/{entry.entry_id}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        ).json()["task"]
        claimed = AITask.objects.get(task_id=created["id"])
        claimed.status = AITask.Status.RUNNING
        claimed.worker_id = "test-worker"
        claimed.started_at = timezone.now()
        claimed.save(update_fields=["status", "worker_id", "started_at", "updated_at"])
        entry.delete()

        from apps.ai.provider_adapters import ProviderRunResult, apply_provider_run_result

        applied = apply_provider_run_result(claimed, ProviderRunResult.fallback("provider unavailable"))
        self.assertEqual(applied.summary_status, AITask.Status.FALLBACK)
        task = AITask.objects.get(task_id=created["id"])
        self.assertEqual(task.status, AITask.Status.FALLBACK)
        self.assertEqual(task.fallback_reason, "Writing entry was deleted before scoring completed.")

    def test_prompts_random_save_summary_detail_and_score_flow(self):
        prompts = self.client.get("/api/writing/prompts?task_type=task1_academic")
        self.assertEqual(prompts.status_code, 200)
        self.assertGreaterEqual(len(prompts.json()["items"]), 1)

        random_prompt = self.client.post("/api/writing/prompts/random", data={"task_type": "task1_academic"}, content_type="application/json")
        self.assertEqual(random_prompt.status_code, 200)
        prompt = random_prompt.json()
        self.assertEqual(prompt["task_type"], "task1_academic")
        self.assertTrue(prompt["unwritten"])

        save = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": prompt["task_type"],
                "prompt_id": prompt["id"],
                "title": prompt["title"],
                "prompt": prompt["prompt"],
                "answer": paragraph_answer(
                    "The chart shows a clear change in transport habits over time.",
                    "Overall, the main trend is easy to compare across the period.",
                ),
                "prompt_highlights": [{"start": 0, "end": 12}],
                "practice_date": "2026-05-14",
            },
            content_type="application/json",
        )
        self.assertEqual(save.status_code, 200)
        saved = save.json()
        self.assertEqual(saved["status"], WritingEntry.Status.SAVED)
        self.assertEqual(saved["task_label"], WRITING_TASK_LABELS[WritingPrompt.TaskType.TASK1_ACADEMIC])
        self.assertGreater(saved["word_count"], 0)
        self.assertTrue(saved["image_url"])
        self.assertEqual(saved["prompt_highlights"], [{"start": 0, "end": 12}])

        summary = self.client.get("/api/writing/summary?month=2026-05")
        self.assertEqual(summary.status_code, 200)
        summary_payload = summary.json()
        self.assertEqual(summary_payload["stats"]["practiced_days"], 1)
        self.assertIn(saved["id"], [item["id"] for item in summary_payload["recent_entries"]])
        self.assertEqual(next(day for day in summary_payload["days"] if day["date"] == "2026-05-14")["status"], "saved")

        detail = self.client.get(f"/api/writing/entries/{saved['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["answer"], saved["answer"])
        self.assertEqual(detail.json()["image_url"], saved["image_url"])
        self.assertEqual(detail.json()["prompt_highlights"], [{"start": 0, "end": 12}])

        score = self.client.post(f"/api/writing/entries/{saved['id']}/score", content_type="application/json")
        self.assertEqual(score.status_code, 200)
        scored = score.json()
        self.assertEqual(scored["status"], WritingEntry.Status.SCORED)
        self.assertEqual(scored["score"]["backend"], "fallback")
        self.assertIn("AI \u8bc4\u5206\u751f\u6210\u5931\u8d25", scored["score"]["feedback_markdown"])
        self.assertEqual(scored["writing_profile"]["total_scored"], 0)

        summary_after_score = self.client.get("/api/writing/summary?month=2026-05").json()
        self.assertEqual(summary_after_score["stats"]["scored_entries"], 1)
        self.assertEqual(next(day for day in summary_after_score["days"] if day["date"] == "2026-05-14")["status"], "scored")

    def test_prompt_list_returns_user_practice_statuses(self):
        unpracticed_prompt = self.create_prompt(
            prompt_id="task2-status-unpracticed",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Unpracticed prompt",
            prompt="Some people believe public transport should be free. Discuss.",
        )
        saved_prompt = self.create_prompt(
            prompt_id="task2-status-saved",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Saved prompt",
            prompt="Some people think cities should limit private cars. Discuss.",
        )
        scored_prompt = self.create_prompt(
            prompt_id="task2-status-scored",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Scored prompt",
            prompt="Some people think museums should be free. Discuss.",
        )
        self.create_entry(prompt=saved_prompt, answer=paragraph_answer("Saved answer.", "Second paragraph."))
        self.create_entry(
            prompt=scored_prompt,
            answer=paragraph_answer("Scored answer.", "Second paragraph."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )

        response = self.client.get("/api/writing/prompts?task_type=task2")
        self.assertEqual(response.status_code, 200)
        by_id = {item["id"]: item for item in response.json()["items"]}
        self.assertEqual(by_id[unpracticed_prompt.prompt_id]["practice_status"], "unpracticed")
        self.assertEqual(by_id[unpracticed_prompt.prompt_id]["practice_status_label"], "\u672a\u7ec3\u4e60")
        self.assertEqual(by_id[saved_prompt.prompt_id]["practice_status"], "saved")
        self.assertEqual(by_id[saved_prompt.prompt_id]["practice_status_label"], "\u5df2\u4fdd\u5b58")
        self.assertEqual(by_id[scored_prompt.prompt_id]["practice_status"], "scored")
        self.assertEqual(by_id[scored_prompt.prompt_id]["practice_status_label"], "\u5df2\u8bc4\u5206")

    def test_public_task1_samples_are_labeled_and_have_images(self):
        response = self.client.get("/api/writing/prompts?task_type=task1_academic")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]

        self.assertGreaterEqual(len(items), 2)
        by_id = {item["id"]: item for item in items}
        self.assertEqual(by_id["public_sample_task1_bc_001"]["source_label"], "\u5b98\u65b9\u516c\u5f00\u6837\u9898 1")
        self.assertTrue(by_id["public_sample_task1_bc_001"]["image_url"])
        self.assertEqual(by_id["public_sample_task1_bc_002"]["source_label"], "\u5b98\u65b9\u516c\u5f00\u6837\u9898 2")
        self.assertTrue(by_id["public_sample_task1_bc_002"]["image_url"])

    def test_random_prompt_excludes_scored_but_not_saved_until_all_scored(self):
        saved_prompt = self.create_prompt(
            prompt_id="task2-random-saved-still-eligible",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Saved still eligible",
            prompt="Some people think online shopping is replacing local shops. Discuss.",
            category="random_status",
        )
        scored_prompt = self.create_prompt(
            prompt_id="task2-random-scored-excluded",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Scored excluded",
            prompt="Some people think art classes are less important than science. Discuss.",
            category="random_status",
        )
        self.create_entry(prompt=saved_prompt, answer=paragraph_answer("Saved answer.", "Second paragraph."))
        self.create_entry(
            prompt=scored_prompt,
            answer=paragraph_answer("Scored answer.", "Second paragraph."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )

        response = self.client.post(
            "/api/writing/prompts/random",
            data={"task_type": "task2", "category": "random_status"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], saved_prompt.prompt_id)
        self.assertEqual(response.json()["practice_status"], "saved")
        self.assertTrue(response.json()["unwritten"])

        self.create_entry(
            prompt=saved_prompt,
            answer=paragraph_answer("Second scored answer.", "Second paragraph."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )
        fallback_response = self.client.post(
            "/api/writing/prompts/random",
            data={"task_type": "task2", "category": "random_status"},
            content_type="application/json",
        )
        self.assertEqual(fallback_response.status_code, 200)
        self.assertIn(fallback_response.json()["id"], {saved_prompt.prompt_id, scored_prompt.prompt_id})
        self.assertFalse(fallback_response.json()["unwritten"])


    def test_writing_reports_are_owner_scoped_ordered_and_include_latest_ai_task(self):
        older_prompt = self.create_prompt(
            prompt_id="task1-reports-owner-scope",
            task_type=WritingPrompt.TaskType.TASK1_ACADEMIC,
            title="Older owned report",
            prompt="Summarise the chart below.",
        )
        older_entry = self.create_entry(
            prompt=older_prompt,
            answer="The chart shows a steady increase in the use of trains.",
            updated_at=timezone.now() - timezone.timedelta(days=2),
        )

        latest_prompt = self.create_prompt(
            prompt_id="task2-reports-latest-task",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Latest owned report",
            prompt="Some people think public libraries are no longer necessary. Discuss both views and give your opinion.",
        )
        saved = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": latest_prompt.task_type,
                "prompt_id": latest_prompt.prompt_id,
                "prompt": latest_prompt.prompt,
                "title": latest_prompt.title,
                "answer": paragraph_answer(
                    "Public libraries still matter because they provide quiet study space and trusted information.",
                    "They are especially useful for people who cannot afford many books or a quiet place to study.",
                ),
            },
            content_type="application/json",
        ).json()
        task = self.client.post(
            f"/api/writing/entries/{saved['id']}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        ).json()["task"]

        other_user = get_user_model().objects.create_user(username="other-writing-user", password="test-pass")
        self.create_entry(
            user=other_user,
            prompt=latest_prompt,
            answer="Another user's essay should not appear in this list.",
            updated_at=timezone.now() + timezone.timedelta(minutes=1),
        )

        response = self.client.get("/api/writing/reports")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual([item["id"] for item in payload["items"]], [saved["id"], older_entry.entry_id])
        latest_item = payload["items"][0]
        self.assertEqual(latest_item["status"], WritingEntry.Status.SAVED)
        self.assertEqual(latest_item["task_type"], WritingPrompt.TaskType.TASK2)
        self.assertEqual(latest_item["task_label"], WRITING_TASK_LABELS[WritingPrompt.TaskType.TASK2])
        self.assertEqual(latest_item["title"], latest_prompt.title)
        self.assertIsNotNone(latest_item["display_time"])
        self.assertEqual(latest_item["ai_task"]["id"], task["id"])
        self.assertEqual(latest_item["ai_task"]["task_type"], "writing_score")
        self.assertEqual(latest_item["ai_task"]["status"], AITask.Status.PENDING)
        self.assertEqual(latest_item["ai_task"]["related_type"], "writing_entry")
        self.assertEqual(latest_item["ai_task"]["related_id"], saved["id"])
        self.assertNotIn("request_payload", latest_item["ai_task"])
        self.assertNotIn("result_payload", latest_item["ai_task"])
        self.assertNotIn("billing", latest_item["ai_task"])
        self.assertNotIn("metadata", latest_item["ai_task"])
        self.assertNotIn("idempotency_key", latest_item["ai_task"])
        self.assertIsNone(payload["items"][1]["ai_task"])

    def test_writing_reports_order_by_stable_report_time_not_latest_task_update(self):
        now = timezone.now()
        report_prompt = self.create_prompt(
            prompt_id="task2-reports-stable-activity",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Stable activity prompt",
            prompt="Some people believe online learning will replace classrooms. Discuss both views.",
        )
        older_entry = self.create_entry(
            prompt=report_prompt,
            answer=paragraph_answer(
                "Older entry answer with enough detail to create a report item.",
                "This second paragraph makes the answer eligible for scoring.",
            ),
            updated_at=now - timezone.timedelta(days=3),
        )
        older_created_at = now - timezone.timedelta(days=3)
        WritingEntry.objects.filter(pk=older_entry.pk).update(created_at=older_created_at)
        older_entry.refresh_from_db()
        newer_prompt = self.create_prompt(
            prompt_id="task2-reports-newer-stable-activity",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Newer saved activity prompt",
            prompt="Some people think governments should invest more in public transport. Discuss both views.",
        )
        newer_entry = self.create_entry(
            prompt=newer_prompt,
            answer="Newer saved entry that should sort after the task-updated item.",
            updated_at=now - timezone.timedelta(hours=1),
        )
        newer_created_at = now - timezone.timedelta(hours=1)
        WritingEntry.objects.filter(pk=newer_entry.pk).update(created_at=newer_created_at)
        newer_entry.refresh_from_db()

        task_payload = self.client.post(
            f"/api/writing/entries/{older_entry.entry_id}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        ).json()["task"]
        task = AITask.objects.get(task_id=task_payload["id"])
        latest_task_update = now
        AITask.objects.filter(pk=task.pk).update(
            created_at=now - timezone.timedelta(minutes=5),
            updated_at=latest_task_update,
        )

        response = self.client.get("/api/writing/reports")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["id"] for item in payload["items"][:2]], [newer_entry.entry_id, older_entry.entry_id])
        self.assertEqual(
            payload["items"][1]["display_time"],
            older_created_at.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%d %H:%M"),
        )
        self.assertEqual(payload["items"][0]["ai_task"], None)
        self.assertEqual(payload["items"][1]["ai_task"]["id"], task.task_id)

    def test_writing_reports_hide_saved_duplicate_when_scored_report_exists_for_prompt(self):
        prompt = self.create_prompt(
            prompt_id="task2-reports-dedupe-scored-prompt",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Dedupe scored prompt",
            prompt="Some people think competition is more important than cooperation. Discuss both views.",
        )
        scored_entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Original paragraph one.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=7.5,
            updated_at=timezone.now() - timezone.timedelta(minutes=3),
        )
        saved_duplicate = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Later saved paragraph one.", "Later saved paragraph two."),
            status=WritingEntry.Status.SAVED,
            updated_at=timezone.now(),
        )

        response = self.client.get("/api/writing/reports")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = [item["id"] for item in payload["items"]]
        self.assertIn(scored_entry.entry_id, ids)
        self.assertNotIn(saved_duplicate.entry_id, ids)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["overall_band"], 7.5)

    def test_scored_report_display_time_stays_pinned_after_rescore_and_save(self):
        prompt = self.create_prompt(
            prompt_id="task2-reports-pinned-created-time",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Pinned report time prompt",
            prompt="Some people think competition is more important than cooperation. Discuss both views.",
        )
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Original paragraph one.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )
        pinned = timezone.now() - timezone.timedelta(days=4)
        entry.metadata = {**(entry.metadata or {}), "report_created_at": pinned.isoformat()}
        entry.save(update_fields=["metadata", "updated_at"])

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": entry.entry_id,
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer("Edited paragraph one.", "Original paragraph two."),
                "preserve_score": True,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        from apps.writing.services import persist_score
        persist_score(entry, ai_score_payload(overall_band=7.0, task_response=7.0, coherence_cohesion=7.0, lexical_resource=7.0, grammatical_range_accuracy=7.0))

        reports = self.client.get("/api/writing/reports").json()["items"]
        item = next(item for item in reports if item["id"] == entry.entry_id)
        self.assertEqual(item["display_time"], pinned.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%d %H:%M"))

    def test_writing_reports_order_does_not_jump_after_scored_report_edit(self):
        older_prompt = self.create_prompt(
            prompt_id="task2-reports-order-stable-older",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Older stable report",
            prompt="Some people think competition is more important than cooperation. Discuss both views.",
        )
        newer_prompt = self.create_prompt(
            prompt_id="task2-reports-order-stable-newer",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Newer stable report",
            prompt="Some people think shorter working weeks are better. Discuss both views.",
        )
        older_entry = self.create_entry(
            prompt=older_prompt,
            answer=paragraph_answer("Older paragraph one.", "Older paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=7.5,
        )
        newer_entry = self.create_entry(
            prompt=newer_prompt,
            answer=paragraph_answer("Newer paragraph one.", "Newer paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
        )
        older_pin = timezone.now() - timezone.timedelta(days=3)
        newer_pin = timezone.now() - timezone.timedelta(days=1)
        older_entry.metadata = {**(older_entry.metadata or {}), "report_created_at": older_pin.isoformat()}
        newer_entry.metadata = {**(newer_entry.metadata or {}), "report_created_at": newer_pin.isoformat()}
        older_entry.save(update_fields=["metadata", "updated_at"])
        newer_entry.save(update_fields=["metadata", "updated_at"])

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": older_entry.entry_id,
                "task_type": "task2",
                "prompt_id": older_prompt.prompt_id,
                "prompt": older_prompt.prompt,
                "answer": paragraph_answer("Older paragraph one with a local edit.", "Older paragraph two."),
                "preserve_score": True,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        reports = self.client.get("/api/writing/reports").json()["items"]
        ids = [item["id"] for item in reports[:2]]
        self.assertEqual(ids, [newer_entry.entry_id, older_entry.entry_id])

    def test_saving_existing_scored_report_does_not_reset_practice_date(self):
        prompt = self.create_prompt(
            prompt_id="task2-save-keeps-practice-date",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Save keeps practice date prompt",
            prompt="Some people think competition is more important than cooperation. Discuss both views.",
        )
        original_date = timezone.localdate() - timezone.timedelta(days=6)
        entry = self.create_entry(
            prompt=prompt,
            answer=paragraph_answer("Original paragraph one.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=6.0,
            practice_date=original_date,
        )

        response = self.client.post(
            "/api/writing/entries",
            data={
                "id": entry.entry_id,
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer("Edited paragraph one.", "Original paragraph two."),
                "preserve_score": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.practice_date, original_date)
        self.assertEqual(response.json()["practice_date"], original_date.isoformat())

    def test_writing_reports_dedupe_same_cambridge_source_even_with_different_prompt_ids(self):
        scored_prompt = self.create_prompt(
            prompt_id="task2-reports-dedupe-source-scored",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Competition and cooperation scored",
            prompt="Some people think competition is more important than cooperation. Discuss both views.",
            source_book=19,
            source_test=1,
            source_question=2,
        )
        saved_prompt = self.create_prompt(
            prompt_id="task2-reports-dedupe-source-saved",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Competition And Cooperation saved duplicate",
            prompt="Some people think competition is more important than cooperation. Discuss both views and give your opinion.",
            source_book=19,
            source_test=1,
            source_question=2,
        )
        scored_entry = self.create_entry(
            prompt=scored_prompt,
            answer=paragraph_answer("Original paragraph one.", "Original paragraph two."),
            status=WritingEntry.Status.SCORED,
            overall_band=7.5,
            updated_at=timezone.now() - timezone.timedelta(minutes=5),
        )
        saved_duplicate = self.create_entry(
            prompt=saved_prompt,
            answer=paragraph_answer("Saved duplicate paragraph one.", "Saved duplicate paragraph two."),
            status=WritingEntry.Status.SAVED,
            updated_at=timezone.now(),
        )

        response = self.client.get("/api/writing/reports")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = [item["id"] for item in payload["items"]]
        self.assertIn(scored_entry.entry_id, ids)
        self.assertNotIn(saved_duplicate.entry_id, ids)
        self.assertEqual(payload["count"], 1)

    def test_writing_reports_limit_and_filters(self):
        task2_prompt = self.create_prompt(
            prompt_id="task2-reports-filter",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Task 2 filter prompt",
            prompt="Some people think schools should spend more money on sports. Discuss both views.",
        )
        task1_prompt = self.create_prompt(
            prompt_id="task1-reports-filter",
            task_type=WritingPrompt.TaskType.TASK1_ACADEMIC,
            title="Task 1 filter prompt",
            prompt="Summarise the table below.",
        )

        for index in range(105):
            saved_prompt = self.create_prompt(
                prompt_id=f"task2-reports-filter-saved-{index}",
                task_type=WritingPrompt.TaskType.TASK2,
                title=f"Task 2 saved prompt {index}",
                prompt=f"Some people think schools should spend more money on sports topic {index}. Discuss both views.",
            )
            self.create_entry(
                prompt=saved_prompt,
                answer=f"Saved task 2 answer number {index} with enough words for the reports filter test.",
                title=f"Task 2 saved {index}",
            )

        scored_entry = self.create_entry(
            prompt=task2_prompt,
            answer="A scored task 2 answer with feedback metadata.",
            status=WritingEntry.Status.SCORED,
            overall_band=6.5,
            title="Task 2 scored",
        )
        task1_entry = self.create_entry(
            prompt=task1_prompt,
            answer="A task 1 answer used to verify task type filtering.",
            title="Task 1 saved",
        )

        invalid_limit = self.client.get("/api/writing/reports?limit=not-a-number")
        self.assertEqual(invalid_limit.status_code, 200)
        invalid_limit_payload = invalid_limit.json()
        self.assertEqual(invalid_limit_payload["count"], 107)
        self.assertEqual(len(invalid_limit_payload["items"]), 50)

        max_limit = self.client.get("/api/writing/reports?limit=999")
        self.assertEqual(max_limit.status_code, 200)
        max_limit_payload = max_limit.json()
        self.assertEqual(max_limit_payload["count"], 107)
        self.assertEqual(len(max_limit_payload["items"]), 100)

        scored_only = self.client.get("/api/writing/reports?status=scored")
        self.assertEqual(scored_only.status_code, 200)
        scored_payload = scored_only.json()
        self.assertEqual(scored_payload["count"], 1)
        self.assertEqual([item["id"] for item in scored_payload["items"]], [scored_entry.entry_id])
        self.assertEqual(scored_payload["items"][0]["status"], WritingEntry.Status.SCORED)
        self.assertEqual(scored_payload["items"][0]["overall_band"], 6.5)

        task1_only = self.client.get("/api/writing/reports?task_type=task1_academic")
        self.assertEqual(task1_only.status_code, 200)
        task1_payload = task1_only.json()
        self.assertEqual(task1_payload["count"], 1)
        self.assertEqual([item["id"] for item in task1_payload["items"]], [task1_entry.entry_id])
        self.assertEqual(task1_payload["items"][0]["task_type"], WritingPrompt.TaskType.TASK1_ACADEMIC)

        saved_task2 = self.client.get("/api/writing/reports?status=saved&task_type=task2&limit=5")
        self.assertEqual(saved_task2.status_code, 200)
        saved_task2_payload = saved_task2.json()
        self.assertEqual(saved_task2_payload["count"], 105)
        self.assertEqual(len(saved_task2_payload["items"]), 5)
        self.assertTrue(all(item["status"] == WritingEntry.Status.SAVED for item in saved_task2_payload["items"]))
        self.assertTrue(all(item["task_type"] == WritingPrompt.TaskType.TASK2 for item in saved_task2_payload["items"]))

    def test_saving_changed_answer_on_scored_entry_updates_original(self):
        prompt = WritingPrompt.objects.create(
            prompt_id="task2-api-reset",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Reset score prompt",
            prompt="Some people think cities should invest more in public transport. Discuss.",
        )
        save = self.client.post(
            "/api/writing/entries",
            data={"task_type": "task2", "prompt_id": prompt.prompt_id, "prompt": prompt.prompt, "answer": paragraph_answer("First answer with a clear position.", "Second paragraph adds a basic supporting reason.")},
            content_type="application/json",
        ).json()
        self.client.post(f"/api/writing/entries/{save['id']}/score", content_type="application/json")
        self.assertTrue(WritingScore.objects.filter(entry__entry_id=save["id"]).exists())

        changed = self.client.post(
            "/api/writing/entries",
            data={"id": save["id"], "task_type": "task2", "prompt_id": prompt.prompt_id, "prompt": prompt.prompt, "answer": paragraph_answer("A changed answer with new wording.", "The second paragraph gives a new reason.")},
            content_type="application/json",
        )
        self.assertEqual(changed.status_code, 200)
        changed_payload = changed.json()
        self.assertEqual(changed_payload["id"], save["id"])
        self.assertEqual(changed_payload["status"], WritingEntry.Status.SAVED)
        self.assertIsNone(changed_payload["score"])
        self.assertFalse(WritingScore.objects.filter(entry__entry_id=save["id"]).exists())
        original = WritingEntry.objects.get(entry_id=save["id"])
        self.assertEqual(original.answer, "A changed answer with new wording.\n\nThe second paragraph gives a new reason.")

    def test_score_task_creates_refresh_safe_billable_ai_task(self):
        prompt = WritingPrompt.objects.create(
            prompt_id="task2-api-score-task",
            task_type=WritingPrompt.TaskType.TASK2,
            title="AI task prompt",
            prompt="Some people think technology helps students learn independently. Discuss.",
        )
        save = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer(
                    "Technology can help students learn independently because they can review lessons.",
                    "It also lets them practise at their own pace with flexible resources.",
                ),
            },
            content_type="application/json",
        ).json()

        created = self.client.post(
            f"/api/writing/entries/{save['id']}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        task = created.json()["task"]
        self.assertEqual(task["task_type"], "writing_score")
        self.assertEqual(task["provider"], "codex")
        self.assertEqual(task["status"], AITask.Status.PENDING)
        self.assertEqual(task["related_type"], "writing_entry")
        self.assertEqual(task["related_id"], save["id"])
        self.assertIsNone(task["billing"]["reservation_id"])

        duplicate = self.client.post(
            f"/api/writing/entries/{save['id']}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertFalse(duplicate.json()["created"])
        self.assertEqual(duplicate.json()["task"]["id"], task["id"])
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U)
        self.assertEqual(wallet.reserved_u, 0)

        detail = self.client.get(f"/api/writing/entries/{save['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["ai_task"]["id"], task["id"])
        self.assert_entry_detail_contract(
            detail.json(),
            entry_id=save["id"],
            prompt_id=prompt.prompt_id,
            task_type="task2",
            word_count=save["word_count"],
            ai_task_status=AITask.Status.PENDING,
        )

        cancelled = self.client.post(
            f"/api/ai/tasks/{task['id']}/cancel/",
            data={"reason": "user cancelled score request"},
            content_type="application/json",
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["status"], AITask.Status.CANCELLED)

        detail_after_cancel = self.client.get(f"/api/writing/entries/{save['id']}")
        self.assertEqual(detail_after_cancel.status_code, 200)
        self.assertEqual(detail_after_cancel.json()["ai_task"]["id"], task["id"])
        self.assert_entry_detail_contract(
            detail_after_cancel.json(),
            entry_id=save["id"],
            prompt_id=prompt.prompt_id,
            task_type="task2",
            word_count=save["word_count"],
            ai_task_status=AITask.Status.CANCELLED,
        )
        self.assertFalse(WritingScore.objects.filter(entry__entry_id=save["id"]).exists())

    def test_force_score_task_on_scored_entry_creates_new_task_and_hides_stale_score(self):
        prompt = WritingPrompt.objects.create(
            prompt_id="task2-force-score-task",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Force score task prompt",
            prompt="Some people think technology helps students learn independently. Discuss.",
        )
        save = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer(
                    "Technology can help students learn independently because they can review lessons.",
                    "It also lets them practise at their own pace with flexible resources.",
                ),
            },
            content_type="application/json",
        ).json()
        first_task = self.client.post(
            f"/api/writing/entries/{save['id']}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        ).json()["task"]
        complete_score_task(
            first_task["id"],
            {
                "score": ai_score_payload(overall_band=7.5, task_response=7.5, coherence_cohesion=7.5, lexical_resource=7.5, grammatical_range_accuracy=7.5),
                "usage": {"input_tokens": 1000, "output_tokens": 100},
            },
        )
        scored_detail = self.client.get(f"/api/writing/entries/{save['id']}").json()
        self.assertEqual(scored_detail["score"]["overall_band"], 7.5)

        forced = self.client.post(
            f"/api/writing/entries/{save['id']}/score-task",
            data={"reserved_u": 300_000, "force": True},
            content_type="application/json",
        )

        self.assertEqual(forced.status_code, 201)
        payload = forced.json()
        self.assertTrue(payload["created"])
        self.assertNotEqual(payload["task"]["id"], first_task["id"])
        self.assertEqual(payload["task"]["status"], AITask.Status.PENDING)
        self.assertIsNone(payload["entry"]["score"])
        detail = self.client.get(f"/api/writing/entries/{save['id']}").json()
        self.assertEqual(detail["ai_task"]["id"], payload["task"]["id"])
        self.assertIsNone(detail["score"])
        self.assertTrue(WritingScore.objects.filter(entry__entry_id=save["id"], overall_band=7.5).exists())

    @override_settings(AI_HTTP_BASE_URL="", AI_HTTP_API_KEY="", AI_HTTP_MODEL="")
    def test_score_task_worker_uses_codex_provider_on_normal_path(self):
        prompt = WritingPrompt.objects.create(
            prompt_id="task2-codex-worker-normal",
            task_type=WritingPrompt.TaskType.TASK2,
            title="AI provider normal path",
            prompt="Some people think online learning is better than classroom learning. Discuss.",
        )
        save = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer(
                    "Online learning can be useful because students can review lessons at any time.",
                    "However, classrooms still provide direct support and immediate interaction.",
                ),
            },
            content_type="application/json",
        ).json()
        task = self.client.post(
            f"/api/writing/entries/{save['id']}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        ).json()["task"]
        out = StringIO()

        with patch("apps.ai.provider_adapters.run_codex") as run_codex:
            run_codex.return_value = (json.dumps(ai_score_payload()), {"input_tokens": 1200, "output_tokens": 420})
            call_command("run_ai_tasks", "--limit", "5", "--worker-id", "writing-codex-normal", stdout=out)

        run_codex.assert_called_once()
        task_row = AITask.objects.get(task_id=task["id"])
        self.assertEqual(task_row.provider, "codex")
        self.assertEqual(task_row.status, AITask.Status.SUCCEEDED)
        scored = self.client.get(f"/api/writing/entries/{save['id']}").json()
        self.assertEqual(scored["score"]["backend"], "ai")
        self.assertEqual(scored["score"]["analysis_backend"], "ai")
        self.assertEqual(scored["score"]["billing_usage"]["input_tokens"], 1200)

    def test_score_task_rejects_unsegmented_task2_answer_with_guidance(self):
        prompt = WritingPrompt.objects.create(
            prompt_id="task2-paragraph-required",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Paragraph required prompt",
            prompt="Some people think technology improves education. Discuss.",
        )
        save = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": "Technology can improve education because students can review lessons and practise more flexibly.",
            },
            content_type="application/json",
        ).json()

        response = self.client.post(
            f"/api/writing/entries/{save['id']}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["code"], "paragraphs_required")
        self.assertEqual(payload["paragraph_guidance"]["task_type"], WritingPrompt.TaskType.TASK2)
        self.assertGreaterEqual(len(payload["paragraph_guidance"]["tips"]), 2)
        self.assertTrue(payload["paragraph_guidance"]["tips"][1])

    def test_sync_score_rejects_unsegmented_task1_answer_with_guidance(self):
        prompt = WritingPrompt.objects.create(
            prompt_id="task1-paragraph-required",
            task_type=WritingPrompt.TaskType.TASK1_ACADEMIC,
            title="Task 1 paragraph required prompt",
            prompt="Summarise the chart below.",
        )
        save = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": "task1_academic",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": "The chart shows a clear increase in public transport use over time.",
            },
            content_type="application/json",
        ).json()

        response = self.client.post(f"/api/writing/entries/{save['id']}/score", content_type="application/json")

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["code"], "paragraphs_required")
        self.assertEqual(payload["paragraph_guidance"]["task_type"], WritingPrompt.TaskType.TASK1_ACADEMIC)
        self.assertIn("Overview", " ".join(payload["paragraph_guidance"]["tips"]))

    def test_complete_score_task_persists_score_profile_and_settles_billing(self):
        prompt = WritingPrompt.objects.create(
            prompt_id="task2-complete-score-task",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Complete score task prompt",
            prompt="Some people think online learning is better than classroom learning. Discuss.",
        )
        save = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer(
                    "Online learning can be useful because students can review lessons at any time.",
                    "However, classrooms still provide direct support and immediate interaction.",
                ),
            },
            content_type="application/json",
        ).json()
        task_payload = self.client.post(
            f"/api/writing/entries/{save['id']}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        ).json()["task"]
        claim_ai_task(task_payload["id"], worker_id="test-worker")

        completed = complete_score_task(
            task_payload["id"],
            {
                "score": ai_score_payload(),
                "usage": {"input_tokens": 1000, "output_tokens": 100},
            },
        )

        self.assertEqual(completed["status"], WritingEntry.Status.SCORED)
        self.assertEqual(completed["score"]["backend"], "ai")
        self.assertEqual(completed["writing_profile"]["total_scored"], 1)
        task = AITask.objects.get(task_id=task_payload["id"])
        self.assertEqual(task.status, AITask.Status.SUCCEEDED)
        self.assertIsNotNone(task.usage)
        score = WritingScore.objects.get(entry__entry_id=save["id"])
        self.assertEqual(score.billing_metadata, {"input_tokens": 1000, "output_tokens": 100})
        self.assertEqual(score.analysis_payload["analysis_backend"], "ai")
        self.assertEqual(score.analysis_payload["paragraph_reviews"][0]["coaching"], "AI explains how this paragraph works logically.")
        self.assertIn("article", score.analysis_payload["paragraph_reviews"][0]["language_correction_upgrade"])
        self.assertEqual(score.analysis_payload["inline_annotations"], [])
        self.assertEqual(score.analysis_payload["spelling_correction_summary"], "No obvious spelling errors.")
        detail_after_complete = self.client.get(f"/api/writing/entries/{save['id']}")
        self.assertEqual(detail_after_complete.status_code, 200)
        self.assert_entry_detail_contract(
            detail_after_complete.json(),
            entry_id=save["id"],
            prompt_id=prompt.prompt_id,
            task_type="task2",
            word_count=save["word_count"],
            ai_task_status=AITask.Status.SUCCEEDED,
            score_backend="ai",
        )
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.reserved_u, 0)
        self.assertLess(wallet.balance_u, DEFAULT_INITIAL_GRANT_U)
        repeated = complete_score_task(
            task_payload["id"],
            {
                "score": ai_score_payload(),
                "usage": {"input_tokens": 1000, "output_tokens": 100},
            },
        )
        self.assertEqual(repeated["ai_task"]["status"], AITask.Status.SUCCEEDED)
        profile = WritingLearnerProfile.objects.get(user=self.user)
        self.assertEqual(profile.total_scored, 1)
        self.assertEqual(
            WalletLedgerEntry.objects.filter(user=self.user, call_id=task.call_id, entry_type=WalletLedgerEntry.EntryType.SETTLE).count(),
            1,
        )

    def test_complete_score_task_overrides_inconsistent_model_overall_with_average(self):
        # Reproduces the "Clean Water" bug: the model returns four sub-scores that
        # average to 8.0 but reports overall_band 7.5. The persisted overall must
        # be the IELTS average (8.0), not the model's inconsistent number.
        prompt = WritingPrompt.objects.create(
            prompt_id="task2-overall-average",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Overall average prompt",
            prompt="Some people think clean water should be free for everyone. Discuss.",
        )
        save = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer(
                    "Providing clean water free of charge could improve public health for everyone.",
                    "However, it may also encourage waste, so a small fee might use the resource wisely.",
                ),
            },
            content_type="application/json",
        ).json()
        task_payload = self.client.post(
            f"/api/writing/entries/{save['id']}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        ).json()["task"]
        claim_ai_task(task_payload["id"], worker_id="test-worker")

        completed = complete_score_task(
            task_payload["id"],
            {
                "score": ai_score_payload(
                    overall_band=7.5,  # model's inconsistent overall 閳?must be ignored
                    task_response=7.5,
                    coherence_cohesion=8.0,
                    lexical_resource=8.0,
                    grammatical_range_accuracy=8.0,
                ),
                "usage": {"input_tokens": 1000, "output_tokens": 100},
            },
        )
        self.assertEqual(completed["score"]["overall_band"], 8.0)
        score = WritingScore.objects.get(entry__entry_id=save["id"])
        self.assertEqual(float(score.overall_band), 8.0)
        self.assertEqual(float(score.task_response), 7.5)

    def test_complete_score_task_rejects_ai_score_without_structured_analysis(self):
        prompt = WritingPrompt.objects.create(
            prompt_id="task2-complete-score-task-missing-analysis",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Missing analysis prompt",
            prompt="Some people think online learning is better than classroom learning. Discuss.",
        )
        save = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer(
                    "Online learning can be useful because students can review lessons at any time.",
                    "However, classrooms still provide direct support and immediate interaction.",
                ),
            },
            content_type="application/json",
        ).json()
        task_payload = self.client.post(
            f"/api/writing/entries/{save['id']}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        ).json()["task"]
        claim_ai_task(task_payload["id"], worker_id="test-worker")

        with self.assertRaises(WritingError):
            complete_score_task(
                task_payload["id"],
                {
                    "score": {
                        "overall_band": 6.0,
                        "task_response": 6.0,
                        "coherence_cohesion": 6.0,
                        "lexical_resource": 6.0,
                        "grammatical_range_accuracy": 6.0,
                        "feedback_markdown": "- Score without AI paragraph analysis.",
                        "grammar_corrections": [],
                        "backend": "ai",
                    },
                    "usage": {"input_tokens": 1000, "output_tokens": 100},
                },
            )

        self.assertFalse(WritingScore.objects.filter(entry__entry_id=save["id"]).exists())

    def test_fallback_score_task_persists_default_score_and_releases_billing(self):
        prompt = WritingPrompt.objects.create(
            prompt_id="task2-fallback-score-task",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Fallback score task prompt",
            prompt="Some people think students should have more homework. Discuss.",
        )
        save = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer(
                    "Homework can help students review lessons and remember important content.",
                    "However, too much homework may reduce rest time and lower motivation.",
                ),
            },
            content_type="application/json",
        ).json()
        task_payload = self.client.post(
            f"/api/writing/entries/{save['id']}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        ).json()["task"]

        fallback = fallback_score_task(task_payload["id"], "provider unavailable")

        self.assertEqual(fallback["status"], WritingEntry.Status.SCORED)
        self.assertEqual(fallback["score"]["backend"], "fallback")
        self.assertEqual(fallback["score"]["analysis_backend"], "fallback")
        self.assertEqual(fallback["score"]["fallback_reason"], "provider unavailable")
        self.assertIn("AI \u8bc4\u5206\u751f\u6210\u5931\u8d25", fallback["score"]["feedback_markdown"])
        task = AITask.objects.get(task_id=task_payload["id"])
        self.assertEqual(task.status, AITask.Status.FALLBACK)
        detail_after_fallback = self.client.get(f"/api/writing/entries/{save['id']}")
        self.assertEqual(detail_after_fallback.status_code, 200)
        self.assert_entry_detail_contract(
            detail_after_fallback.json(),
            entry_id=save["id"],
            prompt_id=prompt.prompt_id,
            task_type="task2",
            word_count=save["word_count"],
            ai_task_status=AITask.Status.FALLBACK,
            score_backend="fallback",
        )
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.reserved_u, 0)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U)

    def test_cancelled_score_task_ignores_late_completion_and_keeps_entry_unscored(self):
        prompt = WritingPrompt.objects.create(
            prompt_id="task2-cancelled-complete-score-task",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Cancelled completion prompt",
            prompt="Some people think children should start learning a foreign language earlier. Discuss.",
        )
        save = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer(
                    "Starting earlier can improve fluency because children have more time to practise.",
                    "However, teaching methods still need to match children's age and attention span.",
                ),
            },
            content_type="application/json",
        ).json()
        task_payload = self.client.post(
            f"/api/writing/entries/{save['id']}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        ).json()["task"]
        cancel_billable_ai_task(task_payload["id"], "user cancelled before scoring started")

        completed = complete_score_task(
            task_payload["id"],
            {
                "score": ai_score_payload(feedback_markdown="- This should be ignored after cancellation."),
                "usage": {"input_tokens": 900, "output_tokens": 100},
            },
        )

        self.assertEqual(completed["ai_task"]["status"], AITask.Status.CANCELLED)
        self.assertIsNone(completed["score"])
        self.assertFalse(WritingScore.objects.filter(entry__entry_id=save["id"]).exists())

    def test_cancelled_pending_score_task_ignores_late_fallback_and_keeps_entry_unscored(self):
        prompt = WritingPrompt.objects.create(
            prompt_id="task2-cancelled-fallback-score-task",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Cancelled fallback prompt",
            prompt="Some people think school holidays should be longer. Discuss.",
        )
        save = self.client.post(
            "/api/writing/entries",
            data={
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer(
                    "Longer holidays can reduce pressure and give students time to recover.",
                    "However, students may forget routines if the break is too long.",
                ),
            },
            content_type="application/json",
        ).json()
        task_payload = self.client.post(
            f"/api/writing/entries/{save['id']}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        ).json()["task"]
        cancel_billable_ai_task(task_payload["id"], "user cancelled before scoring started")

        fallback = fallback_score_task(task_payload["id"], "provider unavailable")

        self.assertEqual(fallback["ai_task"]["status"], AITask.Status.CANCELLED)
        self.assertIsNone(fallback["score"])
        self.assertFalse(WritingScore.objects.filter(entry__entry_id=save["id"]).exists())

    def test_prompt_bank_filters_categories_and_sorts_cambridge_descending(self):
        image_path = "/assets/writing/task1/cambridge/20/test_1_task_1.png"
        self.create_prompt(
            prompt_id="cambridge-20-test-1-task-1",
            task_type=WritingPrompt.TaskType.TASK1_ACADEMIC,
            title="Cambridge 20 Test 1 Task 1",
            prompt="The first table below shows a Cambridge test prompt.",
            category="table",
            image_url=image_path,
            source="cambridge_ielts_authorized_import",
            source_book=20,
            source_test=1,
            source_question=1,
        )
        self.create_prompt(
            prompt_id="cambridge-19-test-1-task-1",
            task_type=WritingPrompt.TaskType.TASK1_ACADEMIC,
            title="Cambridge 19 Test 1 Task 1",
            prompt="The line graph below shows another Cambridge test prompt.",
            category="line_graph",
            image_url="/assets/writing/task1/cambridge/19/test_1_task_1.png",
            source="cambridge_ielts_authorized_import",
            source_book=19,
            source_test=1,
            source_question=1,
        )
        self.create_prompt(
            prompt_id="cambridge-20-test-2-task-2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Cambridge 20 Test 2 Task 2",
            prompt="Some people think a Cambridge test prompt should be practised. To what extent do you agree?",
            category="opinion",
            source="cambridge_ielts_authorized_import",
            source_book=20,
            source_test=2,
            source_question=2,
        )
        self.create_prompt(
            prompt_id="cambridge-20-test-3-task-2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Cambridge 20 Test 3 Task 2",
            prompt="Some people think another Cambridge prompt should be practised. Discuss both views.",
            category="discussion",
            source="cambridge_ielts_authorized_import",
            source_book=20,
            source_test=3,
            source_question=2,
        )

        task1 = self.client.get("/api/writing/prompts?task_type=task1_academic&category=table")
        self.assertEqual(task1.status_code, 200)
        task1_payload = task1.json()
        task1_ids = [item["id"] for item in task1_payload["items"]]
        self.assertIn("cambridge-20-test-1-task-1", task1_ids)
        all_task1 = self.client.get("/api/writing/prompts?task_type=task1_academic")
        self.assertEqual(all_task1.status_code, 200)
        all_task1_ids = [item["id"] for item in all_task1.json()["items"]]
        self.assertLess(all_task1_ids.index("cambridge-20-test-1-task-1"), all_task1_ids.index("cambridge-19-test-1-task-1"))
        cambridge_task1_items = [item for item in task1_payload["items"] if item["source_book"]]
        self.assertEqual(cambridge_task1_items[0]["source_book"], 20)
        self.assertEqual(cambridge_task1_items[0]["source_label"], "\u5251\u96c520-1 Task 1")
        self.assertTrue(cambridge_task1_items[0]["image_url"])
        self.assertEqual(len(task1_payload["catalog"]), 80)
        self.assertEqual(task1_payload["catalog"][0]["id"], "cambridge-20-test-1-task-1")
        self.assertEqual(task1_payload["catalog"][0]["source_label"], "\u5251\u96c520-1 Task 1")
        self.assertIn("table", {item["category"] for item in task1_payload["categories"]})
        self.assertGreaterEqual(
            next(item["count"] for item in task1_payload["categories"] if item["category"] == "table"),
            1,
        )

        task2 = self.client.get("/api/writing/prompts?task_type=task2&category=opinion")
        self.assertEqual(task2.status_code, 200)
        task2_payload = task2.json()
        self.assertTrue(task2_payload["items"])
        cambridge_task2_items = [item for item in task2_payload["items"] if item["source_book"]]
        self.assertTrue(cambridge_task2_items[0]["source_label"].startswith("\u5251\u96c520-"))
        self.assertEqual(len(task2_payload["catalog"]), 80)
        self.assertEqual(task2_payload["catalog"][0]["id"], "cambridge-20-test-1-task-2")
        self.assertEqual(task2_payload["catalog"][0]["source_label"], "\u5251\u96c520-1 Task 2")
        self.assertTrue(all(item["task_type"] == WritingPrompt.TaskType.TASK2 for item in task2_payload["items"]))
        self.assertTrue(all(item["category"] == "opinion" for item in task2_payload["items"]))

    def test_cambridge_task1_seed_bank_is_complete_and_visually_classified(self):
        repo_root = Path(__file__).resolve().parents[3]
        seed_root = repo_root / "data" / "ielts" / "writing" / "cambridge" / "task1_academic"
        static_root = repo_root / "web" / "static"
        prompts = {}
        for path in seed_root.glob("cambridge_*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            for prompt in payload["prompts"]:
                prompts[prompt["id"]] = prompt

        expected_ids = {
            f"cambridge-{book}-test-{test}-task-1"
            for book in range(7, 21)
            for test in range(1, 5)
        }
        self.assertEqual(set(prompts), expected_ids)

        expected_categories = {
            "cambridge-7-test-1-task-1": "table",
            "cambridge-7-test-2-task-1": "line_graph",
            "cambridge-7-test-3-task-1": "bar_chart",
            "cambridge-7-test-4-task-1": "pie_chart",
            "cambridge-8-test-1-task-1": "mixed",
            "cambridge-8-test-2-task-1": "pie_chart",
            "cambridge-8-test-3-task-1": "process",
            "cambridge-8-test-4-task-1": "line_graph",
            "cambridge-9-test-2-task-1": "bar_chart",
            "cambridge-9-test-3-task-1": "pie_chart",
            "cambridge-10-test-1-task-1": "pie_chart",
            "cambridge-11-test-1-task-1": "pie_chart",
            "cambridge-11-test-2-task-1": "pie_chart",
            "cambridge-11-test-4-task-1": "mixed",
            "cambridge-12-test-1-task-1": "bar_chart",
            "cambridge-13-test-1-task-1": "map",
            "cambridge-13-test-2-task-1": "bar_chart",
            "cambridge-13-test-3-task-1": "bar_chart",
            "cambridge-13-test-4-task-1": "map",
            "cambridge-14-test-1-task-1": "pie_chart",
            "cambridge-14-test-2-task-1": "mixed",
            "cambridge-15-test-4-task-1": "mixed",
            "cambridge-16-test-1-task-1": "line_graph",
            "cambridge-19-test-4-task-1": "mixed",
            "cambridge-20-test-3-task-1": "mixed",
        }
        for prompt_id, expected_category in expected_categories.items():
            self.assertEqual(prompts[prompt_id]["category"], expected_category, prompt_id)

        for prompt_id, prompt in prompts.items():
            self.assertEqual(prompt["source_label"], f"\u5251\u96c5{prompt['source_book']}-{prompt['source_test']} Task 1")
            image_url = prompt.get("image_url")
            self.assertTrue(image_url, prompt_id)
            self.assertTrue((static_root / image_url.removeprefix("/")).exists(), prompt_id)

    def test_cambridge_task2_seed_bank_is_complete_from_book_5(self):
        repo_root = Path(__file__).resolve().parents[3]
        seed_root = repo_root / "data" / "ielts" / "writing" / "cambridge" / "task2"
        prompts = {}
        for path in seed_root.glob("cambridge_*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            for prompt in payload["prompts"]:
                prompts[prompt["id"]] = prompt

        expected_ids = {
            f"cambridge-{book}-test-{test}-task-2"
            for book in range(5, 21)
            for test in range(1, 5)
        }
        self.assertEqual({prompt_id for prompt_id in prompts if "-task-2" in prompt_id}, expected_ids)

        for book in range(5, 21):
            for test in range(1, 5):
                prompt_id = f"cambridge-{book}-test-{test}-task-2"
                prompt = prompts[prompt_id]
                self.assertEqual(prompt["source_book"], book)
                self.assertEqual(prompt["source_test"], test)
                self.assertEqual(prompt["source_question"], 2)
                self.assertEqual(prompt["source_label"], f"\u5251\u96c5{book}-{test} Task 2")
                self.assertGreater(len(prompt["prompt"]), 80)
                self.assertNotIn("??", prompt["source_label"])
                self.assertNotIn("Write at least 250 words", prompt["prompt"])
                self.assertTrue(prompt.get("source_url"))

    def test_seed_prompt_sync_uses_file_signature_not_loaded_count(self):
        from apps.writing import prompt_services
        from apps.writing.prompt_services import sync_seed_prompts

        prompt_services._seed_prompt_sync_done = True
        prompt_services._seed_prompt_sync_signature = "stale-signature"
        for index in range(60):
            self.create_prompt(
                prompt_id=f"already-loaded-{index}",
                task_type=WritingPrompt.TaskType.TASK2,
                title=f"Loaded {index}",
                prompt=f"Existing writing prompt {index}. Do you agree or disagree?",
                category="opinion",
                source="local_seed",
            )

        sync_seed_prompts()

        self.assertTrue(WritingPrompt.objects.filter(prompt_id="cambridge-5-test-1-task-2").exists())
        self.assertNotEqual(prompt_services._seed_prompt_sync_signature, "stale-signature")

    def test_task2_prompt_bank_filters_by_fixed_question_pattern(self):
        self.create_prompt(
            prompt_id="task2-pattern-discussion",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Discussion Pattern",
            prompt="Some people think public money should be spent on parks, while others think it should be spent on roads.\n\nDiscuss both views and give your own opinion.",
            category="discussion",
            source="cambridge_ielts_authorized_import",
            source_book=20,
            source_test=1,
            source_question=2,
        )
        self.create_prompt(
            prompt_id="task2-pattern-discussion-singular-view",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Information Sharing",
            prompt="Some people believe that it is good to share as much information as possible. Others believe that some information is too important to be shared freely.\n\nDiscuss both these view and give your own opinion.",
            category="discussion",
            source="cambridge_ielts_authorized_import",
            source_book=12,
            source_test=1,
            source_question=2,
        )
        self.create_prompt(
            prompt_id="task2-pattern-discussion-sides",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Education Purpose",
            prompt="Some people believe the purpose of education is to prepare individuals to be useful to society. Others say the purpose of education is to achieve personal ambitions.\n\nDiscuss both sides and give your opinion.",
            category="discussion",
            source="local_seed",
        )
        self.create_prompt(
            prompt_id="task2-pattern-discussion-short",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Printed Books",
            prompt="Some people think that printed books are no longer needed in a digital era. Others think that printed books will still play an important role.\n\nDiscuss both and give your own opinion.",
            category="discussion",
            source="local_seed",
        )
        self.create_prompt(
            prompt_id="task2-pattern-positive-negative",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Positive Negative Pattern",
            prompt="More people now work remotely than in the past.\n\nDo you think this is a positive or a negative development?",
            category="two_part",
            source="cambridge_ielts_authorized_import",
            source_book=20,
            source_test=2,
            source_question=2,
        )
        self.create_prompt(
            prompt_id="task2-pattern-positive-negative-no-second-article",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Global Food",
            prompt="In many countries nowadays, consumers can go to a supermarket and buy food produced all over the world.\n\nDo you think this is a positive or negative development? Give reasons for your answer.",
            category="opinion",
            source="cambridge_ielts_authorized_import",
            source_book=19,
            source_test=4,
            source_question=2,
        )
        self.create_prompt(
            prompt_id="task2-pattern-positive-negative-with-first-question",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Children And Smartphones",
            prompt="Some children spend hours every day on their smartphones.\n\nWhy is this the case? Do you think this is a positive or a negative development?",
            category="two_part",
            source="cambridge_ielts_authorized_import",
            source_book=17,
            source_test=2,
            source_question=2,
        )
        self.create_prompt(
            prompt_id="task2-pattern-positive-negative-has-this-become",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Technology And Relationships",
            prompt="Nowadays the way many people interact with each other has changed because of technology.\n\nIn what ways has technology affected the types of relationships people make? Has this become a positive or negative development?",
            category="two_part",
            source="cambridge_ielts_authorized_import",
            source_book=8,
            source_test=2,
            source_question=2,
        )
        self.create_prompt(
            prompt_id="task2-pattern-positive-negative-missing-words",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Western Clothing",
            prompt="In many countries, people wear more western-style clothes than their traditional clothes.\n\nWhy is this the case? ls this a positive negative development?",
            category="two_part",
            source="local_seed",
        )
        self.create_prompt(
            prompt_id="task2-pattern-positive-negative-situation",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Advertising",
            prompt="People are surrounded by advertising. Why might this be the case? Do you think this is a positive or negative situation?",
            category="two_part",
            source="local_seed",
        )
        self.create_prompt(
            prompt_id="task2-pattern-agree",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Agree Pattern",
            prompt="Schools should teach financial skills to all students.\n\nTo what extent do you agree or disagree?",
            category="opinion",
            source="cambridge_ielts_authorized_import",
            source_book=20,
            source_test=3,
            source_question=2,
        )
        self.create_prompt(
            prompt_id="task2-pattern-agree-typo",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Music",
            prompt="Some people say that music is a good way of bringing people of different cultures and ages together.\n\nTo what extent do you agree of disagree with this opinion?",
            category="opinion",
            source="cambridge_ielts_authorized_import",
            source_book=14,
            source_test=3,
            source_question=2,
        )
        self.create_prompt(
            prompt_id="task2-pattern-agree-extend-typo",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Children And Advertising",
            prompt="Some people think advertising aimed at children should be banned.\n\nTo what extend do agree or disagree?",
            category="opinion",
            source="local_seed",
        )
        self.create_prompt(
            prompt_id="task2-pattern-benefits-outweigh",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Environmental Benefits",
            prompt="Some people believe new transport systems can reduce pollution. Do you think the environmental benefits of this development outweigh the disadvantages for individuals and businesses?",
            category="advantages_disadvantages",
            source="cambridge_ielts_authorized_import",
            source_book=20,
            source_test=4,
            source_question=2,
        )
        self.create_prompt(
            prompt_id="task2-pattern-benefits-outweigh-drawbacks",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Knowledge Online",
            prompt="In the past, people stored knowledge in books. Nowadays, it is stored on the Internet.\n\nDo the benefits of this development outweigh the drawbacks?",
            category="advantages_disadvantages",
            source="local_seed",
        )
        self.create_prompt(
            prompt_id="task2-pattern-negative-effect-outweigh",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Reading Online",
            prompt="More people read news online instead of in newspapers.\n\nDo you think the negative effect of such trend outweigh the positive effect?",
            category="advantages_disadvantages",
            source="local_seed",
        )
        self.create_prompt(
            prompt_id="task2-pattern-extent-advantages-outweigh",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Ageing Population",
            prompt="In many countries, people are now living longer than ever before. Some people say an ageing population creates problems for governments. Other people think there are benefits if society has more elderly people. To what extent do the advantages of having an ageing population outweigh the disadvantages?",
            category="advantages_disadvantages",
            source="local_seed",
        )
        self.create_prompt(
            prompt_id="task2-pattern-reasons-research",
            task_type=WritingPrompt.TaskType.TASK2,
            title="House History",
            prompt="In some countries, more and more people are becoming interested in finding out about the history of the house or building they live in.\n\nWhat are the reasons for this? How can people research this?",
            category="two_part",
            source="local_seed",
        )
        self.create_prompt(
            prompt_id="task2-pattern-causes-effects",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Time Away From Family",
            prompt="People in many countries spend more and more time far away from their families.\n\nWhy does this happen and what effects will it have on them and their families?",
            category="causes_effects",
            source="local_seed",
        )
        self.create_prompt(
            prompt_id="task2-pattern-health-causes-measures",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Health And Fitness",
            prompt="In some countries the average weight of people is increasing and their levels of health and fitness are decreasing. What do you think are the causes of these problems and what measures could be taken to solve them?",
            category="two_part",
            source="local_seed",
        )
        self.create_prompt(
            prompt_id="task2-pattern-value-arguments",
            task_type=WritingPrompt.TaskType.TASK2,
            title="School Holidays",
            prompt="In many countries, primary and secondary schools close for two months or more in the summer holidays.\n\nWhat is the value of long school holidays? What are the arguments in favour of shorter school holidays?",
            category="two_part",
            source="local_seed",
        )
        self.create_prompt(
            prompt_id="task2-pattern-extent-think",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Recycling Laws",
            prompt="Some people claim that not enough of the waste from homes is recycled.\n\nTo what extent do you think laws are needed to make people recycle more of their waste?",
            category="opinion",
            source="local_seed",
        )
        self.create_prompt(
            prompt_id="task2-pattern-factors-realistic",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Job Satisfaction",
            prompt="As most people spend a major part of their adult life at work, job satisfaction is an important element of individual wellbeing.\n\nWhat factors contribute to job satisfaction? How realistic is the expectation of job satisfaction for all workers?",
            category="two_part",
            source="local_seed",
        )

        discussion = self.client.get("/api/writing/prompts?task_type=task2&prompt_pattern=discussion_opinion")
        self.assertEqual(discussion.status_code, 200)
        discussion_payload = discussion.json()
        discussion_ids = {item["id"] for item in discussion_payload["items"]}
        self.assertIn("task2-pattern-discussion", discussion_ids)
        self.assertIn("task2-pattern-discussion-singular-view", discussion_ids)
        self.assertIn("task2-pattern-discussion-sides", discussion_ids)
        self.assertIn("task2-pattern-discussion-short", discussion_ids)
        self.assertIn("task2-pattern-value-arguments", discussion_ids)
        self.assertNotIn("task2-pattern-positive-negative", discussion_ids)
        self.assertTrue(all(item["prompt_pattern"] == "discussion_opinion" for item in discussion_payload["items"]))
        self.assertIn("prompt_patterns", discussion_payload)
        self.assertNotIn("value_arguments", {item["pattern"] for item in discussion_payload["prompt_patterns"]})

        problem_solution = self.client.get("/api/writing/prompts?task_type=task2&prompt_pattern=problem_solution")
        self.assertEqual(problem_solution.status_code, 200)
        problem_solution_payload = problem_solution.json()
        problem_solution_ids = {item["id"] for item in problem_solution_payload["items"]}
        self.assertIn("task2-pattern-positive-negative-with-first-question", problem_solution_ids)
        self.assertIn("task2-pattern-positive-negative-missing-words", problem_solution_ids)
        self.assertIn("task2-pattern-positive-negative-situation", problem_solution_ids)
        self.assertIn("task2-pattern-reasons-research", problem_solution_ids)
        self.assertIn("task2-pattern-causes-effects", problem_solution_ids)
        self.assertIn("task2-pattern-health-causes-measures", problem_solution_ids)
        self.assertIn("task2-pattern-factors-realistic", problem_solution_ids)
        self.assertTrue(all(item["prompt_pattern"] == "problem_solution" for item in problem_solution_payload["items"]))
        self.assertTrue(all(item["prompt_pattern_label"] == "Why / What reasons / solutions?" for item in problem_solution_payload["items"]))

        causes_effects_alias = self.client.get("/api/writing/prompts?task_type=task2&prompt_pattern=causes_effects")
        self.assertEqual(causes_effects_alias.status_code, 200)
        self.assertIn("task2-pattern-causes-effects", {item["id"] for item in causes_effects_alias.json()["items"]})
        self.assertTrue(all(item["prompt_pattern"] == "problem_solution" for item in causes_effects_alias.json()["items"]))

        positive_negative = self.client.get("/api/writing/prompts?task_type=task2&prompt_pattern=positive_negative_do_you_think")
        self.assertEqual(positive_negative.status_code, 200)
        positive_payload = positive_negative.json()
        positive_ids = {item["id"] for item in positive_payload["items"]}
        self.assertIn("task2-pattern-positive-negative", positive_ids)
        self.assertIn("task2-pattern-positive-negative-no-second-article", positive_ids)
        self.assertIn("task2-pattern-positive-negative-has-this-become", positive_ids)
        self.assertNotIn("task2-pattern-positive-negative-with-first-question", positive_ids)
        self.assertNotIn("task2-pattern-positive-negative-missing-words", positive_ids)
        self.assertNotIn("task2-pattern-positive-negative-situation", positive_ids)
        self.assertNotIn("task2-pattern-discussion", positive_ids)
        self.assertTrue(all(item["prompt_pattern"] == "positive_negative_do_you_think" for item in positive_payload["items"]))
        self.assertTrue(all(item["prompt_pattern_label"] for item in positive_payload["items"]))
        self.assertTrue(all(item["prompt_pattern_label"] == "a positive or a negative development?" for item in positive_payload["items"]))

        has_this_become = self.client.get("/api/writing/prompts?task_type=task2&prompt_pattern=positive_negative_has_this_become")
        self.assertEqual(has_this_become.status_code, 200)
        self.assertIn("task2-pattern-positive-negative-has-this-become", {item["id"] for item in has_this_become.json()["items"]})
        self.assertTrue(all(item["prompt_pattern"] == "positive_negative_do_you_think" for item in has_this_become.json()["items"]))

        benefits = self.client.get("/api/writing/prompts?task_type=task2&prompt_pattern=benefits_outweigh_disadvantages")
        self.assertEqual(benefits.status_code, 200)
        benefits_payload = benefits.json()
        benefits_items = {item["id"]: item for item in benefits_payload["items"]}
        self.assertIn("task2-pattern-benefits-outweigh", benefits_items)
        self.assertIn("task2-pattern-benefits-outweigh-drawbacks", benefits_items)
        self.assertIn("task2-pattern-negative-effect-outweigh", benefits_items)
        self.assertIn("task2-pattern-extent-advantages-outweigh", benefits_items)
        self.assertEqual(benefits_items["task2-pattern-benefits-outweigh"]["prompt_pattern"], "advantages_outweigh")
        self.assertEqual(benefits_items["task2-pattern-benefits-outweigh"]["prompt_pattern_label"], "Do the advantages outweigh the disadvantages?")

        agree = self.client.get("/api/writing/prompts?task_type=task2&prompt_pattern=agree_to_what_extent")
        self.assertEqual(agree.status_code, 200)
        agree_items = {item["id"]: item for item in agree.json()["items"]}
        self.assertIn("task2-pattern-agree", agree_items)
        self.assertIn("task2-pattern-agree-typo", agree_items)
        self.assertIn("task2-pattern-agree-extend-typo", agree_items)
        self.assertIn("task2-pattern-extent-think", agree_items)
        self.assertTrue(all(item["prompt_pattern"] == "agree_to_what_extent" for item in agree_items.values()))

        agree_alias = self.client.get("/api/writing/prompts?task_type=task2&prompt_pattern=agree_do_you_agree")
        self.assertEqual(agree_alias.status_code, 200)
        self.assertEqual({item["id"] for item in agree_alias.json()["items"]}, set(agree_items))

        value_arguments = self.client.get("/api/writing/prompts?task_type=task2&prompt_pattern=value_arguments")
        self.assertEqual(value_arguments.status_code, 200)
        value_arguments_payload = value_arguments.json()
        self.assertIn("task2-pattern-value-arguments", {item["id"] for item in value_arguments_payload["items"]})
        self.assertTrue(all(item["prompt_pattern"] == "discussion_opinion" for item in value_arguments_payload["items"]))
        self.assertTrue(all(item["prompt_pattern_label"] == "Discuss both views and give your own opinion." for item in value_arguments_payload["items"]))

        random_response = self.client.post(
            "/api/writing/prompts/random",
            data={"task_type": "task2", "prompt_pattern": "problem_solution"},
            content_type="application/json",
        )
        self.assertEqual(random_response.status_code, 200)
        self.assertEqual(random_response.json()["prompt_pattern"], "problem_solution")

    def test_cambridge_task2_why_reason_solution_patterns_are_not_split_by_old_categories(self):
        from apps.writing.prompt_services import sync_seed_prompts

        sync_seed_prompts()
        response = self.client.get("/api/writing/prompts?task_type=task2&prompt_pattern=problem_solution")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = {item["id"] for item in payload["items"]}
        expected_cambridge_ids = {
            "cambridge-7-test-3-task-2",
            "cambridge-8-test-4-task-2",
            "cambridge-13-test-4-task-2",
            "cambridge-14-test-4-task-2",
            "cambridge-15-test-1-task-2",
            "cambridge-16-test-1-task-2",
            "cambridge-16-test-2-task-2",
            "cambridge-17-test-2-task-2",
        }
        self.assertTrue(expected_cambridge_ids <= ids)
        cambridge_items = [item for item in payload["items"] if item["id"] in expected_cambridge_ids]
        self.assertEqual(len(cambridge_items), len(expected_cambridge_ids))
        self.assertTrue(all(item["prompt_pattern"] == "problem_solution" for item in cambridge_items))
        self.assertTrue(all(item["prompt_pattern_label"] == "Why / What reasons / solutions?" for item in cambridge_items))

        positive_response = self.client.get("/api/writing/prompts?task_type=task2&prompt_pattern=positive_negative_do_you_think")
        self.assertEqual(positive_response.status_code, 200)
        positive_ids = {item["id"] for item in positive_response.json()["items"]}
        self.assertFalse(expected_cambridge_ids & positive_ids)

    def test_invalid_writing_requests_return_json_errors(self):
        bad_prompt_type = self.client.get("/api/writing/prompts?task_type=unknown")
        self.assertEqual(bad_prompt_type.status_code, 400)

        missing_prompt = self.client.post("/api/writing/entries", data={"task_type": "task2", "answer": "hello"}, content_type="application/json")
        self.assertEqual(missing_prompt.status_code, 400)

        missing_entry = self.client.get("/api/writing/entries/not-found")
        self.assertEqual(missing_entry.status_code, 404)

    def test_agent_prompt_search_returns_deep_links_without_source_access(self):
        user = get_user_model().objects.create_user(username="agent-searcher", password="test-pass")
        self.client.force_login(user)
        target = self.create_prompt(
            prompt_id="reported-cn-task2-2015-05-30-20",
            task_type=WritingPrompt.TaskType.TASK2,
            title="2015.05.30 Computer and Internet Education",
            prompt="Some people think computers and the Internet are more important in child's education. Others believe that schools and teachers are essential for children to learn. Discuss both views and give your opinion.",
            category="discussion",
            source="reported_actual_engopen",
        )
        self.create_prompt(
            prompt_id="other-task2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Traffic",
            prompt="Some people think traffic should be reduced by public transport.",
            category="opinion",
        )

        response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "computer Internet children study schools teachers", "task_type": "task2", "limit": "1"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        item = payload["items"][0]
        self.assertEqual(item["id"], target.prompt_id)
        self.assertIn("?view=writing&task=task2&prompt=reported-cn-task2-2015-05-30-20", item["url"])
        self.assertGreater(item["match_score"], 0.5)

    def test_agent_prompt_search_uses_hybrid_semantic_retrieval(self):
        self.create_prompt(
            prompt_id="reported-cn-task2-education-unique",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Education and online technology",
            prompt="Some people think technology and the Internet are more important in children's education than schools and teachers. Discuss both views and give your opinion.",
            category="discussion",
            source="reported_actual_engopen",
        )
        self.create_prompt(
            prompt_id="reported-cn-task2-traffic",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Traffic and public transport",
            prompt="Some people think traffic congestion should be reduced by improving public transport. To what extent do you agree?",
            category="opinion",
            source="reported_actual_engopen",
        )

        response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "technology internet education schools teachers", "task_type": "task2", "limit": "20"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["count"], 1)
        item = payload["items"][0]
        self.assertIn(item["match_type"], {"semantic", "bm25"})
        self.assertGreater(item["semantic_score"], 0)
        self.assertTrue({"technology", "computer", "internet"} & set(item["matched_terms"]))
        self.assertIn("learn", item["prompt"].lower())

    def test_agent_prompt_search_handles_chinese_water_free_waste_query(self):
        target = self.create_prompt(
            prompt_id="cambridge-20-test-1-task-2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Clean water should be free",
            prompt="Access to clean water is a basic human right. Therefore, every home should have a water supply that is provided free of charge. To what extent do you agree or disagree?",
            category="opinion",
            source_book=20,
            source_test=1,
            source_question=2,
            source="cambridge",
        )
        self.create_prompt(
            prompt_id="cambridge-11-test-2-task-2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Household waste recycling",
            prompt="Some people claim that not enough household waste is recycled. They say that the only way to increase recycling is for governments to make it a legal requirement.",
            category="opinion",
            source_book=11,
            source_test=2,
            source_question=2,
            source="cambridge",
        )
        self.create_prompt(
            prompt_id="task1-water-line",
            task_type=WritingPrompt.TaskType.TASK1_ACADEMIC,
            title="Water consumption line graph",
            prompt="The line graph shows water consumption in three countries over time.",
            category="line_graph",
        )

        response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "clean water free", "task_type": "task2", "limit": "5"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["count"], 1)
        item = payload["items"][0]
        self.assertEqual(item["id"], target.prompt_id)
        self.assertGreater(item["match_score"], 0.25)
        self.assertIn("water", item["matched_terms"])
        self.assertIn("free", item["matched_terms"])
        self.assertIn(item["match_type"], {"bm25", "semantic"})

    def test_agent_prompt_search_chinese_recycling_query_prefers_waste_prompt(self):
        target = self.create_prompt(
            prompt_id="cambridge-11-test-2-task-2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Household waste recycling",
            prompt="Some people claim that not enough household waste is recycled. They say that the only way to increase recycling is for governments to make it a legal requirement.",
            category="opinion",
            source_book=11,
            source_test=2,
            source_question=2,
            source="cambridge",
        )
        self.create_prompt(
            prompt_id="cambridge-20-test-1-task-2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Clean water should be free",
            prompt="Access to clean water is a basic human right. Therefore, every home should have a water supply that is provided free of charge.",
            category="opinion",
            source_book=20,
            source_test=1,
            source_question=2,
            source="cambridge",
        )

        response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "household waste recycling", "task_type": "task2", "limit": "3"},
        )

        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["id"], target.prompt_id)
        self.assertIn("waste", item["matched_terms"])
        self.assertIn("recycle", item["matched_terms"])

    def test_agent_prompt_search_chinese_task1_population_visual_query(self):
        self.create_prompt(
            prompt_id="task1-population-table-unique",
            task_type=WritingPrompt.TaskType.TASK1_ACADEMIC,
            title="Population table",
            prompt="The table shows the population of three cities in 1990, 2000 and 2010.",
            category="table",
        )
        self.create_prompt(
            prompt_id="task2-city-life",
            task_type=WritingPrompt.TaskType.TASK2,
            title="City life",
            prompt="Some people believe city life is becoming more stressful.",
            category="opinion",
        )

        response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "population table", "task_type": "task1_academic", "limit": "3"},
        )

        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertIn("population", item["prompt"].lower())
        self.assertIn("population", item["matched_terms"])
        self.assertTrue({"table", "graph", "chart"} & set(item["matched_terms"]))

    def test_agent_prompt_search_chinese_decision_query_matches_choices(self):
        target = self.create_prompt(
            prompt_id="cambridge-13-test-2-task-2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Too Many Choices",
            prompt="In many countries, people now have more choices than ever before. To what extent do you agree or disagree?",
            category="opinion",
            source_book=13,
            source_test=2,
            source_question=2,
            source="cambridge",
        )
        self.create_prompt(
            prompt_id="traffic-filler",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Traffic",
            prompt="Some people think traffic should be reduced by public transport.",
            category="opinion",
        )

        response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "many choices decision", "task_type": "task2", "limit": "3"},
        )

        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["id"], target.prompt_id)
        self.assertIn("choice", item["matched_terms"])
        self.assertIn("decision_choice", item["matched_concepts"])

    def test_agent_prompt_search_chinese_late_query_matches_delay(self):
        target = self.create_prompt(
            prompt_id="delay-punctuality-task2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Punctuality",
            prompt="Some people think being late is unacceptable, while others believe delays are sometimes unavoidable. Discuss both views and give your opinion.",
            category="discussion",
        )
        self.create_prompt(
            prompt_id="water-filler",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Water",
            prompt="Access to clean water is a basic human right.",
            category="opinion",
        )

        response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "late delay punctuality", "task_type": "task2", "limit": "3"},
        )

        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["id"], target.prompt_id)
        self.assertIn("late", item["matched_terms"])
        self.assertIn("lateness_delay", item["matched_concepts"])

    def test_agent_prompt_search_chinese_weekend_query_matches_weekend_and_holiday_prompts(self):
        weekend_prompt = self.create_prompt(
            prompt_id="cambridge-19-test-2-task-2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Shorter Working Week",
            prompt="The working week should be shorter and workers should have a longer weekend. Do you agree or disagree?",
            category="opinion",
            source_book=19,
            source_test=2,
            source_question=2,
            source="cambridge",
        )
        holiday_prompt = self.create_prompt(
            prompt_id="cambridge-20-test-2-task-2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="School Holidays",
            prompt="In many countries, primary and secondary schools close for two months or more in the summer holidays. What is the value of long school holidays? What are the arguments in favour of shorter school holidays?",
            category="two_part",
            source_book=20,
            source_test=2,
            source_question=2,
            source="cambridge",
        )
        self.create_prompt(
            prompt_id="water-filler-weekend-query",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Water",
            prompt="Access to clean water is a basic human right.",
            category="opinion",
        )

        response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "weekend holiday", "task_type": "task2", "limit": "5"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = [item["id"] for item in payload["items"]]
        self.assertIn(weekend_prompt.prompt_id, ids)
        self.assertIn(holiday_prompt.prompt_id, ids)
        top_ids = ids[:2]
        self.assertTrue(any(item_id in top_ids for item_id in {weekend_prompt.prompt_id, "reported-cn-task2-2021-04-17-17"}))
        weekend_item = next(item for item in payload["items"] if item["id"] == weekend_prompt.prompt_id)
        self.assertIn("weekend", weekend_item["matched_terms"])
        self.assertIn("leisure_holiday", weekend_item["matched_concepts"])

    def test_agent_prompt_search_chinese_topic_audit_covers_cambridge_themes(self):
        fixtures = [
            (
                "home ownership rent",
                "cambridge-15-test-1-task-2",
                "Home Ownership",
                "In some countries, owning a home rather than renting one is very important for people.",
                "city_housing",
            ),
            (
                "building history",
                "cambridge-16-test-1-task-2",
                "Building History",
                "People are becoming interested in finding out about the history of the house or building they live in.",
                "building_history",
            ),
            (
                "species loss animals plants",
                "cambridge-14-test-2-task-2",
                "Species Loss",
                "The main environmental problem of our time is the loss of particular species of plants and animals.",
                "animals_nature",
            ),
            (
                "foreign language travel work",
                "cambridge-11-test-3-task-2",
                "Foreign Languages",
                "Some people say that the only reason for learning a foreign language is to travel to or work in a foreign country.",
                "culture_language",
            ),
            (
                "language loss fewer languages",
                "cambridge-9-test-4-task-2",
                "Language Loss",
                "Every year several languages die out. Some people think life will be easier if there are fewer languages.",
                "culture_language",
            ),
            (
                "global fashion dress clothes",
                "cambridge-20-test-4-task-2",
                "Global Fashion",
                "Many aspects of the way people dress today are influenced by global fashion trends.",
                "tourism_globalization",
            ),
            (
                "information sharing scientific research business academic",
                "cambridge-12-test-1-task-2",
                "Information Sharing",
                "It is good to share as much information as possible in scientific research, business and the academic world.",
                "science_information",
            ),
            (
                "most important aim of science improve people lives",
                "cambridge-18-test-1-task-2",
                "Science Aim",
                "The most important aim of science should be to improve people's lives.",
                "science_aim",
            ),
            (
                "competition cooperation work school",
                "cambridge-19-test-1-task-2",
                "Competition And Cooperation",
                "Competition at work, at school and in daily life is a good thing, while others believe we should cooperate more.",
                "competition_cooperation",
            ),
            (
                "printed books online",
                "cambridge-15-test-2-task-2",
                "Printed Books",
                "Nobody will buy printed books or newspapers because they will be able to read everything online.",
                "reading_books",
            ),
            (
                "ageing population elderly",
                "cambridge-18-test-4-task-2",
                "Ageing Population",
                "An ageing population creates problems for governments, while others think there are benefits if society has more elderly people.",
                "ageing_population",
            ),
            (
                "driverless vehicles passengers cars buses trucks",
                "cambridge-16-test-4-task-2",
                "Driverless Vehicles",
                "In the future all cars, buses and trucks will be driverless and passengers will travel inside these vehicles.",
                "driverless_vehicle",
            ),
            (
                "sugary products obesity",
                "cambridge-16-test-3-task-2",
                "Sugary Products",
                "Manufactured food and drink products contain high levels of sugar and sugary products should be made more expensive.",
                "sugar_obesity",
            ),
            (
                "alternative medicine treatment doctor",
                "cambridge-17-test-4-task-2",
                "Alternative Medicine",
                "People with health problems are trying alternative medicines and treatments instead of visiting their usual doctor.",
                "medical_treatment",
            ),
            (
                "community service charity",
                "cambridge-9-test-2-task-2",
                "Community Service",
                "Unpaid community service should be a compulsory part of high school programmes, for example working for a charity.",
                "community_charity",
            ),
            (
                "air travel pollution environmental benefits",
                "cambridge-20-test-3-task-2",
                "Air Travel",
                "Some people have decided to reduce the number of times they fly every year or to stop flying altogether because of environmental benefits.",
                "air_travel_pollution",
            ),
        ]
        for index, (_, prompt_id, title, prompt, _) in enumerate(fixtures, start=1):
            self.create_prompt(
                prompt_id=prompt_id,
                task_type=WritingPrompt.TaskType.TASK2,
                title=title,
                prompt=prompt,
                category="opinion",
                source_book=20 if "20" in prompt_id else None,
                source_test=index,
                source_question=2,
                source="cambridge",
            )

        for query, expected_id, _, _, expected_concept in fixtures:
            with self.subTest(query=query):
                response = self.client.get(
                    "/api/agent/writing/prompts/search",
                    {"q": query, "task_type": "task2", "limit": "8"},
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                ids = [item["id"] for item in payload["items"]]
                self.assertIn(expected_id, ids)
                matched = next(item for item in payload["items"] if item["id"] == expected_id)
                self.assertGreater(matched["match_score"], 0.18)
                self.assertIn(expected_concept, matched["matched_concepts"])

    def test_agent_prompt_search_chinese_task1_compound_queries_prefer_visual_prompts(self):
        rent_chart = self.create_prompt(
            prompt_id="reported-task1-weekly-rent",
            task_type=WritingPrompt.TaskType.TASK1_ACADEMIC,
            title="Weekly rent chart",
            prompt="The chart shows the average weekly rent for houses and apartments in three cities.",
            category="bar_chart",
            source="reported_actual_engopen",
        )
        student_table = self.create_prompt(
            prompt_id="reported-task1-international-students",
            task_type=WritingPrompt.TaskType.TASK1_ACADEMIC,
            title="International students table",
            prompt="The table shows the number of international students from different countries studying in Canada and the USA.",
            category="table",
            source="reported_actual_engopen",
        )
        self.create_prompt(
            prompt_id="task2-international-student-filler",
            task_type=WritingPrompt.TaskType.TASK2,
            title="International students",
            prompt="Some people think international students should work after graduation.",
            category="opinion",
        )

        rent_response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "weekly rent chart", "limit": "5"},
        )
        self.assertEqual(rent_response.status_code, 200)
        rent_payload = rent_response.json()
        self.assertEqual(rent_payload["items"][0]["task_type"], WritingPrompt.TaskType.TASK1_ACADEMIC)
        self.assertTrue(
            rent_chart.prompt_id in [item["id"] for item in rent_payload["items"]]
            or "rent" in " ".join(rent_payload["items"][0]["matched_terms"])
        )

        student_response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "international students table Canada USA", "limit": "5"},
        )
        self.assertEqual(student_response.status_code, 200)
        student_payload = student_response.json()
        self.assertEqual(student_payload["items"][0]["task_type"], WritingPrompt.TaskType.TASK1_ACADEMIC)
        self.assertTrue({"student", "table", "graph", "chart"} & set(student_payload["items"][0]["matched_terms"]))

    def test_agent_prompt_search_keeps_small_bank_fast(self):
        target = self.create_prompt(
            prompt_id="cambridge-20-test-1-task-2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Clean water should be free",
            prompt="Access to clean water is a basic human right. Therefore, every home should have a water supply that is provided free of charge.",
            category="opinion",
            source_book=20,
            source_test=1,
            source_question=2,
            source="cambridge",
        )
        for index in range(220):
            self.create_prompt(
                prompt_id=f"filler-task2-{index}",
                task_type=WritingPrompt.TaskType.TASK2,
                title=f"Filler topic {index}",
                prompt=f"Some people discuss topic number {index} about society and work.",
                category="opinion",
            )

        started = time.perf_counter()
        response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "clean water free", "task_type": "task2", "limit": "5"},
        )
        elapsed_ms = (time.perf_counter() - started) * 1000

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["id"], target.prompt_id)
        self.assertLess(elapsed_ms, 500)

    def test_agent_prompt_search_cache_refreshes_after_prompt_insert(self):
        self.create_prompt(
            prompt_id="task2-initial-unrelated-cache",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Initial unrelated cache",
            prompt="Some people discuss city transport and public roads.",
            category="opinion",
        )

        first_response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "cacheonly hydrosolar", "task_type": "task2", "limit": "3"},
        )
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json()["items"], [])

        target = self.create_prompt(
            prompt_id="task2-new-hydrosolar",
            task_type=WritingPrompt.TaskType.TASK2,
            title="New hydrosolar water supply",
            prompt="Every hydrosolar home should have a clean water supply.",
            category="opinion",
        )

        second_response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "hydrosolar", "task_type": "task2", "limit": "3"},
        )

        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json()["items"][0]["id"], target.prompt_id)

    def test_agent_prompt_search_handles_common_typos_without_heavy_dependencies(self):
        museum = self.create_prompt(
            prompt_id="cambridge-10-test-4-task-2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Museums admission charges",
            prompt="Many museums charge for admission while others are free.",
            category="advantages_disadvantages",
            source_book=10,
            source_test=4,
            source_question=2,
            source="cambridge",
        )
        self.create_prompt(
            prompt_id="cambridge-20-test-1-task-2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Clean water should be free",
            prompt="Access to clean water is a basic human right and every home should have a water supply that is provided free of charge.",
            category="opinion",
            source_book=20,
            source_test=1,
            source_question=2,
            source="cambridge",
        )

        museum_response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "musem free admision charge", "task_type": "task2", "limit": "3"},
        )
        water_response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "fresh water goverment controll", "task_type": "task2", "limit": "3"},
        )

        self.assertEqual(museum_response.status_code, 200)
        self.assertEqual(museum_response.json()["items"][0]["id"], museum.prompt_id)
        self.assertEqual(water_response.status_code, 200)
        water_item = water_response.json()["items"][0]
        self.assertIn("water", water_item["matched_concepts"])
        self.assertIn("public_services", water_item["matched_concepts"])
        self.assertIn("water", water_item["prompt"].lower())

    def test_agent_prompt_search_does_not_treat_salary_as_water(self):
        self.create_prompt(
            prompt_id="task2-work-salary",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Work and salary",
            prompt="Some people choose a job mainly because of salary and company benefits.",
            category="opinion",
        )
        self.create_prompt(
            prompt_id="cambridge-20-test-1-task-2",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Clean water should be free",
            prompt="Access to clean water is a basic human right and every home should have a water supply that is provided free of charge.",
            category="opinion",
            source_book=20,
            source_test=1,
            source_question=2,
            source="cambridge",
        )

        response = self.client.get(
            "/api/agent/writing/prompts/search",
            {"q": "competition cooperation work school", "task_type": "task2", "limit": "3"},
        )

        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["id"], "task2-work-salary")
        self.assertIn("work", item["matched_concepts"])
