from __future__ import annotations

import json
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.ai.http_provider import HttpApiProviderError
from apps.speaking import services


class _ProviderResult:
    def __init__(self, text: str, model: str = "gpt-5.4-mini"):
        self.text = text
        self.usage = {"input_tokens": 100, "output_tokens": 50}
        self.elapsed_seconds = 0.25
        self.model = model


class _JsonProvider:
    def __init__(self, text: str, captured: dict | None = None, config=None):
        self.text = text
        self.captured = captured if captured is not None else {}
        self.config = config
        if config is not None:
            self.captured["model"] = config.model

    def complete_chat(self, *args, **kwargs):
        self.captured["messages"] = args[0] if args else kwargs.get("messages")
        self.captured["max_tokens"] = kwargs.get("max_tokens")
        return _ProviderResult(self.text, model=self.captured.get("model") or "gpt-5.4-mini")


@override_settings(
    AI_HTTP_BASE_URL="https://ai.example/v1",
    AI_HTTP_API_KEY="test-key",
    AI_HTTP_MODEL="legacy-model",
    SPEAKING_AI_MODEL="",
    SPEAKING_REPORT_AI_MODEL="gpt-5.4-mini",
)
class SpeakingAiProviderRoutingTests(SimpleTestCase):
    def test_speaking_report_score_prefers_http_gpt54mini(self):
        payload = {
            "fluency_coherence": 6,
            "lexical_resource": 6,
            "grammatical_range": 6,
            "overall_band": 6,
            "feedback": "Clear enough with room for development.",
            "overall_review": {
                "markdown": "### 总体点评\n回答基本完整。\n\n### 复盘重点\n继续展开。",
                "comment": "回答基本完整。",
                "review_points": ["继续展开回答。"],
            },
        }
        captured = {}

        def fake_provider(config=None):
            return _JsonProvider(json.dumps(payload), captured, config=config)

        with patch("apps.speaking.services.HttpApiProvider", side_effect=fake_provider), patch(
            "apps.speaking.services.run_codex"
        ) as run_codex:
            result = services.score_with_codex(
                "Q1: Do you work or study?\nA: I study software engineering because I enjoy solving practical problems.",
                "Q1: Do you work or study?",
                "p1",
                "score-http-route",
            )

        self.assertEqual(result["backend"], "http_api")
        self.assertEqual(result["generation_backend"], "http_api")
        self.assertEqual(result["model"], "gpt-5.4-mini")
        self.assertEqual(captured["model"], "gpt-5.4-mini")
        run_codex.assert_not_called()

    def test_speaking_report_claude_preference_falls_back_to_http(self):
        payload = {
            "fluency_coherence": 6,
            "lexical_resource": 6,
            "grammatical_range": 6,
            "overall_band": 6,
            "feedback": "HTTP fallback after Claude failure.",
            "overall_review": {
                "markdown": "### 总体点评\nHTTP fallback worked.\n\n### 复盘重点\nKeep developing answers.",
                "comment": "HTTP fallback worked.",
                "review_points": ["Keep developing answers."],
            },
        }
        captured = {}

        def fake_provider(config=None):
            return _JsonProvider(json.dumps(payload), captured, config=config)

        with patch(
            "apps.speaking.services.run_claude_cli",
            side_effect=RuntimeError("Claude CLI API error for score-test: 403"),
        ) as run_claude_cli, patch("apps.speaking.services.HttpApiProvider", side_effect=fake_provider), patch(
            "apps.speaking.services.run_codex"
        ) as run_codex:
            result = services.score_with_codex(
                "Q1: Describe a device.\nA: I would like to own a tablet because it is useful for study.",
                "Q1: Describe a device.",
                "p2",
                "score-claude-fallback",
                ai_source="claude_cli",
            )

        self.assertEqual(result["backend"], "http_api")
        self.assertEqual(result["generation_backend"], "http_api")
        self.assertEqual(result["model"], "gpt-5.4-mini")
        self.assertEqual(captured["model"], "gpt-5.4-mini")
        run_claude_cli.assert_called_once()
        run_codex.assert_not_called()

    @override_settings(SPEAKING_REPORT_AI_CALL_MODE="codex")
    def test_speaking_report_can_force_codex_mode(self):
        payload = {
            "fluency_coherence": 6,
            "lexical_resource": 6,
            "grammatical_range": 6,
            "overall_band": 6,
            "feedback": "Codex route.",
        }
        with patch("apps.speaking.services.HttpApiProvider") as http_provider, patch(
            "apps.speaking.services.run_codex", return_value=(json.dumps(payload), {"input_tokens": 10})
        ) as run_codex:
            result = services.score_with_codex(
                "Q1: Do you work or study?\nA: I study software engineering.",
                "Q1: Do you work or study?",
                "p1",
                "score-codex-route",
            )

        self.assertEqual(result["backend"], "codex")
        http_provider.assert_not_called()
        run_codex.assert_called_once()

    def test_speaking_report_preserves_http_error_when_codex_fallback_missing(self):
        class _FailingHttpProvider:
            def complete_chat(self, *args, **kwargs):
                raise HttpApiProviderError(
                    "HTTP AI provider returned 401: Invalid token",
                    status_code=401,
                )

        with patch("apps.speaking.services.HttpApiProvider", return_value=_FailingHttpProvider()), patch(
            "apps.speaking.services.run_codex",
            side_effect=RuntimeError("codex CLI not found"),
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTP AI provider returned 401: Invalid token"):
                services.score_with_codex(
                    "Q1: Do you work or study?\nA: I study software engineering.",
                    "Q1: Do you work or study?",
                    "p1",
                    "score-http-token-expired",
                )

    def test_report_provider_json_preserves_http_error_when_codex_fallback_missing(self):
        class _FailingHttpProvider:
            def complete_chat(self, *args, **kwargs):
                raise HttpApiProviderError(
                    "HTTP AI provider returned 401: Invalid token",
                    status_code=401,
                )

        with patch("apps.speaking.services.HttpApiProvider", return_value=_FailingHttpProvider()), patch(
            "apps.speaking.services.run_codex",
            side_effect=RuntimeError("codex CLI not found"),
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTP AI provider returned 401: Invalid token"):
                services._report_provider_json(
                    "Return JSON.",
                    {"feedback"},
                    "report-json-http-token-expired",
                )

    def test_p3_plan_uses_claude_preference_without_http(self):
        claude_payload = {
            "questions": [
                "Why do some people prefer visiting historic cities?",
                "How can tourism affect local residents?",
                "Do you think domestic travel will become more popular in the future?",
            ],
            "follow_up": "What might be one disadvantage of that trend?",
        }

        with patch(
            "apps.speaking.services.run_claude_cli",
            return_value=(json.dumps(claude_payload), {"input_tokens": 100, "output_tokens": 50}),
        ) as run_claude_cli, patch("apps.speaking.services.HttpApiProvider") as http_provider:
            plan = services.build_p3_plan(
                {
                    "source": "p2_report",
                    "theme": "Describe a place you would like to visit in the future",
                    "prior_answer": "I would like to visit Chengdu because I am interested in food and local culture.",
                    "ai_source": "claude_cli",
                }
            )

        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["backend"], "claude_cli")
        self.assertEqual(plan["question_count"], 3)
        run_claude_cli.assert_called_once()
        http_provider.assert_not_called()

    def test_p3_plan_claude_failure_does_not_fall_through_to_http(self):
        with patch(
            "apps.speaking.services.run_claude_cli",
            side_effect=RuntimeError("Claude CLI API error for p3: 429"),
        ) as run_claude_cli, patch("apps.speaking.services.HttpApiProvider") as http_provider:
            plan = services.build_p3_plan(
                {
                    "source": "p2_report",
                    "theme": "Describe a place you would like to visit in the future",
                    "prior_answer": "I would like to visit Chengdu because I am interested in food and local culture.",
                    "ai_source": "claude_cli",
                }
            )

        self.assertEqual(plan["status"], "failed")
        self.assertIn("Claude CLI API error", plan["error"])
        run_claude_cli.assert_called_once()
        http_provider.assert_not_called()
