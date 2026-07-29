from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import sys
import threading
import time
from typing import Any

from django.db import close_old_connections, transaction
from django.db.utils import DatabaseError

from .models import SpeakingAttempt, SpeakingTurn
from .runtime_payload_services import _find_turn, _load_attempt_for_user
from .text_utils import clean_report_text
from .tts_services import cached_tts_url as _cached_tts_url
from .tts_services import volcengine_tts
from .turn_building_services import FIXED_EXAMINER_TTS_ITEMS


def _facade_attr(name: str, default: Any) -> Any:
    facade = sys.modules.get("apps.speaking.services")
    if facade is not None and hasattr(facade, name):
        return getattr(facade, name)
    return default


def _cached_examiner_url(role: str, cache_key: str) -> str | None:
    return _facade_attr("_cached_tts_url", _cached_tts_url)(role, cache_key)


def _volcengine_examiner_tts(text: str, *, role: str = "examiner", cache_key: str) -> dict[str, Any]:
    return _facade_attr("volcengine_tts", volcengine_tts)(text, role=role, cache_key=cache_key)


def _threading_module() -> Any:
    return _facade_attr("threading", threading)


def _fixed_examiner_item_for_text(text: str) -> dict[str, str] | None:
    normalized = " ".join(str(text or "").strip().lower().split())
    for item in FIXED_EXAMINER_TTS_ITEMS:
        if normalized == " ".join(item["text"].lower().split()):
            return item
    return None


def _fixed_examiner_pending_state(item: dict[str, str]) -> dict[str, Any]:
    return {
        "provider": "volcengine",
        "status": "warming",
        "audio_url": None,
        "message": f"Fixed examiner audio is warming in the background: {item['key']}",
    }


def _fixed_examiner_fallback(cache_key: str) -> dict[str, Any]:
    return {
        "provider": "browser",
        "status": "fallback",
        "audio_url": None,
        "message": f"Fixed examiner audio is using browser fallback for now: {cache_key}",
    }


def _warm_fixed_examiner_tts_item(item: dict[str, str]) -> dict[str, Any]:
    return _volcengine_examiner_tts(item["text"], role="examiner", cache_key=item["key"])


def _warm_fixed_examiner_tts_item_background(item: dict[str, str]) -> None:
    if _cached_examiner_url("examiner", item["key"]):
        return
    _threading_module().Thread(target=_warm_fixed_examiner_tts_item, args=(item,), daemon=True).start()


def _warm_fixed_examiner_tts_item_background_facade(item: dict[str, str]) -> None:
    _facade_attr("_warm_fixed_examiner_tts_item_background", _warm_fixed_examiner_tts_item_background)(item)


def _warm_fixed_examiner_tts_item_facade(item: dict[str, str]) -> dict[str, Any]:
    return _facade_attr("_warm_fixed_examiner_tts_item", _warm_fixed_examiner_tts_item)(item)


def _examiner_tts_text_hash(examiner_text: str) -> str:
    normalized = clean_report_text(examiner_text)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def _examiner_tts_cache_key(attempt_id: str, turn_id: str, examiner_text: str) -> str:
    # attempt_id and turn_id stay in the signature for existing call sites, but
    # examiner audio is text-bound and globally reusable.
    return f"examiner_{_examiner_tts_text_hash(examiner_text)}"


def _examiner_tts_identity(examiner_text: str, cache_key: str) -> dict[str, str]:
    return {
        "text_hash": _examiner_tts_text_hash(examiner_text),
        "cache_key": cache_key,
        "tts_source_text": clean_report_text(examiner_text),
    }


def _with_examiner_tts_identity(tts: dict[str, Any], examiner_text: str, cache_key: str) -> dict[str, Any]:
    return {
        **(tts or {}),
        **_examiner_tts_identity(examiner_text, cache_key),
    }


def _examiner_tts_not_started(message: str = "Examiner text is not ready yet.") -> dict[str, Any]:
    return {
        "provider": "volcengine",
        "status": "not_started",
        "audio_url": None,
        "message": message,
    }


