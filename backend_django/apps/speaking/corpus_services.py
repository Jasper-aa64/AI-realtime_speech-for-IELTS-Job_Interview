"""Speaking question-bank, corpus, and Takeaway services.

This module owns learner-managed speaking materials and phrase takeaways.
`apps.speaking.services` re-exports these functions for existing views/tests
while runtime attempts, scoring, reports, and TTS remain in narrower modules or
the compatibility facade.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .exceptions import SpeakingError
from .models import (
    ExpressionReplacementEntry,
    LanguageTakeawayEntry,
    P1CorpusEntry,
    P2BankCorpusEntry,
    P2CorpusEntry,
    P3BankFollowupCorpusEntry,
    SpeakingTurn,
    TakeawayReviewState,
)
from .text_utils import clean_markdown_text, clean_report_text


P1_INTRO_QUESTIONS: list[dict[str, Any]] = [
    {
        "topic": "intro",
        "question": "What is your full name?",
        "flow": "intro",
        "role": "name",
        "counts_toward_total": False,
    },
    {
        "topic": "intro",
        "question": "Do you work or do you study?",
        "flow": "intro",
        "role": "work_study",
        "counts_toward_total": True,
    },
]


CURRENT_SPEAKING_SEASON = "2026-may-august"
CURRENT_SPEAKING_REGION = "china_mainland"
QUESTION_BANK_SCOPE_CURRENT = "current"
QUESTION_BANK_SCOPE_NEW = "new"
QUESTION_BANK_SCOPE_RETAINED = "retained"
QUESTION_BANK_SCOPE_ARCHIVE = "archive"
QUESTION_BANK_SCOPE_ALL = "all"
QUESTION_BANK_SCOPE_LABELS = {
    QUESTION_BANK_SCOPE_CURRENT: "当前考季",
    QUESTION_BANK_SCOPE_NEW: "新题",
    QUESTION_BANK_SCOPE_RETAINED: "保留题",
    QUESTION_BANK_SCOPE_ARCHIVE: "历史考季",
    QUESTION_BANK_SCOPE_ALL: "全部题库",
}


def normalize_question_bank_scope(scope: str | None) -> str:
    value = str(scope or "").strip().lower().replace("-", "_")
    aliases = {
        "current_season": QUESTION_BANK_SCOPE_CURRENT,
        "current_season_only": QUESTION_BANK_SCOPE_CURRENT,
        "season": QUESTION_BANK_SCOPE_CURRENT,
        "all_current": QUESTION_BANK_SCOPE_CURRENT,
        "new_questions": QUESTION_BANK_SCOPE_NEW,
        "retained_questions": QUESTION_BANK_SCOPE_RETAINED,
        "archive_bank": QUESTION_BANK_SCOPE_ARCHIVE,
        "archived": QUESTION_BANK_SCOPE_ARCHIVE,
        "history": QUESTION_BANK_SCOPE_ARCHIVE,
        "historical": QUESTION_BANK_SCOPE_ARCHIVE,
        "old": QUESTION_BANK_SCOPE_ARCHIVE,
        "all": QUESTION_BANK_SCOPE_ALL,
        "full": QUESTION_BANK_SCOPE_ALL,
        "all_bank": QUESTION_BANK_SCOPE_ALL,
        "all_questions": QUESTION_BANK_SCOPE_ALL,
    }
    value = aliases.get(value, value)
    if value in QUESTION_BANK_SCOPE_LABELS:
        return value
    return QUESTION_BANK_SCOPE_CURRENT


class QuestionBank:
    """Load IELTS speaking questions from JSON files."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or Path(settings.BASE_DIR).parent / "data" / "ielts"
        self.all_p1: list[dict[str, Any]] = []
        self.all_p2: list[dict[str, Any]] = []
        self.p1: list[dict[str, Any]] = []
        self.p2: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        self.all_p1 = self._load_p1()
        self.all_p2 = self._load_p2()
        self.p1 = self._current_season_items(self.all_p1)
        self.p2 = self._current_season_items(self.all_p2)

    def _current_season_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        current = [
            item
            for item in items
            if str(item.get("season") or "") == CURRENT_SPEAKING_SEASON
        ]
        return current or items

    def _load_p1(self) -> list[dict[str, Any]]:
        part_dir = self.data_dir / "part1"
        if not part_dir.is_dir():
            return []
        questions: list[dict[str, Any]] = []
        for path in sorted(part_dir.glob("*.json")):
            payload = self._read_json(path)
            if payload.get("part") != 1:
                continue
            items = payload.get("questions")
            if not isinstance(items, list):
                continue
            file_topic = str(payload.get("topic") or path.stem)
            file_meta = {
                "season": str(payload.get("season") or ""),
                "status": str(payload.get("status") or ""),
                "region": str(payload.get("region") or ""),
                "source": str(payload.get("source") or ""),
                "source_url": str(payload.get("source_url") or ""),
            }
            for item in items:
                topic = file_topic
                meta = dict(file_meta)
                question = ""
                if isinstance(item, str):
                    question = item.strip()
                elif isinstance(item, dict):
                    question = str(item.get("question") or item.get("text") or "").strip()
                    topic = str(item.get("topic") or topic)
                    for key in ("season", "status", "region", "source", "source_url"):
                        if item.get(key):
                            meta[key] = str(item[key])
                if question:
                    questions.append({
                        "topic": topic,
                        "question": question,
                        "question_id": p1_question_id(topic, question),
                        "legacy_question_id": legacy_p1_question_id(topic, question),
                        **{key: value for key, value in meta.items() if value},
                    })
        return questions

    def _load_p2(self) -> list[dict[str, Any]]:
        part_dir = self.data_dir / "part2"
        if not part_dir.is_dir():
            return []
        topics: list[dict[str, Any]] = []
        for path in sorted(part_dir.glob("*.json")):
            payload = self._read_json(path)
            if payload.get("part") != 2:
                continue
            items = payload.get("topics")
            if not isinstance(items, list):
                continue
            file_meta = {
                "season": str(payload.get("season") or ""),
                "status": str(payload.get("status") or ""),
                "region": str(payload.get("region") or ""),
                "source": str(payload.get("source") or ""),
                "source_url": str(payload.get("source_url") or ""),
            }
            for item in items:
                if isinstance(item, dict) and item.get("title"):
                    topic = dict(item)
                    for key, value in file_meta.items():
                        topic.setdefault(key, value)
                    topic["cue_id"] = p2_cue_id(topic)
                    topic["canonical_entry_id"] = p2_canonical_entry_id(topic)
                    topics.append(topic)
        return topics

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _items_for_scope(self, items: list[dict[str, Any]], scope: str | None = None) -> list[dict[str, Any]]:
        normalized = normalize_question_bank_scope(scope)
        if normalized == QUESTION_BANK_SCOPE_ALL:
            selected = list(items)
        elif normalized == QUESTION_BANK_SCOPE_ARCHIVE:
            selected = [
                item
                for item in items
                if str(item.get("season") or "") != CURRENT_SPEAKING_SEASON
            ]
        else:
            selected = [
                item
                for item in items
                if str(item.get("season") or "") == CURRENT_SPEAKING_SEASON
            ]
            if normalized in {QUESTION_BANK_SCOPE_NEW, QUESTION_BANK_SCOPE_RETAINED}:
                selected = [
                    item
                    for item in selected
                    if str(item.get("status") or "").lower() == normalized
                ]
        return self._dedupe_scope_items(selected)

    def _dedupe_scope_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for item in items:
            key = str(item.get("question_id") or item.get("cue_id") or item.get("title") or item.get("question") or "")
            if not key:
                continue
            existing = deduped.get(key)
            if not existing:
                deduped[key] = item
                continue
            if str(existing.get("season") or "") != CURRENT_SPEAKING_SEASON and str(item.get("season") or "") == CURRENT_SPEAKING_SEASON:
                deduped[key] = item
        return list(deduped.values())

    def part1_for_scope(self, scope: str | None = None) -> list[dict[str, Any]]:
        selected = self._items_for_scope(self.all_p1, scope)
        if normalize_question_bank_scope(scope) == QUESTION_BANK_SCOPE_CURRENT and not selected:
            return self.all_p1
        return selected

    def part2_for_scope(self, scope: str | None = None) -> list[dict[str, Any]]:
        selected = self._items_for_scope(self.all_p2, scope)
        if normalize_question_bank_scope(scope) == QUESTION_BANK_SCOPE_CURRENT and not selected:
            return self.all_p2
        return selected

    def scope_options(self) -> list[dict[str, Any]]:
        return [
            {
                "scope": scope,
                "label": QUESTION_BANK_SCOPE_LABELS[scope],
                "part1_count": len(self.part1_for_scope(scope)),
                "part2_count": len(self.part2_for_scope(scope)),
            }
            for scope in (
                QUESTION_BANK_SCOPE_CURRENT,
                QUESTION_BANK_SCOPE_NEW,
                QUESTION_BANK_SCOPE_RETAINED,
                QUESTION_BANK_SCOPE_ARCHIVE,
                QUESTION_BANK_SCOPE_ALL,
            )
        ]

    def summary(self, scope: str | None = None) -> dict[str, Any]:
        normalized_scope = normalize_question_bank_scope(scope)
        selected_p1 = self.part1_for_scope(normalized_scope)
        selected_p2 = self.part2_for_scope(normalized_scope)
        p1_status_counts: dict[str, int] = {}
        for item in selected_p1:
            status = str(item.get("status") or "seed")
            p1_status_counts[status] = p1_status_counts.get(status, 0) + 1
        p2_status_counts: dict[str, int] = {}
        for item in selected_p2:
            status = str(item.get("status") or "seed")
            p2_status_counts[status] = p2_status_counts.get(status, 0) + 1
        archived_p1 = [
            item
            for item in self.all_p1
            if str(item.get("season") or "") != CURRENT_SPEAKING_SEASON
        ]
        archived_p2 = [
            item
            for item in self.all_p2
            if str(item.get("season") or "") != CURRENT_SPEAKING_SEASON
        ]
        p3_follow_up_count = sum(
            len(item.get("p3_follow_ups") or [])
            for item in selected_p2
            if isinstance(item.get("p3_follow_ups"), list)
        )
        return {
            "active_season": CURRENT_SPEAKING_SEASON,
            "active_region": CURRENT_SPEAKING_REGION,
            "active_scope": normalized_scope,
            "active_scope_label": QUESTION_BANK_SCOPE_LABELS[normalized_scope],
            "scope": "current_season_only" if normalized_scope == QUESTION_BANK_SCOPE_CURRENT else normalized_scope,
            "part3_mode": "derived_from_part2",
            "part3_follow_up_count": p3_follow_up_count,
            "part1_count": len(selected_p1),
            "part2_count": len(selected_p2),
            "part1_total_count": len(self.all_p1),
            "part2_total_count": len(self.all_p2),
            "archived_part1_count": len(archived_p1),
            "archived_part2_count": len(archived_p2),
            "part1_topics": sorted({item["topic"] for item in selected_p1}),
            "part2_themes": sorted({item.get("p3_theme", "") for item in selected_p2 if item.get("p3_theme")}),
            "part1_status_counts": p1_status_counts,
            "part2_status_counts": p2_status_counts,
            "bank_scope_options": self.scope_options(),
            "seasons": sorted({str(item.get("season") or "") for item in [*self.all_p1, *self.all_p2] if item.get("season")}),
            "regions": sorted({str(item.get("region") or "") for item in [*self.all_p1, *self.all_p2] if item.get("region")}),
        }

    def sample(self, p1_count: int = 5, scope: str | None = None) -> dict[str, Any]:
        p1_pool = self.part1_for_scope(scope)
        p2_pool = self.part2_for_scope(scope)
        p1_count = max(1, min(p1_count, len(p1_pool)))
        result = {}
        if p1_pool:
            result["part1"] = random.sample(p1_pool, p1_count)
        if p2_pool:
            result["part2"] = random.choice(p2_pool)
        result["active_scope"] = normalize_question_bank_scope(scope)
        return result


