#!/usr/bin/env python3
"""Voice-first web boundary for the IELTS Speaking Simulator.

The browser receives only JSON contracts. Audio, reports, CLI integrations, and
TTS/scoring credentials stay on the server side.

DEPRECATED: This server is no longer the primary runtime backend.
All API endpoints have been migrated to Django (backend_django/).
This file is retained for reference and fallback purposes only.
See backend_django/README.md for the current runtime setup.
"""

from __future__ import annotations

import argparse
import base64
import calendar
import datetime as dt
from collections import Counter
import hashlib
import json
import math
import mimetypes
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_AUDIO_BYTES = 25 * 1024 * 1024
P1_TURN_COUNT = 10
P1_INTRO_QUESTIONS = [
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
P3_MAIN_COUNT = 5
P3_TURN_COUNT = 10
DEFAULT_CANDIDATE = "jasper"
DEFAULT_USER_ID = "local-default"
DEFAULT_FULL_NAME = "LiHua"
DEFAULT_ENGLISH_NAME = "Jasper"
CODEX_REASONING_EFFORT = "low"
MICRO_RMB_PER_RMB = 1_000_000
DEFAULT_INITIAL_GRANT_U = 5 * MICRO_RMB_PER_RMB
DJANGO_BACKEND_URL = os.environ.get("IELTS_DJANGO_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
DJANGO_PROXY_TIMEOUT_SECONDS = float(os.environ.get("IELTS_DJANGO_PROXY_TIMEOUT", "2"))
DJANGO_PROXY_WRITE_FIRST = os.environ.get("IELTS_DJANGO_PROXY_WRITE_FIRST", "1") != "0"
DJANGO_FORCE_WRITING_PROXY = os.environ.get("IELTS_DJANGO_FORCE_WRITING_PROXY", "0") == "1"
DJANGO_PROXY_SPEAKING_RUNTIME = os.environ.get("IELTS_DJANGO_PROXY_SPEAKING_RUNTIME", "0") == "1"
WRITING_TASK_TYPES = {"task1_academic", "task2"}
WRITING_TASK_LABELS = {
    "task1_academic": "Task 1 Academic",
    "task2": "Task 2",
}


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
    ]
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric:
        return 0.0
    average = sum(numeric) / len(numeric)
    return clamp_band(math.floor(average * 2.0 + 0.5) / 2.0)


def band_cap(scores: dict[str, Any], cap: float) -> None:
    for key in ("fluency_coherence", "lexical_resource", "grammatical_range", "overall_band"):
        if isinstance(scores.get(key), (int, float)):
            scores[key] = min(float(scores[key]), cap)


def development_markers(text: str) -> int:
    lowered = text.lower()
    markers = (
        "because",
        "for example",
        "for instance",
        "such as",
        "when ",
        "although",
        "however",
        "whereas",
        "compared",
        "rather than",
        "in contrast",
        "as a result",
        "therefore",
        "so ",
    )
    return sum(1 for marker in markers if marker in lowered)


def generic_template_score(text: str) -> int:
    lowered = text.lower()
    patterns = (
        "it is very important",
        "it is very convenient",
        "it is good for me",
        "it can improve my",
        "in modern society",
        "with the development of",
        "broaden my horizons",
        "learn more knowledge",
        "make me feel relaxed",
        "leave a deep impression",
        "from my perspective",
        "as far as i am concerned",
        "there are many advantages",
    )
    return sum(1 for pattern in patterns if pattern in lowered)


def simple_grammar_ratio(sentences: list[str]) -> float:
    if not sentences:
        return 1.0
    complex_markers = re.compile(
        r"\b(because|although|though|while|whereas|which|who|that|when|if|unless|since|after|before|so that|even though)\b",
        re.I,
    )
    simple_count = sum(1 for sentence in sentences if not complex_markers.search(sentence))
    return simple_count / max(1, len(sentences))


def is_template_like_answer(text: str) -> bool:
    lowered = text.lower()
    repeated_phrases = (
        "from my perspective",
        "as far as i am concerned",
        "there are many advantages",
        "it is very important",
        "it is very convenient",
        "in modern society",
        "with the development of",
        "broaden my horizons",
        "learn more knowledge",
        "make me feel relaxed",
        "leave a deep impression",
    )
    if sum(1 for phrase in repeated_phrases if phrase in lowered) >= 2:
        return True
    if re.search(r"\b(there are many|it is very|it can)\b.{0,40}\b(there are many|it is very|it can)\b", lowered):
        return True
    return False


def append_calibration_note(scores: dict[str, Any], note: str) -> None:
    feedback = clean_report_text(str(scores.get("feedback") or ""))
    if note.lower() not in feedback.lower():
        feedback = f"{feedback} {note}".strip()
    scores["feedback"] = feedback[:500]


def calibrate_realistic_score(scores: dict[str, Any], question: str, transcript: str, part: str = "") -> dict[str, Any]:
    words = re.findall(r"[A-Za-z']+", transcript)
    word_count = len(words)
    sentences = [item.strip() for item in re.split(r"[.!?\n]+", transcript) if item.strip()]
    unique_ratio = len(set(word.lower() for word in words)) / max(1, word_count)
    marker_count = development_markers(transcript)
    template_count = generic_template_score(transcript)
    template_like = template_count >= 2 or is_template_like_answer(transcript)
    grammar_simple = simple_grammar_ratio(sentences)
    part = part.lower()

    scores["word_count"] = word_count

    if not words:
        band_cap(scores, 0.0)
        scores["overall_band"] = rounded_overall(scores)
        return scores

    if part == "p2":
        if word_count < 35:
            band_cap(scores, 5.0)
            append_calibration_note(scores, "Calibration: Part 2 is too short for a sustained long-turn score.")
        elif word_count < 80 or template_like:
            band_cap(scores, 5.5)
            append_calibration_note(scores, "Calibration: Part 2 needs fuller cue-card development and clear cue-card coverage.")
        elif word_count < 120 and marker_count < 2:
            band_cap(scores, 6.0)
            append_calibration_note(scores, "Calibration: Part 2 lacks enough supported development for 6.5+.")
    elif part == "p3":
        if word_count < 25:
            band_cap(scores, 5.0)
            append_calibration_note(scores, "Calibration: Part 3 is too brief for abstract discussion.")
        elif word_count < 55 or marker_count < 2 or template_like:
            band_cap(scores, 6.0)
            append_calibration_note(scores, "Calibration: Part 3 needs reasons, examples, comparison, or extension for 6.5+.")
    elif part == "p1":
        if word_count < 8:
            band_cap(scores, 5.0)
            append_calibration_note(scores, "Calibration: the answer is too short to show stable higher-band control.")
    else:
        if word_count < 60:
            band_cap(scores, 5.5)
            append_calibration_note(scores, "Calibration: the sample is too short for a high overall practice score.")

    if template_like or (word_count >= 20 and unique_ratio < 0.48):
        cap = 5.0 if part == "p2" else 5.5 if part == "p3" else 6.0
        band_cap(scores, cap)
        append_calibration_note(scores, "Calibration: generic or repetitive wording limits the score.")

    if grammar_simple >= 0.80 and word_count >= 25 and max(float(scores.get("grammatical_range") or 0.0), 0.0) > 6.0:
        scores["grammatical_range"] = 6.0
        append_calibration_note(scores, "Calibration: mostly simple sentence forms limit grammatical range.")

    scores["overall_band"] = rounded_overall(scores)
    return scores


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


def stable_question_id(part: str, question: str) -> str:
    digest = hashlib.sha1(f"{part}:{question}".encode("utf-8")).hexdigest()[:16]
    return f"{part}_{digest}"


def stable_writing_prompt_id(task_type: str, prompt: str) -> str:
    digest = hashlib.sha1(f"writing:{task_type}:{prompt}".encode("utf-8")).hexdigest()[:16]
    return f"{task_type}_{digest}"


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_iso_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


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


class TrainingStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @contextmanager
    def connection(self) -> sqlite3.Connection:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS training_observations (
                    observation_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    part TEXT NOT NULL,
                    question TEXT NOT NULL,
                    transcript TEXT NOT NULL,
                    overall_band REAL,
                    fluency_coherence REAL,
                    lexical_resource REAL,
                    grammatical_range REAL,
                    pronunciation_estimate REAL,
                    relevance REAL NOT NULL,
                    weak_item_flag INTEGER NOT NULL,
                    weak_reason_json TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    next_due TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_training_user_due
                    ON training_observations(user_id, next_due, weak_item_flag);
                CREATE INDEX IF NOT EXISTS idx_training_question
                    ON training_observations(question_id);
                """
            )

    def record_attempt(self, attempt: dict[str, Any]) -> list[dict[str, Any]]:
        score = attempt.get("ielts_score") or {}
        user_id = str(attempt.get("user_id") or DEFAULT_USER_ID)
        observed_at = now_iso()
        recorded: list[dict[str, Any]] = []
        for turn in attempt.get("turns") or []:
            if turn.get("status") != "completed":
                continue
            transcript = str(turn.get("transcript_cleaned") or turn.get("transcript_raw") or "").strip()
            question = str(turn.get("question") or "").strip()
            part = str(turn.get("part") or attempt.get("part") or "unknown").lower()
            question_id = str(turn.get("question_id") or stable_question_id(part, question))
            relevance = prompt_relevance(question, transcript)
            word_count = len(re.findall(r"[A-Za-z']+", transcript))
            reasons: list[str] = []
            if isinstance(score.get("overall_band"), (int, float)) and float(score["overall_band"]) < 5.5:
                reasons.append("low_band")
            if relevance < 0.20:
                reasons.append("off_topic")
            if word_count < 25:
                reasons.append("short_answer")
            weak = bool(reasons)
            due_days = 1 if weak else 14
            next_due = (utcnow() + dt.timedelta(days=due_days)).isoformat()
            observation = {
                "observation_id": f"{attempt['id']}_{turn['id']}",
                "user_id": user_id,
                "attempt_id": attempt["id"],
                "turn_id": turn["id"],
                "question_id": question_id,
                "part": part,
                "question": question,
                "transcript": transcript,
                "overall_band": score.get("overall_band"),
                "fluency_coherence": score.get("fluency_coherence"),
                "lexical_resource": score.get("lexical_resource"),
                "grammatical_range": score.get("grammatical_range"),
                "pronunciation_estimate": None,
                "relevance": round(relevance, 3),
                "weak_item_flag": weak,
                "weak_reason": reasons,
                "model_version": str(score.get("backend") or "unknown"),
                "observed_at": observed_at,
                "next_due": next_due,
            }
            self.record_observation(observation)
            recorded.append(observation)
        return recorded

    def record_observation(self, item: dict[str, Any]) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO training_observations (
                    observation_id, user_id, attempt_id, turn_id, question_id, part, question, transcript,
                    overall_band, fluency_coherence, lexical_resource, grammatical_range, pronunciation_estimate,
                    relevance, weak_item_flag, weak_reason_json, model_version, observed_at, next_due
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["observation_id"],
                    item["user_id"],
                    item["attempt_id"],
                    item["turn_id"],
                    item["question_id"],
                    item["part"],
                    item["question"],
                    item["transcript"],
                    item.get("overall_band"),
                    item.get("fluency_coherence"),
                    item.get("lexical_resource"),
                    item.get("grammatical_range"),
                    item.get("pronunciation_estimate"),
                    item["relevance"],
                    1 if item["weak_item_flag"] else 0,
                    json_dumps(item["weak_reason"]),
                    item["model_version"],
                    item["observed_at"],
                    item["next_due"],
                ),
            )

    def weak_items(self, user_id: str = DEFAULT_USER_ID, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT question_id, part, question, COUNT(*) AS attempts,
                       MAX(observed_at) AS last_seen,
                       MIN(next_due) AS next_due,
                       AVG(COALESCE(overall_band, 0)) AS avg_band,
                       AVG(relevance) AS avg_relevance,
                       SUM(weak_item_flag) AS weak_count,
                       '[' || GROUP_CONCAT(weak_reason_json) || ']' AS reasons_json
                FROM training_observations
                WHERE user_id = ?
                GROUP BY question_id, part, question
                HAVING weak_count > 0
                ORDER BY weak_count DESC, last_seen DESC, next_due ASC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        current = now_iso()
        return [self._weak_row_to_dict(row, current) for row in rows]

    def replay_queue(self, user_id: str = DEFAULT_USER_ID, limit: int = 10, bank: QuestionBank | None = None) -> list[dict[str, Any]]:
        weak_items = self.weak_items(user_id, limit=100)
        due = [self._queue_item(item, "weak") for item in weak_items if item["due"]]
        pending = [self._queue_item(item, "weak") for item in weak_items if not item["due"]]
        queue = (due + pending)[:limit]
        if len(queue) < limit and bank is not None:
            weak_ids = {item["question_id"] for item in weak_items}
            queue.extend(self.coverage_queue(weak_ids, limit - len(queue), bank))
        return queue[:limit]

    def coverage_queue(self, weak_question_ids: set[str], limit: int, bank: QuestionBank) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for item in sorted(bank.p1, key=lambda row: (row["topic"], row["question"])):
            question = str(item.get("question") or "").strip()
            if not question:
                continue
            question_id = stable_question_id("p1", question)
            if question_id in weak_question_ids:
                continue
            candidates.append(
                self._queue_item(
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
        for item in sorted(bank.p2, key=lambda row: (row["p3_theme"], row["title"])):
            title = str(item.get("title") or "").strip()
            bullets = [str(b).strip() for b in item.get("bullets") or [] if str(b).strip()]
            question = "\n".join([title, *[f"- {bullet}" for bullet in bullets]]).strip()
            if not question:
                continue
            question_id = stable_question_id("p2", question)
            if question_id in weak_question_ids:
                continue
            candidates.append(
                self._queue_item(
                    {
                        "question_id": question_id,
                        "part": "p2",
                        "question": question,
                        "weak_reason": [],
                        "next_due": None,
                        "due": False,
                    },
                    "coverage",
                )
            )
            if len(candidates) >= limit:
                break
        return candidates[:limit]

    def _queue_item(self, item: dict[str, Any], source: str) -> dict[str, Any]:
        result = dict(item)
        result["source"] = source
        result["weak_item_flag"] = source == "weak"
        return result

    def _weak_row_to_dict(self, row: sqlite3.Row, current: str) -> dict[str, Any]:
        reasons: set[str] = set()
        try:
            grouped = json.loads(row["reasons_json"] or "[]")
            for group in grouped:
                for reason in group:
                    reasons.add(str(reason))
        except (TypeError, ValueError):
            pass
        avg_band = row["avg_band"]
        avg_relevance = row["avg_relevance"]
        return {
            "question_id": row["question_id"],
            "part": row["part"],
            "question": row["question"],
            "attempts": int(row["attempts"] or 0),
            "weak_count": int(row["weak_count"] or 0),
            "weak_reason": sorted(reasons),
            "avg_band": round(float(avg_band), 2) if avg_band is not None else None,
            "avg_relevance": round(float(avg_relevance), 2) if avg_relevance is not None else None,
            "last_seen": row["last_seen"],
            "next_due": row["next_due"],
            "due": (parse_iso_datetime(row["next_due"]) or parse_iso_datetime(current) or utcnow())
            <= (parse_iso_datetime(current) or utcnow()),
        }


class BillingStore:
    DEFAULT_SNAPSHOT = {
        "snapshot_id": "local_2026_05_default",
        "model": "codex-cli",
        "input_price_u_per_1m_tokens": 12_000_000,
        "cached_input_price_u_per_1m_tokens": 3_000_000,
        "output_price_u_per_1m_tokens": 48_000_000,
        "reasoning_price_u_per_1m_tokens": 0,
        "effective_from": "2026-05-10T00:00:00+00:00",
        "effective_to": None,
        "source": "local_config_snapshot",
    }

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self.ensure_price_snapshot(self.DEFAULT_SNAPSHOT)
        self.ensure_user(DEFAULT_USER_ID, "Local user")

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @contextmanager
    def connection(self) -> sqlite3.Connection:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    balance_u INTEGER NOT NULL,
                    reserved_u INTEGER NOT NULL DEFAULT 0,
                    carry_numerator_u INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS wallet_ledger_entries (
                    entry_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    call_id TEXT,
                    entry_type TEXT NOT NULL,
                    amount_u INTEGER NOT NULL,
                    snapshot_id TEXT,
                    usage_id TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS codex_usage_events (
                    usage_id TEXT PRIMARY KEY,
                    call_id TEXT NOT NULL UNIQUE,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    raw_jsonl_path TEXT,
                    input_tokens INTEGER NOT NULL,
                    cached_input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    reasoning_output_tokens INTEGER NOT NULL,
                    raw_usage_json TEXT NOT NULL,
                    semantics_version TEXT NOT NULL,
                    captured_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS price_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    input_price_u_per_1m_tokens INTEGER NOT NULL,
                    cached_input_price_u_per_1m_tokens INTEGER NOT NULL,
                    output_price_u_per_1m_tokens INTEGER NOT NULL,
                    reasoning_price_u_per_1m_tokens INTEGER NOT NULL,
                    effective_from TEXT NOT NULL,
                    effective_to TEXT,
                    source TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS wallet_reservations (
                    reservation_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    call_id TEXT NOT NULL UNIQUE,
                    reserved_u INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    released_at TEXT
                );
                """
            )

    def ensure_price_snapshot(self, snapshot: dict[str, Any]) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO price_snapshots (
                    snapshot_id, model, input_price_u_per_1m_tokens, cached_input_price_u_per_1m_tokens,
                    output_price_u_per_1m_tokens, reasoning_price_u_per_1m_tokens,
                    effective_from, effective_to, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot["snapshot_id"],
                    snapshot["model"],
                    snapshot["input_price_u_per_1m_tokens"],
                    snapshot["cached_input_price_u_per_1m_tokens"],
                    snapshot["output_price_u_per_1m_tokens"],
                    snapshot["reasoning_price_u_per_1m_tokens"],
                    snapshot["effective_from"],
                    snapshot["effective_to"],
                    snapshot["source"],
                ),
            )

    def ensure_user(self, user_id: str, display_name: str) -> None:
        now = now_iso()
        with self.connection() as conn:
            row = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                return
            conn.execute(
                "INSERT INTO users (user_id, display_name, balance_u, reserved_u, status, created_at, updated_at) VALUES (?, ?, 0, 0, 'active', ?, ?)",
                (user_id, display_name, now, now),
            )
            self._append_entry(conn, user_id, None, "grant", DEFAULT_INITIAL_GRANT_U, None, None, f"grant:initial:{user_id}", {"reason": "initial 5 RMB local balance"})
            conn.execute(
                "UPDATE users SET balance_u = balance_u + ?, updated_at = ? WHERE user_id = ?",
                (DEFAULT_INITIAL_GRANT_U, now, user_id),
            )

    def wallet(self, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
        self.ensure_user(user_id, "Local user")
        with self.connection() as conn:
            user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            entries = conn.execute(
                "SELECT * FROM wallet_ledger_entries WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
                (user_id,),
            ).fetchall()
        return {
            "user_id": user["user_id"],
            "display_name": user["display_name"],
            "balance_u": int(user["balance_u"]),
            "reserved_u": int(user["reserved_u"]),
            "balance_rmb": round(int(user["balance_u"]) / MICRO_RMB_PER_RMB, 6),
            "reserved_rmb": round(int(user["reserved_u"]) / MICRO_RMB_PER_RMB, 6),
            "entries": [self._entry_to_dict(row) for row in entries],
        }

    def _entry_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "entry_id": row["entry_id"],
            "call_id": row["call_id"],
            "entry_type": row["entry_type"],
            "amount_u": int(row["amount_u"]),
            "amount_rmb": round(int(row["amount_u"]) / MICRO_RMB_PER_RMB, 6),
            "snapshot_id": row["snapshot_id"],
            "usage_id": row["usage_id"],
            "created_at": row["created_at"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
        }

    def _reservation_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "reservation_id": row["reservation_id"],
            "user_id": row["user_id"],
            "call_id": row["call_id"],
            "reserved_u": int(row["reserved_u"]),
            "reserved_rmb": round(int(row["reserved_u"]) / MICRO_RMB_PER_RMB, 6),
            "status": row["status"],
            "expires_at": row["expires_at"],
            "created_at": row["created_at"],
            "released_at": row["released_at"],
        }

    def recharge(self, user_id: str, amount_rmb: float) -> dict[str, Any]:
        if amount_rmb <= 0:
            raise ValueError("Amount must be positive")
        self.ensure_user(user_id, "Local user")
        amount_u = int(amount_rmb * MICRO_RMB_PER_RMB)
        entry_id = f"recharge_{uuid.uuid4().hex}"
        idempotency_key = f"recharge_{user_id}_{uuid.uuid4().hex}"
        now = dt.datetime.now(tz=dt.UTC).isoformat()
        with self.connection() as conn:
            conn.execute(
                "UPDATE users SET balance_u = balance_u + ?, updated_at = ? WHERE user_id = ?",
                (amount_u, now, user_id),
            )
            conn.execute(
                """INSERT INTO wallet_ledger_entries
                   (entry_id, user_id, call_id, entry_type, amount_u, snapshot_id, usage_id, idempotency_key, metadata_json, created_at)
                   VALUES (?, ?, NULL, 'recharge', ?, NULL, NULL, ?, ?, ?)""",
                (entry_id, user_id, amount_u, idempotency_key, json.dumps({"reason": f"充值 ¥{amount_rmb:.2f}"}), now),
            )
            user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return {
            "entry_id": entry_id,
            "amount_rmb": amount_rmb,
            "new_balance_rmb": round(int(user["balance_u"]) / MICRO_RMB_PER_RMB, 6),
        }

    def normalize_usage(self, usage: dict[str, Any]) -> dict[str, int]:
        input_tokens = int(usage.get("input_tokens") or 0)
        cached = int(usage.get("cached_input_tokens") or usage.get("input_tokens_details", {}).get("cached_tokens") or 0)
        output = int(usage.get("output_tokens") or 0)
        reasoning = int(usage.get("reasoning_output_tokens") or usage.get("output_tokens_details", {}).get("reasoning_tokens") or 0)
        cached = max(0, min(cached, input_tokens))
        return {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached,
            "uncached_input_tokens": max(0, input_tokens - cached),
            "output_tokens": output,
            "reasoning_output_tokens": reasoning,
        }

    def calculate_charge(self, usage: dict[str, Any], snapshot_id: str | None = None) -> dict[str, Any]:
        normalized = self.normalize_usage(usage)
        snapshot = self.get_snapshot(snapshot_id)
        numerator = (
            normalized["uncached_input_tokens"] * int(snapshot["input_price_u_per_1m_tokens"])
            + normalized["cached_input_tokens"] * int(snapshot["cached_input_price_u_per_1m_tokens"])
            + normalized["output_tokens"] * int(snapshot["output_price_u_per_1m_tokens"])
        )
        amount_u = numerator // 1_000_000
        carry_numerator_u = numerator % 1_000_000
        return {
            "amount_u": int(amount_u),
            "carry_numerator_u": int(carry_numerator_u),
            "charge_numerator_u": int(numerator),
            "usage": normalized,
            "snapshot_id": snapshot["snapshot_id"],
        }

    def get_snapshot(self, snapshot_id: str | None = None) -> sqlite3.Row:
        with self.connection() as conn:
            if snapshot_id:
                row = conn.execute("SELECT * FROM price_snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM price_snapshots ORDER BY effective_from DESC LIMIT 1").fetchone()
        if not row:
            raise ValueError("No billing price snapshot configured")
        return row

    def capture_usage(self, call_id: str, usage: dict[str, Any], provider: str = "codex", model: str = "codex-cli", raw_jsonl_path: str | None = None) -> dict[str, Any]:
        normalized = self.normalize_usage(usage)
        usage_id = f"usage_{hashlib.sha1(call_id.encode('utf-8')).hexdigest()[:20]}"
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO codex_usage_events (
                    usage_id, call_id, provider, model, raw_jsonl_path, input_tokens, cached_input_tokens,
                    output_tokens, reasoning_output_tokens, raw_usage_json, semantics_version, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usage_id,
                    call_id,
                    provider,
                    model,
                    raw_jsonl_path,
                    normalized["input_tokens"],
                    normalized["cached_input_tokens"],
                    normalized["output_tokens"],
                    normalized["reasoning_output_tokens"],
                    json_dumps(usage),
                    "codex_cli_json_v1",
                    now_iso(),
            ),
        )
        return {"usage_id": usage_id, **normalized}

    def reserve_usage(
        self,
        user_id: str,
        call_id: str,
        reserved_u: int,
        snapshot_id: str | None = None,
        ttl_seconds: int = 24 * 60 * 60,
    ) -> dict[str, Any]:
        self.ensure_user(user_id, "Local user")
        amount_u = max(0, int(reserved_u))
        if amount_u <= 0:
            raise ValueError("reserved_u must be greater than zero")
        now = now_iso()
        expires_at = (utcnow() + dt.timedelta(seconds=max(60, int(ttl_seconds)))).isoformat()
        key = f"reserve:{call_id}"
        with self.connection() as conn:
            existing = conn.execute("SELECT * FROM wallet_reservations WHERE call_id = ?", (call_id,)).fetchone()
            if existing:
                return self._reservation_to_dict(existing)
            user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not user:
                raise ValueError("User not found")
            if int(user["balance_u"]) < amount_u:
                raise ValueError("Insufficient balance for reservation")
            conn.execute(
                """
                INSERT INTO wallet_reservations (
                    reservation_id, user_id, call_id, reserved_u, status, expires_at, created_at, released_at
                ) VALUES (?, ?, ?, ?, 'reserved', ?, ?, NULL)
                """,
                (f"reservation_{hashlib.sha1(call_id.encode('utf-8')).hexdigest()[:20]}", user_id, call_id, amount_u, expires_at, now),
            )
            conn.execute(
                "UPDATE users SET balance_u = balance_u - ?, reserved_u = reserved_u + ?, updated_at = ? WHERE user_id = ?",
                (amount_u, amount_u, now, user_id),
            )
            self._append_entry(
                conn,
                user_id,
                call_id,
                "reserve",
                -amount_u,
                snapshot_id,
                None,
                key,
                {"reserved_u": amount_u, "expires_at": expires_at},
            )
            row = conn.execute("SELECT * FROM wallet_reservations WHERE call_id = ?", (call_id,)).fetchone()
        return self._reservation_to_dict(row)

    def release_reservation(self, user_id: str, call_id: str) -> dict[str, Any]:
        key = f"release:{call_id}"
        now = now_iso()
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM wallet_reservations WHERE call_id = ?", (call_id,)).fetchone()
            if not row:
                raise ValueError("Reservation not found")
            owner_user_id = row["user_id"]
            if row["status"] == "released":
                return self._reservation_to_dict(row)
            if row["status"] != "reserved":
                return self._reservation_to_dict(row)
            reserved_u = int(row["reserved_u"])
            if reserved_u > 0:
                conn.execute(
                    "UPDATE users SET balance_u = balance_u + ?, reserved_u = reserved_u - ?, updated_at = ? WHERE user_id = ?",
                    (reserved_u, reserved_u, now, owner_user_id),
                )
                self._append_entry(
                    conn,
                    owner_user_id,
                    call_id,
                    "release",
                    reserved_u,
                    None,
                    None,
                    key,
                    {"released_u": reserved_u, "reservation_id": row["reservation_id"]},
                )
            conn.execute(
                "UPDATE wallet_reservations SET status = 'released', released_at = ? WHERE call_id = ?",
                (now, call_id),
            )
            row = conn.execute("SELECT * FROM wallet_reservations WHERE call_id = ?", (call_id,)).fetchone()
        return self._reservation_to_dict(row)

    def reconcile_usage(self, user_id: str, call_id: str, usage: dict[str, Any] | None, snapshot_id: str | None = None) -> dict[str, Any]:
        return self.settle_usage(user_id, call_id, usage, snapshot_id)

    def settle_usage(self, user_id: str, call_id: str, usage: dict[str, Any] | None, snapshot_id: str | None = None) -> dict[str, Any]:
        self.ensure_user(user_id, "Local user")
        if not usage:
            return {"status": "pending_reconciliation", "charged_u": 0, "reason": "missing authoritative usage"}
        captured = self.capture_usage(call_id, usage)
        charge = self.calculate_charge(usage, snapshot_id)
        key = f"settle:{call_id}"
        now = now_iso()
        with self.connection() as conn:
            existing = conn.execute("SELECT * FROM wallet_ledger_entries WHERE idempotency_key = ?", (key,)).fetchone()
            if existing:
                return {"status": "already_settled", "charged_u": abs(int(existing["amount_u"])), "usage_id": existing["usage_id"], "snapshot_id": existing["snapshot_id"]}
            reservation = conn.execute("SELECT * FROM wallet_reservations WHERE call_id = ?", (call_id,)).fetchone()
            ledger_user_id = reservation["user_id"] if reservation else user_id
            reserved_u = int(reservation["reserved_u"]) if reservation and reservation["status"] == "reserved" else 0
            settled_from_reservation = min(reserved_u, int(charge["amount_u"])) if reserved_u else 0
            released_from_reservation = max(0, reserved_u - int(charge["amount_u"])) if reserved_u else 0
            extra_charged = max(0, int(charge["amount_u"]) - reserved_u) if reserved_u else int(charge["amount_u"])
            if reserved_u:
                conn.execute(
                    "UPDATE users SET reserved_u = reserved_u - ?, carry_numerator_u = carry_numerator_u + ?, updated_at = ? WHERE user_id = ?",
                    (reserved_u, charge["carry_numerator_u"], now, ledger_user_id),
                )
                if extra_charged:
                    conn.execute(
                        "UPDATE users SET balance_u = balance_u - ?, updated_at = ? WHERE user_id = ?",
                        (extra_charged, now, ledger_user_id),
                    )
                if released_from_reservation:
                    conn.execute(
                        "UPDATE users SET balance_u = balance_u + ?, updated_at = ? WHERE user_id = ?",
                        (released_from_reservation, now, ledger_user_id),
                    )
                conn.execute(
                    "UPDATE wallet_reservations SET status = 'settled', released_at = ? WHERE call_id = ?",
                    (now, call_id),
                )
                if released_from_reservation > 0:
                    self._append_entry(
                        conn,
                        ledger_user_id,
                        call_id,
                        "release",
                        released_from_reservation,
                        charge["snapshot_id"],
                        captured["usage_id"],
                        f"release:{call_id}",
                        {"released_u": released_from_reservation, "reservation_id": reservation["reservation_id"]},
                    )
            else:
                conn.execute(
                    "UPDATE users SET balance_u = balance_u - ?, carry_numerator_u = carry_numerator_u + ?, updated_at = ? WHERE user_id = ?",
                    (charge["amount_u"], charge["carry_numerator_u"], now, ledger_user_id),
                )
            self._append_entry(
                conn,
                ledger_user_id,
                call_id,
                "settle",
                -charge["amount_u"],
                charge["snapshot_id"],
                captured["usage_id"],
                key,
                {"usage": charge["usage"], "charge_numerator_u": charge["charge_numerator_u"], "carry_numerator_u": charge["carry_numerator_u"], "settled_from_reservation_u": settled_from_reservation, "released_from_reservation_u": released_from_reservation, "extra_charged_u": extra_charged},
            )
        result = {"status": "settled", "charged_u": charge["amount_u"], "usage_id": captured["usage_id"], "snapshot_id": charge["snapshot_id"], "usage": charge["usage"]}
        if reserved_u:
            result["reserved_u"] = reserved_u
        if released_from_reservation:
            result["released_u"] = released_from_reservation
        if extra_charged:
            result["extra_charged_u"] = extra_charged
        return result

    def _append_entry(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        call_id: str | None,
        entry_type: str,
        amount_u: int,
        snapshot_id: str | None,
        usage_id: str | None,
        idempotency_key: str,
        metadata: dict[str, Any],
    ) -> None:
        entry_id = f"entry_{hashlib.sha1(f'{user_id}:{idempotency_key}'.encode('utf-8')).hexdigest()[:20]}"
        conn.execute(
            """
            INSERT INTO wallet_ledger_entries (
                entry_id, user_id, call_id, entry_type, amount_u, snapshot_id,
                usage_id, idempotency_key, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (entry_id, user_id, call_id, entry_type, amount_u, snapshot_id, usage_id, idempotency_key, json_dumps(metadata), now_iso()),
        )


@dataclass
class AppState:
    data_dir: Path
    reports_dir: Path
    bank: QuestionBank = field(init=False)
    writing_bank: WritingPromptBank = field(init=False)
    training: TrainingStore = field(init=False)
    billing: BillingStore = field(init=False)
    lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    latest_report: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.bank = QuestionBank(self.data_dir)
        self.writing_bank = WritingPromptBank(self.data_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.attempts_dir.mkdir(parents=True, exist_ok=True)
        self.writing_dir.mkdir(parents=True, exist_ok=True)
        self.writing_profiles_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.model_audio_dir.mkdir(parents=True, exist_ok=True)
        self.examiner_audio_dir.mkdir(parents=True, exist_ok=True)
        self.training = TrainingStore(self.reports_dir / "training" / "training.sqlite3")
        self.billing = BillingStore(self.reports_dir / "billing" / "billing.sqlite3")

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

    @property
    def writing_dir(self) -> Path:
        return self.reports_dir / "writing"

    @property
    def writing_profiles_dir(self) -> Path:
        return self.reports_dir / "writing_profiles"

    def attempt_path(self, attempt_id: str) -> Path:
        return self.attempts_dir / f"{safe_slug(attempt_id)}.json"

    def writing_entry_path(self, entry_id: str) -> Path:
        return self.writing_dir / f"{safe_slug(entry_id)}.json"

    def writing_profile_path(self, user_id: str | None = None) -> Path:
        return self.writing_profiles_dir / f"{safe_slug(user_id or DEFAULT_USER_ID)}.json"

    def save_attempt(self, attempt: dict[str, Any]) -> None:
        path = self.attempt_path(str(attempt["id"]))
        with self.lock:
            tmp_path = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(attempt, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            tmp_path.replace(path)
            if is_scored_report(attempt):
                self.latest_report = attempt | {"path": str(path)}
                if attempt.get("part") == "p1" or attempt.get("mode") == "p1":
                    self.delete_older_p1_reports(str(attempt["id"]))

    def delete_older_p1_reports(self, keep_attempt_id: str) -> None:
        with self.lock:
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
        with self.lock:
            if not path.exists():
                raise FileNotFoundError(f"Attempt not found: {attempt_id}")
            return read_json(path)

    def load_report_attempt(self, attempt_id: str) -> dict[str, Any]:
        attempt = self.load_attempt(attempt_id)
        if not is_scored_report(attempt):
            raise ValueError("Attempt report is not available until scoring is complete.")
        return attempt

    def save_writing_entry(self, entry: dict[str, Any]) -> None:
        path = self.writing_entry_path(str(entry["id"]))
        with self.lock:
            tmp_path = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(entry, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            tmp_path.replace(path)

    def load_writing_entry(self, entry_id: str) -> dict[str, Any]:
        path = self.writing_entry_path(entry_id)
        with self.lock:
            if not path.exists():
                raise FileNotFoundError(f"Writing entry not found: {entry_id}")
            return read_json(path)

    def load_writing_profile(self, user_id: str | None = None) -> dict[str, Any]:
        path = self.writing_profile_path(user_id)
        with self.lock:
            if not path.exists():
                return default_writing_profile(user_id or DEFAULT_USER_ID)
            try:
                profile = read_json(path)
            except ValueError:
                return default_writing_profile(user_id or DEFAULT_USER_ID)
        return normalize_writing_profile(profile, user_id or DEFAULT_USER_ID)

    def save_writing_profile(self, profile: dict[str, Any]) -> None:
        user_id = str(profile.get("user_id") or DEFAULT_USER_ID)
        path = self.writing_profile_path(user_id)
        with self.lock:
            tmp_path = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(profile, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            tmp_path.replace(path)

    def writing_entries(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self.lock:
            for path in sorted(self.writing_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
                try:
                    entry = read_json(path)
                except ValueError:
                    continue
                rows.append(entry)
        return rows

    def writing_summary(self, month_value: str | None = None) -> dict[str, Any]:
        start, end = month_bounds(month_value)
        month = start.strftime("%Y-%m")
        today = local_date_string()
        day_map: dict[str, dict[str, Any]] = {}
        recent: list[dict[str, Any]] = []
        for entry in self.writing_entries():
            practice_date = str(entry.get("practice_date") or local_date_string(str(entry.get("saved_at") or entry.get("created_at") or "")))
            score = entry.get("score") if isinstance(entry.get("score"), dict) else {}
            compact = {
                "id": entry.get("id"),
                "practice_date": practice_date,
                "display_time": local_timestamp(str(entry.get("updated_at") or entry.get("created_at") or "")),
                "task_type": entry.get("task_type"),
                "task_label": WRITING_TASK_LABELS.get(str(entry.get("task_type")), "Writing"),
                "title": entry.get("title") or entry.get("prompt_title") or short_question(str(entry.get("prompt") or "")),
                "word_count": entry.get("word_count"),
                "status": entry.get("status"),
                "overall_band": score.get("overall_band"),
            }
            recent.append(compact)
            try:
                entry_date = dt.date.fromisoformat(practice_date)
            except ValueError:
                continue
            if start <= entry_date <= end:
                current = day_map.get(practice_date)
                entry_status = "scored" if entry.get("status") == "scored" else "saved"
                if not current or (entry_status == "scored" and current.get("status") != "scored"):
                    day_map[practice_date] = {**compact, "date": practice_date, "status": entry_status, "entry_id": entry.get("id")}
        days = []
        current_day = start
        while current_day <= end:
            key = current_day.isoformat()
            days.append(day_map.get(key) or {"date": key, "status": "empty"})
            current_day += dt.timedelta(days=1)
        practiced_dates = {item["date"] for item in day_map.values() if item.get("status") in {"saved", "scored"}}
        scored_count = sum(1 for item in day_map.values() if item.get("status") == "scored")
        streak = 0
        cursor = dt.date.fromisoformat(today)
        all_practiced_dates = {
            str(entry.get("practice_date") or "")
            for entry in self.writing_entries()
            if entry.get("status") in {"saved", "scored"}
        }
        while cursor.isoformat() in all_practiced_dates:
            streak += 1
            cursor -= dt.timedelta(days=1)
        today_entry = next((entry for entry in self.writing_entries() if str(entry.get("practice_date")) == today), None)
        return {
            "month": month,
            "today": today,
            "days": days,
            "stats": {
                "practiced_days": len(practiced_dates),
                "scored_entries": scored_count,
                "streak_days": streak,
                "total_entries": len(recent),
            },
            "recent_entries": recent[:20],
            "today_entry": today_entry,
        }

    def random_writing_prompt(self, task_type: str | None = None) -> dict[str, Any]:
        selected_type = normalize_writing_task_type(task_type) if task_type else next_default_writing_task_type()
        prompts = self.writing_bank.list(selected_type)
        if not prompts:
            raise ValueError(f"No writing prompts available for {selected_type}")
        used_prompt_ids = {
            str(entry.get("prompt_id"))
            for entry in self.writing_entries()
            if entry.get("status") in {"saved", "scored"} and entry.get("prompt_id")
        }
        unused = [prompt for prompt in prompts if prompt.get("id") not in used_prompt_ids]
        prompt = random.choice(unused or prompts)
        return {**prompt, "selection": "random", "unwritten": bool(unused)}

    def history(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self.lock:
            paths = sorted(self.attempts_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
            for path in paths:
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


def normalize_writing_task_type(value: str | None) -> str:
    task_type = str(value or "").strip().lower()
    aliases = {
        "task1": "task1_academic",
        "task_1": "task1_academic",
        "task1academic": "task1_academic",
        "task 1 academic": "task1_academic",
        "task2": "task2",
        "task_2": "task2",
        "task 2": "task2",
    }
    task_type = aliases.get(task_type, task_type)
    if task_type not in WRITING_TASK_TYPES:
        raise ValueError("Unknown writing task type")
    return task_type


def local_date_string(value: str | None = None) -> str:
    if value:
        parsed = parse_iso_datetime(value)
        if parsed:
            return parsed.astimezone().strftime("%Y-%m-%d")
    return dt.datetime.now().strftime("%Y-%m-%d")


def month_bounds(month_value: str | None) -> tuple[dt.date, dt.date]:
    value = (month_value or local_date_string()[:7]).strip()
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        value = local_date_string()[:7]
    year, month = [int(part) for part in value.split("-")]
    _, day_count = calendar.monthrange(year, month)
    start = dt.date(year, month, 1)
    return start, dt.date(year, month, day_count)


class WritingPromptBank:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.prompts = self.load()

    def load(self) -> dict[str, list[dict[str, Any]]]:
        base_dir = self.data_dir / "writing"
        loaded: dict[str, list[dict[str, Any]]] = {}
        for task_type in sorted(WRITING_TASK_TYPES):
            path = base_dir / f"{task_type}.json"
            if not path.exists():
                loaded[task_type] = []
                continue
            payload = read_json(path)
            raw_items = payload.get("prompts") if isinstance(payload, dict) else payload
            if not isinstance(raw_items, list):
                raise ValueError(f"Writing prompt file must contain a prompts array: {path}")
            items: list[dict[str, Any]] = []
            for index, raw_item in enumerate(raw_items):
                if not isinstance(raw_item, dict):
                    raise ValueError(f"Writing prompt must be an object in {path}")
                prompt = clean_markdown_text(str(raw_item.get("prompt") or raw_item.get("question") or ""))
                if not prompt:
                    continue
                prompt_id = clean_report_text(str(raw_item.get("id") or "")) or stable_writing_prompt_id(task_type, prompt)
                items.append(
                    {
                        "id": safe_slug(prompt_id),
                        "task_type": task_type,
                        "task_label": WRITING_TASK_LABELS[task_type],
                        "title": clean_report_text(str(raw_item.get("title") or "")) or f"{WRITING_TASK_LABELS[task_type]} {index + 1}",
                        "prompt": prompt,
                        "category": clean_report_text(str(raw_item.get("category") or "")),
                        "source": clean_report_text(str(raw_item.get("source") or "")) or "local",
                    }
                )
            loaded[task_type] = items
        return loaded

    def list(self, task_type: str | None = None) -> list[dict[str, Any]]:
        if task_type:
            return list(self.prompts.get(normalize_writing_task_type(task_type), []))
        items: list[dict[str, Any]] = []
        for value in self.prompts.values():
            items.extend(value)
        return items

    def get(self, prompt_id: str, task_type: str | None = None) -> dict[str, Any] | None:
        pools = [self.prompts.get(normalize_writing_task_type(task_type), [])] if task_type else self.prompts.values()
        for pool in pools:
            for prompt in pool:
                if prompt.get("id") == prompt_id:
                    return dict(prompt)
        return None


def writing_word_count(answer: str) -> int:
    return len(re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)?|\d+(?:\.\d+)?", answer or ""))


def default_writing_profile(user_id: str | None = None) -> dict[str, Any]:
    return {
        "user_id": str(user_id or DEFAULT_USER_ID),
        "updated_at": "",
        "total_scored": 0,
        "task_counts": {"task1_academic": 0, "task2": 0},
        "average_overall_band": None,
        "criterion_averages": {
            "task_achievement": None,
            "task_response": None,
            "coherence_cohesion": None,
            "lexical_resource": None,
            "grammatical_range_accuracy": None,
        },
        "tag_counts": {},
        "primary_focus": "insufficient_data",
        "primary_focus_text": "还需要更多已评分作文来形成稳定画像。",
        "recent_evidence": [],
    }


def normalize_writing_profile(profile: dict[str, Any], user_id: str | None = None) -> dict[str, Any]:
    base = default_writing_profile(user_id or str(profile.get("user_id") or DEFAULT_USER_ID))
    merged = {**base, **profile}
    task_counts = merged.get("task_counts") if isinstance(merged.get("task_counts"), dict) else {}
    merged["task_counts"] = {
        "task1_academic": int(task_counts.get("task1_academic") or 0),
        "task2": int(task_counts.get("task2") or 0),
    }
    tag_counts = merged.get("tag_counts") if isinstance(merged.get("tag_counts"), dict) else {}
    merged["tag_counts"] = {str(key): int(value or 0) for key, value in tag_counts.items() if str(key).strip()}
    averages = merged.get("criterion_averages") if isinstance(merged.get("criterion_averages"), dict) else {}
    merged["criterion_averages"] = {**base["criterion_averages"], **averages}
    evidence = merged.get("recent_evidence") if isinstance(merged.get("recent_evidence"), list) else []
    merged["recent_evidence"] = [str(item) for item in evidence if str(item).strip()][:8]
    try:
        merged["total_scored"] = int(merged.get("total_scored") or 0)
    except (TypeError, ValueError):
        merged["total_scored"] = 0
    return merged


def writing_profile_tags(entry: dict[str, Any], score: dict[str, Any]) -> list[str]:
    task_type = normalize_writing_task_type(str(entry.get("task_type") or "task2"))
    word_count = int(entry.get("word_count") or writing_word_count(str(entry.get("answer") or "")))
    task_key = "task_achievement" if task_type == "task1_academic" else "task_response"
    tags: list[str] = []
    if (task_type == "task1_academic" and word_count < 150) or (task_type == "task2" and word_count < 250):
        tags.append("under_length")
    if isinstance(score.get(task_key), (int, float)) and float(score[task_key]) <= 5.0:
        tags.append("weak_task_achievement" if task_type == "task1_academic" else "weak_task_response")
    if isinstance(score.get("coherence_cohesion"), (int, float)) and float(score["coherence_cohesion"]) <= 5.0:
        tags.append("coherence_issue")
    if isinstance(score.get("lexical_resource"), (int, float)) and float(score["lexical_resource"]) <= 5.0:
        tags.append("weak_lexical_resource")
    corrections = score.get("grammar_corrections") if isinstance(score.get("grammar_corrections"), list) else []
    if (isinstance(score.get("grammatical_range_accuracy"), (int, float)) and float(score["grammatical_range_accuracy"]) <= 5.0) or corrections:
        tags.append("grammar_accuracy")
    if score.get("backend") == "fallback":
        tags.append("fallback_scoring")
    return sorted(dict.fromkeys(tags))


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


def infer_writing_primary_focus(tag_counts: dict[str, int]) -> str:
    priority = [
        "weak_task_response",
        "weak_task_achievement",
        "under_length",
        "coherence_issue",
        "grammar_accuracy",
        "weak_lexical_resource",
    ]
    ranked = sorted(tag_counts.items(), key=lambda item: (-item[1], priority.index(item[0]) if item[0] in priority else 99))
    return ranked[0][0] if ranked else "insufficient_data"


def writing_profile_snapshot(profile: dict[str, Any]) -> dict[str, Any]:
    tag_counts = profile.get("tag_counts") if isinstance(profile.get("tag_counts"), dict) else {}
    top_tags = sorted(tag_counts.items(), key=lambda item: (-int(item[1] or 0), str(item[0])))[:5]
    return {
        "total_scored": profile.get("total_scored", 0),
        "average_overall_band": profile.get("average_overall_band"),
        "primary_focus": profile.get("primary_focus"),
        "primary_focus_text": profile.get("primary_focus_text"),
        "top_issues": [{"tag": tag, "label": writing_tag_text(tag), "count": count} for tag, count in top_tags],
        "recent_evidence": list(profile.get("recent_evidence") or [])[:4],
        "updated_at": profile.get("updated_at"),
    }


def summarize_writing_profile_for_prompt(profile: dict[str, Any]) -> str:
    snapshot = writing_profile_snapshot(profile)
    if not snapshot.get("total_scored"):
        return "No scored writing profile yet. Use this answer as the first data point."
    return json_dumps(snapshot)


def update_writing_profile(state: AppState, entry: dict[str, Any], score: dict[str, Any]) -> dict[str, Any]:
    user_id = str(entry.get("user_id") or DEFAULT_USER_ID)
    profile = state.load_writing_profile(user_id)
    previous_total = int(profile.get("total_scored") or 0)
    new_total = previous_total + 1
    task_type = normalize_writing_task_type(str(entry.get("task_type") or "task2"))
    task_counts = dict(profile.get("task_counts") or {})
    task_counts[task_type] = int(task_counts.get(task_type) or 0) + 1
    profile["task_counts"] = task_counts
    profile["total_scored"] = new_total
    band = score.get("overall_band")
    if isinstance(band, (int, float)) and not isinstance(band, bool):
        previous_average = profile.get("average_overall_band")
        previous_value = float(previous_average) if isinstance(previous_average, (int, float)) else float(band)
        profile["average_overall_band"] = round(((previous_value * previous_total) + float(band)) / new_total, 2)
    averages = dict(profile.get("criterion_averages") or {})
    for key in ("task_achievement", "task_response", "coherence_cohesion", "lexical_resource", "grammatical_range_accuracy"):
        value = score.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            previous_average = averages.get(key)
            previous_value = float(previous_average) if isinstance(previous_average, (int, float)) else float(value)
            averages[key] = round(((previous_value * previous_total) + float(value)) / new_total, 2)
    profile["criterion_averages"] = averages
    tags = writing_profile_tags(entry, score)
    tag_counts = dict(profile.get("tag_counts") or {})
    for tag in tags:
        tag_counts[tag] = int(tag_counts.get(tag) or 0) + 1
    profile["tag_counts"] = tag_counts
    primary_focus = infer_writing_primary_focus({tag: count for tag, count in tag_counts.items() if tag != "fallback_scoring"})
    profile["primary_focus"] = primary_focus
    profile["primary_focus_text"] = writing_tag_text(primary_focus) if primary_focus != "insufficient_data" else default_writing_profile(user_id)["primary_focus_text"]
    evidence_item = (
        f"{WRITING_TASK_LABELS[task_type]} · Band {score.get('overall_band', '—')} · "
        f"{int(entry.get('word_count') or 0)} words · {', '.join(writing_tag_text(tag) for tag in tags[:3]) or '暂无明显弱项'}"
    )
    recent = [evidence_item] + [str(item) for item in profile.get("recent_evidence") or [] if str(item) != evidence_item]
    profile["recent_evidence"] = recent[:8]
    profile["updated_at"] = now_iso()
    state.save_writing_profile(profile)
    score["profile_tags"] = tags
    score["personalization_note"] = "本次 AI 评分与辅导已用于更新你的写作画像。"
    return writing_profile_snapshot(profile)


def writing_fallback_score(task_type: str, answer: str, reason: str = "") -> dict[str, Any]:
    word_count = writing_word_count(answer)
    if word_count >= 250:
        base = 5.5
    elif word_count >= 150:
        base = 5.0
    elif word_count >= 80:
        base = 4.5
    else:
        base = 4.0
    task_key = "task_achievement" if task_type == "task1_academic" else "task_response"
    task_label = "Task Achievement" if task_type == "task1_academic" else "Task Response"
    feedback = clean_markdown_text(
        "\n".join(
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
        "error": clean_report_text(reason)[:240],
    }


def normalize_writing_score(payload: dict[str, Any], task_type: str, usage: dict[str, Any] | None, billing: BillingStore | None) -> dict[str, Any]:
    task_key = "task_achievement" if task_type == "task1_academic" else "task_response"
    alternate_task_key = "task_response" if task_key == "task_achievement" else "task_achievement"
    feedback = clean_markdown_text(str(payload.get("feedback_markdown") or payload.get("feedback") or ""))
    corrections = payload.get("grammar_corrections")
    if not isinstance(corrections, list):
        corrections = []
    cleaned_corrections = [clean_report_text(str(item)) for item in corrections]
    cleaned_corrections = [item for item in cleaned_corrections if item and item.lower() not in {"none", "无"}][:8]
    if "语法错误纠正" not in feedback:
        feedback = clean_markdown_text(
            feedback
            + "\n\n- 语法错误纠正：\n"
            + ("\n".join(f"  {index}. {item}" for index, item in enumerate(cleaned_corrections, start=1)) if cleaned_corrections else "  1. 无")
        )
    result: dict[str, Any] = {
        "overall_band": clamp_band(payload.get("overall_band")),
        task_key: clamp_band(payload.get(task_key, payload.get(alternate_task_key))),
        "coherence_cohesion": clamp_band(payload.get("coherence_cohesion")),
        "lexical_resource": clamp_band(payload.get("lexical_resource")),
        "grammatical_range_accuracy": clamp_band(payload.get("grammatical_range_accuracy")),
        "feedback_markdown": feedback,
        "grammar_corrections": cleaned_corrections,
        "backend": "codex",
    }
    if usage:
        result["billing_usage"] = billing.normalize_usage(usage) if billing else usage
    return result


def score_writing_with_codex(
    entry: dict[str, Any],
    data_dir: Path,
    billing: BillingStore | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_type = normalize_writing_task_type(str(entry.get("task_type") or "task2"))
    task_key = "task_achievement" if task_type == "task1_academic" else "task_response"
    task_label = "Task Achievement" if task_type == "task1_academic" else "Task Response"
    answer = str(entry.get("answer") or "")
    prompt = (
        "You are an IELTS Writing examiner for a Chinese learner. Return JSON only. "
        "Score this IELTS Writing answer using official IELTS Writing criteria. "
        f"The task-specific criterion is {task_label}; return it as numeric key {task_key}. "
        "Also return numeric keys overall_band, coherence_cohesion, lexical_resource, grammatical_range_accuracy, "
        "string key feedback_markdown, and array key grammar_corrections. "
        "feedback_markdown should be natural Chinese Markdown with useful bullets; do not force a fixed template. "
        "Use the learner profile to personalize advice when it is available, but do not mention private storage details. "
        "Do not reward or assume copied AI sample essays; encourage feedback based on the learner's own real writing. "
        "For grammar_corrections, include only meaningful grammar issues for spoken/written learner improvement; "
        "do not include punctuation-only fixes. If none, return an empty array. "
        f"\n\nLearner writing profile:\n{summarize_writing_profile_for_prompt(profile or default_writing_profile(str(entry.get('user_id') or DEFAULT_USER_ID)))}"
        f"\n\nTask type: {WRITING_TASK_LABELS[task_type]}\nPrompt:\n{entry.get('prompt', '')}\n\nAnswer:\n{answer}\n"
    )
    output, usage = run_codex(prompt, f"writing_score_{entry['id']}", billing)
    return normalize_writing_score(extract_json_object(output), task_type, usage, billing)


def next_default_writing_task_type(date_value: str | None = None) -> str:
    current = dt.date.fromisoformat(date_value or local_date_string())
    return "task1_academic" if current.toordinal() % 2 == 0 else "task2"


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


def p3_with_codex(theme: str, prior_answer: str, billing: BillingStore | None = None) -> dict[str, Any]:
    prompt = (
        "Return JSON only with keys questions (array of 5 IELTS Part 3 questions) "
        "and follow_up (one examiner follow-up). "
        "Questions must be natural IELTS Speaking Part 3 examiner questions. "
        f"Theme: {theme}\nCandidate answer: {prior_answer}\n"
    )
    output, _usage = run_codex(prompt, f"p3_plan_{hashlib.sha1(prompt.encode('utf-8')).hexdigest()[:20]}", billing)
    payload = extract_json_object(output)
    questions = [str(item) for item in payload.get("questions", []) if str(item).strip()]
    if len(questions) < 5:
        raise RuntimeError("codex returned fewer than five questions")
    return {"questions": questions[:5], "follow_up": str(payload.get("follow_up", "")), "backend": "codex"}


def generate_p3_plan(theme: str, prior_answer: str, source: str, billing: BillingStore | None = None) -> dict[str, Any]:
    try:
        result = p3_with_codex(theme, prior_answer, billing)
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


def fallback_p1_identity_follow_up(answer: str) -> str:
    normalized = answer.lower()
    if any(word in normalized for word in ("university", "college", "major", "degree", "undergraduate", "postgraduate")):
        return "Why did you choose that subject or major?"
    if any(word in normalized for word in ("school", "middle school", "high school", "primary school", "secondary school")):
        return "What subject do you enjoy most at school?"
    if any(word in normalized for word in ("study", "student", "studying")):
        return "What do you enjoy most about your studies?"
    if any(word in normalized for word in ("work", "job", "company", "office", "teacher", "engineer", "business")):
        return "What do you like most about your work?"
    return "Could you tell me a little more about what you do now?"


def generate_p1_identity_follow_up(answer: str, billing: BillingStore | None = None) -> dict[str, str]:
    fallback = fallback_p1_identity_follow_up(answer)
    prompt = (
        "You are an IELTS Speaking examiner. Generate exactly one short Part 1 follow-up question "
        "based on whether the candidate works, studies at university, or goes to school. "
        "Return JSON only with key question. "
        f"Candidate answer: {answer}\n"
    )
    try:
        output, _usage = run_codex(prompt, f"p1_identity_{hashlib.sha1(prompt.encode('utf-8')).hexdigest()[:20]}", billing)
        payload = extract_json_object(output)
        question = clean_report_text(str(payload.get("question") or ""))
        if not question:
            raise RuntimeError("codex returned empty follow-up")
        return {"question": question, "backend": "codex", "status": "ready"}
    except Exception:
        return {"question": fallback, "backend": "fallback", "status": "fallback"}


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
        "transcript_markdown": "",
        "transcript_status": "missing",
        "duration_seconds": None,
        "band7_version": "",
        "band7_markdown": "",
        "model_audio": None,
        "upgrade_notes": [],
        "ai_coaching": "",
    }


def candidate_names_from_payload(payload: dict[str, Any]) -> tuple[str, str]:
    full_name = clean_report_text(str(payload.get("full_name") or payload.get("fullname") or DEFAULT_FULL_NAME)) or DEFAULT_FULL_NAME
    english_name = clean_report_text(str(payload.get("english_name") or payload.get("englishName") or payload.get("candidate") or DEFAULT_ENGLISH_NAME)) or DEFAULT_ENGLISH_NAME
    return full_name, english_name


def display_question_number(turn: dict[str, Any]) -> int:
    value = turn.get("display_index")
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(turn.get("index") or 0) + 1


def is_p1_name_intro_turn(turn: dict[str, Any]) -> bool:
    prompt = turn.get("prompt") or {}
    return turn.get("part") == "p1" and prompt.get("flow") == "intro" and prompt.get("role") == "name"


def p1_name_answer(attempt: dict[str, Any]) -> str:
    full_name = clean_report_text(str(attempt.get("full_name") or DEFAULT_FULL_NAME)) or DEFAULT_FULL_NAME
    english_name = clean_report_text(str(attempt.get("english_name") or DEFAULT_ENGLISH_NAME)) or DEFAULT_ENGLISH_NAME
    if full_name.lower() == english_name.lower():
        return f"My full name is {full_name}."
    return f"My full name is {full_name}, but you can call me {english_name}."


def apply_p1_name_identity(attempt: dict[str, Any], turn: dict[str, Any]) -> None:
    if not is_p1_name_intro_turn(turn):
        return
    answer = p1_name_answer(attempt)
    turn["transcript_raw"] = answer
    turn["transcript_cleaned"] = answer
    turn["transcript_markdown"] = spoken_markdown(answer)
    turn["transcript_status"] = "captured"
    turn["identity_corrected"] = True
    notes = list(turn.get("cleaning_notes") or [])
    note = "Name intro corrected from Settings full name and English name."
    if note not in notes:
        notes.append(note)
    turn["cleaning_notes"] = notes


def is_p1_work_study_identity_question(question: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()
    return any(
        phrase in normalized
        for phrase in (
            "do you work or are you",
            "are you a student or do you work",
            "do you work or study",
            "do you work or are you a full time student",
            "what subject are you studying or what did you study",
        )
    )


def build_p1_turns(
    state: AppState,
    attempt_id: str,
    total: int = P1_TURN_COUNT,
    display_total: int | None = None,
) -> list[dict[str, Any]]:
    countable_intro_items = [item for item in P1_INTRO_QUESTIONS if item.get("counts_toward_total", True)]
    uncounted_intro_items = [item for item in P1_INTRO_QUESTIONS if not item.get("counts_toward_total", True)]
    remaining_count = max(0, total - len(countable_intro_items))
    ordinary_pool = [
        item
        for item in state.bank.p1
        if not is_p1_work_study_identity_question(str(item.get("question") or ""))
    ]
    if len(ordinary_pool) < remaining_count:
        raise ValueError("Not enough ordinary IELTS Part 1 questions after reserving intro identity turns.")
    ordinary_questions = random.sample(ordinary_pool, remaining_count)
    turn_items = uncounted_intro_items + countable_intro_items + ordinary_questions
    turns: list[dict[str, Any]] = []
    display_index = 0
    for index, item in enumerate(turn_items):
        counts_toward_total = bool(item.get("counts_toward_total", True))
        if counts_toward_total:
            display_index += 1
        turn = create_turn(
            state,
            attempt_id,
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
    intensity: str = "high",
    allow_codex: bool = True,
) -> None:
    if allow_codex:
        plan = generate_p3_plan(theme, prior_answer, source, state.billing)
    else:
        fallback = fallback_p3(theme, prior_answer, P3_MAIN_COUNT)
        plan = {
            "questions": fallback["questions"],
            "follow_up": fallback["follow_up"],
            "backend": "fallback",
            "status": "skipped_sync_ai",
            "source": source,
            "theme": theme,
        }
    start_index = len(attempt.get("turns") or [])
    use_follow_ups = intensity == "high"
    new_turns: list[dict[str, Any]] = []
    for main_index, question in enumerate(plan["questions"]):
        main_turn = create_turn(
            state,
            str(attempt["id"]),
            "p3",
            start_index + len(new_turns),
            start_index + (P3_TURN_COUNT if use_follow_ups else P3_MAIN_COUNT),
            question,
            {"theme": theme, "question": question, "role": "main", "source": source},
        )
        new_turns.append(main_turn)
        if not use_follow_ups:
            continue
        follow_up = plan["follow_up"]
        follow_turn = create_turn(
            state,
            str(attempt["id"]),
            "p3",
            start_index + len(new_turns),
            start_index + P3_TURN_COUNT,
            follow_up,
            {"theme": theme, "question": follow_up, "role": "follow_up", "after_main": main_index + 1, "source": source},
        )
        new_turns.append(follow_turn)
    attempt["turns"].extend(new_turns)
    for index, turn in enumerate(attempt["turns"]):
        turn["index"] = index
        turn["total"] = len(attempt["turns"])
    attempt["p3_generation_status"] = plan["status"]
    attempt["p3_generation_source"] = plan["source"]
    attempt["p3_generation_backend"] = plan["backend"]
    attempt["p3_theme"] = theme
    attempt["p3_intensity"] = intensity


def adapt_p3_follow_up(state: AppState, attempt: dict[str, Any], completed_turn: dict[str, Any], next_turn: dict[str, Any] | None) -> None:
    if not next_turn or completed_turn.get("part") != "p3" or next_turn.get("part") != "p3":
        return
    if completed_turn.get("prompt", {}).get("role") != "main" or next_turn.get("prompt", {}).get("role") != "follow_up":
        return
    theme = str(completed_turn.get("prompt", {}).get("theme") or attempt.get("p3_theme") or "general speaking")
    prior_answer = str(completed_turn.get("transcript_cleaned") or completed_turn.get("transcript_raw") or "")
    plan = {
        **fallback_p3(theme, prior_answer, P3_MAIN_COUNT),
        "status": "skipped_sync_ai",
        "source": "adaptive_answer",
        "theme": theme,
    }
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


def insert_p1_identity_follow_up(state: AppState, attempt: dict[str, Any], completed_turn: dict[str, Any]) -> None:
    prompt = completed_turn.get("prompt") or {}
    if completed_turn.get("part") != "p1" or prompt.get("role") != "work_study":
        return
    turns = attempt.get("turns") or []
    try:
        completed_position = turns.index(completed_turn)
    except ValueError:
        return
    if completed_position + 1 < len(turns):
        next_prompt = turns[completed_position + 1].get("prompt") or {}
        if next_prompt.get("flow") == "intro" and next_prompt.get("role") == "follow_up":
            return
    answer = str(completed_turn.get("transcript_cleaned") or completed_turn.get("transcript_raw") or "")
    question = clean_report_text(fallback_p1_identity_follow_up(answer)) or fallback_p1_identity_follow_up("")
    follow_turn = create_turn(
        state,
        str(attempt["id"]),
        "p1",
        int(completed_turn.get("index") or 0),
        int(completed_turn.get("total") or P1_TURN_COUNT),
        question,
        {
            "topic": "intro",
            "question": question,
            "flow": "intro",
            "role": "follow_up",
            "after_role": "work_study",
            "after_turn": completed_turn.get("id"),
            "source": "identity_answer",
            "backend": "fallback",
            "generation_status": "skipped_sync_ai",
            "counts_toward_total": False,
        },
    )
    follow_turn["id"] = f"{completed_turn.get('id', 't2')}_followup"
    follow_turn["counts_toward_total"] = False
    follow_turn["examiner_tts"] = {
        "provider": "volcengine",
        "status": "pending",
        "audio_url": None,
        "message": "Identity follow-up uses deterministic fallback; examiner audio uses the normal TTS path.",
    }
    turns.insert(completed_position + 1, follow_turn)


def build_turns(state: AppState, attempt_id: str, mode: str, payload: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
    sample = state.bank.sample(P1_TURN_COUNT)
    metadata: dict[str, Any] = {}
    if mode == "mock":
        cue = sample["part2"]
        turns = build_p1_turns(state, attempt_id, P1_TURN_COUNT, P1_TURN_COUNT + 1)
        turns.append(create_turn(state, attempt_id, "p2", len(turns), P1_TURN_COUNT + 1, cue_to_text(cue), cue, cue))
        metadata = {
            "p3_generation_status": "pending_after_p2",
            "p3_generation_source": "p2_answer",
            "p3_theme": str(cue.get("p3_theme") or cue.get("title") or "general speaking"),
        }
        return "mock", "Full mock exam", turns, cue, metadata
    if mode == "p1":
        turns = build_p1_turns(state, attempt_id, P1_TURN_COUNT)
        return "p1", "Part 1 practice", turns, None, metadata
    if mode == "p2":
        cue = sample["part2"]
        return "p2", str(cue["title"]), [create_turn(state, attempt_id, "p2", 0, 1, cue_to_text(cue), cue, cue)], cue, metadata
    if mode == "p3":
        theme = str(payload.get("theme") or payload.get("topic") or "society and daily life").strip()
        intensity = str(payload.get("p3_intensity") or payload.get("intensity") or "high").strip().lower()
        if intensity not in {"normal", "high"}:
            intensity = "high"
        generated = {"id": attempt_id, "turns": []}
        append_p3_turns(state, generated, theme, str(payload.get("prior_answer") or ""), "topic", intensity)
        metadata = {
            "p3_generation_status": generated.get("p3_generation_status"),
            "p3_generation_source": generated.get("p3_generation_source"),
            "p3_generation_backend": generated.get("p3_generation_backend"),
            "p3_theme": theme,
            "p3_intensity": generated.get("p3_intensity"),
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


def clean_transcript_with_codex(
    transcript: str,
    question: str,
    part: str,
    billing: BillingStore | None = None,
    call_id: str | None = None,
) -> dict[str, Any]:
    fallback = clean_transcript(transcript)
    text = fallback["text"]
    if not text:
        return fallback
    prompt = f"""Clean this IELTS Speaking ASR transcript for report display.
Keep the candidate's meaning, wording level, grammar quality, hesitations, and any real mistakes.
Only fix obvious speech-recognition noise, broken punctuation, duplicated filler caused by ASR, and paragraph breaks.
Do not upgrade vocabulary, do not add new ideas, and do not make the answer sound better than the candidate.
For Part 2, split the answer into short Markdown paragraphs when the content naturally moves between idea, example, result, and conclusion.
Return only the cleaned transcript text.

Part: {part}
Question:
{question}

Raw ASR transcript:
{transcript}
"""
    try:
        output, _usage = run_codex(prompt, call_id or f"asr_clean_{hashlib.sha1(prompt.encode('utf-8')).hexdigest()[:20]}", billing)
        cleaned = clean_band7_output(output)
        if not cleaned or len(re.findall(r"[A-Za-z']+", cleaned)) < max(3, len(re.findall(r"[A-Za-z']+", text)) // 3):
            raise RuntimeError("codex ASR cleanup was too short")
        notes = [*fallback["notes"], "ASR text was lightly cleaned and paragraph-broken by local Codex CLI."]
        return {"text": cleaned, "notes": notes, "backend": "codex-cli"}
    except Exception as exc:  # noqa: BLE001 - ASR cleanup must not block scoring
        return {**fallback, "notes": [*fallback["notes"], f"AI ASR cleanup unavailable; used local cleanup: {exc}"], "backend": "fallback"}


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


def clean_markdown_text(value: str) -> str:
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
    text = clean_markdown_text(value)
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
    paragraphs = [" ".join(sentences[index:index + 2]) for index in range(0, len(sentences), 2)]
    return "\n\n".join(paragraphs)


def extract_codex_json_events(stdout: str, raw_path: Path | None = None) -> tuple[str, dict[str, Any] | None]:
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
    if raw_path and events:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text("\n".join(json_dumps(event) for event in events) + "\n", encoding="utf-8")
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


def run_codex(prompt: str, call_id: str, billing: BillingStore | None = None) -> tuple[str, dict[str, Any] | None]:
    if os.environ.get("IELTS_WEB_DISABLE_CODEX") == "1":
        raise RuntimeError("codex disabled by IELTS_WEB_DISABLE_CODEX=1")
    codex = shutil.which("codex") or "/opt/homebrew/bin/codex"
    if not shutil.which(codex) and not Path(codex).exists():
        raise RuntimeError("codex CLI not found")
    raw_path = billing.db_path.parent / "codex_jsonl" / f"{safe_slug(call_id)}.jsonl" if billing else None
    config_args = ["-c", f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"']
    try:
        result = subprocess.run(
            [codex, "exec", "--json", *config_args],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=45,
            check=True,
        )
        output, usage = extract_codex_json_events(result.stdout, raw_path)
    except Exception:
        result = subprocess.run([codex, "exec", *config_args], input=prompt, text=True, capture_output=True, timeout=45, check=True)
        output, usage = result.stdout, None
    if billing:
        billing.settle_usage(DEFAULT_USER_ID, call_id, usage)
    return output, usage


def plausible_spoken_answer(value: str) -> bool:
    text = clean_band7_output(value)
    words = re.findall(r"[A-Za-z']+", text)
    if len(words) < 12:
        return False
    lowered = text.lower()
    bad_markers = ("json", "requirements", "acceptance criteria", "here is", "i cannot", "as an ai")
    return not any(marker in lowered[:220] for marker in bad_markers)


def generic_band7_answer(value: str) -> bool:
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
    if part != "p1":
        return True
    relevance = prompt_relevance(question, answer)
    if relevance >= 0.20:
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
        return any(marker in lowered_answer for marker in ("yes", "no", "i do", "i don't", "i am", "i'm", "not really", "sometimes"))
    return False


def valid_turn_band7(question: str, answer: str, part: str) -> bool:
    return plausible_spoken_answer(answer) and not generic_band7_answer(answer) and band7_addresses_question(question, answer, part)


def concise_coaching_markdown(value: str) -> bool:
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
        re.match(r"^\s{2,}\d+\.\s+", line) for line in lines[grammar_index + 1 :]
    )
    return has_markdown_point and has_valid_grammar_detail and len(text) <= 1100


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


def _azure_prepare_audio(audio_path: Path) -> tuple[Path | None, Path, dict[str, Any] | None]:
    """Convert audio to WAV if needed. Returns (temp_wav, assessment_path, error_dict_or_None)."""
    if audio_path.suffix.lower() in {".wav"}:
        return None, audio_path, None
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None, audio_path, {
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
        return temp_wav, temp_wav, None
    except Exception as exc:  # noqa: BLE001
        return None, audio_path, {
            "provider": "azure",
            "status": "audio_conversion_failed",
            "pron_score": None,
            "accuracy": None,
            "fluency": None,
            "prosody": None,
            "issues": [],
            "message": f"Could not convert browser audio for Azure pronunciation assessment: {exc}",
        }


def _azure_not_configured_result() -> dict[str, Any]:
    return {
        "provider": "azure",
        "status": "not_configured",
        "pron_score": None,
        "accuracy": None,
        "fluency": None,
        "prosody": None,
        "issues": [],
        "message": "Azure Speech key/region is not configured; pronunciation is estimate only and not assessed.",
    }


def transcribe_and_assess_azure(audio_path: Path) -> dict[str, Any]:
    """Unified Azure call: transcribes audio AND scores pronunciation without needing a reference transcript.
    Returns dict with keys: transcript, pronunciation (same shape as pronunciation_from_azure output).
    """
    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        return {"transcript": "", "pronunciation": _azure_not_configured_result()}
    temp_wav, assessment_path, err = _azure_prepare_audio(audio_path)
    if err:
        return {"transcript": "", "pronunciation": err}
    try:
        import azure.cognitiveservices.speech as speechsdk  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"transcript": "", "pronunciation": {
            "provider": "azure", "status": "sdk_missing",
            "pron_score": None, "accuracy": None, "fluency": None, "prosody": None, "issues": [],
            "message": f"Azure Speech SDK is not installed: {exc}",
        }}
    try:
        speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
        speech_config.speech_recognition_language = "en-US"
        audio_config = speechsdk.audio.AudioConfig(filename=str(assessment_path))
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        pron_config = speechsdk.PronunciationAssessmentConfig(
            reference_text="",
            grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
            granularity=speechsdk.PronunciationAssessmentGranularity.Word,
            enable_miscue=False,
        )
        pron_config.enable_prosody_assessment()
        pron_config.apply_to(recognizer)

        done_event = threading.Event()
        all_results: list[dict[str, Any]] = []
        recognized_texts: list[str] = []

        def on_recognized(evt: Any) -> None:
            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech and evt.result.text:
                recognized_texts.append(evt.result.text)
                raw = evt.result.properties.get(speechsdk.PropertyId.SpeechServiceResponse_JsonResult)
                if raw:
                    all_results.append(json.loads(raw))

        def on_stopped(evt: Any) -> None:
            done_event.set()

        def on_canceled(evt: Any) -> None:
            done_event.set()

        recognizer.recognized.connect(on_recognized)
        recognizer.session_stopped.connect(on_stopped)
        recognizer.canceled.connect(on_canceled)
        recognizer.start_continuous_recognition()
        done_event.wait(timeout=60)
        recognizer.stop_continuous_recognition()

        full_transcript = " ".join(recognized_texts).strip()
        if not all_results:
            return {"transcript": full_transcript, "pronunciation": {
                "provider": "azure", "status": "no_speech",
                "pron_score": None, "accuracy": None, "fluency": None, "prosody": None, "issues": [],
                "message": "Azure did not detect any speech in the audio.",
            }}

        scores: list[dict[str, float]] = []
        all_issues: list[dict[str, Any]] = []
        for payload in all_results:
            nbest = payload.get("NBest", [{}])[0]
            assessment = nbest.get("PronunciationAssessment", {})
            if assessment.get("PronScore") is not None:
                scores.append({
                    "pron_score": float(assessment["PronScore"]),
                    "accuracy": float(assessment.get("AccuracyScore") or 0),
                    "fluency": float(assessment.get("FluencyScore") or 0),
                    "prosody": float(assessment.get("ProsodyScore") or 0),
                })
            for word_item in nbest.get("Words", []):
                word_assessment = word_item.get("PronunciationAssessment", {})
                if word_assessment.get("ErrorType") not in (None, "None"):
                    all_issues.append({
                        "word": word_item.get("Word"),
                        "accuracy": word_assessment.get("AccuracyScore"),
                        "error_type": word_assessment.get("ErrorType"),
                    })

        if not scores:
            return {"transcript": full_transcript, "pronunciation": {
                "provider": "azure", "status": "assessed",
                "pron_score": None, "accuracy": None, "fluency": None, "prosody": None,
                "issues": all_issues[:12],
                "message": "Azure recognized speech but pronunciation scores were not returned.",
            }}

        avg = lambda key: round(sum(s[key] for s in scores) / len(scores), 1)
        return {"transcript": full_transcript, "pronunciation": {
            "provider": "azure",
            "status": "assessed",
            "pron_score": avg("pron_score"),
            "accuracy": avg("accuracy"),
            "fluency": avg("fluency"),
            "prosody": avg("prosody"),
            "issues": all_issues[:12],
            "message": "Transcription and pronunciation assessed with Azure Speech (unreferenced).",
        }}
    except Exception as exc:  # noqa: BLE001
        return {"transcript": "", "pronunciation": {
            "provider": "azure", "status": "failed",
            "pron_score": None, "accuracy": None, "fluency": None, "prosody": None, "issues": [],
            "message": f"Azure transcription+pronunciation failed: {exc}",
        }}
    finally:
        if temp_wav:
            temp_wav.unlink(missing_ok=True)


def pronunciation_from_azure(audio_path: Path, transcript: str) -> dict[str, Any]:
    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        return _azure_not_configured_result()
    temp_wav, assessment_path, err = _azure_prepare_audio(audio_path)
    if err:
        return err
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


def band_advice(band: float | None, low: str, mid: str, high: str) -> str:
    if band is None:
        return low
    if band < 5.5:
        return low
    if band < 7.0:
        return mid
    return high


def base_criteria(band: float, label: str, transcript: str) -> dict[str, Any]:
    standards = {
        "fluency and coherence": (
            "Assesses whether answers are developed, logically connected, and spoken without excessive hesitation or repetition."
        ),
        "lexical resource": (
            "Assesses range and precision of vocabulary, including natural collocations and the ability to paraphrase."
        ),
        "grammar": (
            "Assesses sentence control, tense accuracy, clause variety, and whether errors reduce clarity."
        ),
    }
    advice = {
        "fluency and coherence": band_advice(
            band,
            "Build each answer with a direct point, one reason, and one concrete example before closing.",
            "Add contrast, consequence, and smoother linking so ideas feel connected rather than listed.",
            "Refine pacing and use clearer signposting when moving from reason to example to conclusion.",
        ),
        "lexical resource": band_advice(
            band,
            "Replace repeated basic words with topic-specific phrases copied from your Band 7 version.",
            "Paraphrase the question and add two or three natural collocations for the topic.",
            "Use more precise topic vocabulary while keeping the answer conversational.",
        ),
        "grammar": band_advice(
            band,
            "Prioritise complete simple sentences first, then add one because/when/although clause.",
            "Vary sentence openings and check tense consistency when giving examples.",
            "Reduce small accuracy slips in longer complex sentences.",
        ),
    }
    words = len(re.findall(r"[A-Za-z']+", transcript))
    sample_note = (
        "The sample is short or incomplete, so the advice focuses on building enough answer content."
        if words < 20
        else "The advice is a static IELTS reference for the current band range, not live AI-generated feedback."
    )
    return {
        "band": band,
        "standard": standards.get(label, standards["fluency and coherence"]),
        "focus": sample_note,
        "advice": advice.get(label, advice["fluency and coherence"]),
        "strengths": [standards.get(label, standards["fluency and coherence"])],
        "problems": [sample_note],
        "suggestion": advice.get(label, advice["fluency and coherence"]),
    }


def heuristic_score(transcript: str, reason: str, question: str = "", part: str = "") -> dict[str, Any]:
    words = re.findall(r"[A-Za-z']+", transcript)
    unique_ratio = len(set(word.lower() for word in words)) / max(1, len(words))
    if not words:
        base = 0.0
    elif part == "p1":
        if len(words) >= 220:
            base = 6.5
        elif len(words) >= 130:
            base = 6.0
        elif len(words) >= 70:
            base = 5.5
        elif len(words) >= 25:
            base = 5.0
        else:
            base = 4.5
    else:
        if len(words) >= 260:
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
    }
    scores["overall_band"] = rounded_overall(scores)
    feedback = f"Content score uses fallback estimate: {reason}. Record clear, relevant English answers for a more useful assessment."
    result = {**scores, "feedback": feedback, "backend": "heuristic", "word_count": len(words)}
    return cap_off_topic_score(calibrate_realistic_score(result, question, transcript, part), question, transcript)


def score_prompt_for_part(part: str) -> str:
    if part == "p1":
        return (
            "Section type: IELTS Speaking Part 1. Part 1 answers are normally short. "
            "Do not penalize a relevant answer just because it is not a long turn; 3-5 spoken sentences per question is enough. "
            "Score for relevance, clarity, basic sentence control, and natural short-answer development."
        )
    if part == "p2":
        return (
            "Section type: IELTS Speaking Part 2. Score the long-turn response by cue-card coverage, sustained development, "
            "coherence across the story, vocabulary range, and grammar control. Do not award 6.5+ for short, generic, "
            "memorized, or thinly developed long-turn answers."
        )
    if part == "p3":
        return (
            "Section type: IELTS Speaking Part 3. Score abstract discussion quality: clear opinions, reasons, examples, "
            "comparison, speculation, and ability to extend ideas. Do not award 6.5+ for brief opinions without reasons, "
            "examples, comparison, or abstract development."
        )
    return "Section type: full/mock IELTS Speaking section. Score the completed section as a whole."


def attempt_part(attempt: dict[str, Any]) -> str:
    mode = str(attempt.get("mode") or attempt.get("part") or "").lower()
    if mode in {"p1", "p2", "p3", "mock"}:
        return mode
    parts = {str(turn.get("part") or "").lower() for turn in attempt.get("turns", []) if turn.get("part")}
    if len(parts) == 1:
        return next(iter(parts))
    return ""


def score_with_codex(
    transcript: str,
    data_dir: Path,
    question: str = "",
    billing: BillingStore | None = None,
    call_id: str | None = None,
    part: str = "",
) -> dict[str, Any]:
    prompt_path = data_dir / "prompts" / "scorer_system.md"
    prompt = (
        prompt_path.read_text(encoding="utf-8")
        + "\n\nReturn JSON only with numeric keys fluency_coherence, lexical_resource, "
        "grammatical_range, overall_band, string key feedback, and optional overall_review object "
        "with string key comment and array key review_points. Do not score pronunciation or reference pronunciation. "
        + score_prompt_for_part(part)
        + "\n\nPrompt(s):\n"
        + (question.strip() or "(not provided)")
        + "\n\nTranscript:\n"
        + transcript
        + "\n"
    )
    output, usage = run_codex(prompt, call_id or f"score_{hashlib.sha1(prompt.encode('utf-8')).hexdigest()[:20]}", billing)
    payload = extract_json_object(output)
    scores: dict[str, Any] = {
        "fluency_coherence": clamp_band(payload.get("fluency_coherence")),
        "lexical_resource": clamp_band(payload.get("lexical_resource")),
        "grammatical_range": clamp_band(payload.get("grammatical_range")),
    }
    scores["overall_band"] = rounded_overall(scores)
    result_payload = {**scores, "feedback": str(payload.get("feedback", "")), "backend": "codex"}
    overall_review = payload.get("overall_review")
    if isinstance(overall_review, dict):
        comment = clean_report_text(str(overall_review.get("comment") or ""))
        points = [clean_report_text(str(item)) for item in overall_review.get("review_points") or []]
        points = [item for item in points if item][:4]
        if comment or points:
            result_payload["overall_review"] = {"comment": comment, "review_points": points, "source": "codex_score"}
    if usage:
        result_payload["billing_usage"] = billing.normalize_usage(usage) if billing else usage
    return cap_off_topic_score(calibrate_realistic_score(result_payload, question, transcript, part), question, transcript)


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


def model_answer_constraints(part: str) -> str:
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


def target_band(attempt: dict[str, Any]) -> float:
    try:
        value = float(attempt.get("target_band") or 7.0)
    except (TypeError, ValueError):
        value = 7.0
    return max(5.0, min(9.0, round(value * 2) / 2))


def target_band_label(attempt: dict[str, Any]) -> str:
    value = target_band(attempt)
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


def model_answer_with_codex(attempt: dict[str, Any], transcript: str, billing: BillingStore | None = None, call_id: str | None = None) -> str:
    part = attempt_part(attempt)
    target = target_band_label(attempt)
    prompt = (
        f"Write a natural IELTS Speaking Band {target} spoken version. Preserve the candidate's core ideas, "
        "but improve cohesion, vocabulary, and grammar. Do not include the original question or cue-card bullets. "
        "Format the answer as concise Markdown paragraphs with blank lines between paragraphs. "
        "Try to keep paragraph order aligned with the candidate transcript when the transcript has usable ideas. "
        "If the candidate transcript is too weak or lacks a conclusion, you may add a short closing paragraph. "
        "Return only the answer text: no title, no labels, no cue-card text, no logs.\n"
        + model_answer_constraints(part)
        + f"\n\nSection: {part or attempt.get('mode')}\nQuestions:\n{questions_text(attempt)}\n\nCandidate transcript:\n{transcript}\n"
    )
    output, _usage = run_codex(prompt, call_id or f"band7_{hashlib.sha1(prompt.encode('utf-8')).hexdigest()[:20]}", billing)
    cleaned = clean_band7_output(output)
    if not plausible_spoken_answer(cleaned):
        raise RuntimeError("codex model answer was not a plausible spoken answer")
    return cleaned


def questions_text(attempt: dict[str, Any]) -> str:
    lines: list[str] = []
    for turn in attempt.get("turns", []):
        prefix = "Intro" if not turn.get("counts_toward_total", True) else str(display_question_number(turn))
        lines.append(f"{prefix}. {turn['question']}")
    return "\n".join(lines)


def build_band7_version(state: AppState, attempt: dict[str, Any], transcript: str) -> str:
    if not transcript:
        return f"Record a full answer first. A Band {target_band_label(attempt)} spoken version will appear after the system has a transcript to work from."
    try:
        generated = model_answer_with_codex(attempt, transcript, state.billing, f"band7_attempt_{attempt['id']}")
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


def _transcript_usable_for_band7(question: str, transcript: str) -> bool:
    """Check if a transcript is coherent enough to quote in a Band 7 model answer."""
    if not transcript or len(transcript.split()) < 4:
        return False
    relevance = prompt_relevance(question, transcript)
    if relevance >= 0.25:
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
        "usually", "sometimes", "often", "actually", "probably", "maybe",
    }
    recognized = sum(1 for w in words if w.lower() in common_english)
    if recognized / len(words) < 0.35:
        return False
    return True


def _p1_question_only_answer(question: str, answer_lower: str = "") -> str:
    """Generate a clean Band 7 P1 answer based on the question type. Uses answer_lower only for intent direction (yes/no, study/work)."""
    lowered = question.lower()
    if "name" in lowered:
        return "My full name is Jasper Chen, but most people just call me Jasper."
    if lowered.startswith(("do you prefer", "would you prefer")) or ("prefer" in lowered and ("or" in lowered)):
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
    if "plan" in lowered and ("live" in lowered or "living" in lowered):
        if any(w in answer_lower for w in ("no", "not", "temporary", "move")):
            return "No, I don't plan to stay there long-term. It is just a temporary arrangement while I finish my studies, and after that I will probably move somewhere else."
        return "Yes, I think I will stay there for a while. The area is convenient and I have gotten used to the routine, so there is no strong reason to move."
    if "neighbourhood" in lowered or "neighbor" in lowered:
        return "Yes, I think it is a good place to live. It is quiet, safe, and close to public transport, which makes my daily commute quite easy."
    if "continue" in lowered and ("live" in lowered or "living" in lowered):
        if any(w in answer_lower for w in ("no", "not", "temporary", "move")):
            return "No, I don't plan to stay there long-term. It is just a temporary arrangement while I finish my studies, and after that I will probably move somewhere else."
        return "Yes, I think I will stay there for a while. The area is convenient and I have gotten used to the routine, so there is no strong reason to move."
    if any(word in lowered for word in ("live", "living", "hometown", "house", "apartment", "flat", "city")):
        return "I live in a fairly convenient area close to my university. I like it because transport and daily shopping are easy, and the neighbourhood is quiet enough to study."
    if any(word in lowered for word in ("favourite", "favorite", "like most", "enjoy most")):
        if "room" in lowered:
            return "My favourite room is my bedroom. It is cozy and quiet, and I spend most of my free time there reading or relaxing after a long day."
        if "food" in lowered:
            return "My favourite food is probably noodles. I grew up eating them and they remind me of home, plus they are quick and easy to prepare."
        return "My favourite would be the one that connects with my personal routine. It feels natural because I do it regularly and it always puts me in a good mood."
    if "fast food" in lowered or ("food" in lowered and "think" in lowered):
        return "I think fast food is convenient when you are busy and don't have much time to cook. But I try not to eat it too often because it is not very healthy."
    if any(word in lowered for word in ("think", "opinion", "important")):
        if any(w in answer_lower for w in ("yes", "yeah", "important", "of course")):
            return "Yes, I think it is quite important. It plays a meaningful role in people's daily lives and helps them maintain a sense of balance."
        if any(w in answer_lower for w in ("no", "not")):
            return "Not necessarily. I think it depends on the individual and their circumstances. For some people it matters a lot, but others might not feel the same way."
        return "I think it depends on the situation. For most people it probably matters, but personally I would say it is useful rather than essential."
    if "easy" in lowered or "difficult" in lowered or "hard" in lowered:
        if any(w in answer_lower for w in ("easy", "simple", "not hard", "fast")):
            return "I find it fairly easy, mainly because I have been doing it for a while now. Practice makes a big difference, and once you get used to it, it feels natural."
        if any(w in answer_lower for w in ("difficult", "hard", "struggle", "not easy")):
            return "I find it a bit difficult sometimes, especially when I am tired or in a hurry. But with practice it has gotten easier over time."
        return "I find it fairly easy, mainly because I have been doing it for a while now. Practice makes a big difference, and once you get used to it, it feels natural."
    if any(word in lowered for word in ("how often", "how much", "how long", "how many")):
        return "For me, it happens fairly regularly, maybe a few times a week. It has become part of my routine without me really noticing."
    if any(word in lowered for word in ("when", "last time", "recently")):
        return "The last time was not long ago, probably within the past week. I remember it quite clearly because it was a pleasant experience."
    if lowered.startswith(("do you", "are you", "is there", "can you", "have you")):
        if any(w in answer_lower for w in ("no", "not", "rarely", "hardly", "don't")):
            return "No, not really. It is not something I do very often, mainly because my schedule does not leave much time for it."
        return "Yes, I would say so. It is something I do fairly often, and I find it quite enjoyable because it fits naturally into my daily life."
    if "why" in lowered:
        return "The main reason is that it connects with my daily routine and gives me a sense of satisfaction. I think that is what makes it worth doing."
    if "what" in lowered and "enjoy" in lowered:
        return "What I enjoy most is the problem-solving aspect. Every day brings something different, and I like the feeling of figuring things out step by step."
    return "I would say it is something I experience quite often in my daily life. The main reason is that it connects with my routine and gives me a practical benefit."


def build_turn_band7_fallback(turn: dict[str, Any], transcript: str, target: str = "7") -> str:
    """Generate a rule-based Band 7 answer. Never quotes raw transcript — only uses it to detect intent direction."""
    question = clean_report_text(str(turn.get("question") or "this question")) or "this question"
    part = str(turn.get("part") or "").lower()
    answer_lower = clean_report_text(transcript).lower() if transcript else ""
    if part == "p1":
        attempt = turn.get("attempt") if isinstance(turn.get("attempt"), dict) else {}
        if is_p1_name_intro_turn(turn) and attempt:
            return p1_name_answer(attempt)
        return _p1_question_only_answer(question, answer_lower)
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


def turn_feedback_with_codex(
    attempt: dict[str, Any],
    turn: dict[str, Any],
    transcript: str,
    profile: dict[str, Any],
    billing: BillingStore | None = None,
    call_id: str | None = None,
) -> dict[str, str]:
    part = str(turn.get("part") or attempt_part(attempt)).lower()
    target = target_band_label(attempt)
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
{turn.get("question") or ""}

Candidate transcript:
{transcript or "(missing)"}

Learning profile:
{json_dumps(profile)}
"""
    output, _usage = run_codex(prompt, call_id or f"turn_feedback_{hashlib.sha1(prompt.encode('utf-8')).hexdigest()[:20]}", billing)
    payload = extract_json_object(output)
    band7 = clean_band7_output(str(payload.get("band7_version") or ""))
    coaching = clean_markdown_text(str(payload.get("ai_coaching") or ""))
    if not valid_turn_band7(str(turn.get("question") or ""), band7, part):
        raise RuntimeError("codex turn feedback did not include a question-aware Band 7 answer")
    coaching = ensure_grammar_correction_bullet(coaching, transcript)
    if not concise_coaching_markdown(coaching):
        raise RuntimeError("codex turn feedback did not include concise Markdown coaching")
    return {"band7_version": band7, "ai_coaching": coaching}


def build_turn_feedback(
    state: AppState,
    attempt: dict[str, Any],
    turn: dict[str, Any],
    allow_codex: bool = True,
    include_tts: bool = True,
) -> None:
    transcript = str(turn.get("transcript_cleaned") or turn.get("transcript_raw") or "").strip()
    target = target_band_label(attempt)
    profile = build_learning_profile(state, attempt)
    turn_context = {**turn, "attempt": attempt}
    generated: dict[str, str] = {}
    if allow_codex and transcript:
        try:
            generated = turn_feedback_with_codex(
                {**attempt, "turns": [turn]},
                turn,
                transcript,
                profile,
                state.billing,
                f"turn_feedback_{attempt['id']}_{turn['id']}",
            )
        except Exception as exc:  # noqa: BLE001 - report feedback must degrade cleanly
            turn["feedback_generation_error"] = str(exc)
    band7 = generated.get("band7_version") or str(turn.get("band7_version") or "")
    if not valid_turn_band7(str(turn.get("question") or ""), band7, str(turn.get("part") or "").lower()):
        band7 = build_turn_band7_fallback(turn_context, transcript, target)
    turn["band7_version"] = clean_report_text(band7) or build_turn_band7_fallback(turn_context, transcript, target)
    turn_part = str(turn.get("part") or "").lower()
    turn["band7_markdown"] = spoken_markdown(band7, turn_part) or spoken_markdown(turn["band7_version"], turn_part)
    turn["target_band_version"] = turn["band7_version"]
    turn["target_band_markdown"] = turn["band7_markdown"]
    turn["target_band"] = target
    if include_tts:
        current_audio = turn.get("model_audio") or {}
        if not current_audio.get("audio_url") and current_audio.get("status") not in {"ready", "cached"}:
            turn["model_audio"] = volcengine_tts(state, turn["band7_version"], role="model", cache_key=f"{attempt['id']}_{turn['id']}_band7")
    turn["upgrade_notes"] = build_upgrade_notes(transcript)
    coaching = generated.get("ai_coaching") or str(turn.get("ai_coaching") or "")
    if not concise_coaching_markdown(coaching):
        coaching = build_ai_coaching(turn, transcript, turn["band7_version"], profile=profile, allow_codex=False)
    turn["ai_coaching"] = clean_markdown_text(coaching)
    turn["feedback_generation_status"] = "ready"
    turn["feedback_generation_backend"] = "codex" if generated else "fallback"


def build_turn_band7(state: AppState, attempt: dict[str, Any], turn: dict[str, Any], include_coaching: bool = True) -> None:
    build_turn_feedback(state, attempt, turn, allow_codex=include_coaching, include_tts=True)


def schedule_turn_feedback_generation(state: AppState, attempt_id: str, turn_id: str) -> None:
    def worker() -> None:
        try:
            attempt = state.load_attempt(attempt_id)
            if attempt.get("status") in {"aborted", "scored"}:
                return
            turn = next((item for item in attempt.get("turns", []) if item.get("id") == turn_id), None)
            if not turn or turn.get("status") != "completed":
                return
            if turn.get("feedback_generation_status") == "ready" and turn.get("band7_version") and turn.get("ai_coaching"):
                return
            turn["feedback_generation_status"] = "generating"
            build_turn_feedback(state, attempt, turn, allow_codex=True, include_tts=True)
            feedback_fields = {
                key: turn.get(key)
                for key in (
                    "band7_version",
                    "band7_markdown",
                    "target_band_version",
                    "target_band_markdown",
                    "target_band",
                    "model_audio",
                    "upgrade_notes",
                    "ai_coaching",
                    "feedback_generation_status",
                    "feedback_generation_backend",
                    "feedback_generation_error",
                )
                if key in turn
            }
            latest = state.load_attempt(attempt_id)
            if latest.get("status") in {"aborted", "scored"}:
                return
            latest_turn = next((item for item in latest.get("turns", []) if item.get("id") == turn_id), None)
            if not latest_turn or latest_turn.get("status") != "completed":
                return
            latest_turn.update(feedback_fields)
            state.save_attempt(latest)
        except Exception as exc:  # noqa: BLE001 - background feedback must never break the speaking flow
            try:
                attempt = state.load_attempt(attempt_id)
                if attempt.get("status") in {"aborted", "scored"}:
                    return
                turn = next((item for item in attempt.get("turns", []) if item.get("id") == turn_id), None)
                if not turn:
                    return
                turn["feedback_generation_status"] = "failed"
                turn["feedback_generation_error"] = str(exc)
                state.save_attempt(attempt)
            except Exception:
                return

    threading.Thread(target=worker, name=f"ielts-turn-feedback-{safe_slug(attempt_id)}-{safe_slug(turn_id)}", daemon=True).start()


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


def answer_development_level(text: str) -> str:
    words = re.findall(r"[A-Za-z']+", text)
    if len(words) < 12:
        return "very short"
    if len(words) < 35:
        return "short"
    return "developed"


def transcript_word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z']+", text))


def repeated_phrases_from_texts(texts: list[str]) -> list[str]:
    candidates = [
        "it is very important",
        "it is very convenient",
        "in modern society",
        "from my perspective",
        "as far as i am concerned",
        "there are many advantages",
        "make me feel relaxed",
        "broaden my horizons",
        "learn more knowledge",
        "for example",
        "because it helps me",
        "one of the main reasons",
    ]
    counts: Counter[str] = Counter()
    for text in texts:
        lowered = text.lower()
        for phrase in candidates:
            if phrase in lowered:
                counts[phrase] += 1
    return [phrase for phrase, count in counts.items() if count >= 2]


def turn_habit_tags(turn: dict[str, Any], score: dict[str, Any] | None = None) -> list[str]:
    transcript = str(turn.get("transcript_cleaned") or turn.get("transcript_raw") or "").strip()
    part = str(turn.get("part") or "").lower()
    tags: set[str] = set()
    word_count = transcript_word_count(transcript)
    if not transcript:
        tags.add("missing_transcript")
    if word_count and word_count < 25:
        tags.add("short_answer")
    if part == "p2" and word_count and word_count < 90:
        tags.add("limited_development")
    if part == "p3" and word_count and word_count < 55:
        tags.add("limited_development")
    lowered = transcript.lower()
    if any(phrase in lowered for phrase in ("it is very important", "it is very convenient", "in modern society", "from my perspective", "as far as i am concerned")):
        tags.add("template_language")
    if transcript and len(set(re.findall(r"[A-Za-z']+", lowered))) < max(8, word_count // 2 or 8):
        tags.add("repeated_phrases")
    if score and isinstance(score.get("overall_band"), (int, float)) and float(score["overall_band"]) < 5.5:
        tags.add("low_band")
    if transcript and prompt_relevance(str(turn.get("question") or ""), transcript) < 0.20:
        tags.add("off_topic")
    if part == "p1" and word_count < 15:
        tags.add("too_short_p1")
    return sorted(tags)


def summarize_weak_history(weak_items: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: Counter[str] = Counter()
    parts: Counter[str] = Counter()
    phrases: list[str] = []
    evidence: list[str] = []
    for item in weak_items[:8]:
        part = str(item.get("part") or "").lower() or "unknown"
        parts[part] += 1
        for reason in item.get("weak_reason") or []:
            reasons[str(reason)] += 1
        question = short_question(str(item.get("question") or ""), 72)
        if question:
            evidence.append(f"{part.upper()} 弱项：{question}")
        transcript = str(item.get("transcript") or "").strip()
        if transcript:
            evidence.append(f"历史转写：{short_question(transcript, 90)}")
            phrases.extend(repeated_phrases_from_texts([transcript]))
    return {"reasons": reasons, "parts": parts, "phrases": sorted(set(phrases)), "evidence": evidence[:6]}


def part_focus_text(part: str, tags: list[str], score: dict[str, Any] | None = None) -> str:
    if part == "p2":
        if "short_answer" in tags or "limited_development" in tags:
            return "Part 2 需要先覆盖 cue card，并把答案展开到接近两分钟。"
        if "template_language" in tags:
            return "Part 2 模板痕迹偏重，先换成自己的经历说法。"
        return "Part 2 重点是把经历、细节和感受说完整。"
    if part == "p3":
        if "short_answer" in tags or "limited_development" in tags:
            return "Part 3 需要补上观点背后的原因、对比和例子。"
        return "Part 3 重点是做抽象讨论，不只停留在个人经历。"
    if part == "p1":
        return "Part 1 先做到直接回答，再补一个自然的小细节。"
    if score and isinstance(score.get("overall_band"), (int, float)) and float(score["overall_band"]) < 5.5:
        return "先把答案说完整、说具体，再追求高级表达。"
    return "先处理最影响分数的表达习惯。"

def infer_primary_focus(tags: list[str]) -> str:
    if "off_topic" in tags:
        return "task_relevance"
    if "short_answer" in tags or "limited_development" in tags:
        return "answer_development"
    if "template_language" in tags or "repeated_phrases" in tags:
        return "lexical_variety"
    if "low_band" in tags:
        return "answer_development"
    return "answer_development"


def build_learning_profile(state: AppState, attempt: dict[str, Any], score: dict[str, Any] | None = None) -> dict[str, Any]:
    turns = [turn for turn in attempt.get("turns", []) if turn.get("status") == "completed"]
    completed_transcripts = [
        str(turn.get("transcript_cleaned") or turn.get("transcript_raw") or "").strip()
        for turn in turns
        if str(turn.get("transcript_cleaned") or turn.get("transcript_raw") or "").strip()
    ]
    turn_tags: Counter[str] = Counter()
    part_focus: dict[str, str] = {}
    part_evidence: dict[str, list[str]] = {}
    evidence: list[str] = []
    for turn in turns:
        transcript = str(turn.get("transcript_cleaned") or turn.get("transcript_raw") or "").strip()
        if not transcript:
            continue
        tags = turn_habit_tags(turn, score)
        turn_tags.update(tags)
        part = str(turn.get("part") or "").lower()
        word_count = transcript_word_count(transcript)
        if part == "p2":
            evidence.append(f"P2 回答约 {word_count} 词，需要继续拉长展开。")
        elif part == "p3":
            evidence.append(f"P3 回答约 {word_count} 词，需要补上原因、对比或例子。")
        elif part == "p1":
            evidence.append(f"P1 回答约 {word_count} 词，需要更直接、更自然。")
        part_evidence.setdefault(part, []).append(short_question(transcript, 90))
    weak_summary = summarize_weak_history(state.training.weak_items(str(attempt.get("user_id") or DEFAULT_USER_ID)))
    turn_tags.update(weak_summary["reasons"].keys())
    turn_tags.update(weak_summary["phrases"])
    evidence.extend(weak_summary["evidence"])
    if score and score.get("feedback"):
        evidence.append(f"评分反馈：{short_question(str(score.get('feedback')), 90)}")
    parts = sorted({str(turn.get("part") or "").lower() for turn in turns if turn.get("part")})
    tags = sorted(tag for tag in turn_tags if tag and tag != "missing_transcript")
    for part in parts:
        focus = part_focus_text(part, tags, score)
        if weak_summary["parts"].get(part):
            focus = f"{focus} 历史弱项里也反复出现这一部分。"
        part_focus[part] = focus
    repeated_phrases = repeated_phrases_from_texts(completed_transcripts)
    for phrase in weak_summary["phrases"]:
        if phrase not in repeated_phrases:
            repeated_phrases.append(phrase)
    primary_focus = infer_primary_focus(tags)
    primary_focus_text = {
        "task_relevance": "这次主要问题是没有完全扣住题目，先把回答方向答准。",
        "answer_development": "这次主要卡在回答展开不够，不是题目完全不会。",
        "lexical_variety": "这次主要问题是表达重复或模板感重，需要换成更自然的说法。",
    }.get(primary_focus, "先处理最影响分数的一个说话习惯。")
    recurring_weak_reasons = sorted({str(reason) for reason in weak_summary["reasons"].keys()} | set(tags))
    return {
        "primary_focus": primary_focus,
        "primary_focus_text": primary_focus_text,
        "habit_tags": tags,
        "recurring_weak_reasons": recurring_weak_reasons[:10],
        "repeated_phrases": repeated_phrases[:6],
        "part_focus": part_focus,
        "part_evidence": part_evidence,
        "evidence": evidence[:8],
    }

def build_personalized_coaching(profile: dict[str, Any], attempt: dict[str, Any], score: dict[str, Any]) -> dict[str, Any]:
    focus = str(profile.get("primary_focus_text") or "先把答案说完整、说具体。")
    tags = [str(tag) for tag in profile.get("habit_tags") or []]
    evidence = [str(item) for item in profile.get("evidence") or []]
    repeated = [str(item) for item in profile.get("repeated_phrases") or []]
    headline = {
        "task_relevance": "先把题目答准，再去追求更高阶表达",
        "answer_development": "先补答案展开，不要只停在一句点到为止",
        "lexical_variety": "先把模板化表达换掉，改成更自然的说法",
    }.get(str(profile.get("primary_focus") or ""), "先处理最影响分数的说话习惯")
    next_practice: list[str] = []
    if "short_answer" in tags or "limited_development" in tags:
        next_practice.append('每题都按"直接回答 + 原因 + 例子 + 一句收尾"练 2 轮。')
    if "template_language" in tags or repeated:
        next_practice.append("把高频模板词替换成你自己的经历说法，先录 1 次再回听。")
    if "off_topic" in tags:
        next_practice.append("每次开口前先复述题目里的关键词，确认回答没有跑题。")
    if not next_practice:
        next_practice.extend([
            "先挑一题慢速录音，再对照 Band 7 版本改一遍。",
            "每次练习只修一个问题，避免一次想改太多。",
        ])
    return {
        "headline": headline,
        "focus": focus,
        "evidence": evidence[:5],
        "next_practice": next_practice[:3],
        "habit_tags": tags[:8],
    }


def overall_review_with_codex(
    profile: dict[str, Any],
    attempt: dict[str, Any],
    score: dict[str, Any],
    billing: BillingStore | None = None,
    call_id: str | None = None,
) -> str:
    """Generate AI-powered personalized overall review based on learning profile and performance."""
    band = score.get("overall_band")
    band_text = f"Band {band}" if isinstance(band, (int, float)) and not isinstance(band, bool) else "本次练习"
    part = attempt_part(attempt)
    turns_summary = "\n".join(
        f"Q{i+1}: {turn.get('question', '')[:60]}... → {turn.get('transcript_cleaned', turn.get('transcript_raw', ''))[:80]}..."
        for i, turn in enumerate(attempt.get("turns", [])[:5])
    )
    prompt = f"""请为这次 IELTS Speaking 练习生成中文总体点评与复盘重点。输出格式为 Markdown，包含两个部分。

要求：
- 第一部分「总体点评」：2-3 句话概括本次表现的核心问题和突破方向，结合用户画像给出针对性建议
-第二部分「复盘重点」：3-5 个具体可执行的改进建议，用 bullet list 呈现
- 语气要具体、实用、有针对性，避免空泛评价
- 可以稍长，不要限制 AI 内容，让建议充分展开
- 必须结合学习画像进行个性化点评

本次成绩：{band_text}
练习部分：{part}
评分详情：
- Fluency & Coherence: {score.get('fluency_coherence', '—')}
- Lexical Resource: {score.get('lexical_resource', '—')}
- Grammatical Range: {score.get('grammatical_range', '—')}

部分转写样本：
{turns_summary}

学习画像：
{json_dumps(profile)}

请输出 Markdown 格式的总体点评与复盘重点。"""
    output, _usage = run_codex(prompt, call_id or f"overall_review_{hashlib.sha1(prompt.encode('utf-8')).hexdigest()[:20]}", billing)
    return clean_markdown_text(output)


def build_overall_review(
    profile: dict[str, Any],
    coaching: dict[str, Any],
    attempt: dict[str, Any],
    score: dict[str, Any],
    billing: BillingStore | None = None,
    allow_codex: bool = True,
) -> dict[str, Any]:
    if allow_codex:
        try:
            markdown = overall_review_with_codex(profile, attempt, score, billing, f"overall_review_{attempt.get('id')}")
            if markdown and len(markdown) > 50:
                return {
                    "comment": "",
                    "review_points": [],
                    "markdown": markdown,
                    "source": "codex_personalized",
                }
        except Exception:
            pass
    score_review = score.get("overall_review")
    if isinstance(score_review, dict):
        band = score.get("overall_band")
        band_text = f"Band {band}" if isinstance(band, (int, float)) and not isinstance(band, bool) else "本次练习"
        comment = clean_report_text(str(score_review.get("comment") or ""))
        points = [clean_report_text(str(item)) for item in score_review.get("review_points") or []]
        points = [item for item in points if item][:4]
        if comment or points:
            if not comment:
                comment = f"{band_text} 的主要突破口：先处理最影响分数的说话习惯。"
            markdown_lines = [
                "### 总体点评",
                "",
                comment,
                "",
                "### 复盘重点",
                "",
                *[f"- {point}" for point in points],
            ]
            return {
                "comment": comment,
                "review_points": points or ["先选一题重录，确认答案有直接回答、原因和一个具体例子。"],
                "markdown": clean_markdown_text("\n".join(markdown_lines)),
                "source": "codex_score",
            }
    band = score.get("overall_band")
    band_text = f"Band {band}" if isinstance(band, (int, float)) and not isinstance(band, bool) else "本次练习"
    headline = str(coaching.get("headline") or "先处理最影响分数的说话习惯")
    focus = str(coaching.get("focus") or profile.get("primary_focus_text") or "先把答案说完整、说具体。")
    evidence = [str(item) for item in coaching.get("evidence") or profile.get("evidence") or [] if str(item).strip()]
    next_practice = [str(item) for item in coaching.get("next_practice") or [] if str(item).strip()]
    comment = f"{band_text} 的主要突破口：{headline}。{focus}"
    review_points = (next_practice + evidence)[:5]
    if not review_points:
        review_points = ["先选一题重录，确认答案有直接回答、原因和一个具体例子。"]
    markdown_lines = [
        "### 总体点评",
        "",
        comment,
        "",
        "### 复盘重点",
        "",
        *[f"- {point}" for point in review_points[:4]],
    ]
    return {
        "comment": clean_report_text(comment),
        "review_points": review_points[:4],
        "markdown": clean_markdown_text("\n".join(markdown_lines)),
        "source": "learning_profile",
    }


def ai_coaching_with_codex(
    turn: dict[str, Any],
    transcript: str,
    band7: str,
    profile: dict[str, Any] | None = None,
    billing: BillingStore | None = None,
    call_id: str | None = None,
) -> str:
    question = str(turn.get("question") or "this question")
    part = str(turn.get("part") or "").lower()
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
- 不要强制给“可以直接替换成”的英文句子；只有在确实有帮助时才自然给例句。
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
{json_dumps(profile or {})}
"""
    output, _usage = run_codex(prompt, call_id or f"coach_{hashlib.sha1(prompt.encode('utf-8')).hexdigest()[:20]}", billing)
    coaching = normalize_coaching_markdown(output)
    coaching = ensure_grammar_correction_bullet(coaching, transcript)
    if not concise_coaching_markdown(coaching):
        raise RuntimeError("codex coaching was too short")
    return coaching


def _coaching_reason_for_question(question_lower: str, part: str, transcript_words: int, transcript_usable: bool, tags: list[str]) -> str:
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
    if not transcript_usable:
        return "下一次练这题时，先把 Band 7 版本读出声 3 遍，熟悉句型后再脱稿说。"
    if "short_answer" in tags or "limited_development" in tags:
        return "下一次先用 20 秒把答案补完整，确保有直接回答 + 原因 + 细节。"
    if "template_language" in tags:
        return "下一次试着不用模板句，直接从自己的经历开始说。"
    if "off_topic" in tags:
        return "下一次先在心里复述题目关键词，确认每句话都在回答问题。"
    if any(w in question_lower for w in ("favourite", "favorite", "enjoy", "like")):
        return "下一次试着加一个具体的例子或场景，让答案更生动。"
    if any(w in question_lower for w in ("think", "opinion", "important")):
        return "下一次试着先表态再解释，避免绕圈子。"
    return "下一次对照 Band 7 版本，挑一句最想改的句型反复练 3 次。"


def build_ai_coaching(
    turn: dict[str, Any],
    transcript: str,
    band7: str = "",
    billing: BillingStore | None = None,
    call_id: str | None = None,
    profile: dict[str, Any] | None = None,
    allow_codex: bool = True,
) -> str:
    if profile is None and isinstance(billing, dict):
        profile = billing
        billing = None
    if profile is None and isinstance(call_id, dict):
        profile = call_id
        call_id = None
    if allow_codex and transcript.strip() and band7.strip():
        try:
            return ai_coaching_with_codex(turn, transcript, band7, profile, billing, call_id)
        except Exception:
            pass
    profile = profile or {}
    tags = [str(tag) for tag in profile.get("habit_tags") or []]
    repeated_phrases = [str(item) for item in profile.get("repeated_phrases") or []]
    part = str(turn.get("part") or "").lower()
    transcript_text = transcript.strip()
    transcript_words = transcript_word_count(transcript_text)
    question_text = short_question(str(turn.get("question") or "this question"), 120)
    question_lower = question_text.lower()
    transcript_usable = _transcript_usable_for_band7(question_text, transcript_text)
    evidence = short_question(transcript_text, 72) if transcript_text else "这次没有抓到完整转写。"
    reason = _coaching_reason_for_question(question_lower, part, transcript_words, transcript_usable, tags)
    next_action = _coaching_next_action(question_lower, part, transcript_usable, tags)
    no_transcript_hint = "转写不太清楚，先看 Band 7 版本学句型。"
    evidence_text = evidence if transcript_usable else no_transcript_hint

    seed = int(hashlib.sha1(f"{question_text}|{transcript_text}|{part}".encode("utf-8")).hexdigest()[:8], 16)
    opener_variants = [
        "这题先把回答方向钉住，再补一句原因。",
        "先别追求复杂词，先把主句说清楚。",
        "这一题重点是先直答，再补一个具体细节。",
        "先把身份/观点说明确，流畅度自然会上来。",
    ]
    action_variants = [
        "下次练习时，先完整说 2 句，再加 1 个生活化细节。",
        "先照着 Band 7 句型读 2-3 遍，再脱稿复述。",
        "这题先按“直接回答 + 原因”练熟，再加例子。",
        "先把语速放慢一点，保证每句都完整落地。",
    ]

    opener = opener_variants[seed % len(opener_variants)]
    action = action_variants[(seed // 7) % len(action_variants)]
    if not transcript_usable:
        opener = no_transcript_hint
    elif transcript_words < 16:
        opener = "这次回答偏短，建议至少说到 2 句完整句。"

    lines: list[str] = []
    lines.append("- AI 辅导生成失败，以下是系统默认建议。")
    lines.append(f"- 本题关键词：{question_text}")
    lines.append(f"- {opener}")
    lines.append(f"- {reason}")
    if transcript_usable and evidence_text:
        lines.append(f"- 这次转写里最需要处理的是：{evidence_text}")
    if repeated_phrases:
        lines.append(f"- 少重复这些表达：{', '.join(repeated_phrases[:2])}")

    concise_action = action if part in {"p1", "p3"} else next_action
    lines.append(f"- {concise_action}")
    return ensure_grammar_correction_bullet("\n".join(lines), transcript)


def score_for_part(turns: list[dict[str, Any]], part: str, fallback_score: dict[str, Any]) -> dict[str, Any]:
    part_turns = [turn for turn in turns if turn.get("part") == part]
    transcript = "\n".join(str(turn.get("transcript_cleaned") or turn.get("transcript_raw") or "") for turn in part_turns)
    if not part_turns:
        return {}
    part_score = heuristic_score(
        transcript,
        f"{part.upper()} section estimate",
        "\n".join(str(turn.get("question") or "") for turn in part_turns),
        part,
    )
    part_score["overall_band"] = rounded_overall(part_score)
    part_score = calibrate_realistic_score(
        part_score,
        "\n".join(str(turn.get("question") or "") for turn in part_turns),
        transcript,
        part,
    )
    return {
        "part": part,
        "turn_count": len(part_turns),
        "band": part_score.get("overall_band", fallback_score.get("overall_band")),
        "fluency_coherence": part_score.get("fluency_coherence", fallback_score.get("fluency_coherence")),
        "lexical_resource": part_score.get("lexical_resource", fallback_score.get("lexical_resource")),
        "grammatical_range": part_score.get("grammatical_range", fallback_score.get("grammatical_range")),
    }


def build_part_scores(attempt: dict[str, Any], score: dict[str, Any]) -> dict[str, dict[str, Any]]:
    turns = attempt.get("turns") or []
    return {
        part: score_for_part(turns, part, score)
        for part in ("p1", "p2", "p3")
        if any(turn.get("part") == part for turn in turns)
    }


def build_detailed_report(
    state: AppState,
    attempt: dict[str, Any],
    score: dict[str, Any],
    pronunciation: dict[str, Any],
    transcript: str,
) -> dict[str, Any]:
    score["overall_band"] = rounded_overall(score)
    score = calibrate_realistic_score(score, questions_text(attempt), transcript, attempt_part(attempt))
    summary = clean_report_text(str(score.get("feedback") or "")) or "Score generated from the completed speaking section."
    learning_profile = build_learning_profile(state, attempt, score)
    personalized_coaching = build_personalized_coaching(learning_profile, attempt, score)
    overall_review = build_overall_review(learning_profile, personalized_coaching, attempt, score, state.billing, allow_codex=True)
    for turn in attempt.get("turns", []):
        transcript_turn = str(turn.get("transcript_cleaned") or turn.get("transcript_raw") or "").strip()
        if not transcript_turn:
            continue
        if not turn.get("band7_version") or not turn.get("ai_coaching"):
            build_turn_feedback(state, attempt, turn, allow_codex=False, include_tts=True)
    return {
        "feedback_summary": summary,
        "ielts_score": score,
        "criteria_feedback": {
            "fluency_coherence": base_criteria(score["fluency_coherence"], "fluency and coherence", transcript),
            "lexical_resource": base_criteria(score["lexical_resource"], "lexical resource", transcript),
            "grammatical_range_accuracy": base_criteria(score["grammatical_range"], "grammar", transcript),
        },
        "part_scores": build_part_scores(attempt, score),
        "target_band": target_band(attempt),
        "band7_version": "",
        "band7_markdown": "",
        "target_band_version": "",
        "target_band_markdown": "",
        "model_audio": None,
        "upgrade_notes": build_upgrade_notes(transcript),
        "ai_coaching": clean_report_text(personalized_coaching.get("focus") or "先把答案说完整、说具体，再根据 Band 7 示例调整表达。"),
        "coaching_focus": personalized_coaching.get("focus") or "",
        "learning_profile": learning_profile,
        "personalized_coaching": personalized_coaching,
        "overall_review": overall_review,
        "report": {
            "candidate": str(attempt.get("candidate") or DEFAULT_CANDIDATE),
            "timestamp": attempt.get("timestamp") or now_iso(),
            "overall_band": score.get("overall_band"),
            "feedback_summary": summary,
        },
    }
class IELTSHandler(SimpleHTTPRequestHandler):
    state: AppState

    def end_headers(self) -> None:
        if self.path.endswith(("/app.js", "/styles.css", "/index.html")) or urlparse(self.path).path == "/":
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        path = urlparse(path).path
        if path == "/":
            path = "/index.html"
        return str(STATIC_DIR / unquote(path).lstrip("/"))

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[ielts-web] " + fmt % args + "\n")

    def should_proxy_django_path(self, path: str) -> bool:
        if path.startswith("/api/accounts/"):
            return True
        if path.startswith("/api/writing/"):
            cookie = self.headers.get("Cookie", "")
            return DJANGO_PROXY_WRITE_FIRST and (DJANGO_FORCE_WRITING_PROXY or "sessionid=" in cookie)
        if path.startswith("/api/ai/tasks/"):
            cookie = self.headers.get("Cookie", "")
            return "sessionid=" in cookie
        if self.is_django_corpus_path(path):
            cookie = self.headers.get("Cookie", "")
            return "sessionid=" in cookie
        if DJANGO_PROXY_SPEAKING_RUNTIME and self.is_django_speaking_runtime_path(path):
            cookie = self.headers.get("Cookie", "")
            return "sessionid=" in cookie
        return False

    def is_django_corpus_path(self, path: str) -> bool:
        return path in {
            "/api/p1-corpus",
            "/api/p2-corpus",
            "/api/language-takeaways",
            "/api/language-takeaways/translate",
        }

    def is_django_speaking_runtime_path(self, path: str) -> bool:
        if path == "/api/attempts/start":
            return True
        if re.fullmatch(r"/api/attempts/[^/]+/turns/[^/]+/(audio|complete)", path):
            return True
        if re.fullmatch(r"/api/attempts/[^/]+/(score|abort)", path):
            return True
        if re.fullmatch(r"/api/audio/[^/]+/[^/]+/candidate", path):
            return True
        return False

    def try_proxy_django(self, method: str, path_with_query: str, payload: dict[str, Any] | None = None) -> bool:
        path = urlparse(path_with_query).path
        if not self.should_proxy_django_path(path):
            return False
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        cookie = self.headers.get("Cookie")
        if cookie:
            headers["Cookie"] = cookie
        csrf_token = self.headers.get("X-CSRFToken")
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token
        request = urllib.request.Request(
            f"{DJANGO_BACKEND_URL}{path_with_query}",
            data=body,
            headers=headers,
            method=method,
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=DJANGO_PROXY_TIMEOUT_SECONDS) as response:
                self.forward_django_response(response.status, response.headers, response.read())
                return True
        except urllib.error.HTTPError as error:
            self.forward_django_response(error.code, error.headers, error.read())
            return True
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            if path.startswith("/api/accounts/"):
                self.send_error_json(HTTPStatus.SERVICE_UNAVAILABLE, f"Django backend unavailable: {error}")
                return True
            return False

    def try_proxy_django_raw(self, method: str, path_with_query: str, body: bytes, content_type: str | None = None) -> bool:
        path = urlparse(path_with_query).path
        if not self.should_proxy_django_path(path):
            return False
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        cookie = self.headers.get("Cookie")
        if cookie:
            headers["Cookie"] = cookie
        csrf_token = self.headers.get("X-CSRFToken")
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token
        request = urllib.request.Request(
            f"{DJANGO_BACKEND_URL}{path_with_query}",
            data=body,
            headers=headers,
            method=method,
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=DJANGO_PROXY_TIMEOUT_SECONDS) as response:
                self.forward_django_response(response.status, response.headers, response.read())
                return True
        except urllib.error.HTTPError as error:
            self.forward_django_response(error.code, error.headers, error.read())
            return True
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def forward_django_response(self, status: int, headers: Any, body: bytes) -> None:
        self.send_response(status)
        content_type = headers.get("Content-Type") or "application/json; charset=utf-8"
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for cookie in headers.get_all("Set-Cookie", []):
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        try:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            if self.try_proxy_django("GET", self.path):
                return
            if path == "/api/question-bank/summary":
                self.send_json(self.state.bank.summary())
                return
            if path == "/api/history":
                self.send_json({"items": self.state.history()})
                return
            if path == "/api/writing/summary":
                params = parse_qs(parsed_url.query)
                self.send_json(self.state.writing_summary((params.get("month") or [""])[0]))
                return
            if path == "/api/writing/prompts":
                params = parse_qs(parsed_url.query)
                task_type = (params.get("task_type") or [""])[0] or None
                self.send_json({"items": self.state.writing_bank.list(task_type)})
                return
            if path == "/api/training/weak-items":
                self.send_json({"items": self.state.training.weak_items(DEFAULT_USER_ID)})
                return
            if path == "/api/training/replay-queue":
                query = parsed_url.query
                limit = 10
                if query:
                    params = dict(part.split("=", 1) if "=" in part else (part, "") for part in query.split("&") if part)
                    try:
                        limit = max(1, min(50, int(params.get("limit") or 10)))
                    except ValueError:
                        limit = 10
                self.send_json({"items": self.state.training.replay_queue(DEFAULT_USER_ID, limit=limit, bank=self.state.bank)})
                return
            if path == "/api/billing/wallet":
                query = parsed_url.query
                params = dict(part.split("=", 1) if "=" in part else (part, "") for part in query.split("&") if part)
                self.send_json(self.state.billing.wallet(str(params.get("user_id") or DEFAULT_USER_ID)))
                return
            match = re.fullmatch(r"/api/history/([^/]+)", path)
            if match:
                self.send_json(self.state.load_report_attempt(match.group(1)))
                return
            match = re.fullmatch(r"/api/writing/entries/([^/]+)", path)
            if match:
                self.send_json(self.state.load_writing_entry(match.group(1)))
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

    def do_DELETE(self) -> None:
        try:
            path = urlparse(self.path).path
            match = re.fullmatch(r"/api/history/([^/]+)", path)
            if match:
                attempt_id = match.group(1)
                file_path = self.state.attempt_path(attempt_id)
                with self.state.lock:
                    if not file_path.exists():
                        self.send_error_json(HTTPStatus.NOT_FOUND, "Attempt not found")
                        return
                    file_path.unlink()
                    if self.state.latest_report and self.state.latest_report.get("id") == attempt_id:
                        self.state.latest_report = None
                self.send_json({"ok": True})
                return
            self.send_error_json(HTTPStatus.NOT_FOUND, "Unknown API endpoint")
        except Exception as exc:  # noqa: BLE001
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path
            turn_audio = re.fullmatch(r"/api/attempts/([^/]+)/turns/([^/]+)/audio", path)
            if turn_audio:
                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length) if content_length > 0 else b""
                if self.try_proxy_django_raw(
                    "POST",
                    self.path,
                    raw_body,
                    self.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip(),
                ):
                    return
                self._raw_body_override = raw_body
                self.handle_turn_audio_upload(turn_audio.group(1), turn_audio.group(2))
                return
            legacy_audio = re.fullmatch(r"/api/attempts/([^/]+)/audio", path)
            if legacy_audio:
                attempt = self.state.load_attempt(legacy_audio.group(1))
                self.handle_turn_audio_upload(legacy_audio.group(1), attempt["turns"][0]["id"])
                return
            payload = self.read_json_body()
            if self.try_proxy_django("POST", self.path, payload):
                return
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
            elif path == "/api/writing/prompts/random":
                self.handle_writing_random_prompt(payload)
            elif path == "/api/writing/entries":
                self.handle_writing_entry_save(payload)
            elif path == "/api/billing/reserve":
                call_id = str(payload.get("call_id") or "").strip()
                if not call_id:
                    raise ValueError("Missing call_id")
                reserved_u = int(payload.get("reserved_u") or 0)
                snapshot_id = str(payload.get("snapshot_id") or "") or None
                ttl_seconds = int(payload.get("ttl_seconds") or 24 * 60 * 60)
                self.send_json(self.state.billing.reserve_usage(str(payload.get("user_id") or DEFAULT_USER_ID), call_id, reserved_u, snapshot_id, ttl_seconds))
            elif path == "/api/billing/release":
                call_id = str(payload.get("call_id") or "").strip()
                if not call_id:
                    raise ValueError("Missing call_id")
                self.send_json(self.state.billing.release_reservation(str(payload.get("user_id") or DEFAULT_USER_ID), call_id))
            elif path == "/api/billing/reconcile":
                call_id = str(payload.get("call_id") or "").strip()
                if not call_id:
                    raise ValueError("Missing call_id")
                result = self.state.billing.reconcile_usage(str(payload.get("user_id") or DEFAULT_USER_ID), call_id, payload.get("usage"), str(payload.get("snapshot_id") or "") or None)
                self.send_json(result)
            elif path == "/api/billing/settle-usage":
                self.handle_billing_settle(payload)
            elif path == "/api/billing/recharge":
                amount_rmb = float(payload.get("amount_rmb") or 0)
                if amount_rmb <= 0:
                    raise ValueError("Amount must be positive")
                self.send_json(self.state.billing.recharge(str(payload.get("user_id") or DEFAULT_USER_ID), amount_rmb))
            else:
                turn_complete = re.fullmatch(r"/api/attempts/([^/]+)/turns/([^/]+)/complete", path)
                turn_feedback_regenerate = re.fullmatch(r"/api/attempts/([^/]+)/turns/([^/]+)/feedback/regenerate", path)
                turn_transcript_regenerate = re.fullmatch(r"/api/attempts/([^/]+)/turns/([^/]+)/transcript/regenerate", path)
                score_match = re.fullmatch(r"/api/attempts/([^/]+)/score", path)
                abort_match = re.fullmatch(r"/api/attempts/([^/]+)/abort", path)
                writing_score_match = re.fullmatch(r"/api/writing/entries/([^/]+)/score", path)
                if turn_complete:
                    self.handle_turn_complete(turn_complete.group(1), turn_complete.group(2), payload)
                elif turn_feedback_regenerate:
                    self.handle_turn_feedback_regenerate(turn_feedback_regenerate.group(1), turn_feedback_regenerate.group(2))
                elif turn_transcript_regenerate:
                    self.handle_turn_transcript_regenerate(turn_transcript_regenerate.group(1), turn_transcript_regenerate.group(2))
                elif score_match:
                    self.handle_attempt_score(score_match.group(1), payload)
                elif abort_match:
                    self.handle_attempt_abort(abort_match.group(1))
                elif writing_score_match:
                    self.handle_writing_entry_score(writing_score_match.group(1), payload)
                elif path == "/api/p3/questions" or path == "/api/p3/follow-up":
                    self.handle_p3(payload)
                else:
                    self.send_error_json(HTTPStatus.NOT_FOUND, "Unknown API endpoint")
        except Exception as exc:  # noqa: BLE001
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def do_PATCH(self) -> None:
        try:
            payload = self.read_json_body()
            if self.try_proxy_django("PATCH", self.path, payload):
                return
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
        full_name, english_name = candidate_names_from_payload(payload)
        part, title, turns, cue_card, metadata = build_turns(self.state, attempt_id, mode, payload)
        attempt = {
            "id": attempt_id,
            "timestamp": now_iso(),
            "status": "started",
            "user_id": str(payload.get("user_id") or DEFAULT_USER_ID),
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
        if attempt["turns"]:
            ensure_examiner_tts(self.state, attempt_id, attempt["turns"][0])
        self.state.save_attempt(attempt)
        self.send_json(attempt)

    def handle_writing_random_prompt(self, payload: dict[str, Any]) -> None:
        task_type = str(payload.get("task_type") or "").strip() or None
        self.send_json(self.state.random_writing_prompt(task_type))

    def handle_writing_entry_save(self, payload: dict[str, Any]) -> None:
        answer = str(payload.get("answer") or "")
        task_type = normalize_writing_task_type(str(payload.get("task_type") or ""))
        raw_prompt_id = str(payload.get("prompt_id") or "").strip()
        prompt_id = safe_slug(raw_prompt_id) if raw_prompt_id else ""
        prompt = self.state.writing_bank.get(prompt_id, task_type) if prompt_id else None
        prompt_text = clean_markdown_text(str(payload.get("prompt") or (prompt or {}).get("prompt") or ""))
        if not prompt_text:
            raise ValueError("Missing writing prompt")
        now = now_iso()
        raw_entry_id = str(payload.get("id") or "").strip()
        entry_id = safe_slug(raw_entry_id) if raw_entry_id else uuid.uuid4().hex
        existing: dict[str, Any] | None = None
        if payload.get("id"):
            try:
                existing = self.state.load_writing_entry(entry_id)
            except FileNotFoundError:
                existing = None
        created_at = str((existing or {}).get("created_at") or now)
        saved_at = now
        entry = {
            **(existing or {}),
            "id": entry_id,
            "user_id": str(payload.get("user_id") or (existing or {}).get("user_id") or DEFAULT_USER_ID),
            "created_at": created_at,
            "updated_at": now,
            "saved_at": saved_at,
            "practice_date": str(payload.get("practice_date") or (existing or {}).get("practice_date") or local_date_string(saved_at)),
            "status": "scored" if (existing or {}).get("status") == "scored" and (existing or {}).get("answer") == answer else "saved",
            "task_type": task_type,
            "task_label": WRITING_TASK_LABELS[task_type],
            "prompt_id": prompt_id or stable_writing_prompt_id(task_type, prompt_text),
            "title": clean_report_text(str(payload.get("title") or (prompt or {}).get("title") or "")) or WRITING_TASK_LABELS[task_type],
            "category": clean_report_text(str(payload.get("category") or (prompt or {}).get("category") or "")),
            "prompt": prompt_text,
            "answer": answer,
            "word_count": writing_word_count(answer),
        }
        if (existing or {}).get("answer") != answer:
            entry.pop("score", None)
            entry.pop("scored_at", None)
        self.state.save_writing_entry(entry)
        self.send_json(entry)

    def handle_writing_entry_score(self, entry_id: str, payload: dict[str, Any]) -> None:
        entry = self.state.load_writing_entry(entry_id)
        if payload.get("answer") is not None:
            entry["answer"] = str(payload.get("answer") or "")
            entry["word_count"] = writing_word_count(entry["answer"])
        if not str(entry.get("answer") or "").strip():
            raise ValueError("Write an answer before requesting AI scoring.")
        entry["updated_at"] = now_iso()
        entry["saved_at"] = entry.get("saved_at") or entry["updated_at"]
        entry["practice_date"] = entry.get("practice_date") or local_date_string(str(entry.get("saved_at") or ""))
        profile_before = self.state.load_writing_profile(str(entry.get("user_id") or DEFAULT_USER_ID))
        try:
            score = score_writing_with_codex(entry, self.state.data_dir, self.state.billing, profile_before)
        except Exception as exc:  # noqa: BLE001
            score = writing_fallback_score(str(entry.get("task_type") or "task2"), str(entry.get("answer") or ""), str(exc))
        entry["writing_profile"] = update_writing_profile(self.state, entry, score)
        entry["score"] = score
        entry["status"] = "scored"
        entry["scored_at"] = now_iso()
        entry["updated_at"] = entry["scored_at"]
        self.state.save_writing_entry(entry)
        self.send_json(entry)

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
        raw_body = getattr(self, "_raw_body_override", None)
        if raw_body is not None:
            delattr(self, "_raw_body_override")
        with audio_path.open("wb") as handle:
            handle.write(raw_body if raw_body is not None else self.rfile.read(content_length))
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
        browser_transcript = str(payload.get("transcript_raw") or payload.get("transcript") or "").strip()
        turn["duration_seconds"] = payload.get("duration_seconds")
        audio_path = Path((turn.get("audio") or {}).get("path", ""))
        if audio_path.exists():
            azure_result = transcribe_and_assess_azure(audio_path)
            azure_transcript = azure_result.get("transcript", "").strip()
            turn["pronunciation"] = azure_result["pronunciation"]
            transcript = azure_transcript or browser_transcript
            turn["transcript_source"] = "azure" if azure_transcript else "browser_dictation"
        else:
            transcript = browser_transcript
            turn["transcript_source"] = "browser_dictation"
            turn["pronunciation"] = {
                "provider": "azure",
                "status": "missing_audio",
                "pron_score": None,
                "accuracy": None,
                "fluency": None,
                "prosody": None,
                "issues": [],
                "message": "No candidate audio was uploaded; pronunciation is estimate only and not assessed.",
            }
        transcript_status = "captured" if transcript else "missing"
        cleaned = clean_transcript(transcript)
        turn["transcript_raw"] = transcript
        turn["transcript_cleaned"] = cleaned["text"]
        turn["transcript_markdown"] = spoken_markdown(cleaned["text"])
        turn["transcript_status"] = transcript_status
        turn["cleaning_notes"] = cleaned["notes"]
        apply_p1_name_identity(attempt, turn)
        turn["status"] = "completed"
        turn["feedback_generation_status"] = "pending"
        if (
            attempt.get("mode") == "mock"
            and turn.get("part") == "p2"
            and attempt.get("p3_generation_status") == "pending_after_p2"
        ):
            cue = attempt.get("cue_card") or {}
            theme = str(cue.get("p3_theme") or cue.get("title") or attempt.get("p3_theme") or "general speaking")
            prior_answer = turn.get("transcript_cleaned") or turn.get("transcript_raw") or ""
            append_p3_turns(self.state, attempt, theme, str(prior_answer), "p2_answer", allow_codex=False)
        insert_p1_identity_follow_up(self.state, attempt, turn)
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
            f"Q{display_question_number(turn) if turn.get('counts_toward_total', True) else 'Intro'}: {turn['question']}\nA: {turn.get('transcript_cleaned') or turn.get('transcript_raw') or ''}"
            for turn in completed
        )
        prompt_text = questions_text(attempt)
        part = attempt_part(attempt)
        attempt["target_band"] = target_band({"target_band": payload.get("target_band") or attempt.get("target_band") or 7.0})
        pronunciation = aggregate_pronunciation(completed)
        try:
            score = score_with_codex(transcript, self.state.data_dir, prompt_text, self.state.billing, f"score_attempt_{attempt_id}", part)
        except Exception as exc:  # noqa: BLE001
            score = heuristic_score(transcript, str(exc), prompt_text, part)
        for turn in completed:
            build_turn_band7(self.state, attempt, turn, include_coaching=True)
        detailed = build_detailed_report(self.state, attempt, score, pronunciation, transcript)
        attempt.update(detailed)
        attempt["transcript_cleaned"] = transcript
        attempt["training_observations"] = self.state.training.record_attempt(attempt)
        attempt["status"] = "scored"
        self.state.save_attempt(attempt)
        self.send_json(attempt)

    def handle_turn_feedback_regenerate(self, attempt_id: str, turn_id: str) -> None:
        attempt = self.state.load_report_attempt(attempt_id)
        turn = self.find_turn(attempt, turn_id)
        if turn.get("status") != "completed":
            raise ValueError("Only completed turns can regenerate AI feedback.")
        turn["feedback_generation_status"] = "generating"
        turn.pop("feedback_generation_error", None)
        build_turn_feedback(self.state, attempt, turn, allow_codex=True, include_tts=True)
        attempt["updated_at"] = now_iso()
        self.state.save_attempt(attempt)
        self.send_json({"ok": True, "attempt": attempt, "turn": turn})

    def handle_turn_transcript_regenerate(self, attempt_id: str, turn_id: str) -> None:
        attempt = self.state.load_report_attempt(attempt_id)
        turn = self.find_turn(attempt, turn_id)
        if turn.get("status") != "completed":
            raise ValueError("Only completed turns can regenerate transcript.")
        audio_path = Path((turn.get("audio") or {}).get("path", ""))
        if not audio_path.exists():
            raise ValueError("重新转写失败：这题没有可用录音文件。")

        result = transcribe_and_assess_azure(audio_path)
        transcript = str(result.get("transcript") or "").strip()
        pronunciation = result.get("pronunciation") or {}
        turn["pronunciation"] = pronunciation
        if not transcript:
            message = str(pronunciation.get("message") or "Azure did not return a transcript.")
            raise ValueError(f"重新转写失败：{message}")

        cleaned = clean_transcript(transcript)
        turn["transcript_raw"] = transcript
        turn["transcript_cleaned"] = cleaned["text"]
        turn["transcript_markdown"] = spoken_markdown(cleaned["text"])
        turn["transcript_status"] = "captured"
        turn["transcript_source"] = "azure_retranscribe"
        turn["cleaning_notes"] = cleaned["notes"]
        turn["feedback_generation_status"] = "generating"
        turn.pop("feedback_generation_error", None)
        build_turn_feedback(self.state, attempt, turn, allow_codex=True, include_tts=True)
        attempt["updated_at"] = now_iso()
        self.state.save_attempt(attempt)
        self.send_json({"ok": True, "attempt": attempt, "turn": turn})

    def handle_billing_settle(self, payload: dict[str, Any]) -> None:
        call_id = str(payload.get("call_id") or "").strip()
        if not call_id:
            raise ValueError("Missing call_id")
        usage = payload.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise ValueError("usage must be an object when provided")
        result = self.state.billing.settle_usage(
            str(payload.get("user_id") or DEFAULT_USER_ID),
            call_id,
            usage,
            str(payload.get("snapshot_id") or "") or None,
        )
        self.send_json(result)

    def handle_legacy_score(self, payload: dict[str, Any]) -> None:
        transcript = str(payload.get("transcript") or "").strip()
        question = str(payload.get("question") or "").strip()
        if not transcript:
            raise ValueError("Missing transcript")
        part = str(payload.get("part") or payload.get("mode") or "").lower()
        try:
            score = score_with_codex(
                transcript,
                self.state.data_dir,
                question,
                self.state.billing,
                f"score_legacy_{hashlib.sha1(transcript.encode('utf-8')).hexdigest()[:20]}",
                part,
            )
        except Exception as exc:  # noqa: BLE001
            score = heuristic_score(transcript, str(exc), question, part)
        report = {
            "timestamp": now_iso(),
            "candidate": str(payload.get("candidate") or DEFAULT_CANDIDATE),
            "mode": str(payload.get("mode") or "practice"),
            "parts": [{"part": str(payload.get("part") or "unknown"), "question": payload.get("question"), "transcript": transcript, "score": score}],
            "overall": {"band": score["overall_band"]},
            "feedback_summary": score.get("feedback") or "",
            "ielts_score": score,
        }
        self.state.latest_report = report
        self.send_json({"score": score, "report": report, "report_path": ""})

    def handle_p3(self, payload: dict[str, Any]) -> None:
        theme = str(payload.get("theme") or "general speaking")
        prior_answer = str(payload.get("prior_answer") or "")
        try:
            result = p3_with_codex(theme, prior_answer, self.state.billing)
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
            self.send_file_audio(path, str(audio.get("content_type") or "audio/mpeg"), cacheable=True)
            return
        self.send_error_json(HTTPStatus.NOT_FOUND, "Examiner audio not available")

    def send_legacy_audio(self, attempt_id: str, kind: str) -> None:
        attempt = self.state.load_attempt(attempt_id)
        if kind == "model":
            audio = attempt.get("model_audio") or {}
            self.send_file_audio(Path(str(audio.get("path") or "")), str(audio.get("content_type") or "audio/mpeg"), cacheable=True)
            return
        first = next((turn for turn in attempt.get("turns", []) if (turn.get("audio") or {}).get("path")), None)
        if not first:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Candidate audio not available")
            return
        audio = first.get("audio") or {}
        self.send_file_audio(Path(str(audio.get("path") or "")), str(audio.get("content_type") or ""))

    def send_tts_audio(self, role: str, filename: str) -> None:
        folder = self.state.examiner_audio_dir if role == "examiner" else self.state.model_audio_dir
        self.send_file_audio(folder / safe_slug(filename), "audio/mpeg", cacheable=True)

    def send_file_audio(self, path: Path, content_type: str = "", cacheable: bool = False) -> None:
        if not path.exists():
            self.send_error_json(HTTPStatus.NOT_FOUND, "Audio not available")
            return
        resolved_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        file_size = path.stat().st_size
        start = 0
        end = file_size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range", "").strip()
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
            if not match:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return
            start_text, end_text = match.groups()
            if start_text:
                start = int(start_text)
                end = int(end_text) if end_text else end
            elif end_text:
                suffix_length = int(end_text)
                start = max(file_size - suffix_length, 0)
            if file_size <= 0 or start >= file_size or start > end:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return
            end = min(end, file_size - 1)
            status = HTTPStatus.PARTIAL_CONTENT

        content_length = max(0, end - start + 1)
        self.send_response(status)
        self.send_header("Content-Type", resolved_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Last-Modified", self.date_time_string(path.stat().st_mtime))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Cache-Control", "public, max-age=86400, immutable" if cacheable else "no-store")
        self.end_headers()
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = content_length
            while remaining > 0:
                chunk = handle.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

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
    print("Set IELTS_WEB_DISABLE_CODEX=1 or IELTS_WEB_DISABLE_VOLCENGINE_TTS=1 to force fallbacks.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down IELTS Web UI")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
