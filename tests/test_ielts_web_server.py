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
from ielts_server import AppState, IELTSHandler, clean_band7_output  # noqa: E402


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

    def test_p3_generation_falls_back_without_server_cli_env(self):
        payload = self.post_json("/api/p3/questions", {"theme": "technology_and_society"})
        self.assertEqual(payload["backend"], "fallback")
        self.assertEqual(len(payload["questions"]), 5)
        self.assertIn("follow_up", payload)

    def test_p1_attempt_uses_ten_turns_and_scores_after_completion(self):
        attempt = self.post_json("/api/attempts/start", {"part": "p1", "mode": "p1"})
        self.assertEqual(attempt["part"], "p1")
        self.assertEqual(len(attempt["turns"]), 10)
        self.assertEqual(attempt["turns"][0]["timers"]["prep_seconds"], 3)
        self.assertEqual(attempt["turns"][0]["examiner_behavior"], "auto_play_question")
        self.assertEqual(attempt["turns"][0]["examiner_tts"]["status"], "fallback")

        status, payload = self.post_raw(f"/api/attempts/{attempt['id']}/score", "{}")
        self.assertEqual(status, 400)
        self.assertIn("Complete all speaking turns", payload["error"])

        for turn in attempt["turns"]:
            self.upload_audio(attempt["id"], turn["id"], b"fake-webm-audio")
            completed = self.post_json(
                f"/api/attempts/{attempt['id']}/turns/{turn['id']}/complete",
                {
                    "transcript_raw": (
                        "I usually answer this question with one reason and one example "
                        "because that makes my speaking clearer."
                    )
                },
            )
        self.assertIsNone(completed["next_turn"])

        scored = self.post_json(f"/api/attempts/{attempt['id']}/score", {})
        self.assertEqual(scored["status"], "scored")
        self.assertEqual(scored["pronunciation"]["provider"], "azure")
        self.assertEqual(scored["pronunciation"]["status"], "not_configured")
        self.assertIsNone(scored["ielts_score"]["pronunciation_estimate"])
        self.assertIn("criteria_feedback", scored)
        self.assertIn("band7_version", scored)
        self.assertIn("model_audio", scored)
        self.assertTrue(scored["turns"][0]["band7_version"])
        self.assertTrue(scored["turns"][0]["upgrade_notes"])
        self.assertIn("model_audio", scored["turns"][0])

        history = self.get_json("/api/history")
        self.assertTrue(any(item["id"] == attempt["id"] for item in history["items"]))

        detail = self.get_json(f"/api/history/{attempt['id']}")
        self.assertEqual(detail["id"], attempt["id"])

    def test_p2_start_preserves_cue_card_and_p3_has_five_turns(self):
        p2 = self.post_json("/api/attempts/start", {"part": "p2", "mode": "p2"})
        self.assertEqual(p2["part"], "p2")
        self.assertEqual(len(p2["turns"]), 1)
        self.assertIn("cue_card", p2)
        self.assertEqual(p2["turns"][0]["timers"]["prep_seconds"], 60)
        self.assertEqual(p2["turns"][0]["examiner_behavior"], "auto_play_instruction_only")
        self.assertNotIn("You should say", p2["turns"][0]["examiner_text"])
        self.assertNotIn(p2["cue_card"]["title"], p2["turns"][0]["examiner_text"])
        self.assertIn("one minute to think", p2["turns"][0]["examiner_text"])
        self.assertIn("You should say", p2["turns"][0]["question"])

        p3 = self.post_json("/api/attempts/start", {"part": "p3", "mode": "p3"})
        self.assertEqual(p3["part"], "p3")
        self.assertEqual(len(p3["turns"]), 5)
        self.assertEqual(p3["turns"][0]["timers"]["prep_seconds"], 7)
        self.assertEqual(p3["turns"][0]["examiner_behavior"], "auto_play_question")

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
