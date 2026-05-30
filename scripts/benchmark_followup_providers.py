#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend_django"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from apps.ai.http_provider import HttpApiProvider, HttpApiProviderError  # noqa: E402
from apps.speaking.services import quick_follow_up_codex_runner, quick_follow_up_http_runner  # noqa: E402


PROMPTS = [
    (
        "Why do many people prefer living in big cities?",
        "I think cities give people more job opportunities and better public services, although life can be stressful.",
        "cause_effect",
    ),
    (
        "How might education change in the future?",
        "Online learning will probably become more common because it is flexible and can reach students in smaller towns.",
        "future_prediction",
    ),
]


def _measure(label: str, runner, rounds: int) -> dict[str, object]:
    samples: list[float] = []
    failures: list[str] = []
    for index in range(rounds):
        question, answer, question_type = PROMPTS[index % len(PROMPTS)]
        started = time.monotonic()
        try:
            runner(question, answer, question_type)
            samples.append(time.monotonic() - started)
        except Exception as exc:  # noqa: BLE001 - benchmark should report availability
            failures.append(type(exc).__name__)
    if samples:
        sorted_samples = sorted(samples)
        p95_index = min(len(sorted_samples) - 1, int(round((len(sorted_samples) - 1) * 0.95)))
        p50_ms = int(statistics.median(sorted_samples) * 1000)
        p95_ms = int(sorted_samples[p95_index] * 1000)
    else:
        p50_ms = None
        p95_ms = None
    return {
        "provider": label,
        "rounds": rounds,
        "successes": len(samples),
        "failures": len(failures),
        "failure_types": sorted(set(failures)),
        "p50_ms": p50_ms,
        "p95_ms": p95_ms,
    }


def _http_runner(question: str, answer: str, question_type: str) -> None:
    quick_follow_up_http_runner(question, answer, question_type=question_type)


def _codex_runner(question: str, answer: str, question_type: str) -> None:
    quick_follow_up_codex_runner(question, answer, question_type=question_type)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare speaking follow-up provider availability and latency.")
    parser.add_argument("--rounds", type=int, default=2, help="Number of attempts per provider.")
    parser.add_argument("--skip-codex", action="store_true", help="Skip Codex CLI comparison.")
    args = parser.parse_args()

    try:
        HttpApiProvider()
        http_configured = True
    except HttpApiProviderError:
        http_configured = False

    print("Follow-up provider diagnostic")
    print(f"HTTP configured: {'yes' if http_configured else 'no'}")
    print("Secrets: not displayed")

    if http_configured:
        print(_measure("http_api", _http_runner, max(1, args.rounds)))
    else:
        print({"provider": "http_api", "successes": 0, "failures": max(1, args.rounds), "reason": "not_configured"})

    if not args.skip_codex:
        print(_measure("codex_cli", _codex_runner, max(1, args.rounds)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
