import calendar
import hashlib
import json
import random
import re
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.ai.models import AITask
from apps.ai.orchestration import AIOrchestrationError, create_billable_ai_task, fallback_billable_ai_task, succeed_billable_ai_task
from apps.ai.services import task_payload

from .models import WritingEntry, WritingLearnerProfile, WritingPrompt, WritingScore


DEFAULT_WRITING_SCORE_RESERVATION_U = 1_000_000
WRITING_TASK_LABELS = {
    WritingPrompt.TaskType.TASK1_ACADEMIC: "Task 1 Academic",
    WritingPrompt.TaskType.TASK2: "Task 2",
}
WRITING_TASK_TYPES = set(WRITING_TASK_LABELS)


class WritingError(ValueError):
    pass


def normalize_task_type(value: str | None) -> str:
    task_type = str(value or "").strip().lower()
    aliases = {
        "task1": WritingPrompt.TaskType.TASK1_ACADEMIC,
        "task_1": WritingPrompt.TaskType.TASK1_ACADEMIC,
        "task1academic": WritingPrompt.TaskType.TASK1_ACADEMIC,
        "task 1 academic": WritingPrompt.TaskType.TASK1_ACADEMIC,
        "task2": WritingPrompt.TaskType.TASK2,
        "task_2": WritingPrompt.TaskType.TASK2,
        "task 2": WritingPrompt.TaskType.TASK2,
    }
    task_type = aliases.get(task_type, task_type)
    if task_type not in WRITING_TASK_TYPES:
        raise WritingError("Unknown writing task type")
    return task_type


def word_count(answer: str) -> int:
    return len(re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)?|\d+(?:\.\d+)?", answer or ""))


def data_writing_dir() -> Path:
    return Path(settings.BASE_DIR).parent / "data" / "ielts" / "writing"


def stable_prompt_id(task_type: str, prompt: str) -> str:
    digest = hashlib.sha1(f"{task_type}:{prompt}".encode("utf-8")).hexdigest()[:16]
    return f"{task_type}_{digest}"


def prompt_payload(prompt: WritingPrompt) -> dict[str, Any]:
    return {
        "id": prompt.prompt_id,
        "task_type": prompt.task_type,
        "task_label": WRITING_TASK_LABELS.get(prompt.task_type, "Writing"),
        "title": prompt.title,
        "category": prompt.category,
        "prompt": prompt.prompt,
        "source": prompt.source,
    }


def sync_seed_prompts() -> None:
    base_dir = data_writing_dir()
    for task_type in sorted(WRITING_TASK_TYPES):
        path = base_dir / f"{task_type}.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WritingError(f"Unable to load writing prompts: {path}") from exc
        raw_items = payload.get("prompts") if isinstance(payload, dict) else payload
        if not isinstance(raw_items, list):
            raise WritingError(f"Writing prompt file must contain a prompts array: {path}")
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                raise WritingError(f"Writing prompt must be an object in {path}")
            prompt_text = str(raw_item.get("prompt") or raw_item.get("question") or "").strip()
            if not prompt_text:
                continue
            prompt_id = str(raw_item.get("id") or "").strip() or stable_prompt_id(task_type, prompt_text)
            WritingPrompt.objects.update_or_create(
                prompt_id=prompt_id[:120],
                defaults={
                    "task_type": task_type,
                    "title": str(raw_item.get("title") or f"{WRITING_TASK_LABELS[task_type]} {index + 1}")[:200],
                    "category": str(raw_item.get("category") or "")[:120],
                    "prompt": prompt_text,
                    "source": str(raw_item.get("source") or "local_seed")[:120],
                    "is_active": True,
                },
            )


def list_prompts(task_type: str | None = None) -> list[dict[str, Any]]:
    sync_seed_prompts()
    queryset = WritingPrompt.objects.filter(is_active=True)
    if task_type:
        queryset = queryset.filter(task_type=normalize_task_type(task_type))
    return [prompt_payload(prompt) for prompt in queryset.order_by("task_type", "prompt_id")]


def next_default_task_type(date_value=None) -> str:
    today = date_value or timezone.localdate()
    return WritingPrompt.TaskType.TASK1_ACADEMIC if today.toordinal() % 2 == 0 else WritingPrompt.TaskType.TASK2