_question_bank: QuestionBank | None = None


def get_question_bank() -> QuestionBank:
    global _question_bank
    if _question_bank is None:
        _question_bank = QuestionBank()
    return _question_bank


def question_bank_summary(scope: str | None = None) -> dict[str, Any]:
    return get_question_bank().summary(scope)


def question_bank_sample(p1_count: int = 5, scope: str | None = None) -> dict[str, Any]:
    return get_question_bank().sample(p1_count, scope)


def stable_question_text(value: str) -> str:
    text = clean_report_text(str(value or "")).lower()
    text = re.sub(r"[\u2018\u2019\u201c\u201d\"'`]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def legacy_p1_question_id(topic: str, question: str) -> str:
    topic_key = re.sub(r"[^a-z0-9]+", "_", str(topic or "general").lower()).strip("_") or "general"
    digest = hashlib.md5(f"{topic_key}\n{str(question or '').strip()}".encode("utf-8")).hexdigest()[:12]
    return f"p1:{topic_key}:{digest}"


def p1_question_id(topic: str, question: str) -> str:
    normalized = stable_question_text(question)
    digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]
    return f"p1q:{digest}"


def p1_topic_label(topic: str) -> str:
    return str(topic or "general").replace("_", " ").strip().title()


def p1_corpus_library(user, scope: str | None = None) -> dict[str, Any]:
    bank = get_question_bank()
    normalized_scope = normalize_question_bank_scope(scope)
    entries = {
        entry.question_id: entry
        for entry in P1CorpusEntry.objects.filter(user=user)
    }
    grouped: dict[str, dict[str, Any]] = {}

    def add_question(topic: str, question: str, meta: dict[str, Any] | None = None) -> None:
        meta = meta or {}
        question_id = p1_question_id(topic, question)
        legacy_question_id = legacy_p1_question_id(topic, question)
        entry = entries.get(question_id) or entries.get(legacy_question_id)
        group = grouped.setdefault(
            topic,
            {
                "topic": topic,
                "label": p1_topic_label(topic),
                "questions": [],
            },
        )
        group["questions"].append(
            {
                "question_id": question_id,
                "legacy_question_id": legacy_question_id,
                "storage_question_id": question_id,
                "topic": topic,
                "question": question,
                "corpus_text": entry.corpus_text if entry else "",
                "last_ai_answer": entry.last_ai_answer if entry else "",
                "updated_at": timezone.localtime(entry.updated_at).strftime("%Y-%m-%d %H:%M") if entry else "",
                **{key: meta[key] for key in ("season", "status", "region", "source", "source_url") if meta.get(key)},
            }
        )

    for item in P1_INTRO_QUESTIONS:
        add_question(str(item.get("topic") or "intro"), str(item.get("question") or ""))
    for item in bank.part1_for_scope(normalized_scope):
        add_question(str(item.get("topic") or "general"), str(item.get("question") or ""), item)

    topics = sorted(grouped.values(), key=lambda item: (item["topic"] != "intro", item["label"]))
    total_questions = sum(len(topic["questions"]) for topic in topics)
    saved_count = sum(1 for topic in topics for question in topic["questions"] if question.get("corpus_text"))
    return {
        "topics": topics,
        "topic_count": len(topics),
        "question_count": total_questions,
        "saved_count": saved_count,
        "active_season": CURRENT_SPEAKING_SEASON,
        "active_region": CURRENT_SPEAKING_REGION,
        "active_scope": normalized_scope,
        "active_scope_label": QUESTION_BANK_SCOPE_LABELS[normalized_scope],
        "scope": "current_season_only" if normalized_scope == QUESTION_BANK_SCOPE_CURRENT else normalized_scope,
    }


