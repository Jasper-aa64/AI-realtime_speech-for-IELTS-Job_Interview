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


@override_settings(MEDIA_ROOT="/tmp/interview-runtime-test-media")
class InterviewRuntimeStartTests(TestCase):
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
