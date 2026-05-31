from __future__ import annotations

import json
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

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


@override_settings(AI_HTTP_BASE_URL="https://ai.example/v1", AI_HTTP_API_KEY="test-key", AI_HTTP_MODEL="legacy-model")
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
