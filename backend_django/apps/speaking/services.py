from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count, Max, Min, Sum
from django.utils import timezone

from .models import SpeakingAttempt, SpeakingReport, SpeakingTrainingObservation, SpeakingTurn


# --- Codex Integration ---

CODEX_REASONING_EFFORT = "low"


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract first JSON object from text."""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("model output did not contain a JSON object")
    return json.loads(match.group(0))


def extract_codex_json_events(stdout: str) -> tuple[str, dict[str, Any] | None]:
    """Parse codex CLI JSON events from stdout."""
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
    for event in events:
        event_usage = event.get("usage")
        if isinstance(event_usage, dict):
            usage = event_usage
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]
        message = event.get("message") or event.get("item") or event.get("response")
        if isinstance(message, dict):
            content = message.get("content") or message.get("text")
            if isinstance(content, str):
                final_text = content
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
        elif isinstance(event.get("content"), str):
            final_text = event["content"]

    if not events:
        return str(stdout or ""), None
    return final_text or str(stdout or ""), usage


def run_codex(prompt: str, call_id: str) -> tuple[str, dict[str, Any] | None]:
    """Call codex CLI and return output and usage.

    The `-` argument is required to make codex exec read from stdin.
    Without it, the model receives 0 tokens and outputs only thread/turn events.
    """
    if os.environ.get("IELTS_WEB_DISABLE_CODEX") == "1":
        raise RuntimeError("codex disabled by IELTS_WEB_DISABLE_CODEX=1")

    codex = shutil.which("codex") or "/opt/homebrew/bin/codex"
    if not shutil.which(codex) and not Path(codex).exists():
        raise RuntimeError("codex CLI not found")

    config_args = ["-c", f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"']
    try:
        result = subprocess.run(
            [codex, "exec", "--json", *config_args, "-"],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=45,
            check=True,
        )
        output, usage = extract_codex_json_events(result.stdout)
    except Exception:
        result = subprocess.run(
            [codex, "exec", *config_args, "-"],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=45,
            check=True,
        )
        output, usage = result.stdout, None

    return output, usage


def clamp_band(value: float | int | None) -> float:
    """Clamp band score to 0.0-9.0 in 0.5 increments."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(0.0, min(9.0, round(numeric * 2.0) / 2.0))


def rounded_overall(scores: dict[str, float | None]) -> float:
    """Calculate overall band from component scores."""
    values = [
        scores.get("fluency_coherence"),
        scores.get("lexical_resource"),
        scores.get("grammatical_range"),
    ]
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric:
        return 0.0
    average = sum(numeric) / len(numeric)
    return clamp_band(math.floor(average * 2.0 + 0.5) / 2.0)