def _examiner_tts_matches_text(tts: dict[str, Any], examiner_text: str) -> bool:
    if not isinstance(tts, dict) or not examiner_text:
        return False
    fixed_item = _fixed_examiner_item_for_text(examiner_text)
    if fixed_item and tts.get("cache_key") == fixed_item["key"]:
        return True
    return tts.get("text_hash") == _examiner_tts_text_hash(examiner_text)


def ensure_examiner_tts(attempt_id: str, turn: dict[str, Any]) -> None:
    """Ensure turn has examiner TTS audio_url generated."""
    current = turn.get("examiner_tts") or {}
    examiner_text = str(turn.get("examiner_text") or turn.get("question") or "")
    if not clean_report_text(examiner_text):
        turn["examiner_tts"] = _examiner_tts_not_started()
        return
    if current.get("audio_url") or current.get("status") not in (None, "pending"):
        if _examiner_tts_matches_text(current, examiner_text):
            return
    try:
        fixed_item = _fixed_examiner_item_for_text(examiner_text)
        if fixed_item:
            cached_url = _cached_examiner_url("examiner", fixed_item["key"])
            if cached_url:
                turn["examiner_tts"] = _with_examiner_tts_identity(
                    {
                        "provider": "volcengine",
                        "status": "cached",
                        "audio_url": cached_url,
                        "content_type": "audio/mpeg",
                    },
                    examiner_text,
                    fixed_item["key"],
                )
                return
            _warm_fixed_examiner_tts_item_background_facade(fixed_item)
            turn["examiner_tts"] = _with_examiner_tts_identity(
                _fixed_examiner_pending_state(fixed_item),
                examiner_text,
                fixed_item["key"],
            )
            return
        cache_key = _examiner_tts_cache_key(attempt_id, str(turn["id"]), examiner_text)
        turn["examiner_tts"] = _with_examiner_tts_identity(
            _volcengine_examiner_tts(
                examiner_text,
                role="examiner",
                cache_key=cache_key,
            ),
            examiner_text,
            cache_key,
        )
    except Exception as exc:
        cache_key = _examiner_tts_cache_key(attempt_id, str(turn["id"]), examiner_text)
        turn["examiner_tts"] = _with_examiner_tts_identity(
            {
                "provider": "volcengine",
                "status": "fallback",
                "audio_url": None,
                "message": f"Server TTS unavailable: {exc}",
            },
            examiner_text,
            cache_key,
        )


def _cached_examiner_tts_for_turn(attempt_id: str, turn_id: str, examiner_text: str) -> dict[str, Any] | None:
    fixed_item = _fixed_examiner_item_for_text(examiner_text)
    if fixed_item:
        cached_url = _cached_examiner_url("examiner", fixed_item["key"])
        if cached_url:
            return _with_examiner_tts_identity(
                {
                    "provider": "volcengine",
                    "status": "cached",
                    "audio_url": cached_url,
                    "content_type": "audio/mpeg",
                },
                examiner_text,
                fixed_item["key"],
            )
    cache_key = _examiner_tts_cache_key(attempt_id, turn_id, examiner_text)
    cached_url = _cached_examiner_url("examiner", cache_key)
    if cached_url:
        return _with_examiner_tts_identity(
            {
                "provider": "volcengine",
                "status": "cached",
                "audio_url": cached_url,
                "content_type": "audio/mpeg",
            },
            examiner_text,
            cache_key,
        )
    return None


def _generate_fixed_examiner_tts_now(fixed_item: dict[str, str], examiner_text: str) -> dict[str, Any]:
    cached_url = _cached_examiner_url("examiner", fixed_item["key"])
    if cached_url:
        return _with_examiner_tts_identity(
            {
                "provider": "volcengine",
                "status": "cached",
                "audio_url": cached_url,
                "content_type": "audio/mpeg",
            },
            examiner_text,
            fixed_item["key"],
        )
    try:
        tts = _warm_fixed_examiner_tts_item_facade(fixed_item)
    except Exception as exc:
        tts = {
            **_fixed_examiner_fallback(fixed_item["key"]),
            "message": f"Fixed examiner audio unavailable: {exc}",
        }
    return _with_examiner_tts_identity(tts, examiner_text, fixed_item["key"])


