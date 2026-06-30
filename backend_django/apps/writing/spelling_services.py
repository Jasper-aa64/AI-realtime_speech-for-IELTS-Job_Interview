from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.speaking.corpus_services import LOCAL_TAKEAWAY_WORD_TRANSLATIONS

from .models import SpellingDrillDailyBatch, SpellingDrillWord, WritingScore
from .report_services import looks_like_single_word_spelling_fix, spelling_terms_from_summary
from .validation import WritingError


SPELLING_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]*$")

# SRS Leitner box intervals in review days. A review day refreshes at 04:00
# local time, so items are grouped into stable daily batches instead of
# reappearing exactly 24 hours after the previous answer.
SRS_DAY_ROLLOVER_HOUR = 4
SRS_REVIEW_TIMEZONE = ZoneInfo("Asia/Shanghai")
SRS_STAGE_INTERVAL_DAYS: list[int] = [
    1,  # stage 0→1
    2,  # stage 1→2
    4,  # stage 2→3
    7,  # stage 3→4 (graduation)
]
SRS_MAX_STAGE = len(SRS_STAGE_INTERVAL_DAYS)  # 4
SRS_LAPSE_INTERVAL_DAYS = 1
SRS_MASTERED_LAPSE_STAGE = max(0, SRS_MAX_STAGE - 1)
SRS_MASTERED_INTERVAL_DAYS: list[int] = [7, 14, 30, 60, 90]


def review_day_start(value=None):
    current = timezone.localtime(value or timezone.now(), SRS_REVIEW_TIMEZONE)
    start = current.replace(
        hour=SRS_DAY_ROLLOVER_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )
    if current < start:
        start -= timedelta(days=1)
    return start


def next_review_refresh(days: int, value=None):
    interval = max(0, int(days or 0))
    return review_day_start(value) + timedelta(days=interval)


def current_review_batch_cutoff(value=None):
    return review_day_start(value)


def review_day_key(value=None):
    return review_day_start(value).date()


def effective_spelling_due_at(word: SpellingDrillWord):
    due = word.due_at or timezone.now()
    due_local = timezone.localtime(due, SRS_REVIEW_TIMEZONE)
    if (
        due_local.hour == SRS_DAY_ROLLOVER_HOUR + 8
        and due_local.minute == 0
        and due_local.second == 0
        and due_local.microsecond == 0
    ):
        return due - timedelta(hours=8)
    return due


def is_due_for_current_batch(word: SpellingDrillWord, *, now=None) -> bool:
    if word.status not in {SpellingDrillWord.Status.ACTIVE, SpellingDrillWord.Status.MASTERED}:
        return False
    due = effective_spelling_due_at(word)
    return due <= current_review_batch_cutoff(now)


def practiced_in_review_day(word: SpellingDrillWord, *, now=None) -> bool:
    practiced = word.last_practiced_at
    if not practiced:
        return False
    start = review_day_start(now)
    return start <= timezone.localtime(practiced) < start + timedelta(days=1)


def mastered_review_level(word: SpellingDrillWord) -> int:
    metadata = word.metadata if isinstance(word.metadata, dict) else {}
    try:
        return max(0, int(metadata.get("mastered_review_level") or 0))
    except (TypeError, ValueError):
        return 0


def set_mastered_review_level(word: SpellingDrillWord, level: int) -> None:
    metadata = dict(word.metadata or {})
    metadata["mastered_review_level"] = max(0, int(level or 0))
    word.metadata = metadata


def due_human(due_at, now=None) -> str:
    if now is None:
        now = timezone.now()
    seconds = (due_at - now).total_seconds()
    if seconds <= 60:
        return "马上"
    due_local = timezone.localtime(due_at, SRS_REVIEW_TIMEZONE)
    now_local = timezone.localtime(now, SRS_REVIEW_TIMEZONE)
    day_delta = (due_local.date() - now_local.date()).days
    if day_delta == 1:
        return "明天"
    if day_delta > 1:
        return f"{day_delta} 天后"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟后"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时后"
    return f"{int(seconds // 86400)} 天后"


