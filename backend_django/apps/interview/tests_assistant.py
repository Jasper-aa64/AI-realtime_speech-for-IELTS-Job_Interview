"""The AI assistant: chat replies, and agent-mode changes to the library only through validated, undoable actions."""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from . import ai_schema
from .models import InterviewAssistantThread as Thread
from .models import InterviewCorpusEntry as Entry
from .validation import InterviewError

RUN = "apps.interview.assistant.ai_services.run_generation"


class AssistantTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="assistant-owner", password="pw")
        self.client.force_login(self.user)

    def ask(self, message, result, **extra):
        output = ai_schema.validate("assistant", result, {})
        with patch(RUN, return_value={**output, "model": "gpt-6-luna", "elapsed_ms": 4200, "effort": "medium"}) as run:
            response = self.client.post("/api/interview/assistant/", json.dumps({"message": message, **extra}), content_type="application/json")
        return response, run

    def agent(self, message, actions, reply="好的", **extra):
        return self.ask(message, {"reply": reply, "actions": actions}, mode="agent", **extra)

    def card(self, **fields):
        return Entry.objects.create(user=self.user, kind=fields.pop("kind", "knowledge"), source="custom", **fields)

    def test_plain_question_starts_a_thread_and_writes_nothing(self):
        response, run = self.ask("SPSC 队列为什么不用锁？", {"reply": "因为只有一个生产者和一个消费者……", "actions": [], "title": "SPSC 无锁原理"})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["reply"]["content"], "因为只有一个生产者和一个消费者……")
        self.assertEqual(body["reply"]["applied"], [])
        self.assertEqual([step["kind"] for step in body["reply"]["steps"]], ["library", "model"])
        self.assertIn("gpt-6-luna · 推理 medium · 4.2 s", body["reply"]["steps"][1]["detail"])
        self.assertEqual(body["thread"]["title"], "SPSC 无锁原理")
        self.assertEqual(Entry.objects.count(), 0)
        inputs = run.call_args.args[2]
        self.assertEqual(inputs["mode"], "chat")
        self.assertEqual(inputs["conversation"], [{"role": "user", "content": "SPSC 队列为什么不用锁？"}])
        self.assertIn("C++ 基础与进阶 / RAII 与资源管理", inputs["library"]["bank_topics"])

    def test_chat_mode_never_writes_even_if_the_model_returns_actions(self):
        response, _ = self.ask("存一下", {"reply": "请切到 Agent 模式", "actions": [{"type": "jd_question", "question": "讲讲 epoll", "answer": ""}]})
        self.assertEqual(response.json()["reply"]["applied"], [])
        self.assertFalse(Entry.objects.exists())
        self.assertIn("CHAT mode", ai_schema.prompt("assistant", {"mode": "chat", "conversation": [], "library": {}}))
        self.assertIn("AGENT mode", ai_schema.prompt("assistant", {"mode": "agent", "conversation": [], "library": {}}))

    def test_agent_sees_card_ids_and_can_update_and_delete(self):
        spsc = self.card(group="低延迟与性能", title="内存对齐", question="为什么要缓存行对齐？", corpus_text="旧答案" * 600)
        project = self.card(kind="project", title="行情网关", question="介绍项目")
        follow = Entry.objects.create(user=self.user, kind="project_followup", source="custom", parent=project, question="延迟怎么测？")
        _, run = self.agent("看看", [])
        cards = {c["id"]: c for c in run.call_args.args[2]["library"]["cards"]}
        self.assertTrue(cards[spsc.entry_id]["answer"].endswith("…(共 1800 字)"))
        self.assertEqual(cards[follow.entry_id]["parent"], project.entry_id)
        response, _ = self.agent("保留问题，删掉回答；项目删了", [
            {"type": "update", "id": spsc.entry_id, "answer": ""},
            {"type": "delete", "id": project.entry_id},
        ], reply="已清空回答并删除项目。")
        body = response.json()["reply"]
        self.assertEqual([(a["op"], a["label"]) for a in body["applied"]],
                         [("update", "知识点语料库 · 低延迟与性能 / 内存对齐"), ("delete", "简历题卡 · 行情网关")])
        self.assertTrue(body["undoable"])
        spsc.refresh_from_db()
        self.assertEqual((spsc.question, spsc.corpus_text), ("为什么要缓存行对齐？", ""))
        self.assertFalse(Entry.objects.filter(entry_id__in=[project.entry_id, follow.entry_id]).exists())

    def test_undo_restores_updates_deletes_and_removes_creations(self):
        spsc = self.card(group="低延迟", title="对齐", question="为什么对齐？", corpus_text="原答案")
        project = self.card(kind="project", title="行情网关", question="介绍项目", metadata={"resume_excerpt": "简历原文"})
        follow = Entry.objects.create(user=self.user, kind="project_followup", source="custom", parent=project, question="延迟怎么测？", corpus_text="直方图")
        response, _ = self.agent("整理一下", [
            {"type": "update", "id": spsc.entry_id, "append_answer": "补充"},
            {"type": "delete", "id": project.entry_id},
            {"type": "knowledge", "tag": "低延迟", "topic": "背压", "question": "SPSC 满了怎么办？", "answer": "丢弃或阻塞"},
        ])
        message_id = response.json()["reply"]["id"]
        undone = self.client.post(f"/api/interview/assistant/messages/{message_id}/undo/")
        self.assertEqual(undone.status_code, 200, undone.content)
        self.assertTrue(undone.json()["message"]["undone"])
        spsc.refresh_from_db()
        self.assertEqual(spsc.corpus_text, "原答案")
        restored = Entry.objects.get(entry_id=project.entry_id)
        self.assertEqual(restored.metadata["resume_excerpt"], "简历原文")
        self.assertEqual(Entry.objects.get(entry_id=follow.entry_id).parent, restored)
        self.assertFalse(Entry.objects.filter(question="SPSC 满了怎么办？").exists())
        self.assertEqual(self.client.post(f"/api/interview/assistant/messages/{message_id}/undo/").status_code, 409)

    def test_bad_ids_and_malformed_actions_are_skipped_not_fatal(self):
        other = get_user_model().objects.create_user(username="someone-else", password="pw")
        foreign = Entry.objects.create(user=other, kind="knowledge", source="custom", question="别人的题")
        response, _ = self.ask("删掉", {"reply": "好", "actions": [
            {"type": "delete", "id": foreign.entry_id}, {"type": "drop_table"},
            {"type": "jd_question", "kind": "jd_question", "question": "讲讲 epoll", "answer": ""},
        ]}, mode="agent")
        body = response.json()["reply"]
        self.assertEqual([a["op"] for a in body["applied"]], ["create"])
        kinds = [s["kind"] for s in body["steps"]]
        self.assertIn("skip", kinds)
        self.assertIn("1 个格式不对已丢弃", next(s["detail"] for s in body["steps"] if s["kind"] == "validate"))
        self.assertTrue(Entry.objects.filter(entry_id=foreign.entry_id).exists())

    def test_history_tells_the_model_what_earlier_turns_changed(self):
        first, _ = self.agent("存一张", [{"type": "knowledge", "tag": "C++", "topic": "RAII", "question": "讲讲 RAII", "answer": "析构释放"}], reply="已保存")
        _, run = self.agent("刚才存了什么？", [], thread_id=first.json()["thread"]["id"])
        conversation = run.call_args.args[2]["conversation"]
        self.assertEqual([m["role"] for m in conversation], ["user", "assistant", "user"])
        self.assertIn("[本轮已执行：新建 知识点语料库 · C++ / RAII]", conversation[1]["content"])

    def test_agent_mode_creates_knowledge_resume_card_and_jd(self):
        response, _ = self.agent("把这些总结到语料库", [
            {"type": "knowledge", "tag": "低延迟与性能", "topic": "SPSC 队列与背压", "question": "SPSC 队列为什么不用锁？", "answer": "单生产者单消费者……"},
            {"type": "resume_card", "section": "intern", "title": "某券商交易组 · 行情接入", "resume_excerpt": "负责行情接入",
             "star": "**S 情境**：……", "follow_ups": [{"question": "延迟怎么测？", "answer": "直方图"}]},
            {"type": "jd", "title": "C++ 低延迟开发", "jd": "负责交易系统", "questions": [{"kind": "reverse_question", "question": "团队怎么衡量延迟？", "answer": ""}]},
            {"type": "jd_question", "kind": "jd_question", "question": "讲讲 epoll。", "answer": "……"},
        ])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([item["where"] for item in response.json()["reply"]["applied"]], ["knowledge", "resume", "resume", "jd"])
        intern = Entry.objects.get(kind="project")
        self.assertEqual((intern.group, intern.metadata["resume_excerpt"]), ("实习", "负责行情接入"))
        self.assertEqual(intern.children.get().question, "延迟怎么测？")
        self.assertEqual(Entry.objects.get(kind="jd").children.get().kind, "reverse_question")
        self.assertIn(Entry.objects.get(kind="knowledge").entry_id, {e["id"] for e in response.json()["entries"] if e["id"]})

    def test_thread_keeps_history(self):
        first, _ = self.ask("讲讲 RAII", {"reply": "RAII 是……", "actions": []})
        thread_id = first.json()["thread"]["id"]
        self.ask("再说说", {"reply": "好", "actions": []}, thread_id=thread_id)
        detail = self.client.get(f"/api/interview/assistant/threads/{thread_id}/").json()
        self.assertEqual([m["content"] for m in detail["messages"]], ["讲讲 RAII", "RAII 是……", "再说说", "好"])
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

    def test_bad_input_is_rejected(self):
        self.assertEqual(self.client.post("/api/interview/assistant/", json.dumps({"message": "  "}), content_type="application/json").status_code, 400)
        missing = self.client.post("/api/interview/assistant/", json.dumps({"message": "hi", "thread_id": "iat_nope"}), content_type="application/json")
        self.assertEqual(missing.status_code, 404)


class AssistantOutputParsingTests(TestCase):
    def test_trailing_junk_after_the_json_is_ignored(self):
        from .ai_services import _validated_output
        raw = '{"reply":"已保存","actions":[{"type":"knowledge","tag":"低延迟与性能","topic":"内存对齐","question":"为什么对齐？","answer":"避免伪共享"}]}"}'
        result = _validated_output("assistant", raw, {})
        self.assertEqual((result["reply"], result["actions"][0]["topic"]), ("已保存", "内存对齐"))
        with self.assertRaises(ValueError):
            _validated_output("assistant", "没有 JSON", {})
