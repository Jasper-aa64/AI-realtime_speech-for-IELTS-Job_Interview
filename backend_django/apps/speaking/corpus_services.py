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
from django.utils import timezone

from .exceptions import SpeakingError
from .models import LanguageTakeawayEntry, P1CorpusEntry, P2CorpusEntry, SpeakingTurn
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


class QuestionBank:
    """Load IELTS speaking questions from JSON files."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or Path(settings.BASE_DIR).parent / "data" / "ielts"
        self.p1: list[dict[str, Any]] = []
        self.p2: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        self.p1 = self._load_p1()
        self.p2 = self._load_p2()

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
                    topics.append(topic)
        return topics

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def summary(self) -> dict[str, Any]:
        p1_status_counts: dict[str, int] = {}
        for item in self.p1:
            status = str(item.get("status") or "seed")
            p1_status_counts[status] = p1_status_counts.get(status, 0) + 1
        p2_status_counts: dict[str, int] = {}
        for item in self.p2:
            status = str(item.get("status") or "seed")
            p2_status_counts[status] = p2_status_counts.get(status, 0) + 1
        return {
            "part1_count": len(self.p1),
            "part2_count": len(self.p2),
            "part1_topics": sorted({item["topic"] for item in self.p1}),
            "part2_themes": sorted({item.get("p3_theme", "") for item in self.p2 if item.get("p3_theme")}),
            "part1_status_counts": p1_status_counts,
            "part2_status_counts": p2_status_counts,
            "seasons": sorted({str(item.get("season") or "") for item in [*self.p1, *self.p2] if item.get("season")}),
            "regions": sorted({str(item.get("region") or "") for item in [*self.p1, *self.p2] if item.get("region")}),
        }

    def sample(self, p1_count: int = 5) -> dict[str, Any]:
        p1_count = max(1, min(p1_count, len(self.p1)))
        result = {}
        if self.p1:
            result["part1"] = random.sample(self.p1, p1_count)
        if self.p2:
            result["part2"] = random.choice(self.p2)
        return result


_question_bank: QuestionBank | None = None


def get_question_bank() -> QuestionBank:
    global _question_bank
    if _question_bank is None:
        _question_bank = QuestionBank()
    return _question_bank


def question_bank_summary() -> dict[str, Any]:
    return get_question_bank().summary()


def question_bank_sample(p1_count: int = 5) -> dict[str, Any]:
    return get_question_bank().sample(p1_count)


def p1_question_id(topic: str, question: str) -> str:
    topic_key = re.sub(r"[^a-z0-9]+", "_", str(topic or "general").lower()).strip("_") or "general"
    digest = hashlib.md5(f"{topic_key}\n{str(question or '').strip()}".encode("utf-8")).hexdigest()[:12]
    return f"p1:{topic_key}:{digest}"


def p1_topic_label(topic: str) -> str:
    return str(topic or "general").replace("_", " ").strip().title()


def p1_corpus_library(user) -> dict[str, Any]:
    bank = get_question_bank()
    entries = {
        entry.question_id: entry
        for entry in P1CorpusEntry.objects.filter(user=user)
    }
    grouped: dict[str, dict[str, Any]] = {}

    def add_question(topic: str, question: str, meta: dict[str, Any] | None = None) -> None:
        meta = meta or {}
        question_id = p1_question_id(topic, question)
        entry = entries.get(question_id)
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
    for item in bank.p1:
        add_question(str(item.get("topic") or "general"), str(item.get("question") or ""), item)

    topics = sorted(grouped.values(), key=lambda item: (item["topic"] != "intro", item["label"]))
    total_questions = sum(len(topic["questions"]) for topic in topics)
    saved_count = sum(1 for topic in topics for question in topic["questions"] if question.get("corpus_text"))
    return {
        "topics": topics,
        "topic_count": len(topics),
        "question_count": total_questions,
        "saved_count": saved_count,
    }


def save_p1_corpus(user, payload: dict[str, Any]) -> dict[str, Any]:
    topic = clean_report_text(str(payload.get("topic") or "general")) or "general"
    question = clean_report_text(str(payload.get("question") or ""))
    if not question:
        raise SpeakingError("Missing P1 question.")
    question_id = clean_report_text(str(payload.get("question_id") or "")) or p1_question_id(topic, question)
    corpus_text = clean_markdown_text(str(payload.get("corpus_text") or ""))[:8000]
    if not corpus_text.strip():
        raise SpeakingError("Corpus text is empty.")
    last_ai_answer = clean_markdown_text(str(payload.get("last_ai_answer") or ""))[:8000]
    entry, _ = P1CorpusEntry.objects.update_or_create(
        user=user,
        question_id=question_id,
        defaults={
            "topic": topic,
            "question": question,
            "corpus_text": corpus_text,
            "last_ai_answer": last_ai_answer,
            "metadata": {"saved_from": clean_report_text(str(payload.get("source") or "p1_corpus"))},
        },
    )
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


def p2_entry_id(category: str, title: str) -> str:
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


def p2_corpus_library(user) -> dict[str, Any]:
    grouped = {
        item["category"]: {
            "category": item["category"],
            "label": item["label"],
            "items": [],
        }
        for item in P2_CORPUS_CATEGORIES
    }
    for entry in P2CorpusEntry.objects.filter(user=user).order_by("category", "-updated_at", "title"):
        group = grouped.setdefault(
            entry.category,
            {"category": entry.category, "label": entry.get_category_display(), "items": []},
        )
        group["items"].append(p2_corpus_entry_payload(entry))
    categories = list(grouped.values())
    return {
        "categories": categories,
        "category_count": len(categories),
        "material_count": sum(len(group["items"]) for group in categories),
    }


def save_p2_corpus(user, payload: dict[str, Any]) -> dict[str, Any]:
    category = clean_report_text(str(payload.get("category") or P2CorpusEntry.Category.SPECIAL))
    valid_categories = {item["category"] for item in P2_CORPUS_CATEGORIES}
    if category not in valid_categories:
        category = P2CorpusEntry.Category.SPECIAL
    title = clean_report_text(str(payload.get("title") or "未命名素材"))[:200] or "未命名素材"
    entry_id = clean_report_text(str(payload.get("entry_id") or "")) or p2_entry_id(category, title)
    material_text = clean_markdown_text(str(payload.get("material_text") or ""))[:12000]
    if not material_text.strip():
        raise SpeakingError("P2 material text is empty.")
    p3_follow_up_text = clean_markdown_text(str(payload.get("p3_follow_up_text") or ""))[:8000]
    linked_question = clean_report_text(str(payload.get("linked_question") or ""))[:1000]
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


def language_takeaway_library(user) -> dict[str, Any]:
    entries = [
        language_takeaway_payload(entry)
        for entry in LanguageTakeawayEntry.objects.filter(user=user).order_by("-updated_at")[:300]
    ]
    return {"items": entries, "count": len(entries)}


def writing_takeaway_library(user) -> dict[str, Any]:
    entries = [
        language_takeaway_payload(entry)
        for entry in LanguageTakeawayEntry.objects.filter(
            user=user,
            metadata__saved_from="writing_takeaway",
        ).order_by("-updated_at")[:300]
    ]
    return {"items": entries, "count": len(entries)}


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


def delete_language_takeaway(user, entry_id: str) -> dict[str, Any]:
    entry = LanguageTakeawayEntry.objects.filter(user=user, entry_id=str(entry_id or "").strip()).first()
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
    id_by_turn: dict[str, str] = {}
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
        question_id = str(ref_prompt.get("question_id") or p1_question_id(topic, ref_turn.question))
        ids.append(question_id)
        id_by_turn[turn.turn_id] = question_id
    if not ids:
        return {}
    entries = {
        entry.question_id: entry.corpus_text
        for entry in P1CorpusEntry.objects.filter(user=user, question_id__in=ids)
        if entry.corpus_text.strip()
    }
    return {
        turn_id: entries[question_id]
        for turn_id, question_id in id_by_turn.items()
        if question_id in entries
    }


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
