from __future__ import annotations

import random
from collections import Counter
from typing import Any

FIXED_EXAMINER_TTS_ITEMS = [
    {
        "key": "fixed_examiner_what_is_your_full_name",
        "text": "What is your full name?",
    },
    {
        "key": "fixed_examiner_do_you_work_or_do_you_study",
        "text": "Do you work or do you study?",
    },
    {
        "key": "fixed_examiner_p2_cue_card_instruction",
        "text": (
            "I'm going to give you a topic and I would like you to talk about it for one to two minutes. "
            "You have one minute to think about what you are going to say. "
            "You can make some notes if you wish."
        ),
    },
]


def _is_p1_work_study_identity_question(question: str) -> bool:
    normalized = "".join(c if c.isalnum() else " " for c in question.lower()).strip()
    phrases = [
        "do you work or are you",
        "are you a student or do you work",
        "do you work or study",
        "are you working or studying",
    ]
    return any(phrase in normalized for phrase in phrases)


def _cue_to_text(topic: dict[str, Any]) -> str:
    bullets = "\n".join(f"- {item}" for item in topic.get("bullets", []))
    return f"{topic.get('title', '')}\n\nYou should say:\n{bullets}\n\n{topic.get('rounding', '')}".strip()


def _cue_examiner_text() -> str:
    return FIXED_EXAMINER_TTS_ITEMS[2]["text"]


def _timers_for_part(part: str) -> dict[str, Any]:
    defaults = {"prep_seconds": 3, "speak_seconds": 60}
    if part == "p1":
        return {"prep_seconds": 3, "speak_seconds": 35}
    if part == "p2":
        return {"prep_seconds": 60, "speak_seconds": 120}
    if part == "p3":
        return {"prep_seconds": 7, "speak_seconds": 75}
    return defaults


def _normalize_question_text(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _p1_topic_practice_counts(
    user: Any, topics: dict[str, list[dict[str, Any]]]
) -> dict[str, int]:
    """Per-topic practice count for this user, summed over the topic's questions.

    Counts come from the user's historical P1 turns (matched on question text),
    so "least-practiced first" needs no extra schema. Returns {} when there is no
    authenticated user or on any query error, which makes topic selection fall
    back to plain random.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return {}
    try:
        from .models import SpeakingTurn

        practiced = list(
            SpeakingTurn.objects.filter(user=user, part="p1").values_list("question", flat=True)
        )
    except Exception:
        return {}
    practiced_counts = Counter(_normalize_question_text(q) for q in practiced)
    topic_counts: dict[str, int] = {}
    for topic, items in topics.items():
        topic_counts[topic] = sum(
            practiced_counts.get(_normalize_question_text(str(it.get("question") or "")), 0)
            for it in items
        )
    return topic_counts


def _weighted_topic_order(topic_names: list[str], counts: dict[str, int]) -> list[str]:
    """Permutation of topics biased toward least-practiced (weight 1/(count+1)).

    Unpractised topics are most likely to lead, but every ordering stays possible
    so sessions are not identical. With no counts this is a plain shuffle.
    """
    pool = list(topic_names)
    random.shuffle(pool)
    if not counts:
        return pool
    order: list[str] = []
    while pool:
        weights = [1.0 / (counts.get(name, 0) + 1) for name in pool]
        pick = random.choices(pool, weights=weights, k=1)[0]
        order.append(pick)
        pool.remove(pick)
    return order


def _question_practice_counts(user: Any, part: str) -> dict[str, int]:
    """Per-question practice counts for this user within one part, keyed by
    normalized text. Returns {} for anonymous users or on error, so selection
    falls back to plain random.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return {}
    try:
        from .models import SpeakingTurn

        practiced = list(
            SpeakingTurn.objects.filter(user=user, part=part).values_list("question", flat=True)
        )
    except Exception:
        return {}
    return dict(Counter(_normalize_question_text(q) for q in practiced))


def _p3_question_practice_counts(user: Any) -> dict[str, int]:
    """Per-question P3 practice counts (thin wrapper over the generic helper)."""
    return _question_practice_counts(user, "p3")


def _select_least_practiced_items(
    items: list[dict[str, Any]], count: int, counts: dict[str, int]
) -> list[dict[str, Any]]:
    """Pick `count` bank items favouring the least-practiced (weight 1/(n+1)),
    then restore their original bank order so the questions still flow naturally.

    This is the per-topic coverage guard: questions the user has never practised
    carry count 0 (max weight) and are drawn first, so repeated sessions walk
    through a topic's whole question list before any question repeats — no item
    is ever starved. With no history it degrades to a plain sample.
    """
    if count >= len(items):
        return list(items)
    indexed = list(enumerate(items))
    pool = list(indexed)
    random.shuffle(pool)
    chosen: list[tuple[int, dict[str, Any]]] = []
    if not counts:
        chosen = pool[:count]
    else:
        while pool and len(chosen) < count:
            weights = [
                1.0 / (counts.get(_normalize_question_text(str(it.get("question") or "")), 0) + 1)
                for _, it in pool
            ]
            pick = random.choices(range(len(pool)), weights=weights, k=1)[0]
            chosen.append(pool.pop(pick))
    chosen.sort(key=lambda pair: pair[0])
    return [it for _, it in chosen]


def _select_p3_followups(followups: list[str], count: int, user: Any = None) -> list[str]:
    """Pick `count` follow-ups, least-practiced first (weight 1/(count+1)).

    A card may carry more bank follow-ups (e.g. 6) than a session should drill;
    this draws `count` of them favouring the ones the user has practised least, so
    repeat sessions rotate through the rest. When there are at most `count`
    follow-ups the list is returned unchanged (callers rely on the order).
    """
    items = [f for f in followups if str(f).strip()]
    if len(items) <= count:
        return items
    counts = _p3_question_practice_counts(user)
    pool = list(items)
    random.shuffle(pool)
    if not counts:
        return pool[:count]
    chosen: list[str] = []
    while pool and len(chosen) < count:
        weights = [1.0 / (counts.get(_normalize_question_text(q), 0) + 1) for q in pool]
        pick = random.choices(pool, weights=weights, k=1)[0]
        chosen.append(pick)
        pool.remove(pick)
    return chosen