def warm_fixed_examiner_tts() -> dict[str, Any]:
    """Ensure fixed examiner prompts are cached before the learner starts."""
    items = []
    for item in FIXED_EXAMINER_TTS_ITEMS:
        tts = _warm_fixed_examiner_tts_item_facade(item)
        items.append(
            {
                "key": item["key"],
                "status": tts.get("status"),
                "audio_url": tts.get("audio_url"),
                "provider": tts.get("provider"),
            }
        )
    ready_urls = [item["audio_url"] for item in items if item.get("audio_url")]
    return {
        "items": items,
        "audio_urls": ready_urls,
        "ready_count": len(ready_urls),
    }


def warm_examiner_tts_for_attempt(user, attempt_id: str, turn_ids: list[str] | None = None) -> dict[str, Any]:
    """Queue every known examiner turn once and return its durable TTS state.

    This deliberately does not synthesize in the request thread: practice can
    enter its first question immediately while the bounded background pool
    prepares the remaining known P1/P3 prompts.
    """
    attempt = _load_attempt_for_user(user, attempt_id)
    requested_ids = list(dict.fromkeys(str(value or "").strip() for value in (turn_ids or []) if str(value or "").strip()))
    turns = list(attempt.turns.order_by("sequence"))
    by_id = {turn.turn_id: turn for turn in turns}
    selected_ids = requested_ids or [turn.turn_id for turn in turns]
    queued_ids: list[str] = []
    items: list[dict[str, Any]] = []

    for turn_id in selected_ids:
        turn = by_id.get(turn_id)
        if not turn:
            continue
        metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
        current = metadata.get("examiner_tts") if isinstance(metadata.get("examiner_tts"), dict) else {}
        examiner_text = str(metadata.get("examiner_text") or turn.question)
        if _is_stream_pending_follow_up_metadata(metadata):
            tts = {
                "provider": "volcengine",
                "status": "pending",
                "audio_url": None,
                "message": "Follow-up text is still generating; server TTS waits for the finalized question.",
            }
        elif not clean_report_text(examiner_text):
            tts = _examiner_tts_not_started()
        else:
            cached = _cached_examiner_tts_for_turn(attempt.attempt_id, turn.turn_id, examiner_text)
            if cached:
                tts = cached
            elif current.get("audio_url") and _examiner_tts_matches_text(current, examiner_text):
                tts = current
            else:
                fixed_item = _fixed_examiner_item_for_text(examiner_text)
                cache_key = (fixed_item or {}).get("key") or _examiner_tts_cache_key(attempt.attempt_id, turn.turn_id, examiner_text)
                tts = _with_examiner_tts_identity(
                    {"provider": "volcengine", "status": "pending", "audio_url": None},
                    examiner_text,
                    cache_key,
                )
                queued_ids.append(turn.turn_id)
        metadata["examiner_tts"] = tts
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])
        items.append({"turn_id": turn.turn_id, "examiner_tts": tts})

    if queued_ids:
        _generate_remaining_examiner_tts_after_commit(attempt.attempt_id, queued_ids)
    return {"attempt_id": attempt.attempt_id, "items": items, "queued_turn_ids": queued_ids}


def _generate_remaining_examiner_tts_after_commit(attempt_id: str, turn_ids: list[str]) -> None:
    clean_turn_ids = [str(turn_id) for turn_id in turn_ids if turn_id]
    if not clean_turn_ids:
        return

    def start_background_tts() -> None:
        _threading_module().Thread(
            target=_generate_remaining_examiner_tts,
            args=(str(attempt_id), clean_turn_ids),
            daemon=True,
        ).start()

    transaction.on_commit(start_background_tts)


