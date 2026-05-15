from __future__ import annotations

import hashlib
import json
import random
import uuid
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models import Avg, Count, Max, Min, Sum
from django.utils import timezone

from .models import SpeakingAttempt, SpeakingReport, SpeakingTrainingObservation, SpeakingTurn


class QuestionBank:
    """Load IELTS speaking questions from JSON files."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or Path(settings.BASE_DIR).parent / "data" / "ielts"
        self.p1: list[dict[str, Any]] = []
        self.p2: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        self.p1 = self._load_p1()
        self.p2 = self._load_p2()

    def _load_p1(self) -> list[dict[str, Any]]:
        part_dir = self.data_dir / "part1"
        if not part_dir.is_dir():
            return []
        questions: list[dict[str, Any]] = []
        for path in sorted(part_dir.glob("*.json")):
            payload = self._read_json(path)
            if payload.get("part") != 1:
                continue
            items = payload.get("questions")
            if not isinstance(items, list):
                continue
            topic = str(payload.get("topic") or path.stem)
            for item in items:
                if isinstance(item, str) and item.strip():
                    questions.append({"topic": topic, "question": item.strip()})
        return questions

    def _load_p2(self) -> list[dict[str, Any]]:
        part_dir = self.data_dir / "part2"
        if not part_dir.is_dir():
            return []
        topics: list[dict[str, Any]] = []
        for path in sorted(part_dir.glob("*.json")):
            payload = self._read_json(path)
            if payload.get("part") != 2:
                continue
            items = payload.get("topics")
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and item.get("title"):
                    topics.append(item)
        return topics

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def summary(self) -> dict[str, Any]:
        return {
            "part1_count": len(self.p1),
            "part2_count": len(self.p2),
            "part1_topics": sorted({item["topic"] for item in self.p1}),
            "part2_themes": sorted({item.get("p3_theme", "") for item in self.p2 if item.get("p3_theme")}),
        }

    def sample(self, p1_count: int = 5) -> dict[str, Any]:
        p1_count = max(1, min(p1_count, len(self.p1)))
        result = {}
        if self.p1:
            result["part1"] = random.sample(self.p1, p1_count)
        if self.p2:
            result["part2"] = random.choice(self.p2)
        return result


_question_bank: QuestionBank | None = None


def get_question_bank() -> QuestionBank:
    global _question_bank
    if _question_bank is None:
        _question_bank = QuestionBank()
    return _question_bank


def question_bank_summary() -> dict[str, Any]:
    return get_question_bank().summary()


def question_bank_sample(p1_count: int = 5) -> dict[str, Any]:
    return get_question_bank().sample(p1_count)


class SpeakingError(ValueError):
    pass


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
    return payload


def history_item(attempt: SpeakingAttempt) -> dict[str, Any]:
    payload = attempt.report.report_payload if isinstance(attempt.report.report_payload, dict) else {}
    score = payload.get("ielts_score") if isinstance(payload.get("ielts_score"), dict) else {}
    return {
        "id": attempt.attempt_id,
        "timestamp": attempt.created_at.isoformat(),
        "display_time": attempt.updated_at.isoformat(),
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


# --- Attempt Start ---

P1_TURN_COUNT = 10
P3_MAIN_COUNT = 5
P3_TURN_COUNT = 10
DEFAULT_FULL_NAME = "LiHua"
DEFAULT_ENGLISH_NAME = "Jasper"

P1_INTRO_QUESTIONS: list[dict[str, Any]] = [
    {
        "topic": "intro",
        "question": "What is your full name?",
        "flow": "intro",
        "role": "name",
        "counts_toward_total": False,
    },
    {
        "topic": "intro",
        "question": "Do you work or do you study?",
        "flow": "intro",
        "role": "work_study",
        "counts_toward_total": True,
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
    return (
        "I'm going to give you a topic and I would like you to talk about it for one to two minutes. "
        "You have one minute to think about what you are going to say. "
        "You can make some notes if you wish."
    )


def _fallback_p3(theme: str, count: int = P3_MAIN_COUNT) -> dict[str, Any]:
    label = theme.replace("_", " ").strip() or "this topic"
    questions = [
        f"Why do people have different opinions about {label}?",
        f"How has {label} changed in your country in recent years?",
        f"Do you think {label} will become more important in the future?",
        f"What problems can {label} create for ordinary people?",
        f"How should governments or schools respond to changes in {label}?",
    ]
    follow_up = "Could you give a specific example to support that view?"
    return {"questions": questions[:count], "follow_up": follow_up}


def _timers_for_part(part: str) -> dict[str, Any]:
    defaults = {"prepare": 0, "speak": 0}
    if part == "p1":
        return {"prepare": 5, "speak": 30}
    if part == "p2":
        return {"prepare": 60, "speak": 120}
    if part == "p3":
        return {"prepare": 5, "speak": 45}
    return defaults


def _create_turn(
    part: str,
    index: int,
    total: int,
    question: str,
    prompt: dict[str, Any] | None = None,
    cue_card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    turn_id = f"t{index + 1}"
    examiner_text = _cue_examiner_text() if part == "p2" and cue_card else question
    examiner_behavior = "auto_play_instruction_only" if part == "p2" and cue_card else "auto_play_question"
    return {
        "id": turn_id,
        "part": part,
        "index": index,
        "total": total,
        "status": "pending",
        "question": question,
        "prompt": prompt or {"question": question},
        "cue_card": cue_card,
        "timers": _timers_for_part(part),
        "examiner_text": examiner_text,
        "examiner_behavior": examiner_behavior,
        "examiner_tts": {"provider": "volcengine", "status": "pending", "audio_url": None},
        "audio": None,
        "transcript_raw": "",
        "transcript_cleaned": "",
        "transcript_markdown": "",
        "transcript_status": "missing",
        "duration_seconds": None,
        "band7_version": "",
        "band7_markdown": "",
        "model_audio": None,
        "upgrade_notes": [],
        "ai_coaching": "",
    }


def _build_p1_turns(total: int = P1_TURN_COUNT, display_total: int | None = None) -> list[dict[str, Any]]:
    bank = get_question_bank()
    countable_intro_items = [item for item in P1_INTRO_QUESTIONS if item.get("counts_toward_total", True)]
    uncounted_intro_items = [item for item in P1_INTRO_QUESTIONS if not item.get("counts_toward_total", True)]
    remaining_count = max(0, total - len(countable_intro_items))
    ordinary_pool = [
        item for item in bank.p1 if not _is_p1_work_study_identity_question(str(item.get("question") or ""))
    ]
    if len(ordinary_pool) < remaining_count:
        ordinary_pool = bank.p1
    if not ordinary_pool:
        ordinary_pool = [
            {"topic": "general", "question": "What do you like to do in your free time?"},
            {"topic": "general", "question": "Do you prefer mornings or evenings?"},
            {"topic": "general", "question": "Tell me about your hometown."},
            {"topic": "general", "question": "What kind of music do you enjoy?"},
            {"topic": "general", "question": "Do you like traveling?"},
            {"topic": "general", "question": "What is your favorite food?"},
            {"topic": "general", "question": "How do you usually spend your weekends?"},
            {"topic": "general", "question": "Do you prefer reading or watching movies?"},
            {"topic": "general", "question": "What is the weather like in your country?"},
            {"topic": "general", "question": "Do you have any hobbies?"},
        ]
    ordinary_questions = random.sample(ordinary_pool, min(remaining_count, len(ordinary_pool)))
    turn_items = uncounted_intro_items + countable_intro_items + ordinary_questions
    turns: list[dict[str, Any]] = []
    display_index = 0
    for index, item in enumerate(turn_items):
        counts_toward_total = bool(item.get("counts_toward_total", True))
        if counts_toward_total:
            display_index += 1
        turn = _create_turn(
            "p1",
            index,
            display_total or total,
            item["question"],
            {
                "topic": item["topic"],
                "question": item["question"],
                "counts_toward_total": counts_toward_total,
                **({"flow": item["flow"], "role": item["role"]} if item.get("flow") else {}),
            },
        )
        turn["counts_toward_total"] = counts_toward_total
        turn["display_index"] = display_index if counts_toward_total else 0
        turns.append(turn)
    return turns


def _build_p3_turns(theme: str, intensity: str = "high") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    plan = _fallback_p3(theme, P3_MAIN_COUNT)
    questions = [str(q).strip() for q in plan.get("questions", []) if str(q).strip()][:P3_MAIN_COUNT]
    use_follow_ups = intensity == "high"
    total = P3_TURN_COUNT if use_follow_ups else P3_MAIN_COUNT
    turns: list[dict[str, Any]] = []
    for main_index, question in enumerate(questions):
        main_turn = _create_turn(
            "p3",
            len(turns),
            total,
            question,
            {"theme": theme, "question": question, "role": "main", "source": "topic"},
        )
        turns.append(main_turn)
        if use_follow_ups:
            follow_up = plan.get("follow_up", "Could you give a specific example to support that view?")
            follow_turn = _create_turn(
                "p3",
                len(turns),
                total,
                str(follow_up),
                {
                    "theme": theme,
                    "question": str(follow_up),
                    "role": "follow_up",
                    "after_main": main_index + 1,
                    "source": "topic",
                },
            )
            turns.append(follow_turn)
    metadata = {
        "p3_generation_status": "fallback",
        "p3_generation_source": "topic",
        "p3_generation_backend": "fallback",
        "p3_theme": theme,
        "p3_intensity": intensity,
    }
    return turns, metadata


def _build_turns(mode: str, payload: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
    bank = get_question_bank()
    metadata: dict[str, Any] = {}
    if mode == "mock":
        cue = bank.p2[0] if bank.p2 else {"title": "Describe a person you admire", "bullets": [], "rounding": ""}
        p1_turns = _build_p1_turns(P1_TURN_COUNT, P1_TURN_COUNT + 1)
        p2_turn = _create_turn("p2", len(p1_turns), P1_TURN_COUNT + 1, _cue_to_text(cue), cue, cue)
        turns = p1_turns + [p2_turn]
        metadata = {
            "p3_generation_status": "pending_after_p2",
            "p3_generation_source": "p2_answer",
            "p3_theme": str(cue.get("p3_theme") or cue.get("title") or "general speaking"),
        }
        return "mock", "Full mock exam", turns, cue, metadata
    if mode == "p1":
        turns = _build_p1_turns(P1_TURN_COUNT)
        return "p1", "Part 1 practice", turns, None, metadata
    if mode == "p2":
        cue = bank.p2[0] if bank.p2 else {"title": "Describe a person you admire", "bullets": [], "rounding": ""}
        turns = [_create_turn("p2", 0, 1, _cue_to_text(cue), cue, cue)]
        return "p2", str(cue.get("title", "Part 2 practice")), turns, cue, metadata
    if mode == "p3":
        theme = str(payload.get("theme") or payload.get("topic") or "society and daily life").strip()
        intensity = str(payload.get("p3_intensity") or payload.get("intensity") or "high").strip().lower()
        if intensity not in {"normal", "high"}:
            intensity = "high"
        turns, metadata = _build_p3_turns(theme, intensity)
        return "p3", f"Part 3 discussion: {theme}", turns, None, metadata
    raise ValueError(f"Unsupported mode: {mode}")


def _candidate_names_from_payload(payload: dict[str, Any]) -> tuple[str, str]:
    full_name = str(payload.get("full_name") or payload.get("fullname") or DEFAULT_FULL_NAME).strip() or DEFAULT_FULL_NAME
    english_name = str(
        payload.get("english_name") or payload.get("englishName") or payload.get("candidate") or DEFAULT_ENGLISH_NAME
    ).strip() or DEFAULT_ENGLISH_NAME
    return full_name, english_name


def _clean_report_text(text: str) -> str:
    return "".join(c for c in text if c.isprintable() or c in "\n\t").strip()


def start_attempt(user, payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode") or payload.get("part") or "p1").lower().strip()
    if mode == "full":
        mode = "mock"
    if mode not in {"p1", "p2", "p3", "mock"}:
        raise ValueError(f"Invalid mode: {mode}")
    attempt_id = uuid.uuid4().hex
    full_name, english_name = _candidate_names_from_payload(payload)
    part, title, turns, cue_card, metadata = _build_turns(mode, payload)
    attempt = SpeakingAttempt.objects.create(
        user=user,
        attempt_id=attempt_id,
        mode=mode,
        part=part,
        title=title,
        status=SpeakingAttempt.Status.STARTED,
        full_name=full_name,
        english_name=english_name,
        metadata={
            "cue_card": cue_card,
            **metadata,
        },
    )
    for index, turn_data in enumerate(turns):
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id=turn_data["id"],
            sequence=index,
            part=turn_data["part"],
            question=turn_data["question"],
            counts_toward_total=turn_data.get("counts_toward_total", True),
            metadata={
                "prompt": turn_data.get("prompt"),
                "cue_card": turn_data.get("cue_card"),
                "timers": turn_data.get("timers"),
                "examiner_text": turn_data.get("examiner_text"),
                "examiner_behavior": turn_data.get("examiner_behavior"),
                "display_index": turn_data.get("display_index"),
            },
        )
    response = {
        "id": attempt_id,
        "timestamp": attempt.created_at.isoformat(),
        "status": "started",
        "user_id": str(user.id),
        "mode": mode,
        "part": part,
        "title": title,
        "question": turns[0]["question"] if turns else "",
        "cue_card": cue_card,
        "turns": turns,
        "current_turn": turns[0]["id"] if turns else None,
        "candidate": english_name,
        "full_name": full_name,
        "english_name": english_name,
        "pronunciation": {"provider": "azure", "status": "pending"},
        "ielts_score": None,
        "feedback_summary": "",
        "criteria_feedback": {},
        "band7_version": "",
        "model_audio": None,
        "upgrade_notes": [],
        "ai_coaching": "",
        **metadata,
    }
    return response


# --- Audio Upload ---

MAX_AUDIO_BYTES = 25 * 1024 * 1024


def upload_turn_audio(user, attempt_id: str, turn_id: str, audio_file) -> dict[str, Any]:
    """Upload audio for a speaking turn.

    Args:
        user: The authenticated user
        attempt_id: The attempt ID
        turn_id: The turn ID
        audio_file: Django UploadedFile object

    Returns:
        dict with 'ok' and 'audio' keys

    Raises:
        SpeakingError: If validation fails or attempt/turn not found
    """
    attempt = SpeakingAttempt.objects.filter(user=user, attempt_id=attempt_id).first()
    if not attempt:
        raise SpeakingError("Attempt not found")
    if attempt.status == SpeakingAttempt.Status.ABORTED:
        raise SpeakingError("Aborted attempts cannot accept audio")

    turn = SpeakingTurn.objects.filter(attempt=attempt, turn_id=turn_id).first()
    if not turn:
        raise SpeakingError("Turn not found")

    content_type = getattr(audio_file, 'content_type', '') or ''
    if not (content_type.startswith('audio/') or content_type == 'application/octet-stream'):
        raise SpeakingError(f"Unsupported audio content type: {content_type}")

    audio_file.seek(0, 2)
    size = audio_file.tell()
    audio_file.seek(0)

    if size <= 0:
        raise SpeakingError("Audio upload is empty")
    if size > MAX_AUDIO_BYTES:
        raise SpeakingError("Audio upload exceeds 25 MB")

    import mimetypes
    extension = mimetypes.guess_extension(content_type) or '.webm'
    if extension == '.weba':
        extension = '.webm'

    media_root = Path(settings.MEDIA_ROOT)
    audio_dir = media_root / 'audio'
    audio_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{attempt_id}_{turn_id}{extension}"
    relative_path = f"audio/{filename}"
    full_path = media_root / relative_path

    with open(full_path, 'wb') as dest:
        for chunk in audio_file.chunks():
            dest.write(chunk)

    turn.audio_path = relative_path
    turn.metadata['audio_content_type'] = content_type
    turn.metadata['audio_bytes'] = size
    turn.metadata['audio_uploaded_at'] = timezone.now().isoformat()
    turn.save(update_fields=['audio_path', 'metadata'])

    return {
        "ok": True,
        "audio": {
            "path": str(full_path),
            "content_type": content_type,
            "bytes": size,
            "duration_seconds": None,
            "url": f"/api/audio/{attempt_id}/{turn_id}/candidate",
        },
    }


def get_turn_audio_path(user, attempt_id: str, turn_id: str) -> Path | None:
    """Get the audio file path for a turn.

    Args:
        user: The authenticated user
        attempt_id: The attempt ID
        turn_id: The turn ID

    Returns:
        Path to audio file or None if not found
    """
    turn = (
        SpeakingTurn.objects
        .filter(attempt__user=user, attempt__attempt_id=attempt_id, turn_id=turn_id)
        .first()
    )
    if not turn or not turn.audio_path:
        return None
    return Path(settings.MEDIA_ROOT) / turn.audio_path
    return response
