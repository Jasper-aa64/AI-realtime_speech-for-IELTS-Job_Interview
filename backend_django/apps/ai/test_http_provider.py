from __future__ import annotations

import os
import urllib.error
from io import BytesIO
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.ai.http_provider import HttpApiProvider, HttpApiProviderConfig, HttpApiProviderError, load_http_api_provider_config


class _StreamingResponse:
    def __init__(self, lines: list[bytes]):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self.lines)


class HttpApiProviderTests(SimpleTestCase):
    @override_settings(AI_HTTP_BASE_URL="", AI_HTTP_API_KEY="", AI_HTTP_MODEL="")
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_config_is_explicit(self):
        with self.assertRaises(HttpApiProviderError) as raised:
            load_http_api_provider_config()

        self.assertEqual(raised.exception.error_code, "http_api_provider_not_configured")
        self.assertIn("AI_HTTP_BASE_URL", str(raised.exception))
        self.assertIn("AI_HTTP_API_KEY", str(raised.exception))
        self.assertIn("AI_HTTP_MODEL", str(raised.exception))

    def test_streaming_delta_content_is_combined(self):
        response = _StreamingResponse(
            [
                b'data: {"choices":[{"delta":{"content":"What "}}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"changed?"},"finish_reason":"stop"}]}\n\n',
                b'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2}}\n\n',
                b"data: [DONE]\n\n",
            ]
        )

        text, usage = HttpApiProvider._parse_stream_response(response)

        self.assertEqual(text, "What changed?")
        self.assertEqual(usage, {"prompt_tokens": 3, "completion_tokens": 2})

    def test_stream_tokens_yields_delta_content_as_it_arrives(self):
        config = HttpApiProviderConfig(
            base_url="https://example.test/v1",
            api_key="secret-token",
            model="fast-model",
            timeout_seconds=1,
        )
        provider = HttpApiProvider(config)
        response = _StreamingResponse(
            [
                b'data: {"choices":[{"delta":{"content":"How "}}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"exactly?"},"finish_reason":"stop"}]}\n\n',
                b"data: [DONE]\n\n",
            ]
        )

        with patch.object(provider._opener, "open", return_value=response):
            chunks = list(provider.stream_tokens([{"role": "user", "content": "Ask one question"}], max_tokens=8))

        self.assertEqual(chunks, ["How ", "exactly?"])

    def test_stream_tokens_rejects_provider_stream_error(self):
        config = HttpApiProviderConfig(
            base_url="https://example.test/v1",
            api_key="secret-token",
            model="fast-model",
            timeout_seconds=1,
        )
        provider = HttpApiProvider(config)
        response = _StreamingResponse([b'data: {"error":{"message":"bad request secret-token"}}\n\n'])

        with patch.object(provider._opener, "open", return_value=response):
            with self.assertRaises(HttpApiProviderError) as raised:
                list(provider.stream_tokens([{"role": "user", "content": "Ask one question"}], max_tokens=8))

        self.assertEqual(raised.exception.error_code, "http_api_provider_stream_error")
        self.assertNotIn("secret-token", str(raised.exception))

    def test_complete_chat_redacts_api_key_from_http_error(self):
        config = HttpApiProviderConfig(
            base_url="https://example.test/v1",
            api_key="secret-token",
            model="fast-model",
            timeout_seconds=1,
        )
        provider = HttpApiProvider(config)
        error = urllib.error.HTTPError(
            "https://example.test/v1/chat/completions",
            401,
            "Unauthorized",
            {},
            BytesIO(b'{"error":{"message":"bad key secret-token"}}'),
        )

        with patch.object(provider._opener, "open", side_effect=error):
            with self.assertRaises(HttpApiProviderError) as raised:
                provider.complete_chat([{"role": "user", "content": "Say hello"}], max_tokens=8)

        self.assertNotIn("secret-token", str(raised.exception))
        self.assertIn("[redacted]", str(raised.exception))

    def test_complete_chat_success_does_not_expose_api_key_in_metadata(self):
        config = HttpApiProviderConfig(
            base_url="https://example.test/v1",
            api_key="secret-token",
            model="fast-model",
            timeout_seconds=1,
        )
        provider = HttpApiProvider(config)
        response = _StreamingResponse([b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n', b"data: [DONE]\n\n"])

        with patch.object(provider._opener, "open", return_value=response) as urlopen:
            result = provider.complete_chat([{"role": "user", "content": "Say hello"}], max_tokens=8)

        self.assertEqual(result.text, "Hello")
        self.assertEqual(result.model, "fast-model")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/v1/chat/completions")
        self.assertNotIn("secret-token", repr(result.metadata))

    def test_streaming_length_finish_reason_keeps_received_text(self):
        response = _StreamingResponse(
            [
                b'data: {"choices":[{"delta":{"content":"Partial"},"finish_reason":"length"}]}\n\n',
                b'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":8}}\n\n',
            ]
        )

        text, usage = HttpApiProvider._parse_stream_response(response)

        self.assertEqual(text, "Partial")
        self.assertEqual(usage, {"prompt_tokens": 10, "completion_tokens": 8})