def _generate_remaining_examiner_tts(attempt_id: str, turn_ids: list[str]) -> None:
    unique_turn_ids = list(dict.fromkeys(str(turn_id) for turn_id in turn_ids if turn_id))
    if not unique_turn_ids:
        return
    close_old_connections()
    try:
        db_turns = list(
            SpeakingTurn.objects.filter(attempt__attempt_id=attempt_id, turn_id__in=unique_turn_ids)
            .order_by("sequence")
        )
        work_items = []
        for db_turn in db_turns:
            metadata = db_turn.metadata if isinstance(db_turn.metadata, dict) else {}
            current = metadata.get("examiner_tts") if isinstance(metadata.get("examiner_tts"), dict) else {}
            examiner_text = str(metadata.get("examiner_text") or db_turn.question)
            if not clean_report_text(examiner_text):
                metadata["examiner_tts"] = _examiner_tts_not_started()
                db_turn.metadata = metadata
                db_turn.save(update_fields=["metadata", "updated_at"])
                continue
            if (
                (current.get("audio_url") or current.get("status") not in (None, "pending"))
                and _examiner_tts_matches_text(current, examiner_text)
            ):
                continue
            cache_key = (
                (_fixed_examiner_item_for_text(examiner_text) or {}).get("key")
                or _examiner_tts_cache_key(attempt_id, db_turn.turn_id, examiner_text)
            )
            metadata["examiner_tts"] = {
                **(current or {}),
                "provider": "volcengine",
                "status": "generating",
                "audio_url": None,
                **_examiner_tts_identity(examiner_text, cache_key),
            }
            db_turn.metadata = metadata
            db_turn.save(update_fields=["metadata", "updated_at"])
            work_items.append((db_turn, examiner_text))

        if not work_items:
            return
        with ThreadPoolExecutor(
            max_workers=min(3, len(work_items)),
            thread_name_prefix="speaking-examiner-tts",
        ) as executor:
            futures = [executor.submit(_synthesize_examiner_tts, attempt_id, db_turn, examiner_text) for db_turn, examiner_text in work_items]
            for (db_turn, examiner_text), future in zip(work_items, futures):
                try:
                    tts = future.result()
                except Exception as exc:
                    cache_key = _examiner_tts_cache_key(attempt_id, db_turn.turn_id, examiner_text)
                    tts = _with_examiner_tts_identity(
                        {"provider": "volcengine", "status": "fallback", "audio_url": None, "message": f"Server TTS unavailable: {exc}"},
                        examiner_text,
                        cache_key,
                    )
                metadata = db_turn.metadata if isinstance(db_turn.metadata, dict) else {}
                metadata["examiner_tts"] = tts
                db_turn.metadata = metadata
                db_turn.save(update_fields=["metadata", "updated_at"])
    except DatabaseError:
        return
    finally:
        close_old_connections()


def _synthesize_examiner_tts(attempt_id: str, db_turn: SpeakingTurn, examiner_text: str) -> dict[str, Any]:
    fixed_item = _fixed_examiner_item_for_text(examiner_text)
    if fixed_item:
        return _generate_fixed_examiner_tts_now(fixed_item, examiner_text)
    turn_data = {
        "id": db_turn.turn_id,
        "question": db_turn.question,
        "examiner_text": examiner_text,
        "examiner_tts": {"provider": "volcengine", "status": "pending", "audio_url": None},
    }
    ensure_examiner_tts(attempt_id, turn_data)
    return turn_data.get("examiner_tts") or _examiner_tts_not_started()


def _is_stream_pending_follow_up_metadata(metadata: dict[str, Any]) -> bool:
    prompt = metadata.get("prompt") if isinstance(metadata.get("prompt"), dict) else {}
    return (
        prompt.get("role") == "follow_up"
        and (
            prompt.get("backend") == "stream_pending"
            or prompt.get("generation_status") == "pending"
        )
    )


