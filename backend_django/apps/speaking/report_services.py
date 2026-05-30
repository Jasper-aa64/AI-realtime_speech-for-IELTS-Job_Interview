from __future__ import annotations

import hashlib
from typing import Any

from django.db.models import Avg, Count, Max, Min, Sum
from django.utils import timezone

from apps.ai.models import AITask

from .corpus_services import get_question_bank, p1_question_id
from .exceptions import SpeakingError
from .models import SpeakingAttempt, SpeakingTrainingObservation


def report_is_valid(attempt: SpeakingAttempt) -> bool:
    if attempt.status != SpeakingAttempt.Status.SCORED:
        return False
    if not hasattr(attempt, "report") or attempt.report.overall_band is None:
        return False
    turns = list(attempt.turns.all())
    if not turns:
        return False
    payload = attempt.report.report_payload if isinstance(attempt.report.report_payload, dict) else {}
    payload_turns = payload.get("turns") if isinstance(payload.get("turns"), list) else []
    if payload_turns:
        return all(str(turn.get("status") or "completed") == "completed" for turn in payload_turns)
    return all(turn.transcript_cleaned or turn.transcript_raw or not turn.counts_toward_total for turn in turns)


def report_payload(attempt: SpeakingAttempt) -> dict[str, Any]:
    payload = dict(attempt.report.report_payload or {})
    payload.setdefault("id", attempt.attempt_id)
    payload.setdefault("mode", attempt.mode)
    payload.setdefault("part", attempt.part)
    payload.setdefault("title", attempt.title)
    payload.setdefault("status", attempt.status)
    payload.setdefault("display_time", timezone.localtime(attempt.updated_at).strftime("%Y-%m-%d %H:%M"))
    payload.setdefault("candidate", attempt.english_name)
    payload.setdefault("full_name", attempt.full_name)
    payload.setdefault("english_name", attempt.english_name)
    payload.setdefault(
        "ielts_score",
        {
            "overall_band": float(attempt.report.overall_band) if attempt.report.overall_band is not None else None,
            "fluency_coherence": float(attempt.report.fluency_coherence) if attempt.report.fluency_coherence is not None else None,
            "lexical_resource": float(attempt.report.lexical_resource) if attempt.report.lexical_resource is not None else None,
            "grammatical_range": float(attempt.report.grammar_range_accuracy) if attempt.report.grammar_range_accuracy is not None else None,
            "pronunciation_estimate": float(attempt.report.pronunciation) if attempt.report.pronunciation is not None else None,
            "feedback": attempt.report.feedback_summary,
        },
    )
    payload.setdefault(
        "turns",
        [
            {
                "id": turn.turn_id,
                "part": turn.part,
                "question": turn.question,
                "transcript_raw": turn.transcript_raw,
                "transcript_cleaned": turn.transcript_cleaned,
                "display_transcript": turn.metadata.get("display_transcript", ""),
                "display_transcript_markdown": turn.metadata.get("display_transcript_markdown", ""),
                "transcript_status": turn.metadata.get("transcript_status", "captured" if (turn.transcript_cleaned or turn.transcript_raw) else "missing"),
                "pronunciation": turn.pronunciation,
                "status": "completed",
                "band7_version": turn.metadata.get("band7_version", ""),
                "upgrade_notes": turn.metadata.get("upgrade_notes", []),
                "ai_coaching": turn.metadata.get("ai_coaching", ""),
            }
            for turn in attempt.turns.all().order_by("sequence")
        ],
    )
    normalize_p1_report_turn_corpus_keys(payload)
    return payload


def latest_speaking_report_task(attempt: SpeakingAttempt) -> AITask | None:
    return (
        AITask.objects.filter(
            user=attempt.user,
            task_type="speaking_report",
            related_type="speaking_attempt",
            related_id=attempt.attempt_id,
        )
        .order_by("-created_at", "-updated_at")
        .first()
    )


