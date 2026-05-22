#!/usr/bin/env python3
"""Import publicly visible Cambridge IELTS writing references.

This fills the app's existing Cambridge writing bank from pages that already
publish a Cambridge book/test/task reference. It preserves source attribution
and downloaded Task 1 images as published.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
import urllib.parse
from html import unescape
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "ielts" / "writing" / "cambridge"
STATIC_DIR = ROOT / "web" / "static"

TASK1 = "task1_academic"
TASK2 = "task2"
SOURCE = "cambridge_ielts_public_reference"
BASE_URL = "https://engnovate.com/ielts-writing-tests/cambridge-ielts-{book}-academic-writing-test-{test}-task-{task}/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


TASK1_CATEGORIES = {
    "map": "map",
    "maps": "map",
    "plan": "map",
    "plans": "map",
    "diagram": "process",
    "process": "process",
    "table and charts": "mixed",
    "table and chart": "mixed",
    "table": "table",
    "pie charts": "pie_chart",
    "pie chart": "pie_chart",
    "bar chart": "bar_chart",
    "bar charts": "bar_chart",
    "chart": "bar_chart",
    "charts": "mixed",
    "line graph": "line_graph",
    "graph": "line_graph",
}


def fetch(url: str, retries: int = 4) -> bytes:
    last_error: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(safe_url(url), headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 429 or attempt == retries - 1:
                raise
            time.sleep(6 + attempt * 4)
        except Exception as exc:
            last_error = exc
            if attempt == retries - 1:
                raise
            time.sleep(2 + attempt)
    raise RuntimeError(f"Unable to fetch {url}: {last_error}")


def safe_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%")
    query = urllib.parse.quote(parts.query, safe="=&%")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def clean_text(value: str) -> str:
    value = unescape(value)
    value = value.replace("Summarize", "Summarise")
    value = re.sub(r"\s+", " ", value)
    value = value.replace(" .", ".").strip()
    return value


def html_text(html: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return clean_text(text)


def extract_task1_prompt(text: str) -> str:
    start_match = re.search(
        r"\bThe (?:first |second |third |following )?(?:chart|charts|graph|graphs|table|tables|diagram|diagrams|plans|maps|map|picture|pictures)\b",
        text,
        flags=re.I,
    )
    if not start_match:
        raise ValueError("Task 1 prompt start not found")
    tail = text[start_match.start() :]
    end_match = re.search(
        r"Summari[sz]e the information by selecting and reporting the main features,? and make comparisons where relevant\.",
        tail,
        flags=re.I,
    )
    if not end_match:
        raise ValueError("Task 1 prompt end not found")
    return clean_text(tail[: end_match.end()])


def extract_task2_prompt(text: str) -> str:
    match = re.search(
        r"You should spend about 40 minutes on this task\. Write at least 250 words\. (?P<prompt>.*?)(?: Samples\b| Words: 0\b| More Samples\b)",
        text,
        flags=re.I,
    )
    if not match:
        raise ValueError("Task 2 prompt not found")
    suffix = "Give reasons for your answer and include any relevant examples from your own knowledge or experience."
    prompt = clean_text(match.group("prompt"))
    prompt = re.sub(r"^(?:You should spend about 40 minutes on this task\.\s*)+", "", prompt, flags=re.I)
    prompt = re.sub(r"^(?:Write at least 250 words\.\s*)+", "", prompt, flags=re.I)
    prompt = re.sub(r"^(?:Write about the following topic:\s*)+", "", prompt, flags=re.I)
    if prompt.lower().startswith(suffix.lower()):
        prompt = clean_text(prompt[len(suffix) :])
    if suffix.lower() not in prompt.lower():
        prompt = f"{prompt} {suffix}"
    return clean_text(prompt)


def extract_task1_image(html: str) -> str:
    for tag in re.findall(r"<img[^>]+>", html, flags=re.I):
        if "ielts-writing-image" not in tag:
            continue
        match = re.search(r"\bsrc=[\"']([^\"']+)[\"']", tag, flags=re.I)
        if match:
            return unescape(match.group(1))
    raise ValueError("Task 1 image not found")


def task1_category(prompt: str) -> str:
    lower = prompt.lower()
    for key, category in TASK1_CATEGORIES.items():
        if key in lower:
            return category
    return "mixed"


def task2_category(prompt: str) -> str:
    lower = prompt.lower()
    if "discuss both these views" in lower:
        return "discussion"
    if "advantages" in lower and "disadvantages" in lower:
        return "advantages_disadvantages"
    if "why" in lower and ("positive or negative" in lower or "what" in lower):
        return "two_part"
    if "what are" in lower or "why is" in lower:
        return "two_part"
    if "problem" in lower or "solution" in lower:
        return "problem_solution"
    return "opinion"


def output_path(task_type: str, book: int) -> Path:
    return DATA_DIR / task_type / f"cambridge_{book}.json"


def image_output(book: int, test: int, image_url: str) -> tuple[str, Path]:
    suffix = Path(image_url.split("?", 1)[0]).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        suffix = ".png"
    rel = Path("assets") / "writing" / "task1" / "cambridge" / str(book) / f"test_{test}_task_1{suffix}"
    return "/" + rel.as_posix(), STATIC_DIR / rel


def source_label(book: int, test: int, task: int) -> str:
    return f"剑雅{book}-{test} Task {task}"


def sort_order(book: int, test: int) -> int:
    return (21 - book) * 10 + test


def scrape_item(book: int, test: int, task: int, download_images: bool) -> dict[str, Any]:
    url = BASE_URL.format(book=book, test=test, task=task)
    html = fetch(url).decode("utf-8", "replace")
    text = html_text(html)
    task_type = TASK1 if task == 1 else TASK2
    prompt = extract_task1_prompt(text) if task == 1 else extract_task2_prompt(text)
    item: dict[str, Any] = {
        "id": f"cambridge-{book}-test-{test}-task-{task}",
        "title": f"Cambridge IELTS {book} Test {test} Task {task}",
        "category": task1_category(prompt) if task == 1 else task2_category(prompt),
        "source_book": book,
        "source_test": test,
        "source_question": task,
        "source_label": source_label(book, test, task),
        "prompt": prompt,
        "source": SOURCE,
        "source_url": url,
        "sort_order": sort_order(book, test),
    }
    if task == 1:
        image_url = extract_task1_image(html)
        local_url, local_path = image_output(book, test, image_url)
        if download_images:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(fetch(image_url))
        item["image_url"] = local_url
        item["source_image_url"] = image_url
    return item


def write_book(task_type: str, book: int, prompts: list[dict[str, Any]]) -> None:
    prompts.sort(key=lambda item: item["source_test"])
    payload = {
        "task_type": task_type,
        "source": SOURCE,
        "source_url": "https://engnovate.com/ielts-writing-tests/",
        "license_note": "Publicly visible Cambridge IELTS writing reference pages imported with source attribution for local study use; images are preserved as published, without watermark removal.",
        "book": book,
        "prompts": prompts,
    }
    path = output_path(task_type, book)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books", nargs="+", type=int, default=[20, 19, 18, 17, 16, 15])
    parser.add_argument("--delay", type=float, default=1.2)
    parser.add_argument("--no-images", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for book in args.books:
        grouped = {TASK1: [], TASK2: []}
        for test in range(1, 5):
            for task in (1, 2):
                try:
                    item = scrape_item(book, test, task, download_images=not args.no_images)
                    grouped[TASK1 if task == 1 else TASK2].append(item)
                    print(f"imported {item['id']}")
                except Exception as exc:
                    print(f"failed cambridge-{book}-test-{test}-task-{task}: {exc}")
                time.sleep(args.delay)
        for task_type, prompts in grouped.items():
            if prompts:
                write_book(task_type, book, prompts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
