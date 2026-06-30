import calendar
import re
from typing import Any

from django.utils import timezone

from apps.ai.models import AITask
from apps.ai.services import task_payload

from .models import WritingEntry, WritingLearnerProfile, WritingPrompt, WritingScore
from .prompt_services import WRITING_TASK_LABELS, prompt_source_label
from .validation import WritingError, normalize_task_type


DEFAULT_WRITING_REPORT_LIMIT = 50
MAX_WRITING_REPORT_LIMIT = 100


def month_bounds(month_value: str | None):
    value = str(month_value or timezone.localdate().strftime("%Y-%m")).strip()
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        value = timezone.localdate().strftime("%Y-%m")
    year, month = [int(part) for part in value.split("-")]
    _, day_count = calendar.monthrange(year, month)
    return timezone.datetime(year, month, 1).date(), timezone.datetime(year, month, day_count).date()


def report_limit(value: Any) -> int:
    try:
        limit = int(str(value or "").strip() or DEFAULT_WRITING_REPORT_LIMIT)
    except (TypeError, ValueError):
        return DEFAULT_WRITING_REPORT_LIMIT
    if limit <= 0:
        return DEFAULT_WRITING_REPORT_LIMIT
    return min(limit, MAX_WRITING_REPORT_LIMIT)


def report_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if not status:
        return ""
    if status not in {WritingEntry.Status.SAVED, WritingEntry.Status.SCORED}:
        raise WritingError("Unknown writing status")
    return status


def spelling_terms_from_summary(value: Any) -> set[str]:
    text = str(value or "")
    return {match.group(1).lower() for match in re.finditer(r"`?([A-Za-z]{2,})`?\s*(?:->|\u2192)", text)}


def looks_like_single_word_spelling_fix(value: str) -> bool:
    compact = value.replace("`", "").strip().strip("。. ")
    arrow = "->" if "->" in compact else ("\u2192" if "\u2192" in compact else "")
    if not arrow:
        return False
    left, right = compact.split(arrow, 1)
    right = right.strip()
    for prefix in ("正确：", "正确:", "correct:", "Correct:"):
        if right.startswith(prefix):
            right = right[len(prefix):].strip()
    right = right.split("（", 1)[0].split("(", 1)[0].strip()
    return bool(re.fullmatch(r"[A-Za-z]{2,}", left.strip()) and re.fullmatch(r"[A-Za-z]{2,}", right))


def strip_spelling_from_language_upgrade(value: Any, *, spelling_summary: Any = "") -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    spelling_keywords = ("拼写", "错拼", "错别字", "spelling", "misspell", "typo")
    spelling_terms = spelling_terms_from_summary(spelling_summary)
    cleaned: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if any(keyword in lowered for keyword in spelling_keywords):
            continue
        if spelling_terms and any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in spelling_terms):
            continue
        compact = line.lstrip("-*• \t")
        if looks_like_single_word_spelling_fix(compact):
            continue
        cleaned.append(raw_line)
    return "\n".join(cleaned).strip()


def strip_spelling_from_paragraph_coaching(value: Any, *, spelling_summary: Any = "") -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    spelling_terms = spelling_terms_from_summary(spelling_summary)
    text = re.sub(r"[，,；;]?\s*但?有(?:明显)?拼写错误[，,]?\s*而且?", "，", text)
    text = re.sub(r"[，,；;]?\s*存在(?:明显)?拼写错误[，,。；;]?", "。", text)
    text = re.sub(r"[，,；;]?\s*拼写(?:方面)?(?:也)?(?:需要|可以|应当)?(?:再)?(?:检查|注意|修改|纠正)[，,。；;]?", "。", text)
    cleaned: list[str] = []
    for raw_line in text.splitlines():
        lowered = raw_line.lower()
        if spelling_terms and any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in spelling_terms):
            continue
        cleaned.append(raw_line)
    return "\n".join(cleaned).replace("，。", "。").strip(" ，,")


