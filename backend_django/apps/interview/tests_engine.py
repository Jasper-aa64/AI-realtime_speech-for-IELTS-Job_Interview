import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from . import ai_schema
from .models import InterviewCorpusEntry as Entry
from .models import InterviewTurn
from .validation import InterviewError

RUN = "apps.interview.engine.ai_services.run_generation"


def decision(action="next", prompt="", signal="adequate"):
    return {"action": action, "prompt": prompt, "signal": signal, "evidence": "依据", "boundary": "", "task_id": "t"}


class StudioEngineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="studio-owner", password="pw")
        self.client.force_login(self.user)

    def post(self, path, data=None):
        return self.client.post(path, json.dumps(data or {}), content_type="application/json")

    def seed_resume(self):
        intro = Entry.objects.create(user=self.user, kind="self_intro", question="请先做一个简单的自我介绍。", source="resume",
                                     source_key="resume:self_intro")
        gateway = Entry.objects.create(user=self.user, kind="project", question="介绍一下你的「撮合网关」项目。", title="撮合网关",
                                       source="resume", source_key="resume:project:gw", order=0)
        replay = Entry.objects.create(user=self.user, kind="project", question="介绍一下你的「行情回放」项目。", title="行情回放",
                                      source="resume", source_key="resume:project:rp", order=1)
        Entry.objects.create(user=self.user, kind="knowledge", question="讲讲内存序。", group="C++", source="resume",
                             source_key="resume:tech:a")
        Entry.objects.create(user=self.user, kind="award", question="讲讲你的「ACM 银牌」经历。", title="ACM 银牌",
                             source="resume", source_key="resume:award:acm")
        Entry.objects.create(user=self.user, kind="project", question="旧项目", source="resume", source_key="resume:project:old",
                             metadata={"orphaned": True})
        return intro, gateway, replay

    def start(self, **payload):
        response = self.post("/api/interview/sessions/", payload)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def answer(self, session, value="我的回答", **extra):
        turn = session["current_turn"]
        response = self.post(f"/api/interview/sessions/{session['session']['id']}/turns/{turn['id']}/answer/",
                             {"answer": value, **extra})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_full_interview_requires_resume_and_follows_interview_order(self):
        response = self.post("/api/interview/sessions/", {"part": "full"})
        self.assertEqual(response.json()["code"], "resume_required")
        self.seed_resume()
        payload = self.start(part="full")
        stages = [t["stage"] for t in payload["turns"]]
        self.assertEqual(stages, ["self_intro", "project", "project"] + ["knowledge"] * 5 + ["award", "reverse"])
        self.assertEqual(payload["session"]["plan"], ["self_intro", "project", "knowledge", "award", "reverse"])
        self.assertNotIn("旧项目", [t["prompt"] for t in payload["turns"]])
        knowledge = [t for t in payload["turns"] if t["stage"] == "knowledge"]
        self.assertEqual(knowledge[0]["prompt"], "讲讲内存序。")
        self.assertNotIn("projects", [t["category"] for t in knowledge])

    def test_standard_mode_never_follows_up(self):
        self.seed_resume()
        session = self.start(part="project", intensity="standard")
        with patch(RUN) as run:
            after = self.answer(session)
        run.assert_not_called()
        self.assertEqual(after["turns"][0]["decision"]["reason"], "depth_limit")
        self.assertEqual(after["current_turn"]["prompt"], "介绍一下你的「行情回放」项目。")
        self.assertEqual(after["current_turn"]["kind"], "main")

    def test_pressure_mode_follows_up_until_the_interviewer_moves_on(self):
        self.seed_resume()
        session = self.start(part="knowledge", intensity="pressure", count=1)
        prompts = ["追问一", "追问二", "追问三", "追问四"]
        for prompt in prompts:
            with patch(RUN, return_value=decision("follow_up", prompt, "")) as run:
                session = self.answer(session)
            self.assertEqual(session["current_turn"]["prompt"], prompt)
            self.assertNotIn("max_depth", run.call_args.args[2])
        with patch(RUN, return_value=decision("next")):
            session = self.answer(session)
        self.assertIsNone(session["current_turn"])
        self.assertEqual([t["kind"] for t in session["turns"]], ["main"] + ["follow_up"] * 4)

    def test_ai_failure_moves_on_without_inventing_a_question(self):
        self.seed_resume()
        session = self.start(part="project", intensity="pressure")
        failure = InterviewError("AI generation failed", code="ai_generation_failed", status=502)
        with patch(RUN, side_effect=failure):
            after = self.answer(session)
        self.assertEqual(after["turns"][0]["decision"]["status"], "failed")
        self.assertEqual(after["current_turn"]["prompt"], "介绍一下你的「行情回放」项目。")
        self.assertEqual(InterviewTurn.objects.filter(kind="follow_up").count(), 0)

    def test_reverse_round_replies_and_allows_one_more_question(self):
        session = self.start(part="reverse")
        reply = {"reply": "团队按 P99 看延迟。", "signal": "strong", "evidence": "问到了核心指标"}
        with patch(RUN, return_value=reply) as run:
            session = self.answer(session, "团队怎么衡量延迟？")
        self.assertEqual(run.call_args.args[1], "reverse_reply")
        self.assertEqual(session["turns"][0]["reply"], "团队按 P99 看延迟。")
        self.assertEqual(session["current_turn"]["prompt"], "还有其他想了解的吗？没有的话我们今天就到这里。")
        with patch(RUN, return_value=reply):
            session = self.answer(session, "新人怎么上手？")
        self.assertIsNone(session["current_turn"])

    @override_settings(MEDIA_ROOT="/tmp/interview-test-media")
    def test_audio_upload_transcribes_current_turn(self):
        session = self.start(part="reverse")
        url = f"/api/interview/sessions/{session['session']['id']}/turns/{session['current_turn']['id']}/audio/"
        audio = SimpleUploadedFile("a.webm", b"\x1aE\xdf\xa3fake", content_type="audio/webm")
        with patch("apps.interview.engine.transcribe_audio", return_value={"ok": True, "transcript": "团队用什么技术栈？"}):
            response = self.client.post(url, {"audio": audio})
        self.assertEqual(response.json()["transcript"], "团队用什么技术栈？")
        audio = SimpleUploadedFile("a.webm", b"\x1aE\xdf\xa3fake", content_type="audio/webm")
        with patch("apps.interview.engine.transcribe_audio", return_value={"ok": False, "transcript": "", "status": "error"}):
            failed = self.client.post(url, {"audio": audio})
        self.assertEqual((failed.status_code, failed.json()["code"]), (502, "asr_failed"))
        self.assertEqual(self.client.post(url, {}).json()["code"], "invalid_audio")

    def test_save_answers_back_to_the_corpus(self):
        _, gateway, _ = self.seed_resume()
        session = self.start(part="project", intensity="pressure")
        with patch(RUN, return_value=decision("follow_up", "延迟怎么测的？")):
            session = self.answer(session, "我的网关讲述")
        with patch(RUN, return_value=decision("next")):
            session = self.answer(session, "用 HdrHistogram 统计")
        sid = session["session"]["id"]
        saved = self.post(f"/api/interview/sessions/{sid}/turns/{session['turns'][0]['id']}/save-corpus/").json()["entry"]
        self.assertEqual((saved["id"], saved["corpus_text"]), (gateway.entry_id, "我的网关讲述"))
        follow = self.post(f"/api/interview/sessions/{sid}/turns/{session['turns'][1]['id']}/save-corpus/").json()["entry"]
        self.assertEqual((follow["kind"], follow["parent_id"], follow["question"]), ("project_followup", gateway.entry_id, "延迟怎么测的？"))
        pending = self.post(f"/api/interview/sessions/{sid}/turns/{session['current_turn']['id']}/save-corpus/")
        self.assertEqual(pending.status_code, 400)

    def test_curated_knowledge_saves_to_curated_entry(self):
        session = self.start(part="knowledge", question_ids=["cpp-1"])
        with patch(RUN, return_value=decision()):
            session = self.answer(session, "RAII 的答法")
        sid = session["session"]["id"]
        saved = self.post(f"/api/interview/sessions/{sid}/turns/{session['turns'][0]['id']}/save-corpus/").json()["entry"]
        self.assertEqual((saved["source_key"], saved["corpus_text"]), ("curated:cpp-1", "RAII 的答法"))

    def test_hundred_point_report(self):
        session = self.start(part="knowledge", count=1)
        with patch(RUN, return_value=decision()):
            session = self.answer(session)
        sid = session["session"]["id"]
        self.assertEqual(self.post(f"/api/interview/sessions/{sid}/report/").json()["code"], "session_not_completed")
        self.post(f"/api/interview/sessions/{sid}/finish/")
        dims = {key: {"score": maximum // 2, "evidence": "e"} for key, _, maximum in ai_schema.DIMENSIONS}
        validated = ai_schema.validate("score_report", {"dimensions": dims, "summary": "s"}, {"turn_ids": []})
        failure = InterviewError("AI generation failed", code="ai_generation_failed", status=502)
        with patch(RUN, side_effect=failure):
            failed = self.post(f"/api/interview/sessions/{sid}/report/")
        self.assertEqual(failed.status_code, 502)
        self.assertEqual(self.client.get(f"/api/interview/sessions/{sid}/").json()["session"]["score"]["status"], "failed")
        with patch(RUN, return_value=validated):
            ready = self.post(f"/api/interview/sessions/{sid}/report/").json()
        self.assertEqual(ready["session"]["score"]["total"], 49)
        self.assertEqual(ready["session"]["score"]["status"], "ready")
        listed = self.client.get("/api/interview/sessions/").json()["sessions"][0]
        self.assertEqual(listed["score"], {"status": "ready", "total": 49})
