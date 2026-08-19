import hashlib
import re
import uuid
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import CustomWritingPrompt, WritingEntry, WritingPrompt
from .prompt_services import (
    WRITING_CATEGORY_LABELS,
    WRITING_TASK2_PROMPT_PATTERN_LABELS,
    WRITING_TASK_LABELS,
    task2_prompt_pattern,
)
from .validation import WritingError, normalize_task_type


MAX_CUSTOM_PROMPT_LENGTH = 20000


def normalize_custom_prompt_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def custom_prompt_content_hash(content: str) -> str:
    normalized = re.sub(r"\s+", " ", normalize_custom_prompt_text(content)).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def strip_custom_prompt_markdown(content: str) -> str:
    """Return visible text without mutating stored legacy Markdown."""
    text = normalize_custom_prompt_text(content)
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}(?:[-*+]\s+|\d+[.)]\s+)", "", text, flags=re.MULTILINE)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[`*_~]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def classify_custom_prompt(content: str, task_type: str) -> tuple[str, str]:
    if task_type != WritingPrompt.TaskType.TASK2:
        return "", "other"
    text = strip_custom_prompt_markdown(content).lower()
    pattern = task2_prompt_pattern(text)
    question_count = text.count("?")
    has_causes = bool(re.search(r"\b(?:cause|causes|reason|reasons|problem|problems)\b", text))
    has_solutions = bool(re.search(r"\b(?:solution|solutions|measure|measures|solve|solved)\b", text))
    has_effects = bool(re.search(r"\b(?:effect|effects|impact|impacts|affect)\b", text))
    if has_causes and has_solutions:
        category = "causes_solutions" if re.search(r"\b(?:cause|causes|reason|reasons)\b", text) else "problem_solution"
        pattern = "problem_solution"
    elif has_causes and has_effects:
        category = "causes_effects"
        pattern = "problem_solution"
    elif pattern == "discussion_opinion":
        category = "discussion"
    elif pattern in {"agree_to_what_extent", "positive_negative_do_you_think"}:
        category = "opinion"
    elif pattern == "advantages_outweigh":
        category = "advantages_disadvantages"
    elif question_count >= 2:
        category, pattern = "two_part", "two_question"
    elif pattern == "problem_solution":
        category = "problem_solution"
    else:
        category, pattern = "opinion", pattern or "other"
    return category, pattern


def generated_custom_prompt_title(task_type: str, category: str, *, created_at=None) -> str:
    local_time = (created_at or timezone.now()).astimezone(timezone.get_current_timezone())
    label = WRITING_CATEGORY_LABELS.get(category) or WRITING_TASK_LABELS.get(task_type, "Writing")
    return f"{local_time.date().isoformat()} · {label}"[:200]


def validated_custom_prompt_values(payload: dict[str, Any], *, existing=None):
    task_type = normalize_task_type(str(payload.get("task_type") or (existing.task_type if existing else "")))
    # New requests send the plain-text `prompt` field; `prompt_markdown` stays
    # accepted for legacy callers and old stored data. Both carry the same
    # user-authored text — custom prompts are plain text, never parsed as
    # Markdown.
    if "prompt" in payload:
        raw_content = payload.get("prompt")
    elif "prompt_markdown" in payload:
        raw_content = payload.get("prompt_markdown")
    else:
        raw_content = existing.prompt_markdown if existing else ""
    content = normalize_custom_prompt_text(raw_content)
    if not content:
        raise WritingError("prompt is required")
    if len(content) > MAX_CUSTOM_PROMPT_LENGTH:
        raise WritingError(f"prompt must be {MAX_CUSTOM_PROMPT_LENGTH} characters or fewer")
    raw_title = str(payload.get("title") or "").strip() if "title" in payload else ""
    if len(raw_title) > 200:
        raise WritingError("title must be 200 characters or fewer")
    category, pattern = classify_custom_prompt(content, task_type)
    if existing and "title" not in payload:
        title = existing.title
    elif existing:
        old_generated = generated_custom_prompt_title(existing.task_type, existing.category, created_at=existing.created_at)
        title = existing.title if raw_title == old_generated else (raw_title or existing.title)
    else:
        title = raw_title or generated_custom_prompt_title(task_type, category)
    return task_type, title, content, category, pattern


