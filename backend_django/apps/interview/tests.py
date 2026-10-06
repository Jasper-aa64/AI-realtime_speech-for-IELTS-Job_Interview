import io
import json
import subprocess
import shutil
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone

from apps.ai.http_provider import HttpApiProviderConfig, HttpApiProviderResult
from apps.ai.models import AITask
from apps.billing.models import CodexUsageEvent

from . import services
from .bank import QUESTIONS
from .models import InterviewSession
from .validation import InterviewError, extract_pdf


class InterviewApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="interview-owner", password="test-password")
        self.other = get_user_model().objects.create_user(username="interview-other", password="test-password")
        self.client.force_login(self.user)

    def post(self, path, data=None, client=None):
        return (client or self.client).post(path, json.dumps(data or {}), content_type="application/json")

    def create(self, count=2):
        response = self.post("/api/interview/sessions/", {"mode": "general", "count": count})
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        return payload["session"]["id"], payload["turns"]

    def answer(self, session_id, turn, value="I used a bounded queue and measured tail latency."):
        return self.post(f"/api/interview/sessions/{session_id}/turns/{turn['id']}/answer/", {"answer": value})

    def fake_generation(self, **values):
        return {"provider": "http_api", "model": "fixture-model", "task_id": "fixture-task", "ai_source": "gpt", **values}

    def test_authentication_all_routes_and_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get("/api/interview/questions/").status_code, 401)
        self.assertEqual(self.post("/api/interview/sessions/", client=client).status_code, 401)
        client.force_login(self.user)
        denied = self.post("/api/interview/sessions/", client=client)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["code"], "csrf_failed")
        client.get("/api/interview/questions/")
        csrf = client.cookies["csrftoken"].value
        accepted = client.post("/api/interview/sessions/", json.dumps({"mode": "general", "count": 1}),
                               content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(accepted.status_code, 200)

    def test_bank_and_category_validation(self):
        payload = self.client.get("/api/interview/questions/?category=low_latency").json()
        self.assertEqual(len(payload["questions"]), 19)
        self.assertTrue(all(q["category"] == "low_latency" and q["source"] == "curated" for q in payload["questions"]))
        self.assertEqual(len(payload["categories"]), 5)
        self.assertEqual(self.client.get("/api/interview/questions/?category=invalid").status_code, 400)

    def test_full_answer_skip_finish_reload_history(self):
        sid, turns = self.create(count=3)
        first = self.answer(sid, turns[0])
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["current_turn"]["id"], turns[1]["id"])
        skipped = self.post(f"/api/interview/sessions/{sid}/turns/{turns[1]['id']}/skip/")
        self.assertEqual(skipped.json()["current_turn"]["id"], turns[2]["id"])
        self.answer(sid, turns[2])
        finished = self.post(f"/api/interview/sessions/{sid}/finish/").json()
        report = finished["session"]["report"]
        self.assertEqual(finished["session"]["status"], "completed")
        self.assertIsNone(finished["current_turn"])
        self.assertEqual(report["completed_count"], 2)
        self.assertEqual(report["skipped_count"], 1)
        self.assertEqual(report["answer_mode"], "text")
        self.assertIn("不含语音", report["limitations"])
        self.assertNotIn("score", report)
        loaded = self.client.get(f"/api/interview/sessions/{sid}/").json()
        self.assertEqual(loaded["session"]["report"], report)
        self.assertEqual(self.client.get("/api/interview/sessions/").json()["sessions"][0]["id"], sid)
        self.assertNotIn("transcript", self.client.get("/api/interview/sessions/").json()["sessions"][0]["report"])

    def test_owner_isolation_for_reads_and_every_mutation(self):
        sid, turns = self.create()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f"/api/interview/sessions/{sid}/").status_code, 404)
        self.assertEqual(self.client.get("/api/interview/sessions/").json()["sessions"], [])
        for suffix in ("finish/", "abort/", "report/", f"turns/{turns[0]['id']}/answer/",
                       f"turns/{turns[0]['id']}/skip/", f"turns/{turns[0]['id']}/follow-up/"):
            self.assertEqual(self.post(f"/api/interview/sessions/{sid}/{suffix}", {"answer": "text"}).status_code, 404)

    def test_answer_skip_finish_idempotency_and_conflicting_stale_payload(self):
        sid, turns = self.create()
        original = self.answer(sid, turns[0], "first answer").json()
        self.assertEqual(self.answer(sid, turns[0], "first answer").json(), original)
        self.assertEqual(self.answer(sid, turns[0], "different answer").status_code, 409)
        self.assertEqual(self.post(f"/api/interview/sessions/{sid}/turns/{turns[0]['id']}/skip/").status_code, 409)
        finish = self.post(f"/api/interview/sessions/{sid}/finish/").json()
        self.assertEqual(self.post(f"/api/interview/sessions/{sid}/finish/").json(), finish)
        self.assertEqual(self.answer(sid, turns[1]).status_code, 409)
        self.assertEqual(self.post(f"/api/interview/sessions/{sid}/abort/").status_code, 409)

    def test_invalid_body_bounds_question_ids_and_atomic_creation(self):
        for data in ({"mode": "unknown"}, {"count": True}, {"count": 11}, {"count": 1.5},
                     {"question_ids": [QUESTIONS[0]["id"], QUESTIONS[0]["id"]]},
                     {"question_ids": ["missing"]}, {"mode": "custom", "questions": []},
                     {"mode": "custom", "questions": [{"prompt": "x" * 1501}]},
                     {"mode": "custom", "questions": ["same", "same"]}):
            self.assertEqual(self.post("/api/interview/sessions/", data).status_code, 400)
        self.assertEqual(InterviewSession.objects.count(), 0)
        self.assertEqual(self.client.post("/api/interview/sessions/", "[1]", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post("/api/interview/sessions/", "broken", content_type="application/json").status_code, 400)
        sid, turns = self.create()
        self.assertEqual(self.answer(sid, turns[1]).status_code, 409)
        self.assertEqual(self.answer(sid, turns[0], " ").status_code, 400)
        self.assertEqual(self.answer(sid, turns[0], "x" * 6001).status_code, 400)

    def test_custom_session_provenance_does_not_trust_client_ai_claim(self):
        response = self.post("/api/interview/sessions/", {"mode": "custom", "questions": [
            {"prompt": "Explain your actual project.", "source": "ai_generated"}, "Explain its limitations."
        ]})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(t["source"] == "user_custom" for t in response.json()["turns"]))

    def test_follow_up_success_once_and_current_turn_order(self):
        sid, turns = self.create()
        self.answer(sid, turns[0])
        with patch("apps.interview.ai_services.run_generation", return_value=self.fake_generation(prompt="How did you prove bounded latency?")) as generate:
            payload = self.post(f"/api/interview/sessions/{sid}/turns/{turns[0]['id']}/follow-up/").json()
            self.assertEqual(payload["current_turn"]["kind"], "follow_up")
            self.assertEqual([t["order"] for t in payload["turns"]], [1, 2, 3])
            self.assertEqual(payload["turns"][2]["id"], turns[1]["id"])
            duplicate = self.post(f"/api/interview/sessions/{sid}/turns/{turns[0]['id']}/follow-up/")
            self.assertEqual(duplicate.status_code, 200)
            self.assertEqual(generate.call_count, 1)
        self.answer(sid, payload["current_turn"])
        self.assertEqual(self.post(f"/api/interview/sessions/{sid}/turns/{payload['current_turn']['id']}/follow-up/").status_code, 409)

    def test_follow_up_failure_preserves_answers_and_is_retryable(self):
        sid, turns = self.create()
        self.answer(sid, turns[0])
        before = self.client.get(f"/api/interview/sessions/{sid}/").json()["turns"]
        with patch("apps.interview.ai_services.run_generation", side_effect=InterviewError("Safe AI failure", status=502)):
            response = self.post(f"/api/interview/sessions/{sid}/turns/{turns[0]['id']}/follow-up/")
            self.assertEqual(response.status_code, 502)
        self.assertEqual(self.client.get(f"/api/interview/sessions/{sid}/").json()["turns"], before)
        self.assertIsNone(InterviewSession.objects.get(public_id=sid).ai_busy_since)
        with patch("apps.interview.ai_services.run_generation", return_value=self.fake_generation(prompt="Retry question")):
            self.assertEqual(self.post(f"/api/interview/sessions/{sid}/turns/{turns[0]['id']}/follow-up/").status_code, 200)

    def test_follow_up_rejects_later_progress_and_busy_interleaving(self):
        sid, turns = self.create()
        self.answer(sid, turns[0])
        self.answer(sid, turns[1])
        self.assertEqual(self.post(f"/api/interview/sessions/{sid}/turns/{turns[0]['id']}/follow-up/").status_code, 409)
        sid, turns = self.create()
        self.answer(sid, turns[0])
        def generate(*_args, **_kwargs):
            self.assertEqual(self.answer(sid, turns[1]).status_code, 409)
            self.assertEqual(self.post(f"/api/interview/sessions/{sid}/finish/").status_code, 409)
            self.assertEqual(self.post(f"/api/interview/sessions/{sid}/turns/{turns[0]['id']}/follow-up/").status_code, 409)
            return self.fake_generation(prompt="One safe follow-up")
        with patch("apps.interview.ai_services.run_generation", side_effect=generate):
            self.assertEqual(self.post(f"/api/interview/sessions/{sid}/turns/{turns[0]['id']}/follow-up/").status_code, 200)

    def test_late_generation_rejected_after_lease_replacement(self):
        sid, turns = self.create()
        self.answer(sid, turns[0])
        def generate(*_args, **_kwargs):
            InterviewSession.objects.filter(public_id=sid).update(ai_busy_token="different-generation")
            return self.fake_generation(prompt="Late answer must not insert")
        with patch("apps.interview.ai_services.run_generation", side_effect=generate):
            response = self.post(f"/api/interview/sessions/{sid}/turns/{turns[0]['id']}/follow-up/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "stale_generation")
        self.assertEqual(InterviewSession.objects.get(public_id=sid).turns.count(), 2)

    def test_report_coaching_failure_reload_retry_and_idempotence(self):
        sid, turns = self.create(1)
        self.assertEqual(self.post(f"/api/interview/sessions/{sid}/report/").status_code, 409)
        self.answer(sid, turns[0])
        self.post(f"/api/interview/sessions/{sid}/finish/")
        with patch("apps.interview.ai_services.run_generation", side_effect=InterviewError("AI unavailable", status=502)):
            self.assertEqual(self.post(f"/api/interview/sessions/{sid}/report/").status_code, 502)
        self.assertEqual(self.client.get(f"/api/interview/sessions/{sid}/").json()["session"]["report"]["ai_feedback"]["status"], "failed")
        with patch("apps.interview.ai_services.run_generation", return_value=self.fake_generation(text="Provide reproducible benchmark evidence.")) as generate:
            feedback = self.post(f"/api/interview/sessions/{sid}/report/").json()["session"]["report"]["ai_feedback"]
            self.assertEqual(feedback["status"], "ready")
            self.assertIn("不含语音", feedback["limitations"])
            self.post(f"/api/interview/sessions/{sid}/report/")
            self.assertEqual(generate.call_count, 1)

    def test_custom_text_and_pdf_validation(self):
        result = self.fake_generation(questions=[{"prompt": "Explain your C++ internship", "category": "projects", "difficulty": "intermediate", "source": "ai_generated"}])
        with patch("apps.interview.ai_services.run_generation", return_value=result) as generate:
            response = self.post("/api/interview/custom-questions/", {"resume_text": "C++ internship", "job_description": "Low latency C++", "count": 1})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("resume_excerpt", response.json())
            self.assertEqual(generate.call_args.args[2]["count"], 1)
        for body in ({"resume_text": "", "job_description": "Job"}, {"resume_text": "Resume", "job_description": ""}):
            self.assertEqual(self.post("/api/interview/custom-questions/", body).status_code, 400)
        invalid = SimpleUploadedFile("not.pdf", b"not a PDF", content_type="application/pdf")
        self.assertEqual(self.client.post("/api/interview/custom-questions/", {"resume_file": invalid, "job_description": "Job"}).status_code, 400)
        valid = SimpleUploadedFile("resume.pdf", b"%PDF-fixture", content_type="application/pdf")
        with patch("apps.interview.validation.extract_pdf", return_value="Actual extracted experience"), patch("apps.interview.ai_services.run_generation", return_value=result) as generate:
            response = self.client.post("/api/interview/custom-questions/", {"resume_file": valid, "job_description": "Job", "count": "1"})
            self.assertEqual(response.status_code, 200)
            self.assertIn("Actual extracted experience", generate.call_args.args[2]["resume_text"])

    def test_abort_is_durable_and_history_is_bounded(self):
        sid, turns = self.create()
        self.assertEqual(self.post(f"/api/interview/sessions/{sid}/abort/").json()["session"]["status"], "aborted")
        self.assertEqual(self.post(f"/api/interview/sessions/{sid}/abort/").status_code, 200)
        self.assertEqual(self.answer(sid, turns[0]).status_code, 409)
        InterviewSession.objects.bulk_create([InterviewSession(user=self.user, mode="general", title="Test") for _ in range(101)])
        self.assertEqual(len(self.client.get("/api/interview/sessions/").json()["sessions"]), 100)


class InterviewAiLifecycleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ai-owner", password="test-password")
        self.client.force_login(self.user)
        self.provider = Mock()
        self.provider.config = HttpApiProviderConfig("https://example.test/v1", "secret-fixture", "fixture-model")

    def generate(self):
        return self.client.post("/api/interview/custom-questions/", json.dumps({"resume_text": "C++ internship", "job_description": "C++ role", "count": 1}), content_type="application/json")

    def test_synchronous_success_accounts_usage_and_creates_no_pending_worker_job(self):
        self.provider.complete_chat.return_value = HttpApiProviderResult(
            text=json.dumps({"questions": [{"prompt": "Explain your internship", "category": "projects", "difficulty": "intermediate"}]}),
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}, elapsed_seconds=0.2,
        )
        with patch("apps.interview.ai_services._speaking_http_provider", return_value=self.provider):
            response = self.generate()
        self.assertEqual(response.status_code, 200, response.content)
        task = AITask.objects.get(task_type="interview_custom_questions")
        self.assertEqual(task.status, "succeeded")
        self.assertEqual(task.attempt_count, 1)
        self.assertEqual(task.worker_id, "interview-sync-request")
        self.assertEqual(task.result_payload["provider_elapsed_ms"], 200)
        self.assertIsNotNone(task.usage_id)
        self.assertEqual(CodexUsageEvent.objects.filter(usage_id=task.usage.usage_id).count(), 1)
        self.assertNotIn("secret-fixture", json.dumps(task.result_payload))
        self.assertEqual(response.json()["questions"][0]["source"], "ai_generated")

    def test_provider_error_is_redacted_and_task_terminal(self):
        self.provider.complete_chat.side_effect = RuntimeError("provider secret-fixture password raw trace")
        with patch("apps.interview.ai_services._speaking_http_provider", return_value=self.provider):
            response = self.generate()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret-fixture", response.content.decode())
        task = AITask.objects.get()
        self.assertEqual(task.status, "failed")
        self.assertNotIn("secret-fixture", task.error_message)
        self.assertIsNone(task.usage_id)

    def test_invalid_ai_schema_no_fake_questions_or_success(self):
        for output in ("not json", '{"questions":[]}', '{"questions":[{"prompt":""}]}'):
            self.provider.complete_chat.return_value = HttpApiProviderResult(output)
            with patch("apps.interview.ai_services._speaking_http_provider", return_value=self.provider):
                self.assertEqual(self.generate().status_code, 502)
        self.assertEqual(AITask.objects.filter(status="succeeded").count(), 0)
        self.assertEqual(AITask.objects.filter(status="failed").count(), 3)

    def test_unconfigured_provider_does_not_create_billable_task(self):
        with patch("apps.interview.ai_services._speaking_http_provider", side_effect=RuntimeError("secret-value")):
            response = self.generate()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(AITask.objects.count(), 0)
        self.assertNotIn("secret-value", response.content.decode())


