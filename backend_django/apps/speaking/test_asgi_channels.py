from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase, override_settings

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