def save_p1_corpus(user, payload: dict[str, Any]) -> dict[str, Any]:
    topic = clean_report_text(str(payload.get("topic") or "general")) or "general"
    question = clean_report_text(str(payload.get("question") or ""))
    if not question:
        raise SpeakingError("Missing P1 question.")
    submitted_question_id = clean_report_text(str(payload.get("question_id") or ""))
    question_id = p1_question_id(topic, question)
    corpus_text = clean_markdown_text(str(payload.get("corpus_text") or ""))[:8000]
    has_last_ai_answer = "last_ai_answer" in payload
    last_ai_answer = clean_markdown_text(str(payload.get("last_ai_answer") or ""))[:8000] if has_last_ai_answer else None
    entry = P1CorpusEntry.objects.filter(user=user, question_id=question_id).first()
    if not entry and submitted_question_id and submitted_question_id != question_id:
        submitted_entry = P1CorpusEntry.objects.filter(user=user, question_id=submitted_question_id).first()
        if submitted_entry and stable_question_text(submitted_entry.question) == stable_question_text(question):
            entry = submitted_entry
            if not P1CorpusEntry.objects.filter(user=user, question_id=question_id).exists():
                entry.question_id = question_id
    if not entry:
        entry = P1CorpusEntry(user=user, question_id=question_id)
    entry.topic = topic
    entry.question = question
    entry.corpus_text = corpus_text
    if has_last_ai_answer:
        entry.last_ai_answer = last_ai_answer or ""
    if not corpus_text.strip():
        entry.last_ai_answer = ""
    entry.metadata = {
        "saved_from": clean_report_text(str(payload.get("source") or "p1_corpus")),
        "legacy_question_id": submitted_question_id if submitted_question_id and submitted_question_id != question_id else "",
    }
    entry.save()
    return {
        "question_id": entry.question_id,
        "topic": entry.topic,
        "question": entry.question,
        "corpus_text": entry.corpus_text,
        "last_ai_answer": entry.last_ai_answer,
        "updated_at": timezone.localtime(entry.updated_at).strftime("%Y-%m-%d %H:%M"),
    }


P2_CORPUS_CATEGORIES = [
    {"category": P2CorpusEntry.Category.PERSON, "label": "人物"},
    {"category": P2CorpusEntry.Category.PLACE, "label": "地点"},
    {"category": P2CorpusEntry.Category.EVENT, "label": "事件"},
    {"category": P2CorpusEntry.Category.OBJECT, "label": "物品"},
    {"category": P2CorpusEntry.Category.SPECIAL, "label": "特殊题目素材"},
]


def p2_topic_category(topic: dict[str, Any]) -> str:
    title = str(topic.get("title") or "").lower()
    theme = str(topic.get("p3_theme") or "").lower()
    text = f"{title} {theme}"
    if any(word in text for word in ("person", "friend", "family member", "old person", "sportsperson", "business person")):
        return P2CorpusEntry.Category.PERSON
    if any(word in text for word in ("place", "building", "city", "mall", "shop", "store", "park", "natural", "country")):
        return P2CorpusEntry.Category.PLACE
    if any(word in text for word in ("item", "thing", "object", "book", "technology", "toy", "website", "app", "food")):
        return P2CorpusEntry.Category.OBJECT
    if any(word in text for word in ("time", "occasion", "activity", "trip", "journey", "event", "decision", "promise", "advice")):
        return P2CorpusEntry.Category.EVENT
    return P2CorpusEntry.Category.SPECIAL


def p2_current_topic_categories(topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = {
        item["category"]: {
            "category": item["category"],
            "label": item["label"],
            "topic_count": 0,
        }
        for item in P2_CORPUS_CATEGORIES
    }
    for topic in topics:
        category = p2_topic_category(topic)
        grouped.setdefault(category, {"category": category, "label": str(category), "topic_count": 0})
        grouped[category]["topic_count"] += 1
    return list(grouped.values())


def p2_category_label(category: str) -> str:
    for item in P2_CORPUS_CATEGORIES:
        if item["category"] == category:
            return item["label"]
    return str(category or P2CorpusEntry.Category.SPECIAL)


def p2_cue_identity_text(topic: dict[str, Any]) -> str:
    title = clean_report_text(str(topic.get("title") or ""))
    bullets = [clean_report_text(str(item)) for item in topic.get("bullets") or [] if clean_report_text(str(item))]
    rounding = clean_report_text(str(topic.get("rounding") or ""))
    return "\n".join([title, *bullets, rounding]).strip()


def p2_cue_id(topic: dict[str, Any]) -> str:
    normalized = stable_question_text(p2_cue_identity_text(topic))
    digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]
    return f"p2cue:{digest}"