def random_prompt(user, task_type: str | None = None) -> dict[str, Any]:
    selected_type = normalize_task_type(task_type) if task_type else next_default_task_type()
    sync_seed_prompts()
    prompts = list(WritingPrompt.objects.filter(task_type=selected_type, is_active=True).order_by("prompt_id"))
    if not prompts:
        raise WritingError(f"No writing prompts available for {selected_type}")
    used_ids = set(
        WritingEntry.objects.filter(user=user, status__in=[WritingEntry.Status.SAVED, WritingEntry.Status.SCORED])
        .exclude(prompt__isnull=True)
        .values_list("prompt__prompt_id", flat=True)
    )
    unused = [prompt for prompt in prompts if prompt.prompt_id not in used_ids]
    selected = random.choice(unused or prompts)
    return {**prompt_payload(selected), "selection": "random", "unwritten": bool(unused)}


def month_bounds(month_value: str | None):
    value = str(month_value or timezone.localdate().strftime("%Y-%m")).strip()
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        value = timezone.localdate().strftime("%Y-%m")
    year, month = [int(part) for part in value.split("-")]
    _, day_count = calendar.monthrange(year, month)
    return timezone.datetime(year, month, 1).date(), timezone.datetime(year, month, day_count).date()


def score_payload(score: WritingScore | None) -> dict[str, Any] | None:
    if not score:
        return None
    return {
        "overall_band": float(score.overall_band) if score.overall_band is not None else None,
        "task_response": float(score.task_response) if score.task_response is not None else None,
        "task_achievement": float(score.task_response) if score.task_response is not None else None,
        "coherence_cohesion": float(score.coherence_cohesion) if score.coherence_cohesion is not None else None,
        "lexical_resource": float(score.lexical_resource) if score.lexical_resource is not None else None,
        "grammatical_range_accuracy": float(score.grammar_range_accuracy) if score.grammar_range_accuracy is not None else None,
        "feedback_markdown": score.feedback_markdown,
        "grammar_corrections": score.grammar_corrections,
        "backend": score.source,
        "billing_usage": score.billing_metadata,
        "scored_at": score.scored_at.isoformat() if score.scored_at else None,
    }


def profile_snapshot(profile: WritingLearnerProfile | None) -> dict[str, Any] | None:
    if not profile:
        return None
    tag_counts = profile.tag_counts if isinstance(profile.tag_counts, dict) else {}
    top_tags = sorted(tag_counts.items(), key=lambda item: (-int(item[1] or 0), str(item[0])))[:5]
    return {
        "total_scored": profile.total_scored,
        "average_overall_band": float(profile.average_overall_band) if profile.average_overall_band is not None else None,
        "primary_focus": profile.primary_focus,
        "primary_focus_text": profile.primary_focus_text,
        "top_issues": [{"tag": tag, "label": writing_tag_text(tag), "count": count} for tag, count in top_tags],
        "recent_evidence": list(profile.recent_evidence or [])[:4],
        "updated_at": profile.updated_at.isoformat() if profile.pk else None,
    }


def writing_score_task_payload(entry: WritingEntry) -> dict[str, Any] | None:
    task = (
        AITask.objects.filter(
            user=entry.user,
            task_type="writing_score",
            related_type="writing_entry",
            related_id=entry.entry_id,
        )
        .order_by("-created_at")
        .first()
    )
    return task_payload(task) if task else None


def entry_payload(entry: WritingEntry, include_answer: bool = True) -> dict[str, Any]:
    score = getattr(entry, "score", None)
    payload = {
        "id": entry.entry_id,
        "user_id": str(entry.user_id),
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
        "saved_at": entry.saved_at.isoformat() if entry.saved_at else None,
        "practice_date": entry.practice_date.isoformat(),
        "status": entry.status,
        "task_type": entry.task_type,
        "task_label": WRITING_TASK_LABELS.get(entry.task_type, "Writing"),
        "prompt_id": entry.prompt.prompt_id if entry.prompt_id else "",
        "title": entry.title,
        "category": entry.prompt.category if entry.prompt_id else entry.metadata.get("category", ""),
        "prompt": entry.prompt_text,
        "word_count": entry.word_count,
        "score": score_payload(score),
        "ai_task": writing_score_task_payload(entry),
        "writing_profile": profile_snapshot(getattr(entry.user, "writing_learner_profile", None)),
    }
    if include_answer:
        payload["answer"] = entry.answer
    return payload


