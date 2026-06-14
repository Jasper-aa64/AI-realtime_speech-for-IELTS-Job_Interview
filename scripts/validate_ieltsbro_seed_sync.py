#!/usr/bin/env python3
"""Validate source-backed IELTSBro seed question-bank sync requirements."""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


SOURCE_DOC = REPO_ROOT / "data/ielts/SOURCES.md"
SOURCE_PDF = REPO_ROOT / "data/ielts/sources/2026_may_august_ielts_speaking_bank_0604.pdf"
SOURCE_TEXT = REPO_ROOT / "data/ielts/sources/2026_may_august_ielts_speaking_bank_0604.txt"
ARCHIVE_BUCKET = REPO_ROOT / "data/ielts/archive/old_topics.json"
OPTIONAL_FIRECRAWL_FILES = [
    REPO_ROOT / ".firecrawl/ieltsbro-api/getDataV2-latest-1.json",
    REPO_ROOT / ".firecrawl/ieltsbro-api/question-pics/008_new_or_current_P1_Headphones_320210901180829.jpg",
    REPO_ROOT / ".firecrawl/ieltsbro-api/question-pics/010_new_or_current_P1_Clothing_320230909101428.jpg",
    REPO_ROOT / ".firecrawl/ieltsbro-api/question-pics/030_new_or_current_P2P3_想颁布的新法律_320240417155859.jpg",
    REPO_ROOT / ".firecrawl/ieltsbro-api/question-pics/032_new_or_current_P2P3_早起经历_320210901143903.jpg",
]

# Minimum question depth every current-season P1 topic must reach. The 2026-06-14
# multi-source merge (idictation 神奇题库 base + distinct PDF/public-list top-ups)
# exists precisely to give every topic real depth, so this is the core invariant.
P1_MIN_TOPIC_DEPTH = 4

# Stable anchor questions that must remain present in the named new-topic cards.
# These survive the multi-source merge, so they are checked as a subset (must
# contain), not as an exact ordered list.
EXPECTED_P1_NEW_ANCHORS = {
    "headphones": [
        "Do you use headphones?",
        "Is wearing headphones comfortable?",
    ],
    "clothes": [
        "What kind of clothes do you like to wear?",
        "Do you like wearing T-shirts?",
    ],
}

# Pinned post-merge per-topic counts in the file (regression guard). Source of
# truth is the data file; update these together when the seed bank changes.
EXPECTED_P1_NEW_COUNTS = {
    "boring_things": 8,
    "history": 4,
    "mirrors": 4,
    "outer_space_and_stars": 5,
    "singing": 8,
    "tidiness": 7,
    "watches": 4,
    "public_gardens_and_parks": 8,
    "websites": 7,
    "ambition_and_dreams": 4,
    "social_media": 5,
    "cinema": 7,
    "headphones": 6,
    "old_buildings": 4,
    "evening_time": 6,
    "cars": 6,
    "shopping": 7,
    "clothes": 6,
    "jokes": 5,
    "art": 4,
    "sports_programs": 6,
    "morning_routines": 4,
    "science": 6,
    "teachers": 6,
    "music": 6,
    "daily_routine": 5,
}

EXPECTED_P1_RETAINED_COUNTS = {
    "food": 4,
    "pets_and_animals": 7,
    "sports_team": 4,
    "hobby": 4,
    "morning_time": 5,
    "gifts": 5,
    "reading": 4,
    "walking": 5,
    "typing": 4,
    "scenery": 4,
    "building": 4,
    "childhood_activities": 4,
    "views": 4,
    "life_stages": 6,
    "free_time": 4,
    "memory": 4,
    "crowded_places": 6,
    "study_or_work": 18,
    "home_and_accommodation": 18,
    "hometown": 12,
    "the_area_you_live_in": 8,
    "the_city_you_live_in": 8,
}

# The Django loader globally de-duplicates the "How long have you lived there?"
# question shared across the three "where you live" topics, keeping the first
# occurrence, so two location topics load one fewer item than the file holds.
EXPECTED_P1_RETAINED_LOADER_COUNTS = {
    **EXPECTED_P1_RETAINED_COUNTS,
    "hometown": 11,
    "the_area_you_live_in": 7,
}

# Questions that legitimately recur across the three "where you live" topics in the
# idictation (神奇题库) current-season bank — each topic genuinely asks it.
EXPECTED_P1_RETAINED_DUPLICATES = {
    ("home_and_accommodation", "How long have you lived there?"),
    ("hometown", "How long have you lived there?"),
    ("the_area_you_live_in", "How long have you lived there?"),
}

EXPECTED_P2_FOLLOW_UPS = {
    "Describe a time when you got up early": [
        "Do you know anyone who likes to get up early?",
        "Why do people get up early?",
        "What kinds of occasions need people to arrive early?",
        "Why do some people like to stay up late?",
        "Is it good to arrive early in any situation?",
        "What kind of people like getting up early?",
    ],
    "Describe a new law you would like to introduce in your country": [
        "What rules should students follow at school?",
        "Do people in your country usually obey the law?",
        "What kinds of behavior are considered as good behavior?",
        "Do you think children can learn about the law outside of school?",
        "What are the benefits for people to obey rules?",
        "How can parents teach children to obey rules?",
    ],
}


