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
