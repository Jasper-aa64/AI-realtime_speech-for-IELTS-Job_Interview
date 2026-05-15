from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.ai.models import AITask
from apps.ai.services import claim_ai_task
from apps.billing.models import TokenWallet, WalletReservation
from apps.billing.services import DEFAULT_INITIAL_GRANT_U
from apps.writing.models import WritingEntry, WritingLearnerProfile, WritingPrompt, WritingScore
from apps.writing.services import WRITING_TASK_LABELS, complete_score_task, fallback_score_task


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

    def test_writing_api_requires_login(self):
        self.client.logout()
        response = self.client.get("/api/writing/summary")
        self.assertEqual(response.status_code, 401)

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
                "answer": "The chart shows a clear change in transport habits over time.",
                "practice_date": "2026-05-14",
            },
            content_type="application/json",
        )
        self.assertEqual(save.status_code, 200)
        saved = save.json()
        self.assertEqual(saved["status"], WritingEntry.Status.SAVED)
        self.assertEqual(saved["task_label"], WRITING_TASK_LABELS[WritingPrompt.TaskType.TASK1_ACADEMIC])
        self.assertGreater(saved["word_count"], 0)

        summary = self.client.get("/api/writing/summary?month=2026-05")
        self.assertEqual(summary.status_code, 200)
        summary_payload = summary.json()
        self.assertEqual(summary_payload["stats"]["practiced_days"], 1)
        self.assertIn(saved["id"], [item["id"] for item in summary_payload["recent_entries"]])
        self.assertEqual(next(day for day in summary_payload["days"] if day["date"] == "2026-05-14")["status"], "saved")

        detail = self.client.get(f"/api/writing/entries/{saved['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["answer"], saved["answer"])

        score = self.client.post(f"/api/writing/entries/{saved['id']}/score", content_type="application/json")
        self.assertEqual(score.status_code, 200)
        scored = score.json()
        self.assertEqual(scored["status"], WritingEntry.Status.SCORED)
        self.assertEqual(scored["score"]["backend"], "fallback")
        self.assertIn("AI 评分生成失败", scored["score"]["feedback_markdown"])
        self.assertEqual(scored["writing_profile"]["total_scored"], 1)

        summary_after_score = self.client.get("/api/writing/summary?month=2026-05").json()
        self.assertEqual(summary_after_score["stats"]["scored_entries"], 1)
        self.assertEqual(next(day for day in summary_after_score["days"] if day["date"] == "2026-05-14")["status"], "scored")

    def test_saving_changed_answer_resets_existing_score(self):
        prompt = WritingPrompt.objects.create(
            prompt_id="task2-api-reset",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Reset score prompt",
            prompt="Some people think cities should invest more in public transport. Discuss.",
        )
        save = self.client.post(
            "/api/writing/entries",
            data={"task_type": "task2", "prompt_id": prompt.prompt_id, "prompt": prompt.prompt, "answer": "First answer."},
            content_type="application/json",
        ).json()
        self.client.post(f"/api/writing/entries/{save['id']}/score", content_type="application/json")
        self.assertTrue(WritingScore.objects.filter(entry__entry_id=save["id"]).exists())

        changed = self.client.post(
            "/api/writing/entries",
            data={"id": save["id"], "task_type": "task2", "prompt_id": prompt.prompt_id, "prompt": prompt.prompt, "answer": "A changed answer with new wording."},
            content_type="application/json",
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["status"], WritingEntry.Status.SAVED)
        self.assertIsNone(changed.json()["score"])
        self.assertFalse(WritingScore.objects.filter(entry__entry_id=save["id"]).exists())

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
                "answer": "Technology can help students learn independently because they can review lessons and practise at their own pace.",
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
        self.assertEqual(task["status"], AITask.Status.PENDING)
        self.assertEqual(task["related_type"], "writing_entry")
        self.assertEqual(task["related_id"], save["id"])
        self.assertEqual(task["billing"]["reservation_id"], WalletReservation.objects.get(user=self.user).reservation_id)

        duplicate = self.client.post(
            f"/api/writing/entries/{save['id']}/score-task",
            data={"reserved_u": 300_000},
            content_type="application/json",
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertFalse(duplicate.json()["created"])
        self.assertEqual(duplicate.json()["task"]["id"], task["id"])
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U - 300_000)
        self.assertEqual(wallet.reserved_u, 300_000)
        self.assertEqual(WalletReservation.objects.filter(user=self.user).count(), 1)

        detail = self.client.get(f"/api/writing/entries/{save['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["ai_task"]["id"], task["id"])

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
                "answer": "Online learning can be useful because students can review lessons, but classrooms still provide direct support.",
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
                "score": {
                    "overall_band": 6.0,
                    "task_response": 6.0,
                    "coherence_cohesion": 6.0,
                    "lexical_resource": 6.0,
                    "grammatical_range_accuracy": 6.0,
                    "feedback_markdown": "- Clear position with room for more examples.",
                    "grammar_corrections": [],
                    "backend": "ai",
                },
                "usage": {"input_tokens": 1000, "output_tokens": 100},
            },
        )

        self.assertEqual(completed["status"], WritingEntry.Status.SCORED)
        self.assertEqual(completed["score"]["backend"], "ai")
        self.assertEqual(completed["writing_profile"]["total_scored"], 1)
        task = AITask.objects.get(task_id=task_payload["id"])
        self.assertEqual(task.status, AITask.Status.SUCCEEDED)
        self.assertIsNotNone(task.usage)
        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.SETTLED)
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.reserved_u, 0)

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
                "answer": "Homework can help students review lessons, but too much homework may reduce rest time.",
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
        self.assertIn("AI 评分生成失败", fallback["score"]["feedback_markdown"])
        task = AITask.objects.get(task_id=task_payload["id"])
        self.assertEqual(task.status, AITask.Status.FALLBACK)
        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.RELEASED)
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.reserved_u, 0)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U)

    def test_invalid_writing_requests_return_json_errors(self):
        bad_prompt_type = self.client.get("/api/writing/prompts?task_type=unknown")
        self.assertEqual(bad_prompt_type.status_code, 400)

        missing_prompt = self.client.post("/api/writing/entries", data={"task_type": "task2", "answer": "hello"}, content_type="application/json")
        self.assertEqual(missing_prompt.status_code, 400)

        missing_entry = self.client.get("/api/writing/entries/not-found")
        self.assertEqual(missing_entry.status_code, 404)
