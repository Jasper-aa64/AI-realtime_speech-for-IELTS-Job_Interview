#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend_django"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from asgiref.sync import async_to_sync  # noqa: E402
from channels.testing import WebsocketCommunicator  # noqa: E402
from django.test.utils import override_settings  # noqa: E402

REQUIRED_EVENTS = {"connected", "asr_started", "pcm_ack", "asr_interim", "asr_final", "asr_done"}
TRANSCRIPT_FRAGMENT = "software engineering"


def _pcm_frame(seed: int, samples: int = 160) -> bytes:
    high = seed & 0xFF
    low = (seed * 3) & 0xFF
    return bytes([high, low]) * samples


def _safe_event(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if key not in {"headers", "access_key", "app_key"}}


def _assert_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    event_names = [str(event.get("event") or "") for event in events]
    missing = sorted(REQUIRED_EVENTS - set(event_names))
    if missing:
        raise AssertionError(f"missing events: {missing}; saw={event_names}")

    providers = {
        str(event.get("provider") or "")
        for event in events
        if str(event.get("event") or "").startswith("asr_") and event.get("provider")
    }
    if providers != {"fake_realtime_asr"}:
        raise AssertionError(f"unexpected providers: {sorted(providers)}")

    final_text = " ".join(
        str(event.get("text") or event.get("transcript") or "")
        for event in events
        if event.get("event") in {"asr_final", "asr_done"}
    )
    if TRANSCRIPT_FRAGMENT not in final_text:
        raise AssertionError(f"fake transcript did not include {TRANSCRIPT_FRAGMENT!r}: {final_text!r}")

    context_events = [event for event in events if event.get("turn_context")]
    if not context_events:
        raise AssertionError("turn_context was not echoed back by the ASR stream")

    return {
        "events": event_names,
        "providers": sorted(providers),
        "transcript": final_text.strip(),
        "context": context_events[-1].get("turn_context"),
    }


async def _run_inprocess() -> list[dict[str, Any]]:
    from config.asgi import application

    communicator = WebsocketCommunicator(
        application,
        "/ws/realtime/pcm/",
        headers=[
            (b"host", b"testserver"),
            (b"origin", b"http://testserver"),
        ],
    )
    connected, _subprotocol = await communicator.connect()
    if not connected:
        raise AssertionError("in-process websocket did not connect")

    events: list[dict[str, Any]] = []
    try:
        events.append(await communicator.receive_json_from())
        await communicator.send_json_to({
            "event": "start_asr",
            "attempt_id": "fake-drill-attempt",
            "turn_id": "fake-drill-turn",
            "stream_follow_up": True,
            "fake_asr": True,
        })

        await _receive_until(communicator, events, {"asr_started"})
        await communicator.send_to(bytes_data=_pcm_frame(1))
        await _receive_until(communicator, events, {"pcm_ack", "asr_interim"})
        await communicator.send_to(bytes_data=_pcm_frame(2))
        await _receive_until(communicator, events, {"pcm_ack", "asr_final"})
        await communicator.send_json_to({"event": "stop_asr"})
        await _receive_until(communicator, events, {"asr_done", "asr_stopped"})
    finally:
        await communicator.disconnect()
    return events


async def _receive_until(
    communicator: WebsocketCommunicator,
    events: list[dict[str, Any]],
    required_events: set[str],
    limit: int = 12,
) -> None:
    required = set(required_events)
    for _ in range(limit):
        event = await communicator.receive_json_from()
        events.append(event)
        required.discard(str(event.get("event") or ""))
        if not required:
            return
    raise AssertionError(f"did not receive {sorted(required)}; saw={[event.get('event') for event in events]}")


def _run_live(url: str) -> list[dict[str, Any]]:
    try:
        import websocket  # type: ignore
    except ImportError as exc:
        raise RuntimeError("websocket-client is required for --url live validation") from exc

    for key in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        os.environ.pop(key, None)
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

    ws = websocket.create_connection(url, timeout=5, origin="http://127.0.0.1:8767")
    events: list[dict[str, Any]] = []
    try:
        events.append(json.loads(ws.recv()))
        ws.send(json.dumps({
            "event": "start_asr",
            "attempt_id": "fake-drill-attempt",
            "turn_id": "fake-drill-turn",
            "stream_follow_up": True,
            "fake_asr": True,
        }))
        _live_receive_until(ws, events, {"asr_started"})
        ws.send_binary(_pcm_frame(1))
        _live_receive_until(ws, events, {"pcm_ack", "asr_interim"})
        ws.send_binary(_pcm_frame(2))
        _live_receive_until(ws, events, {"pcm_ack", "asr_final"})
        ws.send(json.dumps({"event": "stop_asr"}))
        _live_receive_until(ws, events, {"asr_done", "asr_stopped"})
    finally:
        ws.close()
    return events


def _live_receive_until(ws: Any, events: list[dict[str, Any]], required_events: set[str], limit: int = 12) -> None:
    required = set(required_events)
    for _ in range(limit):
        event = json.loads(ws.recv())
        events.append(event)
        required.discard(str(event.get("event") or ""))
        if not required:
            return
    raise AssertionError(f"did not receive {sorted(required)}; saw={[event.get('event') for event in events]}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the DEBUG-only fake realtime ASR WebSocket drill without real ASR credentials."
    )
    parser.add_argument(
        "--url",
        help="Optional live WebSocket URL, e.g. ws://127.0.0.1:8767/ws/realtime/pcm/. Omit for in-process ASGI.",
    )
    parser.add_argument("--json", action="store_true", help="Print only the final JSON summary.")
    args = parser.parse_args()

    try:
        if args.url:
            events = _run_live(args.url)
        else:
            with override_settings(DEBUG=True, ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"]):
                events = async_to_sync(_run_inprocess)()
        summary = _assert_summary(events)
    except Exception as exc:  # noqa: BLE001 - this is a diagnostic CLI
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 1

    payload = {"ok": True, "mode": "live" if args.url else "inprocess", **summary}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print("Fake realtime ASR drill passed")
        for event in events:
            print(json.dumps(_safe_event(event), ensure_ascii=False, sort_keys=True))
        print(json.dumps({"summary": payload}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
