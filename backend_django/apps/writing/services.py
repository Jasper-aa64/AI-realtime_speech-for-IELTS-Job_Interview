import difflib
import hashlib
import math
import os
import re
import uuid
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.ai.models import AITask
from apps.ai.orchestration import AIOrchestrationError, cancel_billable_ai_task, create_billable_ai_task, fallback_billable_ai_task, succeed_billable_ai_task
from apps.ai.services import task_payload

from .custom_prompt_services import get_custom_prompt
from .models import CustomWritingPrompt, WritingEntry, WritingLearnerProfile, WritingPrompt, WritingScore
from .validation import WRITING_TASK_TYPES, WritingEntryDeleted, WritingError, normalize_task_type, paragraph_guidance, validate_answer_paragraphs, word_count, writing_entry_is_scored, writing_paragraphs


DEFAULT_WRITING_SCORE_RESERVATION_U = 0


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
    prompt_patterns,
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


def edited_paragraph_indices(previous_answer: str, next_answer: str) -> set[int]:
    previous = writing_paragraphs(previous_answer)
    current = writing_paragraphs(next_answer)
    changed: set[int] = set()
    for index in range(max(len(previous), len(current))):
        if (previous[index] if index < len(previous) else "") != (current[index] if index < len(current) else ""):
            changed.add(index + 1)
    return changed


def _split_sentences(text: str) -> list[str]:
    """Split an answer into whitespace-normalized sentences for sentence-level diffing.

    The annotation-preservation rule is sentence-scoped: edit a sentence at all and its
    annotations drop; sentences left untouched keep theirs. Normalizing internal
    whitespace keeps trivial spacing changes from falsely invalidating a sentence.
    """
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    if not raw:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", raw) if part.strip()]


