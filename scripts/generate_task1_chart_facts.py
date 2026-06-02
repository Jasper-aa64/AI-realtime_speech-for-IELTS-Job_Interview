#!/usr/bin/env python3
"""Generate Task 1 chart fact sheets for existing writing prompts.

This script is intentionally offline-preprocessing oriented: it reads local
Task 1 prompt images, asks an OpenAI-compatible vision model for structured
facts, and stores the result on WritingPrompt as ai_unverified evidence for
later scoring prompts.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend_django"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from apps.writing.models import WritingPrompt  # noqa: E402


FACT_SCHEMA = {
    "chart_type": "line_graph | bar_chart | table | pie_chart | map | process | mixed | other",
    "overview_hint": "One sentence describing the main overall pattern without over-detail.",
    "main_features": ["3-6 short factual bullets about the most important features."],
    "key_figures": ["Important figures, units, time periods, rankings, or comparisons."],
    "comparisons": ["Explicit highest/lowest/fastest/crossover/major contrast facts."],
    "common_student_traps": ["Likely misreadings or tempting but wrong claims."],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ai_unverified Task 1 chart facts for local writing prompt images.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum prompts to process.")
    parser.add_argument("--prompt-id", action="append", default=[], help="Specific prompt_id to process. Can be repeated.")
    parser.add_argument("--source", default="", help="Filter WritingPrompt.source with icontains, e.g. cambridge.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing non-human chart facts.")
    parser.add_argument("--dry-run", action="store_true", help="Print selected prompts without calling the model or saving.")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=1400)
    return parser.parse_args()


def chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def image_path_for_prompt(prompt: WritingPrompt) -> Path | None:
    image_url = str(prompt.image_url or "").strip()
    if not image_url or image_url.startswith(("http://", "https://")):
        return None
    if image_url.startswith("/"):
        image_url = image_url[1:]
    return REPO_ROOT / "web" / "static" / image_url


def image_data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def extract_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("Vision response did not contain a JSON object")


def normalize_facts(payload: dict[str, Any]) -> dict[str, Any]:
    facts = dict(payload)
    facts.setdefault("chart_type", "other")
    facts.setdefault("overview_hint", "")
    for key in ("main_features", "key_figures", "comparisons", "common_student_traps"):
        value = facts.get(key)
        if isinstance(value, str):
            facts[key] = [value]
        elif not isinstance(value, list):
            facts[key] = []
    facts["facts_source"] = "ai_unverified"
    return facts


def build_prompt(prompt: WritingPrompt) -> str:
    schema = json.dumps(FACT_SCHEMA, ensure_ascii=False, indent=2)
    return f"""You are preparing a fact sheet for IELTS Academic Writing Task 1 scoring.

Return JSON only. Inspect the chart image and the prompt text. Extract only facts visible in the image or stated in the prompt. Do not invent missing values. If exact numbers are hard to read, mark them as approximate with the word "approx".

Required JSON shape:
{schema}

Prompt title:
{prompt.title}

Prompt text:
{prompt.prompt}
"""


def call_vision_model(prompt: WritingPrompt, image_data: str, *, temperature: float, max_tokens: int) -> dict[str, Any]:
    base_url = os.environ.get("AI_HTTP_BASE_URL", "").strip()
    api_key = os.environ.get("AI_HTTP_API_KEY", "").strip()
    model = os.environ.get("AI_VISION_MODEL", "").strip() or os.environ.get("AI_HTTP_MODEL", "").strip()
    if not base_url or not api_key or not model:
        raise RuntimeError("AI_HTTP_BASE_URL, AI_HTTP_API_KEY, and AI_VISION_MODEL or AI_HTTP_MODEL are required")

    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": build_prompt(prompt)},
                    {"type": "image_url", "image_url": {"url": image_data}},
                ],
            }
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    request = urllib.request.Request(
        chat_completions_url(base_url),
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "IELTS-Studio-chart-facts/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Vision provider HTTP {exc.code}: {body_text}") from exc
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Vision provider response missing choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else ""
    if isinstance(content, list):
        content = "\n".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
    return normalize_facts(extract_json_object(str(content or "")))


def selected_prompts(args: argparse.Namespace):
    queryset = WritingPrompt.objects.filter(task_type=WritingPrompt.TaskType.TASK1_ACADEMIC, is_active=True).exclude(image_url="")
    if args.prompt_id:
        queryset = queryset.filter(prompt_id__in=args.prompt_id)
    if args.source:
        queryset = queryset.filter(source__icontains=args.source)
    if not args.overwrite:
        queryset = queryset.filter(chart_facts_status__in=["", "none", "failed"])
    return queryset.order_by("source", "prompt_id")[: max(args.limit, 0)]


def main() -> int:
    args = parse_args()
    processed = 0
    skipped = 0
    failed = 0
    for prompt in selected_prompts(args):
        path = image_path_for_prompt(prompt)
        if not path or not path.exists():
            skipped += 1
            print(f"SKIP {prompt.prompt_id}: local image not found ({prompt.image_url})")
            continue
        print(f"PROMPT {prompt.prompt_id}: {prompt.title} [{path.name}]")
        if args.dry_run:
            processed += 1
            continue
        try:
            facts = call_vision_model(prompt, image_data_url(path), temperature=args.temperature, max_tokens=args.max_tokens)
        except Exception as exc:  # noqa: BLE001 - CLI should continue through bad prompts.
            failed += 1
            print(f"FAIL {prompt.prompt_id}: {exc}")
            WritingPrompt.objects.filter(pk=prompt.pk).update(chart_facts_status="failed")
            continue
        prompt.chart_facts = facts
        prompt.chart_facts_status = "ai_unverified"
        prompt.save(update_fields=["chart_facts", "chart_facts_status", "updated_at"])
        processed += 1
        print(f"OK {prompt.prompt_id}: {facts.get('chart_type')} | {facts.get('overview_hint')}")
    print(json.dumps({"processed": processed, "skipped": skipped, "failed": failed}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
