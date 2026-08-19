import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import resolve

from apps.writing import views as writing_views
from apps.writing.models import CustomWritingPrompt, WritingEntry


class CustomWritingPromptApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="custom-writing-owner", password="test-pass")
        self.other_user = user_model.objects.create_user(username="custom-writing-other", password="test-pass")
        self.client = Client()
        self.client.force_login(self.user)

    def create_prompt(self, content="To what extent do you agree or disagree?", **extra):
        response = self.client.post(
            "/api/writing/custom-prompts",
            data=json.dumps({"task_type": "task2", "prompt_markdown": content, **extra}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_crud_routes_exist_and_are_owner_scoped(self):
        self.assertIs(resolve("/api/writing/custom-prompts").func, writing_views.custom_prompts)
        prompt = self.create_prompt()
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get("/api/writing/custom-prompts?task_type=task2").json()["items"], [])
        self.assertEqual(self.client.delete(f"/api/writing/custom-prompts/{prompt['id']}").status_code, 404)

    def test_auto_classifies_and_keeps_generated_title_stable(self):
        prompt = self.create_prompt()
        self.assertEqual(prompt["category"], "opinion")
        self.assertEqual(prompt["prompt_pattern"], "agree_to_what_extent")
        self.assertRegex(prompt["title"], r"^\d{4}-\d{2}-\d{2} · 观点类$")

        changed = self.client.patch(
            f"/api/writing/custom-prompts/{prompt['id']}",
            data=json.dumps({"prompt_markdown": "Discuss both these views and give your own opinion."}),
            content_type="application/json",
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.json()["title"], prompt["title"])
        self.assertEqual(changed.json()["category"], "discussion")

    def test_edit_and_delete_preserve_existing_entry_snapshot(self):
        prompt = self.create_prompt(content="**Discuss both views and give your own opinion.**")
        saved = self.client.post(
            "/api/writing/entries",
            data=json.dumps({
                "task_type": "task2",
                "custom_prompt_id": prompt["id"],
                "prompt": prompt["prompt_markdown"],
                "title": prompt["title"],
                "answer": "This answer must survive prompt edits and deletion.",
            }),
            content_type="application/json",
        )
        self.assertEqual(saved.status_code, 200, saved.content)
        entry_id = saved.json()["id"]

        self.client.patch(
            f"/api/writing/custom-prompts/{prompt['id']}",
            data=json.dumps({"prompt_markdown": "A completely different prompt."}),
            content_type="application/json",
        )
        self.assertEqual(self.client.delete(f"/api/writing/custom-prompts/{prompt['id']}").status_code, 200)

        entry = WritingEntry.objects.get(entry_id=entry_id)
        self.assertIsNone(entry.custom_prompt_id)
        self.assertEqual(entry.prompt_text, "**Discuss both views and give your own opinion.**")
        self.assertEqual((entry.metadata or {}).get("custom_prompt_id"), prompt["id"])
        self.assertFalse(CustomWritingPrompt.objects.filter(pk=prompt["id"]).exists())

    def test_custom_prompt_reopens_and_updates_the_single_maintained_essay(self):
        prompt = self.create_prompt(content="To what extent do you agree or disagree?")
        first = self.client.post(
            "/api/writing/entries",
            data=json.dumps({
                "task_type": "task2",
                "custom_prompt_id": prompt["id"],
                "prompt": prompt["prompt_markdown"],
                "title": prompt["title"],
                "answer": "First maintained answer.",
            }),
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200, first.content)

        reopened = self.client.get(
            f"/api/writing/entry-for-prompt?task_type=task2&custom_prompt_id={prompt['id']}"
        )
        self.assertEqual(reopened.status_code, 200, reopened.content)
        self.assertEqual(reopened.json()["entry"]["id"], first.json()["id"])
        self.assertEqual(reopened.json()["entry"]["answer"], "First maintained answer.")

        second = self.client.post(
            "/api/writing/entries",
            data=json.dumps({
                "task_type": "task2",
                "custom_prompt_id": prompt["id"],
                "prompt": prompt["prompt_markdown"],
                "title": prompt["title"],
                "answer": "Updated maintained answer.",
            }),
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(WritingEntry.objects.filter(user=self.user, custom_prompt_id=prompt["id"]).count(), 1)

    def test_blank_and_duplicate_prompts_are_rejected(self):
        blank = self.client.post(
            "/api/writing/custom-prompts",
            data=json.dumps({"task_type": "task2", "prompt_markdown": "  "}),
            content_type="application/json",
        )
        self.assertEqual(blank.status_code, 400)
        self.create_prompt(content="Same prompt")
        duplicate = self.client.post(
            "/api/writing/custom-prompts",
            data=json.dumps({"task_type": "task2", "prompt_markdown": "  same   prompt  "}),
            content_type="application/json",
        )
        self.assertEqual(duplicate.status_code, 400)

    def test_plain_text_prompt_field_is_the_standard(self):
        # `prompt` is the plain-text field new clients send; content is stored
        # and returned verbatim — Markdown markers and newlines are content.
        content = "**Discuss both views** and give your own opinion.\n\nSecond line."
        response = self.client.post(
            "/api/writing/custom-prompts",
            data=json.dumps({"task_type": "task2", "prompt": content}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        prompt = response.json()
        self.assertEqual(prompt["prompt"], content)
        self.assertEqual(prompt["prompt_markdown"], content)
        self.assertEqual(prompt["category"], "discussion")

        changed = self.client.patch(
            f"/api/writing/custom-prompts/{prompt['id']}",
            data=json.dumps({"prompt": "To what extent do you agree or disagree?"}),
            content_type="application/json",
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.json()["prompt"], "To what extent do you agree or disagree?")

    def test_legacy_prompt_markdown_field_still_accepted(self):
        response = self.client.post(
            "/api/writing/custom-prompts",
            data=json.dumps({"task_type": "task2", "prompt_markdown": "Do the advantages outweigh the disadvantages?"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["prompt"], "Do the advantages outweigh the disadvantages?")

    def test_prompt_field_edit_keeps_entry_snapshot(self):
        prompt = self.create_prompt(content="To what extent do you agree or disagree?")
        saved = self.client.post(
            "/api/writing/entries",
            data=json.dumps({
                "task_type": "task2",
                "custom_prompt_id": prompt["id"],
                "prompt": prompt["prompt"],
                "title": prompt["title"],
                "answer": "Snapshot answer that must survive prompt edits.",
            }),
            content_type="application/json",
        )
        self.assertEqual(saved.status_code, 200, saved.content)
        entry_id = saved.json()["id"]

        changed = self.client.patch(
            f"/api/writing/custom-prompts/{prompt['id']}",
            data=json.dumps({"prompt": "A completely different prompt **with markers**."}),
            content_type="application/json",
        )
        self.assertEqual(changed.status_code, 200, changed.content)

        entry = WritingEntry.objects.get(entry_id=entry_id)
        self.assertEqual(entry.prompt_text, "To what extent do you agree or disagree?")
        self.assertEqual(entry.answer, "Snapshot answer that must survive prompt edits.")
