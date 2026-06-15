from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from .corpus_services import p1_question_id
from .exceptions import SpeakingError
from .models import SpeakingAttempt, SpeakingTurn
from .text_utils import clean_report_text
from .turn_building_services import _timers_for_part


def _turn_status(turn: SpeakingTurn) -> str:
    status = str(turn.metadata.get("status") or "").strip()
    if status:
        return status
    if turn.transcript_cleaned or turn.transcript_raw:
        return "completed"
    if turn.audio_path:
        return "audio_uploaded"
    return "pending"


def _spoken_markdown(text: str) -> str:
    cleaned = clean_report_text(text)
    return cleaned


def _turn_payload(turn: SpeakingTurn, total: int | None = None) -> dict[str, Any]:
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    prompt = metadata.get("prompt") if isinstance(metadata.get("prompt"), dict) else {"question": turn.question}
    cue_card = metadata.get("cue_card") if isinstance(metadata.get("cue_card"), dict) else None
    timers = metadata.get("timers") if isinstance(metadata.get("timers"), dict) else _timers_for_part(turn.part)
    audio = None
    if turn.audio_path:
        audio = {
            "path": str(Path(settings.MEDIA_ROOT) / turn.audio_path),
            "content_type": metadata.get("audio_content_type", "application/octet-stream"),
            "bytes": metadata.get("audio_bytes"),
            "duration_seconds": float(turn.duration_seconds) if turn.duration_seconds is not None else None,
            "url": f"/api/audio/{turn.attempt.attempt_id}/{turn.turn_id}/candidate",
        }
    return {
        "id": turn.turn_id,
        "part": turn.part,
        "index": max(0, int(turn.sequence or 0)),
        "total": total if total is not None else turn.attempt.turns.count(),
        "status": _turn_status(turn),
        "question": turn.question,
        "prompt": prompt,
        "cue_card": cue_card,
        "timers": timers,
        "examiner_text": metadata.get("examiner_text") or turn.question,
        "examiner_behavior": metadata.get("examiner_behavior") or "auto_play_question",
        "examiner_tts": metadata.get("examiner_tts") or {"provider": "volcengine", "status": "pending", "audio_url": None},
        "audio": audio,
        "transcript_raw": turn.transcript_raw,
        "transcript_cleaned": turn.transcript_cleaned,
        "display_transcript": metadata.get("display_transcript", ""),
        "display_transcript_markdown": metadata.get("display_transcript_markdown", ""),
        "transcript_markdown": metadata.get("transcript_markdown") or _spoken_markdown(turn.transcript_cleaned or turn.transcript_raw),
        "transcript_status": metadata.get("transcript_status") or ("captured" if (turn.transcript_cleaned or turn.transcript_raw) else "missing"),
        "transcript_source": turn.transcript_source or metadata.get("transcript_source", ""),
        "duration_seconds": float(turn.duration_seconds) if turn.duration_seconds is not None else None,
        "band7_version": metadata.get("band7_version", ""),
        "band7_markdown": metadata.get("band7_markdown", metadata.get("band7_version", "")),
        "model_audio": metadata.get("model_audio"),
        "upgrade_notes": metadata.get("upgrade_notes", []),
        "ai_coaching": metadata.get("ai_coaching", ""),
        "target_band_version": metadata.get("target_band_version", metadata.get("band7_version", "")),
        "target_band_markdown": metadata.get("target_band_markdown", metadata.get("band7_markdown", metadata.get("band7_version", ""))),
        "target_band": metadata.get("target_band"),
        "feedback_generation_status": metadata.get("feedback_generation_status"),
        "feedback_generation_backend": metadata.get("feedback_generation_backend"),
        "feedback_generation_error": metadata.get("feedback_generation_error"),
        "band7_source": metadata.get("band7_source"),
        "ai_coaching_source": metadata.get("ai_coaching_source"),
        "audio_preprocessing_metrics": metadata.get("audio_preprocessing_metrics") if isinstance(metadata.get("audio_preprocessing_metrics"), dict) else None,
        "realtime_asr_metrics": metadata.get("realtime_asr_metrics") if isinstance(metadata.get("realtime_asr_metrics"), dict) else None,
        "counts_toward_total": turn.counts_toward_total,
        "display_index": metadata.get("display_index"),
        "question_id": prompt.get("question_id") or p1_question_id(str(prompt.get("topic") or "general"), turn.question) if turn.part == "p1" else "",
        "topic": prompt.get("topic", ""),
        "p2_corpus_link": metadata.get("p2_corpus_link") if isinstance(metadata.get("p2_corpus_link"), dict) else None,
    }


def _runtime_attempt_payload(attempt: SpeakingAttempt) -> dict[str, Any]:
    turns = list(attempt.turns.all().order_by("sequence"))
    total = len(turns)
    turn_payloads = [_turn_payload(turn, total) for turn in turns]
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    current_turn = metadata.get("current_turn")
    if attempt.status == SpeakingAttempt.Status.STARTED and not current_turn:
        next_turn = next((turn for turn in turn_payloads if turn.get("status") != "completed"), None)
        current_turn = next_turn.get("id") if next_turn else None
    return {
        "id": attempt.attempt_id,
        "timestamp": attempt.created_at.isoformat(),
        "display_time": timezone.localtime(attempt.updated_at).strftime("%Y-%m-%d %H:%M"),
        "status": attempt.status,
        "user_id": str(attempt.user_id),
        "mode": attempt.mode,
        "part": attempt.part,
        "title": attempt.title,
        "question": turn_payloads[0]["question"] if turn_payloads else "",
        "cue_card": metadata.get("cue_card"),
        "turns": turn_payloads,
        "current_turn": current_turn,
        "candidate": attempt.english_name,
        "full_name": attempt.full_name,
        "english_name": attempt.english_name,
        "pronunciation": {"provider": "azure", "status": "pending"},
        "ielts_score": None,
        "feedback_summary": "",
        "criteria_feedback": {},
        "band7_version": "",
        "model_audio": None,
        "upgrade_notes": [],
        "ai_coaching": "",
        **{key: value for key, value in metadata.items() if key.startswith("p3_")},
    }


def _load_attempt_for_user(user, attempt_id: str) -> SpeakingAttempt:
    attempt = (
        SpeakingAttempt.objects.filter(user=user, attempt_id=str(attempt_id or "").strip())
        .prefetch_related("turns")
        .first()
    )
    if not attempt:
        raise SpeakingError("Attempt not found")
    return attempt


def _find_turn(attempt: SpeakingAttempt, turn_id: str) -> SpeakingTurn:
    turn = next((item for item in attempt.turns.all() if item.turn_id == str(turn_id or "").strip()), None)
    if not turn:
        raise SpeakingError("Turn not found")
    return turn