def compact_entry_payload(entry: WritingEntry) -> dict[str, Any]:
    score = getattr(entry, "score", None)
    return {
        "id": entry.entry_id,
        "practice_date": entry.practice_date.isoformat(),
        "display_time": entry.updated_at.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%d %H:%M"),
        "task_type": entry.task_type,
        "task_label": WRITING_TASK_LABELS.get(entry.task_type, "Writing"),
        "title": entry.title or (entry.prompt.title if entry.prompt_id else "Writing"),
        "word_count": entry.word_count,
        "status": entry.status,
        "overall_band": float(score.overall_band) if score and score.overall_band is not None else None,
    }


def writing_summary(user, month_value: str | None = None) -> dict[str, Any]:
    start, end = month_bounds(month_value)
    today = timezone.localdate()
    entries = list(
        WritingEntry.objects.filter(user=user)
        .select_related("prompt", "score")
        .order_by("-updated_at")
    )
    day_map: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if start <= entry.practice_date <= end:
            key = entry.practice_date.isoformat()
            status = "scored" if entry.status == WritingEntry.Status.SCORED else "saved"
            current = day_map.get(key)
            if not current or (status == "scored" and current.get("status") != "scored"):
                day_map[key] = {**compact_entry_payload(entry), "date": key, "status": status, "entry_id": entry.entry_id}
    days = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        days.append(day_map.get(key) or {"date": key, "status": "empty"})
        cursor += timezone.timedelta(days=1)
    practiced_dates = {item["date"] for item in day_map.values() if item.get("status") in {"saved", "scored"}}
    all_practiced_dates = {
        entry.practice_date.isoformat()
        for entry in entries
        if entry.status in {WritingEntry.Status.SAVED, WritingEntry.Status.SCORED}
    }
    streak = 0
    cursor = today
    while cursor.isoformat() in all_practiced_dates:
        streak += 1
        cursor -= timezone.timedelta(days=1)
    today_entry = next((entry_payload(entry) for entry in entries if entry.practice_date == today), None)
    return {
        "month": start.strftime("%Y-%m"),
        "today": today.isoformat(),
        "days": days,
        "stats": {
            "practiced_days": len(practiced_dates),
            "scored_entries": sum(1 for item in day_map.values() if item.get("status") == "scored"),
            "streak_days": streak,
            "total_entries": len(entries),
        },
        "recent_entries": [compact_entry_payload(entry) for entry in entries[:20]],
        "today_entry": today_entry,
    }


def parse_practice_date(value: str | None):
    if not value:
        return timezone.localdate()
    try:
        return timezone.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise WritingError("Invalid practice_date") from exc


@transaction.atomic
def save_entry(user, payload: dict[str, Any]) -> dict[str, Any]:
    answer = str(payload.get("answer") or "")
    task_type = normalize_task_type(str(payload.get("task_type") or ""))
    prompt_id = str(payload.get("prompt_id") or "").strip()
    prompt = WritingPrompt.objects.filter(prompt_id=prompt_id, task_type=task_type, is_active=True).first() if prompt_id else None
    prompt_text = str(payload.get("prompt") or (prompt.prompt if prompt else "")).strip()
    if not prompt_text:
        raise WritingError("Missing writing prompt")
    entry_id = str(payload.get("id") or "").strip()
    existing = WritingEntry.objects.select_related("prompt").filter(user=user, entry_id=entry_id).first() if entry_id else None
    if not entry_id:
        entry_id = uuid.uuid4().hex
    title = str(payload.get("title") or (prompt.title if prompt else "") or WRITING_TASK_LABELS[task_type])[:200]
    now = timezone.now()
    entry = existing or WritingEntry(user=user, entry_id=entry_id, task_type=task_type)
    answer_changed = bool(existing and existing.answer != answer)
    entry.prompt = prompt
    entry.task_type = task_type
    entry.practice_date = parse_practice_date(str(payload.get("practice_date") or "") or None)
    entry.title = title
    entry.prompt_text = prompt_text
    entry.answer = answer
    entry.word_count = word_count(answer)
    entry.status = WritingEntry.Status.SAVED if answer_changed or not existing else entry.status
    entry.saved_at = now
    entry.metadata = {**(entry.metadata or {}), "category": str(payload.get("category") or (prompt.category if prompt else ""))}
    entry.save()
    if answer_changed:
        WritingScore.objects.filter(entry=entry).delete()
    return entry_payload(entry)


