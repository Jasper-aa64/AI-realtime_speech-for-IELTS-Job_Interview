from __future__ import annotations

import json

from channels.generic.websocket import AsyncJsonWebsocketConsumer, AsyncWebsocketConsumer


class RealtimePingConsumer(AsyncJsonWebsocketConsumer):
    """Minimal Phase 2.1 WebSocket consumer used to validate ASGI wiring."""

    async def connect(self):
        await self.accept()
        await self.send_json({
            "event": "connected",
            "service": "ielts-realtime",
            "protocol": "ping-v1",
        })

    async def receive_json(self, content, **kwargs):
        event = str((content or {}).get("event") or "")
        if event == "ping":
            await self.send_json({
                "event": "pong",
                "echo": (content or {}).get("echo"),
            })
            return
        await self.send_json({
            "event": "error",
            "error": "unsupported_event",
        })


class RealtimePcmUplinkConsumer(AsyncWebsocketConsumer):
    """Phase 2.2 transport smoke consumer for browser PCM frame uplink."""

    async def connect(self):
        self.frame_count = 0
        self.byte_count = 0
        await self.accept()
        await self._send_json({
            "event": "connected",
            "service": "ielts-realtime",
            "protocol": "pcm-uplink-v1",
            "sample_rate": 16000,
            "channels": 1,
        })

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is not None:
            self.frame_count += 1
            self.byte_count += len(bytes_data)
            await self._send_json({
                "event": "pcm_ack",
                "frames": self.frame_count,
                "bytes": self.byte_count,
                "last_bytes": len(bytes_data),
            })
            return

        payload = self._parse_json(text_data)
        event = str(payload.get("event") or "")
        if event in {"start", "status"}:
            await self._send_json(self._status_payload("status"))
            return
        if event == "stop":
            await self._send_json(self._status_payload("stopped"))
            await self.close(code=1000)
            return
        await self._send_json({"event": "error", "error": "unsupported_event"})

    def _status_payload(self, event: str) -> dict:
        return {
            "event": event,
            "frames": self.frame_count,
            "bytes": self.byte_count,
            "sample_rate": 16000,
            "channels": 1,
        }

    async def _send_json(self, payload: dict):
        await self.send(text_data=json.dumps(payload, separators=(",", ":")))

    @staticmethod
    def _parse_json(text_data) -> dict:
        if not text_data:
            return {}
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
