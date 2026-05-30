"""Validation and small text helpers for writing entries.

This module is intentionally free of persistence and AI-provider work. It is
the first production split from `services.py`: request/service orchestration can
import these helpers while views keep their existing `services` import surface.
"""

from __future__ import annotations

import re
from typing import Any

from .models import WritingEntry, WritingPrompt


WRITING_TASK_TYPES = {
    WritingPrompt.TaskType.TASK1_ACADEMIC,
    WritingPrompt.TaskType.TASK2,
}


class WritingError(ValueError):
    pass


class WritingEntryDeleted(WritingError):
    pass


def writing_entry_is_scored(entry: WritingEntry) -> bool:
    return entry.status == WritingEntry.Status.SCORED and getattr(entry, "score", None) is not None


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


def writing_paragraphs(answer: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n+", answer or "") if part.strip()]


def paragraph_guidance(task_type: str) -> dict[str, Any]:
    normalized = normalize_task_type(task_type)
    if normalized == WritingPrompt.TaskType.TASK1_ACADEMIC:
        return {
            "task_type": normalized,
            "title": "Task 1 需要先分段，再进行 AI 评分",
            "message": "你的作文现在还没有清楚分段。Task 1 评分会看信息组织和概述位置，所以请先把答案分成 3-4 段。",
            "tips": [
                "第 1 段：改写题目，说明图表、地图或流程图展示的内容。",
                "第 2 段：写 Overview，总结最明显的总体趋势或关键特征，不要堆细节。",
                "第 3-4 段：按类别、时间段或对比关系展开主要数据和细节。",
            ],
        }
    return {
        "task_type": normalized,
        "title": "Task 2 需要先分段，再进行 AI 评分",
        "message": "你的作文现在还没有清楚分段。Task 2 评分会看观点展开和段落组织，所以请先把答案分成清晰的 4 段左右。",
        "tips": [
            "第 1 段：引入题目，并给出你的立场或回应方向。",
            "第 2-3 段：每段只讲一个中心观点，用解释和例子展开。",
            "第 4 段：总结立场，不要加入新的大观点。",
        ],
    }


def validate_answer_paragraphs(task_type: str, answer: str) -> None:
    if len(writing_paragraphs(answer)) >= 2:
        return
    guidance = paragraph_guidance(task_type)
    error = WritingError(guidance["message"])
    error.payload = {"code": "paragraphs_required", "paragraph_guidance": guidance}
    raise error
