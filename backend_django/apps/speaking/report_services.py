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
        return all(str(turn.get("status") or "completed") == "completed" for turn in payload_turns) and all(
            _report_turn_has_required_band7(turn)
            for turn in payload_turns
        )
    return all(turn.transcript_cleaned or turn.transcript_raw or not turn.counts_toward_total for turn in turns)


def _report_turn_has_required_band7(turn: dict[str, Any]) -> bool:
    prompt = turn.get("prompt") if isinstance(turn.get("prompt"), dict) else {}
    is_fixed_intro = (
        turn.get("part") == "p1"
        and prompt.get("flow") == "intro"
        and prompt.get("role") in {"name", "work_study"}
    )
    if is_fixed_intro:
        return True
    return bool(str(turn.get("band7_version") or turn.get("band7_markdown") or "").strip())


def report_payload(attempt: SpeakingAttempt) -> dict[str, Any]:
    payload = dict(attempt.report.report_payload or {})
    payload.setdefault("id", attempt.attempt_id)
    payload["report_status"] = "ready"
    payload.setdefault("mode", attempt.mode)
    payload.setdefault("part", attempt.part)
    payload.setdefault("title", attempt.title)
    payload.setdefault("status", attempt.status)
    payload.setdefault("display_time", timezone.localtime(attempt.created_at).strftime("%Y-%m-%d %H:%M"))
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
    # Only rebuild turns from the DB when the stored payload lacks them. Python
    # evaluates setdefault's second argument eagerly, so a setdefault here would
    # run this query + comprehension on every read even when "turns" is present.
    if "turns" not in payload:
        payload["turns"] = [
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
        ]
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


_FAILED_REPORT_TASK_STATUSES = {
    AITask.Status.FAILED,
    AITask.Status.FALLBACK,
    AITask.Status.CANCELLED,
}


def report_generation_failed_by_metadata(attempt: SpeakingAttempt) -> bool:
    """Metadata-only failure check (no DB query) for cheap use in list views."""
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    return (
        str(metadata.get("report_generation_status") or "") == "failed"
        or str(metadata.get("analysis_status") or "") == "failed"
    )


def report_generation_failed(attempt: SpeakingAttempt) -> bool:
    """Whether report generation terminally failed and no valid report exists.

    A re-queued retry overwrites ``analysis_status`` with ``queued``/``running``,
    so a pending retry is intentionally NOT reported as failed.
    """
    if report_is_valid(attempt):
        return False
    if report_generation_failed_by_metadata(attempt):
        return True
    task = latest_speaking_report_task(attempt)
    return bool(task and task.status in _FAILED_REPORT_TASK_STATUSES)


# A healthy background worker claims a queued report within a few seconds and
# finishes the RUNNING phase within a couple of minutes. When the worker is
# offline or wedged the task just sits in ``pending``/``running`` forever, so the
# report screen would otherwise spin with no feedback. Past these windows we
# treat the attempt as stalled and surface a "未评分" card (with a 重新生成报告
# button) instead of letting the frontend hang. The RUNNING window matches the
# worker's own ``--recover-stale-seconds 900`` lease so we never flag a report
# that is still legitimately generating.
STALLED_PENDING_REPORT_AFTER_SECONDS = 180
STALLED_RUNNING_REPORT_AFTER_SECONDS = 900


def report_generation_stalled(attempt: SpeakingAttempt) -> bool:
    """Whether a queued report is stuck because no worker is processing it.

    Distinct from :func:`report_generation_failed`: the task never reached a
    terminal status, it is simply not being picked up (the AI worker is down).
    """
    if report_is_valid(attempt):
        return False
    task = latest_speaking_report_task(attempt)
    if task is None:
        return False
    if task.status == AITask.Status.PENDING:
        reference = task.available_at or task.created_at
        threshold = STALLED_PENDING_REPORT_AFTER_SECONDS
    elif task.status == AITask.Status.RUNNING:
        reference = task.started_at or task.available_at or task.created_at
        threshold = STALLED_RUNNING_REPORT_AFTER_SECONDS
    else:
        return False
    if reference is None:
        return False
    return (timezone.now() - reference).total_seconds() >= threshold


def friendly_report_error(raw: str) -> str:
    text = str(raw or "").strip()
    lowered = text.lower()
    if "quota" in lowered or "usage limit" in lowered or "rate limit" in lowered:
        return "AI 评分服务的额度已用尽，稍后额度恢复后点「重新生成报告」即可。"
    if "non-zero exit status" in lowered or "ai analysis failed" in lowered or not text:
        return "AI 评分服务暂时没有返回报告（可能是额度用尽或网络波动）。点「重新生成报告」重试，不会重开整场练习。"
    return text


