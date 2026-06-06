import json
import time
import uuid
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone

from apps.ai.models import AITask
from apps.ai.orchestration import cancel_billable_ai_task
from apps.ai.services import claim_ai_task
from apps.billing.models import TokenWallet, WalletLedgerEntry
from apps.billing.services import DEFAULT_INITIAL_GRANT_U
from apps.writing.models import WritingEntry, WritingLearnerProfile, WritingPrompt, WritingScore
from apps.writing.services import WRITING_TASK_LABELS, WritingError, complete_score_task, fallback_score_task


def paragraph_answer(*parts: str) -> str:
    return "\n\n".join(parts)


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
        "spelling_correction_summary": "未发现明显拼写错误。",
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
            primary_focus_text="句子结构和语法准确度是当前重点。",
            recent_evidence=["Task 2 · Band 5.0 · 120 words"],
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

    def test_saving_changed_scored_entry_creates_revision_instead_of_deleting_report(self):
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
        revision = response.json()
        self.assertNotEqual(revision["id"], entry.entry_id)
        self.assertEqual(revision["status"], WritingEntry.Status.SAVED)
        self.assertIsNone(revision["score"])
        self.assertEqual(revision["answer"], "Revised paragraph one.\n\nRevised paragraph two.")
        entry.refresh_from_db()
        self.assertEqual(entry.answer, "Original paragraph one.\n\nOriginal paragraph two.")
        self.assertEqual(entry.status, WritingEntry.Status.SCORED)
        self.assertTrue(WritingScore.objects.filter(entry=entry, overall_band=6.0).exists())

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

    def test_writing_reports_order_by_latest_task_update_time(self):
        now = timezone.now()
        report_prompt = self.create_prompt(
            prompt_id="task2-reports-latest-activity",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Latest activity prompt",
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
        newer_entry = self.create_entry(
            prompt=report_prompt,
            answer="Newer saved entry that should sort after the task-updated item.",
            updated_at=now - timezone.timedelta(hours=1),
        )

        task_payload = self.client.post(
            f"/api/writing/entries/{older_entry.entry_id}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        ).json()["task"]
        task = AITask.objects.get(task_id=task_payload["id"])
        older_created_at = now - timezone.timedelta(hours=2)
        latest_task_update = now
        AITask.objects.filter(pk=task.pk).update(created_at=older_created_at, updated_at=latest_task_update)

        response = self.client.get("/api/writing/reports")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["id"] for item in payload["items"][:2]], [older_entry.entry_id, newer_entry.entry_id])
        self.assertEqual(
            payload["items"][0]["display_time"],
            latest_task_update.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%d %H:%M"),
        )

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
            self.create_entry(
                prompt=task2_prompt,
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

    def test_saving_changed_answer_on_scored_entry_creates_revision(self):
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
        self.assertNotEqual(changed_payload["id"], save["id"])
        self.assertEqual(changed_payload["status"], WritingEntry.Status.SAVED)
        self.assertIsNone(changed_payload["score"])
        self.assertTrue(WritingScore.objects.filter(entry__entry_id=save["id"]).exists())
        original = WritingEntry.objects.get(entry_id=save["id"])
        self.assertEqual(original.answer, "First answer with a clear position.\n\nSecond paragraph adds a basic supporting reason.")

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
        self.assertIn("第 2-3 段", payload["paragraph_guidance"]["tips"][1])

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
        self.assertEqual(score.analysis_payload["spelling_correction_summary"], "未发现明显拼写错误。")
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
            title="2015.05.30 大作文真题",
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
            {"q": "孩子线上学习 科技 比 老师 学校 更重要", "task_type": "task2", "limit": "20"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["count"], 1)
        item = payload["items"][0]
        self.assertIn(item["match_type"], {"semantic", "bm25"})
        self.assertGreater(item["semantic_score"], item["keyword_score"])
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
            {"q": "水 浪费 免费", "task_type": "task2", "limit": "5"},
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
            {"q": "浪费 回收 垃圾", "task_type": "task2", "limit": "3"},
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
            {"q": "人口 图表", "task_type": "task1_academic", "limit": "3"},
        )

        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertIn("population", item["prompt"].lower())
        self.assertIn("population", item["matched_terms"])
        self.assertTrue({"table", "graph", "chart"} & set(item["matched_terms"]))

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
            {"q": "免费 供水", "task_type": "task2", "limit": "5"},
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
        self.assertIn("government", water_item["matched_concepts"])
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
            {"q": "工作 薪水 公司", "task_type": "task2", "limit": "3"},
        )

        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["id"], "task2-work-salary")
        self.assertIn("work", item["matched_concepts"])
