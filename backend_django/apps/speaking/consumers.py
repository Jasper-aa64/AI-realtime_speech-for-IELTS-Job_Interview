from __future__ import annotations

from channels.generic.websocket import AsyncJsonWebsocketConsumer


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