def _normalize_answer_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _clean_inline_suggestion(value: Any) -> str:
    text = str(value or "").strip()
    for prefix in ("正确：", "正确:", "correct:", "Correct:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    return text.split("（", 1)[0].split("(", 1)[0].strip()


def _local_replacement_fix_annotation_indices(annotations: list[dict[str, Any]], previous_answer: str, next_answer: str) -> set[int]:
    """Find inline annotations consumed by a precise local Fix action.

    Normal manual sentence edits still invalidate that whole sentence. The exception is
    the report popover Fix for `original -> suggestion`: when the new answer equals
    the old answer with exactly one annotation span replaced by its suggestion, only
    that annotation is consumed and nearby untouched annotations survive. This is not
    limited to spelling words; short grammar and phrase replacements use the same rule.
    """
    normalized_next = _normalize_answer_text(next_answer)
    consumed: set[int] = set()
    for index, item in enumerate(annotations):
        original = re.sub(r"\s+", " ", str(item.get("original") or "")).strip()
        suggestion = _clean_inline_suggestion(item.get("suggestion"))
        if not (original and suggestion and original != suggestion):
            continue
        matched = False
        start = previous_answer.find(original)
        while start >= 0:
            candidate = f"{previous_answer[:start]}{suggestion}{previous_answer[start + len(original):]}"
            if _normalize_answer_text(candidate) == normalized_next:
                matched = True
                break
            start = previous_answer.find(original, start + 1)
        if matched:
            consumed.add(index)
    return consumed


def _paragraph_similarity(left: str, right: str) -> float:
    return difflib.SequenceMatcher(None, str(left or ""), str(right or "")).ratio()


def _paragraph_index_map(previous_paragraphs: list[str], current_paragraphs: list[str]) -> dict[int, int]:
    mapped: dict[int, int] = {}
    used_current: set[int] = set()
    for old_index, old_text in enumerate(previous_paragraphs):
        ranked = sorted(
            (
                (_paragraph_similarity(old_text, current_text), new_index)
                for new_index, current_text in enumerate(current_paragraphs)
                if new_index not in used_current
            ),
            key=lambda item: (-item[0], item[1]),
        )
        if ranked and ranked[0][0] >= 0.35:
            mapped[old_index + 1] = ranked[0][1] + 1
            used_current.add(ranked[0][1])
    return mapped


def _remap_inline_annotation(
    item: dict[str, Any],
    *,
    previous_paragraphs: list[str],
    current_paragraphs: list[str],
    paragraph_map: dict[int, int],
) -> dict[str, Any] | None:
    original = str(item.get("original") or "").strip()
    if not original:
        return None
    try:
        old_paragraph_index = int(item.get("paragraph_index")) if item.get("paragraph_index") not in (None, "") else None
    except (TypeError, ValueError):
        old_paragraph_index = None

    candidate_indices: list[int] = []
    mapped_index = paragraph_map.get(old_paragraph_index or -1)
    if mapped_index:
        candidate_indices.append(mapped_index)
    if old_paragraph_index and 0 < old_paragraph_index <= len(previous_paragraphs):
        old_text = previous_paragraphs[old_paragraph_index - 1]
        ranked = sorted(
            ((_paragraph_similarity(old_text, text), index + 1) for index, text in enumerate(current_paragraphs)),
            key=lambda value: (-value[0], value[1]),
        )
        candidate_indices.extend(index for _score, index in ranked)
    candidate_indices.extend(range(1, len(current_paragraphs) + 1))

    seen: set[int] = set()
    for new_index in candidate_indices:
        if new_index in seen or new_index < 1 or new_index > len(current_paragraphs):
            continue
        seen.add(new_index)
        if original in current_paragraphs[new_index - 1]:
            return {**item, "paragraph_index": new_index}
    return None


def _legacy_preserve_score_after_answer_edit(entry: WritingEntry, previous_answer: str, next_answer: str) -> None:
    changed_indices = edited_paragraph_indices(previous_answer, next_answer)
    if not changed_indices:
        return
    score = getattr(entry, "score", None) or WritingScore.objects.filter(entry=entry).first()
    if not score:
        return
    analysis = dict(score.analysis_payload or {})
    previous_paragraphs = writing_paragraphs(previous_answer)
    current_paragraphs = writing_paragraphs(next_answer)
    annotations = []
    for item in analysis.get("inline_annotations") or []:
        if not isinstance(item, dict):
            continue
        try:
            paragraph_index = int(item.get("paragraph_index")) if item.get("paragraph_index") not in (None, "") else None
        except (TypeError, ValueError):
            paragraph_index = None
        original = str(item.get("original") or "")
        if paragraph_index in changed_indices:
            continue
        if paragraph_index is None and any(original and original in (previous_paragraphs[i - 1] if i - 1 < len(previous_paragraphs) else "") for i in changed_indices):
            continue
        annotations.append(item)
    analysis["inline_annotations"] = annotations

    reviews = []
    for offset, item in enumerate(analysis.get("paragraph_reviews") or []):
        if not isinstance(item, dict):
            continue
        try:
            paragraph_index = int(item.get("index") or offset + 1)
        except (TypeError, ValueError):
            paragraph_index = offset + 1
        if paragraph_index in changed_indices:
            reviews.append({
                **item,
                "index": paragraph_index,
                "learner": current_paragraphs[paragraph_index - 1] if paragraph_index - 1 < len(current_paragraphs) else "",
                "model": "",
                "coaching": "这一段已按你的修改保存。重新提交并生成报告后，会刷新这一段的 AI 改写与辅导。",
                "language_correction_upgrade": "",
            })
        else:
            reviews.append(item)
    if reviews:
        analysis["paragraph_reviews"] = reviews
    score.analysis_payload = analysis
    score.save(update_fields=["analysis_payload", "updated_at"])


def preserve_score_after_answer_edit(entry: WritingEntry, previous_answer: str, next_answer: str) -> None:
    changed_indices = edited_paragraph_indices(previous_answer, next_answer)
    if not changed_indices:
        return
    score = getattr(entry, "score", None) or WritingScore.objects.filter(entry=entry).first()
    if not score:
        return
    analysis = dict(score.analysis_payload or {})
    previous_paragraphs = writing_paragraphs(previous_answer)
    current_paragraphs = writing_paragraphs(next_answer)
    paragraph_map = _paragraph_index_map(previous_paragraphs, current_paragraphs)
    previous_sentences = _split_sentences(previous_answer)
    current_sentence_set = set(_split_sentences(next_answer))
    raw_annotations = [item for item in analysis.get("inline_annotations") or [] if isinstance(item, dict)]
    consumed_fix_indices = _local_replacement_fix_annotation_indices(raw_annotations, previous_answer, next_answer)
    fix_host_sentences = {
        sentence
        for index in consumed_fix_indices
        for sentence in previous_sentences
        if re.sub(r"\s+", " ", str(raw_annotations[index].get("original") or "")).strip() in sentence
    }

    annotations = []
    for annotation_index, item in enumerate(raw_annotations):
        original = re.sub(r"\s+", " ", str(item.get("original") or "")).strip()
        if not original:
            continue
        if annotation_index in consumed_fix_indices:
            continue
        # Sentence-level invalidation: locate the OLD sentence that hosted this
        # annotation; it only survives if that exact sentence is still present in the
        # new answer. Touch a sentence at all and its annotations drop; sentences left
        # untouched keep theirs (so fixing one sentence never disturbs another's marks).
        host_sentence = next((sentence for sentence in previous_sentences if original in sentence), None)
        if host_sentence is not None:
            if host_sentence not in current_sentence_set and not (host_sentence in fix_host_sentences and original in _normalize_answer_text(next_answer)):
                continue
        elif not any(original in sentence for sentence in current_sentence_set):
            continue
        remapped = _remap_inline_annotation(
            item,
            previous_paragraphs=previous_paragraphs,
            current_paragraphs=current_paragraphs,
            paragraph_map=paragraph_map,
        )
        if remapped:
            annotations.append(remapped)
    analysis["inline_annotations"] = annotations

    raw_reviews = [item for item in analysis.get("paragraph_reviews") or [] if isinstance(item, dict)]
    reviews = []
    used_review_indices: set[int] = set()
    for offset, item in enumerate(raw_reviews):
        try:
            old_paragraph_index = int(item.get("index") or offset + 1)
        except (TypeError, ValueError):
            old_paragraph_index = offset + 1
        new_paragraph_index = paragraph_map.get(old_paragraph_index, old_paragraph_index)
        if new_paragraph_index < 1 or new_paragraph_index > len(current_paragraphs) or new_paragraph_index in used_review_indices:
            continue
        used_review_indices.add(new_paragraph_index)
        current_text = current_paragraphs[new_paragraph_index - 1]
        reviews.append({**item, "index": new_paragraph_index, "learner": current_text})
    if raw_reviews:
        for paragraph_index, current_text in enumerate(current_paragraphs, start=1):
            if paragraph_index in used_review_indices:
                continue
            reviews.append({
                "index": paragraph_index,
                "learner": current_text,
                "model": "",
                "coaching": "这一段已保存。重新生成报告后，AI 会补充这一段的改写与辅导。",
                "language_correction_upgrade": "",
            })
        reviews.sort(key=lambda review: int(review.get("index") or 0))
        analysis["paragraph_reviews"] = reviews
    score.analysis_payload = analysis
    score.save(update_fields=["analysis_payload", "updated_at"])


def scored_entry_for_same_prompt(
    user,
    *,
    task_type: str,
    prompt: WritingPrompt | None,
    prompt_text: str,
    custom_prompt: CustomWritingPrompt | None = None,
) -> WritingEntry | None:
    queryset = (
        WritingEntry.objects.select_related("prompt", "custom_prompt", "score")
        .filter(user=user, task_type=task_type, status=WritingEntry.Status.SCORED, score__isnull=False)
        .order_by("-updated_at", "-created_at")
    )
    if custom_prompt:
        return queryset.filter(custom_prompt=custom_prompt).first()
    if prompt:
        if prompt.source_book is not None and prompt.source_test is not None and prompt.source_question is not None:
            source_match = queryset.filter(
                prompt__source_book=prompt.source_book,
                prompt__source_test=prompt.source_test,
                prompt__source_question=prompt.source_question,
            ).first()
            if source_match:
                return source_match
        return queryset.filter(prompt=prompt).first()
    normalized_prompt_text = str(prompt_text or "").strip()
    if normalized_prompt_text:
        return queryset.filter(prompt__isnull=True, prompt_text=normalized_prompt_text).first()
    return None


def maintained_entry_for_same_prompt(
    user,
    *,
    task_type: str,
    prompt: WritingPrompt | None,
    prompt_text: str,
    custom_prompt: CustomWritingPrompt | None = None,
) -> WritingEntry | None:
    """Return the single essay the user is maintaining for this question.

    Historical duplicate rows can exist from older flows. Prefer a scored report
    because it is the authoritative maintained essay; otherwise prefer a non-empty
    saved draft, then the newest empty draft only when that is all that exists.
    """
    queryset = (
        WritingEntry.objects.select_related("prompt", "custom_prompt", "score")
        .filter(user=user, task_type=task_type)
    )
    if custom_prompt:
        queryset = queryset.filter(custom_prompt=custom_prompt)
    elif prompt:
        if prompt.source_book is not None and prompt.source_test is not None and prompt.source_question is not None:
            queryset = queryset.filter(
                prompt__source_book=prompt.source_book,
                prompt__source_test=prompt.source_test,
                prompt__source_question=prompt.source_question,
            )
        else:
            queryset = queryset.filter(prompt=prompt)
    else:
        normalized_prompt_text = str(prompt_text or "").strip()
        if not normalized_prompt_text:
            return None
        queryset = queryset.filter(prompt__isnull=True, prompt_text=normalized_prompt_text)

    candidates = list(queryset)
    if not candidates:
        return None
    candidates.sort(
        key=lambda entry: (
            1 if writing_entry_is_scored(entry) else 0,
            1 if str(entry.answer or "").strip() else 0,
            entry.updated_at,
            entry.created_at,
        ),
        reverse=True,
    )
    return candidates[0]


def entry_for_prompt(
    user,
    *,
    task_type: str,
    prompt_id: str = "",
    prompt_text: str = "",
    custom_prompt_id: str = "",
) -> dict[str, Any]:
    """The single essay the user maintains for a given question (scored or not).

    One essay per question: opening a prompt should reload whatever the user last
    saved for it, regardless of scoring status. Returns {"entry": payload|None}.
    """
    normalized_task = normalize_task_type(str(task_type or ""))
    prompt = (
        WritingPrompt.objects.filter(prompt_id=str(prompt_id or "").strip(), task_type=normalized_task, is_active=True).first()
        if str(prompt_id or "").strip()
        else None
    )
    custom_id = str(custom_prompt_id or "").strip()
    if not custom_id and not prompt and str(prompt_id or "").strip():
        custom_id = str(prompt_id).strip()
    custom_prompt = get_custom_prompt(user, custom_id) if custom_id else None
    entry = maintained_entry_for_same_prompt(
        user,
        task_type=normalized_task,
        prompt=prompt,
        prompt_text=prompt_text,
        custom_prompt=custom_prompt,
    )
    return {"entry": entry_payload(entry) if entry else None}


@transaction.atomic
def save_entry(user, payload: dict[str, Any]) -> dict[str, Any]:
    answer = str(payload.get("answer") or "")
    task_type = normalize_task_type(str(payload.get("task_type") or ""))
    entry_id = str(payload.get("id") or "").strip()
    existing = (
        WritingEntry.objects.select_related("prompt", "custom_prompt", "score")
        .filter(user=user, entry_id=entry_id)
        .first()
        if entry_id else None
    )
    existing_custom_id = str((existing.metadata or {}).get("custom_prompt_id") or "") if existing else ""
    custom_prompt_id = str(payload.get("custom_prompt_id") or "").strip()
    custom_prompt = None
    if custom_prompt_id:
        try:
            custom_prompt = get_custom_prompt(user, custom_prompt_id)
        except WritingError:
            if not existing or existing_custom_id != custom_prompt_id or (existing.metadata or {}).get("source") != "custom":
                raise
    elif existing and existing.custom_prompt:
        # Scoring / report updates don't resend the custom id — keep the
        # linkage so the maintained-essay lookup and practice status still
        # resolve to this prompt instead of flipping back to 未练习.
        custom_prompt = existing.custom_prompt
    if custom_prompt and custom_prompt.task_type != task_type:
        raise WritingError("Custom writing prompt task type does not match entry")
    prompt_id = str(payload.get("prompt_id") or "").strip()
    prompt = WritingPrompt.objects.filter(prompt_id=prompt_id, task_type=task_type, is_active=True).first() if prompt_id else None
    if custom_prompt and prompt:
        raise WritingError("Choose either a formal or custom writing prompt")
    if custom_prompt:
        # Keep the entry's prompt snapshot when the same custom prompt is
        # re-saved; otherwise snapshot the prompt's current text.
        prompt_text = (
            existing.prompt_text
            if existing and existing.custom_prompt_id == custom_prompt.id
            else custom_prompt.prompt_markdown
        )
    else:
        prompt_text = str(payload.get("prompt") or (prompt.prompt if prompt else "")).strip()
    if not prompt_text:
        raise WritingError("Missing writing prompt")
    preserve_score_requested = payload.get("preserve_score", False) is True
    scored_same_prompt = None
    if not existing and not entry_id:
        maintained_same_prompt = maintained_entry_for_same_prompt(
            user,
            task_type=task_type,
            prompt=prompt,
            prompt_text=prompt_text,
            custom_prompt=custom_prompt,
        )
        if maintained_same_prompt:
            existing = maintained_same_prompt
            entry_id = existing.entry_id
            existing_custom_id = str((existing.metadata or {}).get("custom_prompt_id") or "")
            if existing_custom_id == custom_prompt_id and custom_prompt_id:
                prompt_text = existing.prompt_text
    elif existing and preserve_score_requested and not writing_entry_is_scored(existing):
        scored_same_prompt = scored_entry_for_same_prompt(
            user,
            task_type=task_type,
            prompt=prompt,
            prompt_text=prompt_text,
            custom_prompt=custom_prompt,
        )
        if scored_same_prompt:
            existing = scored_same_prompt
            entry_id = existing.entry_id
            existing_custom_id = str((existing.metadata or {}).get("custom_prompt_id") or "")
            if existing_custom_id == custom_prompt_id and custom_prompt_id:
                prompt_text = existing.prompt_text
    if not entry_id:
        entry_id = uuid.uuid4().hex
    title = str(
        existing.title
        if existing and existing_custom_id == custom_prompt_id and custom_prompt_id
        else custom_prompt.title
        if custom_prompt
        else payload.get("title") or (prompt.title if prompt else "") or WRITING_TASK_LABELS[task_type]
    )[:200]
    now = timezone.now()
    previous_answer = existing.answer if existing else ""
    answer_changed = bool(existing and existing.answer != answer)
    preserve_score = bool(
        answer_changed
        and existing
        and writing_entry_is_scored(existing)
        and preserve_score_requested
    )
    entry = existing or WritingEntry(user=user, entry_id=entry_id, task_type=task_type)
    entry.prompt = prompt
    entry.custom_prompt = custom_prompt
    entry.task_type = task_type
    if existing and not payload.get("practice_date"):
        entry.practice_date = existing.practice_date
    else:
        entry.practice_date = parse_practice_date(str(payload.get("practice_date") or "") or None)
    entry.title = title
    entry.prompt_text = prompt_text
    entry.answer = answer
    entry.word_count = word_count(answer)
    entry.status = WritingEntry.Status.SAVED if (answer_changed and not preserve_score) or not existing else entry.status
    entry.saved_at = now
    base_metadata = entry.metadata or {}
    metadata = {
        **(base_metadata or {}),
        "category": str(payload.get("category") or (custom_prompt.category if custom_prompt else (prompt.category if prompt else ""))),
        "image_url": str(payload.get("image_url") or (prompt.image_url if prompt else "")),
        "prompt_highlights": normalize_prompt_highlights(
            payload.get("prompt_highlights") if "prompt_highlights" in payload else (base_metadata or {}).get("prompt_highlights"),
            prompt_text,
        ),
    }
    is_custom_snapshot = bool(
        custom_prompt
        or (custom_prompt_id and existing_custom_id == custom_prompt_id and base_metadata.get("source") == "custom")
    )
    if is_custom_snapshot:
        metadata["source"] = "custom"
        metadata["source_label"] = "自定义练习"
        metadata["custom_prompt_id"] = custom_prompt_id or str(custom_prompt.id)
    else:
        metadata.pop("custom_prompt_id", None)
        if metadata.get("source") == "custom":
            metadata.pop("source", None)
            metadata.pop("source_label", None)
        if prompt:
            metadata["source"] = prompt.source
    entry.metadata = metadata
    entry.save()
    if answer_changed and preserve_score:
        preserve_score_after_answer_edit(entry, previous_answer, answer)
        entry.refresh_from_db()
    elif answer_changed:
        WritingScore.objects.filter(entry=entry).delete()
        entry.refresh_from_db()
    return entry_payload(entry)


def get_entry(user, entry_id: str) -> dict[str, Any]:
    entry = (
        WritingEntry.objects.select_related("user", "prompt", "custom_prompt", "score")
        .filter(user=user, entry_id=str(entry_id or "").strip())
        .first()
    )
    if not entry:
        raise WritingError("Writing entry not found")
    return entry_payload(entry)


@transaction.atomic
def clone_entry_for_revision(user, entry_id: str) -> dict[str, Any]:
    source = (
        WritingEntry.objects.select_related("prompt", "custom_prompt", "score")
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
        custom_prompt=source.custom_prompt,
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
def delete_entry_report(user, entry_id: str) -> dict[str, Any]:
    entry = WritingEntry.objects.select_related("prompt", "custom_prompt", "score").filter(user=user, entry_id=str(entry_id or "").strip()).first()
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
            cancel_billable_ai_task(task.task_id, reason="Writing report deleted", error_code="writing_report_deleted")
        else:
            task.status = AITask.Status.CANCELLED
            task.error_code = "writing_report_deleted"
            task.error_message = "Writing report deleted"
            task.available_at = None
            task.finished_at = timezone.now()
            task.save(update_fields=["status", "error_code", "error_message", "available_at", "finished_at", "updated_at"])
    WritingScore.objects.filter(entry=entry).delete()
    entry.status = WritingEntry.Status.SAVED
    # Deleting the report releases the pinned report time: the essay is kept (so the
    # user still finds it next time they open this question), but a future re-score
    # starts a brand-new report whose time is set fresh at that creation.
    metadata = dict(entry.metadata or {})
    metadata.pop("report_created_at", None)
    metadata["report_deleted_at"] = timezone.now().isoformat()
    entry.metadata = metadata
    entry.save(update_fields=["status", "metadata", "updated_at"])
    entry.refresh_from_db()
    return entry_payload(entry)


@transaction.atomic
def create_score_task(user, entry_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    entry = (
        WritingEntry.objects.select_related("user", "prompt", "custom_prompt", "score")
        .filter(user=user, entry_id=str(entry_id or "").strip())
        .first()
    )
    if not entry:
        raise WritingError("Writing entry not found")
    if not entry.answer.strip():
        raise WritingError("Write an answer before requesting AI scoring.")
    validate_answer_paragraphs(entry.task_type, entry.answer)
    answer_hash = hashlib.sha1(entry.answer.encode("utf-8")).hexdigest()[:16]
    # Freeze the user's chosen AI source as the task's requested intent so the
    # completion path can fall back to it when the response lacks a model, and
    # so the task row never silently records the internal codex default.
    profile_source = str(getattr(getattr(user, "profile", None), "report_ai_source", "") or "").strip().lower()
    requested_provider = str(payload.get("provider") or "").strip()
    if not requested_provider:
        requested_provider = "claude" if profile_source == "claude" else ("openai" if profile_source in {"gpt", "openai"} else "")
    requested_model = str(payload.get("model") or "").strip()
    if not requested_model:
        if requested_provider == "claude":
            requested_model = str(os.environ.get("CLAUDE_CLI_MODEL") or "").strip() or "sonnet"
        elif requested_provider == "openai":
            requested_model = str(getattr(settings, "AI_HTTP_MODEL", "") or "").strip()
    base_idempotency_key = f"writing_score:{entry.entry_id}:{answer_hash}"
    idempotency_key = base_idempotency_key
    force_regenerate = payload.get("force") is True or str(payload.get("force") or "").strip().lower() in {"1", "true", "yes"}
    if force_regenerate:
        active_task = (
            AITask.objects.filter(
                user=user,
                task_type="writing_score",
                related_type="writing_entry",
                related_id=entry.entry_id,
                request_payload__answer_hash=answer_hash,
                status__in=[AITask.Status.PENDING, AITask.Status.RUNNING],
            )
            .order_by("-created_at", "-updated_at")
            .first()
        )
        if active_task:
            return {"created": False, "task": task_payload(active_task), "entry": entry_payload(entry)}
        idempotency_key = f"{base_idempotency_key}:regen:{uuid.uuid4().hex[:12]}"
    # If a previous task with the same key failed, remove it so the user can retry.
    # Only block re-submission when the previous task succeeded (same content already scored).
    AITask.objects.filter(
        user=user,
        idempotency_key=base_idempotency_key if not force_regenerate else idempotency_key,
        status=AITask.Status.FAILED,
    ).delete()
    prompt_chart_facts = entry.prompt.chart_facts if entry.prompt_id and isinstance(entry.prompt.chart_facts, dict) else {}
    prompt_chart_facts_status = entry.prompt.chart_facts_status if entry.prompt_id else "none"
    try:
        task, created = create_billable_ai_task(
            user=user,
            task_type="writing_score",
            reserved_u=DEFAULT_WRITING_SCORE_RESERVATION_U,
            idempotency_key=idempotency_key,
            provider=requested_provider or None,
            model=requested_model,
            related_type="writing_entry",
            related_id=entry.entry_id,
            prompt_version=str(payload.get("prompt_version") or "writing_score_v1"),
            request_payload={
                "entry_id": entry.entry_id,
                "requested_provider": requested_provider,
                "requested_model": requested_model,
                "task_type": entry.task_type,
                "prompt_id": entry.prompt.prompt_id if entry.prompt_id else "",
                "custom_prompt_id": str(entry.custom_prompt_id) if entry.custom_prompt_id else str((entry.metadata or {}).get("custom_prompt_id") or ""),
                "title": entry.title,
                "prompt": entry.prompt_text,
                "answer": entry.answer,
                "word_count": entry.word_count,
                "answer_hash": answer_hash,
                "chart_facts": prompt_chart_facts if entry.task_type == WritingPrompt.TaskType.TASK1_ACADEMIC else {},
                "chart_facts_status": prompt_chart_facts_status if entry.task_type == WritingPrompt.TaskType.TASK1_ACADEMIC else "none",
            },
            metadata={"source": "writing_score_task"},
        )
    except AIOrchestrationError as exc:
        raise WritingError(str(exc)) from exc
    if created:
        original_metadata = dict(entry.metadata or {})
        metadata = dict(original_metadata)
        # A successfully queued task is a live report again, even when the user
        # previously deleted its report while keeping the maintained essay.
        metadata.pop("report_deleted_at", None)
        if force_regenerate:
            # Replace the report only after a new task exists so a rejected task
            # submission never destroys a report the learner can still read.
            WritingScore.objects.filter(entry=entry).delete()
            entry.status = WritingEntry.Status.SAVED
            metadata.pop("report_created_at", None)
            metadata["report_regeneration_started_at"] = timezone.now().isoformat()
        if force_regenerate or metadata != original_metadata:
            entry.metadata = metadata
            entry.save(update_fields=["status", "metadata", "updated_at"])
            entry.refresh_from_db()
    return {"created": created, "task": task_payload(task), "entry": entry_payload(entry)}


def decimal_band(value: float) -> Decimal:
    return Decimal(str(round(float(value) * 2) / 2)).quantize(Decimal("0.1"))


def ielts_overall_band(*criteria: float) -> float:
    """IELTS Writing overall band = the average of the four equally-weighted
    criteria (TR/TA, CC, LR, GRA), rounded to the nearest half band.

    Uses round-half-UP (not Python's banker's ``round``) so a .25 average goes up
    to .5 and .75 up to the next whole band, per the official IELTS rule —
    e.g. 7.875 -> 8.0, 7.25 -> 7.5, 6.625 -> 6.5. We compute this ourselves
    instead of trusting the model's own ``overall_band`` field, which can be
    internally inconsistent with the four sub-scores it returns.
    """
    mean = sum(criteria) / len(criteria)
    return math.floor(mean * 2 + 0.5) / 2


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


def scoring_provenance(score: dict[str, Any]) -> dict[str, str]:
    """Immutable provenance keys copied into the report snapshot.

    The completion path sets ``score["scoring_provider"]``/``score["scoring_model"]``
    from the REAL executed provider/model; fallback scoring sets provider
    "fallback" and an empty model. Reports must never infer a model later.
    """
    return {
        "scoring_provider": str(score.get("scoring_provider") or "").strip(),
        "scoring_model": str(score.get("scoring_model") or "").strip(),
    }


def normalize_analysis_payload(entry: WritingEntry, score: dict[str, Any]) -> dict[str, Any]:
    backend = str(score.get("backend") or "ai")
    provenance = scoring_provenance(score)
    if backend == "fallback":
        supplied = score.get("analysis_payload")
        if isinstance(supplied, dict):
            return {**supplied, "analysis_backend": "fallback", **provenance}
        return {**fallback_analysis_payload(entry, str(score.get("fallback_reason") or "")), **provenance}

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
        "data_accuracy_notes": score.get("data_accuracy_notes") if isinstance(score.get("data_accuracy_notes"), list) else [],
        "spelling_correction_summary": spelling_summary,
        "expression_upgrade_summary": str(score.get("expression_upgrade_summary") or "").strip(),
        "structure_advice_only": advice_only,
        "structure_advice": structure_advice,
        "analysis_backend": "ai",
        **provenance,
    }


def persist_score(entry: WritingEntry, score: dict[str, Any]) -> None:
    task_response_value = score.get(task_score_key(entry.task_type))
    analysis_payload = normalize_analysis_payload(entry, score)
    now = timezone.now()
    metadata = dict(entry.metadata or {})
    metadata.setdefault("report_created_at", now.isoformat())
    metadata.pop("report_deleted_at", None)
    entry.metadata = metadata
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
            "scored_at": now,
        },
    )
    entry.status = WritingEntry.Status.SCORED
    entry.saved_at = entry.saved_at or now
    entry.practice_date = entry.practice_date or timezone.localdate()
    entry.save(update_fields=["status", "saved_at", "practice_date", "metadata", "updated_at"])

    # Spelling mistakes are historical training evidence. Archive them while
    # this score still exists so report edits, regeneration, and deletion can
    # never retract a word the learner has already misspelled.
    from .spelling_services import harvest_spelling_words
    harvest_spelling_words(entry.user)


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
    if score.get("backend") == "fallback":
        score["profile_tags"] = profile_tags(entry, score)
        score["personalization_note"] = "本次使用系统默认评分，未计入你的写作画像。"
        existing_profile = WritingLearnerProfile.objects.filter(user=entry.user).first()
        return profile_snapshot(existing_profile) or {
            "total_scored": 0,
            "average_overall_band": None,
            "primary_focus": "insufficient_data",
            "primary_focus_text": "还需要真实 AI 评分作文来形成稳定画像。",
            "top_tags": [],
            "recent_evidence": [],
        }
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
    payload = entry_payload(entry)
    payload["writing_profile"] = score["writing_profile"]
    return payload


def normalize_score_payload(entry: WritingEntry, payload: dict[str, Any]) -> dict[str, Any]:
    score = payload.get("score") if isinstance(payload.get("score"), dict) else payload
    if not isinstance(score, dict):
        raise WritingError("score must be an object")
    task_key = task_score_key(entry.task_type)
    required = ["overall_band", task_key, "coherence_cohesion", "lexical_resource", "grammatical_range_accuracy"]
    missing = [key for key in required if score.get(key) is None]
    if missing:
        raise WritingError(f"Missing score fields: {', '.join(missing)}")
    task_value = float(score[task_key])
    coherence_cohesion = float(score["coherence_cohesion"])
    lexical_resource = float(score["lexical_resource"])
    grammatical_range_accuracy = float(score["grammatical_range_accuracy"])
    return {
        # Derive the overall from the four criteria (IELTS averaging rule) rather
        # than trusting the model's own overall_band, which can disagree with its
        # sub-scores — e.g. it returned 7.5 while TR7.5/CC8/LR8/GRA8 averages to 8.0.
        "overall_band": ielts_overall_band(
            task_value, coherence_cohesion, lexical_resource, grammatical_range_accuracy
        ),
        task_key: task_value,
        "coherence_cohesion": coherence_cohesion,
        "lexical_resource": lexical_resource,
        "grammatical_range_accuracy": grammatical_range_accuracy,
        "feedback_markdown": str(score.get("feedback_markdown") or ""),
        "grammar_corrections": score.get("grammar_corrections") if isinstance(score.get("grammar_corrections"), list) else [],
        "overall_review": str(score.get("overall_review") or payload.get("overall_review") or ""),
        "practice_focus": str(score.get("practice_focus") or payload.get("practice_focus") or ""),
        "model_answer": str(score.get("model_answer") or payload.get("model_answer") or ""),
        "paragraph_reviews": score.get("paragraph_reviews") if isinstance(score.get("paragraph_reviews"), list) else payload.get("paragraph_reviews"),
        "inline_annotations": score.get("inline_annotations") if isinstance(score.get("inline_annotations"), list) else payload.get("inline_annotations"),
        "data_accuracy_notes": score.get("data_accuracy_notes") if isinstance(score.get("data_accuracy_notes"), list) else payload.get("data_accuracy_notes"),
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


def score_task_matches_current_entry(task: AITask, entry: WritingEntry) -> bool:
    """A task may finish after the learner has already saved a newer essay."""
    request_payload = task.request_payload if isinstance(task.request_payload, dict) else {}
    expected_hash = str(request_payload.get("answer_hash") or "").strip()
    if not expected_hash:
        # Older tasks did not persist a snapshot hash. Keep their legacy behavior
        # instead of calling them stale without evidence.
        return True
    current_hash = hashlib.sha1(str(entry.answer or "").encode("utf-8")).hexdigest()[:16]
    return expected_hash == current_hash


@transaction.atomic
def complete_score_task(task_id: str, payload: dict[str, Any], provider: str = "", model: str = "") -> dict[str, Any]:
    task, entry = get_writing_score_task_and_entry(task_id)
    if task.is_terminal:
        return entry_payload(entry)
    if not score_task_matches_current_entry(task, entry):
        try:
            succeed_billable_ai_task(
                task.task_id,
                {"entry_id": entry.entry_id, "stale_result": True},
                payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
                provider=provider or None,
                model=model or None,
            )
        except AIOrchestrationError as exc:
            raise WritingError(str(exc)) from exc
        entry.refresh_from_db()
        return entry_payload(entry)
    score = normalize_score_payload(entry, payload)
    # Freeze the actual scoring model into the immutable report snapshot. A
    # later rescore replaces this score wholesale, so old tasks can never
    # pollute the new report's provenance.
    score["scoring_provider"] = str(provider or "").strip()
    score["scoring_model"] = str(model or "").strip()
    persist_score(entry, score)
    score["writing_profile"] = update_profile(entry, score)
    try:
        succeed_billable_ai_task(
            task.task_id,
            {"entry_id": entry.entry_id, "score": score},
            payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
            provider=provider or None,
            model=model or None,
        )
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
    # Local fallback scoring has no AI model — record that honestly instead of
    # leaving any stale or default model name behind.
    score["scoring_provider"] = "fallback"
    score["scoring_model"] = ""
    persist_score(entry, score)
    score["writing_profile"] = update_profile(entry, score)
    try:
        fallback_billable_ai_task(task.task_id, reason or "AI scoring unavailable", {"entry_id": entry.entry_id, "score": score})
    except AIOrchestrationError as exc:
        raise WritingError(str(exc)) from exc
    entry.refresh_from_db()
    return entry_payload(entry)
