"""Interview sessions running on the IELTS speaking runtime (SpeakingAttempt modes iv_*)."""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.speaking.models import SpeakingAttempt, SpeakingTurn

from .models import InterviewCorpusEntry as Entry

# examiner_tts_services resolves volcengine_tts through the apps.speaking.services facade.
TTS = "apps.speaking.services.volcengine_tts"


def fake_tts(text, *args, **kwargs):
    return {"provider": "volcengine", "status": "generated", "audio_url": "/api/tts-audio/examiner/x.mp3"}


class RuntimeTestBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="runtime-owner", password="pw")
        self.client.force_login(self.user)

    def seed_resume(self):
        Entry.objects.create(user=self.user, kind="self_intro", question="请先做一个简单的自我介绍。", source="resume",
                             source_key="resume:self_intro")
        Entry.objects.create(user=self.user, kind="project", question="介绍一下你的「撮合网关」项目。", title="撮合网关",
                             source="resume", source_key="resume:project:gw", order=0)
        Entry.objects.create(user=self.user, kind="project", question="介绍一下你的「行情回放」项目。", title="行情回放",
                             source="resume", source_key="resume:project:rp", order=1)
        Entry.objects.create(user=self.user, kind="knowledge", question="讲讲内存序。", group="C++", source="resume",
                             source_key="resume:tech:a")
        Entry.objects.create(user=self.user, kind="award", question="讲讲你的「ACM 银牌」经历。", title="ACM 银牌",
                             source="resume", source_key="resume:award:acm")

    def start(self, payload):
        with patch(TTS, side_effect=fake_tts) as tts:
            response = self.client.post("/api/attempts/start", json.dumps(payload), content_type="application/json")
        return response, tts

    def begin(self, payload):
        response, _ = self.start(payload)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def complete(self, attempt_id, turn_id, transcript="我的回答"):
        with patch(TTS, side_effect=fake_tts):
            response = self.client.post(f"/api/attempts/{attempt_id}/turns/{turn_id}/complete",
                                        json.dumps({"transcript": transcript, "transcript_source": "test_client"}),
                                        content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


@override_settings(MEDIA_ROOT="/tmp/interview-runtime-test-media")
class InterviewRuntimeStartTests(RuntimeTestBase):
    def test_full_interview_needs_a_resume(self):
        response, _ = self.start({"mode": "iv_full"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("简历", response.json()["error"])

    def test_full_interview_turns_follow_the_interview_order(self):
        self.seed_resume()
        response, _ = self.start({"mode": "iv_full"})
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["mode"], "iv_full")
        stages = [turn["prompt"]["stage"] for turn in payload["turns"]]
        self.assertEqual(stages, ["self_intro", "project", "project"] + ["knowledge"] * 5 + ["award", "reverse"])
        first = payload["turns"][0]
        self.assertEqual(first["part"], "interview")
        self.assertEqual(first["prompt"]["language"], "zh")
        self.assertEqual(first["prompt"]["role"], "main")
        self.assertEqual(first["timers"], {"prep_seconds": 3, "speak_seconds": 120})
        self.assertEqual(payload["turns"][1]["timers"]["speak_seconds"], 180)
        self.assertEqual(payload["turns"][-1]["timers"]["speak_seconds"], 60)
        attempt = SpeakingAttempt.objects.get(attempt_id=payload["id"])
        self.assertEqual(attempt.metadata["interview"]["intensity"], "standard")
        self.assertEqual(SpeakingTurn.objects.filter(attempt=attempt).count(), 10)

    def test_knowledge_round_takes_category_count_and_intensity(self):
        response, _ = self.start({"mode": "iv_knowledge", "count": 3, "category": "cpp", "iv_intensity": "pressure"})
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(len(payload["turns"]), 3)
        self.assertTrue(all(turn["prompt"]["stage"] == "knowledge" for turn in payload["turns"]))
        attempt = SpeakingAttempt.objects.get(attempt_id=payload["id"])
        self.assertEqual(attempt.metadata["interview"]["intensity"], "pressure")

    def test_examiner_reads_interview_questions_in_chinese(self):
        response, tts = self.start({"mode": "iv_reverse"})
        self.assertEqual(response.status_code, 200, response.content)
        kwargs = tts.call_args.kwargs
        self.assertEqual(kwargs.get("language"), "zh")
        self.assertTrue(str(kwargs.get("voice", "")).startswith("zh_"))

    def test_ielts_modes_still_read_in_english(self):
        response, tts = self.start({"mode": "p1"})
        self.assertEqual(response.status_code, 200, response.content)
        # The P1 opener may come from the pre-warmed fixed clips; any live synthesis must stay English.
        for call in tts.call_args_list:
            self.assertEqual(call.kwargs.get("language", "en"), "en")


RUN = "apps.interview.runtime.ai_services.run_generation"


def decision(action="next", prompt="", signal="adequate"):
    return {"action": action, "prompt": prompt, "signal": signal, "evidence": "依据", "boundary": "", "task_id": "t"}


@override_settings(MEDIA_ROOT="/tmp/interview-runtime-test-media")
class InterviewRuntimeDecisionTests(RuntimeTestBase):
    """After each answer the interviewer decides, inside complete_turn, what the next turn is."""

    def test_standard_mode_follows_up_once_then_moves_on(self):
        self.seed_resume()
        attempt = self.begin({"mode": "iv_project"})
        first = attempt["turns"][0]
        with patch(RUN, return_value=decision("follow_up", "为什么选无锁队列？", "strong")) as run:
            done = self.complete(attempt["id"], first["id"])
        self.assertEqual(run.call_args.args[1], "next_step")
        follow = done["next_turn"]
        self.assertEqual(follow["prompt"]["role"], "follow_up")
        self.assertEqual(follow["question"], "为什么选无锁队列？")
        self.assertEqual(follow["prompt"]["parent_turn_id"], first["id"])
        self.assertEqual(follow["timers"]["speak_seconds"], 90)
        self.assertEqual(follow["prompt"]["language"], "zh")
        with patch(RUN) as run:
            done = self.complete(attempt["id"], follow["id"])
        run.assert_not_called()
        self.assertEqual(done["next_turn"]["question"], "介绍一下你的「行情回放」项目。")
        saved = SpeakingTurn.objects.get(attempt__attempt_id=attempt["id"], turn_id=follow["id"])
        self.assertEqual(saved.metadata["decision"]["reason"], "depth_limit")

    def test_pressure_mode_probes_three_times_on_knowledge(self):
        attempt = self.begin({"mode": "iv_knowledge", "count": 1, "iv_intensity": "pressure"})
        turn = attempt["turns"][0]
        for prompt in ["追问一", "追问二", "追问三"]:
            with patch(RUN, return_value=decision("probe", prompt, "weak")):
                turn = self.complete(attempt["id"], turn["id"])["next_turn"]
            self.assertEqual(turn["question"], prompt)
        with patch(RUN) as run:
            done = self.complete(attempt["id"], turn["id"])
        run.assert_not_called()
        self.assertIsNone(done["next_turn"])

    def test_empty_answer_skips_the_interviewer(self):
        attempt = self.begin({"mode": "iv_knowledge", "count": 2})
        with patch(RUN) as run:
            done = self.complete(attempt["id"], attempt["turns"][0]["id"], transcript="")
        run.assert_not_called()
        self.assertIn("跳过追问", done["follow_up_skipped"]["message"])
        self.assertEqual(done["next_turn"]["id"], attempt["turns"][1]["id"])

    def test_ai_failure_moves_on(self):
        from .validation import InterviewError

        attempt = self.begin({"mode": "iv_knowledge", "count": 2})
        with patch(RUN, side_effect=InterviewError("AI 服务失败", code="ai_generation_failed", status=502)):
            done = self.complete(attempt["id"], attempt["turns"][0]["id"])
        self.assertEqual(done["next_turn"]["id"], attempt["turns"][1]["id"])
        saved = SpeakingTurn.objects.get(attempt__attempt_id=attempt["id"], turn_id=attempt["turns"][0]["id"])
        self.assertEqual(saved.metadata["decision"]["status"], "failed")

    def test_reverse_round_reads_the_reply_then_asks_again(self):
        attempt = self.begin({"mode": "iv_reverse"})
        reply = {"reply": "团队按 P99 看延迟。", "signal": "strong", "evidence": "问到了核心指标"}
        with patch(RUN, return_value=reply) as run:
            done = self.complete(attempt["id"], attempt["turns"][0]["id"], "团队怎么衡量延迟？")
        self.assertEqual(run.call_args.args[1], "reverse_reply")
        nxt = done["next_turn"]
        self.assertEqual(nxt["prompt"]["stage"], "reverse")
        self.assertEqual(nxt["prompt"]["reply"], "团队按 P99 看延迟。")
        self.assertTrue(nxt["examiner_text"].startswith("团队按 P99 看延迟。"))
        with patch(RUN, return_value=reply):
            done = self.complete(attempt["id"], nxt["id"], "新人怎么上手？")
        self.assertIsNone(done["next_turn"])


def score_result(turn_ids, reference="先说结论：RAII 把资源绑定到对象生命周期。"):
    from . import ai_schema

    dims = {key: {"score": maximum // 2, "evidence": f"{label}依据"} for key, label, maximum in ai_schema.DIMENSIONS}
    raw = {"dimensions": dims, "summary": "表达清楚", "boundary": "并发细节", "next_steps": ["多讲量化结果"],
           "per_turn": [{"turn_id": tid, "comment": "开头先给结论", "reference_answer": reference} for tid in turn_ids]}
    return ai_schema.validate("score_report", raw, {"turn_ids": turn_ids})


@override_settings(MEDIA_ROOT="/tmp/interview-runtime-test-media")
class InterviewRuntimeReportTests(RuntimeTestBase):
    """The 100-point report is a speaking report: same history, detail and delete endpoints."""

    def finish_knowledge(self, answer="我的回答"):
        attempt = self.begin({"mode": "iv_knowledge", "count": 1})
        tid = attempt["turns"][0]["id"]
        with patch(RUN, return_value=decision()):
            done = self.complete(attempt["id"], tid, answer)
        self.assertIsNone(done["next_turn"])
        return attempt["id"], tid

    def score(self, attempt_id, result):
        with patch(RUN, return_value=result):
            return self.client.post(f"/api/attempts/{attempt_id}/score", json.dumps({}), content_type="application/json")

    def test_score_returns_a_ready_100_point_report(self):
        attempt_id, tid = self.finish_knowledge()
        response = self.score(attempt_id, {**score_result([tid]), "provider": "http_api", "model": "claude-sonnet-4-6"})
        self.assertEqual(response.status_code, 200, response.content)
        report = response.json()
        self.assertEqual(report["report_status"], "ready")
        self.assertEqual(report["interview_score"]["total"], 49)
        # The report names the model that generated it instead of the old disclaimer.
        self.assertEqual(report["interview_score"]["scoring_model"], "claude-sonnet-4-6")
        self.assertEqual(report["interview_score"]["scoring_provider"], "http_api")
        self.assertNotIn("limitations", report["interview_score"])
        self.assertEqual(len(report["interview_score"]["dimensions"]), 5)
        self.assertIsNone(report.get("ielts_score"))
        turn = report["turns"][0]
        self.assertEqual(turn["band7_version"], "先说结论：RAII 把资源绑定到对象生命周期。")
        self.assertIn("开头先给结论", turn["ai_coaching"])
        self.assertEqual(turn["prompt"]["stage"], "knowledge")
        detail = self.client.get(f"/api/history/{attempt_id}").json()
        self.assertEqual(detail["interview_score"]["total"], 49)

    def test_history_is_split_by_domain(self):
        attempt_id, tid = self.finish_knowledge()
        self.score(attempt_id, score_result([tid]))
        interview = self.client.get("/api/history?domain=interview").json()["items"]
        self.assertEqual([item["id"] for item in interview], [attempt_id])
        self.assertEqual(interview[0]["interview_total"], 49)
        ielts = self.client.get("/api/history").json()["items"]
        self.assertNotIn(attempt_id, [item["id"] for item in ielts])
        self.assertEqual(self.client.delete(f"/api/history/{attempt_id}").status_code, 200)
        self.assertEqual(self.client.get("/api/history?domain=interview").json()["items"], [])

    def test_sessions_without_any_answer_stay_out_of_history(self):
        attempt = self.begin({"mode": "iv_knowledge", "count": 1})
        self.complete(attempt["id"], attempt["turns"][0]["id"], transcript="")
        self.assertEqual(self.client.get("/api/history?domain=interview").json()["items"], [])
        response = self.client.post(f"/api/attempts/{attempt['id']}/score", json.dumps({}), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("至少回答", response.json()["error"])


@override_settings(MEDIA_ROOT="/tmp/interview-runtime-test-media")
class InterviewExaminerVoiceTests(RuntimeTestBase):
    def test_background_and_refresh_synthesis_read_chinese_questions_in_chinese(self):
        """Later questions are warmed in the background from DB rows that carry no prompt; they must still be zh."""
        from apps.speaking import examiner_tts_services

        attempt = self.begin({"mode": "iv_knowledge", "count": 2})
        second = SpeakingTurn.objects.get(attempt__attempt_id=attempt["id"], turn_id=attempt["turns"][1]["id"])
        with patch(TTS, side_effect=fake_tts) as tts:
            examiner_tts_services._synthesize_examiner_tts(attempt["id"], second, second.question)
        self.assertEqual(tts.call_args.kwargs.get("language"), "zh")
        self.assertTrue(tts.call_args.kwargs.get("voice", "").startswith("zh_"))
        with patch(TTS, side_effect=fake_tts) as tts:
            examiner_tts_services._volcengine_examiner_tts("Do you work or are you a student?", cache_key="k")
        self.assertNotIn("language", tts.call_args.kwargs)


@override_settings(MEDIA_ROOT="/tmp/interview-runtime-test-media")
class InterviewLaunchOptionTests(RuntimeTestBase):
    """What the practice panel's launch block sends: picked / custom questions, a project text, a JD, planned questions."""

    def test_knowledge_asks_picked_and_custom_questions_up_to_the_count(self):
        mine = Entry.objects.create(user=self.user, kind="knowledge", question="讲讲内存序。", group="C++", source="resume",
                                    source_key="resume:tech:a")
        payload = self.begin({"mode": "iv_knowledge", "count": 3, "entry_ids": [mine.entry_id],
                              "question_ids": ["cpp-1"], "custom_questions": ["epoll 和 select 的区别？"]})
        questions = [turn["question"] for turn in payload["turns"]]
        self.assertEqual(len(questions), 3)
        self.assertIn("讲讲内存序。", questions)
        self.assertIn("epoll 和 select 的区别？", questions)
        self.assertEqual(payload["turns"][questions.index("epoll 和 select 的区别？")]["prompt"]["source"], "custom")

    def test_knowledge_samples_the_picked_pool_down_to_the_count(self):
        payload = self.begin({"mode": "iv_knowledge", "count": 2, "custom_questions": ["题一", "题二", "题三", "题四"]})
        questions = [turn["question"] for turn in payload["turns"]]
        self.assertEqual(len(questions), 2)
        self.assertTrue(set(questions) <= {"题一", "题二", "题三", "题四"})

    def test_knowledge_tops_up_from_the_picked_categories(self):
        payload = self.begin({"mode": "iv_knowledge", "count": 4, "categories": ["cpp"], "custom_questions": ["我的题"]})
        self.assertEqual(len(payload["turns"]), 4)
        self.assertEqual(payload["turns"][0]["question"], "我的题")
        self.assertTrue(all(turn["prompt"]["category"] in {"cpp", "knowledge"} for turn in payload["turns"][1:]))

    def test_project_round_from_a_written_description_needs_no_resume(self):
        text = "## 撮合网关\n用无锁队列把下单延迟从 80us 降到 12us。"
        payload = self.begin({"mode": "iv_project", "project_text": text})
        self.assertEqual(len(payload["turns"]), 1)
        turn = payload["turns"][0]
        self.assertEqual(turn["prompt"]["stage"], "project")
        self.assertIn("撮合网关", turn["question"])
        self.assertEqual(turn["prompt"]["project_context"], text)
        with patch(RUN, return_value=decision("follow_up", "12us 怎么测的？")) as run:
            self.complete(payload["id"], turn["id"])
        self.assertEqual(run.call_args.args[2]["project_context"], text)

    def test_project_round_combines_picked_projects_and_a_description(self):
        self.seed_resume()
        gateway = Entry.objects.get(user=self.user, source_key="resume:project:gw")
        payload = self.begin({"mode": "iv_project", "project_ids": [gateway.entry_id], "project_text": "行情回放系统"})
        self.assertEqual([turn["prompt"]["stage"] for turn in payload["turns"]], ["project", "project"])
        self.assertEqual(payload["turns"][0]["question"], "介绍一下你的「撮合网关」项目。")

    def test_reverse_round_uses_the_session_jd_and_planned_questions(self):
        planned = ["团队怎么衡量延迟？", "新人怎么上手？", "技术栈会怎么演进？"]
        payload = self.begin({"mode": "iv_reverse", "jd_text": "低延迟 C++ 开发", "reverse_questions": planned})
        first = payload["turns"][0]
        self.assertEqual(first["prompt"]["planned_questions"], planned)
        attempt = SpeakingAttempt.objects.get(attempt_id=payload["id"])
        self.assertEqual(attempt.metadata["interview"]["reverse_rounds"], 3)
        reply = {"reply": "按 P99。", "signal": "strong", "evidence": "好问题"}
        turn = first
        for index, question in enumerate(planned):
            with patch(RUN, return_value=reply) as run:
                done = self.complete(payload["id"], turn["id"], question)
            self.assertEqual(run.call_args.args[2]["jd_text"], "低延迟 C++ 开发")
            self.assertTrue(run.call_args.args[2]["has_jd"])
            turn = done["next_turn"]
            if index < 2:
                self.assertEqual(turn["prompt"]["planned_questions"], planned)
        self.assertIsNone(turn)

    def test_full_interview_takes_a_session_jd(self):
        self.seed_resume()
        payload = self.begin({"mode": "iv_full", "jd_text": "低延迟 C++ 开发"})
        attempt = SpeakingAttempt.objects.get(attempt_id=payload["id"])
        self.assertEqual(attempt.metadata["interview"]["jd_text"], "低延迟 C++ 开发")

    def test_bad_launch_input_is_rejected(self):
        for payload in ({"mode": "iv_knowledge", "custom_questions": "不是列表"},
                        {"mode": "iv_reverse", "reverse_questions": ["一", "二", "三", "四", "五", "六"]},
                        {"mode": "iv_project", "project_text": "x" * 8001}):
            response, _ = self.start(payload)
            self.assertEqual(response.status_code, 400, payload)
