import hashlib
import uuid
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.ai.models import AITask
from apps.ai.orchestration import AIOrchestrationError, cancel_billable_ai_task, create_billable_ai_task, fallback_billable_ai_task, succeed_billable_ai_task
from apps.ai.services import task_payload

from .models import WritingEntry, WritingLearnerProfile, WritingPrompt, WritingScore
from .validation import WRITING_TASK_TYPES, WritingEntryDeleted, WritingError, normalize_task_type, paragraph_guidance, validate_answer_paragraphs, word_count, writing_entry_is_scored, writing_paragraphs


DEFAULT_WRITING_SCORE_RESERVATION_U = 1_000_000


from .prompt_services import (
    WRITING_CATEGORY_LABELS,
    WRITING_TASK_LABELS,
    agent_find_writing_prompts,
    agent_search_score,
    agent_search_score_details,
    cambridge_catalog,
    cambridge_source_label,
    data_writing_dir,
    list_prompts,
    normalize_category,
    positive_int,
    prompt_categories,
    prompt_payload,
    prompt_practice_statuses,
    prompt_source_label,
    prompt_status_payload,
    random_prompt,
    seed_prompt_files,
    stable_prompt_id,
    sync_seed_prompts,
    writing_prompt_sort_key,
)
from .report_services import (
    DEFAULT_WRITING_REPORT_LIMIT,
    MAX_WRITING_REPORT_LIMIT,
    compact_entry_payload,
    entry_payload,
    latest_writing_tasks_for_entries,
    looks_like_single_word_spelling_fix,
    month_bounds,
    normalize_prompt_highlights,
    paragraph_reviews_payload,
    profile_snapshot,
    report_entry_payload,
    report_limit,
    report_status,
    score_payload,
    spelling_terms_from_summary,
    strip_spelling_from_language_upgrade,
    strip_spelling_from_paragraph_coaching,
    task_summary_payload,
    writing_reports,
    writing_score_task_payload,
    writing_summary,
    writing_tag_text,
)


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
    existing = WritingEntry.objects.select_related("prompt", "score").filter(user=user, entry_id=entry_id).first() if entry_id else None
    if not entry_id:
        entry_id = uuid.uuid4().hex
    title = str(payload.get("title") or (prompt.title if prompt else "") or WRITING_TASK_LABELS[task_type])[:200]
    now = timezone.now()
    answer_changed = bool(existing and existing.answer != answer)
    create_revision = bool(answer_changed and existing and writing_entry_is_scored(existing))
    entry = WritingEntry(
        user=user,
        entry_id=uuid.uuid4().hex,
        task_type=task_type,
    ) if create_revision else (existing or WritingEntry(user=user, entry_id=entry_id, task_type=task_type))
    entry.prompt = prompt
    entry.task_type = task_type
    entry.practice_date = parse_practice_date(str(payload.get("practice_date") or "") or None)
    entry.title = title
    entry.prompt_text = prompt_text
    entry.answer = answer
    entry.word_count = word_count(answer)
    entry.status = WritingEntry.Status.SAVED if create_revision or answer_changed or not existing else entry.status
    entry.saved_at = now
    base_metadata = entry.metadata if not create_revision else (existing.metadata if existing else {})
    entry.metadata = {
        **(base_metadata or {}),
        "category": str(payload.get("category") or (prompt.category if prompt else "")),
        "image_url": str(payload.get("image_url") or (prompt.image_url if prompt else "")),
        "prompt_highlights": normalize_prompt_highlights(
            payload.get("prompt_highlights") if "prompt_highlights" in payload else (base_metadata or {}).get("prompt_highlights"),
            prompt_text,
        ),
    }
    if create_revision and existing:
        entry.metadata.update({
            "revision_parent_entry_id": existing.entry_id,
            "revision_source": "scored_entry_edit",
        })
    entry.save()
    if answer_changed and not create_revision:
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
def clone_entry_for_revision(user, entry_id: str) -> dict[str, Any]:
    source = (
        WritingEntry.objects.select_related("prompt", "score")
        .filter(user=user, entry_id=str(entry_id or "").strip())
        .first()
    )
    if not source:
        raise WritingError("Writing entry not found")
    if not writing_entry_is_scored(source):
        raise WritingError("Only scored writing entries can be cloned for revision")
    now = timezone.now()
    clone = WritingEntry.objects.create(
        user=user,
        entry_id=uuid.uuid4().hex,
        prompt=source.prompt,
        task_type=source.task_type,
        practice_date=timezone.localdate(),
        title=source.title,
        prompt_text=source.prompt_text,
        answer=source.answer,
        word_count=word_count(source.answer),
        status=WritingEntry.Status.SAVED,
        saved_at=now,
        metadata={
            **(source.metadata or {}),
            "revision_parent_entry_id": source.entry_id,
            "revision_source": "writing_report_edit",
        },
    )
    return entry_payload(clone)