def paragraph_reviews_payload(value: Any, *, spelling_summary: Any = "") -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    reviews: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        review = dict(item)
        review["coaching"] = strip_spelling_from_paragraph_coaching(
            item.get("coaching") or "",
            spelling_summary=spelling_summary,
        )
        review["language_correction_upgrade"] = strip_spelling_from_language_upgrade(
            item.get("language_correction_upgrade") or item.get("expression_upgrade") or "",
            spelling_summary=spelling_summary,
        )
        reviews.append(review)
    return reviews


def score_payload(score: WritingScore | None) -> dict[str, Any] | None:
    if not score:
        return None
    analysis = score.analysis_payload or {}
    return {
        "overall_band": float(score.overall_band) if score.overall_band is not None else None,
        "task_response": float(score.task_response) if score.task_response is not None else None,
        "task_achievement": float(score.task_response) if score.task_response is not None else None,
        "coherence_cohesion": float(score.coherence_cohesion) if score.coherence_cohesion is not None else None,
        "lexical_resource": float(score.lexical_resource) if score.lexical_resource is not None else None,
        "grammatical_range_accuracy": float(score.grammar_range_accuracy) if score.grammar_range_accuracy is not None else None,
        "feedback_markdown": score.feedback_markdown,
        "grammar_corrections": score.grammar_corrections,
        "inline_annotations": analysis.get("inline_annotations", []),
        "data_accuracy_notes": analysis.get("data_accuracy_notes", []),
        "spelling_correction_summary": analysis.get("spelling_correction_summary", ""),
        "expression_upgrade_summary": analysis.get("expression_upgrade_summary", ""),
        "overall_review": analysis.get("overall_review", ""),
        "practice_focus": analysis.get("practice_focus", ""),
        "model_answer": analysis.get("model_answer", ""),
        "paragraph_reviews": paragraph_reviews_payload(
            analysis.get("paragraph_reviews"),
            spelling_summary=analysis.get("spelling_correction_summary", ""),
        ),
        "structure_advice_only": bool(analysis.get("structure_advice_only")),
        "structure_advice": analysis.get("structure_advice", ""),
        "analysis_backend": analysis.get("analysis_backend", score.source),
        "fallback_reason": analysis.get("fallback_reason", ""),
        "backend": score.source,
        "billing_usage": score.billing_metadata,
        "scored_at": score.scored_at.isoformat() if score.scored_at else None,
    }


def report_created_at(entry: WritingEntry):
    value = (entry.metadata or {}).get("report_created_at")
    if isinstance(value, str) and value.strip():
        try:
            parsed = timezone.datetime.fromisoformat(value.strip())
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            return parsed
        except ValueError:
            return None
    return None


