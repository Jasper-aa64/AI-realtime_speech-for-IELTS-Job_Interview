#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
import time
import wave
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend_django"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from apps.speaking.volcengine_asr import realtime_asr_status, stream_pcm_chunks  # noqa: E402


EXIT_NOT_CONFIGURED = 78


def _read_pcm16_mono_16k(path: Path) -> bytes:
    if path.suffix.lower() == ".pcm":
        return path.read_bytes()
    if path.suffix.lower() != ".wav":
        raise ValueError("audio file must be .pcm or 16kHz mono PCM16 .wav")
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getframerate() != 16000:
            raise ValueError("wav input must be 16kHz mono PCM16")
        return source.readframes(source.getnframes())


def _tone_pcm(duration_seconds: float, sample_rate: int = 16000) -> bytes:
    sample_count = max(1, int(sample_rate * duration_seconds))
    amplitude = 8000
    frequency = 440
    return b"".join(
        struct.pack("<h", int(amplitude * math.sin(2 * math.pi * frequency * index / sample_rate)))
        for index in range(sample_count)
    )


def _chunks(payload: bytes, chunk_ms: int, sample_rate: int = 16000) -> Iterable[bytes]:
    bytes_per_sample = 2
    chunk_size = max(bytes_per_sample, int(sample_rate * chunk_ms / 1000) * bytes_per_sample)
    for index in range(0, len(payload), chunk_size):
        yield payload[index:index + chunk_size]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the realtime VolcEngine ASR provider without printing secrets."
    )
    parser.add_argument("--audio", type=Path, help="Optional 16kHz mono PCM16 .pcm or .wav sample to stream.")
    parser.add_argument("--duration-seconds", type=float, default=1.0, help="Generated tone duration when --audio is omitted.")
    parser.add_argument("--chunk-ms", type=int, default=20, help="PCM chunk size in milliseconds.")
    parser.add_argument("--timeout-seconds", type=int, default=10, help="Provider timeout for this validation run.")
    parser.add_argument("--require-transcript", action="store_true", help="Fail if the provider connects but returns no transcript.")
    args = parser.parse_args()

    status = realtime_asr_status()
    print("Realtime ASR provider diagnostic")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    if not status.get("configured"):
        print("Realtime ASR is not configured; set VOLCENGINE_ASR_* env vars or VOLCENGINE_ASR_CONFIG_PATH.")
        return EXIT_NOT_CONFIGURED

    try:
        pcm = _read_pcm16_mono_16k(args.audio) if args.audio else _tone_pcm(args.duration_seconds)
    except Exception as exc:  # noqa: BLE001 - CLI diagnostic should print the validation problem
        print(f"Invalid audio sample: {exc}")
        return 2

    started = time.monotonic()
    events: list[dict] = []
    try:
        for event in stream_pcm_chunks(
            _chunks(pcm, args.chunk_ms),
            chunk_delay_seconds=0,
            receive_timeout_seconds=0.02,
            timeout_seconds=args.timeout_seconds,
        ):
            safe_event = {key: value for key, value in event.items() if key not in {"headers", "access_key", "app_key"}}
            events.append(safe_event)
            print(json.dumps(safe_event, ensure_ascii=False, sort_keys=True))
    except Exception as exc:  # noqa: BLE001 - CLI diagnostic should surface provider failures
        print(json.dumps({"event": "validation_error", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 1

    elapsed_ms = int((time.monotonic() - started) * 1000)
    transcript = " ".join(str(event.get("transcript") or event.get("text") or "") for event in events if event.get("event") in {"final", "done"}).strip()
    summary = {
        "elapsed_ms": elapsed_ms,
        "events": len(events),
        "has_started": any(event.get("event") == "started" for event in events),
        "has_final": any(event.get("event") == "final" for event in events),
        "has_done": any(event.get("event") == "done" for event in events),
        "transcript": transcript,
    }
    print(json.dumps({"summary": summary}, ensure_ascii=False, sort_keys=True))
    if args.require_transcript and not transcript:
        return 3
    return 0 if summary["has_started"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
