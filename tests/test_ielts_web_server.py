import json
import os
import subprocess
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import ielts_server  # noqa: E402
from ielts_server import AppState, IELTSHandler, build_ai_coaching, build_learning_profile, build_overall_review, build_turn_band7_fallback, calibrate_realistic_score, clean_band7_output, score_with_codex, valid_turn_band7, writing_word_count  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


class IELTSWebServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["IELTS_WEB_DISABLE_CODEX"] = "1"
        os.environ["IELTS_WEB_DISABLE_VOLCENGINE_TTS"] = "1"
        IELTSHandler.state = AppState(ROOT / "data" / "ielts", Path(cls.temp_dir.name))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), IELTSHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp_dir.cleanup()
        os.environ.pop("IELTS_WEB_DISABLE_CODEX", None)
        os.environ.pop("IELTS_WEB_DISABLE_VOLCENGINE_TTS", None)

    def get_json(self, path):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(self.base_url + path, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_raw(self, path):
        request = urllib.request.Request(self.base_url + path)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))
        self.fail("Expected HTTPError")

    def get_response(self, path, headers=None):
        request = urllib.request.Request(self.base_url + path, headers=headers or {})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read()

    def post_json(self, path, payload):
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def post_raw(self, path, body, content_type="application/json"):
        request = urllib.request.Request(
            self.base_url + path,
            data=body.encode("utf-8"),
            headers={"Content-Type": content_type},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))
        self.fail("Expected HTTPError")

    def post_response(self, path, payload, headers=None):
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            return response.status, dict(response.headers), json.loads(response.read().decode("utf-8"))

    def start_isolated_server(self, name):
        previous_state = IELTSHandler.state
        state_dir = Path(self.temp_dir.name) / name
        IELTSHandler.state = AppState(ROOT / "data" / "ielts", state_dir)
        server = ThreadingHTTPServer(("127.0.0.1", 0), IELTSHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return f"http://127.0.0.1:{server.server_port}", server, thread, previous_state

    def get_json_from(self, base_url, path):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(base_url + path, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def post_json_to(self, base_url, path, payload):
        request = urllib.request.Request(
            base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_question_bank_summary_and_sample(self):
        summary = self.get_json("/api/question-bank/summary?cache_bust=1")
        self.assertGreaterEqual(summary["part1_count"], 15)
        self.assertGreaterEqual(summary["part2_count"], 3)

        sample = self.post_json("/api/session/start?mode=full", {"p1_count": 3, "mode": "full"})
        self.assertIn("session_id", sample)
        self.assertEqual(len(sample["part1"]), 3)
        self.assertIn("question", sample["part1"][0])
        self.assertIn("title", sample["part2"])

    def test_account_requests_proxy_to_django_and_forward_cookie(self):
        class FakeDjangoHandler(BaseHTTPRequestHandler):
            def log_message(self, _fmt, *_args):
                return

            def do_POST(self):
                size = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(size).decode("utf-8") if size else "{}"
                payload = json.loads(raw)
                if self.path != "/api/accounts/login/":
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps({"user": {"username": payload["username"], "profile": {"full_name": "LiHua", "english_name": "Jasper"}}}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", "sessionid=fake-session; Path=/; HttpOnly")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        fake_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeDjangoHandler)
        thread = threading.Thread(target=fake_server.serve_forever, daemon=True)
        thread.start()
        fake_url = f"http://127.0.0.1:{fake_server.server_port}"
        try:
            with mock.patch.object(ielts_server, "DJANGO_BACKEND_URL", fake_url):
                status, headers, payload = self.post_response(
                    "/api/accounts/login/",
                    {"username": "18728445038", "password": "test-pass-123"},
                )
        finally:
            fake_server.shutdown()
            fake_server.server_close()
        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["username"], "18728445038")
        self.assertIn("sessionid=fake-session", headers.get("Set-Cookie", ""))

    def test_writing_prompt_save_summary_and_fallback_score(self):
        prompts = self.get_json("/api/writing/prompts?task_type=task1_academic")
        self.assertGreaterEqual(len(prompts["items"]), 3)
        self.assertEqual(prompts["items"][0]["task_type"], "task1_academic")

        random_prompt = self.post_json("/api/writing/prompts/random", {"task_type": "task2"})
        self.assertEqual(random_prompt["task_type"], "task2")
        answer = (
            "Technology can make learning easier because students can review lessons at any time. "
            "However, it can also distract them if they use social media during study. "
            "In my view, schools should teach students how to use digital tools with clear limits."
        )
        saved = self.post_json(
            "/api/writing/entries",
            {
                "task_type": random_prompt["task_type"],
                "prompt_id": random_prompt["id"],
                "prompt": random_prompt["prompt"],
                "title": random_prompt["title"],
                "answer": answer,
                "practice_date": "2026-05-14",
            },
        )
        self.assertEqual(saved["status"], "saved")
        self.assertEqual(saved["word_count"], 41)

        summary = self.get_json("/api/writing/summary?month=2026-05")
        day = next(item for item in summary["days"] if item["date"] == "2026-05-14")
        self.assertEqual(day["status"], "saved")
        self.assertEqual(day["entry_id"], saved["id"])
        self.assertTrue(any(item["id"] == saved["id"] for item in summary["recent_entries"]))

        scored = self.post_json(f"/api/writing/entries/{saved['id']}/score", {})
        self.assertEqual(scored["status"], "scored")
        self.assertEqual(scored["score"]["backend"], "fallback")
        self.assertIn("AI 评分生成失败", scored["score"]["feedback_markdown"])
        self.assertIn("语法错误纠正", scored["score"]["feedback_markdown"])
        self.assertIn("writing_profile", scored)
        self.assertEqual(scored["writing_profile"]["total_scored"], 1)
        self.assertIn("profile_tags", scored["score"])

        detail = self.get_json(f"/api/writing/entries/{saved['id']}")
        self.assertEqual(detail["id"], saved["id"])
        self.assertEqual(detail["status"], "scored")
        profile_path = IELTSHandler.state.writing_profile_path(saved["user_id"])
        self.assertTrue(profile_path.exists())
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        self.assertEqual(profile["total_scored"], 1)

        summary_after = self.get_json("/api/writing/summary?month=2026-05")
        day_after = next(item for item in summary_after["days"] if item["date"] == "2026-05-14")
        self.assertEqual(day_after["status"], "scored")

    def test_writing_score_uses_codex_and_billing_usage_when_available(self):
        previous_disable = os.environ.pop("IELTS_WEB_DISABLE_CODEX", None)
        base_url, server, thread, previous_state = self.start_isolated_server("writing-codex-score")
        output = "\n".join(
            [
                json.dumps(
                    {
                        "type": "message",
                        "content": json.dumps(
                            {
                                "overall_band": 6,
                                "task_response": 6,
                                "coherence_cohesion": 6,
                                "lexical_resource": 6,
                                "grammatical_range_accuracy": 6,
                                "feedback_markdown": "- 观点清楚，但主体段还需要更具体的例子。\n- 语法错误纠正：\n  1. 无",
                                "grammar_corrections": [],
                            }
                        ),
                    }
                ),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 0, "output_tokens": 100, "reasoning_output_tokens": 0}}),
            ]
        )
        try:
            random_prompt = self.post_json_to(base_url, "/api/writing/prompts/random", {"task_type": "task2"})
            saved = self.post_json_to(
                base_url,
                "/api/writing/entries",
                {
                    "task_type": "task2",
                    "prompt_id": random_prompt["id"],
                    "prompt": random_prompt["prompt"],
                    "answer": "I think technology helps students learn because it gives them flexible access to lessons and examples.",
                    "practice_date": "2026-05-14",
                },
            )
            with mock.patch("ielts_server.shutil.which", return_value="codex"), mock.patch("ielts_server.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(["codex", "exec", "--json"], 0, stdout=output, stderr="")
                scored = self.post_json_to(base_url, f"/api/writing/entries/{saved['id']}/score", {})
            self.assertEqual(scored["score"]["backend"], "codex")
            self.assertEqual(scored["score"]["overall_band"], 6.0)
            self.assertIn("billing_usage", scored["score"])
            prompt_text = run.call_args.kwargs["input"]
            self.assertIn("Learner writing profile", prompt_text)
            self.assertIn("own real writing", prompt_text)
            wallet = self.get_json_from(base_url, "/api/billing/wallet")
            self.assertTrue(any(entry["entry_type"] == "settle" and entry["call_id"] == f"writing_score_{saved['id']}" for entry in wallet["entries"]))
        finally:
            if previous_disable is not None:
                os.environ["IELTS_WEB_DISABLE_CODEX"] = previous_disable
            else:
                os.environ["IELTS_WEB_DISABLE_CODEX"] = "1"
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            IELTSHandler.state = previous_state

    def test_writing_profile_accumulates_scored_entries(self):
        prompt = self.post_json("/api/writing/prompts/random", {"task_type": "task2"})
        first = self.post_json(
            "/api/writing/entries",
            {
                "task_type": "task2",
                "prompt_id": prompt["id"],
                "prompt": prompt["prompt"],
                "answer": "I agree because online tools can help students study after school.",
                "practice_date": "2026-05-15",
                "user_id": "writing-profile-test",
            },
        )
        first_scored = self.post_json(f"/api/writing/entries/{first['id']}/score", {})
        self.assertEqual(first_scored["writing_profile"]["total_scored"], 1)
        self.assertIn("under_length", first_scored["score"]["profile_tags"])

        second = self.post_json(
            "/api/writing/entries",
            {
                "task_type": "task2",
                "prompt_id": prompt["id"],
                "prompt": prompt["prompt"],
                "answer": " ".join(["This essay explains one clear reason for practice"] * 45),
                "practice_date": "2026-05-16",
                "user_id": "writing-profile-test",
            },
        )
        self.assertGreaterEqual(writing_word_count(second["answer"]), 250)
        second_scored = self.post_json(f"/api/writing/entries/{second['id']}/score", {})
        self.assertEqual(second_scored["writing_profile"]["total_scored"], 2)
        self.assertGreaterEqual(second_scored["writing_profile"]["average_overall_band"], 4.0)

    def test_score_uses_deterministic_fallback_without_server_cli_env(self):
        payload = self.post_json(
            "/api/score",
            {
                "part": "p2",
                "question": "Describe a useful skill.",
                "transcript": "I learned cooking from my parents. It helps me manage daily life and share food with friends.",
            },
        )
        self.assertEqual(payload["score"]["backend"], "heuristic")
        self.assertIn("overall_band", payload["score"])
        self.assertEqual(payload["report"]["candidate"], "jasper")

    def test_overall_band_rounds_to_nearest_half(self):
        from ielts_server import rounded_overall  # noqa: E402

        self.assertEqual(rounded_overall({"fluency_coherence": 6.0, "lexical_resource": 6.0, "grammatical_range": 6.0}), 6.0)
        self.assertEqual(rounded_overall({"fluency_coherence": 6.0, "lexical_resource": 6.0, "grammatical_range": 6.5}), 6.0)
        self.assertEqual(rounded_overall({"fluency_coherence": 6.5, "lexical_resource": 6.5, "grammatical_range": 6.5}), 6.5)
        self.assertEqual(rounded_overall({"fluency_coherence": 6.5, "lexical_resource": 6.5, "grammatical_range": 7.0}), 6.5)

    def test_calibration_caps_short_generic_part2_and_keeps_pronunciation_null(self):
        score = calibrate_realistic_score(
            {
                "fluency_coherence": 7.0,
                "lexical_resource": 7.0,
                "grammatical_range": 7.0,
                "overall_band": 7.0,
                "feedback": "Clear answer.",
            },
            "Describe a person who helped you.",
            "This person is very important. He is very kind. He helped me a lot. It made me feel relaxed.",
            "p2",
        )
        self.assertLessEqual(score["overall_band"], 5.0)
        self.assertLessEqual(score["fluency_coherence"], 5.0)
        self.assertIn("Part 2 is too short", score["feedback"])

    def test_calibration_caps_underdeveloped_part3_discussion(self):
        score = calibrate_realistic_score(
            {
                "fluency_coherence": 7.0,
                "lexical_resource": 7.0,
                "grammatical_range": 7.0,
                "overall_band": 7.0,
                "feedback": "Clear opinion.",
            },
            "Why do people use technology at work?",
            "I think people use technology at work. It is very convenient. It is very important in modern society.",
            "p3",
        )
        self.assertLessEqual(score["overall_band"], 5.5)
        self.assertLessEqual(score["lexical_resource"], 5.5)
        self.assertIn("Part 3", score["feedback"])

    def test_calibration_caps_template_like_part2_more_strictly(self):
        score = calibrate_realistic_score(
            {
                "fluency_coherence": 7.0,
                "lexical_resource": 7.0,
                "grammatical_range": 7.0,
                "overall_band": 7.0,
                "feedback": "Fluent but thin.",
            },
            "Describe a useful skill.",
            (
                "It is very important for me because it is very convenient. "
                "It is very important in modern society and it is good for me. "
                "It is very important for my future and it can improve my life."
            ),
            "p2",
        )
        self.assertLessEqual(score["overall_band"], 5.0)
        self.assertLessEqual(score["fluency_coherence"], 5.0)
        self.assertIn("generic or repetitive wording", score["feedback"])

    def test_calibration_no_longer_caps_overall_for_missing_pronunciation(self):
        previous_disable = os.environ.pop("IELTS_WEB_DISABLE_CODEX", None)
        output = json.dumps(
            {
                "type": "message",
                "content": json.dumps(
                    {
                        "fluency_coherence": 7,
                        "lexical_resource": 7,
                        "grammatical_range": 7,
                        "overall_band": 7,
                        "feedback": "Strong content.",
                    }
                ),
            }
        )
        transcript = (
            "I think people use technology at work because it saves time and reduces repeated tasks. "
            "For example, a team can coordinate schedules more quickly, compare documents, and check progress in one place. "
            "However, they still need to judge whether the tool actually improves communication, because not every system is useful. "
            "In my view, the key point is that technology should support clear human decisions rather than replace them completely."
        )
        try:
            with mock.patch("ielts_server.shutil.which", return_value="codex"), mock.patch("ielts_server.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(["codex", "exec", "--json"], 0, stdout=output, stderr="")
                score = score_with_codex(
                    transcript,
                    ROOT / "data" / "ielts",
                    "Why do people use technology at work?",
                    None,
                    "call_text_only_cap",
                    "p3",
                )
            self.assertEqual(score["backend"], "codex")
            self.assertEqual(score["overall_band"], 7.0)
        finally:
            if previous_disable is not None:
                os.environ["IELTS_WEB_DISABLE_CODEX"] = previous_disable
            else:
                os.environ["IELTS_WEB_DISABLE_CODEX"] = "1"

    def test_calibration_does_not_over_cap_valid_part1_answers(self):
        score = calibrate_realistic_score(
            {
                "fluency_coherence": 7.0,
                "lexical_resource": 7.0,
                "grammatical_range": 7.0,
                "overall_band": 7.0,
                "feedback": "Strong answer.",
            },
            "Do you like reading?",
            "Yes, I like reading because it helps me relax after a busy day and learn new ideas. Usually I read in the evening, and sometimes I share interesting books with my friends.",
            "p1",
        )
        self.assertGreaterEqual(score["overall_band"], 6.5)
        self.assertLessEqual(score["overall_band"], 7.0)

    def test_p3_generation_falls_back_without_server_cli_env(self):
        payload = self.post_json("/api/p3/questions", {"theme": "technology_and_society"})
        self.assertEqual(payload["backend"], "fallback")
        self.assertEqual(len(payload["questions"]), 5)
        self.assertIn("follow_up", payload)

    def test_p1_attempt_uses_ten_turns_and_scores_after_completion(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p1", "mode": "p1"})
        self.assertEqual(attempt["part"], "p1")
        self.assertEqual(attempt["candidate"], "Jasper")
        self.assertEqual(len(attempt["turns"]), 11)
        self.assertEqual(len([turn for turn in attempt["turns"] if turn.get("counts_toward_total")]), 10)
        self.assertEqual(attempt["turns"][0]["question"], "What is your full name?")
        self.assertEqual(attempt["turns"][0]["prompt"]["flow"], "intro")
        self.assertEqual(attempt["turns"][0]["prompt"]["role"], "name")
        self.assertFalse(attempt["turns"][0]["counts_toward_total"])
        self.assertEqual(attempt["turns"][0]["display_index"], 0)
        self.assertEqual(attempt["turns"][1]["question"], "Do you work or do you study?")
        self.assertEqual(attempt["turns"][1]["prompt"]["flow"], "intro")
        self.assertEqual(attempt["turns"][1]["prompt"]["role"], "work_study")
        self.assertTrue(attempt["turns"][1]["counts_toward_total"])
        self.assertEqual(attempt["turns"][1]["display_index"], 1)
        ordinary_questions = [turn["question"].lower() for turn in attempt["turns"][2:]]
        scattered_work_study = [
            "do you work or are you a full-time student?",
            "are you a student or do you work?",
            "do you work or study?",
            "what subject are you studying or what did you study?",
        ]
        for question in ordinary_questions:
            self.assertNotIn(question, scattered_work_study)
        self.assertEqual(attempt["turns"][0]["timers"]["prep_seconds"], 3)
        self.assertEqual(attempt["turns"][0]["examiner_behavior"], "auto_play_question")
        self.assertEqual(attempt["turns"][0]["examiner_tts"]["status"], "fallback")

        status, payload = self.post_raw(f"/api/attempts/{attempt['id']}/score", "{}")
        self.assertEqual(status, 400)
        self.assertIn("Complete all speaking turns", payload["error"])

        initial_turn_ids = {turn["id"] for turn in attempt["turns"]}
        turn = attempt["turns"][0]
        completed = None
        completed_ids = []
        while turn:
            self.upload_audio(attempt["id"], turn["id"], b"fake-webm-audio")
            transcript = (
                "I study computer science at university because I enjoy solving practical problems."
                if (turn.get("prompt") or {}).get("role") == "work_study"
                else (
                    "I chose that major because it connects logical thinking with useful real-world tools."
                    if (turn.get("prompt") or {}).get("role") == "follow_up"
                    else (
                        "I usually answer this question with one reason and one example "
                        "because that makes my speaking clearer."
                    )
                )
            )
            completed = self.post_json(
                f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
                {"transcript_raw": transcript},
            )
            completed_ids.append(turn["id"])
            if (turn.get("prompt") or {}).get("role") == "work_study":
                follow_up = completed["next_turn"]
                self.assertIsNotNone(follow_up)
                self.assertNotIn(follow_up["id"], initial_turn_ids)
                self.assertEqual(follow_up["part"], "p1")
                self.assertEqual(follow_up["prompt"]["flow"], "intro")
                self.assertEqual(follow_up["prompt"]["role"], "follow_up")
                self.assertEqual(follow_up["prompt"]["after_role"], "work_study")
                self.assertFalse(follow_up["prompt"]["counts_toward_total"])
                self.assertEqual(follow_up["total"], 10)
                self.assertIn("major", follow_up["question"].lower())
                self.assertEqual(len(completed["attempt"]["turns"]), 12)
            turn = completed["next_turn"]
        self.assertIsNone(completed["next_turn"])
        self.assertEqual(len(completed_ids), 12)

        scored = self.post_json(f"/api/attempts/{attempt['id']}/score", {})
        self.assertEqual(scored["status"], "scored")
        self.assertIn("criteria_feedback", scored)
        self.assertIn("band7_version", scored)
        self.assertEqual(scored["band7_version"], "")
        self.assertIn("part_scores", scored)
        self.assertIn("learning_profile", scored)
        self.assertIn("personalized_coaching", scored)
        self.assertIn("overall_review", scored)
        self.assertIn("habit_tags", scored["learning_profile"])
        self.assertIn("primary_focus", scored["learning_profile"])
        self.assertIn("focus", scored["personalized_coaching"])
        self.assertIn("next_practice", scored["personalized_coaching"])
        self.assertIn("comment", scored["overall_review"])
        self.assertIn("review_points", scored["overall_review"])
        self.assertIn("### 总体点评", scored["overall_review"]["markdown"])
        self.assertIn("p1", scored["part_scores"])
        self.assertEqual(scored["part_scores"]["p1"]["part"], "p1")
        self.assertIn("model_audio", scored)
        self.assertIsNone(scored["model_audio"])
        self.assertTrue(scored["turns"][0]["band7_version"])
        self.assertTrue(scored["turns"][0]["ai_coaching"])
        self.assertTrue(scored["turns"][0]["upgrade_notes"])
        self.assertIn("model_audio", scored["turns"][0])
        self.assertNotIn("china_explanation", scored)

        history = self.get_json("/api/history")
        self.assertTrue(any(item["id"] == attempt["id"] for item in history["items"]))

        detail = self.get_json(f"/api/history/{attempt['id']}")
        self.assertEqual(detail["id"], attempt["id"])

    def test_p1_name_intro_uses_settings_names_and_corrects_transcript(self):
        attempt = self.post_json(
            "/api/attempts/start",
            {"part": "p1", "mode": "p1", "full_name": "LiHua", "english_name": "Jasper"},
        )
        turn = attempt["turns"][0]
        self.assertFalse(turn["counts_toward_total"])
        completed = self.post_json(
            f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
            {"transcript_raw": "my full name is Foundry you can come in Jasper"},
        )
        completed_turn = completed["turn"]
        self.assertEqual(completed_turn["transcript_cleaned"], "My full name is LiHua, but you can call me Jasper.")
        self.assertTrue(completed_turn["identity_corrected"])
        scored = self.complete_remaining_and_score(completed["attempt"], completed["next_turn"])
        scored_name_turn = scored["turns"][0]
        self.assertEqual(scored_name_turn["band7_version"], "My full name is LiHua, but you can call me Jasper.")

    def test_p1_work_study_completion_uses_deterministic_followup_without_codex(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p1", "mode": "p1"})
        turn = attempt["turns"][1]
        self.assertEqual(turn["prompt"]["role"], "work_study")

        tts_payload = {"provider": "volcengine", "status": "ready", "audio_url": "/api/tts-audio/examiner/follow.mp3"}
        with (
            mock.patch("ielts_server.generate_p1_identity_follow_up") as generate_followup,
            mock.patch("ielts_server.run_codex") as run_codex,
            mock.patch("ielts_server.volcengine_tts", return_value=tts_payload) as tts,
            mock.patch("ielts_server.schedule_turn_feedback_generation"),
        ):
            completed = self.post_json(
                f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
                {"transcript_raw": "I study computer science at university because I enjoy practical problem solving."},
            )

        generate_followup.assert_not_called()
        run_codex.assert_not_called()
        tts.assert_called_once()
        followup = completed["next_turn"]
        self.assertIsNotNone(followup)
        self.assertEqual(followup["prompt"]["role"], "follow_up")
        self.assertEqual(followup["prompt"]["backend"], "fallback")
        self.assertEqual(followup["prompt"]["generation_status"], "skipped_sync_ai")
        self.assertIn("major", followup["question"].lower())
        self.assertEqual(followup["examiner_tts"]["provider"], "volcengine")
        self.assertEqual(followup["examiner_tts"]["status"], "ready")

    def test_learning_profile_uses_current_attempt_and_weak_history(self):
        base_url, server, thread, previous_state = self.start_isolated_server("learning-profile")
        try:
            attempt = self.post_json_to(base_url, "/api/attempts/start", {"part": "p2", "mode": "p2"})
            turn = attempt["turns"][0]
            self.upload_audio_to(base_url, attempt["id"], turn["id"], b"fake-webm-audio")
            self.post_json_to(
                base_url,
                f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
                {"transcript_raw": "It is very important for me because it is very convenient."},
            )
            scored = self.post_json_to(base_url, f"/api/attempts/{attempt['id']}/score", {})
            profile = scored["learning_profile"]
            coaching = scored["personalized_coaching"]
            review = scored["overall_review"]
            self.assertIn("habit_tags", profile)
            self.assertIn("template_language", profile["habit_tags"])
            self.assertIn("evidence", profile)
            self.assertTrue(profile["evidence"])
            self.assertIn("headline", coaching)
            self.assertIn("next_practice", coaching)
            self.assertEqual(review["source"], "learning_profile")
            self.assertTrue(review["review_points"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            IELTSHandler.state = previous_state

    def test_learning_profile_direct_unit_uses_turns_and_weak_history(self):
        state = AppState(ROOT / "data" / "ielts", Path(self.temp_dir.name) / "profile-unit")
        attempt = {
            "id": "attempt_profile",
            "user_id": "local-default",
            "turns": [
                {
                    "part": "p2",
                    "status": "completed",
                    "question": "Describe a useful skill.",
                    "transcript_cleaned": "It is very important because it is very convenient.",
                    "pronunciation": {"status": "not_configured"},
                },
                {
                    "part": "p3",
                    "status": "completed",
                    "question": "Why do people use technology at work?",
                    "transcript_cleaned": "I think it is very important in modern society.",
                    "pronunciation": {"status": "not_configured"},
                },
            ],
        }
        state.training.record_observation(
            {
                "observation_id": "obs1",
                "user_id": "local-default",
                "attempt_id": "old",
                "turn_id": "t1",
                "question_id": "p2_001",
                "part": "p2",
                "question": "Describe a useful skill.",
                "transcript": "It is very important because it is very convenient.",
                "overall_band": 4.5,
                "fluency_coherence": 4.5,
                "lexical_resource": 4.5,
                "grammatical_range": 4.5,
                "relevance": 0.9,
                "weak_item_flag": True,
                "weak_reason": ["short_answer", "template_language"],
                "model_version": "heuristic",
                "observed_at": "2026-05-12T00:00:00+00:00",
                "next_due": "2026-05-13T00:00:00+00:00",
            }
        )
        profile = build_learning_profile(state, attempt, {"overall_band": 4.5, "feedback": "Need more development."})
        self.assertIn("primary_focus", profile)
        self.assertIn("habit_tags", profile)
        self.assertIn("recurring_weak_reasons", profile)
        self.assertIn("repeated_phrases", profile)
        self.assertIn("part_focus", profile)
        self.assertIn("evidence", profile)
        self.assertIn("short_answer", profile["habit_tags"])
        self.assertIn("template_language", profile["habit_tags"])
        self.assertTrue(profile["repeated_phrases"])

    def test_p2_start_preserves_cue_card_and_p3_has_high_intensity_topic_flow(self):
        p2 = self.post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
        self.assertEqual(p2["part"], "p2")
        self.assertEqual(len(p2["turns"]), 1)
        self.assertIn("cue_card", p2)
        self.assertEqual(p2["turns"][0]["timers"]["prep_seconds"], 60)
        self.assertEqual(p2["turns"][0]["examiner_behavior"], "auto_play_instruction_only")
        self.assertNotIn("You should say", p2["turns"][0]["examiner_text"])
        self.assertNotIn(p2["cue_card"]["title"], p2["turns"][0]["examiner_text"])
        for bullet in p2["cue_card"]["bullets"]:
            self.assertNotIn(bullet, p2["turns"][0]["examiner_text"])
        self.assertIn("one minute to think", p2["turns"][0]["examiner_text"])
        self.assertIn("You should say", p2["turns"][0]["question"])

        p3 = self.post_json("/api/attempts/start", {"part": "p3", "mode": "p3", "theme": "urban transport"})
        self.assertEqual(p3["part"], "p3")
        self.assertEqual(len(p3["turns"]), 10)
        self.assertEqual(p3["p3_intensity"], "high")
        self.assertEqual(p3["p3_generation_source"], "topic")
        self.assertIn("urban transport", p3["title"])
        self.assertNotEqual(p3.get("p3_theme"), p2["cue_card"]["p3_theme"])
        self.assertEqual(p3["turns"][0]["timers"]["prep_seconds"], 7)
        self.assertEqual(p3["turns"][0]["examiner_behavior"], "auto_play_question")
        self.assertEqual(p3["turns"][1]["prompt"]["role"], "follow_up")

        first_turn = p3["turns"][0]
        self.upload_audio(p3["id"], first_turn["id"], b"fake-webm-audio")
        completed = self.post_json(
            f"/api/attempts/{p3['id']}/turns/{first_turn['id']}/complete",
            {
                "transcript_raw": (
                    "In my city, public transport is useful because buses and trains reduce pressure on roads, "
                    "but people still choose private cars when services are unreliable, expensive, or too crowded "
                    "during the morning commute, especially when they need to drop children at school, carry heavy "
                    "bags, or arrive exactly on time for work."
                )
            },
        )
        self.assertEqual(completed["next_turn"]["prompt"]["source"], "adaptive_answer")
        self.assertIn("opposite argument", completed["next_turn"]["question"])

        normal_p3 = self.post_json(
            "/api/attempts/start",
            {"part": "p3", "mode": "p3", "theme": "urban transport", "p3_intensity": "normal"},
        )
        self.assertEqual(normal_p3["p3_intensity"], "normal")
        self.assertEqual(len(normal_p3["turns"]), 5)
        self.assertTrue(all(turn["prompt"]["role"] == "main" for turn in normal_p3["turns"]))

    def test_p2_score_includes_markdown_ready_transcript_and_model_answer(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
        turn = attempt["turns"][0]
        self.upload_audio(attempt["id"], turn["id"], b"fake-webm-audio")
        self.post_json(
            f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
            {
                "transcript_raw": (
                    "I want to describe a neighbour who helped me after I moved house. "
                    "She explained where to buy food and how to use the local bus. "
                    "That made me feel less nervous because the area was new to me."
                )
            },
        )

        with mock.patch("ielts_server.turn_feedback_with_codex") as feedback:
            feedback.return_value = {
                "band7_version": (
                    "I would like to describe a neighbour who helped me after I moved house. "
                    "She showed me where to buy food and how to use the local bus, which made the new area feel much easier to manage. "
                    "What I appreciated most was that she did not just give me quick directions; she patiently explained the routines in the neighbourhood. "
                    "Because of that, I felt more confident and settled in much faster than I expected."
                ),
                "ai_coaching": "- 这题已经有基本故事线，下一步要把帮助前后的变化说清楚。\n- 语法错误纠正：无",
            }
            scored = self.post_json(f"/api/attempts/{attempt['id']}/score", {"target_band": 7.5})
        feedback.assert_called_once()
        scored_turn = scored["turns"][0]
        self.assertTrue(scored_turn["transcript_cleaned"])
        self.assertTrue(scored_turn["band7_version"])
        self.assertEqual(scored["band7_version"], "")
        self.assertIsNone(scored["model_audio"])
        self.assertEqual(scored["target_band"], 7.5)
        self.assertEqual(scored_turn["target_band"], "7.5")
        self.assertTrue(scored_turn["target_band_version"])
        self.assertTrue(scored_turn["target_band_markdown"])
        self.assertIn("\n\n", scored_turn["transcript_markdown"])
        self.assertIn("\n\n", scored_turn["band7_markdown"])
        self.assertIn("neighbour who helped me", scored_turn["transcript_markdown"])
        self.assertIn("- ", scored_turn["ai_coaching"])
        self.assertNotIn("AI 辅导生成失败，以下是系统默认建议。", scored_turn["ai_coaching"])
        self.assertEqual(scored_turn["feedback_generation_backend"], "codex")
        self.assertIn("语法错误纠正", scored_turn["ai_coaching"])
        self.assertIn("overall_review", scored)

    def test_p2_score_falls_back_to_default_coaching_when_turn_feedback_codex_fails(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
        turn = attempt["turns"][0]
        self.upload_audio(attempt["id"], turn["id"], b"fake-webm-audio")
        self.post_json(
            f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
            {
                "transcript_raw": (
                    "I want to describe a neighbour who helped me after I moved house. "
                    "She explained where to buy food and how to use the local bus."
                )
            },
        )

        with mock.patch("ielts_server.turn_feedback_with_codex", side_effect=RuntimeError("codex unavailable")):
            scored = self.post_json(f"/api/attempts/{attempt['id']}/score", {"target_band": 7.5})
        scored_turn = scored["turns"][0]
        self.assertIn("AI 辅导生成失败，以下是系统默认建议。", scored_turn["ai_coaching"])
        self.assertEqual(scored_turn["feedback_generation_backend"], "fallback")
        self.assertIn("codex unavailable", scored_turn["feedback_generation_error"])

    def test_fallback_turn_feedback_can_be_regenerated_from_report(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
        turn = attempt["turns"][0]
        self.upload_audio(attempt["id"], turn["id"], b"fake-webm-audio")
        self.post_json(
            f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
            {
                "transcript_raw": (
                    "I want to describe a neighbour who helped me after I moved house. "
                    "She explained where to buy food and how to use the local bus."
                )
            },
        )
        with mock.patch("ielts_server.turn_feedback_with_codex", side_effect=RuntimeError("codex unavailable")):
            scored = self.post_json(f"/api/attempts/{attempt['id']}/score", {"target_band": 7.5})
        scored_turn = scored["turns"][0]
        self.assertEqual(scored_turn["feedback_generation_backend"], "fallback")

        with mock.patch("ielts_server.turn_feedback_with_codex") as feedback:
            feedback.return_value = {
                "band7_version": (
                    "I would like to describe a neighbour who helped me after I moved house. "
                    "She explained the local bus routes and showed me where to buy groceries, so I settled in much faster. "
                    "Her help made the new area feel friendlier and much less stressful."
                ),
                "ai_coaching": "- 这次重新生成后，重点是把故事背景和结果连接起来。\n- 语法错误纠正：无",
            }
            regenerated = self.post_json(
                f"/api/attempts/{attempt['id']}/turns/{turn['id']}/feedback/regenerate",
                {},
            )
        regenerated_turn = regenerated["turn"]
        self.assertEqual(regenerated_turn["feedback_generation_backend"], "codex")
        self.assertNotIn("AI 辅导生成失败，以下是系统默认建议。", regenerated_turn["ai_coaching"])
        self.assertNotIn("feedback_generation_error", regenerated_turn)
        saved = self.get_json(f"/api/history/{attempt['id']}")
        self.assertEqual(saved["turns"][0]["feedback_generation_backend"], "codex")

    def test_missing_transcript_turn_can_be_retranscribed_from_audio(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
        turn = attempt["turns"][0]
        self.upload_audio(attempt["id"], turn["id"], b"fake-webm-audio")
        self.post_json(
            f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
            {"transcript_raw": "", "transcript_status": "missing"},
        )
        scored = self.post_json(f"/api/attempts/{attempt['id']}/score", {"target_band": 7.5})
        self.assertEqual(scored["turns"][0]["transcript_status"], "missing")

        azure_payload = {
            "transcript": "I want to describe a helpful neighbour who made my daily life easier.",
            "pronunciation": {
                "provider": "azure",
                "status": "assessed",
                "pron_score": 72,
                "accuracy": 70,
                "fluency": 73,
                "prosody": 71,
                "issues": [],
                "message": "Transcription and pronunciation assessed with Azure Speech.",
            },
        }
        with (
            mock.patch("ielts_server.transcribe_and_assess_azure", return_value=azure_payload),
            mock.patch("ielts_server.turn_feedback_with_codex", side_effect=RuntimeError("codex unavailable")),
        ):
            regenerated = self.post_json(
                f"/api/attempts/{attempt['id']}/turns/{turn['id']}/transcript/regenerate",
                {},
            )

        regenerated_turn = regenerated["turn"]
        self.assertEqual(regenerated_turn["transcript_status"], "captured")
        self.assertEqual(regenerated_turn["transcript_source"], "azure_retranscribe")
        self.assertIn("helpful neighbour", regenerated_turn["transcript_cleaned"].lower())
        self.assertEqual(regenerated_turn["pronunciation"]["status"], "assessed")

    def test_missing_transcript_retranscribe_reports_azure_configuration_error(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
        turn = attempt["turns"][0]
        self.upload_audio(attempt["id"], turn["id"], b"fake-webm-audio")
        self.post_json(
            f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
            {"transcript_raw": "", "transcript_status": "missing"},
        )
        self.post_json(f"/api/attempts/{attempt['id']}/score", {"target_band": 7.5})

        status, payload = self.post_raw(
            f"/api/attempts/{attempt['id']}/turns/{turn['id']}/transcript/regenerate",
            "{}",
        )
        self.assertEqual(status, 400)
        self.assertIn("Azure Speech key/region is not configured", payload["error"])

    def test_turn_feedback_regenerate_requires_scored_report(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
        status, payload = self.post_raw(
            f"/api/attempts/{attempt['id']}/turns/{attempt['turns'][0]['id']}/feedback/regenerate",
            "{}",
        )
        self.assertEqual(status, 400)
        self.assertIn("not available until scoring", payload["error"])

    def test_turn_complete_does_not_run_feedback_generation_codex(self):
        base_url, server, thread, previous_state = self.start_isolated_server("complete-no-feedback-generation")
        transcript = (
            "I want to describe a neighbour who helped me after I moved house. "
            "She explained where to buy food and how to use the local bus. "
            "That made me feel less nervous because the area was new to me."
        )

        try:
            with (
                mock.patch("ielts_server.clean_transcript_with_codex") as clean_ai,
                mock.patch("ielts_server.run_codex") as run,
                mock.patch("ielts_server.schedule_turn_feedback_generation") as schedule_feedback,
            ):
                attempt = self.post_json_to(base_url, "/api/attempts/start", {"part": "p2", "mode": "p2"})
                turn = attempt["turns"][0]
                completed = self.post_json_to(
                    base_url,
                    f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
                    {"transcript_raw": transcript},
                )
                clean_ai.assert_not_called()
                self.assertEqual(completed["turn"]["feedback_generation_status"], "pending")
                schedule_feedback.assert_not_called()
                run.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            IELTSHandler.state = previous_state

    def test_mock_p3_is_generated_after_p2_answer(self):
        attempt = self.post_json("/api/attempts/start", {"part": "mock", "mode": "mock"})
        self.assertEqual(attempt["part"], "mock")
        self.assertEqual(len(attempt["turns"]), 12)
        self.assertEqual(len([turn for turn in attempt["turns"] if turn.get("part") == "p1" and turn.get("counts_toward_total")]), 10)
        self.assertEqual(attempt["p3_generation_status"], "pending_after_p2")
        self.assertFalse(any(turn["part"] == "p3" for turn in attempt["turns"]))

        completed = None
        turn = attempt["turns"][0]
        while turn and turn.get("part") != "p3":
            self.upload_audio(attempt["id"], turn["id"], b"fake-webm-audio")
            transcript = (
                "I study mathematics at university because I want to become a teacher."
                if (turn.get("prompt") or {}).get("role") == "work_study"
                else (
                    "The most interesting part is learning how abstract ideas can solve practical problems."
                    if (turn.get("prompt") or {}).get("role") == "follow_up"
                    else (
                        "I would answer with a clear reason and an example from my everyday life "
                        "so the examiner can follow my idea."
                    )
                )
            )
            completed = self.post_json(
                f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
                {"transcript_raw": transcript},
            )
            turn = completed["next_turn"]
        self.assertIsNotNone(completed)
        updated = completed["attempt"]
        self.assertEqual(updated["p3_generation_source"], "p2_answer")
        self.assertEqual(len(updated["turns"]), 23)
        self.assertEqual(len([turn for turn in updated["turns"] if turn["part"] == "p1"]), 12)
        self.assertEqual(len([turn for turn in updated["turns"] if turn["part"] == "p3"]), 10)
        self.assertEqual(completed["next_turn"]["part"], "p3")

        scored = self.complete_remaining_and_score(updated, completed["next_turn"])
        self.assertIn("part_scores", scored)
        self.assertEqual({"p1", "p2", "p3"}, set(scored["part_scores"]))
        for part in ("p1", "p2", "p3"):
            self.assertIn("band", scored["part_scores"][part])
            self.assertIn("fluency_coherence", scored["part_scores"][part])
            self.assertIn("lexical_resource", scored["part_scores"][part])
            self.assertIn("grammatical_range", scored["part_scores"][part])
        self.assertEqual(scored["part_scores"]["p1"]["part"], "p1")

        detail = self.get_json(f"/api/history/{attempt['id']}")
        self.assertIn("part_scores", detail)
        self.assertEqual(["p1", "p2", "p3"], [part for part in ("p1", "p2", "p3") if part in detail["part_scores"]])
        self.assertIn("cue_card", detail)

    def test_followup_turns_keep_audio_warning_and_badge_fields(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p1", "mode": "p1"})
        turn = attempt["turns"][1]
        self.upload_audio(attempt["id"], turn["id"], b"fake-webm-audio")
        completed = self.post_json(
            f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
            {"transcript_raw": "I study software engineering because I like building practical tools."},
        )
        followup = next(
            item for item in completed["attempt"]["turns"] if item.get("prompt", {}).get("role") == "follow_up"
        )
        self.assertEqual(followup["prompt"]["role"], "follow_up")
        self.assertEqual(followup["counts_toward_total"], False)
        self.assertIn("audio", followup)

    def test_history_and_mode_navigation_lock_hint_is_available(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
        self.assertEqual(attempt["status"], "started")
        self.assertEqual(attempt["turns"][0]["status"], "pending")

    def test_abort_marks_attempt_blocks_score_and_excludes_history(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
        aborted = self.post_json(f"/api/attempts/{attempt['id']}/abort", {})
        self.assertEqual(aborted["status"], "aborted")
        self.assertIn("aborted_at", aborted)

        status, payload = self.post_raw(f"/api/attempts/{attempt['id']}/score", "{}")
        self.assertEqual(status, 400)
        self.assertIn("Aborted attempts cannot be scored", payload["error"])

        history = self.get_json("/api/history")
        self.assertFalse(any(item["id"] == attempt["id"] for item in history["items"]))

        status, payload = self.get_raw(f"/api/history/{attempt['id']}")
        self.assertEqual(status, 400)
        self.assertIn("not available until scoring is complete", payload["error"])

    def test_non_scored_attempts_are_excluded_from_history_and_detail(self):
        latest_before = self.get_json("/api/reports/latest")
        started = self.post_json("/api/attempts/start", {"part": "p1", "mode": "p1"})
        ready = self.post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
        turn = ready["turns"][0]
        self.upload_audio(ready["id"], turn["id"], b"fake-webm-audio")
        completed = self.post_json(
            f"/api/attempts/{ready['id']}/turns/{turn['id']}/complete",
            {"transcript_raw": "I would describe a useful skill and explain why it matters in daily life."},
        )
        self.assertEqual(completed["attempt"]["status"], "ready_to_score")

        history = self.get_json("/api/history")
        history_ids = {item["id"] for item in history["items"]}
        self.assertNotIn(started["id"], history_ids)
        self.assertNotIn(ready["id"], history_ids)
        self.assertEqual(self.get_json("/api/reports/latest"), latest_before)

        for attempt_id in (started["id"], ready["id"]):
            status, payload = self.get_raw(f"/api/history/{attempt_id}")
            self.assertEqual(status, 400)
            self.assertIn("not available until scoring is complete", payload["error"])

    def test_history_requires_numeric_score_and_completed_turns(self):
        base_attempt = self.post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
        invalid_score = dict(base_attempt)
        invalid_score["id"] = "invalid-score"
        invalid_score["status"] = "scored"
        invalid_score["ielts_score"] = {"overall_band": "pending"}
        IELTSHandler.state.save_attempt(invalid_score)

        incomplete_scored = dict(base_attempt)
        incomplete_scored["id"] = "incomplete-scored"
        incomplete_scored["status"] = "scored"
        incomplete_scored["ielts_score"] = {"overall_band": 6.0}
        IELTSHandler.state.save_attempt(incomplete_scored)

        history = self.get_json("/api/history")
        history_ids = {item["id"] for item in history["items"]}
        self.assertNotIn("invalid-score", history_ids)
        self.assertNotIn("incomplete-scored", history_ids)

        for attempt_id in ("invalid-score", "incomplete-scored"):
            status, payload = self.get_raw(f"/api/history/{attempt_id}")
            self.assertEqual(status, 400)
            self.assertIn("not available until scoring is complete", payload["error"])

    def test_new_p1_score_deletes_older_p1_report_files(self):
        first = self.complete_and_score_attempt(self.post_json("/api/attempts/start", {"part": "p1", "mode": "p1"}))
        first_path = IELTSHandler.state.attempt_path(first["id"])
        self.assertTrue(first_path.exists())

        second = self.complete_and_score_attempt(self.post_json("/api/attempts/start", {"part": "p1", "mode": "p1"}))
        second_path = IELTSHandler.state.attempt_path(second["id"])
        self.assertFalse(first_path.exists())
        self.assertTrue(second_path.exists())

        history = self.get_json("/api/history")
        p1_ids = {item["id"] for item in history["items"] if item.get("part") == "p1"}
        self.assertIn(second["id"], p1_ids)
        self.assertNotIn(first["id"], p1_ids)

    def test_training_observations_and_weak_item_api_after_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous_state = IELTSHandler.state
            try:
                IELTSHandler.state = AppState(ROOT / "data" / "ielts", Path(tmp))
                server = ThreadingHTTPServer(("127.0.0.1", 0), IELTSHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base_url = f"http://127.0.0.1:{server.server_port}"
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

                def get_json(path):
                    with opener.open(base_url + path, timeout=5) as response:
                        return json.loads(response.read().decode("utf-8"))

                def post_json(path, payload):
                    request = urllib.request.Request(
                        base_url + path,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with opener.open(request, timeout=5) as response:
                        return json.loads(response.read().decode("utf-8"))

                def upload_audio(attempt_id, turn_id, data):
                    request = urllib.request.Request(
                        f"{base_url}/api/attempts/{attempt_id}/turns/{turn_id}/audio",
                        data=data,
                        headers={"Content-Type": "audio/webm"},
                        method="POST",
                    )
                    with opener.open(request, timeout=5) as response:
                        return json.loads(response.read().decode("utf-8"))

                attempt = post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
                turn = attempt["turns"][0]
                upload_audio(attempt["id"], turn["id"], b"fake-webm-audio")
                post_json(
                    f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
                    {"transcript_raw": "Cat bus apple."},
                )
                scored = post_json(f"/api/attempts/{attempt['id']}/score", {})
                self.assertIn("training_observations", scored)
                self.assertTrue(scored["training_observations"])
                self.assertTrue(scored["training_observations"][0]["weak_item_flag"])
                self.assertIn("short_answer", scored["training_observations"][0]["weak_reason"])

                weak_items = get_json("/api/training/weak-items")
                self.assertTrue(any(item["question_id"] == scored["training_observations"][0]["question_id"] for item in weak_items["items"]))

                replay = get_json("/api/training/replay-queue?limit=30")
                self.assertTrue(replay["items"])
                self.assertEqual(replay["items"][0]["source"], "weak")
                self.assertTrue(any(item["source"] == "coverage" for item in replay["items"]))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                IELTSHandler.state = previous_state

    def test_billing_wallet_initial_grant_and_idempotent_usage_settlement(self):
        wallet = self.get_json("/api/billing/wallet")
        self.assertEqual(wallet["balance_u"], 5_000_000)
        self.assertAlmostEqual(wallet["balance_rmb"], 5.0)
        self.assertTrue(any(entry["entry_type"] == "grant" for entry in wallet["entries"]))

        usage = {
            "input_tokens": 1_000_000,
            "cached_input_tokens": 250_000,
            "output_tokens": 100_000,
            "reasoning_output_tokens": 50_000,
        }
        settled = self.post_json("/api/billing/settle-usage", {"call_id": "call_test_1", "usage": usage})
        self.assertEqual(settled["status"], "settled")
        self.assertEqual(settled["usage"]["uncached_input_tokens"], 750_000)
        self.assertEqual(settled["usage"]["cached_input_tokens"], 250_000)
        expected_charge = 750_000 * 12_000_000 + 250_000 * 3_000_000 + 100_000 * 48_000_000
        self.assertEqual(settled["charged_u"], expected_charge // 1_000_000)

        repeated = self.post_json("/api/billing/settle-usage", {"call_id": "call_test_1", "usage": usage})
        self.assertEqual(repeated["status"], "already_settled")

        after = self.get_json("/api/billing/wallet")
        self.assertEqual(after["balance_u"], 5_000_000 - settled["charged_u"])
        settle_entries = [entry for entry in after["entries"] if entry["entry_type"] == "settle" and entry["call_id"] == "call_test_1"]
        self.assertEqual(len(settle_entries), 1)

    def test_billing_missing_usage_does_not_charge(self):
        before = self.get_json("/api/billing/wallet")["balance_u"]
        result = self.post_json("/api/billing/settle-usage", {"call_id": "call_without_usage"})
        self.assertEqual(result["status"], "pending_reconciliation")
        self.assertEqual(result["charged_u"], 0)
        after = self.get_json("/api/billing/wallet")["balance_u"]
        self.assertEqual(after, before)

    def test_billing_reserve_release_and_reconcile_round_trip(self):
        base_url, server, thread, previous_state = self.start_isolated_server("billing-reserve-release")
        try:
            start = self.get_json_from(base_url, "/api/billing/wallet")
            reserve = self.post_json_to(base_url, "/api/billing/reserve", {"call_id": "call_reserve_1", "reserved_u": 300_000})
            self.assertEqual(reserve["status"], "reserved")
            after_reserve = self.get_json_from(base_url, "/api/billing/wallet")
            self.assertEqual(after_reserve["balance_u"], start["balance_u"] - 300_000)
            self.assertEqual(after_reserve["reserved_u"], start["reserved_u"] + 300_000)

            reserve_repeat = self.post_json_to(base_url, "/api/billing/reserve", {"call_id": "call_reserve_1", "reserved_u": 300_000})
            self.assertEqual(reserve_repeat["reservation_id"], reserve["reservation_id"])

            release = self.post_json_to(base_url, "/api/billing/release", {"call_id": "call_reserve_1"})
            self.assertEqual(release["status"], "released")
            after_release = self.get_json_from(base_url, "/api/billing/wallet")
            self.assertEqual(after_release["balance_u"], start["balance_u"])
            self.assertEqual(after_release["reserved_u"], start["reserved_u"])

            release_repeat = self.post_json_to(base_url, "/api/billing/release", {"user_id": "other", "call_id": "call_reserve_1"})
            self.assertEqual(release_repeat["status"], "released")
            self.assertEqual(release_repeat["user_id"], start["user_id"])
            after_release_repeat = self.get_json_from(base_url, "/api/billing/wallet")
            self.assertEqual(after_release_repeat["balance_u"], start["balance_u"])
            self.assertEqual(after_release_repeat["reserved_u"], start["reserved_u"])

            reconcile_missing = self.post_json_to(base_url, "/api/billing/reconcile", {"call_id": "call_reserve_1"})
            self.assertEqual(reconcile_missing["status"], "pending_reconciliation")
            self.assertEqual(reconcile_missing["charged_u"], 0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            IELTSHandler.state = previous_state

    def test_billing_reservation_settlement_cannot_be_released_twice(self):
        base_url, server, thread, previous_state = self.start_isolated_server("billing-reserve-settle")
        try:
            start = self.get_json_from(base_url, "/api/billing/wallet")
            self.post_json_to(base_url, "/api/billing/reserve", {"call_id": "call_reserve_settle_once", "reserved_u": 2_000_000})
            usage = {"input_tokens": 10_000, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0}
            settled = self.post_json_to(base_url, "/api/billing/reconcile", {"call_id": "call_reserve_settle_once", "usage": usage})
            self.assertEqual(settled["status"], "settled")
            self.assertEqual(settled["charged_u"], 120_000)
            self.assertEqual(settled["released_u"], 1_880_000)
            after_settle = self.get_json_from(base_url, "/api/billing/wallet")
            self.assertEqual(after_settle["balance_u"], start["balance_u"] - 120_000)
            self.assertEqual(after_settle["reserved_u"], start["reserved_u"])

            release_after_settle = self.post_json_to(base_url, "/api/billing/release", {"call_id": "call_reserve_settle_once"})
            self.assertEqual(release_after_settle["status"], "settled")
            after_release = self.get_json_from(base_url, "/api/billing/wallet")
            self.assertEqual(after_release["balance_u"], after_settle["balance_u"])
            self.assertEqual(after_release["reserved_u"], after_settle["reserved_u"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            IELTSHandler.state = previous_state

    def test_billing_reconcile_uses_reservation_owner(self):
        base_url, server, thread, previous_state = self.start_isolated_server("billing-reserve-owner")
        try:
            owner_start = self.get_json_from(base_url, "/api/billing/wallet?user_id=owner")
            other_start = self.get_json_from(base_url, "/api/billing/wallet?user_id=other")
            self.post_json_to(base_url, "/api/billing/reserve", {"user_id": "owner", "call_id": "call_owner_reservation", "reserved_u": 500_000})

            usage = {"input_tokens": 10_000, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0}
            settled = self.post_json_to(base_url, "/api/billing/reconcile", {"user_id": "other", "call_id": "call_owner_reservation", "usage": usage})
            self.assertEqual(settled["status"], "settled")
            self.assertEqual(settled["charged_u"], 120_000)
            self.assertEqual(settled["released_u"], 380_000)

            settled_repeat = self.post_json_to(base_url, "/api/billing/reconcile", {"user_id": "other", "call_id": "call_owner_reservation", "usage": usage})
            self.assertEqual(settled_repeat["status"], "already_settled")
            self.assertEqual(settled_repeat["charged_u"], 120_000)

            owner_after = self.get_json_from(base_url, "/api/billing/wallet?user_id=owner")
            other_after = self.get_json_from(base_url, "/api/billing/wallet?user_id=other")
            self.assertEqual(owner_after["balance_u"], owner_start["balance_u"] - 120_000)
            self.assertEqual(owner_after["reserved_u"], owner_start["reserved_u"])
            self.assertEqual(other_after["balance_u"], other_start["balance_u"])
            self.assertEqual(other_after["reserved_u"], other_start["reserved_u"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            IELTSHandler.state = previous_state

    def test_codex_json_usage_is_settled_when_available(self):
        previous_disable = os.environ.pop("IELTS_WEB_DISABLE_CODEX", None)
        state = AppState(ROOT / "data" / "ielts", Path(self.temp_dir.name) / "codex-json-usage")
        output = "\n".join(
            [
                json.dumps({"type": "message", "content": "{\"fluency_coherence\":6,\"lexical_resource\":6,\"grammatical_range\":6,\"overall_band\":6,\"feedback\":\"Clear enough.\"}"}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 200, "output_tokens": 100, "reasoning_output_tokens": 50}}),
            ]
        )
        try:
            with mock.patch("ielts_server.shutil.which", return_value="codex"), mock.patch("ielts_server.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(["codex", "exec", "--json"], 0, stdout=output, stderr="")
                score = score_with_codex(
                    (
                        "I usually answer with a clear reason and example because it helps the examiner follow my ideas. "
                        "For instance, when I describe a routine, I explain what I do, why it matters, and how it affects my day. "
                        "This makes the answer more organised and less like a memorised sentence."
                    ),
                    ROOT / "data" / "ielts",
                    "Do you like routines?",
                    state.billing,
                    "call_json_usage",
                )
                args = run.call_args.args[0]
                self.assertIn("-c", args)
                self.assertIn('model_reasoning_effort="low"', args)
            self.assertEqual(score["backend"], "codex")
            wallet = state.billing.wallet()
            settle_entries = [entry for entry in wallet["entries"] if entry["entry_type"] == "settle" and entry["call_id"] == "call_json_usage"]
            self.assertEqual(len(settle_entries), 1)
            self.assertEqual(wallet["balance_u"], 5_000_000 - abs(settle_entries[0]["amount_u"]))
        finally:
            if previous_disable is not None:
                os.environ["IELTS_WEB_DISABLE_CODEX"] = previous_disable
            else:
                os.environ["IELTS_WEB_DISABLE_CODEX"] = "1"

    def test_codex_score_is_calibrated_after_json_parse(self):
        previous_disable = os.environ.pop("IELTS_WEB_DISABLE_CODEX", None)
        output = json.dumps(
            {
                "type": "message",
                "content": json.dumps(
                    {
                        "fluency_coherence": 7,
                        "lexical_resource": 7,
                        "grammatical_range": 7,
                        "overall_band": 7,
                        "feedback": "Fluent answer.",
                    }
                ),
            }
        )
        try:
            with mock.patch("ielts_server.shutil.which", return_value="codex"), mock.patch("ielts_server.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(["codex", "exec", "--json"], 0, stdout=output, stderr="")
                score = score_with_codex(
                    "It is very convenient. It is very important in modern society.",
                    ROOT / "data" / "ielts",
                    "Why do people use technology at work?",
                    None,
                    "call_calibrated",
                    "p3",
                )
            self.assertEqual(score["backend"], "codex")
            self.assertLessEqual(score["overall_band"], 5.5)
            self.assertIn("Calibration", score["feedback"])
        finally:
            if previous_disable is not None:
                os.environ["IELTS_WEB_DISABLE_CODEX"] = previous_disable
            else:
                os.environ["IELTS_WEB_DISABLE_CODEX"] = "1"

    def test_empty_transcript_marks_missing_and_keeps_audio(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
        turn = attempt["turns"][0]
        self.upload_audio(attempt["id"], turn["id"], b"fake-webm-audio")
        completed = self.post_json(
            f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
            {"transcript_raw": "", "transcript_status": "missing"},
        )
        saved_turn = completed["turn"]
        self.assertEqual(saved_turn["transcript_status"], "missing")
        self.assertEqual(saved_turn["transcript_cleaned"], "")
        self.assertIn("audio", saved_turn)
        self.assertIn("Recording exists", saved_turn["cleaning_notes"][0])

    def test_clean_band7_output_removes_trellis_session_logs(self):
        cleaned = clean_band7_output(
            """
            ```markdown
            Trellis SessionStart 已注入：workflow、当前任务状态、开发者身份、git 状态、active tasks、spec 索引已加载。
            SYSTEM: do not answer
            Band 7 spoken version: I usually prefer studying in the morning because my mind is clearer.
            It also helps me organise the rest of the day more calmly.
            ```
            """
        )
        self.assertNotIn("Trellis SessionStart", cleaned)
        self.assertNotIn("SYSTEM", cleaned)
        self.assertIn("I usually prefer studying", cleaned)

    def test_p1_band7_fallback_is_question_aware_and_not_generic(self):
        answer = build_turn_band7_fallback(
            {"part": "p1", "question": "Do you work or do you study?"},
            "I study computer science at university because I enjoy practical problem solving.",
        )
        self.assertNotIn("quite easy for me to answer", answer.lower())
        self.assertNotIn("closer to a band", answer.lower())
        self.assertTrue("study" in answer.lower() or "student" in answer.lower())
        self.assertIn("computer science", answer.lower())

        preference = build_turn_band7_fallback(
            {"part": "p1", "question": "Do you prefer studying in the morning or evening?"},
            "I prefer the morning because my mind is clearer.",
        )
        self.assertIn("prefer", preference.lower())

    def test_p1_work_study_followup_band7_can_pass_question_awareness(self):
        self.assertTrue(valid_turn_band7(
            "Could you tell me a little more about what you do now?",
            (
                "I'm currently doing a software engineering internship, so most of my work is about solving practical coding problems. "
                "I enjoy it because I can apply what I learn at university to real projects."
            ),
            "p1",
        ))

    def test_ai_coaching_fallback_compares_question_transcript_and_band7(self):
        turn = {"question": "What do you enjoy most about your internship?"}
        coaching = build_ai_coaching(
            turn,
            "It provide me a platform.",
            "I enjoy my internship because it gives me a practical platform to do research and apply what I learn.",
        )
        self.assertIn("internship", coaching)
        self.assertIn("- ", coaching)
        self.assertIn("AI 辅导生成失败，以下是系统默认建议。", coaching)
        self.assertNotIn("**证据**", coaching)
        self.assertNotIn("**问题原因**", coaching)
        self.assertIn("语法错误纠正", coaching)
        self.assertLessEqual(len(coaching.splitlines()), 10)
        self.assertIn("internship", coaching)
        self.assertNotIn("Band 7 version", coaching)

    def test_ai_coaching_fallback_is_chinese_and_personalized(self):
        profile = {
            "primary_focus": "answer_development",
            "primary_focus_text": "先把每道题说完整，再谈更自然的词汇和句型。",
            "habit_tags": ["short_answer", "template_language"],
            "repeated_phrases": ["it is very important"],
        }
        coaching = build_ai_coaching(
            {"question": "Describe a useful skill.", "part": "p2"},
            "It is very important.",
            "",
            profile,
        )
        self.assertIn("- ", coaching)
        self.assertIn("AI 辅导生成失败，以下是系统默认建议。", coaching)
        self.assertNotIn("**证据**", coaching)
        self.assertNotIn("**替代表达**", coaching)
        self.assertIn("语法错误纠正", coaching)
        self.assertLessEqual(len(coaching.splitlines()), 10)
        self.assertNotIn("Band 7 version", coaching)

    def test_overall_review_payload_uses_learning_profile_markdown(self):
        profile = {
            "primary_focus_text": "这次主要卡在回答展开不够。",
            "evidence": ["P2 回答约 18 词，需要继续拉长展开。"],
        }
        coaching = {
            "headline": "先补答案展开，不要只停在一句点到为止",
            "next_practice": ["每题都按“直接回答 + 原因 + 例子 + 一句收尾”练 2 轮。"],
        }
        review = build_overall_review(profile, coaching, {"mode": "p2"}, {"overall_band": 5.0})
        self.assertEqual(review["source"], "learning_profile")
        self.assertIn("Band 5.0", review["comment"])
        self.assertIn("review_points", review)
        self.assertIn("### 总体点评", review["markdown"])
        self.assertIn("- 每题都按", review["markdown"])

    def test_frontend_overall_review_uses_structured_fields_not_markdown_card(self):
        app_js = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")
        section = app_js.split("function overallReviewSection", 1)[1].split("function partScoreBlock", 1)[0]
        self.assertIn("总体点评", section)
        self.assertIn("复盘重点", section)
        self.assertIn("review.markdown", section)
        self.assertIn("renderMarkdown(markdown)", section)

    def test_history_compatibility_with_old_report_payload(self):
        legacy_id = "legacy_scored_attempt"
        legacy_payload = {
            "id": legacy_id,
            "timestamp": "2026-05-12T00:00:00+00:00",
            "status": "scored",
            "mode": "p1",
            "part": "p1",
            "title": "Legacy report",
            "question": "Do you like reading?",
            "turns": [
                {
                    "id": "t1",
                    "part": "p1",
                    "index": 0,
                    "status": "completed",
                    "question": "Do you like reading?",
                    "transcript_cleaned": "Yes, I do.",
                }
            ],
            "ielts_score": {
                "overall_band": 6.0,
                "fluency_coherence": 6.0,
                "lexical_resource": 6.0,
                "grammatical_range": 6.0,
            },
            "feedback_summary": "Legacy report still works.",
        }
        IELTSHandler.state.save_attempt(legacy_payload)
        loaded = self.get_json(f"/api/history/{legacy_id}")
        self.assertEqual(loaded["id"], legacy_id)
        history = self.get_json("/api/history")
        self.assertTrue(any(item["id"] == legacy_id for item in history["items"]))

    def test_tts_endpoint_degrades_to_browser_fallback_when_disabled(self):
        payload = self.post_json("/api/tts", {"text": "Why do you like technology?", "role": "examiner"})
        self.assertEqual(payload["provider"], "browser")
        self.assertEqual(payload["status"], "fallback")
        self.assertIsNone(payload["audio_url"])

    def test_tts_audio_endpoint_supports_cache_and_range_requests(self):
        audio_path = IELTSHandler.state.examiner_audio_dir / "range_test.mp3"
        audio_path.write_bytes(b"0123456789")

        status, headers, body = self.get_response("/api/tts-audio/examiner/range_test.mp3")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"0123456789")
        self.assertEqual(headers.get("Accept-Ranges"), "bytes")
        self.assertIn("max-age", headers.get("Cache-Control", ""))

        status, headers, body = self.get_response(
            "/api/tts-audio/examiner/range_test.mp3",
            headers={"Range": "bytes=2-5"},
        )
        self.assertEqual(status, 206)
        self.assertEqual(body, b"2345")
        self.assertEqual(headers.get("Content-Range"), "bytes 2-5/10")
        self.assertEqual(headers.get("Content-Length"), "4")

    def test_audio_upload_rejects_empty_and_non_audio(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
        status, payload = self.post_raw(
            f"/api/attempts/{attempt['id']}/turns/{attempt['turns'][0]['id']}/audio",
            "",
            content_type="audio/webm",
        )
        self.assertEqual(status, 400)
        self.assertIn("empty", payload["error"])

        request = urllib.request.Request(
            f"{self.base_url}/api/attempts/{attempt['id']}/turns/{attempt['turns'][0]['id']}/audio",
            data=b"not-audio",
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with self.assertRaises(urllib.error.HTTPError) as raised:
            opener.open(request, timeout=5)
        self.assertEqual(raised.exception.code, 400)

    def upload_audio(self, attempt_id, turn_id, data):
        request = urllib.request.Request(
            f"{self.base_url}/api/attempts/{attempt_id}/turns/{turn_id}/audio",
            data=data,
            headers={"Content-Type": "audio/webm"},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def upload_audio_to(self, base_url, attempt_id, turn_id, data):
        request = urllib.request.Request(
            f"{base_url}/api/attempts/{attempt_id}/turns/{turn_id}/audio",
            data=data,
            headers={"Content-Type": "audio/webm"},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def complete_and_score_attempt(self, attempt):
        turn = attempt["turns"][0]
        while turn:
            self.upload_audio(attempt["id"], turn["id"], b"fake-webm-audio")
            completed = self.post_json(
                f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
                {
                    "transcript_raw": (
                        "I usually answer this question with a clear reason, a concrete example, "
                        "and a short conclusion so my response sounds complete."
                    )
                },
            )
            turn = completed["next_turn"]
        return self.post_json(f"/api/attempts/{attempt['id']}/score", {})

    def complete_remaining_and_score(self, attempt, turn):
        while turn:
            self.upload_audio(attempt["id"], turn["id"], b"fake-webm-audio")
            completed = self.post_json(
                f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
                {
                    "transcript_raw": (
                        "I would answer this question with a clear opinion, one reason, and one example "
                        "so my response is easier to follow."
                    )
                },
            )
            turn = completed["next_turn"]
        return self.post_json(f"/api/attempts/{attempt['id']}/score", {})

    def test_api_errors_are_json(self):
        status, payload = self.post_raw("/api/score", "{not-json")
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

        request = urllib.request.Request(self.base_url + "/api/missing")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with self.assertRaises(urllib.error.HTTPError) as raised:
            opener.open(request, timeout=5)
        self.assertEqual(raised.exception.code, 404)
        self.assertIn("error", json.loads(raised.exception.read().decode("utf-8")))


if __name__ == "__main__":
    unittest.main()