@transaction.atomic
def delete_entry(user, entry_id: str) -> dict[str, Any]:
    entry = WritingEntry.objects.filter(user=user, entry_id=str(entry_id or "").strip()).first()
    if not entry:
        raise WritingError("Writing entry not found")
    pending_tasks = AITask.objects.filter(
        user=user,
        task_type="writing_score",
        related_type="writing_entry",
        related_id=entry.entry_id,
        status=AITask.Status.PENDING,
    )
    for task in pending_tasks:
        if task.billing_reservation_id:
            cancel_billable_ai_task(task.task_id, reason="Writing entry deleted", error_code="writing_entry_deleted")
        else:
            task.status = AITask.Status.CANCELLED
            task.error_code = "writing_entry_deleted"
            task.error_message = "Writing entry deleted"
            task.available_at = None
            task.finished_at = timezone.now()
            task.save(update_fields=["status", "error_code", "error_message", "available_at", "finished_at", "updated_at"])
    entry.delete()
    return {"ok": True}


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
    validate_answer_paragraphs(entry.task_type, entry.answer)
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


def fallback_analysis_payload(entry: WritingEntry, reason: str = "") -> dict[str, Any]:
    paragraphs = writing_paragraphs(entry.answer)
    message = reason or "AI writing report analysis is unavailable."
    return {
        "overall_review": "AI 写作报告暂不可用，当前结果是本地兜底评分。",
        "practice_focus": "请稍后重新生成 AI 报告；本地兜底不会判断你的逻辑分段。",
        "model_answer": "",
        "paragraph_reviews": [
            {
                "index": index + 1,
                "learner": paragraph,
                "model": "",
                "coaching": "本段尚未经过 AI 逻辑分析。",
            }
            for index, paragraph in enumerate(paragraphs)
        ],
        "inline_annotations": [],
        "spelling_correction_summary": "",
        "expression_upgrade_summary": "",
        "structure_advice_only": True,
        "structure_advice": message,
        "analysis_backend": "fallback",
        "fallback_reason": reason,
    }


def normalize_paragraph_reviews(value: Any, *, require_model: bool, spelling_summary: Any = "") -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise WritingError("AI structured analysis must include paragraph_reviews")
    reviews: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise WritingError("AI paragraph review rows must be objects")
        learner = str(item.get("learner") or "").strip()
        model = str(item.get("model") or "").strip()
        coaching = str(item.get("coaching") or "").strip()
        if not learner or not coaching or (require_model and not model):
            raise WritingError("AI paragraph review rows must include learner, model, and coaching")
        reviews.append(
            {
                "index": int(item.get("index") or index),
                "learner": learner,
                "model": model,
                "coaching": strip_spelling_from_paragraph_coaching(coaching, spelling_summary=spelling_summary),
                "language_correction_upgrade": strip_spelling_from_language_upgrade(
                    item.get("language_correction_upgrade") or item.get("expression_upgrade") or "",
                    spelling_summary=spelling_summary,
                ),
            }
        )
    return reviews


