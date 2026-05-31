#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend_django"
sys.path.insert(0, str(BACKEND))


def _set_env_if_absent(name: str, value: str | None) -> None:
    if value and not os.environ.get(name):
        os.environ[name] = value


def _usage_total(usage: dict[str, Any] | None) -> int:
    if not isinstance(usage, dict):
        return 0
    total = 0
    for key in ("total_tokens", "prompt_tokens", "completion_tokens", "input_tokens", "output_tokens"):
        value = usage.get(key)
        if isinstance(value, (int, float)):
            total += int(value)
    return total


def _compact_usage(usage: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {}
    allowed = ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens")
    return {key: usage[key] for key in allowed if key in usage}


def _case_result(
    name: str,
    *,
    backend: str,
    provider: str = "",
    model: str = "",
    latency_ms: int | str | None = None,
    usage: dict[str, Any] | None = None,
    text: str = "",
) -> dict[str, Any]:
    usage_summary = _compact_usage(usage)
    passed = backend in {"http_api", "http_api_stream"} and provider == "openai_compatible_http" and _usage_total(usage) > 0
    return {
        "case": name,
        "ok": passed,
        "backend": backend,
        "provider": provider,
        "model": model,
        "latency_ms": int(latency_ms or 0),
        "usage": usage_summary,
        "preview": str(text or "")[:160],
    }


def _error_result(name: str, exc: Exception) -> dict[str, Any]:
    return {
        "case": name,
        "ok": False,
        "backend": "error",
        "provider": "",
        "model": "",
        "latency_ms": 0,
        "usage": {},
        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
    }


def _run_case(name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - diagnostic script must keep running all cases
        return _error_result(name, exc)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that speaking follow-up/report/coaching routes use the OpenAI-compatible HTTP "
            "provider with real usage tokens instead of fallback."
        )
    )
    parser.add_argument(
        "--cases",
        default="quick",
        choices=("quick", "all", "p1", "p3", "p3-from-p2", "stream", "report", "band7"),
        help="quick=p1,p3,stream. all also runs report and Band 7/coaching, which costs more tokens.",
    )
    parser.add_argument("--model", default="", help="Optional SPEAKING_AI_MODEL override, e.g. gpt-5.4-mini.")
    parser.add_argument("--mode", default="http", choices=("http", "chain", "codex", "fallback"), help="Speaking AI route.")
    parser.add_argument("--json", action="store_true", help="Emit compact JSON only.")
    args = parser.parse_args()

    _set_env_if_absent("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ["SPEAKING_AI_CALL_MODE"] = args.mode
    if args.model:
        os.environ["SPEAKING_AI_MODEL"] = args.model

    import django  # noqa: PLC0415

    django.setup()

    from apps.speaking import services  # noqa: PLC0415

    config_error = ""
    try:
        provider = services._speaking_http_provider("followup")  # noqa: SLF001
        configured_model = provider.config.model
    except Exception as exc:  # noqa: BLE001 - report missing env without exposing secrets
        config_error = str(exc)
        configured_model = os.environ.get("SPEAKING_AI_MODEL") or os.environ.get("AI_HTTP_MODEL") or "gpt-5.4-mini"

    requested: list[str]
    if args.cases == "quick":
        requested = ["p1", "p3", "stream"]
    elif args.cases == "all":
        requested = ["p1", "p3", "p3-from-p2", "stream", "report", "band7"]
    else:
        requested = [args.cases]

    p1_answer = (
        "I'm a university student majoring in software engineering, and I am also doing an internship "
        "at a technology company where I work on small programming tasks."
    )
    p3_question = "How might education change in the future?"
    p3_answer = (
        "I think online learning will become more common because it is flexible and can reach students "
        "in smaller cities, but schools still need teachers to guide discussion."
    )

    def p1_case() -> dict[str, Any]:
        result = services._generate_p1_identity_follow_up(p1_answer, "live_route_p1")  # noqa: SLF001
        return _case_result(
            "p1",
            backend=str(result.get("backend") or ""),
            provider=str(result.get("provider") or ""),
            model=str(result.get("model") or ""),
            latency_ms=result.get("latency_ms"),
            usage=result.get("usage") if isinstance(result.get("usage"), dict) else {},
            text=str(result.get("follow_up") or ""),
        )

    def p3_case() -> dict[str, Any]:
        result = services.quick_follow_up_runner_with_metadata(
            p3_question,
            p3_answer,
            focus="answer development",
            question_type="future_prediction",
        )
        return _case_result(
            "p3",
            backend=str(result.get("backend") or ""),
            provider=str(result.get("provider") or ""),
            model=str(result.get("model") or ""),
            latency_ms=result.get("latency_ms"),
            usage=result.get("usage") if isinstance(result.get("usage"), dict) else {},
            text=str(result.get("follow_up") or ""),
        )

    def p3_from_p2_case() -> dict[str, Any]:
        result = services._generate_p3_from_p2_answer(  # noqa: SLF001
            "Describe a book you have recently read",
            "I recently read a cultural travel book about Chengdu. I enjoyed it because it described tea houses, food, and the slower pace of city life.",
            "live_route_p3_from_p2",
        )
        return _case_result(
            "p3-from-p2",
            backend=str(result.get("backend") or ""),
            provider="openai_compatible_http" if result.get("backend") == "http_api" else "",
            model=str(result.get("model") or ""),
            latency_ms=0,
            usage=result.get("usage") if isinstance(result.get("usage"), dict) else {},
            text=" | ".join([*(result.get("questions") or [])[:1], str(result.get("follow_up") or "")]),
        )

    def stream_case() -> dict[str, Any]:
        usage: dict[str, Any] = {}
        started = time.monotonic()
        prompt = services._quick_follow_up_prompt(  # noqa: SLF001
            p3_question,
            p3_answer,
            focus="answer development",
            question_type="future_prediction",
        )
        provider = services._speaking_http_provider("followup", timeout_seconds=12)  # noqa: SLF001
        chunks = list(
            provider.stream_tokens(
                [
                    {"role": "system", "content": "You are an IELTS Speaking examiner. Return only one concise follow-up question."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=80,
                temperature=0.2,
                timeout_seconds=12,
                on_usage=lambda value: usage.update(value),
            )
        )
        text = services._extract_single_follow_up_question("".join(chunks), rejected_questions=(p3_question,))  # noqa: SLF001
        return _case_result(
            "stream",
            backend="http_api_stream",
            provider="openai_compatible_http",
            model=services.speaking_ai_http_model("followup"),
            latency_ms=int((time.monotonic() - started) * 1000),
            usage=usage,
            text=text,
        )

    def report_case() -> dict[str, Any]:
        result = services.score_with_codex(
            "Q: Do you work or do you study?\nA: I study software engineering at university and do an internship at a technology company.",
            "Do you work or do you study?",
            "p1",
            "live_route_report",
        )
        return _case_result(
            "report",
            backend=str(result.get("backend") or ""),
            provider="openai_compatible_http" if result.get("backend") == "http_api" else "",
            model=str(result.get("model") or ""),
            latency_ms=0,
            usage=result.get("billing_usage") if isinstance(result.get("billing_usage"), dict) else {},
            text=str(result.get("feedback") or result.get("overall_review") or ""),
        )

    def band7_case() -> dict[str, Any]:
        result = services.turn_feedback_with_codex(
            "Do you work or do you study?",
            "I study software engineering at university and I am doing an internship at a technology company.",
            "p1",
            "7",
            {},
            "live_route_band7",
            requires_ai_coaching=True,
        )
        return _case_result(
            "band7",
            backend="http_api" if _usage_total(result.get("usage")) > 0 else "",
            provider="openai_compatible_http" if _usage_total(result.get("usage")) > 0 else "",
            model=services.speaking_ai_http_model("report"),
            latency_ms=0,
            usage=result.get("usage") if isinstance(result.get("usage"), dict) else {},
            text=str(result.get("band7_version") or ""),
        )

    registry: dict[str, Callable[[], dict[str, Any]]] = {
        "p1": p1_case,
        "p3": p3_case,
        "p3-from-p2": p3_from_p2_case,
        "stream": stream_case,
        "report": report_case,
        "band7": band7_case,
    }
    results = [_run_case(name, registry[name]) for name in requested]
    summary = {
        "http_configured": not bool(config_error),
        "config_error": config_error,
        "mode": args.mode,
        "model": configured_model,
        "cases": results,
        "ok": all(item.get("ok") for item in results),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("Speaking AI route validation")
        print(f"HTTP configured: {'yes' if summary['http_configured'] else 'no'}")
        print(f"Mode: {args.mode}")
        print(f"Model: {configured_model or '(missing)'}")
        print("Secrets: not displayed")
        if config_error:
            print(f"Config error: {config_error}")
        for item in results:
            status = "PASS" if item.get("ok") else "FAIL"
            usage = item.get("usage") or {}
            print(
                f"{status} {item['case']}: backend={item.get('backend') or '-'} "
                f"provider={item.get('provider') or '-'} model={item.get('model') or '-'} "
                f"latency_ms={item.get('latency_ms') or 0} usage={usage} preview={item.get('preview') or ''}"
            )
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
