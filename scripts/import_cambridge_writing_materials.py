#!/usr/bin/env python3
"""Import authorized Cambridge IELTS writing materials.

This tool prepares user-provided materials for the existing writing prompt
loader. It does not download copyrighted content and does not remove
watermarks. It only normalizes local files the user has the right to use.

Input JSON format:

{
  "materials": [
    {
      "id": "cambridge-20-test-1-task-1",
      "task_type": "task1_academic",
      "book": 20,
      "test": 1,
      "source_question": 1,
      "title": "Cambridge IELTS 20 Test 1 Task 1",
      "category": "line_graph",
      "prompt": "The chart below ...",
      "image_path": "images/c20_t1_task1.png"
    }
  ]
}
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "ielts" / "writing"
STATIC_DIR = ROOT / "web" / "static"
MANIFEST_PATH = DATA_DIR / "cambridge" / "cambridge_1_20_manifest.json"


TASK1 = "task1_academic"
TASK2 = "task2"
VALID_TASK_TYPES = {TASK1, TASK2}
VALID_TASK1_CATEGORIES = {"line_graph", "bar_chart", "pie_chart", "table", "map", "process", "mixed"}
VALID_TASK2_CATEGORIES = {"opinion", "discussion", "problem_solution", "advantages_disadvantages", "two_part"}


class ImportErrorWithContext(ValueError):
    pass


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def normalize_task_type(value: Any) -> str:
    task_type = str(value or "").strip().lower()
    aliases = {
        "task1": TASK1,
        "task_1": TASK1,
        "task 1": TASK1,
        "task1academic": TASK1,
        "task 1 academic": TASK1,
        "task2": TASK2,
        "task_2": TASK2,
        "task 2": TASK2,
    }
    task_type = aliases.get(task_type, task_type)
    if task_type not in VALID_TASK_TYPES:
        raise ImportErrorWithContext(f"Invalid task_type: {value!r}")
    return task_type


def positive_int(value: Any, field: str) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ImportErrorWithContext(f"{field} must be a positive integer") from exc
    if number <= 0:
        raise ImportErrorWithContext(f"{field} must be a positive integer")
    return number


def load_manifest_slots() -> set[str]:
    payload = load_json(MANIFEST_PATH)
    slots = payload.get("slots") if isinstance(payload, dict) else []
    return {str(item.get("id") or "").strip() for item in slots if isinstance(item, dict)}


def load_manifest_items() -> list[dict[str, Any]]:
    payload = load_json(MANIFEST_PATH)
    slots = payload.get("slots") if isinstance(payload, dict) else []
    if not isinstance(slots, list):
        raise ImportErrorWithContext("Cambridge manifest must contain a slots array")
    return [item for item in slots if isinstance(item, dict)]


def relative_to_input(path_value: Any, input_path: Path) -> Path:
    raw = Path(str(path_value or "").strip())
    if raw.is_absolute():
        return raw
    return (input_path.parent / raw).resolve()


def safe_prompt_id(item: dict[str, Any]) -> str:
    prompt_id = str(item.get("id") or "").strip()
    if prompt_id:
        return prompt_id
    book = positive_int(item.get("book") or item.get("source_book"), "book")
    test = positive_int(item.get("test") or item.get("source_test"), "test")
    task_type = normalize_task_type(item.get("task_type"))
    source_question = positive_int(item.get("source_question") or (1 if task_type == TASK1 else 2), "source_question")
    return f"cambridge-{book}-test-{test}-task-{source_question}"


def validate_item(raw_item: Any, input_path: Path, manifest_ids: set[str]) -> dict[str, Any]:
    if not isinstance(raw_item, dict):
        raise ImportErrorWithContext("Each material item must be an object")

    task_type = normalize_task_type(raw_item.get("task_type"))
    prompt_id = safe_prompt_id(raw_item)
    if prompt_id not in manifest_ids:
        raise ImportErrorWithContext(f"{prompt_id} is not present in Cambridge 1-20 manifest")

    book = positive_int(raw_item.get("book") or raw_item.get("source_book"), "book")
    test = positive_int(raw_item.get("test") or raw_item.get("source_test"), "test")
    source_question = positive_int(raw_item.get("source_question") or (1 if task_type == TASK1 else 2), "source_question")
    prompt = str(raw_item.get("prompt") or raw_item.get("question") or "").strip()
    if not prompt:
        raise ImportErrorWithContext(f"{prompt_id} is missing prompt text")

    category = str(raw_item.get("category") or "").strip().lower()
    valid_categories = VALID_TASK1_CATEGORIES if task_type == TASK1 else VALID_TASK2_CATEGORIES
    if category and category not in valid_categories:
        raise ImportErrorWithContext(f"{prompt_id} has unsupported category: {category}")

    image_path = None
    if task_type == TASK1:
        image_path = relative_to_input(raw_item.get("image_path"), input_path)
        if not image_path.exists():
            raise ImportErrorWithContext(f"{prompt_id} image not found: {image_path}")

    return {
        "id": prompt_id,
        "task_type": task_type,
        "book": book,
        "test": test,
        "source_question": source_question,
        "title": str(raw_item.get("title") or f"Cambridge IELTS {book} Test {test} Task {source_question}").strip(),
        "category": category,
        "prompt": prompt,
        "image_path": str(image_path) if image_path else "",
    }


def process_image(source: Path, destination: Path, enhance: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not enhance:
        shutil.copyfile(source, destination)
        return

    try:
        from PIL import Image, ImageOps, ImageFilter
    except Exception:
        shutil.copyfile(source, destination)
        return

    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = ImageOps.contain(image, (1800, 1200))
        image = ImageOps.autocontrast(image, cutoff=1)
        image = image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))
        image.save(destination, optimize=True)


def imported_image_url(book: int, test: int, source_question: int, source: Path) -> tuple[str, Path]:
    suffix = source.suffix.lower() if source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} else ".png"
    file_name = f"test_{test}_task_{source_question}{suffix}"
    asset_path = Path("assets") / "writing" / "task1" / "cambridge" / str(book) / file_name
    return "/" + asset_path.as_posix(), STATIC_DIR / asset_path


def grouped_output_path(task_type: str, book: int) -> Path:
    return DATA_DIR / "cambridge" / task_type / f"cambridge_{book}.json"


def imported_prompt_ids() -> set[str]:
    ids: set[str] = set()
    for task_type in VALID_TASK_TYPES:
        prompt_dir = DATA_DIR / "cambridge" / task_type
        if not prompt_dir.exists():
            continue
        for path in prompt_dir.rglob("*.json"):
            payload = load_json(path)
            raw_items = payload.get("prompts") if isinstance(payload, dict) else payload
            if not isinstance(raw_items, list):
                continue
            for item in raw_items:
                if isinstance(item, dict) and item.get("id"):
                    ids.add(str(item["id"]).strip())
    return ids


def print_manifest_report() -> int:
    slots = load_manifest_items()
    imported_ids = imported_prompt_ids()
    counts: Counter[tuple[str, str]] = Counter()
    missing_by_book: Counter[int] = Counter()
    for slot in slots:
        slot_id = str(slot.get("id") or "").strip()
        task_type = normalize_task_type(slot.get("task_type"))
        status = "imported" if slot_id in imported_ids else "missing"
        counts[(task_type, status)] += 1
        if status == "missing":
            book = positive_int(slot.get("source_book"), "source_book")
            missing_by_book[book] += 1

    total = len(slots)
    imported = len(imported_ids & {str(slot.get("id") or "").strip() for slot in slots})
    print(f"Cambridge IELTS Writing manifest: {imported}/{total} slots imported")
    for task_type in sorted(VALID_TASK_TYPES):
        print(
            f"- {task_type}: "
            f"{counts[(task_type, 'imported')]} imported, "
            f"{counts[(task_type, 'missing')]} missing"
        )
    if missing_by_book:
        books = ", ".join(f"{book}:{missing_by_book[book]}" for book in sorted(missing_by_book, reverse=True))
        print(f"Missing slots by book: {books}")
    return 0


def build_outputs(items: list[dict[str, Any]], enhance_images: bool) -> list[Path]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    written: list[Path] = []
    for item in items:
        prompt = {
            "id": item["id"],
            "title": item["title"],
            "category": item["category"],
            "source_book": item["book"],
            "source_test": item["test"],
            "source_question": item["source_question"],
            "prompt": item["prompt"],
        }
        if item["task_type"] == TASK1:
            source_image = Path(item["image_path"])
            image_url, destination = imported_image_url(
                item["book"],
                item["test"],
                item["source_question"],
                source_image,
            )
            process_image(source_image, destination, enhance_images)
            prompt["image_url"] = image_url
            written.append(destination)
        grouped[(item["task_type"], item["book"])].append(prompt)

    for (task_type, book), prompts in grouped.items():
        prompts.sort(key=lambda prompt: (prompt["source_test"], prompt["source_question"], prompt["id"]))
        payload = {
            "task_type": task_type,
            "source": "cambridge_ielts_authorized_import",
            "book": book,
            "prompts": prompts,
        }
        output_path = grouped_output_path(task_type, book)
        write_json(output_path, payload)
        written.append(output_path)
    return written


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import authorized Cambridge IELTS Writing materials.")
    parser.add_argument("input", type=Path, nargs="?", help="Input JSON with a materials array.")
    parser.add_argument("--manifest-report", action="store_true", help="Print imported/missing counts for Cambridge 1-20 slots.")
    parser.add_argument("--no-enhance", action="store_true", help="Copy Task 1 images without contrast/sharpness normalization.")
    parser.add_argument("--dry-run", action="store_true", help="Validate only; do not write files.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.manifest_report:
        return print_manifest_report()
    if not args.input:
        raise ImportErrorWithContext("Input JSON is required unless --manifest-report is used")
    input_path = args.input.resolve()
    payload = load_json(input_path)
    raw_items = payload.get("materials") if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        raise ImportErrorWithContext("Input JSON must be a list or an object with a materials array")

    manifest_ids = load_manifest_slots()
    items = [validate_item(item, input_path, manifest_ids) for item in raw_items]
    if args.dry_run:
        print(f"Validated {len(items)} material item(s).")
        return 0

    written = build_outputs(items, enhance_images=not args.no_enhance)
    print(f"Imported {len(items)} material item(s).")
    for path in written:
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImportErrorWithContext as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