def examiner_tts_status(user, attempt_id: str, turn_id: str) -> dict[str, Any]:
    """Return the latest examiner TTS state, generating it once when pending."""
    started = time.monotonic()
    attempt = _load_attempt_for_user(user, attempt_id)
    turn = _find_turn(attempt, turn_id)
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    current = metadata.get("examiner_tts") if isinstance(metadata.get("examiner_tts"), dict) else {}
    tts = current or {"provider": "volcengine", "status": "pending", "audio_url": None}
    if _is_stream_pending_follow_up_metadata(metadata):
        tts = {
            "provider": "volcengine",
            "status": "pending",
            "audio_url": None,
            "message": "Follow-up text is still generating; server TTS waits for the finalized question.",
        }
        metadata["examiner_tts"] = tts
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])
        return {
            "attempt_id": attempt.attempt_id,
            "turn_id": turn.turn_id,
            "examiner_tts": {
                **tts,
                "refresh_latency_ms": int((time.monotonic() - started) * 1000),
            },
        }
    examiner_text = str(metadata.get("examiner_text") or turn.question)
    if not clean_report_text(examiner_text):
        tts = _examiner_tts_not_started()
        metadata["examiner_tts"] = tts
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])
        return {
            "attempt_id": attempt.attempt_id,
            "turn_id": turn.turn_id,
            "examiner_tts": {
                **tts,
                "refresh_latency_ms": int((time.monotonic() - started) * 1000),
            },
        }
    if tts and not _examiner_tts_matches_text(tts, examiner_text):
        cache_key = (
            (_fixed_examiner_item_for_text(examiner_text) or {}).get("key")
            or _examiner_tts_cache_key(attempt.attempt_id, turn.turn_id, examiner_text)
        )
        tts = {
            "provider": "volcengine",
            "status": "pending",
            "audio_url": None,
            **_examiner_tts_identity(examiner_text, cache_key),
        }
        metadata["examiner_tts"] = tts
    cached_tts = _cached_examiner_tts_for_turn(attempt.attempt_id, turn.turn_id, examiner_text)
    if cached_tts:
        tts = cached_tts
        metadata["examiner_tts"] = tts
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])
    elif not tts.get("audio_url"):
        cache_key = (
            (_fixed_examiner_item_for_text(examiner_text) or {}).get("key")
            or _examiner_tts_cache_key(attempt.attempt_id, turn.turn_id, examiner_text)
        )
        fixed_item = _fixed_examiner_item_for_text(examiner_text)
        if fixed_item:
            tts = _generate_fixed_examiner_tts_now(fixed_item, examiner_text)
        else:
            turn_data = {
                "id": turn.turn_id,
                "question": turn.question,
                "examiner_text": examiner_text,
                "examiner_tts": {
                    "provider": "volcengine",
                    "status": "pending",
                    "audio_url": None,
                    **_examiner_tts_identity(examiner_text, cache_key),
                },
            }
            ensure_examiner_tts(attempt.attempt_id, turn_data)
            tts = turn_data.get("examiner_tts") or tts
        metadata["examiner_tts"] = tts
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])
    return {
        "attempt_id": attempt.attempt_id,
        "turn_id": turn.turn_id,
        "examiner_tts": {
            **tts,
            "refresh_latency_ms": int((time.monotonic() - started) * 1000),
        },
    }


__all__ = [
    "_fixed_examiner_item_for_text",
    "_fixed_examiner_pending_state",
    "_fixed_examiner_fallback",
    "_warm_fixed_examiner_tts_item",
    "_warm_fixed_examiner_tts_item_background",
    "_examiner_tts_text_hash",
    "_examiner_tts_cache_key",
    "_examiner_tts_identity",
    "_with_examiner_tts_identity",
    "_examiner_tts_not_started",
    "_examiner_tts_matches_text",
    "ensure_examiner_tts",
    "_cached_examiner_tts_for_turn",
    "warm_fixed_examiner_tts",
    "warm_examiner_tts_for_attempt",
    "_generate_remaining_examiner_tts_after_commit",
    "_generate_remaining_examiner_tts",
    "_is_stream_pending_follow_up_metadata",
    "examiner_tts_status",
]
