import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from . import ai_schema
from .models import InterviewCorpusEntry, InterviewProfile
from .validation import InterviewError

RESUME = "张三，C++ 开发。项目：低延迟撮合网关（P99 从 900µs 降到 55µs）；行情回放系统。ACM 区域赛银牌。"


def resume_output(projects=("gateway", "replay"), intro="我是张三……"):
    titles = {"gateway": "低延迟撮合网关", "replay": "行情回放系统"}
    return {
        "self_intro": {"draft": intro},
        "projects": [{"key": key, "title": titles[key], "summary": f"{titles[key]}一句话", "draft": f"{titles[key]}讲述稿",
                      "followups": [{"question": f"{titles[key]}最难的部分是什么？", "draft": "参考"}]} for key in projects],
        "tech_stack": [{"group": "C++", "questions": [{"question": "讲讲内存序。", "draft": "acquire/release…"}]}],
        "awards": [{"key": "acm", "title": "ACM 区域赛银牌", "draft": "比赛经历"}],
        "provider": "http_api", "model": "fixture", "task_id": "t", "ai_source": "gpt",
    }


class InterviewCorpusTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="corpus-owner", password="pw")
        self.other = get_user_model().objects.create_user(username="corpus-other", password="pw")
        self.client.force_login(self.user)

    def post(self, path, data=None):
        return self.client.post(path, json.dumps(data or {}), content_type="application/json")

    def patch(self, path, data):
        return self.client.patch(path, json.dumps(data), content_type="application/json")

    def import_resume(self, output):
        with patch("apps.interview.corpus.ai_services.run_generation", return_value=output) as run:
            response = self.post("/api/interview/profile/resume/", {"resume_text": RESUME})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json(), run

    def entry(self, source_key):
        return InterviewCorpusEntry.objects.get(user=self.user, source_key=source_key)

    def test_resume_split_creates_ielts_style_material(self):
        payload, run = self.import_resume(resume_output())
        self.assertEqual(run.call_args.args[1], "resume_profile")
        kinds = sorted(e["kind"] for e in payload["entries"] if e["id"])
        self.assertEqual(kinds, ["award", "knowledge", "project", "project", "project_followup", "project_followup", "self_intro"])
        gateway = self.entry("resume:project:gateway")
        self.assertEqual(gateway.question, "介绍一下你的「低延迟撮合网关」项目。")
        self.assertEqual(gateway.ai_draft, "低延迟撮合网关讲述稿")
        self.assertEqual(gateway.children.get().kind, "project_followup")
        modules = InterviewProfile.objects.get(user=self.user).resume_modules
        self.assertEqual([m["kind"] for m in modules], ["self_intro", "project", "project", "tech_stack", "award"])

    def test_resplit_keeps_my_answer_and_marks_removed_projects(self):
        self.import_resume(resume_output())
        gateway = self.entry("resume:project:gateway")
        self.patch(f"/api/interview/corpus/{gateway.entry_id}/", {"corpus_text": "我自己的讲述"})
        output = resume_output(projects=("gateway",))
        output["projects"][0]["draft"] = "新的 AI 稿"
        self.import_resume(output)
        gateway.refresh_from_db()
        self.assertEqual(gateway.corpus_text, "我自己的讲述")
        self.assertEqual(gateway.ai_draft, "新的 AI 稿")
        self.assertTrue(self.entry("resume:project:replay").metadata["orphaned"])
        self.assertFalse(gateway.metadata.get("orphaned"))

    def test_jd_split_creates_role_questions_and_reverse_round(self):
        output = {"summary": {"role": "C++ 低延迟开发", "requirements": ["熟悉 Linux 网络"]},
                  "questions": [{"question": "如何排查网络抖动？", "draft": "…"}],
                  "reverse_questions": [{"question": "团队如何衡量延迟？", "draft": "想了解指标"}],
                  "provider": "http_api", "model": "m", "task_id": "t", "ai_source": "gpt"}
        with patch("apps.interview.corpus.ai_services.run_generation", return_value=output):
            response = self.post("/api/interview/profile/jd/", {"job_description": "招聘 C++ 低延迟开发"})
        self.assertEqual(response.status_code, 200, response.content)
        kinds = sorted(e["kind"] for e in response.json()["entries"] if e["id"])
        self.assertEqual(kinds, ["jd_question", "reverse_question"])
        self.assertEqual(response.json()["profile"]["jd"]["summary"]["role"], "C++ 低延迟开发")

    def test_curated_questions_listed_and_saved_once(self):
        listing = self.client.get("/api/interview/corpus/?kind=knowledge").json()["entries"]
        curated = [e for e in listing if e["source"] == "curated"]
        self.assertEqual(len(curated), 30)
        key = curated[0]["source_key"]
        first = self.post("/api/interview/corpus/", {"kind": "knowledge", "source_key": key, "corpus_text": "我的答法"}).json()
        again = self.post("/api/interview/corpus/", {"kind": "knowledge", "source_key": key}).json()
        self.assertEqual(first["entry"]["id"], again["entry"]["id"])
        listing = self.client.get("/api/interview/corpus/?kind=knowledge").json()["entries"]
        self.assertEqual(len(listing), 30)
        reword = self.patch(f"/api/interview/corpus/{first['entry']['id']}/", {"question": "改题"})
        self.assertEqual(reword.json()["code"], "read_only_question")
        bad = self.post("/api/interview/corpus/", {"kind": "knowledge", "source_key": "resume:project:x"})
        self.assertEqual(bad.json()["code"], "invalid_source_key")

    def test_custom_entries_owner_isolation_and_delete(self):
        created = self.post("/api/interview/corpus/", {"kind": "reverse_question", "question": "新人如何上手？"}).json()["entry"]
        self.assertEqual(created["source"], "custom")
        self.client.force_login(self.other)
        self.assertEqual(self.patch(f"/api/interview/corpus/{created['id']}/", {"corpus_text": "x"}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/interview/corpus/{created['id']}/").status_code, 404)
        self.client.force_login(self.user)
        self.assertEqual(self.client.delete(f"/api/interview/corpus/{created['id']}/").status_code, 200)
        self.assertFalse(InterviewCorpusEntry.objects.filter(entry_id=created["id"]).exists())

    def test_ai_failure_leaves_profile_untouched(self):
        error = InterviewError("AI generation failed; please retry.", code="ai_generation_failed", status=502)
        with patch("apps.interview.corpus.ai_services.run_generation", side_effect=error):
            response = self.post("/api/interview/profile/resume/", {"resume_text": RESUME})
        self.assertEqual(response.status_code, 502)
        self.assertFalse(InterviewCorpusEntry.objects.filter(user=self.user).exists())
        self.assertEqual(self.client.get("/api/interview/profile/").json()["profile"]["resume"]["text"], "")

    def test_generate_draft_for_entry(self):
        created = self.post("/api/interview/corpus/", {"kind": "knowledge", "question": "什么是 false sharing？"}).json()["entry"]
        with patch("apps.interview.corpus.ai_services.run_generation", return_value={"draft": "两个核心写同一缓存行…"}):
            response = self.post(f"/api/interview/corpus/{created['id']}/draft/")
        self.assertEqual(response.json()["entry"]["ai_draft"], "两个核心写同一缓存行…")


class InterviewSchemaTests(TestCase):
    def test_resume_output_shape_is_enforced(self):
        with self.assertRaises(ValueError):
            ai_schema.validate("resume_profile", {"projects": "not a list"}, {})
        with self.assertRaises(ValueError):
            ai_schema.validate("resume_profile", {"self_intro": {"draft": ""}, "projects": [], "tech_stack": []}, {})
        ok = ai_schema.validate("resume_profile", {"projects": [{"title": "网关", "draft": "稿"}, {"title": "网关", "draft": "稿"}]}, {})
        self.assertEqual([p["key"] for p in ok["projects"]], ["网关", "网关-2"])

    def test_next_step_rejects_repeats_and_unknown_actions(self):
        with self.assertRaises(ValueError):
            ai_schema.validate("next_step", {"action": "lecture"}, {})
        with self.assertRaises(ValueError):
            ai_schema.validate("next_step", {"action": "follow_up", "prompt": "为什么？"}, {"asked": ["为什么？"]})
        done = ai_schema.validate("next_step", {"action": "next", "prompt": "ignored", "signal": "loud"}, {})
        self.assertEqual((done["prompt"], done["signal"]), ("", "adequate"))

    def test_score_report_ranges_and_total(self):
        dims = {key: {"score": maximum, "evidence": "e"} for key, _, maximum in ai_schema.DIMENSIONS}
        report = ai_schema.validate("score_report", {"dimensions": dims, "per_turn": [{"turn_id": "x", "comment": "c"},
                                                                                      {"turn_id": "nope", "comment": "c"}]},
                                    {"turn_ids": ["x"]})
        self.assertEqual(report["total"], 100)
        self.assertEqual([p["turn_id"] for p in report["per_turn"]], ["x"])
        dims["structure"]["score"] = 21
        with self.assertRaises(ValueError):
            ai_schema.validate("score_report", {"dimensions": dims}, {})
