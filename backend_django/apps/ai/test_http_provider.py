from __future__ import annotations

import json
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


class _JsonResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class _FinalEventThenTimeoutResponse:
    """A relay that sends a terminal SSE event but leaves the socket open."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        yield b'data: {"type":"response.output_text.delta","delta":"Complete JSON"}\n\n'
        yield b'data: {"type":"response.completed","response":{"usage":{"output_tokens":2}}}\n\n'
        raise TimeoutError("The read operation timed out")


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

    def test_streaming_delta_content_list_text_is_combined(self):
        response = _StreamingResponse(
            [
                b'data: {"choices":[{"delta":{"content":[{"type":"text","text":"What "},{"type":"text","text":"changed?"}]}}]}\n\n',
                b"data: [DONE]\n\n",
            ]
        )

        text, usage = HttpApiProvider._parse_stream_response(response)

        self.assertEqual(text, "What changed?")
        self.assertIsNone(usage)

    def test_streaming_message_content_is_used_when_delta_is_missing(self):
        response = _StreamingResponse(
            [
                b'data: {"choices":[{"message":{"content":"Whole answer"},"finish_reason":"stop"}]}\n\n',
                b"data: [DONE]\n\n",
            ]
        )

        text, usage = HttpApiProvider._parse_stream_response(response)

        self.assertEqual(text, "Whole answer")
        self.assertIsNone(usage)

    def test_streaming_responses_output_text_delta_is_combined(self):
        response = _StreamingResponse(
            [
                b'data: {"type":"response.output_text.delta","delta":"What "}\n\n',
                b'data: {"type":"response.output_text.delta","delta":"changed?"}\n\n',
                b'data: {"type":"response.completed","response":{"usage":{"input_tokens":4,"output_tokens":2}}}\n\n',
            ]
        )

        text, usage = HttpApiProvider._parse_stream_response(response)

        self.assertEqual(text, "What changed?")
        self.assertEqual(usage, {"input_tokens": 4, "output_tokens": 2})

    def test_streaming_final_event_ends_without_waiting_for_socket_close(self):
        text, usage = HttpApiProvider._parse_stream_response(_FinalEventThenTimeoutResponse())

        self.assertEqual(text, "Complete JSON")
        self.assertEqual(usage, {"output_tokens": 2})

    def test_streaming_anthropic_content_block_delta_is_combined(self):
        response = _StreamingResponse(
            [
                b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"What "}}\n\n',
                b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"changed?"}}\n\n',
                b'data: {"type":"message_delta","usage":{"output_tokens":2}}\n\n',
            ]
        )

        text, usage = HttpApiProvider._parse_stream_response(response)

        self.assertEqual(text, "What changed?")
        self.assertEqual(usage, {"output_tokens": 2})

    def test_streaming_final_response_payload_is_used_when_no_delta_arrives(self):
        response = _StreamingResponse(
            [
                (
                    b'data: {"type":"response.completed","response":{"output":[{"content":'
                    b'[{"type":"output_text","text":"Whole answer"}]}],"usage":{"output_tokens":2}}}\n\n'
                ),
            ]
        )

        text, usage = HttpApiProvider._parse_stream_response(response)

        self.assertEqual(text, "Whole answer")
        self.assertEqual(usage, {"output_tokens": 2})

    def test_streaming_final_response_payload_does_not_duplicate_delta(self):
        response = _StreamingResponse(
            [
                b'data: {"type":"response.output_text.delta","delta":"Whole answer"}\n\n',
                (
                    b'data: {"type":"response.completed","response":{"output":[{"content":'
                    b'[{"type":"output_text","text":"Whole answer"}]}]}}\n\n'
                ),
            ]
        )

        text, usage = HttpApiProvider._parse_stream_response(response)

        self.assertEqual(text, "Whole answer")
        self.assertIsNone(usage)

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

    def test_stream_tokens_yields_responses_delta_without_final_duplicate(self):
        config = HttpApiProviderConfig(
            base_url="https://example.test/v1",
            api_key="secret-token",
            model="fast-model",
            timeout_seconds=1,
        )
        provider = HttpApiProvider(config)
        response = _StreamingResponse(
            [
                b'data: {"type":"response.output_text.delta","delta":"Exactly."}\n\n',
                (
                    b'data: {"type":"response.completed","response":{"output":[{"content":'
                    b'[{"type":"output_text","text":"Exactly."}]}]}}\n\n'
                ),
            ]
        )

        with patch.object(provider._opener, "open", return_value=response):
            chunks = list(provider.stream_tokens([{"role": "user", "content": "Ask one question"}], max_tokens=8))

        self.assertEqual(chunks, ["Exactly."])

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
        self.assertNotIn("response_format", json.loads(request.data.decode("utf-8")))

    def test_complete_chat_sends_optional_json_object_response_format(self):
        config = HttpApiProviderConfig(
            base_url="https://example.test/v1",
            api_key="secret-token",
            model="fast-model",
            timeout_seconds=1,
        )
        provider = HttpApiProvider(config)
        response = _JsonResponse(
            b'{"choices":[{"message":{"content":"{\\"turns\\":[]}"}}]}'
        )

        with patch.object(provider._opener, "open", return_value=response) as urlopen:
            result = provider.complete_chat(
                [{"role": "user", "content": "Return report JSON"}],
                max_tokens=8,
                stream=False,
                response_format={"type": "json_object"},
            )

        self.assertEqual(result.text, '{"turns":[]}')
        request_body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(request_body["response_format"], {"type": "json_object"})
        self.assertFalse(request_body["stream"])

    def test_json_message_content_list_text_is_combined(self):
        raw_body = (
            b'{"choices":[{"message":{"content":[{"type":"text","text":"Hello "},{"type":"text","text":"there"}]}}],'
            b'"usage":{"prompt_tokens":2,"completion_tokens":2}}'
        )

        text, usage = HttpApiProvider._parse_json_response(raw_body)

        self.assertEqual(text, "Hello there")
        self.assertEqual(usage, {"prompt_tokens": 2, "completion_tokens": 2})

    def test_json_responses_output_array_text_is_combined(self):
        raw_body = (
            b'{"output":[{"content":[{"type":"output_text","text":"Hello "},{"type":"output_text","text":"there"}]}],'
            b'"usage":{"input_tokens":2,"output_tokens":2}}'
        )

        text, usage = HttpApiProvider._parse_json_response(raw_body)

        self.assertEqual(text, "Hello there")
        self.assertEqual(usage, {"input_tokens": 2, "output_tokens": 2})

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