class PdfBoundsTests(TestCase):
    def fake_process(self, output):
        process = Mock()
        process.stdout = io.BytesIO(output)
        process.returncode = 0
        return process

    def test_extraction_caps_stdout_and_discards_stderr(self):
        process = self.fake_process(b"x" * 100000)
        with patch("apps.interview.validation.shutil.which", return_value="pdftotext"), patch("apps.interview.validation.subprocess.Popen", return_value=process) as start:
            with self.assertRaises(InterviewError):
                extract_pdf(b"%PDF-fixture")
        process.kill.assert_called_once()
        self.assertEqual(start.call_args.kwargs["stderr"], subprocess.DEVNULL)

    def test_timeout_kills_and_waits_for_process(self):
        process = self.fake_process(b"")
        process.wait.side_effect = [subprocess.TimeoutExpired("pdftotext", 10), None]
        with patch("apps.interview.validation.shutil.which", return_value="pdftotext"), patch("apps.interview.validation.subprocess.Popen", return_value=process):
            with self.assertRaises(InterviewError):
                extract_pdf(b"%PDF-fixture")
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)

    @skipUnless(shutil.which("pdftotext"), "pdftotext unavailable; text input remains supported")
    def test_real_text_pdf_is_extracted_without_uploading_or_ai(self):
        # Minimal valid one-page fixture, including real xref byte offsets.
        stream = b"BT /F1 12 Tf 50 700 Td (C++ internship and systems engineering) Tj ET"
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]
        data = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for number, value in enumerate(objects, 1):
            offsets.append(len(data))
            data.extend(f"{number} 0 obj\n".encode() + value + b"\nendobj\n")
        xref = len(data)
        data.extend(b"xref\n0 6\n0000000000 65535 f \n")
        for offset in offsets[1:]:
            data.extend(f"{offset:010} 00000 n \n".encode())
        data.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
        self.assertIn("C++ internship and systems engineering", extract_pdf(bytes(data)))
