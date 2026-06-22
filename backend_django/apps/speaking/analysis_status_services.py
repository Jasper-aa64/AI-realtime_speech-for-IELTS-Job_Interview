"""Fallback scoring and attempt analysis-status persistence.

Extracted from ``services.py``. These helpers cover the "things went wrong (or
we have no AI scorer)" path: a heuristic fallback score, the report-facing
fallback wrapper, and the two functions that stamp an attempt's metadata with a
ready / failed analysis state so polling never shows a stale status.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from .ai_provider_services import SPEAKING_READY_AI_BACKENDS
from .models import SpeakingAttempt
from .scoring_services import (
    _word_count,
    calibrate_realistic_score,
    cap_off_topic_score,
)


def build_upgrade_notes(transcript: str) -> list[str]:
    """Keep legacy table shape without rule-heavy vocabulary diagnostics."""
    return []


def _fallback_score(transcript: str, part: str) -> dict[str, Any]:
    words = _word_count(transcript)
    if words >= 220:
        base = 6.0
    elif words >= 120:
        base = 5.5
    elif words >= 60:
        base = 5.0
    elif words >= 25:
        base = 4.5
    else:
        base = 4.0
    if part == "p2" and words < 80:
        base = min(base, 5.0)
    if part == "p3" and words < 100:
        base = min(base, 5.0)
    return {
        "overall_band": base,
        "fluency_coherence": base,
        "lexical_resource": max(4.0, base - 0.5),
        "grammatical_range": max(4.0, base - 0.5),
        "pronunciation_estimate": None,
        "feedback": "Fallback score generated from completed browser transcripts. Configure the full AI scorer for richer feedback.",
        "backend": "fallback",
        "word_count": words,
    }


def fallback_score_for_report(transcript: str, questions_text: str, part: str, exc: Exception, call_id: str) -> dict[str, Any]:
    """Build an explicit fallback score after a real Codex scoring failure."""
    reason = f"Codex scoring failed: {exc}"
    score = _fallback_score(transcript, part)
    score["feedback"] = f"{score['feedback']} Fallback reason: {reason}"
    score["backend"] = "fallback"
    score["generation_backend"] = "fallback"
    score["generation_status"] = "fallback"
    score["fallback_reason"] = reason
    score["codex_call_id"] = call_id
    return cap_off_topic_score(calibrate_realistic_score(score, questions_text, transcript, part), questions_text, transcript)


def mark_attempt_analysis_failed(attempt: SpeakingAttempt, exc: Exception, call_id: str) -> None:
    """Persist a failed AI-analysis state without publishing a fake report."""
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    metadata.update(
        {
            "analysis_status": "failed",
            "analysis_backend": "codex",
            "analysis_error": str(exc),
            "analysis_call_id": call_id,
            "analysis_failed_at": timezone.now().isoformat(),
            "score_generation_backend": "codex",
            "score_generation_status": "failed",
            "score_generation_error": str(exc),
            "report_generation_backend": "codex",
            "report_generation_status": "failed",
        }
    )
    attempt.metadata = metadata
    if attempt.status != SpeakingAttempt.Status.SCORED:
        attempt.status = SpeakingAttempt.Status.READY_TO_SCORE
        attempt.save(update_fields=["status", "metadata", "updated_at"])
    else:
        attempt.save(update_fields=["metadata", "updated_at"])


def mark_attempt_analysis_ready(attempt: SpeakingAttempt, score: dict[str, Any], call_id: str) -> None:
    """Persist successful AI-analysis state so polling never shows stale queued/failed status."""
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    backend = str(score.get("generation_backend") or score.get("backend") or "codex")
    status = str(score.get("generation_status") or ("ready" if backend in SPEAKING_READY_AI_BACKENDS else "fallback"))
    metadata.update(
        {
            "analysis_status": "ready",
            "analysis_backend": backend,
            "analysis_error": "",
            "analysis_call_id": call_id,
            "analysis_ready_at": timezone.now().isoformat(),
            "score_generation_backend": backend,
            "score_generation_status": status,
            "score_generation_error": str(score.get("fallback_reason") or ""),
            "report_generation_backend": str(score.get("backend") or backend),
            "report_generation_status": "ready" if status == "ready" else status,
        }
    )
    attempt.metadata = metadata
