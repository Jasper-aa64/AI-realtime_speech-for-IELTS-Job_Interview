#!/usr/bin/env python3
"""Evaluate writing prompt search quality against real local IELTS bank data."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend_django"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.test import RequestFactory  # noqa: E402
from django.test.utils import override_settings  # noqa: E402

from apps.writing.services import agent_find_writing_prompts  # noqa: E402


SEARCH_CASES = [
    {"query": "水 浪费 免费", "task_type": "task2", "expected": "cambridge-20-test-1-task-2", "top_n": 3},
    {"query": "免费 供水", "task_type": "task2", "expected": "cambridge-20-test-1-task-2", "top_n": 3},
    {"query": "浪费 回收 垃圾", "task_type": "task2", "expected": "cambridge-11-test-2-task-2", "top_n": 3},
    {"query": "剑雅20 水", "task_type": "", "expected": "cambridge-20-test-1-task-2", "top_n": 3},
    {"query": "museums free charge", "task_type": "task2", "expected": "cambridge-10-test-4-task-2", "top_n": 3},
    {"query": "博物馆 免费 收费", "task_type": "task2", "expected": "cambridge-10-test-4-task-2", "top_n": 5},
    {"query": "musem free admision charge", "task_type": "task2", "expected": "cambridge-10-test-4-task-2", "top_n": 5},
    {"query": "人口 图表", "task_type": "task1_academic", "expected_prompt_contains": "population", "top_n": 3},
    {"query": "孩子 互联网 老师 学校", "task_type": "task2", "expected": "reported-cn-task2-2015-05-30-20", "top_n": 5},
    {"query": "fresh water government control", "task_type": "task2", "expected": "reported-cn-task2-2023-02-04-4", "top_n": 5},
    {"query": "computer Internet children teachers", "task_type": "task2", "expected": "reported-cn-task2-2015-05-30-20", "top_n": 5},
    {"query": "交通 汽车 道路", "task_type": "task2", "expected_prompt_contains": "traffic", "top_n": 5},
    {"query": "健康 医生 医院", "task_type": "task2", "expected_prompt_contains": "health", "top_n": 5},
    {"query": "工作 薪水 公司", "task_type": "task2", "expected_prompt_contains": "work", "top_n": 5},
    {"query": "fresh water goverment controll", "task_type": "task2", "expected": "reported-cn-task2-2023-02-04-4", "top_n": 5},
]


def case_passed(case: dict, items: list[dict]) -> bool:
    ids = [str(item.get("id") or "") for item in items]
    expected = str(case.get("expected") or "")
    if expected and expected in ids:
        return True
    expected_prompt_contains = str(case.get("expected_prompt_contains") or "").lower()
    if expected_prompt_contains:
        return any(expected_prompt_contains in str(item.get("prompt") or "").lower() for item in items)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate writing prompt search quality and latency.")
    parser.add_argument("--repeat", type=int, default=1, help="Repeat all cases for latency sampling.")
    parser.add_argument("--max-avg-ms", type=float, default=120.0, help="Fail when average query latency is above this threshold.")
    parser.add_argument("--warmup", action="store_true", help="Warm caches before measuring repeated cases.")
    args = parser.parse_args()

    request = RequestFactory().get("/api/agent/writing/prompts/search", HTTP_HOST="127.0.0.1:8082")
    rows: list[dict] = []
    passed = 0
    total = len(SEARCH_CASES)
    repeated_cases = SEARCH_CASES * max(1, args.repeat)

    with override_settings(ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"]):
        if args.warmup:
            for case in SEARCH_CASES:
                agent_find_writing_prompts(case["query"], request, task_type=case["task_type"], limit=case["top_n"])

        started = time.perf_counter()
        first_run_payloads: list[tuple[dict, dict]] = []
        for index, case in enumerate(repeated_cases):
            payload = agent_find_writing_prompts(case["query"], request, task_type=case["task_type"], limit=case["top_n"])
            if index < len(SEARCH_CASES):
                first_run_payloads.append((case, payload))
        elapsed_ms = (time.perf_counter() - started) * 1000

    for case, payload in first_run_payloads:
        items = payload.get("items") if isinstance(payload, dict) else []
        items = items if isinstance(items, list) else []
        ok = case_passed(case, items)
        passed += int(ok)
        top = items[0] if items else {}
        rows.append({
            "query": case["query"],
            "ok": ok,
            "top_ids": [item.get("id") for item in items[:3]],
            "top_score": top.get("match_score", 0),
            "top_type": top.get("match_type", "none"),
            "top_concepts": top.get("matched_concepts", []),
        })

    avg_ms = elapsed_ms / len(repeated_cases)
    print(f"passed={passed}/{total} elapsed_ms={elapsed_ms:.1f} avg_ms={avg_ms:.1f} repeat={args.repeat} warmup={args.warmup}")
    for row in rows:
        status = "PASS" if row["ok"] else "FAIL"
        print(f"{status} query={row['query']!r} top_ids={row['top_ids']} score={row['top_score']} type={row['top_type']} concepts={row['top_concepts']}")
    if passed != total:
        return 1
    if avg_ms > args.max_avg_ms:
        print(f"FAIL avg_ms {avg_ms:.1f} exceeds threshold {args.max_avg_ms:.1f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
