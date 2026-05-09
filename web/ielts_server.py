#!/usr/bin/env python3
"""Voice-first web boundary for the IELTS Speaking Simulator.

The browser receives only JSON contracts. Audio, reports, CLI integrations, and
TTS/scoring credentials stay on the server side.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import math
import mimetypes
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_AUDIO_BYTES = 25 * 1024 * 1024
P1_TURN_COUNT = 10
P3_MAIN_COUNT = 5
P3_TURN_COUNT = 10


def clamp_band(value: float | int | None) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(0.0, min(9.0, round(numeric * 2.0) / 2.0))


def rounded_overall(scores: dict[str, float | None]) -> float:
    values = [
        scores.get("fluency_coherence"),
        scores.get("lexical_resource"),
        scores.get("grammatical_range"),
        scores.get("pronunciation_estimate"),
    ]
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric:
        return 0.0
    return clamp_band(math.ceil((sum(numeric) / len(numeric)) * 2.0) / 2.0)


def read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in {path}: {exc}") from exc


def extract_json_object(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("model output did not contain a JSON object")
    return json.loads(match.group(0))


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def local_timestamp(value: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")[:96] or "attempt"


def short_question(value: str, limit: int = 92) -> str:
    clean = re.sub(r"\s+", " ", value).strip()
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


class QuestionBank:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.p1: list[dict[str, str]] = []
        self.p2: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        self.p1 = self._load_p1()
        self.p2 = self._load_p2()
        if not self.p1:
            raise ValueError(f"No IELTS Part 1 questions loaded from {self.data_dir / 'part1'}")
        if not self.p2:
            raise ValueError(f"No IELTS Part 2 topics loaded from {self.data_dir / 'part2'}")

    def _load_p1(self) -> list[dict[str, str]]:
        part_dir = self.data_dir / "part1"
        if not part_dir.is_dir():
            raise ValueError(f"IELTS Part 1 directory does not exist: {part_dir}")
        questions: list[dict[str, str]] = []
        for path in sorted(part_dir.glob("*.json")):
            payload = read_json(path)
            if payload.get("part") != 1:
                continue
            items = payload.get("questions")
            if not isinstance(items, list):
                raise ValueError(f"Part 1 questions must be an array: {path}")
            topic = str(payload.get("topic") or path.stem)
            for item in items:
                if isinstance(item, str) and item.strip():
                    questions.append({"topic": topic, "question": item.strip()})
        return questions

    def _load_p2(self) -> list[dict[str, Any]]:
        part_dir = self.data_dir / "part2"
        if not part_dir.is_dir():
            raise ValueError(f"IELTS Part 2 directory does not exist: {part_dir}")
        topics: list[dict[str, Any]] = []
        for path in sorted(part_dir.glob("*.json")):
            payload = read_json(path)
            if payload.get("part") != 2:
                continue
            items = payload.get("topics")
            if not isinstance(items, list):
                raise ValueError(f"Part 2 topics must be an array: {path}")
            for item in items:
                if not isinstance(item, dict):
                    continue
                bullets = [str(b).strip() for b in item.get("bullets", []) if str(b).strip()]
                title = str(item.get("title") or "").strip()
                if title and bullets:
                    topics.append(
                        {
                            "title": title,
                            "bullets": bullets,
                            "rounding": str(item.get("rounding") or "").strip(),
                            "p3_theme": str(item.get("p3_theme") or title).strip(),
                        }
                    )
        return topics

    def summary(self) -> dict[str, Any]:
        return {
            "part1_count": len(self.p1),
            "part2_count": len(self.p2),
            "part1_topics": sorted({item["topic"] for item in self.p1}),
            "part2_themes": sorted({item["p3_theme"] for item in self.p2}),
        }

    def sample(self, p1_count: int = 5) -> dict[str, Any]:
        p1_count = max(1, min(p1_count, len(self.p1)))
        return {"part1": random.sample(self.p1, p1_count), "part2": random.choice(self.p2)}


@dataclass
class AppState:
    data_dir: Path
    reports_dir: Path
    bank: QuestionBank = field(init=False)
    latest_report: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.bank = QuestionBank(self.data_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.attempts_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.model_audio_dir.mkdir(parents=True, exist_ok=True)
        self.examiner_audio_dir.mkdir(parents=True, exist_ok=True)

    @property
    def attempts_dir(self) -> Path:
        return self.reports_dir / "attempts"

    @property
    def audio_dir(self) -> Path:
        return self.reports_dir / "audio"

    @property
    def model_audio_dir(self) -> Path:
        return self.reports_dir / "model_audio"

    @property
    def examiner_audio_dir(self) -> Path:
        return self.reports_dir / "examiner_audio"

    def attempt_path(self, attempt_id: str) -> Path:
        return self.attempts_dir / f"{safe_slug(attempt_id)}.json"

    def save_attempt(self, attempt: dict[str, Any]) -> None:
        path = self.attempt_path(str(attempt["id"]))
        with path.open("w", encoding="utf-8") as handle:
            json.dump(attempt, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        if is_scored_report(attempt):
            self.latest_report = attempt | {"path": str(path)}
            if attempt.get("part") == "p1" or attempt.get("mode") == "p1":
                self.delete_older_p1_reports(str(attempt["id"]))

    def delete_older_p1_reports(self, keep_attempt_id: str) -> None:
        for path in self.attempts_dir.glob("*.json"):
            if path == self.attempt_path(keep_attempt_id):
                continue
            try:
                attempt = read_json(path)
            except ValueError:
                continue
            if is_scored_report(attempt) and (attempt.get("part") == "p1" or attempt.get("mode") == "p1"):
                path.unlink(missing_ok=True)

    def load_attempt(self, attempt_id: str) -> dict[str, Any]:
        path = self.attempt_path(attempt_id)
        if not path.exists():
            raise FileNotFoundError(f"Attempt not found: {attempt_id}")
        return read_json(path)

    def load_report_attempt(self, attempt_id: str) -> dict[str, Any]:
        attempt = self.load_attempt(attempt_id)
        if not is_scored_report(attempt):
            raise ValueError("Attempt report is not available until scoring is complete.")
        return attempt

    def history(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted(self.attempts_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                attempt = read_json(path)
            except ValueError:
                continue
            if not is_scored_report(attempt):
                continue
            score = attempt.get("ielts_score") or {}
            pron = attempt.get("pronunciation") or {}
            rows.append(
                {
                    "id": attempt.get("id"),
                    "timestamp": attempt.get("timestamp"),
                    "display_time": local_timestamp(str(attempt.get("timestamp") or "")),
                    "part": attempt.get("part"),
                    "mode": attempt.get("mode"),
                    "title": attempt.get("title") or short_question(str(attempt.get("question") or "")),
                    "question": short_question(str(attempt.get("question") or "")),
                    "overall_band": score.get("overall_band"),
                    "pronunciation_status": pron.get("status", "unknown"),
                    "turn_count": len(attempt.get("turns") or []),
                    "completed_turns": len([t for t in attempt.get("turns") or [] if t.get("status") == "completed"]),
                }
            )
        return rows


def is_scored_report(attempt: dict[str, Any]) -> bool:
    score = attempt.get("ielts_score")
    if attempt.get("status") != "scored" or not isinstance(score, dict):
        return False
    overall_band = score.get("overall_band")
    if not isinstance(overall_band, (int, float)) or isinstance(overall_band, bool):
        return False
    if not math.isfinite(float(overall_band)):
        return False
    turns = attempt.get("turns")
    return isinstance(turns, list) and bool(turns) and all(turn.get("status") == "completed" for turn in turns)


def timers_for_part(part: str) -> dict[str, int]:
    if part == "p1":
        return {"prep_seconds": 3, "speak_seconds": 35}
    if part == "p2":
        return {"prep_seconds": 60, "speak_seconds": 120}
    if part == "p3":
        return {"prep_seconds": 7, "speak_seconds": 75}
    return {"prep_seconds": 3, "speak_seconds": 60}


def cue_to_text(topic: dict[str, Any]) -> str:
    bullets = "\n".join(f"- {item}" for item in topic.get("bullets", []))
    return f"{topic.get('title', '')}\n\nYou should say:\n{bullets}\n\n{topic.get('rounding', '')}".strip()


def cue_examiner_text(topic: dict[str, Any]) -> str:
    return (
        "I'm going to give you a topic and I would like you to talk about it for one to two minutes. "
        "You have one minute to think about what you are going to say. "
        "You can make some notes if you wish."
    )


def fallback_p3(theme: str, prior_answer: str = "", count: int = P3_MAIN_COUNT) -> dict[str, Any]:
    label = theme.replace("_", " ").strip() or "this topic"
    questions = [
        f"Why do people have different opinions about {label}?",
        f"How has {label} changed in your country in recent years?",
        f"Do you think {label} will become more important in the future?",
        f"What problems can {label} create for ordinary people?",
        f"How should governments or schools respond to changes in {label}?",
    ]
    follow_up = "Could you give a specific example to support that view?"
    if len(prior_answer.split()) > 40:
        follow_up = "What might be the opposite argument, and why might some people agree with it?"
    return {"questions": questions[:count], "follow_up": follow_up, "backend": "fallback"}


def p3_with_claude(theme: str, prior_answer: str) -> dict[str, Any]:
    if os.environ.get("IELTS_WEB_DISABLE_CLAUDE") == "1":
        raise RuntimeError("claude generation disabled by IELTS_WEB_DISABLE_CLAUDE=1")
    claude = shutil.which("claude")
    if not claude:
        raise RuntimeError("claude CLI not found")
    prompt = (
        "Return JSON only with keys questions (array of 5 IELTS Part 3 questions) "
        "and follow_up (one examiner follow-up). "
        f"Theme: {theme}\nCandidate answer: {prior_answer}\n"
    )
    result = subprocess.run(
        [claude, "--print"],
        input=prompt,
        text=True,
        capture_output=True,
        timeout=25,
        check=True,
    )
    payload = extract_json_object(result.stdout)
    questions = [str(item) for item in payload.get("questions", []) if str(item).strip()]
    if len(questions) < 5:
        raise RuntimeError("claude returned fewer than five questions")
    return {"questions": questions[:5], "follow_up": str(payload.get("follow_up", "")), "backend": "claude"}


def generate_p3_plan(theme: str, prior_answer: str, source: str) -> dict[str, Any]:
    try:
        result = p3_with_claude(theme, prior_answer)
        status = "generated"
    except Exception as exc:  # noqa: BLE001 - dynamic P3 must degrade cleanly
        result = fallback_p3(theme, prior_answer, P3_MAIN_COUNT)
        status = f"fallback: {exc}"
    questions = [clean_report_text(item) for item in result.get("questions", [])]
    questions = [item for item in questions if item][:P3_MAIN_COUNT]
    fallback_questions = fallback_p3(theme, prior_answer, P3_MAIN_COUNT)["questions"]
    while len(questions) < P3_MAIN_COUNT:
        questions.append(fallback_questions[len(questions)])
    follow_up = clean_report_text(str(result.get("follow_up") or "")) or fallback_p3(theme, prior_answer)["follow_up"]
    return {
        "questions": questions,
        "follow_up": follow_up,
        "backend": result.get("backend", "fallback"),
        "status": status,
        "source": source,
        "theme": theme,
    }


def volcengine_tts(state: AppState, text: str, voice: str = "en_male_adam", role: str = "model", cache_key: str | None = None) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {"provider": "none", "status": "empty_text", "audio_url": None, "message": "No text to synthesize."}
    if os.environ.get("IELTS_WEB_DISABLE_VOLCENGINE_TTS") == "1":
        return {"provider": "browser", "status": "fallback", "audio_url": None, "message": "VolcEngine TTS disabled; use browser fallback."}
    folder = state.examiner_audio_dir if role == "examiner" else state.model_audio_dir
    key = safe_slug(cache_key or f"{role}_{uuid.uuid4().hex}")
    audio_path = folder / f"{key}.mp3"
    if audio_path.exists():
        return {
            "provider": "volcengine",
            "status": "cached",
            "audio_url": f"/api/tts-audio/{role}/{audio_path.name}",
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
        with urllib.request.urlopen(request, timeout=4) as response:  # noqa: S310 - public TTS endpoint, server side only
            data = json.loads(response.read().decode("utf-8"))
        encoded = data.get("audio", {}).get("data")
        if not encoded:
            raise ValueError(f"VolcEngine TTS returned no audio: {data}")
        audio_path.write_bytes(base64.b64decode(encoded))
        return {
            "provider": "volcengine",
            "status": "ready",
            "audio_url": f"/api/tts-audio/{role}/{audio_path.name}",
            "path": str(audio_path),
            "content_type": "audio/mpeg",
        }
    except Exception as exc:  # noqa: BLE001 - TTS must degrade cleanly
        return {
            "provider": "browser",
            "status": "fallback",
            "audio_url": None,
            "message": f"VolcEngine TTS unavailable; use browser fallback: {exc}",
        }


def create_turn(
    state: AppState,
    attempt_id: str,
    part: str,
    index: int,
    total: int,
    question: str,
    prompt: dict[str, Any] | None = None,
    cue_card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    turn_id = f"t{index + 1}"
    examiner_text = cue_examiner_text(cue_card) if part == "p2" and cue_card else question
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
        "timers": timers_for_part(part),
        "examiner_text": examiner_text,
        "examiner_behavior": examiner_behavior,
        "examiner_tts": {"provider": "volcengine", "status": "pending", "audio_url": None},
        "audio": None,
        "transcript_raw": "",
        "transcript_cleaned": "",
        "transcript_status": "missing",
        "duration_seconds": None,
        "band7_version": "",
        "model_audio": None,
        "upgrade_notes": [],
        "ai_coaching": "",
    }


def ensure_examiner_tts(state: AppState, attempt_id: str, turn: dict[str, Any]) -> None:
    current = turn.get("examiner_tts") or {}
    if current.get("audio_url") or current.get("status") not in (None, "pending"):
        return
    turn["examiner_tts"] = volcengine_tts(
        state,
        str(turn.get("examiner_text") or turn.get("question") or ""),
        role="examiner",
        cache_key=f"{attempt_id}_{turn['id']}_examiner",
    )


def append_p3_turns(
    state: AppState,
    attempt: dict[str, Any],
    theme: str,
    prior_answer: str,
    source: str,
) -> None:
    plan = generate_p3_plan(theme, prior_answer, source)
    start_index = len(attempt.get("turns") or [])
    for main_index, question in enumerate(plan["questions"]):
        main_turn = create_turn(
            state,
            str(attempt["id"]),
            "p3",
            start_index + (main_index * 2),
            start_index + P3_TURN_COUNT,
            question,
            {"theme": theme, "question": question, "role": "main", "source": source},
        )
        follow_up = plan["follow_up"]
        follow_turn = create_turn(
            state,
            str(attempt["id"]),
            "p3",
            start_index + (main_index * 2) + 1,
            start_index + P3_TURN_COUNT,
            follow_up,
            {"theme": theme, "question": follow_up, "role": "follow_up", "after_main": main_index + 1, "source": source},
        )
        attempt["turns"].extend([main_turn, follow_turn])
    for index, turn in enumerate(attempt["turns"]):
        turn["index"] = index
        turn["total"] = len(attempt["turns"])
    attempt["p3_generation_status"] = plan["status"]
    attempt["p3_generation_source"] = plan["source"]
    attempt["p3_generation_backend"] = plan["backend"]
    attempt["p3_theme"] = theme


def adapt_p3_follow_up(state: AppState, attempt: dict[str, Any], completed_turn: dict[str, Any], next_turn: dict[str, Any] | None) -> None:
    if not next_turn or completed_turn.get("part") != "p3" or next_turn.get("part") != "p3":
        return
    if completed_turn.get("prompt", {}).get("role") != "main" or next_turn.get("prompt", {}).get("role") != "follow_up":
        return
    theme = str(completed_turn.get("prompt", {}).get("theme") or attempt.get("p3_theme") or "general speaking")
    prior_answer = str(completed_turn.get("transcript_cleaned") or completed_turn.get("transcript_raw") or "")
    plan = generate_p3_plan(theme, prior_answer, "adaptive_answer")
    follow_up = clean_report_text(str(plan.get("follow_up") or ""))
    if not follow_up:
        return
    next_turn["question"] = follow_up
    next_turn["examiner_text"] = follow_up
    next_turn["prompt"] = {
        **(next_turn.get("prompt") or {}),
        "question": follow_up,
        "source": "adaptive_answer",
        "adapted_from_turn": completed_turn.get("id"),
    }
    next_turn["examiner_tts"] = {"provider": "volcengine", "status": "pending", "audio_url": None}


def build_turns(state: AppState, attempt_id: str, mode: str, payload: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
    sample = state.bank.sample(P1_TURN_COUNT)
    metadata: dict[str, Any] = {}
    if mode == "mock":
        cue = sample["part2"]
        turns = [
            create_turn(state, attempt_id, "p1", index, P1_TURN_COUNT + 1, item["question"], {"topic": item["topic"], "question": item["question"]})
            for index, item in enumerate(sample["part1"])
        ]
        turns.append(create_turn(state, attempt_id, "p2", len(turns), P1_TURN_COUNT + 1, cue_to_text(cue), cue, cue))
        metadata = {
            "p3_generation_status": "pending_after_p2",
            "p3_generation_source": "p2_answer",
            "p3_theme": str(cue.get("p3_theme") or cue.get("title") or "general speaking"),
        }
        return "mock", "Full mock exam", turns, cue, metadata
    if mode == "p1":
        questions = random.sample(state.bank.p1, min(P1_TURN_COUNT, len(state.bank.p1)))
        turns = [
            create_turn(state, attempt_id, "p1", index, len(questions), item["question"], {"topic": item["topic"], "question": item["question"]})
            for index, item in enumerate(questions)
        ]
        return "p1", "Part 1 practice", turns, None, metadata
    if mode == "p2":
        cue = sample["part2"]
        return "p2", str(cue["title"]), [create_turn(state, attempt_id, "p2", 0, 1, cue_to_text(cue), cue, cue)], cue, metadata
    if mode == "p3":
        theme = str(payload.get("theme") or payload.get("topic") or "society and daily life").strip()
        generated = {"id": attempt_id, "turns": []}
        append_p3_turns(state, generated, theme, str(payload.get("prior_answer") or ""), "topic")
        metadata = {
            "p3_generation_status": generated.get("p3_generation_status"),
            "p3_generation_source": generated.get("p3_generation_source"),
            "p3_generation_backend": generated.get("p3_generation_backend"),
            "p3_theme": theme,
        }
        return "p3", f"Part 3 discussion: {theme}", generated["turns"], None, metadata
    raise ValueError(f"Unsupported mode: {mode}")


def prompt_relevance(question: str, transcript: str) -> float:
    if not question.strip() or not transcript.strip():
        return 1.0
    stopwords = {
        "about", "address", "after", "also", "answer", "because", "before", "could",
        "describe", "detail", "does", "doing", "explain", "feel", "felt",
        "give", "happened", "have", "having", "more", "person", "question", "should",
        "someone", "something", "that", "their", "there", "these", "thing", "this",
        "time", "what", "when", "where", "which", "while", "with", "would", "your",
    }
    question_terms = {
        word.lower()
        for word in re.findall(r"[A-Za-z']+", question)
        if len(word) > 3 and word.lower() not in stopwords
    }
    if not question_terms:
        return 1.0
    answer_terms = {word.lower() for word in re.findall(r"[A-Za-z']+", transcript)}
    return len(question_terms & answer_terms) / len(question_terms)


def clean_transcript(transcript: str) -> dict[str, Any]:
    text = re.sub(r"\s+", " ", transcript).strip()
    notes = []
    if not text:
        return {"text": "", "notes": ["Recording exists, but browser dictation did not capture a transcript."]}
    if text and text[-1] not in ".!?":
        text += "."
    suspicious = re.findall(r"\b[a-zA-Z]{1,2}\b", text)
    if len(suspicious) >= 4:
        notes.append("Short fragments suggest possible browser dictation noise.")
    return {"text": text, "notes": notes}


def clean_band7_output(value: str) -> str:
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
        stripped = re.sub(r"^\s*(?:band\s*7\s*(?:spoken\s*)?(?:version|answer)?|answer|model answer)\s*:\s*", "", stripped, flags=re.I)
        if stripped:
            kept.append(stripped)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def clean_report_text(value: str) -> str:
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


def plausible_spoken_answer(value: str) -> bool:
    text = clean_band7_output(value)
    words = re.findall(r"[A-Za-z']+", text)
    if len(words) < 12:
        return False
    lowered = text.lower()
    bad_markers = ("json", "requirements", "acceptance criteria", "here is", "i cannot", "as an ai")
    return not any(marker in lowered[:220] for marker in bad_markers)


def pronunciation_from_azure(audio_path: Path, transcript: str) -> dict[str, Any]:
    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        return {
            "provider": "azure",
            "status": "not_configured",
            "pron_score": None,
            "accuracy": None,
            "fluency": None,
            "prosody": None,
            "issues": [],
            "message": "Azure Speech key/region is not configured; pronunciation is not assessed.",
        }
    assessment_path = audio_path
    temp_wav: Path | None = None
    if audio_path.suffix.lower() not in {".wav"}:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return {
                "provider": "azure",
                "status": "audio_conversion_missing",
                "pron_score": None,
                "accuracy": None,
                "fluency": None,
                "prosody": None,
                "issues": [],
                "message": "Azure is configured, but ffmpeg is required to convert browser WebM audio to WAV.",
            }
        temp_wav = audio_path.with_suffix(".azure.wav")
        try:
            subprocess.run(
                [ffmpeg, "-y", "-i", str(audio_path), "-ac", "1", "-ar", "16000", str(temp_wav)],
                text=True,
                capture_output=True,
                timeout=20,
                check=True,
            )
            assessment_path = temp_wav
        except Exception as exc:  # noqa: BLE001
            return {
                "provider": "azure",
                "status": "audio_conversion_failed",
                "pron_score": None,
                "accuracy": None,
                "fluency": None,
                "prosody": None,
                "issues": [],
                "message": f"Could not convert browser audio for Azure pronunciation assessment: {exc}",
            }
    try:
        import azure.cognitiveservices.speech as speechsdk  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {
            "provider": "azure",
            "status": "sdk_missing",
            "pron_score": None,
            "accuracy": None,
            "fluency": None,
            "prosody": None,
            "issues": [],
            "message": f"Azure Speech SDK is not installed: {exc}",
        }
    try:
        speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
        speech_config.speech_recognition_language = "en-US"
        audio_config = speechsdk.audio.AudioConfig(filename=str(assessment_path))
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        pron_config = speechsdk.PronunciationAssessmentConfig(
            reference_text=transcript or "",
            grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
            granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
            enable_miscue=False,
        )
        pron_config.enable_prosody_assessment()
        pron_config.apply_to(recognizer)
        result = recognizer.recognize_once()
        raw = result.properties.get(speechsdk.PropertyId.SpeechServiceResponse_JsonResult)
        payload = json.loads(raw) if raw else {}
        assessment = payload.get("NBest", [{}])[0].get("PronunciationAssessment", {})
        words = payload.get("NBest", [{}])[0].get("Words", [])[:8]
        issues = [
            {
                "word": item.get("Word"),
                "accuracy": item.get("PronunciationAssessment", {}).get("AccuracyScore"),
                "error_type": item.get("PronunciationAssessment", {}).get("ErrorType"),
            }
            for item in words
            if item.get("PronunciationAssessment", {}).get("ErrorType") not in (None, "None")
        ]
        return {
            "provider": "azure",
            "status": "assessed",
            "pron_score": assessment.get("PronScore"),
            "accuracy": assessment.get("AccuracyScore"),
            "fluency": assessment.get("FluencyScore"),
            "prosody": assessment.get("ProsodyScore"),
            "issues": issues,
            "message": "Pronunciation assessed with Azure Speech.",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "provider": "azure",
            "status": "failed",
            "pron_score": None,
            "accuracy": None,
            "fluency": None,
            "prosody": None,
            "issues": [],
            "message": f"Azure pronunciation assessment failed: {exc}",
        }
    finally:
        if temp_wav:
            temp_wav.unlink(missing_ok=True)


def aggregate_pronunciation(turns: list[dict[str, Any]]) -> dict[str, Any]:
    assessments = [turn.get("pronunciation") or {} for turn in turns]
    scored = [item for item in assessments if item.get("status") == "assessed" and item.get("pron_score") is not None]
    if scored:
        return {
            "provider": "azure",
            "status": "assessed",
            "pron_score": round(sum(float(item["pron_score"]) for item in scored) / len(scored), 1),
            "accuracy": round(sum(float(item.get("accuracy") or 0) for item in scored) / len(scored), 1),
            "fluency": round(sum(float(item.get("fluency") or 0) for item in scored) / len(scored), 1),
            "prosody": round(sum(float(item.get("prosody") or 0) for item in scored) / len(scored), 1),
            "issues": [issue for item in scored for issue in item.get("issues", [])][:12],
            "message": "Pronunciation aggregated from turn-level Azure assessments.",
        }
    for item in assessments:
        if item.get("status") and item.get("status") != "pending":
            return item
    return {
        "provider": "azure",
        "status": "missing_audio",
        "pron_score": None,
        "accuracy": None,
        "fluency": None,
        "prosody": None,
        "issues": [],
        "message": "No completed turn audio was available for pronunciation assessment.",
    }


def base_criteria(band: float, label: str, transcript: str) -> dict[str, Any]:
    words = len(re.findall(r"[A-Za-z']+", transcript))
    if words < 20:
        return {
            "band": band,
            "strengths": [],
            "problems": ["The speaking sample is too short or the transcript is incomplete."],
            "suggestion": "Answer each question with a clear reason and one concrete detail.",
        }
    if band < 5.5:
        problems = ["Ideas are understandable but underdeveloped or loosely connected."]
        suggestion = "Use a clearer first point, contrast, example, and conclusion."
    else:
        problems = ["The response would benefit from more precise examples and smoother linking."]
        suggestion = "Extend each answer with a specific detail and a more natural closing sentence."
    return {
        "band": band,
        "strengths": [f"Some {label.lower()} control is visible across the completed answers."],
        "problems": problems,
        "suggestion": suggestion,
    }


def heuristic_score(transcript: str, reason: str, question: str = "") -> dict[str, Any]:
    words = re.findall(r"[A-Za-z']+", transcript)
    unique_ratio = len(set(word.lower() for word in words)) / max(1, len(words))
    if not words:
        base = 0.0
    elif len(words) >= 260:
        base = 6.5
    elif len(words) >= 150:
        base = 6.0
    elif len(words) >= 70:
        base = 5.5
    elif len(words) < 20:
        base = 4.0
    else:
        base = 4.5
    lexical = base + (0.5 if unique_ratio > 0.62 and len(words) >= 50 else 0.0)
    scores: dict[str, Any] = {
        "fluency_coherence": clamp_band(base),
        "lexical_resource": clamp_band(lexical),
        "grammatical_range": clamp_band(base),
        "pronunciation_estimate": None,
    }
    scores["overall_band"] = rounded_overall(scores)
    feedback = f"Content score uses fallback estimate: {reason}. Record clear, relevant English answers for a more useful assessment."
    result = {**scores, "feedback": feedback, "backend": "heuristic", "word_count": len(words)}
    return cap_off_topic_score(result, question, transcript)


def score_with_codex(transcript: str, data_dir: Path, question: str = "") -> dict[str, Any]:
    if os.environ.get("IELTS_WEB_DISABLE_CODEX") == "1":
        raise RuntimeError("codex scoring disabled by IELTS_WEB_DISABLE_CODEX=1")
    codex = shutil.which("codex") or "/opt/homebrew/bin/codex"
    if not shutil.which(codex) and not Path(codex).exists():
        raise RuntimeError("codex CLI not found")
    prompt_path = data_dir / "prompts" / "scorer_system.md"
    prompt = (
        prompt_path.read_text(encoding="utf-8")
        + "\n\nReturn JSON only with numeric keys fluency_coherence, lexical_resource, "
        "grammatical_range, overall_band, and string key feedback. Do not invent a "
        "pronunciation score from text. Score the whole completed speaking section.\n\nPrompt(s):\n"
        + (question.strip() or "(not provided)")
        + "\n\nTranscript:\n"
        + transcript
        + "\n"
    )
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(prompt)
        temp_name = handle.name
    try:
        result = subprocess.run(
            [codex, "exec"],
            input=Path(temp_name).read_text(encoding="utf-8"),
            text=True,
            capture_output=True,
            timeout=45,
            check=True,
        )
    finally:
        Path(temp_name).unlink(missing_ok=True)
    payload = extract_json_object(result.stdout)
    scores: dict[str, Any] = {
        "fluency_coherence": clamp_band(payload.get("fluency_coherence")),
        "lexical_resource": clamp_band(payload.get("lexical_resource")),
        "grammatical_range": clamp_band(payload.get("grammatical_range")),
        "pronunciation_estimate": None,
    }
    scores["overall_band"] = rounded_overall(scores)
    result_payload = {**scores, "feedback": str(payload.get("feedback", "")), "backend": "codex"}
    return cap_off_topic_score(result_payload, question, transcript)


def cap_off_topic_score(scores: dict[str, Any], question: str, transcript: str) -> dict[str, Any]:
    relevance = prompt_relevance(question, transcript)
    feedback = str(scores.get("feedback", ""))
    model_flagged = any(
        marker in feedback.lower()
        for marker in ("off-topic", "does not address", "task relevance", "not address the")
    )
    if relevance >= 0.20 and not model_flagged:
        scores["task_relevance"] = round(relevance, 2)
        return scores
    scores["fluency_coherence"] = min(float(scores.get("fluency_coherence", 0)), 4.0)
    scores["overall_band"] = min(float(scores.get("overall_band", 0)), 4.5)
    if "off-topic" not in feedback.lower():
        feedback = "The response appears off-topic for the prompt. " + feedback
    scores["feedback"] = feedback.strip()
    scores["task_relevance"] = round(relevance, 2)
    return scores


def model_answer_with_codex(attempt: dict[str, Any], transcript: str) -> str:
    if os.environ.get("IELTS_WEB_DISABLE_CODEX") == "1":
        raise RuntimeError("codex model-answer generation disabled")
    codex = shutil.which("codex") or "/opt/homebrew/bin/codex"
    if not shutil.which(codex) and not Path(codex).exists():
        raise RuntimeError("codex CLI not found")
    prompt = (
        "Write a natural IELTS Speaking Band 7 spoken version. Preserve the candidate's core ideas, "
        "but improve cohesion, vocabulary, and grammar. Do not include the original question or cue-card bullets. "
        "Return only the answer text.\n\n"
        f"Section: {attempt.get('mode')}\nQuestions:\n{questions_text(attempt)}\n\nCandidate transcript:\n{transcript}\n"
    )
    result = subprocess.run([codex, "exec"], input=prompt, text=True, capture_output=True, timeout=45, check=True)
    cleaned = clean_band7_output(result.stdout)
    if not plausible_spoken_answer(cleaned):
        raise RuntimeError("codex model answer was not a plausible spoken answer")
    return cleaned


def questions_text(attempt: dict[str, Any]) -> str:
    return "\n".join(f"{turn['index'] + 1}. {turn['question']}" for turn in attempt.get("turns", []))


def build_band7_version(attempt: dict[str, Any], transcript: str) -> str:
    if not transcript:
        return "Record a full answer first. A Band 7 spoken version will appear after the system has a transcript to work from."
    try:
        generated = model_answer_with_codex(attempt, transcript)
        if plausible_spoken_answer(generated):
            return generated
    except Exception:
        pass
    topic_hint = "the topic"
    for turn in attempt.get("turns", []):
        words = re.findall(r"[A-Za-z']+", str(turn.get("question") or ""))
        if words:
            topic_hint = " ".join(words[:6]).lower()
            break
    return (
        f"I think {topic_hint} can be understood in different ways, depending on people's experiences. "
        "In my case, the most important point is to give a clear reason and connect it with a real example. "
        "At the same time, there may be another side to the issue, so I would explain both views before giving my own opinion. "
        "Overall, I would try to answer directly, develop the idea naturally, and finish with a clear conclusion."
    )


def build_turn_band7_fallback(turn: dict[str, Any], transcript: str) -> str:
    if not transcript:
        return "A complete transcript was not captured, so this model answer is a general spoken example for the same question."
    question = str(turn.get("question") or "this topic")
    words = [
        word.lower()
        for word in re.findall(r"[A-Za-z']+", question)
        if len(word) > 3 and word.lower() not in {"describe", "should", "would", "could", "about", "your"}
    ]
    topic_hint = " ".join(words[:5]) or "this topic"
    return (
        f"I'd say {topic_hint} is something I can talk about from my own experience. "
        "The main reason is that it connects with my daily life, so I can explain it quite naturally. "
        "For example, I would give one specific situation, describe what happened, and then say why it mattered to me. "
        "Overall, I think a clear answer with one concrete example sounds more fluent and convincing."
    )


def build_turn_band7(state: AppState, attempt: dict[str, Any], turn: dict[str, Any]) -> None:
    transcript = str(turn.get("transcript_cleaned") or turn.get("transcript_raw") or "").strip()
    band7 = ""
    if transcript:
        try:
            band7 = model_answer_with_codex({**attempt, "turns": [turn]}, transcript)
        except Exception:
            band7 = ""
    if not plausible_spoken_answer(band7):
        band7 = build_turn_band7_fallback(turn, transcript)
    turn["band7_version"] = clean_report_text(band7) or build_turn_band7_fallback(turn, transcript)
    turn["model_audio"] = volcengine_tts(state, turn["band7_version"], role="model", cache_key=f"{attempt['id']}_{turn['id']}_band7")
    turn["upgrade_notes"] = build_upgrade_notes(transcript)
    turn["ai_coaching"] = build_ai_coaching(turn, transcript)


def build_upgrade_notes(transcript: str) -> list[dict[str, str]]:
    notes = [
        {
            "original_problem": "Answers may sound like separate fragments rather than one developed response.",
            "band7_change": "Grouped ideas with a clearer opening, support, contrast, and conclusion.",
            "criterion": "Fluency & Coherence",
        },
        {
            "original_problem": "Topic words may repeat too often.",
            "band7_change": "Used broader phrasing and more natural spoken collocations.",
            "criterion": "Lexical Resource",
        },
        {
            "original_problem": "Sentence patterns may be simple or unfinished.",
            "band7_change": "Added controlled complex sentences and clearer reference.",
            "criterion": "Grammar",
        },
    ]
    if len(transcript.split()) < 50:
        notes.insert(
            0,
            {
                "original_problem": "The completed section is too short for a stable high-band answer.",
                "band7_change": "Expanded the response into fuller spoken development.",
                "criterion": "Development",
            },
        )
    return notes


def build_ai_coaching(turn: dict[str, Any], transcript: str) -> str:
    question = short_question(str(turn.get("question") or "this question"), 120)
    if len(transcript.split()) < 35:
        coaching = (
            f"For this question, focus first on building a fuller answer: give a direct opinion, one clear reason, "
            f"and a concrete example before you close. That will make your response to \"{question}\" sound less fragmented."
        )
    else:
        coaching = (
            f"Your answer has enough material to develop. For \"{question}\", tighten the opening sentence, connect the example "
            "more explicitly to the question, and add one contrast or consequence so the answer sounds more like Band 7 speech."
        )
    return clean_report_text(coaching)


def build_detailed_report(
    state: AppState,
    attempt: dict[str, Any],
    score: dict[str, Any],
    pronunciation: dict[str, Any],
    transcript: str,
) -> dict[str, Any]:
    pron_band = None
    if pronunciation.get("status") == "assessed" and pronunciation.get("pron_score") is not None:
        pron_band = clamp_band(float(pronunciation["pron_score"]) / 100.0 * 9.0)
    score["pronunciation_estimate"] = pron_band
    score["overall_band"] = rounded_overall(score)
    summary = clean_report_text(str(score.get("feedback") or "")) or "Score generated from the completed speaking section."
    band7 = clean_report_text(build_band7_version(attempt, transcript))
    model_tts = volcengine_tts(state, band7, role="model", cache_key=f"{attempt['id']}_band7")
    return {
        "feedback_summary": summary,
        "ielts_score": score,
        "pronunciation": pronunciation,
        "criteria_feedback": {
            "fluency_coherence": base_criteria(score["fluency_coherence"], "fluency and coherence", transcript),
            "lexical_resource": base_criteria(score["lexical_resource"], "lexical resource", transcript),
            "grammatical_range_accuracy": base_criteria(score["grammatical_range"], "grammar", transcript),
            "pronunciation": {
                "band": pron_band,
                "strengths": [] if pron_band is None else ["Pronunciation was assessed from uploaded turn audio."],
                "problems": pronunciation.get("issues", []) or [pronunciation.get("message", "Pronunciation not assessed.")],
                "suggestion": "Configure Azure Speech for real pronunciation scoring." if pron_band is None else "Review low-accuracy words and repeat the model answer aloud.",
            },
        },
        "band7_version": band7 or build_band7_version(attempt, transcript),
        "model_audio": model_tts,
        "upgrade_notes": build_upgrade_notes(transcript),
        "ai_coaching": clean_report_text("Focus on answering directly, extending each point with a concrete example, and linking ideas naturally across the full section."),
    }


class IELTSHandler(SimpleHTTPRequestHandler):
    state: AppState

    def translate_path(self, path: str) -> str:
        path = urlparse(path).path
        if path == "/":
            path = "/index.html"
        return str(STATIC_DIR / unquote(path).lstrip("/"))

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[ielts-web] " + fmt % args + "\n")

    def do_GET(self) -> None:
        try:
            path = urlparse(self.path).path
            if path == "/api/question-bank/summary":
                self.send_json(self.state.bank.summary())
                return
            if path == "/api/history":
                self.send_json({"items": self.state.history()})
                return
            match = re.fullmatch(r"/api/history/([^/]+)", path)
            if match:
                self.send_json(self.state.load_report_attempt(match.group(1)))
                return
            match = re.fullmatch(r"/api/audio/([^/]+)/([^/]+)/(candidate|examiner)", path)
            if match:
                self.send_turn_audio(match.group(1), match.group(2), match.group(3))
                return
            match = re.fullmatch(r"/api/audio/([^/]+)/(candidate|model)", path)
            if match:
                self.send_legacy_audio(match.group(1), match.group(2))
                return
            match = re.fullmatch(r"/api/tts-audio/(examiner|model)/([^/]+)", path)
            if match:
                self.send_tts_audio(match.group(1), match.group(2))
                return
            if path == "/api/reports/latest":
                self.send_json(self.state.latest_report or {"report": None})
                return
            if path.startswith("/api/"):
                self.send_error_json(HTTPStatus.NOT_FOUND, "Unknown API endpoint")
                return
            super().do_GET()
        except Exception as exc:  # noqa: BLE001
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path
            turn_audio = re.fullmatch(r"/api/attempts/([^/]+)/turns/([^/]+)/audio", path)
            if turn_audio:
                self.handle_turn_audio_upload(turn_audio.group(1), turn_audio.group(2))
                return
            legacy_audio = re.fullmatch(r"/api/attempts/([^/]+)/audio", path)
            if legacy_audio:
                attempt = self.state.load_attempt(legacy_audio.group(1))
                self.handle_turn_audio_upload(legacy_audio.group(1), attempt["turns"][0]["id"])
                return
            payload = self.read_json_body()
            if path == "/api/question-bank/sample":
                self.send_json(self.state.bank.sample(int(payload.get("p1_count", 5))))
            elif path == "/api/session/start":
                sample = self.state.bank.sample(int(payload.get("p1_count", 5)))
                self.send_json({"session_id": uuid.uuid4().hex, "mode": payload.get("mode", "full"), **sample})
            elif path == "/api/score":
                self.handle_legacy_score(payload)
            elif path == "/api/tts":
                self.handle_tts(payload)
            elif path == "/api/attempts/start":
                self.handle_attempt_start(payload)
            else:
                turn_complete = re.fullmatch(r"/api/attempts/([^/]+)/turns/([^/]+)/complete", path)
                score_match = re.fullmatch(r"/api/attempts/([^/]+)/score", path)
                abort_match = re.fullmatch(r"/api/attempts/([^/]+)/abort", path)
                if turn_complete:
                    self.handle_turn_complete(turn_complete.group(1), turn_complete.group(2), payload)
                elif score_match:
                    self.handle_attempt_score(score_match.group(1), payload)
                elif abort_match:
                    self.handle_attempt_abort(abort_match.group(1))
                elif path == "/api/p3/questions" or path == "/api/p3/follow-up":
                    self.handle_p3(payload)
                else:
                    self.send_error_json(HTTPStatus.NOT_FOUND, "Unknown API endpoint")
        except Exception as exc:  # noqa: BLE001
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def handle_tts(self, payload: dict[str, Any]) -> None:
        self.send_json(
            volcengine_tts(
                self.state,
                str(payload.get("text") or ""),
                str(payload.get("voice") or "en_male_adam"),
                str(payload.get("role") or "model"),
            )
        )

    def handle_attempt_start(self, payload: dict[str, Any]) -> None:
        mode = str(payload.get("mode") or payload.get("part") or "p1").lower()
        if mode == "full":
            mode = "mock"
        attempt_id = uuid.uuid4().hex
        part, title, turns, cue_card, metadata = build_turns(self.state, attempt_id, mode, payload)
        attempt = {
            "id": attempt_id,
            "timestamp": now_iso(),
            "status": "started",
            "mode": mode,
            "part": part,
            "title": title,
            "question": turns[0]["question"] if turns else "",
            "cue_card": cue_card,
            "turns": turns,
            "current_turn": turns[0]["id"] if turns else None,
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
        if attempt["turns"]:
            ensure_examiner_tts(self.state, attempt_id, attempt["turns"][0])
        self.state.save_attempt(attempt)
        self.send_json(attempt)

    def handle_turn_audio_upload(self, attempt_id: str, turn_id: str) -> None:
        content_type = self.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip()
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise ValueError("Audio upload is empty")
        if content_length > MAX_AUDIO_BYTES:
            raise ValueError("Audio upload exceeds 25 MB")
        if not (content_type.startswith("audio/") or content_type == "application/octet-stream"):
            raise ValueError(f"Unsupported audio content type: {content_type}")
        attempt = self.state.load_attempt(attempt_id)
        if attempt.get("status") == "aborted":
            raise ValueError("Aborted attempts cannot accept audio.")
        turn = self.find_turn(attempt, turn_id)
        extension = mimetypes.guess_extension(content_type) or ".webm"
        if extension == ".weba":
            extension = ".webm"
        audio_path = self.state.audio_dir / f"{safe_slug(attempt_id)}_{safe_slug(turn_id)}{extension}"
        with audio_path.open("wb") as handle:
            handle.write(self.rfile.read(content_length))
        turn["audio"] = {
            "path": str(audio_path),
            "content_type": content_type,
            "bytes": content_length,
            "duration_seconds": None,
            "url": f"/api/audio/{attempt_id}/{turn_id}/candidate",
        }
        turn["status"] = "audio_uploaded"
        self.state.save_attempt(attempt)
        self.send_json({"ok": True, "audio": turn["audio"]})

    def handle_turn_complete(self, attempt_id: str, turn_id: str, payload: dict[str, Any]) -> None:
        attempt = self.state.load_attempt(attempt_id)
        if attempt.get("status") == "aborted":
            raise ValueError("Aborted attempts cannot be completed.")
        turn = self.find_turn(attempt, turn_id)
        transcript = str(payload.get("transcript_raw") or payload.get("transcript") or "").strip()
        requested_status = str(payload.get("transcript_status") or "").strip()
        transcript_status = requested_status if requested_status in {"captured", "interim_fallback", "missing"} else ""
        if not transcript_status:
            transcript_status = "captured" if transcript else "missing"
        if not transcript:
            transcript_status = "missing"
        cleaned = clean_transcript(transcript)
        turn["transcript_raw"] = transcript
        turn["transcript_cleaned"] = cleaned["text"]
        turn["transcript_status"] = transcript_status
        turn["cleaning_notes"] = cleaned["notes"]
        turn["duration_seconds"] = payload.get("duration_seconds")
        audio_path = Path((turn.get("audio") or {}).get("path", ""))
        turn["pronunciation"] = pronunciation_from_azure(audio_path, transcript) if audio_path.exists() else {
            "provider": "azure",
            "status": "missing_audio",
            "pron_score": None,
            "accuracy": None,
            "fluency": None,
            "prosody": None,
            "issues": [],
            "message": "No candidate audio was uploaded; pronunciation is not assessed.",
        }
        turn["status"] = "completed"
        if (
            attempt.get("mode") == "mock"
            and turn.get("part") == "p2"
            and attempt.get("p3_generation_status") == "pending_after_p2"
        ):
            cue = attempt.get("cue_card") or {}
            theme = str(cue.get("p3_theme") or cue.get("title") or attempt.get("p3_theme") or "general speaking")
            prior_answer = turn.get("transcript_cleaned") or turn.get("transcript_raw") or ""
            append_p3_turns(self.state, attempt, theme, str(prior_answer), "p2_answer")
        next_turn = self.next_turn(attempt, turn_id)
        adapt_p3_follow_up(self.state, attempt, turn, next_turn)
        if next_turn:
            ensure_examiner_tts(self.state, attempt_id, next_turn)
        attempt["current_turn"] = next_turn["id"] if next_turn else None
        if next_turn is None:
            attempt["status"] = "ready_to_score"
        self.state.save_attempt(attempt)
        self.send_json({"attempt": attempt, "turn": turn, "next_turn": next_turn})

    def handle_attempt_abort(self, attempt_id: str) -> None:
        attempt = self.state.load_attempt(attempt_id)
        if attempt.get("status") == "scored":
            raise ValueError("Scored attempts cannot be aborted.")
        if attempt.get("status") != "aborted":
            attempt["status"] = "aborted"
            attempt["aborted_at"] = now_iso()
            attempt["current_turn"] = None
            self.state.save_attempt(attempt)
        self.send_json(attempt)

    def handle_attempt_score(self, attempt_id: str, payload: dict[str, Any]) -> None:
        attempt = self.state.load_attempt(attempt_id)
        if attempt.get("status") == "aborted":
            raise ValueError("Aborted attempts cannot be scored.")
        completed = [turn for turn in attempt.get("turns", []) if turn.get("status") == "completed"]
        if len(completed) != len(attempt.get("turns", [])):
            raise ValueError("Complete all speaking turns before generating the section report.")
        transcript = "\n".join(
            f"Q{turn['index'] + 1}: {turn['question']}\nA: {turn.get('transcript_cleaned') or turn.get('transcript_raw') or ''}"
            for turn in completed
        )
        prompt_text = questions_text(attempt)
        pronunciation = aggregate_pronunciation(completed)
        try:
            score = score_with_codex(transcript, self.state.data_dir, prompt_text)
        except Exception as exc:  # noqa: BLE001
            score = heuristic_score(transcript, str(exc), prompt_text)
        detailed = build_detailed_report(self.state, attempt, score, pronunciation, transcript)
        attempt.update(detailed)
        for turn in completed:
            build_turn_band7(self.state, attempt, turn)
        attempt["transcript_cleaned"] = transcript
        attempt["status"] = "scored"
        self.state.save_attempt(attempt)
        self.send_json(attempt)

    def handle_legacy_score(self, payload: dict[str, Any]) -> None:
        transcript = str(payload.get("transcript") or "").strip()
        question = str(payload.get("question") or "").strip()
        if not transcript:
            raise ValueError("Missing transcript")
        try:
            score = score_with_codex(transcript, self.state.data_dir, question)
        except Exception as exc:  # noqa: BLE001
            score = heuristic_score(transcript, str(exc), question)
        report = {
            "timestamp": now_iso(),
            "candidate": str(payload.get("candidate") or "web-user"),
            "mode": str(payload.get("mode") or "practice"),
            "parts": [{"part": str(payload.get("part") or "unknown"), "question": payload.get("question"), "transcript": transcript, "score": score}],
            "overall": {"band": score["overall_band"]},
        }
        self.state.latest_report = report
        self.send_json({"score": score, "report": report, "report_path": ""})

    def handle_p3(self, payload: dict[str, Any]) -> None:
        theme = str(payload.get("theme") or "general speaking")
        prior_answer = str(payload.get("prior_answer") or "")
        try:
            result = p3_with_claude(theme, prior_answer)
        except Exception:
            result = fallback_p3(theme, prior_answer)
        self.send_json(result)

    def find_turn(self, attempt: dict[str, Any], turn_id: str) -> dict[str, Any]:
        for turn in attempt.get("turns", []):
            if turn.get("id") == turn_id:
                return turn
        raise FileNotFoundError(f"Turn not found: {turn_id}")

    def next_turn(self, attempt: dict[str, Any], turn_id: str) -> dict[str, Any] | None:
        turns = attempt.get("turns", [])
        for index, turn in enumerate(turns):
            if turn.get("id") == turn_id:
                return turns[index + 1] if index + 1 < len(turns) else None
        return None

    def send_turn_audio(self, attempt_id: str, turn_id: str, kind: str) -> None:
        attempt = self.state.load_attempt(attempt_id)
        turn = self.find_turn(attempt, turn_id)
        if kind == "candidate":
            audio = turn.get("audio") or {}
            self.send_file_audio(Path(str(audio.get("path") or "")), str(audio.get("content_type") or ""))
            return
        audio = turn.get("examiner_tts") or {}
        path = Path(str(audio.get("path") or ""))
        if path.exists():
            self.send_file_audio(path, str(audio.get("content_type") or "audio/mpeg"))
            return
        self.send_error_json(HTTPStatus.NOT_FOUND, "Examiner audio not available")

    def send_legacy_audio(self, attempt_id: str, kind: str) -> None:
        attempt = self.state.load_attempt(attempt_id)
        if kind == "model":
            audio = attempt.get("model_audio") or {}
            self.send_file_audio(Path(str(audio.get("path") or "")), str(audio.get("content_type") or "audio/mpeg"))
            return
        first = next((turn for turn in attempt.get("turns", []) if (turn.get("audio") or {}).get("path")), None)
        if not first:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Candidate audio not available")
            return
        audio = first.get("audio") or {}
        self.send_file_audio(Path(str(audio.get("path") or "")), str(audio.get("content_type") or ""))

    def send_tts_audio(self, role: str, filename: str) -> None:
        folder = self.state.examiner_audio_dir if role == "examiner" else self.state.model_audio_dir
        self.send_file_audio(folder / safe_slug(filename), "audio/mpeg")

    def send_file_audio(self, path: Path, content_type: str = "") -> None:
        if not path.exists():
            self.send_error_json(HTTPStatus.NOT_FOUND, "Audio not available")
            return
        resolved_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", resolved_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(size).decode("utf-8") if size else "{}"
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        return payload

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the IELTS Speaking Simulator Web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default=str(ROOT / "data" / "ielts"))
    parser.add_argument("--reports-dir", default=str(ROOT / "reports"))
    args = parser.parse_args()

    IELTSHandler.state = AppState(Path(args.data_dir).resolve(), Path(args.reports_dir).resolve())
    server = ThreadingHTTPServer((args.host, args.port), IELTSHandler)
    print(f"IELTS Web UI: http://{args.host}:{args.port}")
    print("Frontend contains no API keys. Audio, scoring, and model calls stay server-side.")
    print("Set IELTS_WEB_DISABLE_CODEX=1, IELTS_WEB_DISABLE_CLAUDE=1, or IELTS_WEB_DISABLE_VOLCENGINE_TTS=1 to force fallbacks.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down IELTS Web UI")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