def get_entry(user, entry_id: str) -> dict[str, Any]:
    entry = (
        WritingEntry.objects.select_related("user", "prompt", "score")
        .filter(user=user, entry_id=str(entry_id or "").strip())
        .first()
    )
    if not entry:
        raise WritingError("Writing entry not found")
    return entry_payload(entry)


@transaction.atomic
def create_score_task(user, entry_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    entry = (
        WritingEntry.objects.select_related("user", "prompt", "score")
        .filter(user=user, entry_id=str(entry_id or "").strip())
        .first()
    )
    if not entry:
        raise WritingError("Writing entry not found")
    if not entry.answer.strip():
        raise WritingError("Write an answer before requesting AI scoring.")
    try:
        reserved_u = int(payload.get("reserved_u") or DEFAULT_WRITING_SCORE_RESERVATION_U)
    except (TypeError, ValueError) as exc:
        raise WritingError("reserved_u must be a positive integer") from exc
    answer_hash = hashlib.sha1(entry.answer.encode("utf-8")).hexdigest()[:16]
    idempotency_key = f"writing_score:{entry.entry_id}:{answer_hash}"
    try:
        task, created = create_billable_ai_task(
            user=user,
            task_type="writing_score",
            reserved_u=reserved_u,
            idempotency_key=idempotency_key,
            provider=payload.get("provider"),
            model=str(payload.get("model") or ""),
            related_type="writing_entry",
            related_id=entry.entry_id,
            prompt_version=str(payload.get("prompt_version") or "writing_score_v1"),
            request_payload={
                "entry_id": entry.entry_id,
                "task_type": entry.task_type,
                "prompt_id": entry.prompt.prompt_id if entry.prompt_id else "",
                "prompt": entry.prompt_text,
                "answer": entry.answer,
                "word_count": entry.word_count,
                "answer_hash": answer_hash,
            },
            metadata={"source": "writing_score_task"},
        )
    except AIOrchestrationError as exc:
        raise WritingError(str(exc)) from exc
    return {"created": created, "task": task_payload(task), "entry": entry_payload(entry)}


def decimal_band(value: float) -> Decimal:
    return Decimal(str(round(float(value) * 2) / 2)).quantize(Decimal("0.1"))


def task_score_key(task_type: str) -> str:
    return "task_achievement" if task_type == WritingPrompt.TaskType.TASK1_ACADEMIC else "task_response"


def persist_score(entry: WritingEntry, score: dict[str, Any]) -> None:
    task_response_value = score.get(task_score_key(entry.task_type))
    WritingScore.objects.update_or_create(
        entry=entry,
        defaults={
            "user": entry.user,
            "overall_band": decimal_band(score["overall_band"]),
            "task_response": decimal_band(task_response_value),
            "coherence_cohesion": decimal_band(score["coherence_cohesion"]),
            "lexical_resource": decimal_band(score["lexical_resource"]),
            "grammar_range_accuracy": decimal_band(score["grammatical_range_accuracy"]),
            "feedback_markdown": score["feedback_markdown"],
            "grammar_corrections": score.get("grammar_corrections") or [],
            "source": str(score.get("backend") or "ai"),
            "billing_metadata": score.get("billing_usage") or {},
            "scored_at": timezone.now(),
        },
    )
    entry.status = WritingEntry.Status.SCORED
    entry.saved_at = entry.saved_at or timezone.now()
    entry.practice_date = entry.practice_date or timezone.localdate()
    entry.save(update_fields=["status", "saved_at", "practice_date", "updated_at"])


def fallback_score(task_type: str, answer: str, reason: str = "") -> dict[str, Any]:
    count = word_count(answer)
    if count >= 250:
        base = 5.5
    elif count >= 150:
        base = 5.0
    elif count >= 80:
        base = 4.5
    else:
        base = 4.0
    task_key = "task_achievement" if task_type == WritingPrompt.TaskType.TASK1_ACADEMIC else "task_response"
    task_label = "Task Achievement" if task_type == WritingPrompt.TaskType.TASK1_ACADEMIC else "Task Response"
    feedback = "\n".join(
        [
            "AI 评分生成失败，以下是系统默认建议。",
            "",
            f"- 先按 {task_label} 检查是否完整回应题目要求。",
            "- 每个主体段保留一个清楚中心句，再用具体细节或数据支持。",
            "- 写完后优先检查句子结构、连接词和重复用词。",
            "- 语法错误纠正：",
            "  1. 无",
        ]
    )
    return {
        "overall_band": base,
        task_key: base,
        "coherence_cohesion": base,
        "lexical_resource": base,
        "grammatical_range_accuracy": base,
        "feedback_markdown": feedback,
        "grammar_corrections": [],
        "backend": "fallback",
        "billing_usage": {},
        "fallback_reason": reason,
    }


def writing_tag_text(tag: str) -> str:
    return {
        "under_length": "字数偏短，展开和论证材料还不够。",
        "weak_task_achievement": "Task 1 对题目/图表信息覆盖不够稳定。",
        "weak_task_response": "Task 2 观点回应和论证深度需要加强。",
        "coherence_issue": "段落衔接和中心句组织需要更清楚。",
        "weak_lexical_resource": "词汇变化和准确度还可以继续提升。",
        "grammar_accuracy": "句子结构和语法准确度是当前重点。",
        "fallback_scoring": "本次使用系统默认评分，画像证据权重较低。",
    }.get(tag, tag.replace("_", " "))


def profile_tags(entry: WritingEntry, score: dict[str, Any]) -> list[str]:
    task_key = "task_achievement" if entry.task_type == WritingPrompt.TaskType.TASK1_ACADEMIC else "task_response"
    tags = []
    if (entry.task_type == WritingPrompt.TaskType.TASK1_ACADEMIC and entry.word_count < 150) or (entry.task_type == WritingPrompt.TaskType.TASK2 and entry.word_count < 250):
        tags.append("under_length")
    if float(score.get(task_key) or 0) <= 5.0:
        tags.append("weak_task_achievement" if entry.task_type == WritingPrompt.TaskType.TASK1_ACADEMIC else "weak_task_response")
    if float(score.get("coherence_cohesion") or 0) <= 5.0:
        tags.append("coherence_issue")
    if float(score.get("lexical_resource") or 0) <= 5.0:
        tags.append("weak_lexical_resource")
    if float(score.get("grammatical_range_accuracy") or 0) <= 5.0 or score.get("grammar_corrections"):
        tags.append("grammar_accuracy")
    if score.get("backend") == "fallback":
        tags.append("fallback_scoring")
    return sorted(dict.fromkeys(tags))


def infer_primary_focus(tag_counts: dict[str, int]) -> str:
    priority = ["weak_task_response", "weak_task_achievement", "under_length", "coherence_issue", "grammar_accuracy", "weak_lexical_resource"]
    ranked = sorted(tag_counts.items(), key=lambda item: (-int(item[1] or 0), priority.index(item[0]) if item[0] in priority else 99))
    return ranked[0][0] if ranked else "insufficient_data"


def update_profile(entry: WritingEntry, score: dict[str, Any]) -> dict[str, Any]:
    profile, _created = WritingLearnerProfile.objects.get_or_create(user=entry.user)
    previous_total = profile.total_scored
    new_total = previous_total + 1
    profile.total_scored = new_total
    task_counts = dict(profile.task_counts or {})
    task_counts[entry.task_type] = int(task_counts.get(entry.task_type) or 0) + 1
    profile.task_counts = task_counts
    band = float(score.get("overall_band") or 0)
    previous_average = float(profile.average_overall_band) if profile.average_overall_band is not None else band
    profile.average_overall_band = Decimal(str(round(((previous_average * previous_total) + band) / new_total, 2))).quantize(Decimal("0.01"))
    averages = dict(profile.criterion_averages or {})
    for key in ("task_achievement", "task_response", "coherence_cohesion", "lexical_resource", "grammatical_range_accuracy"):
        if score.get(key) is None:
            continue
        value = float(score[key])
        previous_value = float(averages.get(key)) if averages.get(key) is not None else value
        averages[key] = round(((previous_value * previous_total) + value) / new_total, 2)
    profile.criterion_averages = averages
    tags = profile_tags(entry, score)
    tag_counts = dict(profile.tag_counts or {})
    for tag in tags:
        tag_counts[tag] = int(tag_counts.get(tag) or 0) + 1
    profile.tag_counts = tag_counts
    primary_focus = infer_primary_focus({tag: count for tag, count in tag_counts.items() if tag != "fallback_scoring"})
    profile.primary_focus = primary_focus
    profile.primary_focus_text = writing_tag_text(primary_focus) if primary_focus != "insufficient_data" else "还需要更多已评分作文来形成稳定画像。"
    evidence_item = f"{WRITING_TASK_LABELS[entry.task_type]} · Band {score.get('overall_band', '—')} · {entry.word_count} words · {', '.join(writing_tag_text(tag) for tag in tags[:3]) or '暂无明显弱项'}"
    profile.recent_evidence = ([evidence_item] + [str(item) for item in profile.recent_evidence or [] if str(item) != evidence_item])[:8]
    profile.profile_payload = {"last_entry_id": entry.entry_id, "last_score_source": score.get("backend")}
    profile.save()
    score["profile_tags"] = tags
    score["personalization_note"] = "本次 AI 评分与辅导已用于更新你的写作画像。"
    return profile_snapshot(profile) or {}


@transaction.atomic
def score_entry(user, entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    entry = WritingEntry.objects.select_related("user", "prompt").filter(user=user, entry_id=str(entry_id or "").strip()).first()
    if not entry:
        raise WritingError("Writing entry not found")
    if payload.get("answer") is not None:
        entry.answer = str(payload.get("answer") or "")
        entry.word_count = word_count(entry.answer)
    if not entry.answer.strip():
        raise WritingError("Write an answer before requesting AI scoring.")
    entry.saved_at = entry.saved_at or timezone.now()
    entry.practice_date = entry.practice_date or timezone.localdate()
    score = fallback_score(entry.task_type, entry.answer)
    persist_score(entry, score)
    entry.save(update_fields=["answer", "word_count", "updated_at"])
    score["writing_profile"] = update_profile(entry, score)
    entry.refresh_from_db()
    return entry_payload(entry)


def normalize_score_payload(entry: WritingEntry, payload: dict[str, Any]) -> dict[str, Any]:
    score = payload.get("score") if isinstance(payload.get("score"), dict) else payload
    if not isinstance(score, dict):
        raise WritingError("score must be an object")
    task_key = task_score_key(entry.task_type)
    required = ["overall_band", task_key, "coherence_cohesion", "lexical_resource", "grammatical_range_accuracy"]
    missing = [key for key in required if score.get(key) is None]
    if missing:
        raise WritingError(f"Missing score fields: {', '.join(missing)}")
    return {
        "overall_band": float(score["overall_band"]),
        task_key: float(score[task_key]),
        "coherence_cohesion": float(score["coherence_cohesion"]),
        "lexical_resource": float(score["lexical_resource"]),
        "grammatical_range_accuracy": float(score["grammatical_range_accuracy"]),
        "feedback_markdown": str(score.get("feedback_markdown") or ""),
        "grammar_corrections": score.get("grammar_corrections") if isinstance(score.get("grammar_corrections"), list) else [],
        "backend": str(score.get("backend") or "ai"),
        "billing_usage": payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
    }


def get_writing_score_task_and_entry(task_id: str) -> tuple[AITask, WritingEntry]:
    task = (
        AITask.objects.select_for_update()
        .select_related("user")
        .filter(task_id=str(task_id or "").strip(), task_type="writing_score", related_type="writing_entry")
        .first()
    )
    if not task:
        raise WritingError("Writing score task not found")
    entry = WritingEntry.objects.select_related("user", "prompt", "score").filter(user=task.user, entry_id=task.related_id).first()
    if not entry:
        raise WritingError("Writing entry not found")
    return task, entry


@transaction.atomic
def complete_score_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    task, entry = get_writing_score_task_and_entry(task_id)
    if task.is_terminal:
        return entry_payload(entry)
    score = normalize_score_payload(entry, payload)
    persist_score(entry, score)
    score["writing_profile"] = update_profile(entry, score)
    try:
        succeed_billable_ai_task(task.task_id, {"entry_id": entry.entry_id, "score": score}, payload.get("usage") if isinstance(payload.get("usage"), dict) else {})
    except AIOrchestrationError as exc:
        raise WritingError(str(exc)) from exc
    entry.refresh_from_db()
    return entry_payload(entry)


@transaction.atomic
def fallback_score_task(task_id: str, reason: str = "") -> dict[str, Any]:
    task, entry = get_writing_score_task_and_entry(task_id)
    if task.is_terminal:
        return entry_payload(entry)
    score = fallback_score(entry.task_type, entry.answer, reason=reason)
    persist_score(entry, score)
    score["writing_profile"] = update_profile(entry, score)
    try:
        fallback_billable_ai_task(task.task_id, reason or "AI scoring unavailable", {"entry_id": entry.entry_id, "score": score})
    except AIOrchestrationError as exc:
        raise WritingError(str(exc)) from exc
    entry.refresh_from_db()
    return entry_payload(entry)