def task_summary_payload(task: AITask | None) -> dict[str, Any] | None:
    if not task:
        return None
    return {
        "id": task.task_id,
        "task_type": task.task_type,
        "provider": task.provider,
        "model": task.model,
        "status": task.status,
        "progress_percent": task.progress_percent,
        "attempt_count": task.attempt_count,
        "max_attempts": task.max_attempts,
        "related_type": task.related_type,
        "related_id": task.related_id,
        "error_code": task.error_code,
        "error_message": task.error_message,
        "fallback_reason": task.fallback_reason,
        "available_at": task.available_at.isoformat() if task.available_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
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


def latest_writing_score_task(entry: WritingEntry) -> AITask | None:
    return (
        AITask.objects.filter(
            user=entry.user,
            task_type="writing_score",
            related_type="writing_entry",
            related_id=entry.entry_id,
        )
        .order_by("-created_at")
        .first()
    )


def writing_score_task_payload(entry: WritingEntry) -> dict[str, Any] | None:
    task = latest_writing_score_task(entry)
    return task_payload(task) if task else None


def active_writing_task_refreshes_score(task: AITask | None, score: WritingScore | None) -> bool:
    superseding_statuses = {AITask.Status.PENDING, AITask.Status.RUNNING}
    if not task or task.status not in superseding_statuses:
        return False
    if not score or not score.scored_at:
        return True
    return task.created_at >= score.scored_at


def normalize_prompt_highlights(value: Any, source_text: str = "") -> list[dict[str, int]]:
    text_len = len(str(source_text or ""))
    if not isinstance(value, list):
        return []
    ranges: list[dict[str, int]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            start = int(item.get("start", 0))
            end = int(item.get("end", 0))
        except (TypeError, ValueError):
            continue
        start = max(0, min(text_len, start))
        end = max(0, min(text_len, end))
        if end > start:
            ranges.append({"start": start, "end": end})
    ranges.sort(key=lambda item: (item["start"], item["end"]))
    return ranges


def entry_payload(entry: WritingEntry, include_answer: bool = True) -> dict[str, Any]:
    score = getattr(entry, "score", None)
    ai_task = latest_writing_score_task(entry)
    visible_score = None if active_writing_task_refreshes_score(ai_task, score) else score
    source_label = prompt_source_label(entry.prompt) if entry.prompt_id else str(entry.metadata.get("source_label") or "")
    prompt_highlights = normalize_prompt_highlights(entry.metadata.get("prompt_highlights"), entry.prompt_text)
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
        "image_url": entry.prompt.image_url if entry.prompt_id else entry.metadata.get("image_url", ""),
        "source": entry.prompt.source if entry.prompt_id else entry.metadata.get("source", ""),
        "source_book": entry.prompt.source_book if entry.prompt_id else entry.metadata.get("source_book"),
        "source_test": entry.prompt.source_test if entry.prompt_id else entry.metadata.get("source_test"),
        "source_question": entry.prompt.source_question if entry.prompt_id else entry.metadata.get("source_question"),
        "source_label": source_label,
        "prompt_highlights": prompt_highlights,
        "word_count": entry.word_count,
        "score": score_payload(visible_score),
        "ai_task": task_payload(ai_task) if ai_task else None,
        "writing_profile": profile_snapshot(getattr(entry.user, "writing_learner_profile", None)),
    }
    if include_answer:
        payload["answer"] = entry.answer
    return payload


def compact_entry_payload(entry: WritingEntry) -> dict[str, Any]:
    score = getattr(entry, "score", None)
    display_at = report_created_at(entry) if score else None
    # A scored report's time is pinned at first creation. If an older entry has no pin,
    # fall back to created_at (stable) rather than updated_at/saved_at, which move on
    # every edit and re-score — the report time must NOT track later modifications.
    if score and not display_at:
        display_at = entry.created_at
    display_at = display_at or getattr(entry, "latest_activity_at", None) or entry.updated_at
    sort_at = display_at
    source_label = prompt_source_label(entry.prompt) if entry.prompt_id else str(entry.metadata.get("source_label") or "")
    return {
        "id": entry.entry_id,
        "practice_date": entry.practice_date.isoformat(),
        "display_time": display_at.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%d %H:%M"),
        "sort_time": sort_at.isoformat(),
        "task_type": entry.task_type,
        "task_label": WRITING_TASK_LABELS.get(entry.task_type, "Writing"),
        "prompt_id": entry.prompt.prompt_id if entry.prompt_id else "",
        "title": entry.title or (entry.prompt.title if entry.prompt_id else "Writing"),
        "category": entry.prompt.category if entry.prompt_id else entry.metadata.get("category", ""),
        "prompt": entry.prompt_text,
        "source": entry.prompt.source if entry.prompt_id else entry.metadata.get("source", ""),
        "source_book": entry.prompt.source_book if entry.prompt_id else entry.metadata.get("source_book"),
        "source_test": entry.prompt.source_test if entry.prompt_id else entry.metadata.get("source_test"),
        "source_question": entry.prompt.source_question if entry.prompt_id else entry.metadata.get("source_question"),
        "source_label": source_label,
        "prompt_highlights": normalize_prompt_highlights(entry.metadata.get("prompt_highlights"), entry.prompt_text),
        "word_count": entry.word_count,
        "status": entry.status,
        "overall_band": float(score.overall_band) if score and score.overall_band is not None else None,
    }


def report_entry_payload(entry: WritingEntry, ai_task: AITask | None = None) -> dict[str, Any]:
    return {
        **compact_entry_payload(entry),
        "ai_task": task_summary_payload(ai_task),
    }


def writing_prompt_identity_key(prompt: WritingPrompt | None, *, task_type: str = "", prompt_text: str = "") -> tuple[str, str]:
    if prompt and prompt.source_book is not None and prompt.source_test is not None and prompt.source_question is not None:
        return (
            "cambridge",
            f"{prompt.task_type or task_type}:{prompt.source_book}:{prompt.source_test}:{prompt.source_question}",
        )
    if prompt:
        return ("prompt", prompt.prompt_id)
    return ("prompt_text", f"{task_type}:{str(prompt_text or '').strip()}")


def writing_entry_report_group_key(entry: WritingEntry) -> tuple[str, str]:
    if entry.prompt_id:
        return writing_prompt_identity_key(entry.prompt, task_type=entry.task_type, prompt_text=entry.prompt_text)
    return ("prompt_text", f"{entry.task_type}:{entry.prompt_text.strip()}")


def dedupe_report_entries(entries: list[WritingEntry]) -> list[WritingEntry]:
    selected: dict[tuple[str, str], WritingEntry] = {}
    for entry in entries:
        key = writing_entry_report_group_key(entry)
        current = selected.get(key)
        if not current:
            selected[key] = entry
            continue
        entry_scored = entry.status == WritingEntry.Status.SCORED and getattr(entry, "score", None) is not None
        current_scored = current.status == WritingEntry.Status.SCORED and getattr(current, "score", None) is not None
        if entry_scored and not current_scored:
            selected[key] = entry
    return list(selected.values())


def writing_report_sort_time(entry: WritingEntry):
    score = getattr(entry, "score", None)
    if score:
        return report_created_at(entry) or entry.created_at
    return entry.created_at


def latest_writing_tasks_for_entries(user, entry_ids: list[str]) -> dict[str, AITask]:
    if not entry_ids:
        return {}
    tasks = (
        AITask.objects.select_related("billing_reservation", "usage")
        .filter(
            user=user,
            task_type="writing_score",
            related_type="writing_entry",
            related_id__in=entry_ids,
        )
        .order_by("related_id", "-created_at", "-updated_at")
    )
    latest: dict[str, AITask] = {}
    for task in tasks:
        latest.setdefault(task.related_id, task)
    return latest


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


def writing_reports(user, query: dict[str, Any] | None = None) -> dict[str, Any]:
    query = query or {}
    limit = report_limit(query.get("limit"))
    status = report_status(query.get("status"))
    task_type_value = str(query.get("task_type") or "").strip()
    task_type = normalize_task_type(task_type_value) if task_type_value else ""

    queryset = (
        WritingEntry.objects.filter(user=user)
        .select_related("prompt", "score")
    )
    if status:
        queryset = queryset.filter(status=status)
    if task_type:
        queryset = queryset.filter(task_type=task_type)
    queryset = queryset.order_by("-created_at")

    deduped_entries = dedupe_report_entries(list(queryset))
    count = len(deduped_entries)
    deduped_entries.sort(key=writing_report_sort_time, reverse=True)
    entries = deduped_entries[:limit]
    task_map = latest_writing_tasks_for_entries(user, [entry.entry_id for entry in entries])
    return {
        "items": [report_entry_payload(entry, task_map.get(entry.entry_id)) for entry in entries],
        "count": count,
    }