def p2_canonical_entry_id(topic: dict[str, Any]) -> str:
    return f"p2:{p2_cue_id(topic)[6:]}"


def p2_entry_id(category: str, title: str, linked_question: str = "") -> str:
    if clean_report_text(linked_question):
        normalized = stable_question_text(linked_question)
        digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]
        return f"p2:{digest}"
    category_key = re.sub(r"[^a-z0-9]+", "_", str(category or "special").lower()).strip("_") or "special"
    digest = hashlib.md5(f"{category_key}\n{str(title or '').strip()}".encode("utf-8")).hexdigest()[:12]
    return f"p2:{category_key}:{digest}"


def p2_corpus_extra(entry: P2CorpusEntry) -> dict[str, str]:
    metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
    return {
        "p3_follow_up_text": clean_markdown_text(str(metadata.get("p3_follow_up_text") or ""))[:8000],
    }


def p2_corpus_entry_payload(entry: P2CorpusEntry) -> dict[str, Any]:
    extra = p2_corpus_extra(entry)
    return {
        "entry_id": entry.entry_id,
        "category": entry.category,
        "label": entry.get_category_display(),
        "title": entry.title,
        "material_text": entry.material_text,
        "p3_follow_up_text": extra["p3_follow_up_text"],
        "linked_question": entry.linked_question,
        "updated_at": timezone.localtime(entry.updated_at).strftime("%Y-%m-%d %H:%M"),
    }


def p3_bank_followup_id(p2_question_id: str, followup_question: str, index: int) -> str:
    normalized = stable_question_text(f"{p2_question_id}\n{index}\n{followup_question}")
    digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]
    return f"p3bank:{digest}"


def _p2_cue_id_from_any(question_id: str) -> str:
    value = clean_report_text(str(question_id or ""))
    if value.startswith("p2:"):
        return f"p2cue:{value[3:]}"
    return value


def p2_bank_topic_for_question_id(question_id: str) -> dict[str, Any] | None:
    cue_id = _p2_cue_id_from_any(question_id)
    if not cue_id:
        return None
    bank = get_question_bank()
    for topic in bank.all_p2:
        topic_cue_id = str(topic.get("cue_id") or p2_cue_id(topic))
        topic_entry_id = str(topic.get("canonical_entry_id") or p2_canonical_entry_id(topic))
        if cue_id in {topic_cue_id, topic_entry_id, str(topic.get("title") or "")}:
            return topic
    return None


def p2_bank_question_text(topic: dict[str, Any] | None, fallback: str = "") -> str:
    if topic:
        title = clean_report_text(str(topic.get("title") or ""))
        bullets = [clean_report_text(str(item)) for item in topic.get("bullets") or [] if clean_report_text(str(item))]
        rounding = clean_report_text(str(topic.get("rounding") or ""))
        return p2_cue_identity_text({"title": title, "bullets": bullets, "rounding": rounding})
    return clean_report_text(str(fallback or ""))


def p2_bank_corpus_payload(user, question_id: str) -> dict[str, Any]:
    cue_id = _p2_cue_id_from_any(question_id)
    topic = p2_bank_topic_for_question_id(cue_id)
    question = p2_bank_question_text(topic, cue_id)
    entry = P2BankCorpusEntry.objects.filter(user=user, question_id=cue_id).first()
    metadata = entry.metadata if entry and isinstance(entry.metadata, dict) else {}
    return {
        "question_id": cue_id,
        "question": entry.question if entry else question,
        "corpus_text": entry.corpus_text if entry else "",
        "last_ai_answer": entry.last_ai_answer if entry else "",
        "metadata": metadata,
        "brainstorm_idea": clean_report_text(str(metadata.get("brainstorm_idea") or "")),
        "updated_at": timezone.localtime(entry.updated_at).strftime("%Y-%m-%d %H:%M") if entry else "",
    }