def custom_prompt_payload(prompt: CustomWritingPrompt, user=None) -> dict[str, Any]:
    category, pattern = classify_custom_prompt(prompt.prompt_markdown, prompt.task_type)
    category = prompt.category or category
    if category and not prompt.category:
        CustomWritingPrompt.objects.filter(pk=prompt.pk).update(category=category)
        prompt.category = category
    latest_entry = None
    if user is not None and getattr(user, "is_authenticated", False):
        latest_entry = (
            WritingEntry.objects.filter(user=user, custom_prompt=prompt)
            .select_related("score")
            .order_by("-updated_at", "-created_at")
            .first()
        )
    status = "unpracticed"
    if latest_entry and latest_entry.status == WritingEntry.Status.SCORED:
        status = "scored"
    elif latest_entry:
        status = "saved"
    return {
        "id": str(prompt.id),
        "custom_prompt_id": str(prompt.id),
        "prompt_id": "",
        "task_type": prompt.task_type,
        "task_label": WRITING_TASK_LABELS.get(prompt.task_type, "Writing"),
        "title": prompt.title,
        "category": category,
        "category_label": WRITING_CATEGORY_LABELS.get(category, "自定义"),
        "prompt": prompt.prompt_markdown,
        "prompt_markdown": prompt.prompt_markdown,
        "prompt_pattern": pattern,
        "prompt_pattern_label": WRITING_TASK2_PROMPT_PATTERN_LABELS.get(pattern, WRITING_TASK2_PROMPT_PATTERN_LABELS["other"]),
        "image_url": "",
        "source": "custom",
        "source_label": "自定义练习",
        "created_at": prompt.created_at.isoformat(),
        "updated_at": prompt.updated_at.isoformat(),
        "practice_status": status,
        "practice_status_label": {"unpracticed": "未练习", "saved": "已保存", "scored": "已评分"}[status],
    }


def list_custom_prompts(user, task_type: str | None = None) -> dict[str, Any]:
    rows = CustomWritingPrompt.objects.filter(user=user).order_by("-updated_at", "-created_at")
    if task_type:
        rows = rows.filter(task_type=normalize_task_type(task_type))
    return {"items": [custom_prompt_payload(row, user) for row in rows]}


@transaction.atomic
def create_custom_prompt(user, payload: dict[str, Any]) -> dict[str, Any]:
    task_type, title, content, category, _pattern = validated_custom_prompt_values(payload)
    content_hash = custom_prompt_content_hash(content)
    try:
        prompt = CustomWritingPrompt.objects.create(
            user=user,
            task_type=task_type,
            title=title,
            prompt_markdown=content,
            category=category,
            content_hash=content_hash,
        )
    except IntegrityError as exc:
        raise WritingError("Duplicate custom prompt") from exc
    return custom_prompt_payload(prompt, user)


def get_custom_prompt(user, prompt_id: str) -> CustomWritingPrompt:
    try:
        normalized_id = uuid.UUID(str(prompt_id or "").strip())
    except (ValueError, AttributeError):
        raise WritingError("Custom writing prompt not found")
    prompt = CustomWritingPrompt.objects.filter(user=user, id=normalized_id).first()
    if not prompt:
        raise WritingError("Custom writing prompt not found")
    return prompt


@transaction.atomic
def update_custom_prompt(user, prompt_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    prompt = get_custom_prompt(user, prompt_id)
    task_type, title, content, category, _pattern = validated_custom_prompt_values(payload, existing=prompt)
    content_hash = custom_prompt_content_hash(content)
    duplicate = CustomWritingPrompt.objects.filter(
        user=user, task_type=task_type, content_hash=content_hash
    ).exclude(pk=prompt.pk).exists()
    if duplicate:
        raise WritingError("Duplicate custom prompt")
    prompt.task_type = task_type
    prompt.title = title
    prompt.prompt_markdown = content
    prompt.category = category
    prompt.content_hash = content_hash
    prompt.save(update_fields=["task_type", "title", "prompt_markdown", "category", "content_hash", "updated_at"])
    return custom_prompt_payload(prompt, user)


@transaction.atomic
def delete_custom_prompt(user, prompt_id: str) -> dict[str, Any]:
    prompt = get_custom_prompt(user, prompt_id)
    prompt.delete()
    return {"ok": True, "id": str(prompt_id)}
