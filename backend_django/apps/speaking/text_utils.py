"""Text cleanup helpers for speaking reports and AI feedback.

These helpers are pure string transformations. Keeping them outside
`services.py` makes the speaking service facade smaller without changing the
existing import surface for views/tests.
"""

from __future__ import annotations

import json
import re
from typing import Any


def _repair_unescaped_string_quotes(text: str) -> str:
    """Escape stray double-quotes that appear *inside* JSON string values.

    LLMs frequently quote an inline example inside a string (e.g. the coaching
    text `说完"看视频"和...`) and forget to escape the inner quotes, producing
    output json.loads rejects. We walk the text tracking string state: a quote
    inside a string that is not immediately followed (ignoring whitespace) by a
    structural delimiter (`:` `,` `}` `]`) is a literal quote, so we escape it.
    Already-escaped quotes (`\\"`) and structural quotes are left untouched, so a
    well-formed object is returned unchanged.
    """
    out: list[str] = []
    in_str = False
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        if not in_str:
            out.append(char)
            if char == '"':
                in_str = True
            i += 1
            continue
        if char == "\\":
            out.append(char)
            if i + 1 < n:
                out.append(text[i + 1])
                i += 2
            else:
                i += 1
            continue
        if char == '"':
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            nxt = text[j] if j < n else ""
            if nxt in ":,}]" or nxt == "":
                out.append('"')
                in_str = False
            else:
                out.append('\\"')
            i += 1
            continue
        out.append(char)
        i += 1
    return "".join(out)


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract first valid JSON object from text using balanced bracket scanning.

    Handles cases where:
    - Text contains multiple JSON objects
    - Text has Trellis/other content before/after JSON
    - JSON spans multiple lines
    - String values contain unescaped inline double-quotes (auto-repaired)

    Returns the first complete, parseable JSON object.
    """
    text = str(text or "")
    try:
        return _extract_json_object_scan(text)
    except ValueError:
        repaired = _repair_unescaped_string_quotes(text)
        if repaired != text:
            return _extract_json_object_scan(repaired)
        raise


def _extract_json_object_scan(text: str) -> dict[str, Any]:
    text = str(text or "")

    # Find the first '{' that starts a JSON object
    start = text.find("{")
    if start == -1:
        raise ValueError("model output did not contain a JSON object")

    # Use balanced bracket scanning to find the matching '}'
    depth = 0
    in_string = False
    escape_next = False

    for i, char in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                # Found the closing brace
                json_str = text[start:i + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    # Try finding next JSON object
                    remaining = text[i + 1:]
                    if "{" in remaining:
                        return extract_json_object(remaining)
                    raise ValueError(f"Invalid JSON object: {json_str[:100]}...")

    raise ValueError("model output contained unbalanced JSON braces")


def extract_json_object_with_keys(text: str, required_keys: set[str]) -> dict[str, Any]:
    """Extract the first JSON object containing all required top-level keys."""
    remaining = str(text or "")
    last_error: Exception | None = None
    while "{" in remaining:
        try:
            payload = extract_json_object(remaining)
        except ValueError as exc:
            last_error = exc
            break
        if required_keys.issubset(set(payload.keys())):
            return payload
        start = remaining.find("{")
        if start == -1:
            break
        depth = 0
        in_string = False
        escape_next = False
        end = -1
        for index, char in enumerate(remaining[start:], start):
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        if end == -1:
            break
        remaining = remaining[end + 1:]
    keys = ", ".join(sorted(required_keys))
    raise ValueError(f"model output did not contain a JSON object with required keys: {keys}") from last_error


def extract_codex_json_events(stdout: str) -> tuple[str, dict[str, Any] | None, bool]:
    """Parse codex CLI JSON events from stdout.

    Extracts the final model output text from:
    1. agent_message events (item.completed with type=agent_message)
    2. message.item events with text content
    3. Raw text events

    Skips Trellis injection text and other non-JSON prefixes.

    Returns:
        tuple of (text, usage, has_real_content)
        - text: extracted model output
        - usage: token usage dict or None
        - has_real_content: True if we found actual agent_message content,
          False if only event stream without model output
    """
    events: list[dict[str, Any]] = []
    for line in str(stdout or "").splitlines():
        stripped = line.strip()
        if not stripped or not stripped.startswith("{"):
            continue
        try:
            event = json.loads(stripped)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)

    usage = None
    final_text = ""
    has_real_content = False

    for event in events:
        # Track usage
        event_usage = event.get("usage")
        if isinstance(event_usage, dict):
            usage = event_usage
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]

        # Extract text from various event formats
        # Format 1: item.completed with agent_message (preferred)
        if event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                content_list = item.get("content", [])
                for content_item in content_list:
                    if isinstance(content_item, dict) and content_item.get("type") == "text":
                        text_value = content_item.get("text", "")
                        if text_value:
                            final_text = text_value
                            has_real_content = True

        # Format 2: message/item/response dict
        message = event.get("message") or event.get("item") or event.get("response")
        if isinstance(message, dict):
            content = message.get("content") or message.get("text")
            if isinstance(content, str) and content.strip():
                final_text = content
                has_real_content = True
            elif isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        value = part.get("text") or part.get("content")
                        if isinstance(value, str):
                            parts.append(value)
                    elif isinstance(part, str):
                        parts.append(part)
                if parts:
                    final_text = "\n".join(parts)
                    has_real_content = True

        # Format 3: direct content field
        elif isinstance(event.get("content"), str) and event["content"].strip():
            final_text = event["content"]
            has_real_content = True

    if not events:
        return str(stdout or ""), None, False
    return final_text or str(stdout or ""), usage, has_real_content


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


def _clean_report_text(text: str) -> str:
    """Strip non-printable characters while preserving newlines and tabs.

    Distinct from ``clean_report_text``: this is the lighter filter used on raw
    candidate transcripts, where line structure must survive.
    """
    return "".join(c for c in text if c.isprintable() or c in "\n\t").strip()