@dataclass(frozen=True)
class SpellingCandidate:
    wrong: str
    correct: str
    gloss: str = ""
    explanation: str = ""
    entry_id: str = ""
    snippet: str = ""

    @property
    def normalized(self) -> str:
        return normalize_spelling_display(self.correct).lower()

    @property
    def harvest_key(self) -> str:
        raw = "|".join([
            self.entry_id,
            self.normalized,
            normalize_spelling_display(self.wrong).lower(),
            self.snippet[:160],
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def normalize_spelling_display(value: Any) -> str:
    text = str(value or "").strip().strip("`*_“”\"'.,;:!?()[]{}，。；：！？、")
    text = text.replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    if text.isupper():
        text = text.lower()
    return text


def is_single_word_spelling(value: Any) -> bool:
    text = normalize_spelling_display(value)
    return len(text) >= 2 and bool(SPELLING_WORD_RE.fullmatch(text))


def spelling_word_id(normalized: str) -> str:
    digest = hashlib.sha1(str(normalized or "").lower().encode("utf-8")).hexdigest()[:16]
    return f"sp:{digest}"


def first_local_gloss(correct: str) -> str:
    normalized = str(correct or "").strip().lower()
    singular = normalized[:-1] if normalized.endswith("s") else normalized
    return LOCAL_TAKEAWAY_WORD_TRANSLATIONS.get(normalized) or LOCAL_TAKEAWAY_WORD_TRANSLATIONS.get(singular) or ""


def short_snippet(text: str, needle: str, *, max_len: int = 180) -> str:
    source = re.sub(r"\s+", " ", str(text or "")).strip()
    if not source:
        return ""
    match = re.search(rf"\b{re.escape(str(needle or ''))}\b", source, flags=re.IGNORECASE)
    if not match:
        return source[:max_len]
    start = max(0, match.start() - 70)
    end = min(len(source), match.end() + 90)
    snippet = source[start:end].strip()
    if start:
        snippet = f"...{snippet}"
    if end < len(source):
        snippet = f"{snippet}..."
    return snippet[:max_len]


def paragraph_snippet(score: WritingScore, annotation: dict[str, Any], wrong: str) -> str:
    entry = getattr(score, "entry", None)
    answer = getattr(entry, "answer", "") or ""
    try:
        index = int(annotation.get("paragraph_index") or 0)
    except (TypeError, ValueError):
        index = 0
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", answer) if part.strip()]
    source = paragraphs[index - 1] if index > 0 and index <= len(paragraphs) else answer
    return short_snippet(source, wrong)


def summary_line_candidate(line: str, score: WritingScore) -> SpellingCandidate | None:
    compact = str(line or "").lstrip("-*• \t").strip()
    if not looks_like_single_word_spelling_fix(compact):
        return None
    arrow = "->" if "->" in compact else "\u2192"
    wrong, right = compact.replace("`", "").split(arrow, 1)
    right = right.strip().strip("。. ")
    for prefix in ("正确：", "正确:", "correct:", "Correct:"):
        if right.startswith(prefix):
            right = right[len(prefix):].strip()
    gloss = ""
    gloss_match = re.search(r"[（(]([^（）()]+)[）)]", right)
    if gloss_match:
        gloss = gloss_match.group(1).strip()
    correct = right.split("（", 1)[0].split("(", 1)[0].strip()
    wrong = wrong.strip()
    if not is_single_word_spelling(wrong) or not is_single_word_spelling(correct):
        return None
    entry = getattr(score, "entry", None)
    entry_id = getattr(entry, "entry_id", "") or str(getattr(entry, "pk", "") or "")
    return SpellingCandidate(
        wrong=normalize_spelling_display(wrong),
        correct=normalize_spelling_display(correct),
        gloss=gloss[:200],
        entry_id=entry_id,
        snippet=short_snippet(getattr(entry, "answer", "") or "", wrong),
    )


def inline_annotation_candidates(score: WritingScore) -> list[SpellingCandidate]:
    analysis = score.analysis_payload if isinstance(score.analysis_payload, dict) else {}
    annotations = analysis.get("inline_annotations")
    if not isinstance(annotations, list):
        return []
    entry = getattr(score, "entry", None)
    entry_id = getattr(entry, "entry_id", "") or str(getattr(entry, "pk", "") or "")
    candidates: list[SpellingCandidate] = []
    for item in annotations:
        if not isinstance(item, dict) or item.get("type") != "spelling":
            continue
        wrong = normalize_spelling_display(item.get("original"))
        correct = normalize_spelling_display(item.get("suggestion"))
        if not is_single_word_spelling(wrong) or not is_single_word_spelling(correct):
            continue
        candidates.append(SpellingCandidate(
            wrong=wrong,
            correct=correct,
            explanation=str(item.get("explanation") or "").strip(),
            entry_id=entry_id,
            snippet=paragraph_snippet(score, item, wrong),
        ))
    return candidates


def summary_candidates(score: WritingScore) -> list[SpellingCandidate]:
    analysis = score.analysis_payload if isinstance(score.analysis_payload, dict) else {}
    summary = str(analysis.get("spelling_correction_summary") or "")
    if not spelling_terms_from_summary(summary):
        return []
    candidates: list[SpellingCandidate] = []
    for line in summary.splitlines():
        candidate = summary_line_candidate(line, score)
        if candidate:
            candidates.append(candidate)
    return candidates


def spelling_candidates_for_score(score: WritingScore) -> list[SpellingCandidate]:
    return inline_annotation_candidates(score) + summary_candidates(score)


def merge_unique(values: list[Any], additions: list[Any], *, limit: int | None = None) -> list[Any]:
    result = list(values or [])
    seen = {str(item).lower() for item in result}
    for item in additions:
        key = str(item).lower()
        if not key or key in seen:
            continue
        result.append(item)
        seen.add(key)
        if limit and len(result) >= limit:
            break
    return result


def merge_examples(existing: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = [item for item in existing or [] if isinstance(item, dict)]
    seen = {(str(item.get("entry_id") or ""), str(item.get("snippet") or "")) for item in result}
    for item in additions:
        key = (str(item.get("entry_id") or ""), str(item.get("snippet") or ""))
        if not key[1] or key in seen:
            continue
        result.append(item)
        seen.add(key)
        if len(result) >= 5:
            break
    return result[:5]


def harvest_spelling_words(user) -> int:
    now = timezone.now()
    changed = 0
    scores = (
        WritingScore.objects
        .filter(user=user)
        .select_related("entry")
        .order_by("created_at", "pk")
    )
    by_normalized: dict[str, list[SpellingCandidate]] = {}
    for score in scores:
        for candidate in spelling_candidates_for_score(score):
            if candidate.normalized:
                by_normalized.setdefault(candidate.normalized, []).append(candidate)

    for normalized, candidates in by_normalized.items():
        with transaction.atomic():
            word = SpellingDrillWord.objects.select_for_update().filter(user=user, normalized=normalized).first()
            new_keys: list[str] = []
            if word:
                metadata = dict(word.metadata or {})
                seen_keys = set(metadata.get("harvest_keys") or [])
            else:
                metadata = {"harvest_keys": []}
                seen_keys = set()
            for candidate in candidates:
                if candidate.harvest_key not in seen_keys:
                    new_keys.append(candidate.harvest_key)
                    seen_keys.add(candidate.harvest_key)
            if word and not new_keys:
                continue
            first = candidates[0]
            wrong_forms = merge_unique(word.wrong_forms if word else [], [item.wrong for item in candidates])
            source_refs = merge_unique(word.source_refs if word else [], [item.entry_id for item in candidates if item.entry_id])
            examples = merge_examples(
                word.examples if word else [],
                [{"entry_id": item.entry_id, "snippet": item.snippet} for item in candidates if item.snippet],
            )
            gloss = (word.chinese_gloss if word else "") or next((item.gloss for item in candidates if item.gloss), "") or first_local_gloss(first.correct)
            if word and (word.metadata or {}).get("gloss_edited"):
                gloss = word.chinese_gloss
            explanation = next((item.explanation for item in reversed(candidates) if item.explanation), "")
            metadata["harvest_keys"] = sorted(seen_keys)
            defaults = {
                "correct_spelling": word.correct_spelling if word else first.correct,
                "wrong_forms": wrong_forms,
                "chinese_gloss": gloss[:200],
                "explanation": explanation or (word.explanation if word else ""),
                "examples": examples,
                "occurrence_count": (word.occurrence_count if word else 0) + len(new_keys),
                "last_seen_at": now,
                "source_refs": source_refs,
                "metadata": metadata,
            }
            if word:
                for field, value in defaults.items():
                    setattr(word, field, value)
                word.save(update_fields=[*defaults.keys(), "updated_at"])
            else:
                SpellingDrillWord.objects.create(
                    user=user,
                    word_id=spelling_word_id(normalized),
                    normalized=normalized,
                    first_seen_at=now,
                    due_at=next_review_refresh(1, now),
                    status=SpellingDrillWord.Status.ACTIVE,
                    **defaults,
                )
            changed += 1
    return changed


def add_manual_spelling_word(user, *, word: str, chinese_gloss: str = "") -> dict[str, Any]:
    """Add a single English word to the user's spelling training on demand
    (from the 划词 popup's + button). Re-activates an existing/mastered entry
    rather than duplicating it."""
    normalized = normalize_spelling_display(word)
    if not is_single_word_spelling(normalized):
        raise WritingError("请选择单个英文单词加入拼写训练。")
    gloss = str(chinese_gloss or "").strip() or first_local_gloss(normalized)
    now = timezone.now()
    with transaction.atomic():
        existing = (
            SpellingDrillWord.objects.select_for_update()
            .filter(user=user, normalized__iexact=normalized)
            .first()
        )
        if existing:
            update_fields = ["last_seen_at", "updated_at"]
            existing.last_seen_at = now
            if existing.status != SpellingDrillWord.Status.ACTIVE:
                existing.status = SpellingDrillWord.Status.ACTIVE
                existing.due_at = now
                update_fields += ["status", "due_at"]
            if gloss and not existing.chinese_gloss:
                existing.chinese_gloss = gloss[:200]
                update_fields.append("chinese_gloss")
            existing.save(update_fields=list(dict.fromkeys(update_fields)))
            return {"ok": True, "created": False, "word": spelling_word_payload(existing)}
        word_obj = SpellingDrillWord.objects.create(
            user=user,
            word_id=spelling_word_id(normalized),
            correct_spelling=normalized,
            normalized=normalized,
            chinese_gloss=gloss[:200],
            occurrence_count=1,
            first_seen_at=now,
            last_seen_at=now,
            due_at=now,
            status=SpellingDrillWord.Status.ACTIVE,
            source_refs=["manual"],
            metadata={"source": "takeaway_popup"},
        )
    return {"ok": True, "created": True, "word": spelling_word_payload(word_obj)}


def spelling_word_payload(word: SpellingDrillWord) -> dict[str, Any]:
    now = timezone.now()
    due = word.due_at if word.due_at else now
    is_due = is_due_for_current_batch(word, now=now) and not practiced_in_review_day(word, now=now)
    return {
        "word_id": word.word_id,
        "correct_spelling": word.correct_spelling,
        "wrong_forms": word.wrong_forms or [],
        "chinese_gloss": word.chinese_gloss,
        "explanation": word.explanation,
        "examples": word.examples or [],
        "occurrence_count": word.occurrence_count,
        "attempt_count": word.attempt_count,
        "correct_count": word.correct_count,
        "current_streak": word.current_streak,
        "review_stage": word.review_stage,
        "max_stage": SRS_MAX_STAGE,
        "lapses": word.lapses,
        "due_at": due.isoformat(),
        "is_due": is_due,
        "status": word.status,
        "last_practiced_at": word.last_practiced_at.isoformat() if word.last_practiced_at else None,
    }


def due_word_ids_for_cutoff(user, cutoff) -> list[str]:
    candidates = list(
        SpellingDrillWord.objects
        .filter(
            user=user,
            status__in=[SpellingDrillWord.Status.ACTIVE, SpellingDrillWord.Status.MASTERED],
            due_at__lte=cutoff + timedelta(hours=8),
        )
        .exclude(status=SpellingDrillWord.Status.DISMISSED)
        .order_by("due_at", "-occurrence_count", "pk")
    )
    return [word.word_id for word in candidates if is_due_for_current_batch(word, now=cutoff)]


def get_or_create_spelling_daily_batch(user, *, now=None) -> SpellingDrillDailyBatch:
    now = now or timezone.now()
    day = review_day_key(now)
    cutoff = current_review_batch_cutoff(now)
    with transaction.atomic():
        batch = SpellingDrillDailyBatch.objects.select_for_update().filter(user=user, review_day=day).first()
        if batch:
            if not batch.word_ids:
                word_ids = due_word_ids_for_cutoff(user, cutoff)
                if word_ids:
                    batch.word_ids = word_ids
                    batch.save(update_fields=["word_ids", "updated_at"])
            return batch
        word_ids = due_word_ids_for_cutoff(user, cutoff)
        try:
            return SpellingDrillDailyBatch.objects.create(user=user, review_day=day, word_ids=word_ids)
        except IntegrityError:
            return SpellingDrillDailyBatch.objects.select_for_update().get(user=user, review_day=day)


def spelling_daily_batch_remaining_words(user, *, now=None):
    now = now or timezone.now()
    batch = get_or_create_spelling_daily_batch(user, now=now)
    word_ids = [str(word_id or "").strip() for word_id in (batch.word_ids or []) if str(word_id or "").strip()]
    if not word_ids:
        return SpellingDrillWord.objects.none(), batch
    ordering = {word_id: index for index, word_id in enumerate(word_ids)}
    words = list(
        SpellingDrillWord.objects
        .filter(
            user=user,
            word_id__in=word_ids,
            status__in=[SpellingDrillWord.Status.ACTIVE, SpellingDrillWord.Status.MASTERED],
        )
        .exclude(status=SpellingDrillWord.Status.DISMISSED)
    )
    remaining = [
        word for word in words
        if is_due_for_current_batch(word, now=now) and not practiced_in_review_day(word, now=now)
    ]
    remaining.sort(key=lambda word: ordering.get(word.word_id, len(ordering)))
    return remaining, batch


def spelling_drill_library(user, *, scope: str = "due") -> dict[str, Any]:
    scope = str(scope or "due").strip().lower()
    if scope not in {"due", "active", "mastered", "all"}:
        raise WritingError("Unknown spelling drill scope")
    harvest_spelling_words(user)
    now = timezone.now()
    batch_cutoff = current_review_batch_cutoff(now)
    queryset = SpellingDrillWord.objects.filter(user=user).exclude(status=SpellingDrillWord.Status.DISMISSED)
    if scope == "due":
        remaining_words, batch = spelling_daily_batch_remaining_words(user, now=now)
        items = [spelling_word_payload(word) for word in remaining_words[:500]]
    elif scope == "active":
        queryset = queryset.filter(status=SpellingDrillWord.Status.ACTIVE).order_by("due_at", "-occurrence_count")
        items = [spelling_word_payload(word) for word in queryset[:500]]
    elif scope == "mastered":
        queryset = queryset.filter(status=SpellingDrillWord.Status.MASTERED).order_by("-updated_at")
        items = [spelling_word_payload(word) for word in queryset[:500]]
    else:
        queryset = queryset.order_by("status", "due_at", "-occurrence_count")
        items = [spelling_word_payload(word) for word in queryset[:500]]
    visible = SpellingDrillWord.objects.filter(user=user).exclude(status=SpellingDrillWord.Status.DISMISSED)
    total = visible.count()
    active_count = visible.filter(status=SpellingDrillWord.Status.ACTIVE).count()
    due_count = len(remaining_words) if scope == "due" else len(spelling_daily_batch_remaining_words(user, now=now)[0])
    mastered_count = visible.filter(status=SpellingDrillWord.Status.MASTERED).count()
    attempt_totals = visible.aggregate(attempts=Sum("attempt_count"), correct=Sum("correct_count"))
    attempts = int(attempt_totals.get("attempts") or 0)
    correct_total = int(attempt_totals.get("correct") or 0)
    return {
        "items": items,
        "count": len(items),
        "stats": {
            "total": total,
            "active": active_count,
            "due": due_count,
            "mastered": mastered_count,
            "accuracy": (correct_total / attempts) if attempts else 0,
            "review_day_start": batch_cutoff.isoformat(),
        },
    }


def get_spelling_word(user, word_id: str) -> SpellingDrillWord:
    word = SpellingDrillWord.objects.filter(user=user, word_id=str(word_id or "").strip()).first()
    if not word:
        raise WritingError("Spelling drill word not found")
    return word


def record_spelling_attempt(user, word_id: str, typed: Any) -> dict[str, Any]:
    typed_text = str(typed or "").strip().lower()
    with transaction.atomic():
        word = SpellingDrillWord.objects.select_for_update().filter(user=user, word_id=str(word_id or "").strip()).first()
        if not word:
            raise WritingError("Spelling drill word not found")
        is_correct = typed_text == word.normalized
        now = timezone.now()
        word.attempt_count += 1
        word.last_practiced_at = now
        if is_correct:
            word.correct_count += 1
            word.current_streak += 1
            if word.status == SpellingDrillWord.Status.MASTERED:
                level = min(mastered_review_level(word) + 1, len(SRS_MASTERED_INTERVAL_DAYS) - 1)
                set_mastered_review_level(word, level)
                word.review_stage = SRS_MAX_STAGE
                word.status = SpellingDrillWord.Status.MASTERED
                word.due_at = next_review_refresh(SRS_MASTERED_INTERVAL_DAYS[level], now)
            else:
                new_stage = min(word.review_stage + 1, SRS_MAX_STAGE)
                word.review_stage = new_stage
                if new_stage >= SRS_MAX_STAGE:
                    word.status = SpellingDrillWord.Status.MASTERED
                    set_mastered_review_level(word, 0)
                    word.due_at = next_review_refresh(SRS_MASTERED_INTERVAL_DAYS[0], now)
                else:
                    word.due_at = next_review_refresh(SRS_STAGE_INTERVAL_DAYS[new_stage - 1], now)
        else:
            was_mastered = word.status == SpellingDrillWord.Status.MASTERED
            word.current_streak = 0
            word.lapses += 1
            word.review_stage = SRS_MASTERED_LAPSE_STAGE if was_mastered else 0
            word.status = SpellingDrillWord.Status.ACTIVE
            set_mastered_review_level(word, 0)
            word.due_at = next_review_refresh(SRS_LAPSE_INTERVAL_DAYS, now)
        word.save(update_fields=[
            "attempt_count", "correct_count", "current_streak",
            "review_stage", "due_at", "lapses", "status",
            "last_practiced_at", "metadata", "updated_at",
        ])
    return {
        "correct": is_correct,
        "correct_spelling": "" if is_correct else word.correct_spelling,
        "current_streak": word.current_streak,
        "review_stage": word.review_stage,
        "status": word.status,
        "explanation": "" if is_correct else word.explanation,
        "next_due_human": due_human(word.due_at, now),
    }


def update_spelling_word(user, word_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    action = str((payload or {}).get("action") or "").strip()
    with transaction.atomic():
        word = SpellingDrillWord.objects.select_for_update().filter(user=user, word_id=str(word_id or "").strip()).first()
        if not word:
            raise WritingError("Spelling drill word not found")
        if action == "master":
            word.status = SpellingDrillWord.Status.MASTERED
            word.review_stage = SRS_MAX_STAGE
            set_mastered_review_level(word, 0)
            word.due_at = next_review_refresh(SRS_MASTERED_INTERVAL_DAYS[0])
            update_fields = ["status", "review_stage", "due_at", "metadata", "updated_at"]
        elif action == "reset":
            word.status = SpellingDrillWord.Status.ACTIVE
            word.current_streak = 0
            word.review_stage = 0
            word.lapses = 0
            word.due_at = timezone.now()
            update_fields = ["status", "current_streak", "review_stage", "lapses", "due_at", "updated_at"]
        elif action == "edit_gloss":
            word.chinese_gloss = str(payload.get("chinese_gloss") or "").strip()[:200]
            metadata = dict(word.metadata or {})
            metadata["gloss_edited"] = True
            word.metadata = metadata
            update_fields = ["chinese_gloss", "metadata", "updated_at"]
        else:
            raise WritingError("Unknown spelling drill action")
        word.save(update_fields=update_fields)
    return spelling_word_payload(word)


def delete_spelling_word(user, word_id: str) -> dict[str, Any]:
    word = get_spelling_word(user, word_id)
    word.status = SpellingDrillWord.Status.DISMISSED
    word.save(update_fields=["status", "updated_at"])
    return {"ok": True}
