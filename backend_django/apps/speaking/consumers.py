from __future__ import annotations

import asyncio
import json
import queue
import threading
from collections.abc import Iterator

from channels.generic.websocket import AsyncJsonWebsocketConsumer, AsyncWebsocketConsumer
from django.conf import settings

from .volcengine_asr import stream_pcm_chunks


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
        self.asr_enabled = False
        self.asr_queue: queue.Queue[bytes | None] | None = None
        self.asr_thread: threading.Thread | None = None
        self.asr_loop = asyncio.get_running_loop()
        self.asr_context: dict[str, str | bool] = {}
        self.fake_asr_enabled = False
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
            if self.asr_enabled and self.asr_queue is not None:
                self.asr_queue.put(bytes(bytes_data))
            await self._send_json({
                "event": "pcm_ack",
                "frames": self.frame_count,
                "bytes": self.byte_count,
                "last_bytes": len(bytes_data),
            })
            return

        payload = self._parse_json(text_data)
        event = str(payload.get("event") or "")
        if event == "start":
            await self._send_json(self._status_payload("status"))
            return
        if event == "start_asr":
            self.asr_context = self._asr_context_from_payload(payload)
            self.fake_asr_enabled = bool(payload.get("fake_asr")) and bool(settings.DEBUG)
            self._start_asr_thread()
            await self._send_json(self._status_payload("asr_connecting"))
            return
        if event == "status":
            await self._send_json(self._status_payload("status"))
            return
        if event == "stop_asr":
            self._stop_asr_thread()
            await self._send_json(self._status_payload("asr_stopped"))
            return
        if event == "stop":
            self._stop_asr_thread()
            await self._send_json(self._status_payload("stopped"))
            await self.close(code=1000)
            return
        await self._send_json({"event": "error", "error": "unsupported_event"})

    async def disconnect(self, close_code):
        self._stop_asr_thread()

    def _status_payload(self, event: str) -> dict:
        return {
            "event": event,
            "frames": self.frame_count,
            "bytes": self.byte_count,
            "sample_rate": 16000,
            "channels": 1,
        }

    def _start_asr_thread(self):
        if self.asr_thread and self.asr_thread.is_alive():
            return
        self.asr_enabled = True
        self.asr_queue = queue.Queue()
        self.asr_thread = threading.Thread(target=self._run_asr_stream, name="ielts-realtime-asr", daemon=True)
        self.asr_thread.start()

    def _stop_asr_thread(self):
        self.asr_enabled = False
        if self.asr_queue is not None:
            self.asr_queue.put(None)
        self.asr_queue = None
        self.asr_thread = None

    def _pcm_chunks(self) -> Iterator[bytes]:
        while True:
            current_queue = self.asr_queue
            if current_queue is None:
                return
            chunk = current_queue.get()
            if chunk is None:
                return
            yield chunk

    def _run_asr_stream(self):
        try:
            stream = self._fake_stream_pcm_chunks if self.fake_asr_enabled else stream_pcm_chunks
            for event in stream(self._pcm_chunks()):
                self._send_from_thread(self._asr_payload(event))
        except Exception as exc:
            self._send_from_thread({
                "event": "asr_error",
                "status": "error",
                "error": str(exc),
            })
        finally:
            self.asr_enabled = False
            self.fake_asr_enabled = False

    def _fake_stream_pcm_chunks(self, pcm_chunks: Iterator[bytes]) -> Iterator[dict]:
        """Deterministic DEBUG-only ASR stream for no-key realtime pipeline drills."""
        provider = "fake_realtime_asr"
        yield {"event": "started", "provider": provider, "sample_rate": 16000, "channels": 1}
        transcript = "I study software engineering and I am doing an internship at a tech company."
        saw_audio = False
        for index, _chunk in enumerate(pcm_chunks, start=1):
            saw_audio = True
            if index == 1:
                yield {"event": "interim", "provider": provider, "text": "", "interim": "I study software engineering"}
            elif index == 2:
                yield {
                    "event": "final",
                    "provider": provider,
                    "text": transcript,
                    "segment": transcript,
                }
            else:
                yield {
                    "event": "interim",
                    "provider": provider,
                    "text": transcript,
                    "interim": "",
                }
        yield {
            "event": "done",
            "provider": provider,
            "transcript": transcript if saw_audio else "",
            "ok": saw_audio,
        }

    def _send_from_thread(self, payload: dict):
        try:
            future = asyncio.run_coroutine_threadsafe(self._send_json(payload), self.asr_loop)
            future.result(timeout=1)
        except Exception:
            # The browser may have disconnected; realtime ASR must never crash
            # the socket thread or the baseline recording flow.
            pass

    @staticmethod
    def _asr_context_from_payload(payload: dict) -> dict[str, str | bool]:
        return {
            "attempt_id": str(payload.get("attempt_id") or "").strip(),
            "turn_id": str(payload.get("turn_id") or "").strip(),
            "stream_follow_up": bool(payload.get("stream_follow_up")),
        }

    def _with_asr_context(self, payload: dict) -> dict:
        context = {key: value for key, value in self.asr_context.items() if value not in ("", None, False)}
        if not context:
            return payload
        return {**payload, "turn_context": context}

    def _asr_payload(self, event: dict) -> dict:
        event_name = str(event.get("event") or "")
        if event_name == "started":
            return self._with_asr_context({
                "event": "asr_started",
                "provider": event.get("provider", ""),
                "sample_rate": event.get("sample_rate", 16000),
                "channels": event.get("channels", 1),
            })
        if event_name == "interim":
            return self._with_asr_context({
                "event": "asr_interim",
                "provider": event.get("provider", ""),
                "text": event.get("text", ""),
                "interim": event.get("interim", ""),
            })
        if event_name == "final":
            return self._with_asr_context({
                "event": "asr_final",
                "provider": event.get("provider", ""),
                "text": event.get("text", ""),
                "segment": event.get("segment", ""),
            })
        if event_name == "done":
            return self._with_asr_context({
                "event": "asr_done",
                "provider": event.get("provider", ""),
                "transcript": event.get("transcript", ""),
                "ok": bool(event.get("ok")),
            })
        if event_name == "error":
            return self._with_asr_context({
                "event": "asr_error",
                "status": event.get("status", "error"),
                "error": event.get("error", "ASR failed."),
            })
        return self._with_asr_context({
            "event": "asr_event",
            "provider": event.get("provider", ""),
            "payload": event,
        })

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