def read_json(relative_path: str) -> dict:
    with (REPO_ROOT / relative_path).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise AssertionError(f"{relative_path} must contain a JSON object")
    return payload


def assert_source_cache_present() -> None:
    missing = [str(path) for path in (SOURCE_DOC, SOURCE_PDF, SOURCE_TEXT) if not path.is_file()]
    if missing:
        raise AssertionError(f"Missing tracked source files: {missing}")
    source_doc = SOURCE_DOC.read_text(encoding="utf-8")
    for marker in (
        "2026_may_august_ielts_speaking_bank_0604.pdf",
        "p1Update 2026-05-22",
        "p23Update 2026-06-10",
        "Firecrawl quota was insufficient",
    ):
        if marker not in source_doc:
            raise AssertionError(f"SOURCES.md is missing provenance marker: {marker!r}")
    optional_missing = [str(path) for path in OPTIONAL_FIRECRAWL_FILES if not path.is_file()]
    if optional_missing:
        print(f"Optional IELTSBro cache files are absent on this clone: {optional_missing}")


def assert_json_files_valid() -> None:
    for relative_path in (
        "data/ielts/part1/2026_may_august_new_topics.json",
        "data/ielts/part1/2026_may_august_retained_topics.json",
        "data/ielts/part2/2026_may_august_topics.json",
        "data/ielts/archive/old_topics.json",
    ):
        read_json(relative_path)


def assert_no_empty_or_duplicate_seed_items() -> None:
    p1_paths = (
        "data/ielts/part1/2026_may_august_new_topics.json",
        "data/ielts/part1/2026_may_august_retained_topics.json",
    )
    for relative_path in p1_paths:
        payload = read_json(relative_path)
        items = payload.get("questions")
        if not isinstance(items, list):
            raise AssertionError(f"{relative_path} questions must be a list")
        keys: list[tuple[str, str]] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise AssertionError(f"{relative_path} question #{index + 1} must be an object")
            topic = str(item.get("topic") or "").strip()
            question = str(item.get("question") or "").strip()
            if not topic or not question:
                raise AssertionError(f"{relative_path} question #{index + 1} has empty topic/question")
            keys.append((topic, question))
        duplicates = [key for key, count in Counter(keys).items() if count > 1]
        if relative_path == "data/ielts/part1/2026_may_august_retained_topics.json":
            duplicate_keys = {
                key
                for key, count in Counter(question for _, question in keys).items()
                if count > 1
            }
            actual_duplicate_rows = {key for key in keys if key[1] in duplicate_keys}
            if actual_duplicate_rows != EXPECTED_P1_RETAINED_DUPLICATES:
                raise AssertionError(f"{relative_path} has unexpected PDF duplicate rows: {actual_duplicate_rows}")
            duplicates = [key for key in duplicates if key not in EXPECTED_P1_RETAINED_DUPLICATES]
        if duplicates:
            raise AssertionError(f"{relative_path} has duplicate P1 questions: {duplicates}")

    p2_path = "data/ielts/part2/2026_may_august_topics.json"
    p2 = read_json(p2_path)
    topics = p2.get("topics")
    if not isinstance(topics, list):
        raise AssertionError(f"{p2_path} topics must be a list")
    titles: list[str] = []
    for index, item in enumerate(topics):
        if not isinstance(item, dict):
            raise AssertionError(f"{p2_path} topic #{index + 1} must be an object")
        title = str(item.get("title") or "").strip()
        if not title:
            raise AssertionError(f"{p2_path} topic #{index + 1} has an empty title")
        follow_ups = item.get("p3_follow_ups")
        if not isinstance(follow_ups, list) or not all(str(question or "").strip() for question in follow_ups):
            raise AssertionError(f"{p2_path} topic {title!r} has invalid P3 follow-ups")
        titles.append(title)
    duplicate_titles = [title for title, count in Counter(titles).items() if count > 1]
    if duplicate_titles:
        raise AssertionError(f"{p2_path} has duplicate P2 titles: {duplicate_titles}")

    archive = read_json("data/ielts/archive/old_topics.json")
    archived_questions = archive.get("questions")
    if not isinstance(archived_questions, list):
        raise AssertionError("data/ielts/archive/old_topics.json questions must be a list")
    archive_keys: list[tuple[str, str]] = []
    for index, item in enumerate(archived_questions):
        if not isinstance(item, dict):
            raise AssertionError(f"data/ielts/archive/old_topics.json question #{index + 1} must be an object")
        topic = str(item.get("topic") or "").strip()
        question = str(item.get("question") or "").strip()
        if not topic or not question:
            raise AssertionError(f"data/ielts/archive/old_topics.json question #{index + 1} has empty topic/question")
        archive_keys.append((topic, question))
    archive_duplicates = [key for key, count in Counter(archive_keys).items() if count > 1]
    if archive_duplicates:
        raise AssertionError(f"data/ielts/archive/old_topics.json has duplicate archived questions: {archive_duplicates}")


