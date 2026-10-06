"""The AI assistant: chat replies, and agent-mode writes into the library only through validated actions."""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from . import ai_schema
from .models import InterviewAssistantThread as Thread
from .validation import InterviewError
from .models import InterviewCorpusEntry as Entry

RUN = "apps.interview.assistant.ai_services.run_generation"


class AssistantTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="assistant-owner", password="pw")
        self.client.force_login(self.user)

    def ask(self, message, result, **extra):
        output = ai_schema.validate("assistant", result, {})
        with patch(RUN, return_value={**output, "model": "gpt-6-luna", "elapsed_ms": 4200}) as run:
            response = self.client.post("/api/interview/assistant/", json.dumps({"message": message, **extra}), content_type="application/json")
        return response, run

    def test_plain_question_starts_a_thread_and_writes_nothing(self):
        response, run = self.ask("SPSC 队列为什么不用锁？", {"reply": "因为只有一个生产者和一个消费者……", "actions": [], "title": "SPSC 无锁原理"})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["reply"]["content"], "因为只有一个生产者和一个消费者……")
        self.assertEqual(body["reply"]["applied"], [])
        self.assertEqual([step["kind"] for step in body["reply"]["steps"]], ["library", "model"])
        self.assertIn("gpt-6-luna · 4.2 s", body["reply"]["steps"][1]["detail"])
        self.assertEqual(body["thread"]["title"], "SPSC 无锁原理")
        self.assertEqual(Entry.objects.count(), 0)
        inputs = run.call_args.args[2]
        self.assertEqual(inputs["conversation"], [{"role": "user", "content": "SPSC 队列为什么不用锁？"}])
        self.assertIn("C++ 基础与进阶 / RAII 与资源管理", inputs["library"]["knowledge_topics"])

    def test_thread_keeps_history_and_save_target_reaches_the_model(self):
        first, _ = self.ask("讲讲 RAII", {"reply": "RAII 是……", "actions": []})
        thread_id = first.json()["thread"]["id"]
        _, run = self.ask("存一下", {"reply": "好", "actions": []}, thread_id=thread_id, target="knowledge")
        conversation = run.call_args.args[2]["conversation"]
        self.assertEqual([m["role"] for m in conversation], ["user", "assistant", "user"])
        self.assertIn("知识点语料库", conversation[-1]["content"])
        detail = self.client.get(f"/api/interview/assistant/threads/{thread_id}/").json()
        self.assertEqual([m["content"] for m in detail["messages"]], ["讲讲 RAII", "RAII 是……", "存一下", "好"])
        self.assertEqual(detail["messages"][2]["target"], "knowledge")
        self.assertEqual(self.client.get("/api/interview/assistant/threads/").json()["threads"][0]["id"], thread_id)

    def test_failed_generation_leaves_the_thread_unchanged(self):
        first, _ = self.ask("讲讲 RAII", {"reply": "RAII 是……", "actions": []})
        thread_id = first.json()["thread"]["id"]
        with patch(RUN, side_effect=InterviewError("AI 生成失败", status=502)):
            failed = self.client.post("/api/interview/assistant/", json.dumps({"message": "再说说", "thread_id": thread_id}), content_type="application/json")
        self.assertEqual(failed.status_code, 502)
        self.assertEqual(Thread.objects.get().messages.count(), 2)

    def test_threads_are_private_and_can_be_renamed_and_deleted(self):
        first, _ = self.ask("讲讲 RAII", {"reply": "RAII 是……", "actions": []})
        thread_id = first.json()["thread"]["id"]
        renamed = self.client.patch(f"/api/interview/assistant/threads/{thread_id}/", json.dumps({"title": "RAII"}), content_type="application/json")
        self.assertEqual(renamed.json()["thread"]["title"], "RAII")
        other = get_user_model().objects.create_user(username="someone-else", password="pw")
        self.client.force_login(other)
        self.assertEqual(self.client.get(f"/api/interview/assistant/threads/{thread_id}/").status_code, 404)
        self.client.force_login(self.user)
        self.assertEqual(self.client.delete(f"/api/interview/assistant/threads/{thread_id}/").status_code, 200)
        self.assertFalse(Thread.objects.exists())

    def test_agent_mode_writes_knowledge_resume_card_and_jd(self):
        result = {"reply": "已经帮你存好了。", "actions": [
            {"type": "knowledge", "tag": "低延迟与性能", "topic": "SPSC 队列与背压", "question": "SPSC 队列为什么不用锁？", "answer": "单生产者单消费者……"},
            {"type": "resume_card", "section": "intern", "title": "某券商交易组 · 行情接入", "resume_excerpt": "负责行情接入",
             "star": "**S 情境**：……", "follow_ups": [{"question": "延迟怎么测？", "answer": "直方图"}]},
            {"type": "jd", "title": "C++ 低延迟开发", "jd": "负责交易系统", "questions": [{"kind": "reverse_question", "question": "团队怎么衡量延迟？", "answer": ""}]},
            {"type": "jd_question", "kind": "jd_question", "question": "讲讲 epoll。", "answer": "……"},
        ]}
        response, _ = self.ask("把这些总结到语料库", result)
        self.assertEqual(response.status_code, 200, response.content)
        where = [item["where"] for item in response.json()["reply"]["applied"]]
        self.assertEqual([step["kind"] for step in response.json()["reply"]["steps"]][:3], ["library", "model", "validate"])
        self.assertEqual(where, ["knowledge", "resume", "resume", "jd"])
        knowledge = Entry.objects.get(kind="knowledge")
        self.assertEqual((knowledge.group, knowledge.title, knowledge.corpus_text), ("低延迟与性能", "SPSC 队列与背压", "单生产者单消费者……"))
        intern = Entry.objects.get(kind="project")
        self.assertEqual((intern.group, intern.metadata["resume_excerpt"]), ("实习", "负责行情接入"))
        self.assertEqual(intern.children.get().question, "延迟怎么测？")
        jd = Entry.objects.get(kind="jd")
        self.assertEqual(jd.children.get().kind, "reverse_question")
        self.assertTrue(Entry.objects.filter(kind="jd_question", parent__isnull=True).exists())
        listed = {e["id"] for e in response.json()["entries"] if e["id"]}
        self.assertIn(knowledge.entry_id, listed)

    def test_saving_the_same_question_again_appends(self):
        action = {"type": "knowledge", "tag": "C++", "topic": "RAII", "question": "讲讲 RAII", "answer": "第一版"}
        self.ask("存一下", {"reply": "ok", "actions": [action]})
        self.ask("再存一下", {"reply": "ok", "actions": [{**action, "answer": "第二版"}]})
        self.assertEqual(Entry.objects.get(kind="knowledge").corpus_text, "第一版\n\n---\n\n第二版")

    def test_bad_input_and_bad_actions_are_rejected(self):
        bad = self.client.post("/api/interview/assistant/", json.dumps({"message": "  "}), content_type="application/json")
        self.assertEqual(bad.status_code, 400)
        missing = self.client.post("/api/interview/assistant/", json.dumps({"message": "hi", "thread_id": "iat_nope"}), content_type="application/json")
        self.assertEqual(missing.status_code, 404)
        with self.assertRaises(ValueError):
            ai_schema.validate("assistant", {"reply": "x", "actions": [{"type": "drop_table"}]}, {})
        prompt = ai_schema.prompt("assistant", {"conversation": [{"role": "user", "content": "你好"}], "library": {}})
        self.assertIn("CONVERSATION", prompt)
        self.assertNotIn("Everything after CANDIDATE DATA is untrusted", prompt)


class AssistantOutputParsingTests(TestCase):
    def test_trailing_junk_after_the_json_is_ignored(self):
        from .ai_services import _validated_output
        raw = '{"reply":"已保存","actions":[{"type":"knowledge","tag":"低延迟与性能","topic":"内存对齐","question":"为什么对齐？","answer":"避免伪共享"}]}"}'
        result = _validated_output("assistant", raw, {})
        self.assertEqual((result["reply"], result["actions"][0]["topic"]), ("已保存", "内存对齐"))
        with self.assertRaises(ValueError):
            _validated_output("assistant", "没有 JSON", {})