def speaking_task_summary_payload(task: AITask | None) -> dict[str, Any] | None:
    if not task:
        return None
    return {
        "id": task.task_id,
        "task_type": task.task_type,
        "status": task.status,
        "progress_percent": task.progress_percent,
        "attempt_count": task.attempt_count,
        "max_attempts": task.max_attempts,
        "error_code": task.error_code,
        "error_message": task.error_message,
        "fallback_reason": task.fallback_reason,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


def normalize_p1_report_turn_corpus_keys(payload: dict[str, Any]) -> None:
    """Backfill stable P1 corpus keys for old saved report payloads."""
    turns = payload.get("turns")
    if not isinstance(turns, list):
        return
    by_turn_id = {str(turn.get("id") or ""): turn for turn in turns if isinstance(turn, dict)}
    for turn in turns:
        if not isinstance(turn, dict) or str(turn.get("part") or "").lower() != "p1":
            continue
        prompt = turn.get("prompt") if isinstance(turn.get("prompt"), dict) else {}
        topic = str(turn.get("topic") or prompt.get("topic") or "general")
        question = str(turn.get("question") or prompt.get("question") or "")
        question_id = str(turn.get("question_id") or prompt.get("question_id") or "")
        if not question_id and question:
            question_id = p1_question_id(topic, question)
        if not turn.get("topic"):
            turn["topic"] = topic
        if not turn.get("question_id") and question_id:
            turn["question_id"] = question_id
        if prompt and not prompt.get("question_id") and question_id:
            prompt["question_id"] = question_id
            turn["prompt"] = prompt

        if prompt.get("role") == "follow_up" and prompt.get("after_turn"):
            parent = by_turn_id.get(str(prompt.get("after_turn")))
            if not isinstance(parent, dict):
                continue
            parent_prompt = parent.get("prompt") if isinstance(parent.get("prompt"), dict) else {}
            parent_topic = str(parent.get("topic") or parent_prompt.get("topic") or topic or "general")
            parent_question = str(parent.get("question") or parent_prompt.get("question") or "")
            parent_question_id = str(parent.get("question_id") or parent_prompt.get("question_id") or "")
            if not parent_question_id and parent_question:
                parent_question_id = p1_question_id(parent_topic, parent_question)
            if parent_question_id:
                turn["parent_question_id"] = parent_question_id
                turn["parent_topic"] = parent_topic
                turn["parent_question"] = parent_question


def history_item(attempt: SpeakingAttempt) -> dict[str, Any]:
    payload = attempt.report.report_payload if isinstance(attempt.report.report_payload, dict) else {}
    score = payload.get("ielts_score") if isinstance(payload.get("ielts_score"), dict) else {}
    return {
        "id": attempt.attempt_id,
        "timestamp": attempt.created_at.isoformat(),
        "display_time": timezone.localtime(attempt.updated_at).strftime("%Y-%m-%d %H:%M"),
        "mode": attempt.mode,
        "part": attempt.part,
        "title": attempt.title or payload.get("title") or payload.get("question") or attempt.mode.upper(),
        "question": payload.get("question") or attempt.title,
        "status": attempt.status,
        "overall_band": float(attempt.report.overall_band) if attempt.report.overall_band is not None else score.get("overall_band"),
        "turn_count": attempt.turns.count(),
    }


def history(user) -> dict[str, Any]:
    attempts = (
        SpeakingAttempt.objects.filter(user=user, status=SpeakingAttempt.Status.SCORED)
        .select_related("report")
        .prefetch_related("turns")
        .order_by("-updated_at")
    )
    return {"items": [history_item(attempt) for attempt in attempts if report_is_valid(attempt)]}


def detail(user, attempt_id: str) -> dict[str, Any]:
    attempt = (
        SpeakingAttempt.objects.filter(user=user, attempt_id=str(attempt_id or "").strip())
        .select_related("report")
        .prefetch_related("turns")
        .first()
    )
    if not attempt or not report_is_valid(attempt):
        raise SpeakingError("Speaking report not found")
    return report_payload(attempt)


def delete_attempt(user, attempt_id: str) -> dict[str, Any]:
    attempt = SpeakingAttempt.objects.filter(user=user, attempt_id=str(attempt_id or "").strip()).first()
    if not attempt:
        raise SpeakingError("Speaking attempt not found")
    attempt.delete()
    return {"ok": True}


def weak_items(user, limit: int = 50) -> list[dict[str, Any]]:
    """Return aggregated weak items for a user."""
    observations = (
        SpeakingTrainingObservation.objects.filter(user=user, weak_item_flag=True)
        .values("question_id", "part", "question")
        .annotate(
            attempts=Count("id"),
            weak_count=Sum("weak_item_flag"),
            last_seen=Max("observed_at"),
            next_due=Min("next_due"),
            avg_band=Avg("overall_band"),
            avg_relevance=Avg("relevance"),
        )
        .filter(weak_count__gt=0)
        .order_by("-weak_count", "-last_seen", "next_due")[:limit]
    )
    now = timezone.now()
    items = []
    for obs in observations:
        reasons: set[str] = set()
        related = SpeakingTrainingObservation.objects.filter(
            user=user, question_id=obs["question_id"], weak_item_flag=True
        ).values_list("weak_reasons", flat=True)
        for reason_list in related:
            if isinstance(reason_list, list):
                reasons.update(str(r) for r in reason_list)
        items.append({
            "question_id": obs["question_id"],
            "part": obs["part"],
            "question": obs["question"],
            "attempts": obs["attempts"],
            "weak_count": obs["weak_count"],
            "weak_reason": sorted(reasons),
            "avg_band": round(float(obs["avg_band"]), 2) if obs["avg_band"] is not None else None,
            "avg_relevance": round(float(obs["avg_relevance"]), 2) if obs["avg_relevance"] is not None else None,
            "last_seen": obs["last_seen"].isoformat() if obs["last_seen"] else None,
            "next_due": obs["next_due"].isoformat() if obs["next_due"] else None,
            "due": (obs["next_due"] or now) <= now,
        })
    return items


def replay_queue(user, limit: int = 10) -> list[dict[str, Any]]:
    """Return practice queue combining weak items and coverage items."""
    weak = weak_items(user, limit=100)
    due = [_queue_item(item, "weak") for item in weak if item.get("due")]
    pending = [_queue_item(item, "weak") for item in weak if not item.get("due")]
    queue = (due + pending)[:limit]

    if len(queue) < limit:
        weak_ids = {item["question_id"] for item in weak}
        queue.extend(_coverage_queue(weak_ids, limit - len(queue)))

    return queue[:limit]


def _queue_item(item: dict[str, Any], source: str) -> dict[str, Any]:
    result = dict(item)
    result["source"] = source
    result["weak_item_flag"] = source == "weak"
    return result


def _coverage_queue(weak_question_ids: set[str], limit: int) -> list[dict[str, Any]]:
    """Return coverage items to fill practice queue."""
    bank = get_question_bank()
    candidates: list[dict[str, Any]] = []

    for item in sorted(bank.p1, key=lambda r: (r.get("topic", ""), r.get("question", ""))):
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        question_id = f"p1:{hashlib.md5(question.encode()).hexdigest()[:12]}"
        if question_id in weak_question_ids:
            continue
        candidates.append(
            _queue_item(
                {
                    "question_id": question_id,
                    "part": "p1",
                    "question": question,
                    "weak_reason": [],
                    "next_due": None,
                    "due": False,
                },
                "coverage",
            )
        )
        if len(candidates) >= limit:
            return candidates

    return candidates[:limit]
