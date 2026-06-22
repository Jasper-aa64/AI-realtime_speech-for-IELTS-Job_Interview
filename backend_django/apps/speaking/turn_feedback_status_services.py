"""Turn-level feedback status lifecycle helpers.

Extracted from ``services.py``. These functions stamp per-turn ``metadata`` with
the AI-feedback generation state (pending / failed) and reconcile dropped or
unanswered turns at scoring time, so a report can publish honestly instead of
looping on "重新分析". They read/write ``SpeakingTurn.metadata`` only.
"""

from __future__ import annotations

from .ai_provider_services import SPEAKING_READY_AI_BACKENDS
from .models import SpeakingTurn
from .runtime_payload_services import _turn_status
from .scoring_services import is_p1_name_intro_turn, is_p1_work_study_intro_turn
from .text_utils import clean_report_text


def mark_missing_turn_feedback_pending(turns: list[SpeakingTurn]) -> None:
    """Keep report payloads honest when turn-level AI feedback is not ready."""
    for turn in turns:
        transcript = (turn.transcript_cleaned or turn.transcript_raw or "").strip()
        if not transcript or is_p1_name_intro_turn(turn) or is_p1_work_study_intro_turn(turn):
            continue
        metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
        if metadata.get("feedback_generation_backend") in SPEAKING_READY_AI_BACKENDS and metadata.get("feedback_generation_status") == "ready":
            continue
        metadata.update(
            {
                "band7_version": "",
                "band7_markdown": "",
                "target_band_version": "",
                "target_band_markdown": "",
                "model_audio": {"provider": "none", "status": "pending", "audio_url": None},
                "ai_coaching": "",
                "feedback_generation_backend": "codex",
                "feedback_generation_status": "pending",
                "band7_source": "pending",
                "ai_coaching_source": "pending",
            }
        )
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])


def complete_dropped_turns(turns: list[SpeakingTurn]) -> int:
    """At scoring time, any turn that never reached "completed" is a dropped
    recording (the audio/transcript never landed). Instead of blocking the whole
    section report forever — which left the learner stuck on an endless "重新分析"
    loop — mark each such turn completed-but-empty so the report can publish.

    An empty turn then flows through the existing empty-answer path: its row in the
    transcript table stays blank, the AI still writes a Band 7 model answer from the
    question alone, and coaching is suppressed (`turn_needs_ai_coaching` -> False,
    "为空 → 本次不辅导"). Returns how many turns were auto-completed.
    """
    dropped = 0
    for turn in turns:
        if _turn_status(turn) == "completed":
            continue
        metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
        metadata["status"] = "completed"
        metadata["dropped_empty"] = True
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])
        dropped += 1
    return dropped


def _turn_feedback_ready(turn: SpeakingTurn) -> bool:
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    return (
        metadata.get("feedback_generation_backend") in SPEAKING_READY_AI_BACKENDS
        and metadata.get("feedback_generation_status") == "ready"
        and bool(clean_report_text(metadata.get("band7_version") or metadata.get("band7_markdown") or ""))
    )


def _mark_turn_feedback_failed(turns: list[SpeakingTurn], exc: Exception) -> None:
    error = str(exc or "AI turn feedback generation failed")
    for turn in turns:
        transcript = (turn.transcript_cleaned or turn.transcript_raw or "").strip()
        if not transcript or is_p1_name_intro_turn(turn) or is_p1_work_study_intro_turn(turn):
            continue
        metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
        metadata.update(
            {
                "band7_version": "",
                "band7_markdown": "",
                "target_band_version": "",
                "target_band_markdown": "",
                "model_audio": {"provider": "none", "status": "empty_text", "audio_url": None},
                "ai_coaching": "",
                "feedback_generation_backend": "codex",
                "feedback_generation_status": "failed",
                "feedback_generation_error": error,
                "band7_source": "failed",
                "ai_coaching_source": "failed",
            }
        )
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])
