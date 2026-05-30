from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase, override_settings
from unittest.mock import patch

from config.asgi import application


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class AsgiChannelsPingTests(SimpleTestCase):
    def test_ping_websocket_connects_and_echoes_json(self):
        async_to_sync(self._run_ping_websocket)()

    async def _run_ping_websocket(self):
        communicator = WebsocketCommunicator(
            application,
            "/ws/realtime/ping/",
            headers=[
                (b"host", b"testserver"),
                (b"origin", b"http://testserver"),
            ],
        )
        connected, _subprotocol = await communicator.connect()
        self.assertTrue(connected)
        try:
            connected_payload = await communicator.receive_json_from()
            self.assertEqual(connected_payload["event"], "connected")
            self.assertEqual(connected_payload["service"], "ielts-realtime")

            await communicator.send_json_to({"event": "ping", "echo": "phase-2.1"})
            pong = await communicator.receive_json_from()
            self.assertEqual(pong, {"event": "pong", "echo": "phase-2.1"})
        finally:
            await communicator.disconnect()

    def test_pcm_uplink_websocket_counts_binary_frames(self):
        async_to_sync(self._run_pcm_uplink_websocket)()

    async def _run_pcm_uplink_websocket(self):
        communicator = WebsocketCommunicator(
            application,
            "/ws/realtime/pcm/",
            headers=[
                (b"host", b"testserver"),
                (b"origin", b"http://testserver"),
            ],
        )
        connected, _subprotocol = await communicator.connect()
        self.assertTrue(connected)
        try:
            connected_payload = await communicator.receive_json_from()
            self.assertEqual(connected_payload["event"], "connected")
            self.assertEqual(connected_payload["protocol"], "pcm-uplink-v1")

            await communicator.send_to(bytes_data=b"\x00\x01" * 160)
            first_ack = await communicator.receive_json_from()
            self.assertEqual(first_ack["event"], "pcm_ack")
            self.assertEqual(first_ack["frames"], 1)
            self.assertEqual(first_ack["bytes"], 320)

            await communicator.send_to(bytes_data=b"\x02\x03" * 80)
            second_ack = await communicator.receive_json_from()
            self.assertEqual(second_ack["frames"], 2)
            self.assertEqual(second_ack["bytes"], 480)

            await communicator.send_json_to({"event": "stop"})
            stopped = await communicator.receive_json_from()
            self.assertEqual(stopped["event"], "stopped")
            self.assertEqual(stopped["frames"], 2)
            self.assertEqual(stopped["bytes"], 480)
        finally:
            await communicator.disconnect()

    def test_pcm_uplink_streams_fake_asr_events(self):
        async_to_sync(self._run_pcm_uplink_streams_fake_asr_events)()

    async def _run_pcm_uplink_streams_fake_asr_events(self):
        def fake_stream_pcm_chunks(pcm_chunks, **_kwargs):
            yield {"event": "started", "provider": "fake_asr", "sample_rate": 16000, "channels": 1}
            chunks = []
            for chunk in pcm_chunks:
                chunks.append(chunk)
                if len(chunks) == 1:
                    yield {"event": "interim", "provider": "fake_asr", "text": "", "interim": "I study"}
                elif len(chunks) == 2:
                    yield {
                        "event": "final",
                        "provider": "fake_asr",
                        "text": "I study software engineering.",
                        "segment": "I study software engineering.",
                    }
            yield {
                "event": "done",
                "provider": "fake_asr",
                "transcript": "I study software engineering.",
                "ok": True,
            }

        communicator = WebsocketCommunicator(
            application,
            "/ws/realtime/pcm/",
            headers=[
                (b"host", b"testserver"),
                (b"origin", b"http://testserver"),
            ],
        )
        connected, _subprotocol = await communicator.connect()
        self.assertTrue(connected)
        try:
            await communicator.receive_json_from()
            with patch("apps.speaking.consumers.stream_pcm_chunks", side_effect=fake_stream_pcm_chunks):
                await communicator.send_json_to({"event": "start_asr"})
                first_events = await self._receive_events_until(communicator, {"asr_started", "asr_connecting"})
                self.assertIn("asr_started", {event["event"] for event in first_events})

                await communicator.send_to(bytes_data=b"\x01\x02" * 160)
                interim_events = await self._receive_events_until(communicator, {"pcm_ack", "asr_interim"})
                self.assertIn("pcm_ack", {event["event"] for event in interim_events})
                self.assertTrue(any(event.get("interim") == "I study" for event in interim_events))

                await communicator.send_to(bytes_data=b"\x03\x04" * 160)
                final_events = await self._receive_events_until(communicator, {"pcm_ack", "asr_final"})
                self.assertTrue(any(event.get("event") == "asr_final" for event in final_events))
                self.assertTrue(any(event.get("text") == "I study software engineering." for event in final_events))

                await communicator.send_json_to({"event": "stop_asr"})
                done_events = await self._receive_events_until(communicator, {"asr_done", "asr_stopped"})
                self.assertTrue(any(event.get("event") == "asr_done" and event.get("ok") for event in done_events))
        finally:
            await communicator.disconnect()

    def test_pcm_uplink_asr_error_does_not_break_pcm_ack(self):
        async_to_sync(self._run_pcm_uplink_asr_error_does_not_break_pcm_ack)()

    async def _run_pcm_uplink_asr_error_does_not_break_pcm_ack(self):
        def fake_stream_pcm_chunks(_pcm_chunks, **_kwargs):
            yield {"event": "error", "status": "disabled", "error": "ASR disabled for test."}

        communicator = WebsocketCommunicator(
            application,
            "/ws/realtime/pcm/",
            headers=[
                (b"host", b"testserver"),
                (b"origin", b"http://testserver"),
            ],
        )
        connected, _subprotocol = await communicator.connect()
        self.assertTrue(connected)
        try:
            await communicator.receive_json_from()
            with patch("apps.speaking.consumers.stream_pcm_chunks", side_effect=fake_stream_pcm_chunks):
                await communicator.send_json_to({"event": "start_asr"})
                error_events = await self._receive_events_until(communicator, {"asr_error"})
                self.assertTrue(any(event.get("event") == "asr_error" for event in error_events))

                await communicator.send_to(bytes_data=b"\x05\x06" * 80)
                ack = await self._receive_event(communicator, "pcm_ack")
                self.assertEqual(ack["frames"], 1)
                self.assertEqual(ack["bytes"], 160)
        finally:
            await communicator.disconnect()

    async def _receive_events_until(self, communicator, required_events: set[str], limit: int = 8):
        seen: list[dict] = []
        required = set(required_events)
        for _ in range(limit):
            event = await communicator.receive_json_from()
            seen.append(event)
            required.discard(event.get("event"))
            if not required:
                return seen
        self.fail(f"Did not receive events {sorted(required)}; saw {seen!r}")

    async def _receive_event(self, communicator, event_name: str, limit: int = 8):
        for _ in range(limit):
            event = await communicator.receive_json_from()
            if event.get("event") == event_name:
                return event
        self.fail(f"Did not receive event {event_name!r}")