def assert_seed_requirements() -> None:
    p1_new = read_json("data/ielts/part1/2026_may_august_new_topics.json")
    by_topic: dict[str, list[str]] = defaultdict(list)
    for item in p1_new.get("questions") or []:
        if isinstance(item, dict):
            by_topic[str(item.get("topic") or "")].append(str(item.get("question") or ""))

    for topic, anchors in EXPECTED_P1_NEW_ANCHORS.items():
        questions = {question for question in by_topic[topic] if question}
        missing = [anchor for anchor in anchors if anchor not in questions]
        if missing:
            raise AssertionError(f"P1 new {topic} is missing anchor questions: {missing}")

    new_counts = {topic: len(questions) for topic, questions in by_topic.items()}
    if new_counts != EXPECTED_P1_NEW_COUNTS:
        raise AssertionError(f"P1 new topic counts drifted from pinned merge: {new_counts}")
    for topic, count in new_counts.items():
        if count < P1_MIN_TOPIC_DEPTH:
            raise AssertionError(f"P1 new topic {topic} has only {count} questions (min {P1_MIN_TOPIC_DEPTH})")

    p1_retained = read_json("data/ielts/part1/2026_may_august_retained_topics.json")
    retained_by_topic: dict[str, list[str]] = defaultdict(list)
    for item in p1_retained.get("questions") or []:
        if not isinstance(item, dict):
            raise AssertionError("P1 retained questions must be objects")
        topic = str(item.get("topic") or "").strip()
        question = str(item.get("question") or "").strip()
        if not topic or not question:
            raise AssertionError(f"P1 retained item has empty topic/question: {item}")
        retained_by_topic[topic].append(question)
    retained_counts = {topic: len(questions) for topic, questions in retained_by_topic.items()}
    if retained_counts != EXPECTED_P1_RETAINED_COUNTS:
        raise AssertionError(f"P1 retained topic counts drifted from pinned merge: {retained_counts}")
    for topic, count in retained_counts.items():
        if count < P1_MIN_TOPIC_DEPTH:
            raise AssertionError(f"P1 retained topic {topic} has only {count} questions (min {P1_MIN_TOPIC_DEPTH})")

    p2 = read_json("data/ielts/part2/2026_may_august_topics.json")
    by_title = {
        str(item.get("title") or ""): item
        for item in p2.get("topics") or []
        if isinstance(item, dict)
    }
    for title, expected_follow_ups in EXPECTED_P2_FOLLOW_UPS.items():
        topic = by_title.get(title)
        if not topic:
            raise AssertionError(f"Missing P2 topic: {title}")
        follow_ups = topic.get("p3_follow_ups")
        if not isinstance(follow_ups, list):
            raise AssertionError(f"{title} p3_follow_ups must be a list")
        if follow_ups != expected_follow_ups:
            raise AssertionError(f"{title} P3 follow-ups differ from IELTSBro source card: {follow_ups}")

    archive = read_json("data/ielts/archive/old_topics.json")
    if archive.get("status") != "archive":
        raise AssertionError("Archive bucket must be marked as archive")
    if archive.get("topic") != "legacy_mixed_part1":
        raise AssertionError("Archive bucket topic marker changed unexpectedly")


def assert_django_loader() -> None:
    sys.path.insert(0, str(REPO_ROOT / "backend_django"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()

    from apps.speaking.corpus_services import QuestionBank

    bank = QuestionBank()
    p1_new_topics: dict[str, int] = defaultdict(int)
    for item in bank.part1_for_scope("new"):
        p1_new_topics[str(item.get("topic") or "")] += 1
    for topic, expected_count in EXPECTED_P1_NEW_COUNTS.items():
        if p1_new_topics[topic] != expected_count:
            raise AssertionError(f"Django loader sees P1 new {topic} count {p1_new_topics[topic]}, expected {expected_count}")

    p1_retained_topics: dict[str, int] = defaultdict(int)
    for item in bank.part1_for_scope("retained"):
        p1_retained_topics[str(item.get("topic") or "")] += 1
    for topic, expected_count in EXPECTED_P1_RETAINED_LOADER_COUNTS.items():
        if p1_retained_topics[topic] != expected_count:
            raise AssertionError(f"Django loader sees P1 retained {topic} count {p1_retained_topics[topic]}, expected {expected_count}")

    p2_by_title = {str(item.get("title") or ""): item for item in bank.part2_for_scope("current")}
    for title, expected_follow_ups in EXPECTED_P2_FOLLOW_UPS.items():
        expected_count = len(expected_follow_ups)
        follow_ups = p2_by_title.get(title, {}).get("p3_follow_ups") or []
        if len(follow_ups) != expected_count:
            raise AssertionError(f"Django loader sees {title} P3 count {len(follow_ups)}, expected {expected_count}")

    if any(item.get("season") == "archive" for item in bank.part1_for_scope("current")):
        raise AssertionError("Archive seed content leaked into current question bank")


def main() -> int:
    assert_source_cache_present()
    assert_json_files_valid()
    assert_no_empty_or_duplicate_seed_items()
    assert_seed_requirements()
    assert_django_loader()
    print("IELTSBro seed sync validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