def _attempt_turns_payload(attempt: SpeakingAttempt) -> list[dict[str, Any]]:
    return [
        {
            "id": turn.turn_id,
            "part": turn.part,
            "question": turn.question,
            "transcript_raw": turn.transcript_raw,
            "transcript_cleaned": turn.transcript_cleaned,
            "display_transcript": turn.metadata.get("display_transcript", "") if isinstance(turn.metadata, dict) else "",
            "status": "completed",
        }
        for turn in attempt.turns.all().order_by("sequence")
    ]


def failed_history_item(attempt: SpeakingAttempt) -> dict[str, Any]:
    return {
        "id": attempt.attempt_id,
        "timestamp": attempt.created_at.isoformat(),
        "display_time": timezone.localtime(attempt.created_at).strftime("%Y-%m-%d %H:%M"),
        "mode": attempt.mode,
        "part": attempt.part,
        "title": attempt.title or attempt.mode.upper(),
        "question": attempt.title,
        "status": attempt.status,
        "overall_band": None,
        "report_status": "failed",
        "turn_count": attempt.turns.count(),
    }


def failed_report_payload(attempt: SpeakingAttempt, *, stalled: bool = False) -> dict[str, Any]:
    task = latest_speaking_report_task(attempt)
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    raw_error = (
        (task.error_message if task else "")
        or metadata.get("report_generation_error")
        or metadata.get("analysis_error")
        or ""
    )
    report_error = (
        "报告还在排队，但后台 AI 评分服务暂时没有响应（worker 可能已离线）。点「重新生成报告」即可重试。"
        if stalled and not raw_error
        else friendly_report_error(raw_error)
    )
    return {
        "id": attempt.attempt_id,
        "mode": attempt.mode,
        "part": attempt.part,
        "title": attempt.title,
        "status": attempt.status,
        "report_status": "failed",
        "report_error": report_error,
        "display_time": timezone.localtime(attempt.created_at).strftime("%Y-%m-%d %H:%M"),
        "candidate": attempt.english_name,
        "full_name": attempt.full_name,
        "english_name": attempt.english_name,
        "ielts_score": {},
        "feedback_summary": "",
        "turns": _attempt_turns_payload(attempt),
        "ai_task": speaking_task_summary_payload(task),
    }


def history_item(attempt: SpeakingAttempt) -> dict[str, Any]:
    payload = attempt.report.report_payload if isinstance(attempt.report.report_payload, dict) else {}
    score = payload.get("ielts_score") if isinstance(payload.get("ielts_score"), dict) else {}
    return {
        "id": attempt.attempt_id,
        "timestamp": attempt.created_at.isoformat(),
        "display_time": timezone.localtime(attempt.created_at).strftime("%Y-%m-%d %H:%M"),
        "mode": attempt.mode,
        "part": attempt.part,
        "title": attempt.title or payload.get("title") or payload.get("question") or attempt.mode.upper(),
        "question": payload.get("question") or attempt.title,
        "status": attempt.status,
        "report_status": "ready",
        "overall_band": float(attempt.report.overall_band) if attempt.report.overall_band is not None else score.get("overall_band"),
        "turn_count": attempt.turns.count(),
    }


def history(user) -> dict[str, Any]:
    attempts = (
        SpeakingAttempt.objects.filter(user=user)
        .exclude(status=SpeakingAttempt.Status.ABORTED)
        .select_related("report")
        .prefetch_related("turns")
        .order_by("-created_at")
    )
    items: list[dict[str, Any]] = []
    for attempt in attempts:
        if report_is_valid(attempt):
            items.append(history_item(attempt))
        elif report_generation_failed_by_metadata(attempt):
            # Surface failed analyses as "未评分" cards with a 重新生成 button instead
            # of silently dropping them — otherwise the attempt vanishes from history.
            items.append(failed_history_item(attempt))
        elif report_generation_stalled(attempt):
            # Worker offline / wedged: the report task is stuck pending and will
            # never resolve on its own. Show it as 未评分 too so the just-recorded
            # attempt does not silently disappear from the list.
            items.append(failed_history_item(attempt))
    return {"items": items}


def detail(user, attempt_id: str) -> dict[str, Any]:
    attempt = (
        SpeakingAttempt.objects.filter(user=user, attempt_id=str(attempt_id or "").strip())
        .select_related("report")
        .prefetch_related("turns")
        .first()
    )
    if not attempt:
        raise SpeakingError("Speaking report not found")
    if report_is_valid(attempt):
        return report_payload(attempt)
    if report_generation_failed(attempt):
        return failed_report_payload(attempt)
    if report_generation_stalled(attempt):
        return failed_report_payload(attempt, stalled=True)
    raise SpeakingError("Speaking report not found")


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