def clean_band7_output(value: str) -> str:
    """Clean Band 7 model answer output."""
    text = str(value or "").replace("\r\n", "\n").strip()
    text = re.sub(r"```(?:[a-zA-Z0-9_-]+)?", "", text)
    text = text.replace("```", "")

    blocked = (
        "trellis sessionstart",
        "workflow",
        "active tasks",
        "spec index",
        "git status",
        "current task",
        "session context",
        "developer",
        "system:",
        "assistant:",
        "user:",
        "codex",
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


def plausible_spoken_answer(value: str) -> bool:
    """Check if Band 7 output looks like a real spoken answer."""
    text = clean_band7_output(value)
    words = re.findall(r"[A-Za-z']+", text)
    if len(words) < 12:
        return False
    lowered = text.lower()
    bad_markers = ("json", "requirements", "acceptance criteria", "here is", "i cannot", "as an ai")
    return not any(marker in lowered[:220] for marker in bad_markers)


def generic_band7_answer(value: str) -> bool:
    """Check if Band 7 output is generic template text."""
    lowered = clean_band7_output(value).lower()
    generic_markers = (
        "quite easy for me to answer",
        "connects with my daily life",
        "give one simple detail",
        "closer to a band",
        "i can talk about from my own experience",
        "this topic is very important",
        "i would answer it directly first",
        "i would answer this directly from my own experience",
        "i would answer this by keeping the main idea",
        "my favourite choice is the one connected with my own routine",
        "a complete transcript was not captured",
        "add one simple reason and a small detail",
        "that gives me a clear reason to support my answer",
        "then i would develop it with one concrete situation",
        "explain why it mattered, and finish with the result",
    )
    return any(marker in lowered for marker in generic_markers)


def band7_addresses_question(question: str, answer: str, part: str) -> bool:
    """Check if Band 7 answer actually addresses the question."""
    if part != "p1":
        return True

    # Use existing relevance check
    relevance = _training_relevance(question, answer)
    if relevance >= Decimal("0.20"):
        return True

    lowered_question = question.lower()
    lowered_answer = answer.lower()

    if "tell me a little more" in lowered_question or "what you do now" in lowered_question:
        work_study_terms = (
            "student", "study", "studying", "university", "school", "major",
            "work", "working", "job", "internship", "engineer", "software",
            "developer", "company", "project",
        )
        return any(term in lowered_answer for term in work_study_terms)

    if lowered_question.startswith(("do you", "are you", "is there", "can you", "have you")):
        return any(
            marker in lowered_answer
            for marker in ("yes", "no", "i do", "i don't", "i am", "i'm", "not really", "sometimes")
        )

    return False


def valid_turn_band7(question: str, answer: str, part: str) -> bool:
    """Validate that Band 7 answer is plausible, not generic, and addresses question."""
    return (
        plausible_spoken_answer(answer)
        and not generic_band7_answer(answer)
        and band7_addresses_question(question, answer, part)
    )


# --- Text Processing Helpers ---


def clean_report_text(value: str) -> str:
    """Clean text for display in reports."""
    text = clean_band7_output(value)
    text = re.sub(r"\s+", " ", text).strip()
    blocked = (
        "trellis sessionstart",
        "workflow-state",
        "session context",
        "current task",
        "active tasks",
        "git status",
    )
    lowered = text.lower()
    if not text or any(marker in lowered for marker in blocked):
        return ""
    return text


def clean_markdown_text(value: str) -> str:
    """Clean and normalize markdown text."""
    text = clean_band7_output(value)
    text = re.sub(r"[ \t]+", " ", text).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    blocked = (
        "trellis sessionstart",
        "workflow-state",
        "session context",
        "current task",
        "active tasks",
        "git status",
    )
    lowered = text.lower()
    if not text or any(marker in lowered for marker in blocked):
        return ""
    return text


def normalize_coaching_markdown(value: str) -> str:
    """Normalize coaching markdown format."""
    text = clean_markdown_text(value)
    if not text:
        return ""
    text = re.sub(r"(可以直接替换成：)\s*`([^`\n]+)`", r"\1\n\2", text)
    text = re.sub(r"(可以说：)\s*`([^`\n]+)`", r"\1\"\2\"", text)
    text = text.replace("\n\n- ", "\n- ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def spoken_markdown(value: str, part: str = "") -> str:
    """Format spoken text with paragraph breaks."""
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
    paragraphs = [" ".join(sentences[index:index + 2]) for index in range(0, len(sentences), 2)]
    return "\n\n".join(paragraphs)


def concise_coaching_markdown(value: str) -> bool:
    """Validate coaching markdown has proper format with grammar correction bullet."""
    text = clean_markdown_text(value)
    if not text:
        return False
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) > 12:
        return False
    has_markdown_point = any(line.lstrip().startswith(("- ", "* ")) for line in lines)
    grammar_index = next((index for index, line in enumerate(lines) if "语法错误纠正" in line), None)
    if grammar_index is None:
        return False
    top_level_lines = [line for line in lines if not re.match(r"^\s{2,}\d+\.\s+", line)]
    grammar_line = lines[grammar_index].strip()
    if top_level_lines and "语法错误纠正" not in top_level_lines[-1]:
        return False
    has_valid_grammar_detail = "无" in grammar_line or any(
        re.match(r"^\s{2,}\d+\.\s+", line) for line in lines[grammar_index + 1:]
    )
    return has_markdown_point and has_valid_grammar_detail and len(text) <= 1100


def infer_grammar_corrections(transcript: str) -> list[str]:
    """Infer grammar corrections from transcript based on common patterns."""
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
    """Ensure coaching ends with a grammar correction bullet."""
    text = clean_markdown_text(coaching)
    if not text:
        return ""
    lines: list[str] = []
    skip_grammar_items = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if "语法错误纠正" in stripped:
            skip_grammar_items = True
            continue
        if skip_grammar_items and re.match(r"^\d+\.\s+", stripped):
            continue
        skip_grammar_items = False
        if re.match(r"^\d+\.\s+`.+?`\s*->", stripped):
            continue
        lines.append(line)
    corrections = infer_grammar_corrections(transcript)
    if not corrections:
        lines.append("- 语法错误纠正：无")
    else:
        lines.append("- 语法错误纠正：")
        lines.extend(f"  {index}. {correction}" for index, correction in enumerate(corrections, start=1))
    return "\n".join(lines).strip()


# --- Model Answer Helpers ---


def model_answer_constraints(part: str) -> str:
    """Get part-specific constraints for Band 7 model answer."""
    if part == "p1":
        return (
            "This is IELTS Speaking Part 1. Write a short natural answer, normally 1-3 sentences, maximum 3 sentences. "
            "Do not turn it into a long Part 2-style speech. One concise Markdown paragraph is preferred."
        )
    if part == "p2":
        return (
            "This is IELTS Speaking Part 2. Write a natural long-turn answer in Markdown paragraphs. "
            "Cover the cue-card points without copying the bullet list."
        )
    if part == "p3":
        return (
            "This is IELTS Speaking Part 3. Write a developed discussion answer, about 4-6 sentences, "
            "with an opinion, reasoning, and one concrete example or contrast."
        )
    return "Write an answer appropriate to the IELTS Speaking part shown by the questions."


def target_band_label(attempt: SpeakingAttempt | dict[str, Any]) -> str:
    """Get target band label from attempt."""
    if isinstance(attempt, SpeakingAttempt):
        metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
        value = metadata.get("target_band", 7.0)
    else:
        value = attempt.get("target_band", 7.0)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 7.0
    numeric = max(5.0, min(9.0, round(numeric * 2) / 2))
    return str(int(numeric)) if numeric.is_integer() else f"{numeric:.1f}"


def _transcript_usable_for_band7(question: str, transcript: str) -> bool:
    """Check if a transcript is coherent enough to quote in a Band 7 model answer."""
    if not transcript or len(transcript.split()) < 4:
        return False
    relevance = _training_relevance(question, transcript)
    if relevance >= Decimal("0.25"):
        return True
    words = re.findall(r"[A-Za-z']+", transcript)
    if len(words) < 5:
        return False
    common_english = {
        "i", "my", "me", "we", "the", "a", "an", "is", "am", "are", "was", "were",
        "it", "its", "this", "that", "and", "but", "or", "so", "because", "if",
        "to", "for", "of", "in", "on", "at", "with", "from", "by", "not", "no",
        "yes", "do", "don't", "have", "has", "had", "can", "will", "would", "could",
        "think", "like", "want", "know", "go", "get", "make", "see", "say", "tell",
        "very", "really", "just", "also", "still", "already", "always", "never",
    }
    uncommon = [word for word in words if word.lower() not in common_english]
    if len(uncommon) < 3:
        return False
    filler_ratio = sum(1 for word in words if word.lower() in {"um", "uh", "er", "mm"}) / max(1, len(words))
    return filler_ratio < 0.15


# --- Coaching Helpers ---


def _coaching_reason_for_question(question_lower: str, part: str, transcript_words: int, transcript_usable: bool, tags: list[str]) -> str:
    """Get coaching reason based on question type."""
    if not transcript_usable:
        if "name" in question_lower:
            return "名字部分转写不清楚，先确保发音清晰、语速适中。"
        if "work" in question_lower or "study" in question_lower:
            return "这题需要直接说明身份（学生/工作），再加一个原因。"
        if any(w in question_lower for w in ("live", "living", "neighbourhood", "neighbor")):
            return "住所类问题先说地点，再加一个你喜欢/不喜欢的原因。"
        if any(w in question_lower for w in ("favourite", "favorite", "enjoy", "like most")):
            return "喜好类问题先说选择，再说为什么喜欢。"
        if any(w in question_lower for w in ("think", "opinion", "important")):
            return "观点类问题先表态（yes/no/depends），再给一个理由。"
        if "easy" in question_lower or "difficult" in question_lower:
            return "难易类问题先说你的感受，再解释为什么。"
        return "转写不太清楚，先把答案说完整、说慢一点，确保每个词都能被识别。"
    if transcript_words < 15:
        return "回答太短了，Part 1 至少需要 2-3 句话。"
    if transcript_words < 35:
        return "回答偏短，试着加一个原因或一个小细节。"
    if "template_language" in tags:
        return "模板感比较明显，试着用自己的真实经历来回答。"
    return "回答已经成形，可以把表达再自然一些。"


def _coaching_next_action(question_lower: str, part: str, transcript_usable: bool, tags: list[str]) -> str:
    """Get next action suggestion for coaching."""
    if not transcript_usable:
        return "下一次练这题时，先把 Band 7 版本读出声 3 遍，熟悉句型后再脱稿说。"
    if "short_answer" in tags or "limited_development" in tags:
        return "下一次先用 20 秒把答案补完整，确保有直接回答 + 原因 + 细节。"
    if "template_language" in tags:
        return "下一次试着把模板词换成自己的说法，先说一遍再录音对比。"
    if "off_topic" in tags:
        return "下一次开口前，先复述题目关键词，确认回答方向是对的。"
    return "下一题试着把语速放慢，让每句话都说完整。"


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
    defaults = {"prep_seconds": 3, "speak_seconds": 60}
    if part == "p1":
        return {"prep_seconds": 3, "speak_seconds": 35}
    if part == "p2":
        return {"prep_seconds": 60, "speak_seconds": 120}
    if part == "p3":
        return {"prep_seconds": 7, "speak_seconds": 75}
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

    # Generate examiner TTS for all turns
    for turn_data in turns:
        ensure_examiner_tts(attempt_id, turn_data)

    # Update database with generated TTS
    for turn_data in turns:
        db_turn = SpeakingTurn.objects.get(attempt=attempt, turn_id=turn_data["id"])
        turn_metadata = db_turn.metadata if isinstance(db_turn.metadata, dict) else {}
        turn_metadata["examiner_tts"] = turn_data.get("examiner_tts")
        db_turn.metadata = turn_metadata
        db_turn.save()

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


# --- Runtime completion and scoring ---

def _turn_status(turn: SpeakingTurn) -> str:
    status = str(turn.metadata.get("status") or "").strip()
    if status:
        return status
    if turn.transcript_cleaned or turn.transcript_raw:
        return "completed"
    if turn.audio_path:
        return "audio_uploaded"
    return "pending"


def _spoken_markdown(text: str) -> str:
    cleaned = _clean_report_text(text)
    return cleaned


def _turn_payload(turn: SpeakingTurn, total: int | None = None) -> dict[str, Any]:
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    prompt = metadata.get("prompt") if isinstance(metadata.get("prompt"), dict) else {"question": turn.question}
    cue_card = metadata.get("cue_card") if isinstance(metadata.get("cue_card"), dict) else None
    timers = metadata.get("timers") if isinstance(metadata.get("timers"), dict) else _timers_for_part(turn.part)
    audio = None
    if turn.audio_path:
        audio = {
            "path": str(Path(settings.MEDIA_ROOT) / turn.audio_path),
            "content_type": metadata.get("audio_content_type", "application/octet-stream"),
            "bytes": metadata.get("audio_bytes"),
            "duration_seconds": float(turn.duration_seconds) if turn.duration_seconds is not None else None,
            "url": f"/api/audio/{turn.attempt.attempt_id}/{turn.turn_id}/candidate",
        }
    return {
        "id": turn.turn_id,
        "part": turn.part,
        "index": max(0, int(turn.sequence or 0)),
        "total": total if total is not None else turn.attempt.turns.count(),
        "status": _turn_status(turn),
        "question": turn.question,
        "prompt": prompt,
        "cue_card": cue_card,
        "timers": timers,
        "examiner_text": metadata.get("examiner_text") or turn.question,
        "examiner_behavior": metadata.get("examiner_behavior") or "auto_play_question",
        "examiner_tts": metadata.get("examiner_tts") or {"provider": "volcengine", "status": "pending", "audio_url": None},
        "audio": audio,
        "transcript_raw": turn.transcript_raw,
        "transcript_cleaned": turn.transcript_cleaned,
        "transcript_markdown": metadata.get("transcript_markdown") or _spoken_markdown(turn.transcript_cleaned or turn.transcript_raw),
        "transcript_status": metadata.get("transcript_status") or ("captured" if (turn.transcript_cleaned or turn.transcript_raw) else "missing"),
        "duration_seconds": float(turn.duration_seconds) if turn.duration_seconds is not None else None,
        "band7_version": metadata.get("band7_version", ""),
        "band7_markdown": metadata.get("band7_markdown", metadata.get("band7_version", "")),
        "model_audio": metadata.get("model_audio"),
        "upgrade_notes": metadata.get("upgrade_notes", []),
        "ai_coaching": metadata.get("ai_coaching", ""),
        "counts_toward_total": turn.counts_toward_total,
        "display_index": metadata.get("display_index"),
    }


def _runtime_attempt_payload(attempt: SpeakingAttempt) -> dict[str, Any]:
    turns = list(attempt.turns.all().order_by("sequence"))
    total = len(turns)
    turn_payloads = [_turn_payload(turn, total) for turn in turns]
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    current_turn = metadata.get("current_turn")
    if attempt.status == SpeakingAttempt.Status.STARTED and not current_turn:
        next_turn = next((turn for turn in turn_payloads if turn.get("status") != "completed"), None)
        current_turn = next_turn.get("id") if next_turn else None
    return {
        "id": attempt.attempt_id,
        "timestamp": attempt.created_at.isoformat(),
        "status": attempt.status,
        "user_id": str(attempt.user_id),
        "mode": attempt.mode,
        "part": attempt.part,
        "title": attempt.title,
        "question": turn_payloads[0]["question"] if turn_payloads else "",
        "cue_card": metadata.get("cue_card"),
        "turns": turn_payloads,
        "current_turn": current_turn,
        "candidate": attempt.english_name,
        "full_name": attempt.full_name,
        "english_name": attempt.english_name,
        "pronunciation": {"provider": "azure", "status": "pending"},
        "ielts_score": None,
        "feedback_summary": "",
        "criteria_feedback": {},
        "band7_version": "",
        "model_audio": None,
        "upgrade_notes": [],
        "ai_coaching": "",
        **{key: value for key, value in metadata.items() if key.startswith("p3_")},
    }


def _load_attempt_for_user(user, attempt_id: str) -> SpeakingAttempt:
    attempt = (
        SpeakingAttempt.objects.filter(user=user, attempt_id=str(attempt_id or "").strip())
        .prefetch_related("turns")
        .first()
    )
    if not attempt:
        raise SpeakingError("Attempt not found")
    return attempt


def _find_turn(attempt: SpeakingAttempt, turn_id: str) -> SpeakingTurn:
    turn = next((item for item in attempt.turns.all() if item.turn_id == str(turn_id or "").strip()), None)
    if not turn:
        raise SpeakingError("Turn not found")
    return turn


def complete_turn(user, attempt_id: str, turn_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    attempt = _load_attempt_for_user(user, attempt_id)
    if attempt.status == SpeakingAttempt.Status.ABORTED:
        raise SpeakingError("Aborted attempts cannot be completed.")
    if attempt.status == SpeakingAttempt.Status.SCORED:
        raise SpeakingError("Scored attempts cannot be completed.")
    turn = _find_turn(attempt, turn_id)

    transcript = str(payload.get("transcript_raw") or payload.get("transcript") or "").strip()
    transcript_status = str(payload.get("transcript_status") or ("captured" if transcript else "missing")).strip()
    if transcript_status not in {"captured", "interim_fallback", "missing"}:
        transcript_status = "captured" if transcript else "missing"
    source = str(payload.get("transcript_source") or "browser_dictation").strip() or "browser_dictation"
    cleaned = _clean_report_text(transcript)
    duration = payload.get("duration_seconds")

    turn.transcript_raw = transcript
    turn.transcript_cleaned = cleaned
    turn.transcript_source = source
    if duration not in (None, ""):
        try:
            turn.duration_seconds = Decimal(str(duration))
        except Exception:
            turn.duration_seconds = None
    turn.pronunciation = turn.pronunciation or {
        "provider": "azure",
        "status": "fallback_browser_dictation" if transcript else "missing_audio",
        "pron_score": None,
        "accuracy": None,
        "fluency": None,
        "prosody": None,
        "issues": [],
        "message": "Pronunciation is not assessed by Django fallback turn completion.",
    }
    turn.metadata = {
        **(turn.metadata if isinstance(turn.metadata, dict) else {}),
        "status": "completed",
        "transcript_status": transcript_status,
        "transcript_markdown": _spoken_markdown(cleaned),
        "cleaning_notes": [],
        "feedback_generation_status": "fallback",
    }
    turn.save()

    turns = list(attempt.turns.all().order_by("sequence"))
    next_turn = next((item for item in turns if item.sequence > turn.sequence and _turn_status(item) != "completed"), None)
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    metadata["current_turn"] = next_turn.turn_id if next_turn else None
    attempt.metadata = metadata
    if next_turn is None:
        attempt.status = SpeakingAttempt.Status.READY_TO_SCORE
    attempt.save()
    attempt.refresh_from_db()

    return {
        "attempt": _runtime_attempt_payload(attempt),
        "turn": _turn_payload(turn, len(turns)),
        "next_turn": _turn_payload(next_turn, len(turns)) if next_turn else None,
    }


def abort_attempt(user, attempt_id: str) -> dict[str, Any]:
    attempt = _load_attempt_for_user(user, attempt_id)
    if attempt.status == SpeakingAttempt.Status.SCORED:
        raise SpeakingError("Scored attempts cannot be aborted.")
    if attempt.status != SpeakingAttempt.Status.ABORTED:
        metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
        metadata["aborted_at"] = timezone.now().isoformat()
        metadata["current_turn"] = None
        attempt.metadata = metadata
        attempt.status = SpeakingAttempt.Status.ABORTED
        attempt.save()
    return _runtime_attempt_payload(attempt)


def _word_count(text: str) -> int:
    return len([word for word in text.replace("\n", " ").split(" ") if word.strip()])


def score_with_codex(transcript: str, question: str, part: str, call_id: str) -> dict[str, Any]:
    """Score transcript using Codex CLI."""
    data_dir = Path(settings.BASE_DIR).parent / "data" / "ielts"
    prompt_path = data_dir / "prompts" / "scorer_system.md"

    if prompt_path.exists():
        system_prompt = prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = (
            "You are an IELTS Speaking examiner. Score the transcript using the official IELTS band descriptors. "
            "Consider fluency and coherence, lexical resource, and grammatical range and accuracy."
        )

    part_guidance = ""
    if part == "p1":
        part_guidance = "\n\nThis is Part 1. Answers should be direct and concise, typically 1-3 sentences."
    elif part == "p2":
        part_guidance = "\n\nThis is Part 2. The candidate should speak for 1-2 minutes covering the cue card points."
    elif part == "p3":
        part_guidance = "\n\nThis is Part 3. Answers should be developed with reasoning and examples, about 4-6 sentences."

    prompt = (
        system_prompt
        + "\n\nReturn JSON only with numeric keys fluency_coherence, lexical_resource, "
        "grammatical_range, overall_band, string key feedback, and optional overall_review object "
        "with string key comment and array key review_points. Do not score pronunciation or reference pronunciation."
        + part_guidance
        + "\n\nPrompt(s):\n"
        + (question.strip() or "(not provided)")
        + "\n\nTranscript:\n"
        + transcript
        + "\n"
    )

    output, usage = run_codex(prompt, call_id)
    payload = extract_json_object(output)

    scores: dict[str, Any] = {
        "fluency_coherence": clamp_band(payload.get("fluency_coherence")),
        "lexical_resource": clamp_band(payload.get("lexical_resource")),
        "grammatical_range": clamp_band(payload.get("grammatical_range")),
    }
    scores["overall_band"] = rounded_overall(scores)

    result_payload = {
        **scores,
        "feedback": str(payload.get("feedback", "")),
        "backend": "codex",
    }

    overall_review = payload.get("overall_review")
    if isinstance(overall_review, dict):
        comment = str(overall_review.get("comment") or "").strip()
        points = [str(item).strip() for item in overall_review.get("review_points") or []]
        points = [item for item in points if item][:4]
        if comment or points:
            result_payload["overall_review"] = {
                "comment": comment,
                "review_points": points,
                "source": "codex_score",
            }

    if usage:
        result_payload["billing_usage"] = usage

    return result_payload


def build_turn_band7_with_codex(question: str, transcript: str, part: str, call_id: str) -> str:
    """Generate Band 7 model answer using Codex CLI."""
    part_constraints = ""
    if part == "p1":
        part_constraints = (
            "This is IELTS Speaking Part 1. Write a short natural answer, normally 1-3 sentences, maximum 3 sentences. "
            "Do not turn it into a long Part 2-style speech. One concise Markdown paragraph is preferred."
        )
    elif part == "p2":
        part_constraints = (
            "This is IELTS Speaking Part 2. Write a natural long-turn answer in Markdown paragraphs. "
            "Cover the cue-card points without copying the bullet list."
        )
    elif part == "p3":
        part_constraints = (
            "This is IELTS Speaking Part 3. Write a developed discussion answer, about 4-6 sentences, "
            "with an opinion, reasoning, and one concrete example or contrast."
        )
    else:
        part_constraints = "Write an answer appropriate to the IELTS Speaking part shown by the questions."

    prompt = (
        f"Write a natural IELTS Speaking Band 7 spoken version. Preserve the candidate's core ideas, "
        "but improve cohesion, vocabulary, and grammar. Do not include the original question or cue-card bullets. "
        "Format the answer as concise Markdown paragraphs with blank lines between paragraphs. "
        + part_constraints
        + "\n\nQuestion:\n"
        + question
        + "\n\nCandidate transcript:\n"
        + transcript
        + "\n\nBand 7 spoken version:"
    )

    output, _ = run_codex(prompt, call_id)
    return clean_band7_output(output)


def build_ai_coaching_with_codex(question: str, transcript: str, band7: str, part: str, call_id: str, profile: dict[str, Any] | None = None) -> str:
    """Generate AI coaching using Codex CLI with full prompt.

    Includes part-specific hints, grammar correction requirements, and format validation.
    """
    part_hint = {
        "p1": "Part 1 要简短、直接、自然。重点提醒：直接回答 + 一个原因 + 一个小细节。",
        "p2": "Part 2 要覆盖 cue card，并把答案说满。重点提醒：开头点题 + 展开细节 + 例子/经历 + 收尾。",
        "p3": "Part 3 要做抽象讨论。重点提醒：观点 + 原因 + 对比/例子 + 简短总结。",
    }.get(part, "按对应的 IELTS Speaking 部分给出实用中文 coaching。")

    prompt = f"""请为这一段 IELTS Speaking 回答生成中文 coaching。只输出简短 Markdown，不要标题。
请结合学习画像、当前转写和 Band 7 版本，写得具体、实用、适合大陆 IELTS 学习者。
输出限制：
- 写 2-4 个自然分点的 Markdown bullet。
- 分点内容由 AI 自己决定，不要套固定格式；可以写问题、原因、结构、练法或示范句。
- 不要强制给"可以直接替换成"的英文句子；只有在确实有帮助时才自然给例句。
- 不要强制使用"证据/问题原因/替代表达/下一步"这四个固定标签。
- 最后一条必须是语法错误纠正：
  - 没有明显口语语法/搭配问题时，写 "- 语法错误纠正：无"。
  - 有问题时，写 "- 语法错误纠正："，并把具体纠正放在它下面的二级编号列表里，例如 "  1. `going internship` -> `I am doing an internship.`"。
- 语法错误纠正只管影响口语表达的语法或搭配问题；不要把句末标点、句号、大小写、书面格式当成语法错误。
- 必须有清晰换行，不要写成长段落。
- 不要空泛评价，不要只复述分数。

{part_hint}

Question:
{question}

Candidate transcript:
{transcript or '(missing)'}

Band 7 spoken version:
{band7}

Learning profile:
{json.dumps(profile or {})}
"""
    output, _ = run_codex(prompt, call_id)
    coaching = normalize_coaching_markdown(output)
    coaching = ensure_grammar_correction_bullet(coaching, transcript)
    if not concise_coaching_markdown(coaching):
        raise RuntimeError("codex coaching was too short or missing grammar correction")
    return coaching


def turn_feedback_with_codex(question: str, transcript: str, part: str, target: str, profile: dict[str, Any] | None, call_id: str) -> dict[str, str]:
    """Generate Band 7 and AI coaching together using Codex CLI.

    This combined generation ensures the Band 7 and coaching are consistent.
    """
    prompt = f"""Return JSON only with keys band7_version and ai_coaching.

Task:
- Write one natural IELTS Speaking Band {target} spoken version for this single turn.
- Then write concise Chinese Markdown coaching for this same turn.
- Answer the exact examiner question directly and preserve the candidate's likely intent.
- Reuse the candidate's concrete idea when it is relevant; improve cohesion, vocabulary, and grammar.
- Do not include the original question, cue-card bullets, titles, labels, code fences, or logs.

Band 7 version constraints:
{model_answer_constraints(part)}
- For Part 1, write only 1-3 natural spoken sentences.
- Do not use generic template lines such as "this is quite easy for me to answer", "connects with my daily life", or "closer to Band 7".
- If the transcript is weak, infer a sensible direct answer from the question type instead of writing a vague template.

Coaching constraints:
- Use natural concise Chinese Markdown bullets.
- Write 2-4 short bullets, choosing the bullet focus freely based on the learner's real issue.
- Do not force a replacement sentence, fixed labels, fixed order, or fixed section names.
- If a sample sentence genuinely helps, include it naturally inside a bullet; otherwise give structure, direction, or practice advice.
- End with exactly one grammar-correction bullet:
  - If there is no meaningful spoken grammar/collocation issue, write "- 语法错误纠正：无".
  - If there are issues, write "- 语法错误纠正：" and put the corrections under it as indented numbered sub-items, for example "  1. `going internship` -> `I am doing an internship.`".
- Only include spoken-English grammar/collocation problems that affect meaning or fluency; do not treat punctuation, periods, full stops, capitalization, or written formatting as grammar errors.

Question:
{question}

Candidate transcript:
{transcript or "(missing)"}

Learning profile:
{json.dumps(profile or {})}
"""
    output, _ = run_codex(prompt, call_id)
    payload = extract_json_object(output)
    band7 = clean_band7_output(str(payload.get("band7_version") or ""))
    coaching = clean_markdown_text(str(payload.get("ai_coaching") or ""))
    if not valid_turn_band7(question, band7, part):
        raise RuntimeError("codex turn feedback did not include a question-aware Band 7 answer")
    coaching = ensure_grammar_correction_bullet(coaching, transcript)
    if not concise_coaching_markdown(coaching):
        raise RuntimeError("codex turn feedback did not include concise Markdown coaching")
    return {"band7_version": band7, "ai_coaching": coaching}


def build_upgrade_notes(transcript: str) -> list[str]:
    """Extract upgrade notes from transcript."""
    notes = []

    # Check for very short answers
    words = _word_count(transcript)
    if words < 30:
        notes.append("Give a direct answer, add a reason, then add one concrete example.")

    # Check for repeated words
    word_list = re.findall(r"\b[a-z]{4,}\b", transcript.lower())
    if word_list:
        from collections import Counter
        counts = Counter(word_list)
        repeated = [word for word, count in counts.most_common(5) if count >= 3]
        if repeated:
            notes.append(f"Avoid repeating: {', '.join(repeated[:3])}")

    # Check for filler words
    fillers = ["um", "uh", "like", "you know", "i mean", "actually", "basically"]
    filler_count = sum(transcript.lower().count(f" {filler} ") for filler in fillers)
    if filler_count >= 3:
        notes.append("Reduce filler words (um, uh, like, you know)")

    if not notes:
        notes.append("Extend answers with specific reasons and examples")

    return notes[:3]


def _fallback_score(transcript: str, part: str) -> dict[str, Any]:
    words = _word_count(transcript)
    if words >= 220:
        base = 6.0
    elif words >= 120:
        base = 5.5
    elif words >= 60:
        base = 5.0
    elif words >= 25:
        base = 4.5
    else:
        base = 4.0
    if part == "p2" and words < 80:
        base = min(base, 5.0)
    if part == "p3" and words < 100:
        base = min(base, 5.0)
    return {
        "overall_band": base,
        "fluency_coherence": base,
        "lexical_resource": max(4.0, base - 0.5),
        "grammatical_range": max(4.0, base - 0.5),
        "pronunciation_estimate": None,
        "feedback": "Fallback score generated from completed browser transcripts. Configure the full AI scorer for richer feedback.",
        "backend": "fallback",
        "word_count": words,
    }


def _criteria_feedback(score: dict[str, Any], transcript: str) -> dict[str, Any]:
    return {
        "fluency_coherence": {
            "band": score["fluency_coherence"],
            "standard": "Answers should be extended, coherent, and easy to follow.",
            "focus": "Add clearer reasons and examples for each answer.",
            "advice": "Use a short point-reason-example structure.",
        },
        "lexical_resource": {
            "band": score["lexical_resource"],
            "standard": "Use precise topic vocabulary instead of repeated simple words.",
            "focus": "Replace vague words with topic-specific expressions.",
            "advice": "Prepare two or three flexible phrases for this topic.",
        },
        "grammatical_range_accuracy": {
            "band": score["grammatical_range"],
            "standard": "Use accurate simple sentences plus some longer complex clauses.",
            "focus": "Control tense and agreement before adding complexity.",
            "advice": "Repeat the answer once using because, although, or which.",
        },
    }


def _band7_fallback(turn: SpeakingTurn) -> str:
    """Simple fallback for Django turn model."""
    question = turn.question.rstrip("?")
    return (
        f"Well, regarding {question.lower()}, I would give a clear answer with a specific reason and a brief example. "
        "That would make the response sound more natural and developed."
    )


# --- P1 Name/Identity Helpers ---


DEFAULT_FULL_NAME = "Li Hua"
DEFAULT_ENGLISH_NAME = "Jasper"


def is_p1_name_intro_turn(turn: dict[str, Any] | SpeakingTurn) -> bool:
    """Check if turn is a P1 name introduction."""
    if isinstance(turn, SpeakingTurn):
        prompt = turn.metadata.get("prompt", {}) if isinstance(turn.metadata, dict) else {}
        return turn.part == "p1" and prompt.get("flow") == "intro" and prompt.get("role") == "name"
    prompt = turn.get("prompt") or {}
    return turn.get("part") == "p1" and prompt.get("flow") == "intro" and prompt.get("role") == "name"


def p1_name_answer(full_name: str | None, english_name: str | None) -> str:
    """Generate P1 name answer from profile."""
    full = clean_report_text(str(full_name or DEFAULT_FULL_NAME)) or DEFAULT_FULL_NAME
    english = clean_report_text(str(english_name or DEFAULT_ENGLISH_NAME)) or DEFAULT_ENGLISH_NAME
    if full.lower() == english.lower():
        return f"My full name is {full}."
    return f"My full name is {full}, but you can call me {english}."


def _p1_question_only_answer(question: str, answer_lower: str = "") -> str:
    """Generate a clean Band 7 P1 answer based on the question type."""
    lowered = question.lower()
    if "name" in lowered:
        return "My full name is Jasper Chen, but most people just call me Jasper."
    if lowered.startswith(("do you prefer", "would you prefer")) or ("prefer" in lowered and "or" in lowered):
        return "I would prefer the option that fits my daily routine better, because convenience matters a lot when you have a busy schedule."
    if ("work" in lowered or "study" in lowered or "student" in lowered) and "prefer" not in lowered:
        if any(w in answer_lower for w in ("work", "job", "company", "office", "engineer", "business")):
            return "I work as a software engineer at the moment. I enjoy it because the work is practical and I get to solve real problems every day."
        return "I'm a university student at the moment, majoring in computer science. I chose it because I enjoy building things and solving practical problems."
    if ("who" in lowered and "live" in lowered) or ("family" in lowered and "own" in lowered) or ("live with" in lowered):
        if any(w in answer_lower for w in ("own", "alone", "myself")):
            return "I live on my own at the moment. It is convenient because my place is close to my university and I can manage my own schedule."
        if any(w in answer_lower for w in ("family", "parent", "mother", "father", "roommate")):
            return "I live with my family right now. It is comfortable because we share the housework and I can save money on rent."
        return "I live on my own at the moment, in a small apartment near my university. It gives me the independence I need for my studies."
    if any(word in lowered for word in ("live", "living", "hometown", "house", "apartment", "flat", "city")):
        return "I live in a fairly convenient area close to my university. I like it because transport and daily shopping are easy, and the neighbourhood is quiet enough to study."
    if any(word in lowered for word in ("favourite", "favorite", "like most", "enjoy most")):
        return "My favourite would be the one that connects with my personal routine. It feels natural because I do it regularly and it always puts me in a good mood."
    if any(word in lowered for word in ("think", "opinion", "important")):
        return "I think it depends on the situation. For most people it probably matters, but personally I would say it is useful rather than essential."
    if "easy" in lowered or "difficult" in lowered or "hard" in lowered:
        return "I find it fairly easy, mainly because I have been doing it for a while now. Practice makes a big difference, and once you get used to it, it feels natural."
    if any(word in lowered for word in ("how often", "how much", "how long", "how many")):
        return "For me, it happens fairly regularly, maybe a few times a week. It has become part of my routine without me really noticing."
    if any(word in lowered for word in ("when", "last time", "recently")):
        return "The last time was not long ago, probably within the past week. I remember it quite clearly because it was a pleasant experience."
    if lowered.startswith(("do you", "are you", "is there", "can you", "have you")):
        if any(w in answer_lower for w in ("no", "not", "rarely", "hardly", "don't")):
            return "No, not really. It is not something I do very often, mainly because my schedule does not leave much time for it."
        return "Yes, I would say so. It is something I do fairly often, and I find it quite enjoyable because it fits naturally into my daily life."
    return "I would say it is something I experience quite often in my daily life. The main reason is that it connects with my routine and gives me a practical benefit."


def build_turn_band7_fallback(
    question: str,
    part: str,
    transcript: str = "",
    full_name: str | None = None,
    english_name: str | None = None,
    turn_metadata: dict[str, Any] | None = None,
) -> str:
    """Generate a rule-based Band 7 answer. Never quotes raw transcript — only uses it to detect intent direction."""
    question_clean = clean_report_text(question) or "this question"
    answer_lower = clean_report_text(transcript).lower() if transcript else ""
    turn_metadata = turn_metadata or {}

    if part == "p1":
        # Check if it's a name intro turn
        if turn_metadata.get("prompt", {}).get("flow") == "intro" and turn_metadata.get("prompt", {}).get("role") == "name":
            return p1_name_answer(full_name, english_name)
        return _p1_question_only_answer(question_clean, answer_lower)

    if part == "p2":
        return (
            "I would like to talk about something that happened to me recently. "
            "It was memorable because it changed the way I think about this topic. "
            "What made it stand out was the combination of timing and the people involved, "
            "and looking back, I feel it was a valuable experience that taught me something new."
        )

    return (
        "I think this is an interesting question because people can look at it from different angles. "
        "From my perspective, the most important factor is practicality, because in everyday life "
        "we often have to balance convenience with long-term value. "
        "I would also add that personal experience plays a big role in shaping people's views on this."
    )


# --- Learning Profile ---


def build_learning_profile(user, attempt: SpeakingAttempt) -> dict[str, Any]:
    """Build learning profile from user's attempt history."""
    turns = list(attempt.turns.all().order_by("sequence"))
    completed_turns = [t for t in turns if _turn_status(t) == "completed"]

    evidence: list[str] = []
    tags: list[str] = []
    repeated_phrases: list[str] = []

    for turn in completed_turns:
        transcript = (turn.transcript_cleaned or turn.transcript_raw or "").strip()
        if not transcript:
            continue
        word_count = _word_count(transcript)
        part = turn.part or ""
        if part == "p2":
            evidence.append(f"P2 回答约 {word_count} 词，需要继续拉长展开。")
        elif part == "p3":
            evidence.append(f"P3 回答约 {word_count} 词，需要补上原因、对比或例子。")
        elif part == "p1":
            evidence.append(f"P1 回答约 {word_count} 词，需要更直接、更自然。")

        # Check for short answers
        if word_count < 20:
            tags.append("short_answer")
        if word_count < 35:
            tags.append("limited_development")

    # Get weak items from training
    weak_obs = SpeakingTrainingObservation.objects.filter(user=user, weak_item_flag=True).order_by("-observed_at")[:10]
    for obs in weak_obs:
        if obs.weak_reasons:
            tags.extend(obs.weak_reasons)

    tags = sorted(set(tags))[:8]

    return {
        "primary_focus": "answer_development" if "short_answer" in tags or "limited_development" in tags else "task_relevance",
        "primary_focus_text": "这次主要卡在回答展开不够，不是题目完全不会。" if "limited_development" in tags else "这次主要问题是没有完全扣住题目，先把回答方向答准。",
        "habit_tags": tags,
        "repeated_phrases": repeated_phrases[:6],
        "evidence": evidence[:8],
    }


# --- Build Turn Feedback (Complete) ---


def build_turn_feedback(
    turn: SpeakingTurn,
    attempt: SpeakingAttempt,
    user_profile: dict[str, Any] | None = None,
    allow_codex: bool = True,
) -> dict[str, Any]:
    """Build complete turn feedback with Band 7 and AI coaching.

    This is the complete migration from old server's build_turn_feedback.
    Returns a dict of fields to update in turn.metadata.
    """
    transcript = (turn.transcript_cleaned or turn.transcript_raw or "").strip()
    target = target_band_label(attempt)
    part = turn.part or "p1"

    # Get user profile for personalization
    profile = user_profile or {}
    full_name = profile.get("full_name")
    english_name = profile.get("english_name")

    # Result dict
    result: dict[str, Any] = {}

    # Try Codex generation first
    generated: dict[str, str] = {}
    if allow_codex and transcript:
        try:
            generated = turn_feedback_with_codex(
                turn.question,
                transcript,
                part,
                target,
                profile,
                f"turn_feedback_{attempt.attempt_id}_{turn.turn_id}",
            )
        except Exception as exc:
            result["feedback_generation_error"] = str(exc)

    # Build Band 7 version
    band7 = generated.get("band7_version") or ""
    if not valid_turn_band7(turn.question, band7, part):
        band7 = build_turn_band7_fallback(
            turn.question,
            part,
            transcript,
            full_name,
            english_name,
            turn.metadata if isinstance(turn.metadata, dict) else None,
        )

    result["band7_version"] = clean_report_text(band7)
    result["band7_markdown"] = spoken_markdown(band7, part)
    result["target_band_version"] = result["band7_version"]
    result["target_band_markdown"] = result["band7_markdown"]
    result["target_band"] = target

    # Model audio placeholder (no real TTS in Django fallback)
    result["model_audio"] = {"status": "fallback", "audio_url": None}

    # Upgrade notes
    result["upgrade_notes"] = build_upgrade_notes(transcript)

    # Build AI coaching
    coaching = generated.get("ai_coaching") or ""
    if not concise_coaching_markdown(coaching):
        # Fallback coaching
        coaching = build_ai_coaching_fallback(
            turn.question,
            transcript,
            result["band7_version"],
            part,
            profile,
        )
    result["ai_coaching"] = clean_markdown_text(coaching)

    # Status fields
    result["feedback_generation_status"] = "ready"
    result["feedback_generation_backend"] = "codex" if generated else "fallback"

    return result


def build_ai_coaching_fallback(
    question: str,
    transcript: str,
    band7: str,
    part: str,
    profile: dict[str, Any] | None = None,
) -> str:
    """Build fallback AI coaching when Codex fails."""
    profile = profile or {}
    tags = profile.get("habit_tags", [])
    repeated_phrases = profile.get("repeated_phrases", [])

    question_clean = clean_report_text(question) or "this question"
    question_lower = question_clean.lower()
    transcript_words = _word_count(transcript)
    transcript_usable = transcript_words >= 10

    reason = _coaching_reason_for_question(question_lower, part, transcript_words, transcript_usable, tags)
    next_action = _coaching_next_action(question_lower, part, transcript_usable, tags)

    lines: list[str] = []
    lines.append("- AI 辅导生成失败，以下是系统默认建议。")
    lines.append(f"- 本题关键词：{question_clean[:60]}")
    lines.append(f"- {reason}")

    if transcript_usable:
        lines.append(f"- 这次回答约 {transcript_words} 词，建议再补充细节。")

    if repeated_phrases:
        lines.append(f"- 少重复这些表达：{', '.join(repeated_phrases[:2])}")

    lines.append(f"- {next_action}")

    return ensure_grammar_correction_bullet("\n".join(lines), transcript)


def _training_relevance(question: str, transcript: str) -> Decimal:
    q_words = {word.strip(".,?!:;").lower() for word in question.split() if len(word.strip(".,?!:;")) > 3}
    t_words = {word.strip(".,?!:;").lower() for word in transcript.split() if len(word.strip(".,?!:;")) > 3}
    if not q_words or not t_words:
        return Decimal("0.000")
    return Decimal(str(round(len(q_words & t_words) / max(1, len(q_words)), 3)))


@transaction.atomic
def score_attempt(user, attempt_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    attempt = _load_attempt_for_user(user, attempt_id)
    if attempt.status == SpeakingAttempt.Status.ABORTED:
        raise SpeakingError("Aborted attempts cannot be scored.")
    turns = list(attempt.turns.all().order_by("sequence"))
    incomplete = [turn for turn in turns if _turn_status(turn) != "completed"]
    if incomplete:
        raise SpeakingError("Complete all speaking turns before generating the section report.")
    transcript = "\n".join(
        f"Q{index + 1}: {turn.question}\nA: {turn.transcript_cleaned or turn.transcript_raw}"
        for index, turn in enumerate(turns)
    )
    if not transcript.strip():
        raise SpeakingError("Missing transcript")

    # Try Codex scoring first, fallback to heuristic on error
    questions_text = "\n".join(f"Q{i+1}: {t.question}" for i, t in enumerate(turns))
    call_id = f"score_attempt_{attempt_id}"
    try:
        score = score_with_codex(transcript, questions_text, attempt.mode, call_id)
    except Exception as exc:
        score = _fallback_score(transcript, attempt.mode)
        score["codex_error"] = str(exc)

    criteria = _criteria_feedback(score, transcript)

    # Get user profile for personalization
    from apps.accounts.models import UserProfile
    profile_obj, _ = UserProfile.objects.get_or_create(user=user)
    user_profile = {
        "full_name": profile_obj.full_name,
        "english_name": profile_obj.english_name,
    }

    # Generate AI feedback for each turn using complete build_turn_feedback
    for turn in turns:
        turn_transcript = turn.transcript_cleaned or turn.transcript_raw
        if not turn_transcript.strip():
            continue

        # Use the complete build_turn_feedback logic
        feedback = build_turn_feedback(turn, attempt, user_profile, allow_codex=True)

        # Update turn metadata
        metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
        metadata.update(feedback)

        # Track source for scoring context
        if feedback.get("feedback_generation_backend") == "codex":
            metadata["band7_source"] = "codex"
            metadata["ai_coaching_source"] = "codex"
        else:
            metadata["band7_source"] = "fallback"
            metadata["ai_coaching_source"] = "fallback"

        turn.metadata = metadata
        turn.save()

    attempt.status = SpeakingAttempt.Status.SCORED
    attempt.metadata = {
        **(attempt.metadata if isinstance(attempt.metadata, dict) else {}),
        "current_turn": None,
        "scored_at": timezone.now().isoformat(),
    }
    attempt.save()
    attempt.refresh_from_db()

    runtime = _runtime_attempt_payload(attempt)

    # Use overall_review from Codex if available, otherwise use fallback
    overall_review = score.get("overall_review")
    if not overall_review or overall_review.get("source") != "codex_score":
        overall_review = {
            "comment": "Fallback report generated locally. Use the full AI pipeline for personalized scoring later.",
            "review_points": ["Complete every answer", "Add reasons and examples", "Review weak short answers first"],
            "source": "django_fallback",
        }

    runtime.update(
        {
            "status": "scored",
            "transcript_cleaned": transcript,
            "ielts_score": score,
            "feedback_summary": score["feedback"],
            "criteria_feedback": criteria,
            "part_scores": {
                attempt.part or attempt.mode: {
                    "part": attempt.part or attempt.mode,
                    "turn_count": len(turns),
                    "band": score["overall_band"],
                    "fluency_coherence": score["fluency_coherence"],
                    "lexical_resource": score["lexical_resource"],
                    "grammatical_range": score["grammatical_range"],
                }
            },
            "overall_review": overall_review,
            "personalized_coaching": {
                "focus": "先确保每题都有完整回答，再逐步提高词汇和语法复杂度。",
                "next_practice": ["重练最短的一题", "每题至少补一个例子"],
            },
        }
    )

    report, _created = SpeakingReport.objects.update_or_create(
        user=user,
        attempt=attempt,
        defaults={
            "overall_band": Decimal(str(score["overall_band"])),
            "fluency_coherence": Decimal(str(score["fluency_coherence"])),
            "lexical_resource": Decimal(str(score["lexical_resource"])),
            "grammar_range_accuracy": Decimal(str(score["grammatical_range"])),
            "pronunciation": None,
            "feedback_summary": score["feedback"],
            "report_payload": runtime,
        },
    )

    observations = []
    for turn in turns:
        turn_text = turn.transcript_cleaned or turn.transcript_raw
        word_count = _word_count(turn_text)
        reasons = []
        if score["overall_band"] < 5.5:
            reasons.append("low_band")
        if word_count < 25:
            reasons.append("short_answer")
        relevance = _training_relevance(turn.question, turn_text)
        if relevance < Decimal("0.200"):
            reasons.append("off_topic")
        observation, _ = SpeakingTrainingObservation.objects.update_or_create(
            user=user,
            observation_id=f"{attempt.attempt_id}_{turn.turn_id}",
            defaults={
                "attempt": attempt,
                "turn": turn,
                "legacy_attempt_id": attempt.attempt_id,
                "legacy_turn_id": turn.turn_id,
                "question_id": f"{turn.part}:{hashlib.md5(turn.question.encode()).hexdigest()[:12]}",
                "part": turn.part,
                "question": turn.question,
                "transcript": turn_text,
                "overall_band": Decimal(str(score["overall_band"])),
                "fluency_coherence": Decimal(str(score["fluency_coherence"])),
                "lexical_resource": Decimal(str(score["lexical_resource"])),
                "grammar_range_accuracy": Decimal(str(score["grammatical_range"])),
                "pronunciation": None,
                "relevance": relevance,
                "weak_item_flag": bool(reasons),
                "weak_reasons": reasons,
                "model_version": "django_fallback",
                "observed_at": timezone.now(),
                "next_due": timezone.now() + timezone.timedelta(days=1 if reasons else 14),
            },
        )
        observations.append(
            {
                "observation_id": observation.observation_id,
                "question_id": observation.question_id,
                "part": observation.part,
                "weak_item_flag": observation.weak_item_flag,
                "weak_reasons": observation.weak_reasons,
            }
        )
    runtime["training_observations"] = observations
    report.report_payload = runtime
    report.save(update_fields=["report_payload", "updated_at"])
    return runtime


# --- Regenerate ---


def regenerate_turn_feedback(user, attempt_id: str, turn_id: str) -> dict[str, Any]:
    """Regenerate AI feedback for a completed turn.

    This is the complete migration from old server's handle_turn_feedback_regenerate.
    Uses build_turn_feedback for consistent logic.

    Args:
        user: The authenticated user
        attempt_id: The attempt ID
        turn_id: The turn ID

    Returns:
        dict with 'ok', 'attempt', 'turn' keys

    Raises:
        SpeakingError: If validation fails or turn not found
    """
    attempt = _load_attempt_for_user(user, attempt_id)
    turn = SpeakingTurn.objects.filter(attempt=attempt, turn_id=turn_id).first()
    if not turn:
        raise SpeakingError("Turn not found")
    if _turn_status(turn) != "completed":
        raise SpeakingError("Only completed turns can regenerate AI feedback.")

    turn_transcript = turn.transcript_cleaned or turn.transcript_raw
    if not turn_transcript.strip():
        raise SpeakingError("Cannot regenerate feedback for empty transcript.")

    # Get user profile for personalization
    from apps.accounts.models import UserProfile
    profile_obj, _ = UserProfile.objects.get_or_create(user=user)
    user_profile = {
        "full_name": profile_obj.full_name,
        "english_name": profile_obj.english_name,
    }

    # Build learning profile
    learning_profile = build_learning_profile(user, attempt)

    # Use the complete build_turn_feedback logic
    feedback = build_turn_feedback(turn, attempt, user_profile, allow_codex=True)

    # Update turn metadata
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    metadata.update(feedback)
    metadata["feedback_regenerated_at"] = timezone.now().isoformat()

    # Track regeneration source
    if feedback.get("feedback_generation_backend") == "codex":
        metadata["band7_source"] = "codex_regenerated"
        metadata["ai_coaching_source"] = "codex_regenerated"
    else:
        metadata["band7_source"] = "fallback_regenerated"
        metadata["ai_coaching_source"] = "fallback_regenerated"

    turn.metadata = metadata
    turn.save(update_fields=["metadata"])

    attempt.updated_at = timezone.now()
    attempt.save(update_fields=["updated_at"])

    # Update report payload if exists
    if hasattr(attempt, "report") and attempt.report:
        report = attempt.report
        payload = report.report_payload if isinstance(report.report_payload, dict) else {}
        turns_payload = payload.get("turns", [])
        for i, t in enumerate(turns_payload):
            if t.get("id") == turn_id:
                turns_payload[i]["band7_version"] = metadata.get("band7_version", "")
                turns_payload[i]["band7_markdown"] = metadata.get("band7_markdown", "")
                turns_payload[i]["target_band_version"] = metadata.get("target_band_version", "")
                turns_payload[i]["target_band_markdown"] = metadata.get("target_band_markdown", "")
                turns_payload[i]["target_band"] = metadata.get("target_band", "7")
                turns_payload[i]["upgrade_notes"] = metadata.get("upgrade_notes", [])
                turns_payload[i]["ai_coaching"] = metadata.get("ai_coaching", "")
                turns_payload[i]["model_audio"] = metadata.get("model_audio", {})
                turns_payload[i]["feedback_generation_status"] = metadata.get("feedback_generation_status", "ready")
                turns_payload[i]["feedback_generation_backend"] = metadata.get("feedback_generation_backend", "fallback")
        report.report_payload = payload
        report.save(update_fields=["report_payload", "updated_at"])

    return {
        "ok": True,
        "attempt": _runtime_attempt_payload(attempt),
        "turn": _turn_payload(turn),
    }


def regenerate_turn_transcript(user, attempt_id: str, turn_id: str) -> dict[str, Any]:
    """Re-transcribe audio and regenerate feedback for a turn.

    Since we don't have real Azure Speech integration, this fallback
    reuses existing transcript and regenerates feedback.

    Args:
        user: The authenticated user
        attempt_id: The attempt ID
        turn_id: The turn ID

    Returns:
        dict with 'ok', 'attempt', 'turn' keys

    Raises:
        SpeakingError: If validation fails or turn/audio not found
    """
    attempt = _load_attempt_for_user(user, attempt_id)
    turn = SpeakingTurn.objects.filter(attempt=attempt, turn_id=turn_id).first()
    if not turn:
        raise SpeakingError("Turn not found")
    if _turn_status(turn) != "completed":
        raise SpeakingError("Only completed turns can regenerate transcript.")

    if not turn.audio_path:
        raise SpeakingError("重新转写失败：这题没有可用录音文件。")

    audio_path = Path(settings.MEDIA_ROOT) / turn.audio_path
    if not audio_path.exists():
        raise SpeakingError("重新转写失败：这题没有可用录音文件。")

    transcript = turn.transcript_cleaned or turn.transcript_raw
    if not transcript:
        transcript = "Fallback transcript: audio file exists but no transcript captured."

    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    metadata["transcript_status"] = "captured"
    metadata["transcript_source"] = "fallback_retranscribe"
    metadata["band7_version"] = _band7_fallback(turn)
    metadata["band7_markdown"] = metadata["band7_version"]
    metadata["upgrade_notes"] = ["Give a direct answer, add a reason, then add one concrete example."]
    metadata["ai_coaching"] = "先把答案说完整，再补一个具体例子；这是当前 fallback 报告的练习重点。"
    metadata["transcript_regenerated_at"] = timezone.now().isoformat()
    turn.metadata = metadata
    turn.save(update_fields=["metadata"])

    attempt.updated_at = timezone.now()
    attempt.save(update_fields=["updated_at"])

    if hasattr(attempt, "report") and attempt.report:
        report = attempt.report
        payload = report.report_payload if isinstance(report.report_payload, dict) else {}
        turns_payload = payload.get("turns", [])
        for i, t in enumerate(turns_payload):
            if t.get("id") == turn_id:
                turns_payload[i]["transcript_status"] = "captured"
                turns_payload[i]["transcript_source"] = "fallback_retranscribe"
                turns_payload[i]["band7_version"] = metadata["band7_version"]
                turns_payload[i]["band7_markdown"] = metadata["band7_markdown"]
                turns_payload[i]["upgrade_notes"] = metadata["upgrade_notes"]
                turns_payload[i]["ai_coaching"] = metadata["ai_coaching"]
        report.report_payload = payload
        report.save(update_fields=["report_payload", "updated_at"])

    return {
        "ok": True,
        "attempt": _runtime_attempt_payload(attempt),
        "turn": _turn_payload(turn),
    }


def p3_fallback(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    theme = str(payload.get("theme") or "general speaking").replace("_", " ").strip() or "general speaking"
    prior_answer = str(payload.get("prior_answer") or "")
    questions = [
        f"Why do people have different opinions about {theme}?",
        f"How has {theme} changed in your country in recent years?",
        f"Do you think {theme} will become more important in the future?",
        f"What problems can {theme} create for ordinary people?",
        f"How should governments or schools respond to changes in {theme}?",
    ]
    follow_up = "Could you give a specific example to support that view?"
    if len(prior_answer.split()) > 40:
        follow_up = "What might be the opposite argument, and why might some people agree with it?"
    return {"questions": questions, "follow_up": follow_up, "backend": "fallback"}


def tts_fallback(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    text = str(payload.get("text") or "").strip()
    if not text:
        return {"provider": "none", "status": "empty_text", "audio_url": None, "message": "No text to synthesize."}
    return {
        "provider": "browser",
        "status": "fallback",
        "audio_url": None,
        "message": "Server TTS provider is not configured; use browser fallback.",
    }


def _safe_slug(value: str) -> str:
    """Convert string to safe filename slug."""
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")[:96] or "audio"


def volcengine_tts(text: str, voice: str = "en_male_adam", role: str = "model", cache_key: str | None = None) -> dict[str, Any]:
    """Generate TTS audio using VolcEngine API, with caching."""
    text = text.strip()
    if not text:
        return {"provider": "none", "status": "empty_text", "audio_url": None, "message": "No text to synthesize."}

    if os.environ.get("IELTS_WEB_DISABLE_VOLCENGINE_TTS") == "1":
        return {"provider": "browser", "status": "fallback", "audio_url": None, "message": "VolcEngine TTS disabled; use browser fallback."}

    safe_role = "examiner" if role == "examiner" else "model"
    folder = Path(settings.MEDIA_ROOT) / "tts" / safe_role
    folder.mkdir(parents=True, exist_ok=True)

    key = _safe_slug(cache_key or f"{role}_{uuid.uuid4().hex}")
    audio_path = folder / f"{key}.mp3"

    if audio_path.exists():
        return {
            "provider": "volcengine",
            "status": "cached",
            "audio_url": f"/api/tts-audio/{safe_role}/{audio_path.name}",
            "path": str(audio_path),
            "content_type": "audio/mpeg",
        }

    payload = json.dumps({"text": text, "speaker": voice, "language": "en"}).encode("utf-8")
    request = urllib.request.Request(
        "https://translate.volcengine.com/crx/tts/v1/",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": "chrome-extension://klgfhbdadaspgppeadghjjemk",
            "User-Agent": "Mozilla/5.0",
            "Cookie": "hasUserBehavior=1",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=4) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
        encoded = data.get("audio", {}).get("data")
        if not encoded:
            raise ValueError(f"VolcEngine TTS returned no audio: {data}")  # noqa: TRY301
        audio_path.write_bytes(base64.b64decode(encoded))
        return {
            "provider": "volcengine",
            "status": "ready",
            "audio_url": f"/api/tts-audio/{safe_role}/{audio_path.name}",
            "path": str(audio_path),
            "content_type": "audio/mpeg",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "provider": "browser",
            "status": "fallback",
            "audio_url": None,
            "message": f"VolcEngine TTS unavailable; use browser fallback: {exc}",
        }


def ensure_examiner_tts(attempt_id: str, turn: dict[str, Any]) -> None:
    """Ensure turn has examiner TTS audio_url generated."""
    current = turn.get("examiner_tts") or {}
    if current.get("audio_url") or current.get("status") not in (None, "pending"):
        return
    turn["examiner_tts"] = volcengine_tts(
        str(turn.get("examiner_text") or turn.get("question") or ""),
        role="examiner",
        cache_key=f"{attempt_id}_{turn['id']}_examiner",
    )


def latest_report(user) -> dict[str, Any]:
    attempts = (
        SpeakingAttempt.objects.filter(user=user, status=SpeakingAttempt.Status.SCORED)
        .select_related("report")
        .prefetch_related("turns")
        .order_by("-updated_at")
    )
    for attempt in attempts:
        if report_is_valid(attempt):
            return report_payload(attempt)
    return {"report": None}


def tts_audio_path(role: str, filename: str) -> Path | None:
    safe_role = "examiner" if role == "examiner" else "model"
    safe_name = Path(str(filename or "")).name
    if not safe_name:
        return None
    path = Path(settings.MEDIA_ROOT) / "tts" / safe_role / safe_name
    return path if path.exists() else None
