from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.speaking import services


@dataclass
class _ProviderResult:
    text: str
    elapsed_seconds: float = 0.123
    model: str = "fast-model"


class _Provider:
    def __init__(self, text: str):
        self.text = text

    def complete_chat(self, *args, **kwargs):
        return _ProviderResult(self.text)


class _CapturingProvider(_Provider):
    def __init__(self, text: str, capture: dict):
        super().__init__(text)
        self.capture = capture

    def complete_chat(self, *args, **kwargs):
        self.capture["args"] = args
        self.capture["kwargs"] = kwargs
        return super().complete_chat(*args, **kwargs)


@override_settings(
    AI_HTTP_BASE_URL="https://ai.example/v1",
    AI_HTTP_API_KEY="test-key",
    AI_HTTP_MODEL="legacy-model",
    SPEAKING_AI_MODEL="",
)
class HttpFollowUpRoutingTests(SimpleTestCase):
    def test_p3_follow_up_prefers_http_success(self):
        with patch("apps.speaking.services.HttpApiProvider", return_value=_Provider("How might this affect families?")), patch(
            "apps.speaking.services.quick_follow_up_codex_runner"
        ) as codex_runner:
            result = services._generate_p3_dynamic_follow_up(
                "Why do some people prefer living in cities?",
                "cause_effect",
                "It gives people better jobs and services, so families can plan their lives more easily.",
                call_id="case-1",
            )

        self.assertEqual(result["follow_up"], "How might this affect families?")
        self.assertEqual(result["backend"], "http_api")
        self.assertEqual(result["status"], "ready")
        codex_runner.assert_not_called()


    def test_follow_up_http_uses_speaking_default_model_override(self):
        captured = {}

        def fake_provider(config=None):
            captured["model"] = config.model
            return _Provider("How might this affect families?")

        with patch("apps.speaking.services.HttpApiProvider", side_effect=fake_provider):
            result = services.quick_follow_up_http_runner(
                "Why do some people prefer living in cities?",
                "It gives people better jobs and services, so families can plan their lives more easily.",
                question_type="cause_effect",
            )

        self.assertEqual(result["backend"], "http_api")
        self.assertEqual(captured["model"], "gpt-5.4-mini")

    def test_p3_follow_up_http_uses_creative_temperature(self):
        captured = {}
        with patch(
            "apps.speaking.services.HttpApiProvider",
            return_value=_CapturingProvider("How might this affect families in the long run?", captured),
        ):
            result = services.quick_follow_up_http_runner(
                "Why do some people prefer living in cities?",
                "It gives people better jobs and services, so families can plan their lives more easily.",
                question_type="cause_effect",
            )

        self.assertEqual(result["backend"], "http_api")
        self.assertGreaterEqual(captured["kwargs"]["temperature"], 0.55)
        user_prompt = captured["args"][0][1]["content"]
        self.assertIn("avoid generic repeats", user_prompt)

    @override_settings(SPEAKING_FOLLOWUP_AI_CALL_MODE="codex")
    def test_p3_follow_up_can_force_codex_mode(self):
        with patch("apps.speaking.services.quick_follow_up_http_runner") as http_runner, patch(
            "apps.speaking.services.quick_follow_up_codex_runner", return_value="What could happen in the future?"
        ):
            result = services._generate_p3_dynamic_follow_up(
                "Why is public transport important?",
                "future_prediction",
                "It can reduce traffic and make cities cleaner for ordinary people.",
                call_id="case-codex-mode",
            )

        self.assertEqual(result["backend"], "codex_quick")
        self.assertEqual(result["provider"], "codex_cli")
        self.assertEqual(result["model"], services.P3_QUICK_FOLLOW_UP_CODEX_MODEL)
        http_runner.assert_not_called()

    def test_p3_http_failure_falls_back_to_codex(self):
        with patch("apps.speaking.services.quick_follow_up_http_runner", side_effect=RuntimeError("http unavailable")), patch(
            "apps.speaking.services.quick_follow_up_codex_runner", return_value="What could happen in the future?"
        ):
            result = services._generate_p3_dynamic_follow_up(
                "Why is public transport important?",
                "future_prediction",
                "It can reduce traffic and make cities cleaner for ordinary people.",
                call_id="case-2",
            )

        self.assertEqual(result["follow_up"], "What could happen in the future?")
        self.assertEqual(result["backend"], "codex_quick")
        self.assertEqual(result["status"], "ready")

    def test_p3_provider_chain_failure_is_explicit_fallback(self):
        with patch("apps.speaking.services.quick_follow_up_http_runner", side_effect=RuntimeError("http unavailable")), patch(
            "apps.speaking.services.quick_follow_up_codex_runner", side_effect=RuntimeError("codex unavailable")
        ):
            result = services._generate_p3_dynamic_follow_up(
                "Why is public transport important?",
                "future_prediction",
                "It helps people move around.",
                call_id="case-3",
            )

        self.assertEqual(result["backend"], "fallback")
        self.assertEqual(result["status"], "fallback")
        self.assertIn("http_api:", result["error"])
        self.assertIn("codex_quick:", result["error"])

    def test_p1_identity_follow_up_prefers_http_success(self):
        with patch(
            "apps.speaking.services.HttpApiProvider",
            return_value=_Provider('{"follow_up": "How does your internship connect with your studies?"}'),
        ), patch("apps.speaking.services.run_codex") as run_codex:
            result = services._generate_p1_identity_follow_up(
                "I am a software engineering student, and I am doing an internship at a small company.",
                "p1-case-1",
            )

        self.assertEqual(result["follow_up"], "How does your internship connect with your studies?")
        self.assertEqual(result["backend"], "http_api")
        self.assertEqual(result["status"], "ready")
        run_codex.assert_not_called()

    def test_p1_identity_follow_up_accepts_plain_http_question(self):
        with patch(
            "apps.speaking.services.HttpApiProvider",
            return_value=_Provider("How does your internship connect with your software engineering studies?"),
        ), patch("apps.speaking.services.run_codex") as run_codex:
            result = services._generate_p1_identity_follow_up(
                "I study software engineering and I am doing an internship.",
                "p1-case-plain",
            )

        self.assertEqual(result["follow_up"], "How does your internship connect with your software engineering studies?")
        self.assertEqual(result["backend"], "http_api")
        run_codex.assert_not_called()

    def test_p1_identity_follow_up_http_uses_creative_temperature(self):
        captured = {}
        with patch(
            "apps.speaking.services.HttpApiProvider",
            return_value=_CapturingProvider('{"follow_up":"What part of your studies feels most useful in real life?"}', captured),
        ):
            result = services._generate_p1_identity_follow_up(
                "I am a software engineering student, and I am doing an internship.",
                "p1-temperature",
            )

        self.assertEqual(result["backend"], "http_api")
        self.assertGreaterEqual(captured["kwargs"]["temperature"], 0.55)
        user_prompt = captured["args"][0][1]["content"]
        self.assertIn("avoid asking the same obvious follow-up every time", user_prompt)

    def test_p1_http_failure_falls_back_to_codex(self):
        with patch("apps.speaking.services.HttpApiProvider", side_effect=RuntimeError("http unavailable")), patch(
            "apps.speaking.services.run_codex",
            return_value=('{"follow_up": "What do you enjoy most about your studies?"}', None),
        ):
            result = services._generate_p1_identity_follow_up("I am a university student.", "p1-case-2")

        self.assertEqual(result["follow_up"], "What do you enjoy most about your studies?")
        self.assertEqual(result["backend"], "codex")
        self.assertEqual(result["status"], "ready")

    def test_p1_provider_chain_failure_is_explicit_fallback(self):
        with patch("apps.speaking.services.HttpApiProvider", side_effect=RuntimeError("http unavailable")), patch(
            "apps.speaking.services.run_codex", side_effect=RuntimeError("codex unavailable")
        ):
            result = services._generate_p1_identity_follow_up("I am a university student.", "p1-case-3")

        self.assertEqual(result["backend"], "fallback")
        self.assertEqual(result["status"], "fallback")
        self.assertIn("http_api:", result["error"])
        self.assertIn("codex:", result["error"])
