"""Learning-profile helpers for speaking attempts.

Extracted from ``services.py`` to keep the learner-diagnosis logic (habit tags,
primary focus, supporting evidence) in one cohesive place. These functions read
turn transcripts and training observations and return a plain ``dict`` profile;
they do not mutate state.
"""

from __future__ import annotations

from typing import Any

from .models import SpeakingAttempt, SpeakingTrainingObservation
from .runtime_payload_services import _turn_status
from .scoring_services import (
    _word_count,
    turn_counts_for_scoring,
    turn_display_transcript,
)


def build_learning_profile(user, attempt: SpeakingAttempt) -> dict[str, Any]:
    """Build learning profile from user's attempt history."""
    turns = list(attempt.turns.all().order_by("sequence"))
    completed_turns = [t for t in turns if _turn_status(t) == "completed" and turn_counts_for_scoring(t)]

    evidence: list[str] = []
    tags: list[str] = []
    repeated_phrases: list[str] = []

    for turn in completed_turns:
        transcript = turn_display_transcript(turn)
        if not transcript:
            continue
        word_count = _word_count(transcript)
        part = turn.part or ""
        if part == "p2":
            evidence.append(f"P2 回答约 {word_count} 词，需要继续拉长展开。")
        elif part == "p3":
            evidence.append(f"P3 回答约 {word_count} 词，需要补上原因、对比或例子。")
        elif part == "p1":
            evidence.append(f"P1 回答约 {word_count} 词，需要更直接、更自然。")

        # Check for short answers
        if word_count < 20:
            tags.append("short_answer")
        if word_count < 35:
            tags.append("limited_development")

    # Get weak items from training
    weak_obs = SpeakingTrainingObservation.objects.filter(user=user, weak_item_flag=True).order_by("-observed_at")[:10]
    for obs in weak_obs:
        if obs.weak_reasons:
            tags.extend(obs.weak_reasons)

    tags = sorted(set(tags))[:8]

    return {
        "primary_focus": "answer_development" if "short_answer" in tags or "limited_development" in tags else "task_relevance",
        "primary_focus_text": "这次主要卡在回答展开不够，不是题目完全不会。" if "limited_development" in tags else "这次主要问题是没有完全扣住题目，先把回答方向答准。",
        "habit_tags": tags,
        "repeated_phrases": repeated_phrases[:6],
        "evidence": evidence[:8],
    }


def build_scoring_learning_profile(transcript: str, part: str) -> dict[str, Any]:
    answers = [line[2:].strip() for line in transcript.splitlines() if line.startswith("A:")]
    word_counts = [_word_count(answer) for answer in answers if answer]
    tags: list[str] = []
    evidence: list[str] = []
    if word_counts:
        short_count = sum(1 for count in word_counts if count < 25)
        if short_count:
            tags.append("short_answer")
            evidence.append(f"{short_count} 个回答少于 25 词，需要展开。")
        if part == "p1" and sum(word_counts) / max(1, len(word_counts)) < 30:
            tags.append("limited_development")
            evidence.append("P1 平均回答偏短，需要稳定扩展到 2-3 句。")
        if part == "p2" and max(word_counts) < 90:
            tags.append("limited_development")
            evidence.append("P2 长回答长度不足，需要覆盖 cue card 并展开细节。")
        if part == "p3" and sum(word_counts) / max(1, len(word_counts)) < 55:
            tags.append("limited_development")
            evidence.append("P3 回答需要补充原因、对比和例子。")
    if part == "p3":
        lowered = transcript.lower()
        if not any(token in lowered for token in ("however", "although", "whereas", "on the other hand", "while some")):
            tags.append("missing_concession")
            evidence.append("P3 缺少对比或让步，观点容易显得单薄。")
        if not any(token in lowered for token in ("society", "government", "public", "community", "generation", "families", "schools")):
            tags.append("limited_abstract_extension")
            evidence.append("P3 还需要从个人想法上升到社会/群体层面。")
    focus = "answer_development" if any(tag in tags for tag in ("short_answer", "limited_development")) else "task_relevance"
    if part == "p3" and any(tag in tags for tag in ("missing_concession", "limited_abstract_extension")):
        focus = "abstract_discussion"
    return {
        "primary_focus": focus,
        "primary_focus_text": (
            "这次 P3 主要要补 discussion move：观点后面要有原因、对比/让步和社会层面的影响。"
            if focus == "abstract_discussion"
            else "这次主要卡在回答展开不够，不是题目完全不会。" if focus == "answer_development" else "这次主要问题是先把回答方向答准。"
        ),
        "habit_tags": sorted(set(tags)),
        "evidence": evidence[:8],
    }
