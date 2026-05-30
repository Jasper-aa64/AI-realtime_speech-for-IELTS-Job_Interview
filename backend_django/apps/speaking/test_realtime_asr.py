from __future__ import annotations

import json
import types
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from .volcengine_asr import (
    ASR_RESULT,
    CONNECTION_STARTED,
    JSON_SERIALIZATION,
    SERVER_FULL_RESPONSE,
    SESSION_FINISHED,
    _header,
    _u32,
    stream_pcm_chunks,
)


def _server_response(event: int, payload: dict, session_id: str = "session-1", connect_id: str = "connect-1") -> bytes:
    body = _u32(event)
    if event not in {1, 2, 50, 51, 52}:
        encoded_session = session_id.encode("utf-8")
        body += _u32(len(encoded_session)) + encoded_session
    if event in {50, 51, 52}:
        encoded_connect = connect_id.encode("utf-8")
        body += _u32(len(encoded_connect)) + encoded_connect
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return _header(SERVER_FULL_RESPONSE, JSON_SERIALIZATION) + body + _u32(len(payload_bytes)) + payload_bytes


class _FakeWebSocket:
    def __init__(self, responses: list[bytes]):
        self.responses = list(responses)
        self.sent: list[bytes] = []
        self.closed = False
        self.timeouts: list[float | int] = []

    def send_binary(self, payload: bytes):
        self.sent.append(payload)

    def recv(self):
        if not self.responses:
            raise TimeoutError("no fake response available")
        return self.responses.pop(0)

    def settimeout(self, value):
        self.timeouts.append(value)

    def close(self):
        self.closed = True


class RealtimeAsrStatusTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="realtime-asr-user", password="test-pass")
        self.client.force_login(self.user)

    def test_status_requires_login(self):
        self.client.logout()
        response = self.client.get("/api/speaking/realtime-asr/status")
        self.assertEqual(response.status_code, 401)

    @override_settings(
        VOLCENGINE_ASR_ENABLED=True,
        VOLCENGINE_ASR_WS_URL="wss://example.invalid/realtime",
        VOLCENGINE_ASR_APP_ID="secret-app-id",
        VOLCENGINE_ASR_ACCESS_KEY="secret-access-key",
        VOLCENGINE_ASR_APP_KEY="secret-app-key",
    )
    def test_status_is_secret_safe(self):
        response = self.client.get("/api/speaking/realtime-asr/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["enabled"])
        self.assertTrue(payload["configured"])
        self.assertEqual(payload["provider"], "volcengine_realtime_asr")
        self.assertEqual(payload["missing_env"], [])
        dumped = json.dumps(payload)
        self.assertNotIn("secret-app-id", dumped)
        self.assertNotIn("secret-access-key", dumped)
        self.assertNotIn("secret-app-key", dumped)


class RealtimeAsrProviderTests(TestCase):
    @override_settings(
        VOLCENGINE_ASR_ENABLED=True,
        VOLCENGINE_ASR_WS_URL="wss://example.invalid/realtime",
        VOLCENGINE_ASR_APP_ID="app-id",
        VOLCENGINE_ASR_ACCESS_KEY="access-key",
        VOLCENGINE_ASR_APP_KEY="app-key",
        VOLCENGINE_ASR_TIMEOUT_SECONDS=5,
    )
    def test_stream_pcm_chunks_emits_interim_final_and_done(self):
        fake_ws = _FakeWebSocket([
            _server_response(CONNECTION_STARTED, {}),
            _server_response(ASR_RESULT, {"results": [{"text": "I study", "is_interim": True}]}),
            _server_response(ASR_RESULT, {"results": [{"text": "I study software engineering.", "is_interim": False}]}),
            _server_response(SESSION_FINISHED, {}),
        ])
        fake_module = types.SimpleNamespace(create_connection=lambda *args, **kwargs: fake_ws)

        with patch.dict("sys.modules", {"websocket": fake_module}):
            events = list(stream_pcm_chunks([b"\x01\x02" * 160], chunk_delay_seconds=0, receive_timeout_seconds=0.001))

        self.assertEqual(events[0]["event"], "started")
        self.assertTrue(any(item["event"] == "interim" and item["interim"] == "I study" for item in events))
        self.assertTrue(any(item["event"] == "final" and item["text"] == "I study software engineering." for item in events))
        self.assertEqual(events[-1]["event"], "done")
        self.assertEqual(events[-1]["transcript"], "I study software engineering.")
        self.assertTrue(fake_ws.closed)

    @override_settings(VOLCENGINE_ASR_ENABLED=False)
    def test_stream_pcm_chunks_reports_disabled_without_connecting(self):
        events = list(stream_pcm_chunks([b"\x00\x00"], chunk_delay_seconds=0))
        self.assertEqual(events, [{"event": "error", "status": "disabled", "error": "VolcEngine ASR disabled."}])
