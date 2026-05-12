#!/usr/bin/env python3
"""Voice-first web boundary for the IELTS Speaking Simulator.

The browser receives only JSON contracts. Audio, reports, CLI integrations, and
TTS/scoring credentials stay on the server side.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
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
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
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
P1_INTRO_QUESTIONS = [
    {
        "topic": "intro",
        "question": "What is your full name?",
        "flow": "intro",
        "role": "name",
    },
    {
        "topic": "intro",
        "question": "Do you work, study at university, or go to school?",
        "flow": "intro",
        "role": "work_study",
    },
]
P3_MAIN_COUNT = 5
P3_TURN_COUNT = 10
DEFAULT_CANDIDATE = "jasper"
DEFAULT_USER_ID = "local-default"
CODEX_REASONING_EFFORT = "low"
MICRO_RMB_PER_RMB = 1_000_000
DEFAULT_INITIAL_GRANT_U = 5 * MICRO_RMB_PER_RMB


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


def pronunciation_missing_text_only_cap(part: str, word_count: int, template_like: bool, generic_repeat: bool, development_count: int) -> float:
    if part == "p2":
        if word_count < 35:
            return 4.5
        if template_like or generic_repeat:
            return 5.0
        if word_count < 80 or development_count < 2:
            return 5.5
        return 6.0 if word_count < 130 else 6.5
    if part == "p3":
        if word_count < 25:
            return 4.5
        if template_like or generic_repeat:
            return 5.0
        if word_count < 55 or development_count < 2:
            return 5.5
        return 6.0 if word_count < 150 else 6.5
    if part == "p1":
        if word_count < 8:
            return 4.5
        if template_like or generic_repeat:
            return 5.5
        if word_count < 25:
            return 6.0
        if word_count < 60:
            return 6.5
        return 7.0
    if word_count < 60:
        return 5.5
    return 6.5


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

    if scores.get("pronunciation_estimate") is None and isinstance(scores.get("overall_band"), (int, float)):
        text_only_cap = pronunciation_missing_text_only_cap(part, word_count, template_like, template_count >= 2, marker_count)
        if float(scores["overall_band"]) > text_only_cap:
            scores["overall_band"] = text_only_cap
            append_calibration_note(scores, "Calibration: pronunciation was not assessed, so text-only scoring is capped conservatively.")

    scores["overall_band"] = rounded_overall(scores)
    if scores.get("pronunciation_estimate") is None and isinstance(scores.get("overall_band"), (int, float)):
        text_only_cap = pronunciation_missing_text_only_cap(part, word_count, template_like, template_count >= 2, marker_count)
        scores["overall_band"] = min(float(scores["overall_band"]), text_only_cap)
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
            if (turn.get("pronunciation") or {}).get("status") not in {"assessed"}:
                reasons.append("pronunciation_unreliable")
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
                "pronunciation_estimate": score.get("pronunciation_estimate"),
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
    training: TrainingStore = field(init=False)
    billing: BillingStore = field(init=False)
    latest_report: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.bank = QuestionBank(self.data_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.attempts_dir.mkdir(parents=True, exist_ok=True)
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
    intro_count = min(len(P1_INTRO_QUESTIONS), total)
    remaining_count = max(0, total - intro_count)
    ordinary_pool = [
        item
        for item in state.bank.p1
        if not is_p1_work_study_identity_question(str(item.get("question") or ""))
    ]
    if len(ordinary_pool) < remaining_count:
        raise ValueError("Not enough ordinary IELTS Part 1 questions after reserving intro identity turns.")
    ordinary_questions = random.sample(ordinary_pool, remaining_count)
    turn_items = P1_INTRO_QUESTIONS[:intro_count] + ordinary_questions
    return [
        create_turn(
            state,
            attempt_id,
            "p1",
            index,
            display_total or len(turn_items),
            item["question"],
            {
                "topic": item["topic"],
                "question": item["question"],
                **({"flow": item["flow"], "role": item["role"]} if item.get("flow") else {}),
            },
        )
        for index, item in enumerate(turn_items)
    ]


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
) -> None:
    plan = generate_p3_plan(theme, prior_answer, source, state.billing)
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
    plan = generate_p3_plan(theme, prior_answer, "adaptive_answer", state.billing)
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
    plan = generate_p1_identity_follow_up(
        str(completed_turn.get("transcript_cleaned") or completed_turn.get("transcript_raw") or ""),
        state.billing,
    )
    question = clean_report_text(plan.get("question") or "") or fallback_p1_identity_follow_up("")
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
            "backend": plan.get("backend", "fallback"),
            "generation_status": plan.get("status", "fallback"),
            "counts_toward_total": False,
        },
    )
    follow_turn["id"] = f"{completed_turn.get('id', 't2')}_followup"
    follow_turn["counts_toward_total"] = False
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


def spoken_markdown(value: str) -> str:
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
            "message": "Azure Speech key/region is not configured; pronunciation is estimate only and not assessed.",
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
        "pronunciation_estimate": None,
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
        "grammatical_range, overall_band, and string key feedback. Do not invent a "
        "pronunciation score from text. "
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
        "pronunciation_estimate": None,
    }
    scores["overall_band"] = rounded_overall(scores)
    result_payload = {**scores, "feedback": str(payload.get("feedback", "")), "backend": "codex"}
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
            "This is IELTS Speaking Part 1. Write a short natural answer, normally 3 sentences, maximum 5 sentences. "
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


def model_answer_with_codex(attempt: dict[str, Any], transcript: str, billing: BillingStore | None = None, call_id: str | None = None) -> str:
    part = attempt_part(attempt)
    prompt = (
        "Write a natural IELTS Speaking Band 7 spoken version. Preserve the candidate's core ideas, "
        "but improve cohesion, vocabulary, and grammar. Do not include the original question or cue-card bullets. "
        "Format the answer as concise Markdown paragraphs with blank lines between paragraphs. "
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
    return "\n".join(f"{turn['index'] + 1}. {turn['question']}" for turn in attempt.get("turns", []))


def build_band7_version(state: AppState, attempt: dict[str, Any], transcript: str) -> str:
    if not transcript:
        return "Record a full answer first. A Band 7 spoken version will appear after the system has a transcript to work from."
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


def build_turn_band7_fallback(turn: dict[str, Any], transcript: str) -> str:
    if not transcript:
        return "A complete transcript was not captured, so this model answer is a general spoken example for the same question."
    question = str(turn.get("question") or "this topic")
    part = str(turn.get("part") or "").lower()
    words = [
        word.lower()
        for word in re.findall(r"[A-Za-z']+", question)
        if len(word) > 3 and word.lower() not in {"describe", "should", "would", "could", "about", "your"}
    ]
    topic_hint = " ".join(words[:5]) or "this topic"
    if part == "p1":
        return (
            f"I'd say {topic_hint} is quite easy for me to answer because it connects with my daily life. "
            "For example, I can give one simple detail from my own experience instead of only saying yes or no. "
            "That makes the answer sound clearer and more natural."
        )
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
            band7 = model_answer_with_codex({**attempt, "turns": [turn]}, transcript, state.billing, f"band7_turn_{attempt['id']}_{turn['id']}")
        except Exception:
            band7 = ""
    if not plausible_spoken_answer(band7):
        band7 = build_turn_band7_fallback(turn, transcript)
    turn["band7_version"] = clean_report_text(band7) or build_turn_band7_fallback(turn, transcript)
    turn["band7_markdown"] = spoken_markdown(band7) or spoken_markdown(turn["band7_version"])
    turn["model_audio"] = volcengine_tts(state, turn["band7_version"], role="model", cache_key=f"{attempt['id']}_{turn['id']}_band7")
    turn["upgrade_notes"] = build_upgrade_notes(transcript)
    turn["ai_coaching"] = build_ai_coaching(
        turn,
        transcript,
        turn["band7_version"],
        state.billing,
        f"coach_turn_{attempt['id']}_{turn['id']}",
    )


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


def ai_coaching_with_codex(
    turn: dict[str, Any],
    transcript: str,
    band7: str,
    billing: BillingStore | None = None,
    call_id: str | None = None,
) -> str:
    question = str(turn.get("question") or "this question")
    part = str(turn.get("part") or "").lower()
    part_hint = {
        "p1": "Part 1 guidance: be concise. Coach toward a 3-sentence answer: direct answer, reason, one detail.",
        "p2": "Part 2 guidance: coach toward cue-card coverage, story structure, and sustained development.",
        "p3": "Part 3 guidance: coach toward abstract reasoning, comparison, examples, and clearer stance.",
    }.get(part, "Coach according to the IELTS Speaking part.")
    prompt = (
        "Generate AI coaching for one IELTS Speaking answer. Return Markdown only, no title. "
        "Compare the candidate's recording transcript with the Band 7 spoken version. "
        "Be specific: mention one thing the candidate already said, one missing improvement, and one next sentence pattern to try. "
        "Keep it concise: 2-4 short bullets or one short paragraph.\n"
        f"{part_hint}\n\nQuestion:\n{question}\n\nCandidate transcript:\n{transcript or '(missing)'}\n\nBand 7 spoken version:\n{band7}\n"
    )
    output, _usage = run_codex(prompt, call_id or f"coach_{hashlib.sha1(prompt.encode('utf-8')).hexdigest()[:20]}", billing)
    coaching = clean_report_text(output)
    if not coaching or len(re.findall(r"[A-Za-z']+", coaching)) < 12:
        raise RuntimeError("codex coaching was too short")
    return coaching


def build_ai_coaching(
    turn: dict[str, Any],
    transcript: str,
    band7: str = "",
    billing: BillingStore | None = None,
    call_id: str | None = None,
) -> str:
    if transcript.strip() and band7.strip():
        try:
            return ai_coaching_with_codex(turn, transcript, band7, billing, call_id)
        except Exception:
            pass
    question = short_question(str(turn.get("question") or "this question"), 120)
    level = answer_development_level(transcript)
    band7_words = re.findall(r"[A-Za-z']+", band7)
    band7_has_example = any(word in band7.lower() for word in ("for example", "especially", "because", "so ", "when "))
    if not transcript.strip():
        coaching = (
            f"For \"{question}\", the transcript was missing, so the Band 7 version is only a general model. "
            "Next time, make sure the recording captures a full spoken answer, then compare your real wording with the model."
        )
    elif level in {"very short", "short"}:
        coaching = (
            f"Your answer to \"{question}\" is {level}, while the Band 7 version develops the idea into about "
            f"{len(band7_words)} words with a clearer reason"
            f"{' and example' if band7_has_example else ''}. Next time, keep your original idea but add: "
            "1) a direct answer, 2) one reason, and 3) one concrete detail from your life."
        )
    else:
        coaching = (
            f"Your answer to \"{question}\" already gives usable content. Compared with the Band 7 version, "
            "the main upgrade is clearer organisation and more natural linking between the point and the example. "
            "Next time, start with the answer in one sentence, then add a specific example and a short result or contrast."
        )
    return clean_report_text(coaching)


def score_for_part(turns: list[dict[str, Any]], part: str, fallback_score: dict[str, Any], pronunciation: dict[str, Any]) -> dict[str, Any]:
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
    pron = aggregate_pronunciation(part_turns)
    pron_band = None
    if pron.get("status") == "assessed" and pron.get("pron_score") is not None:
        pron_band = clamp_band(float(pron["pron_score"]) / 100.0 * 9.0)
    part_score["pronunciation_estimate"] = pron_band
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
        "pronunciation_estimate": part_score.get("pronunciation_estimate"),
        "pronunciation_status": pron.get("status") or pronunciation.get("status"),
    }


def build_part_scores(attempt: dict[str, Any], score: dict[str, Any], pronunciation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    turns = attempt.get("turns") or []
    return {
        part: score_for_part(turns, part, score, pronunciation)
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
    pron_band = None
    if pronunciation.get("status") == "assessed" and pronunciation.get("pron_score") is not None:
        pron_band = clamp_band(float(pronunciation["pron_score"]) / 100.0 * 9.0)
    score["pronunciation_estimate"] = pron_band
    score["overall_band"] = rounded_overall(score)
    score = calibrate_realistic_score(score, questions_text(attempt), transcript, attempt_part(attempt))
    summary = clean_report_text(str(score.get("feedback") or "")) or "Score generated from the completed speaking section."
    band7 = clean_report_text(build_band7_version(state, attempt, transcript))
    final_band7 = band7 or build_band7_version(state, attempt, transcript)
    model_tts = volcengine_tts(state, final_band7, role="model", cache_key=f"{attempt['id']}_band7")
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
                "standard": "Assesses intelligibility, individual sound control, word stress, rhythm, and how naturally speech can be followed.",
                "focus": "Pronunciation estimate only / Azure Speech is not configured." if pron_band is None else "Pronunciation was estimated from uploaded turn audio.",
                "advice": "Configure Azure Speech for real pronunciation scoring." if pron_band is None else "Review low-accuracy words and repeat the model answer aloud.",
                "strengths": [] if pron_band is None else ["Pronunciation was estimated from uploaded turn audio."],
                "problems": pronunciation.get("issues", []) or [pronunciation.get("message", "Pronunciation estimate only / Azure Speech is not configured.")],
                "suggestion": "Configure Azure Speech for real pronunciation scoring." if pron_band is None else "Review low-accuracy words and repeat the model answer aloud.",
            },
        },
        "part_scores": build_part_scores(attempt, score, pronunciation),
        "band7_version": final_band7,
        "band7_markdown": spoken_markdown(final_band7),
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
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            if path == "/api/question-bank/summary":
                self.send_json(self.state.bank.summary())
                return
            if path == "/api/history":
                self.send_json({"items": self.state.history()})
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
            "user_id": str(payload.get("user_id") or DEFAULT_USER_ID),
            "mode": mode,
            "part": part,
            "title": title,
            "question": turns[0]["question"] if turns else "",
            "cue_card": cue_card,
            "turns": turns,
            "current_turn": turns[0]["id"] if turns else None,
            "candidate": str(payload.get("candidate") or DEFAULT_CANDIDATE),
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
        turn["transcript_markdown"] = spoken_markdown(cleaned["text"])
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
            "message": "No candidate audio was uploaded; pronunciation is estimate only and not assessed.",
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
            f"Q{turn['index'] + 1}: {turn['question']}\nA: {turn.get('transcript_cleaned') or turn.get('transcript_raw') or ''}"
            for turn in completed
        )
        prompt_text = questions_text(attempt)
        part = attempt_part(attempt)
        pronunciation = aggregate_pronunciation(completed)
        try:
            score = score_with_codex(transcript, self.state.data_dir, prompt_text, self.state.billing, f"score_attempt_{attempt_id}", part)
        except Exception as exc:  # noqa: BLE001
            score = heuristic_score(transcript, str(exc), prompt_text, part)
        detailed = build_detailed_report(self.state, attempt, score, pronunciation, transcript)
        attempt.update(detailed)
        for turn in completed:
            build_turn_band7(self.state, attempt, turn)
        attempt["transcript_cleaned"] = transcript
        attempt["training_observations"] = self.state.training.record_attempt(attempt)
        attempt["status"] = "scored"
        self.state.save_attempt(attempt)
        self.send_json(attempt)

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
