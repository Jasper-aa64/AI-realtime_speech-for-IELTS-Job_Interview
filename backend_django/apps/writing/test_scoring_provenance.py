import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.accounts.models import UserProfile
from apps.ai.services import claim_ai_task
from apps.writing.models import WritingEntry, WritingScore
from apps.writing.services import complete_score_task, create_score_task, fallback_score_task
from apps.writing.tests import ai_score_payload, paragraph_answer


class WritingScoringProvenanceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="scoring-provenance-user", password="test-pass")
        self.client = Client()
        self.client.force_login(self.user)

    def create_entry(self):
        prompt = self.create_prompt()
        payload = self.client.post(
            "/api/writing/entries",
            data=json.dumps({
                "task_type": "task2",
                "prompt_id": prompt.prompt_id,
                "prompt": prompt.prompt,
                "answer": paragraph_answer(
                    "Online learning can be useful because students can review lessons at any time.",
                    "However, classrooms still provide direct support and immediate interaction.",
                ),
            }),
            content_type="application/json",
        ).json()
        return prompt, payload

    def create_prompt(self):
        from apps.writing.models import WritingPrompt
        return WritingPrompt.objects.create(
            prompt_id="provenance-prompt",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Provenance prompt",
            prompt="Some people think online learning is better than classroom learning. Discuss.",
        )

    def score_entry(self, entry_id, *, provider, model, force=False):
        payload = {"reserved_u": 300_000}
        if force:
            payload["force"] = True
        created = create_score_task(self.user, entry_id, payload)
        task_id = created["task"]["id"]
        claim_ai_task(task_id, worker_id="test-worker")
        completed = complete_score_task(
            task_id,
            {"score": ai_score_payload(), "usage": {"input_tokens": 1000, "output_tokens": 100}},
            provider=provider,
            model=model,
        )
        return completed

    def test_create_score_task_freezes_requested_provenance(self):
        UserProfile.objects.update_or_create(user=self.user, defaults={"report_ai_source": "claude"})
        _prompt, payload = self.create_entry()
        created = create_score_task(self.user, payload["id"], {"reserved_u": 300_000})
        task = created["task"]
        self.assertEqual(task["provider"], "claude")
        self.assertTrue(task["model"])
        request = self.client.get(f"/api/writing/entries/{payload['id']}").json()
        self.assertEqual(request["ai_task"]["request_payload"]["requested_provider"], "claude")
        self.assertTrue(request["ai_task"]["request_payload"]["requested_model"])

    def test_create_score_task_maps_gpt_profile_to_openai_provider(self):
        UserProfile.objects.update_or_create(user=self.user, defaults={"report_ai_source": "gpt"})
        _prompt, payload = self.create_entry()
        created = create_score_task(self.user, payload["id"], {"reserved_u": 300_000})
        self.assertEqual(created["task"]["provider"], "openai")

    def test_complete_score_task_persists_actual_model(self):
        _prompt, payload = self.create_entry()
        completed = self.score_entry(payload["id"], provider="claude", model="claude-sonnet-4-6")
        self.assertEqual(completed["score"]["scoring_provider"], "claude")
        self.assertEqual(completed["score"]["scoring_model"], "claude-sonnet-4-6")
        entry = WritingEntry.objects.get(entry_id=payload["id"])
        analysis = entry.score.analysis_payload
        self.assertEqual(analysis["scoring_provider"], "claude")
        self.assertEqual(analysis["scoring_model"], "claude-sonnet-4-6")

    def test_rescore_replaces_provenance_with_new_task_model(self):
        _prompt, payload = self.create_entry()
        self.score_entry(payload["id"], provider="claude", model="claude-sonnet-4-6")
        completed = self.score_entry(payload["id"], provider="openai", model="gpt-5.6-terra", force=True)
        self.assertEqual(completed["score"]["scoring_provider"], "openai")
        self.assertEqual(completed["score"]["scoring_model"], "gpt-5.6-terra")
        entry = WritingEntry.objects.get(entry_id=payload["id"])
        self.assertEqual(entry.score.analysis_payload["scoring_model"], "gpt-5.6-terra")

    def test_fallback_score_task_records_local_fallback(self):
        _prompt, payload = self.create_entry()
        created = create_score_task(self.user, payload["id"], {"reserved_u": 300_000})
        task_id = created["task"]["id"]
        claim_ai_task(task_id, worker_id="test-worker")
        fallback_score_task(task_id, reason="AI scoring unavailable")
        entry = WritingEntry.objects.get(entry_id=payload["id"])
        analysis = entry.score.analysis_payload
        self.assertEqual(analysis["scoring_provider"], "fallback")
        self.assertEqual(analysis["scoring_model"], "")
