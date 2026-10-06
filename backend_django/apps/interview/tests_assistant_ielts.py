"""The AI assistant in IELTS mode: an IELTS coach whose agent edits P1 / P2 / P3 answers, P2 material and Takeaway."""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.speaking import corpus_services as cs
from apps.speaking.models import LanguageTakeawayEntry, P1CorpusEntry, P2BankCorpusEntry, P2CorpusEntry, P3BankFollowupCorpusEntry

from . import ai_schema, assistant_ielts
from .models import InterviewAssistantThread as Thread

RUN = "apps.interview.assistant.ai_services.run_generation"


class IeltsAssistantTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ielts-owner", password="pw")
        self.client.force_login(self.user)
        p1, p2 = assistant_ielts._bank()
        self.topic, self.question = p1[3]
        self.cue = next(topic for topic in p2 if topic.get("p3_follow_ups"))
        self.cue_id = str(self.cue.get("cue_id") or cs.p2_cue_id(self.cue))

    def agent(self, message, actions, reply="好的", **extra):
        output = ai_schema.validate("assistant", {"reply": reply, "actions": actions}, {"domain": "ielts"})
        with patch(RUN, return_value={**output, "model": "gpt-6-luna", "elapsed_ms": 3000}) as run:
            response = self.client.post("/api/interview/assistant/", json.dumps({"message": message, "mode": "agent", "domain": "ielts", **extra}),
                                        content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json(), run

    def undo(self, body):
        response = self.client.post(f"/api/interview/assistant/messages/{body['reply']['id']}/undo/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_agent_gets_the_bank_and_an_ielts_prompt_chat_does_not_write(self):
        body, run = self.agent("看看", [])
        inputs = run.call_args.args[2]
        self.assertEqual(inputs["domain"], "ielts")
        self.assertIn(self.question, inputs["library"]["p1_bank"][self.topic])
        self.assertTrue(any(item["cue_id"] == self.cue_id for item in inputs["library"]["p2_bank"]))
        self.assertIn("IELTS coach", ai_schema.prompt("assistant", inputs))
        self.assertIn("Part 1", body["reply"]["steps"][0]["detail"].replace("P1", "Part 1"))
        self.assertTrue(body["ielts_changed"] is False and "entries" not in body)
        # chat mode: no bank index, no writes even if the model returns actions
        output = ai_schema.validate("assistant", {"reply": "切到 Agent", "actions": [{"type": "takeaway", "text": "a far cry from"}]}, {"domain": "ielts"})
        with patch(RUN, return_value=output) as chat_run:
            self.client.post("/api/interview/assistant/", json.dumps({"message": "存一下", "domain": "ielts"}), content_type="application/json")
        self.assertNotIn("p1_bank", chat_run.call_args.args[2]["library"])
        self.assertFalse(LanguageTakeawayEntry.objects.exists())

    def test_p1_answer_create_append_and_undo(self):
        body, _ = self.agent("写一个 P1", [{"type": "p1_answer", "question": self.question, "answer": "I usually ..."}])
        entry = P1CorpusEntry.objects.get(user=self.user)
        self.assertEqual((entry.question, entry.corpus_text), (self.question, "I usually ..."))
        self.assertEqual(body["reply"]["applied"][0]["where"], "p1")
        self.assertTrue(body["ielts_changed"])
        second, run = self.agent("补一句", [{"type": "update", "id": f"p1:{entry.question_id}", "append_answer": "Because ..."}])
        self.assertTrue(any(item["id"] == f"p1:{entry.question_id}" for item in run.call_args.args[2]["library"]["saved"]))
        entry.refresh_from_db()
        self.assertEqual(entry.corpus_text, "I usually ...\n\nBecause ...")
        self.undo(second)
        entry.refresh_from_db()
        self.assertEqual(entry.corpus_text, "I usually ...")
        self.undo(body)
        self.assertFalse(P1CorpusEntry.objects.exists())

    def test_p2_and_p3_answers_by_cue_and_index(self):
        body, _ = self.agent("写 P2 和第一道 P3", [
            {"type": "p2_answer", "cue_id": self.cue_id, "answer": "I'd like to talk about ..."},
            {"type": "p3_answer", "cue_id": self.cue_id, "index": 0, "answer": "I think ..."},
            {"type": "p3_answer", "cue_id": self.cue_id, "index": 99, "answer": "x"},
            {"type": "p2_answer", "cue_id": "p2cue:nope", "answer": "x"},
        ])
        self.assertEqual(P2BankCorpusEntry.objects.get().corpus_text, "I'd like to talk about ...")
        p3 = P3BankFollowupCorpusEntry.objects.get()
        self.assertEqual((p3.p2_question_id, p3.corpus_text), (self.cue_id, "I think ..."))
        self.assertEqual([step["kind"] for step in body["reply"]["steps"]].count("skip"), 2)
        self.undo(body)
        self.assertFalse(P2BankCorpusEntry.objects.exists() or P3BankFollowupCorpusEntry.objects.exists())

    def test_p2_material_and_takeaway_edit_delete_and_undo(self):
        body, _ = self.agent("建素材和表达", [
            {"type": "p2_material", "category": "person", "title": "My grandfather", "material": "He taught me chess."},
            {"type": "takeaway", "text": "a far cry from", "chinese": "与……相去甚远"},
        ])
        material = P2CorpusEntry.objects.get()
        takeaway = LanguageTakeawayEntry.objects.get()
        self.assertEqual((material.category, takeaway.chinese_text), ("person", "与……相去甚远"))
        edited, _ = self.agent("改标题，删表达", [
            {"type": "update", "id": f"p2m:{material.entry_id}", "title": "Grandpa", "append_material": "We played every Sunday."},
            {"type": "delete", "id": f"tk:{takeaway.entry_id}"},
        ])
        material.refresh_from_db()
        self.assertEqual((material.title, material.material_text), ("Grandpa", "He taught me chess.\n\nWe played every Sunday."))
        self.assertEqual(P2CorpusEntry.objects.count(), 1, "editing keeps the same entry")
        self.assertFalse(LanguageTakeawayEntry.objects.exists())
        self.undo(edited)
        material.refresh_from_db()
        self.assertEqual(material.title, "My grandfather")
        self.assertEqual(LanguageTakeawayEntry.objects.get().source_text, "a far cry from")

    def test_threads_are_kept_per_mode(self):
        self.agent("雅思问题", [])
        output = ai_schema.validate("assistant", {"reply": "面试", "actions": []}, {})
        with patch(RUN, return_value=output):
            self.client.post("/api/interview/assistant/", json.dumps({"message": "面试问题"}), content_type="application/json")
        ielts = self.client.get("/api/interview/assistant/threads/?domain=ielts").json()["threads"]
        interview = self.client.get("/api/interview/assistant/threads/").json()["threads"]
        self.assertEqual((len(ielts), len(interview)), (1, 1))
        self.assertEqual(Thread.objects.get(thread_id=ielts[0]["id"]).domain, "ielts")
        self.assertNotEqual(ielts[0]["id"], interview[0]["id"])
