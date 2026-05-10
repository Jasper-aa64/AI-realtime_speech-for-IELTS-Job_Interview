import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from ielts_server import AppState, IELTSHandler, build_ai_coaching, clean_band7_output  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


class IELTSWebServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["IELTS_WEB_DISABLE_CODEX"] = "1"
        os.environ["IELTS_WEB_DISABLE_CLAUDE"] = "1"
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
        os.environ.pop("IELTS_WEB_DISABLE_CLAUDE", None)
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

    def test_question_bank_summary_and_sample(self):
        summary = self.get_json("/api/question-bank/summary?cache_bust=1")
        self.assertGreaterEqual(summary["part1_count"], 15)
        self.assertGreaterEqual(summary["part2_count"], 3)

        sample = self.post_json("/api/session/start?mode=full", {"p1_count": 3, "mode": "full"})
        self.assertIn("session_id", sample)
        self.assertEqual(len(sample["part1"]), 3)
        self.assertIn("question", sample["part1"][0])
        self.assertIn("title", sample["part2"])

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

    def test_p3_generation_falls_back_without_server_cli_env(self):
        payload = self.post_json("/api/p3/questions", {"theme": "technology_and_society"})
        self.assertEqual(payload["backend"], "fallback")
        self.assertEqual(len(payload["questions"]), 5)
        self.assertIn("follow_up", payload)

    def test_p1_attempt_uses_ten_turns_and_scores_after_completion(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p1", "mode": "p1"})
        self.assertEqual(attempt["part"], "p1")
        self.assertEqual(attempt["candidate"], "jasper")
        self.assertEqual(len(attempt["turns"]), 10)
        self.assertEqual(attempt["turns"][0]["question"], "What is your full name?")
        self.assertEqual(attempt["turns"][0]["prompt"]["flow"], "intro")
        self.assertEqual(attempt["turns"][0]["prompt"]["role"], "name")
        self.assertEqual(attempt["turns"][1]["question"], "Do you work, study at university, or go to school?")
        self.assertEqual(attempt["turns"][1]["prompt"]["flow"], "intro")
        self.assertEqual(attempt["turns"][1]["prompt"]["role"], "work_study")
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
                self.assertEqual(len(completed["attempt"]["turns"]), 11)
            turn = completed["next_turn"]
        self.assertIsNone(completed["next_turn"])
        self.assertEqual(len(completed_ids), 11)

        scored = self.post_json(f"/api/attempts/{attempt['id']}/score", {})
        self.assertEqual(scored["status"], "scored")
        self.assertEqual(scored["pronunciation"]["provider"], "azure")
        self.assertEqual(scored["pronunciation"]["status"], "not_configured")
        self.assertIsNone(scored["ielts_score"]["pronunciation_estimate"])
        self.assertIn("criteria_feedback", scored)
        self.assertIn("band7_version", scored)
        self.assertIn("part_scores", scored)
        self.assertIn("p1", scored["part_scores"])
        self.assertEqual(scored["part_scores"]["p1"]["part"], "p1")
        self.assertIn("model_audio", scored)
        self.assertTrue(scored["turns"][0]["band7_version"])
        self.assertTrue(scored["turns"][0]["ai_coaching"])
        self.assertTrue(scored["turns"][0]["upgrade_notes"])
        self.assertIn("model_audio", scored["turns"][0])

        history = self.get_json("/api/history")
        self.assertTrue(any(item["id"] == attempt["id"] for item in history["items"]))

        detail = self.get_json(f"/api/history/{attempt['id']}")
        self.assertEqual(detail["id"], attempt["id"])

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

        scored = self.post_json(f"/api/attempts/{attempt['id']}/score", {})
        scored_turn = scored["turns"][0]
        self.assertTrue(scored_turn["transcript_cleaned"])
        self.assertTrue(scored_turn["band7_version"])
        self.assertIn("\n\n", scored_turn["transcript_markdown"])
        self.assertIn("\n\n", scored_turn["band7_markdown"])
        self.assertIn("neighbour who helped me", scored_turn["transcript_markdown"])
        self.assertIn("Band 7 version", scored_turn["ai_coaching"])
        self.assertIn("Describe", scored_turn["ai_coaching"])

    def test_mock_p3_is_generated_after_p2_answer(self):
        attempt = self.post_json("/api/attempts/start", {"part": "mock", "mode": "mock"})
        self.assertEqual(attempt["part"], "mock")
        self.assertEqual(len(attempt["turns"]), 11)
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
        self.assertEqual(len(updated["turns"]), 22)
        self.assertEqual(len([turn for turn in updated["turns"] if turn["part"] == "p1"]), 11)
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
            self.assertIn("pronunciation_estimate", scored["part_scores"][part])
        self.assertEqual(scored["part_scores"]["p1"]["part"], "p1")

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

    def test_ai_coaching_fallback_compares_question_transcript_and_band7(self):
        turn = {"question": "What do you enjoy most about your internship?"}
        coaching = build_ai_coaching(
            turn,
            "It provide me a platform.",
            "I enjoy my internship because it gives me a practical platform to do research and apply what I learn.",
        )
        self.assertIn("internship", coaching)
        self.assertIn("short", coaching)
        self.assertIn("Band 7 version", coaching)
        self.assertNotIn("For this question, focus first on building a fuller answer", coaching)

    def test_tts_endpoint_degrades_to_browser_fallback_when_disabled(self):
        payload = self.post_json("/api/tts", {"text": "Why do you like technology?", "role": "examiner"})
        self.assertEqual(payload["provider"], "browser")
        self.assertEqual(payload["status"], "fallback")
        self.assertIsNone(payload["audio_url"])

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
