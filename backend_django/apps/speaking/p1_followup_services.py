from __future__ import annotations

from typing import Any

from .p3_services import _extract_single_follow_up_question
from .text_utils import clean_report_text, extract_json_object_with_keys


def _is_p1_work_study_turn(turn: Any) -> bool:
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    prompt = metadata.get("prompt") if isinstance(metadata.get("prompt"), dict) else {}
    return turn.part == "p1" and prompt.get("flow") == "intro" and prompt.get("role") == "work_study"


def _fallback_p1_identity_follow_up(answer: str) -> str:
    lowered = answer.lower()
    if any(word in lowered for word in ("intern", "internship", "company")):
        return "How does your internship connect with what you study?"
    if any(word in lowered for word in ("student", "study", "university", "major", "school")):
        return "What do you enjoy most about your studies?"
    if any(word in lowered for word in ("work", "job", "office", "engineer", "business")):
        return "What do you enjoy most about your work?"
    return "Can you tell me a little more about what you do now?"


def _extract_p1_identity_follow_up_output(output: str) -> str:
    try:
        payload = extract_json_object_with_keys(output, {"follow_up"})
        follow_up = clean_report_text(str(payload.get("follow_up") or ""))
    except Exception:  # noqa: BLE001 - HTTP-compatible endpoints may return plain text
        follow_up = _extract_single_follow_up_question(output)
    if not follow_up or len(follow_up) > 160 or "?" not in follow_up:
        raise RuntimeError("p1 follow-up provider did not return a usable question")
    return follow_up


def _p1_identity_follow_up_prompt(answer: str) -> str:
    return f"""Return JSON only with top-level key follow_up.
Do not repeat the input. Do not include Markdown, explanation, or code fences.

You are an IELTS Speaking Part 1 examiner. Write one natural follow-up question based on the candidate's previous answer.
Use the candidate's real identity details. Do not invent facts.
Keep it short, conversational, and suitable for Part 1.
avoid asking the same obvious follow-up every time. Use the most specific detail
in this answer and vary the angle naturally, such as daily routine, challenge,
skill, plan, preference, or personal reason.

Candidate answer:
{answer}
"""


_P1_GENERIC_FOLLOW_UP_ANGLES = [
    "how long they have been in their current role or program",
    "what they find most challenging about their work or studies",
    "what skills they have gained",
    "whether they would recommend their career or field to others",
    "how they first became interested in their work or subject",
    "what their typical day looks like",
    "their plans after finishing their current role or degree",
    "what they like least about their work or studies",
    "how their work or studies affect their daily life",
    "whether they prefer working or studying",
]


def _p1_generic_follow_up_angle() -> str:
    """Pick a question angle that varies across calls (rotates by wall-clock minute)."""
    import time
    return _P1_GENERIC_FOLLOW_UP_ANGLES[int(time.time() // 60) % len(_P1_GENERIC_FOLLOW_UP_ANGLES)]


def _p1_identity_stream_prompt(answer: str) -> str:
    if not answer.strip():
        angle = _p1_generic_follow_up_angle()
        return (
            "You are an IELTS Speaking Part 1 examiner.\n"
            f"Write exactly one short, conversational follow-up question asking about {angle}.\n"
            "Suitable for IELTS Part 1. Output one line only — just the question, no labels or quotes.\n\n"
            "One follow-up question:\n"
        )
    return f"""You are an IELTS Speaking Part 1 examiner.
Write exactly one natural follow-up question based on the candidate's previous answer.
Use the candidate's real identity details. Do not invent facts.
Output one line only. Do not include JSON, Markdown, labels, explanations, or quotes.
avoid asking the same obvious follow-up every time. Use the most specific detail
in this answer and vary the angle naturally, such as daily routine, challenge,
skill, plan, preference, or personal reason.

Candidate answer:
{clean_report_text(answer)[:1800]}

One follow-up question:
"""