def save_p2_bank_corpus(user, question_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    cue_id = _p2_cue_id_from_any(question_id)
    if not cue_id:
        raise SpeakingError("P2 question id is required.")
    topic = p2_bank_topic_for_question_id(cue_id)
    existing = P2BankCorpusEntry.objects.filter(user=user, question_id=cue_id).first()
    question = clean_report_text(str(payload.get("question") or ""))[:2000] or (existing.question if existing else "") or p2_bank_question_text(topic, cue_id)
    metadata = dict(existing.metadata) if existing and isinstance(existing.metadata, dict) else {}
    if isinstance(payload.get("metadata"), dict):
        metadata.update(payload["metadata"])
    if "brainstorm_idea" in payload:
        metadata["brainstorm_idea"] = clean_report_text(str(payload.get("brainstorm_idea") or ""))[:1000]
    if "brainstorm_idea" in metadata:
        metadata["brainstorm_idea"] = clean_report_text(str(metadata.get("brainstorm_idea") or ""))[:1000]

    defaults = {
        "question": question,
        "corpus_text": existing.corpus_text if existing else "",
        "last_ai_answer": existing.last_ai_answer if existing else "",
        "metadata": metadata,
    }
    if "corpus_text" in payload or "material_text" in payload:
        defaults["corpus_text"] = clean_markdown_text(str(payload.get("corpus_text") or payload.get("material_text") or ""))[:12000]
    if "last_ai_answer" in payload:
        defaults["last_ai_answer"] = clean_markdown_text(str(payload.get("last_ai_answer") or ""))[:12000]
    entry, _ = P2BankCorpusEntry.objects.update_or_create(
        user=user,
        question_id=cue_id,
        defaults=defaults,
    )
    return p2_bank_corpus_payload(user, entry.question_id)


def p3_bank_followup_list(user, p2_question_id: str) -> dict[str, Any]:
    cue_id = _p2_cue_id_from_any(p2_question_id)
    topic = p2_bank_topic_for_question_id(cue_id)
    questions = [
        clean_report_text(str(item))[:260]
        for item in (topic or {}).get("p3_follow_ups", [])
        if clean_report_text(str(item))
    ]
    saved = {
        entry.followup_id: entry
        for entry in P3BankFollowupCorpusEntry.objects.filter(user=user, p2_question_id=cue_id)
    }
    items: list[dict[str, Any]] = []
    for index, question in enumerate(questions):
        followup_id = p3_bank_followup_id(cue_id, question, index)
        entry = saved.get(followup_id)
        items.append(
            {
                "p2_question_id": cue_id,
                "followup_id": followup_id,
                "followup_question": entry.followup_question if entry else question,
                "corpus_text": entry.corpus_text if entry else "",
                "last_ai_answer": entry.last_ai_answer if entry else "",
                "metadata": entry.metadata if entry and isinstance(entry.metadata, dict) else {},
                "updated_at": timezone.localtime(entry.updated_at).strftime("%Y-%m-%d %H:%M") if entry else "",
            }
        )
    return {
        "p2_question_id": cue_id,
        "question": p2_bank_question_text(topic, cue_id),
        "items": items,
        "count": len(items),
    }


def save_p3_bank_followup_corpus(user, followup_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    followup_key = clean_report_text(str(followup_id or payload.get("followup_id") or ""))
    if not followup_key:
        raise SpeakingError("P3 follow-up id is required.")
    p2_question_id = _p2_cue_id_from_any(str(payload.get("p2_question_id") or ""))
    followup_question = clean_report_text(str(payload.get("followup_question") or ""))[:1000]
    if not p2_question_id or not followup_question:
        for topic in get_question_bank().all_p2:
            cue_id = str(topic.get("cue_id") or p2_cue_id(topic))
            for index, question in enumerate(topic.get("p3_follow_ups") or []):
                normalized_question = clean_report_text(str(question))[:260]
                if p3_bank_followup_id(cue_id, normalized_question, index) == followup_key:
                    p2_question_id = cue_id
                    followup_question = normalized_question
                    break
            if p2_question_id and followup_question:
                break
    if not p2_question_id or not followup_question:
        raise SpeakingError("P3 follow-up question not found.")
    corpus_text = clean_markdown_text(str(payload.get("corpus_text") or ""))[:12000]
    last_ai_answer = clean_markdown_text(str(payload.get("last_ai_answer") or ""))[:12000]
    entry, _ = P3BankFollowupCorpusEntry.objects.update_or_create(
        user=user,
        followup_id=followup_key,
        defaults={
            "p2_question_id": p2_question_id,
            "followup_question": followup_question,
            "corpus_text": corpus_text,
            "last_ai_answer": last_ai_answer,
            "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        },
    )
    return {
        "p2_question_id": entry.p2_question_id,
        "followup_id": entry.followup_id,
        "followup_question": entry.followup_question,
        "corpus_text": entry.corpus_text,
        "last_ai_answer": entry.last_ai_answer,
        "metadata": entry.metadata if isinstance(entry.metadata, dict) else {},
        "updated_at": timezone.localtime(entry.updated_at).strftime("%Y-%m-%d %H:%M"),
    }


def p2_topic_card_payload(
    topic: dict[str, Any],
    bank_entry: P2BankCorpusEntry | None = None,
    p3_entries_by_id: dict[str, P3BankFollowupCorpusEntry] | None = None,
) -> dict[str, Any]:
    category = p2_topic_category(topic)
    cue_id = str(topic.get("cue_id") or p2_cue_id(topic))
    entry_id = str(topic.get("canonical_entry_id") or p2_canonical_entry_id(topic))
    title = clean_report_text(str(topic.get("title") or ""))
    bullets = [clean_report_text(str(item)) for item in topic.get("bullets") or [] if clean_report_text(str(item))]
    rounding = clean_report_text(str(topic.get("rounding") or ""))
    p3_follow_ups = [
        clean_report_text(str(item))[:260]
        for item in topic.get("p3_follow_ups") or []
        if clean_report_text(str(item))
    ]
    linked_question = p2_cue_identity_text({"title": title, "bullets": bullets, "rounding": rounding})
    p3_entries_by_id = p3_entries_by_id or {}
    metadata = bank_entry.metadata if bank_entry and isinstance(bank_entry.metadata, dict) else {}
    brainstorm_idea = clean_report_text(str(metadata.get("brainstorm_idea") or ""))
    p3_saved_count = 0
    for index, question in enumerate(p3_follow_ups):
        followup_id = p3_bank_followup_id(cue_id, question, index)
        if p3_entries_by_id.get(followup_id) and p3_entries_by_id[followup_id].corpus_text.strip():
            p3_saved_count += 1
    return {
        "entry_id": entry_id,
        "canonical_entry_id": entry_id,
        "cue_id": cue_id,
        "category": category,
        "label": p2_category_label(category),
        "title": title,
        "cue_title": title,
        "bullets": bullets,
        "rounding": rounding,
        "linked_question": linked_question,
        "material_text": bank_entry.corpus_text if bank_entry else "",
        "brainstorm_idea": brainstorm_idea,
        "has_brainstorm_idea": bool(brainstorm_idea),
        "p3_follow_up_text": "",
        "updated_at": timezone.localtime(bank_entry.updated_at).strftime("%Y-%m-%d %H:%M") if bank_entry else "",
        "season": str(topic.get("season") or ""),
        "status": str(topic.get("status") or ""),
        "region": str(topic.get("region") or ""),
        "source": str(topic.get("source") or ""),
        "source_url": str(topic.get("source_url") or ""),
        "p3_theme": str(topic.get("p3_theme") or ""),
        "p3_follow_ups": p3_follow_ups,
        "p3_follow_up_count": len(p3_follow_ups),
        "p3_follow_up_saved_count": p3_saved_count,
        "has_material": bool(bank_entry and bank_entry.corpus_text.strip()),
        "has_p3_follow_up": p3_saved_count > 0,
    }


def p2_corpus_library(user, scope: str | None = None) -> dict[str, Any]:
    normalized_scope = normalize_question_bank_scope(scope)
    entries_by_id = {
        entry.entry_id: entry
        for entry in P2CorpusEntry.objects.filter(user=user)
    }
    grouped = {
        item["category"]: {
            "category": item["category"],
            "label": item["label"],
            "items": [],
        }
        for item in P2_CORPUS_CATEGORIES
    }
    ordered_entries = sorted(entries_by_id.values(), key=lambda item: (item.category, -item.updated_at.timestamp(), item.title))
    for entry in ordered_entries:
        group = grouped.setdefault(
            entry.category,
            {"category": entry.category, "label": entry.get_category_display(), "items": []},
        )
        group["items"].append(p2_corpus_entry_payload(entry))
    categories = list(grouped.values())
    for category in categories:
        category["material_count"] = len(category["items"])
    bank = get_question_bank()
    selected_topics = bank.part2_for_scope(normalized_scope)
    current_part2_categories = p2_current_topic_categories(selected_topics)
    topic_cue_ids = [str(topic.get("cue_id") or p2_cue_id(topic)) for topic in selected_topics]
    bank_entries_by_question_id = {
        entry.question_id: entry
        for entry in P2BankCorpusEntry.objects.filter(user=user, question_id__in=topic_cue_ids)
    }
    p3_entries_by_id = {
        entry.followup_id: entry
        for entry in P3BankFollowupCorpusEntry.objects.filter(user=user, p2_question_id__in=topic_cue_ids)
    }
    current_part2_cards = [
        p2_topic_card_payload(
            topic,
            bank_entries_by_question_id.get(str(topic.get("cue_id") or p2_cue_id(topic))),
            p3_entries_by_id,
        )
        for topic in selected_topics
    ]
    return {
        "categories": categories,
        "category_count": len(categories),
        "material_count": sum(len(group["items"]) for group in categories),
        "active_season": CURRENT_SPEAKING_SEASON,
        "active_region": CURRENT_SPEAKING_REGION,
        "active_scope": normalized_scope,
        "active_scope_label": QUESTION_BANK_SCOPE_LABELS[normalized_scope],
        "scope": "current_season_only" if normalized_scope == QUESTION_BANK_SCOPE_CURRENT else normalized_scope,
        "current_part2_count": len(selected_topics),
        "current_part2_categories": current_part2_categories,
        "current_part2_cards": current_part2_cards,
    }


def save_p2_corpus(user, payload: dict[str, Any]) -> dict[str, Any]:
    category = clean_report_text(str(payload.get("category") or P2CorpusEntry.Category.SPECIAL))
    valid_categories = {item["category"] for item in P2_CORPUS_CATEGORIES}
    if category not in valid_categories:
        category = P2CorpusEntry.Category.SPECIAL
    title = clean_report_text(str(payload.get("title") or "未命名素材"))[:200] or "未命名素材"
    material_text = clean_markdown_text(str(payload.get("material_text") or ""))[:12000]
    p3_follow_up_text = clean_markdown_text(str(payload.get("p3_follow_up_text") or ""))[:8000]
    linked_question = clean_report_text(str(payload.get("linked_question") or ""))[:1000]
    entry_id = clean_report_text(str(payload.get("entry_id") or "")) or p2_entry_id(category, title, linked_question)
    metadata = {
        "saved_from": clean_report_text(str(payload.get("source") or "p2_corpus")),
        "p3_follow_up_text": p3_follow_up_text,
    }
    entry, _ = P2CorpusEntry.objects.update_or_create(
        user=user,
        entry_id=entry_id,
        defaults={
            "category": category,
            "title": title,
            "material_text": material_text,
            "linked_question": linked_question,
            "metadata": metadata,
        },
    )
    return p2_corpus_entry_payload(entry)


def delete_p2_corpus(user, entry_id: str) -> dict[str, Any]:
    entry = P2CorpusEntry.objects.filter(user=user, entry_id=str(entry_id or "").strip()).first()
    if not entry:
        raise SpeakingError("P2 corpus entry not found")
    entry.delete()
    return {"ok": True}


def takeaway_entry_id(source_text: str) -> str:
    digest = hashlib.md5(str(source_text or "").strip().lower().encode("utf-8")).hexdigest()[:14]
    return f"lt:{digest}"


def language_takeaway_payload(entry: LanguageTakeawayEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "source_text": entry.source_text,
        "chinese_text": entry.chinese_text,
        "source_language": entry.source_language,
        "target_language": entry.target_language,
        "context_url": entry.context_url,
        "context_label": entry.context_label,
        "updated_at": timezone.localtime(entry.updated_at).strftime("%Y-%m-%d %H:%M"),
    }


def language_takeaway_queryset(user):
    return LanguageTakeawayEntry.objects.filter(user=user).filter(
        Q(metadata__saved_from__isnull=True) | ~Q(metadata__saved_from="writing_takeaway")
    )


def normalize_takeaway_review_kind(kind: str | None) -> str:
    value = str(kind or "").strip().lower()
    if value not in {"language", "writing"}:
        raise SpeakingError("Invalid takeaway review kind")
    return value


def expression_replacement_payload(entry: ExpressionReplacementEntry) -> dict[str, Any]:
    return {
        "item_id": entry.item_id,
        "id": entry.item_id,
        "source": entry.source,
        "replacements": entry.replacements,
        "updated_at": timezone.localtime(entry.updated_at).isoformat() if entry.updated_at else "",
    }


def expression_replacement_list(user, kind: str) -> dict[str, Any]:
    value = normalize_takeaway_review_kind(kind)
    rows = ExpressionReplacementEntry.objects.filter(user=user, kind=value).order_by("created_at", "id")
    items = [expression_replacement_payload(row) for row in rows]
    return {"kind": value, "items": items, "count": len(items)}


def save_expression_replacement(user, kind: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    value = normalize_takeaway_review_kind(kind)
    clean_item_id = str(item_id or "").strip()
    if not clean_item_id:
        raise SpeakingError("Expression replacement item_id is required")
    if len(clean_item_id) > 160:
        raise SpeakingError("Expression replacement item_id is too long")
    source = str((payload or {}).get("source") or "").strip()
    replacements = str((payload or {}).get("replacements") or "").strip()
    if not source and not replacements:
        raise SpeakingError("Expression replacement content is required")
    row, _created = ExpressionReplacementEntry.objects.update_or_create(
        user=user,
        kind=value,
        item_id=clean_item_id,
        defaults={"source": source, "replacements": replacements},
    )
    return expression_replacement_payload(row)


def delete_expression_replacement(user, kind: str, item_id: str) -> dict[str, Any]:
    value = normalize_takeaway_review_kind(kind)
    clean_item_id = str(item_id or "").strip()
    ExpressionReplacementEntry.objects.filter(user=user, kind=value, item_id=clean_item_id).delete()
    return {"ok": True, "item_id": clean_item_id}


def takeaway_review_state_payload(user, kind: str) -> dict[str, Any]:
    value = normalize_takeaway_review_kind(kind)
    row = TakeawayReviewState.objects.filter(user=user, kind=value).first()
    return row.state if row and isinstance(row.state, dict) else {}


def _review_record_last(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("last") or "")
    return ""


def _review_record_reps(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    raw = value.get("reps") or 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _prefer_review_record(current: Any, incoming: Any) -> Any:
    if not isinstance(current, dict):
        return incoming
    if not isinstance(incoming, dict):
        return current
    current_last = _review_record_last(current)
    incoming_last = _review_record_last(incoming)
    if incoming_last > current_last:
        return incoming
    if incoming_last < current_last:
        return current
    return incoming if _review_record_reps(incoming) > _review_record_reps(current) else current


def _prefer_daily_batch(current: Any, incoming: Any) -> Any:
    if not isinstance(current, dict):
        return incoming
    if not isinstance(incoming, dict):
        return current
    return incoming if str(incoming.get("day") or "") >= str(current.get("day") or "") else current


def merge_takeaway_review_state(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current or {})
    for key, value in (incoming or {}).items():
        if key == "__daily_batch":
            merged[key] = _prefer_daily_batch(merged.get(key), value)
        elif key.startswith("__"):
            merged[key] = value
        else:
            merged[key] = _prefer_review_record(merged.get(key), value)
    return merged


def save_takeaway_review_state(user, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    value = normalize_takeaway_review_kind(kind)
    state = payload.get("state") if isinstance(payload, dict) else {}
    if not isinstance(state, dict):
        raise SpeakingError("Invalid takeaway review state")
    row = TakeawayReviewState.objects.filter(user=user, kind=value).first()
    if row:
        row.state = merge_takeaway_review_state(row.state if isinstance(row.state, dict) else {}, state)
        row.save(update_fields=["state", "updated_at"])
    else:
        row = TakeawayReviewState.objects.create(user=user, kind=value, state=state)
    return {
        "kind": value,
        "review_state": row.state if isinstance(row.state, dict) else {},
        "updated_at": timezone.localtime(row.updated_at).isoformat() if row.updated_at else "",
    }


def language_takeaway_library(user) -> dict[str, Any]:
    entries = [
        language_takeaway_payload(entry)
        for entry in language_takeaway_queryset(user).order_by("-updated_at")[:300]
    ]
    return {"items": entries, "count": len(entries), "review_state": takeaway_review_state_payload(user, "language")}


def writing_takeaway_library(user) -> dict[str, Any]:
    entries = [
        language_takeaway_payload(entry)
        for entry in LanguageTakeawayEntry.objects.filter(
            user=user,
            metadata__saved_from="writing_takeaway",
        ).order_by("-updated_at")[:300]
    ]
    return {"items": entries, "count": len(entries), "review_state": takeaway_review_state_payload(user, "writing")}


LOCAL_TAKEAWAY_PHRASE_TRANSLATIONS = {
    "a big fan of": "非常喜欢",
    "a good fit for": "很适合",
    "a wide range of": "各种各样的",
    "as far as i know": "据我所知",
    "at the moment": "目前",
    "broaden my horizons": "开阔我的眼界",
    "come across": "偶然遇到；偶然发现",
    "deal with": "处理；应对",
    "depend on": "取决于；依靠",
    "from my perspective": "从我的角度来看",
    "get along with": "与……相处",
    "get used to": "习惯于",
    "go by": "流逝；经过",
    "have a positive impact on": "对……有积极影响",
    "in my view": "在我看来",
    "in terms of": "就……而言",
    "keep in touch with": "与……保持联系",
    "look forward to": "期待",
    "make a difference": "产生影响；带来改变",
    "on a regular basis": "定期地；经常",
    "play an important role": "发挥重要作用",
    "put a lot of effort into": "投入很多努力",
    "relieve stress": "缓解压力",
    "spend time doing": "花时间做……",
    "stand out": "突出；显眼",
    "strike a balance": "取得平衡",
    "take advantage of": "利用",
    "take part in": "参加",
    "the majority of": "大多数",
    "to some extent": "在某种程度上",
    "used to": "过去常常",
}


LOCAL_TAKEAWAY_WORD_TRANSLATIONS = {
    "academic": "学术的",
    "advantage": "优势",
    "balance": "平衡",
    "challenge": "挑战",
    "comfortable": "舒服的",
    "convenient": "方便的",
    "creative": "有创造力的",
    "culture": "文化",
    "develop": "发展",
    "efficient": "高效的",
    "enjoy": "享受；喜欢",
    "especially": "尤其",
    "experience": "经历；体验",
    "important": "重要的",
    "improve": "提高",
    "interesting": "有趣的",
    "knowledge": "知识",
    "memorable": "难忘的",
    "opportunity": "机会",
    "practical": "实用的",
    "pressure": "压力",
    "relaxing": "放松的",
    "repetitive": "重复的",
    "responsibility": "责任",
    "routine": "日常安排",
    "solution": "解决方案",
    "specific": "具体的",
    "traditional": "传统的",
    "useful": "有用的",
    "valuable": "有价值的",
    "work": "工作",
}


CAIYUN_COMPAT_TOKEN = "ssdj273ksdiwi923bsd9"
CAIYUN_COMPAT_DEVICE_ID = "F1F902F7-1780-4C88-848D-71F35D88A602"


def local_takeaway_translate_text(text: str, target: str = "zh") -> dict[str, Any]:
    source = clean_report_text(str(text or ""))[:1000]
    if not source:
        raise SpeakingError("Missing text to translate.")
    if (target or "zh") != "zh":
        return {
            "source_text": source,
            "chinese_text": "",
            "provider": "local",
            "status": "unsupported_target",
            "message": "Local offline translation currently supports Chinese only.",
        }
    if re.search(r"[\u4e00-\u9fff]", source):
        return {
            "source_text": source,
            "chinese_text": source,
            "provider": "local",
            "status": "ready",
        }
    normalized = re.sub(r"\s+", " ", source.strip().lower())
    direct = LOCAL_TAKEAWAY_PHRASE_TRANSLATIONS.get(normalized) or LOCAL_TAKEAWAY_WORD_TRANSLATIONS.get(normalized)
    if direct:
        return {
            "source_text": source,
            "chinese_text": direct,
            "provider": "local",
            "status": "ready",
        }
    translated_parts = []
    for token in re.findall(r"[A-Za-z][A-Za-z'-]*", normalized):
        lemma = token.strip("'")
        singular = lemma[:-1] if lemma.endswith("s") else lemma
        translated = LOCAL_TAKEAWAY_WORD_TRANSLATIONS.get(lemma) or LOCAL_TAKEAWAY_WORD_TRANSLATIONS.get(singular)
        if translated and translated not in translated_parts:
            translated_parts.append(translated)
    return {
        "source_text": source,
        "chinese_text": "；".join(translated_parts),
        "provider": "local",
        "status": "ready" if translated_parts else "needs_edit",
        "message": "" if translated_parts else "No local dictionary match. Edit the Chinese field before saving.",
    }


def caiyun_translate_text(text: str, target: str = "zh") -> dict[str, Any]:
    source = clean_report_text(str(text or ""))[:1000]
    if not source:
        raise SpeakingError("Missing text to translate.")
    token = os.environ.get("CAIYUN_TOKEN") or os.environ.get("CAIYUN_TRANSLATE_TOKEN") or CAIYUN_COMPAT_TOKEN
    target_language = target or "zh"
    payload = {
        "source": source,
        "trans_type": f"auto2{target_language}",
        "detect": True,
        "os_type": "ios",
        "device_id": CAIYUN_COMPAT_DEVICE_ID,
        "media": "text",
        "request_id": uuid.uuid4().int % 1_000_000_000,
        "user_id": "",
        "dict": True,
    }
    request = urllib.request.Request(
        "https://interpreter.cyapi.cn/v1/translator",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "X-Authorization": f"token {token}",
            "User-Agent": "caiyunInterpreter/5 CFNetwork/1404.0.5 Darwin/22.3.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        fallback = local_takeaway_translate_text(source, target_language)
        fallback["caiyun_status"] = "unavailable"
        fallback["caiyun_error"] = str(exc)
        return fallback
    target_values = data.get("target") or ""
    if isinstance(target_values, list):
        translated = target_values[0] if target_values else ""
    else:
        translated = target_values
    if not translated:
        fallback = local_takeaway_translate_text(source, target_language)
        fallback["caiyun_status"] = "empty"
        return fallback
    return {
        "source_text": source,
        "chinese_text": clean_report_text(str(translated or ""))[:1000],
        "provider": "caiyun",
        "status": "ready",
        "raw": data,
    }


def save_language_takeaway(user, payload: dict[str, Any]) -> dict[str, Any]:
    source_text = clean_report_text(str(payload.get("source_text") or ""))[:1000]
    if not source_text:
        raise SpeakingError("Source text is empty.")
    chinese_text = clean_report_text(str(payload.get("chinese_text") or ""))[:1000]
    entry_id = clean_report_text(str(payload.get("entry_id") or "")) or takeaway_entry_id(source_text)
    entry, _ = LanguageTakeawayEntry.objects.update_or_create(
        user=user,
        entry_id=entry_id,
        defaults={
            "source_text": source_text,
            "chinese_text": chinese_text,
            "source_language": clean_report_text(str(payload.get("source_language") or ""))[:32],
            "target_language": clean_report_text(str(payload.get("target_language") or "zh"))[:32] or "zh",
            "context_url": clean_report_text(str(payload.get("context_url") or ""))[:1000],
            "context_label": clean_report_text(str(payload.get("context_label") or ""))[:200],
            "metadata": {"saved_from": clean_report_text(str(payload.get("source") or "language_takeaway"))},
        },
    )
    return language_takeaway_payload(entry)


def save_writing_takeaway(user, payload: dict[str, Any]) -> dict[str, Any]:
    payload = {
        **payload,
        "source": "writing_takeaway",
        "entry_id": clean_report_text(str(payload.get("entry_id") or "")) or f"wt:{takeaway_entry_id(str(payload.get('source_text') or ''))[3:]}",
    }
    return save_language_takeaway(user, payload)


def update_language_takeaway(user, entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    entry = language_takeaway_queryset(user).filter(entry_id=str(entry_id or "").strip()).first()
    if not entry:
        raise SpeakingError("Language takeaway entry not found")
    editable_payload = {key: payload[key] for key in ("source_text", "chinese_text") if key in payload}
    payload = {
        "source_text": entry.source_text,
        "chinese_text": entry.chinese_text,
        "source_language": entry.source_language,
        "target_language": entry.target_language,
        "context_url": entry.context_url,
        "context_label": entry.context_label,
        "source": (entry.metadata or {}).get("saved_from") or "language_takeaway",
        **editable_payload,
        "entry_id": entry.entry_id,
    }
    return save_language_takeaway(user, payload)


def update_writing_takeaway(user, entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    entry = LanguageTakeawayEntry.objects.filter(
        user=user,
        entry_id=str(entry_id or "").strip(),
        metadata__saved_from="writing_takeaway",
    ).first()
    if not entry:
        raise SpeakingError("Language takeaway entry not found")
    editable_payload = {key: payload[key] for key in ("source_text", "chinese_text") if key in payload}
    payload = {
        "source_text": entry.source_text,
        "chinese_text": entry.chinese_text,
        "source_language": entry.source_language,
        "target_language": entry.target_language,
        "context_url": entry.context_url,
        "context_label": entry.context_label,
        **editable_payload,
        "entry_id": entry.entry_id,
    }
    return save_writing_takeaway(user, payload)


def delete_language_takeaway(user, entry_id: str) -> dict[str, Any]:
    entry = language_takeaway_queryset(user).filter(entry_id=str(entry_id or "").strip()).first()
    if not entry:
        raise SpeakingError("Language takeaway entry not found")
    entry.delete()
    return {"ok": True}


def delete_writing_takeaway(user, entry_id: str) -> dict[str, Any]:
    entry = LanguageTakeawayEntry.objects.filter(
        user=user,
        entry_id=str(entry_id or "").strip(),
        metadata__saved_from="writing_takeaway",
    ).first()
    if not entry:
        raise SpeakingError("Language takeaway entry not found")
    entry.delete()
    return {"ok": True}


def p2_corpus_for_selection(user, entry_id: str) -> dict[str, Any] | None:
    if not entry_id:
        return None
    entry = P2CorpusEntry.objects.filter(user=user, entry_id=entry_id).first()
    if not entry:
        return None
    return p2_corpus_entry_payload(entry)


def p1_corpus_for_turns(user, turns: list[SpeakingTurn]) -> dict[str, str]:
    ids: list[str] = []
    ids_by_turn: dict[str, list[str]] = {}
    by_turn_id = {turn.turn_id: turn for turn in turns}
    for turn in turns:
        if turn.part != "p1":
            continue
        ref_turn = turn
        metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
        prompt = metadata.get("prompt") if isinstance(metadata.get("prompt"), dict) else {}
        if prompt.get("role") == "follow_up" and prompt.get("after_turn"):
            ref_turn = by_turn_id.get(str(prompt.get("after_turn"))) or turn
        ref_metadata = ref_turn.metadata if isinstance(ref_turn.metadata, dict) else {}
        ref_prompt = ref_metadata.get("prompt") if isinstance(ref_metadata.get("prompt"), dict) else {}
        topic = str(ref_prompt.get("topic") or "general")
        question = str(ref_prompt.get("question") or ref_turn.question)
        canonical_id = p1_question_id(topic, question)
        candidate_ids = [
            canonical_id,
            str(ref_prompt.get("question_id") or ""),
            str(ref_prompt.get("legacy_question_id") or ""),
            legacy_p1_question_id(topic, question),
        ]
        candidate_ids = [item for item in dict.fromkeys(candidate_ids) if item]
        ids.extend(candidate_ids)
        ids_by_turn[turn.turn_id] = candidate_ids
    if not ids:
        return {}
    entries = {
        entry.question_id: entry.corpus_text
        for entry in P1CorpusEntry.objects.filter(user=user, question_id__in=ids)
        if entry.corpus_text.strip()
    }
    prepared: dict[str, str] = {}
    for turn_id, candidate_ids in ids_by_turn.items():
        for question_id in candidate_ids:
            if question_id in entries:
                prepared[turn_id] = entries[question_id]
                break
    return prepared


def prepared_corpus_for_turns(user, turns: list[SpeakingTurn]) -> dict[str, str]:
    prepared: dict[str, str] = {}
    for turn in turns:
        if turn.part != "p2":
            continue
        metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
        link = metadata.get("p2_corpus_link") if isinstance(metadata.get("p2_corpus_link"), dict) else {}
        entry_id = str(link.get("entry_id") or "")
        entry = p2_corpus_for_selection(user, entry_id)
        if entry and entry.get("material_text"):
            blocks = [
                f"P2素材库分类：{entry.get('label')}\n"
                f"素材标题：{entry.get('title')}\n"
                f"素材内容：\n{entry.get('material_text')}"
            ]
            prepared[turn.turn_id] = "\n\n".join(blocks).strip()
    return prepared
