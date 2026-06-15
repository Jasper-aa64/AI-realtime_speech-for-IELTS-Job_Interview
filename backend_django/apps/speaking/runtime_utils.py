"""Runtime payload and metric helpers for speaking sessions."""

from __future__ import annotations

import json
from typing import Any

from .text_utils import clean_report_text

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        return default
    return numeric

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default

def _sanitize_audio_preprocessing_metrics(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not value.get("enabled"):
        return None
    total_frames = _safe_int(value.get("total_frames"))
    speech_frames = min(total_frames, _safe_int(value.get("speech_frames")))
    silence_frames = min(total_frames, _safe_int(value.get("silence_frames"), total_frames - speech_frames))
    if total_frames and speech_frames + silence_frames != total_frames:
        silence_frames = max(0, total_frames - speech_frames)
    speech_ratio = round(_safe_float(value.get("speech_ratio")), 6)
    silence_ratio = round(_safe_float(value.get("silence_ratio")), 6)
    if total_frames:
        speech_ratio = round(speech_frames / total_frames, 6)
        silence_ratio = round(silence_frames / total_frames, 6)
    return {
        "enabled": True,
        "analyzer": clean_report_text(str(value.get("analyzer") or ""))[:80],
        "fallback_analyzer": clean_report_text(str(value.get("fallback_analyzer") or ""))[:80],
        "fallback_reason": clean_report_text(str(value.get("fallback_reason") or ""))[:300],
        "total_frames": total_frames,
        "speech_frames": speech_frames,
        "silence_frames": silence_frames,
        "speech_ratio": speech_ratio,
        "silence_ratio": silence_ratio,
        "latest_rms": round(_safe_float(value.get("latest_rms")), 6),
        "latest_peak": round(_safe_float(value.get("latest_peak")), 6),
        "latest_speech": bool(value.get("latest_speech")),
        "sample_rate": _safe_int(value.get("sample_rate")),
        "frame_size": _safe_int(value.get("frame_size")),
        "started_at_ms": round(_safe_float(value.get("started_at_ms")), 3),
        "stopped_at_ms": round(_safe_float(value.get("stopped_at_ms")), 3),
        "last_error": clean_report_text(str(value.get("last_error") or ""))[:300],
    }

def _sanitize_realtime_asr_metrics(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not value.get("enabled"):
        return None

    status = clean_report_text(str(value.get("status") or ""))[:80]
    asr_status = clean_report_text(str(value.get("asrStatus") or value.get("asr_status") or ""))[:80]
    transcript_source = clean_report_text(str(value.get("transcriptSource") or value.get("transcript_source") or ""))[:80]
    asr_provider = clean_report_text(str(value.get("asrProvider") or value.get("asr_provider") or ""))[:80]
    last_error = clean_report_text(str(value.get("lastError") or value.get("last_error") or ""))[:300]

    frames_sent = _safe_int(value.get("framesSent", value.get("frames_sent")))
    frames_acked = _safe_int(value.get("framesAcked", value.get("frames_acked")))
    dropped_frames = _safe_int(value.get("droppedFrames", value.get("dropped_frames")))
    bytes_sent = _safe_int(value.get("bytesSent", value.get("bytes_sent")))
    bytes_acked = _safe_int(value.get("bytesAcked", value.get("bytes_acked")))

    return {
        "enabled": True,
        "running": bool(value.get("running")),
        "status": status,
        "asr_status": asr_status,
        "asr_configured": bool(value.get("asrConfigured", value.get("asr_configured"))),
        "asr_enabled": bool(value.get("asrEnabled", value.get("asr_enabled"))),
        "asr_provider": asr_provider,
        "transcript_source": transcript_source,
        "frames_sent": frames_sent,
        "frames_acked": min(frames_sent, frames_acked) if frames_sent else frames_acked,
        "dropped_frames": dropped_frames,
        "bytes_sent": bytes_sent,
        "bytes_acked": min(bytes_sent, bytes_acked) if bytes_sent else bytes_acked,
        "asr_status_check_ms": _safe_int(value.get("asrStatusCheckMs", value.get("asr_status_check_ms"))),
        "socket_open_ms": _safe_int(value.get("socketOpenMs", value.get("socket_open_ms"))),
        "first_asr_event_ms": _safe_int(value.get("firstAsrEventMs", value.get("first_asr_event_ms"))),
        "first_transcript_ms": _safe_int(value.get("firstTranscriptMs", value.get("first_transcript_ms"))),
        "final_transcript_ms": _safe_int(value.get("finalTranscriptMs", value.get("final_transcript_ms"))),
        "done_ms": _safe_int(value.get("doneMs", value.get("done_ms"))),
        "last_error": last_error,
    }

def _sse_payload(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