def normalize_inline_annotations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    allowed_types = {"spelling", "punctuation", "format", "grammar", "word_choice", "missing_word", "extra_word"}
    annotations: list[dict[str, Any]] = []
    for item in value[:40]:
        if not isinstance(item, dict):
            continue
        original = str(item.get("original") or "").strip()
        if not original:
            continue
        annotation_type = str(item.get("type") or item.get("category") or "grammar").strip().lower()
        if annotation_type not in allowed_types:
            annotation_type = "grammar"
        paragraph_index = item.get("paragraph_index")
        try:
            paragraph_index = int(paragraph_index) if paragraph_index not in (None, "") else None
        except (TypeError, ValueError):
            paragraph_index = None
        annotations.append(
            {
                "paragraph_index": paragraph_index,
                "original": original[:300],
                "type": annotation_type,
                "suggestion": str(item.get("suggestion") or "").strip()[:300],
                "explanation": str(item.get("explanation") or item.get("reason") or "").strip()[:500],
                "severity": str(item.get("severity") or "medium").strip().lower()[:40],
            }
        )
    return annotations


def normalize_analysis_payload(entry: WritingEntry, score: dict[str, Any]) -> dict[str, Any]:
    backend = str(score.get("backend") or "ai")
    if backend == "fallback":
        supplied = score.get("analysis_payload")
        if isinstance(supplied, dict):
            return {**supplied, "analysis_backend": "fallback"}
        return fallback_analysis_payload(entry, str(score.get("fallback_reason") or ""))

    overall_review = str(score.get("overall_review") or "").strip()
    practice_focus = str(score.get("practice_focus") or "").strip()
    if not overall_review or not practice_focus:
        raise WritingError("AI structured analysis must include overall_review and practice_focus")

    advice_only = bool(score.get("structure_advice_only"))
    structure_advice = str(score.get("structure_advice") or "").strip()
    spelling_summary = str(score.get("spelling_correction_summary") or "").strip()
    if advice_only:
        if not structure_advice:
            raise WritingError("AI structure-advice-only reports must include structure_advice")
        paragraph_reviews = normalize_paragraph_reviews(
            score.get("paragraph_reviews"),
            require_model=False,
            spelling_summary=spelling_summary,
        ) if isinstance(score.get("paragraph_reviews"), list) else []
        model_answer = ""
    else:
        paragraph_reviews = normalize_paragraph_reviews(
            score.get("paragraph_reviews"),
            require_model=True,
            spelling_summary=spelling_summary,
        )
        model_answer = str(score.get("model_answer") or "").strip()

    return {
        "overall_review": overall_review,
        "practice_focus": practice_focus,
        "model_answer": model_answer,
        "paragraph_reviews": paragraph_reviews,
        "inline_annotations": normalize_inline_annotations(score.get("inline_annotations")),
        "spelling_correction_summary": spelling_summary,
        "expression_upgrade_summary": str(score.get("expression_upgrade_summary") or "").strip(),
        "structure_advice_only": advice_only,
        "structure_advice": structure_advice,
        "analysis_backend": "ai",
    }


def persist_score(entry: WritingEntry, score: dict[str, Any]) -> None:
    task_response_value = score.get(task_score_key(entry.task_type))
    analysis_payload = normalize_analysis_payload(entry, score)
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
            "analysis_payload": analysis_payload,
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
    validate_answer_paragraphs(entry.task_type, entry.answer)
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
        "overall_review": str(score.get("overall_review") or payload.get("overall_review") or ""),
        "practice_focus": str(score.get("practice_focus") or payload.get("practice_focus") or ""),
        "model_answer": str(score.get("model_answer") or payload.get("model_answer") or ""),
        "paragraph_reviews": score.get("paragraph_reviews") if isinstance(score.get("paragraph_reviews"), list) else payload.get("paragraph_reviews"),
        "inline_annotations": score.get("inline_annotations") if isinstance(score.get("inline_annotations"), list) else payload.get("inline_annotations"),
        "spelling_correction_summary": str(score.get("spelling_correction_summary") or payload.get("spelling_correction_summary") or ""),
        "expression_upgrade_summary": str(score.get("expression_upgrade_summary") or payload.get("expression_upgrade_summary") or ""),
        "structure_advice_only": bool(score.get("structure_advice_only") or payload.get("structure_advice_only")),
        "structure_advice": str(score.get("structure_advice") or payload.get("structure_advice") or ""),
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
        raise WritingEntryDeleted("Writing entry was deleted")
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
