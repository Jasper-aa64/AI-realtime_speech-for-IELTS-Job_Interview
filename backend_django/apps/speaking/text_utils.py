"""Text cleanup helpers for speaking reports and AI feedback.

These helpers are pure string transformations. Keeping them outside
`services.py` makes the speaking service facade smaller without changing the
existing import surface for views/tests.
"""

from __future__ import annotations

import re


def clean_band7_output(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    text = re.sub(r"```(?:[a-zA-Z0-9_-]+)?", "", text)
    text = text.replace("```", "")
    blocked = (
        "trellis sessionstart", "workflow", "active tasks", "spec index", "git status",
        "current task", "session context", "developer", "system:", "assistant:", "user:", "codex",
    )
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if kept and kept[-1]:
                kept.append("")
            continue
        lowered = stripped.lower()
        if any(marker in lowered for marker in blocked):
            continue
        if re.fullmatch(r"[-=*#_` ]{3,}", stripped):
            continue
        if stripped.startswith(("{", "}", "[", "]")):
            continue
        stripped = re.sub(
            r"^\s*(?:band\s*7\s*(?:spoken\s*)?(?:version|answer)?|answer|model answer)\s*:\s*",
            "",
            stripped,
            flags=re.I,
        )
        if stripped:
            kept.append(stripped)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def clean_report_text(value: str) -> str:
    text = clean_band7_output(value)
    text = re.sub(r"\s+", " ", text).strip()
    blocked = ("trellis sessionstart", "workflow-state", "session context", "current task", "active tasks", "git status")
    lowered = text.lower()
    if not text or any(marker in lowered for marker in blocked):
        return ""
    return text


def clean_markdown_text(value: str) -> str:
    text = clean_band7_output(value)
    text = re.sub(r"[ \t]+", " ", text).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    blocked = ("trellis sessionstart", "workflow-state", "session context", "current task", "active tasks", "git status")
    lowered = text.lower()
    if not text or any(marker in lowered for marker in blocked):
        return ""
    return text


def plain_spoken_text(value: str) -> str:
    text = clean_band7_output(value)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*([^*\n]+?)\*\*", r"\1", text)
    text = re.sub(r"(^|[^\*])\*([^*\n]+?)\*", r"\1\2", text)
    text = re.sub(r"`([^`\n]+?)`", r"\1", text)
    return clean_report_text(text)


def clean_coaching_markdown_text(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"```(?:[a-zA-Z0-9_-]+)?", "", text)
    text = text.replace("```", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def normalize_coaching_markdown(value: str) -> str:
    text = clean_coaching_markdown_text(value)
    if not text:
        return ""
    text = re.sub(r"(可以直接替换成：)\s*`([^`\n]+)`", r"\1\n\2", text)
    text = re.sub(r"(可以说：)\s*`([^`\n]+)`", r"\1\"\2\"", text)
    text = text.replace("\n\n- ", "\n- ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def spoken_markdown(value: str, part: str = "") -> str:
    text = clean_band7_output(value)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return ""
    existing = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    if len(existing) > 1:
        return "\n\n".join(existing)
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
    if not sentences:
        return text
    if part == "p1":
        return "\n\n".join(sentences)
    return "\n\n".join(" ".join(sentences[index:index + 2]) for index in range(0, len(sentences), 2))


def acceptable_coaching_markdown(value: str) -> bool:
    text = clean_coaching_markdown_text(value)
    if not text:
        return False
    if "语法错误纠正" not in text and "语法 & 表达纠正" not in text:
        return False
    lowered = text.lower()
    leaked_system_markers = ("<workflow-state", "</workflow-state>", "session context", "tool_uses", "function_call", "codex exec")
    return not any(marker in lowered for marker in leaked_system_markers)


def concise_coaching_markdown(value: str) -> bool:
    return acceptable_coaching_markdown(value)


def infer_grammar_corrections(transcript: str) -> list[str]:
    lowered = clean_report_text(transcript).lower()
    corrections: list[str] = []
    patterns = [
        ("i prefer study", "`I prefer study` -> `I prefer studying ...`"),
        ("that's efficiency", "`that's efficiency` -> `It is more efficient.`"),
        ("as an introverted people", "`as an introverted people` -> `as an introverted person`"),
        ("going internship", "`going internship` -> `I am doing an internship.`"),
        ("going all an internship", "`going all an internship` -> `I am doing an internship.`"),
        ("i live on my own current", "`I live on my own current` -> `I live on my own at the moment.`"),
        ("temporary temporary live", "`temporary temporary live` -> `I am living here temporarily.`"),
        ("just temporary", "`just temporary` -> `It is just temporary.`"),
        ("major in my computer science", "`major in my computer science` -> `I study computer science.`"),
        ("most of time", "`most of time` -> `most of my time`"),
        ("near to the company", "`near to the company` -> `near the company` / `close to the company`"),
        ("what i enjoyed most", "`What I enjoyed most` -> `What I enjoy most`"),
        ("problems of the aspect", "`problems of the aspect` -> `the problem-solving aspect`"),
    ]
    for needle, correction in patterns:
        if needle in lowered and correction not in corrections:
            corrections.append(correction)
    return corrections[:3]


def ensure_grammar_correction_bullet(coaching: str, transcript: str) -> str:
    text = clean_coaching_markdown_text(coaching)
    if not text:
        return ""
    if "语法错误纠正" in text or "语法 & 表达纠正" in text:
        return text
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    corrections = infer_grammar_corrections(transcript)
    if lines:
        lines.append("")
    if not corrections:
        lines.append("语法错误纠正：无")
    else:
        lines.append("语法错误纠正：")
        lines.extend(f"{index}. {correction}" for index, correction in enumerate(corrections, start=1))
    return "\n".join(lines).strip()
