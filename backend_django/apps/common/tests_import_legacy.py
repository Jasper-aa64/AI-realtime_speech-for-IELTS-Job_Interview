import json
import sqlite3
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from apps.billing.models import LegacyBillingUser, WalletLedgerEntry
from apps.speaking.models import SpeakingAttempt, SpeakingTrainingObservation
from apps.writing.models import WritingEntry, WritingLearnerProfile


class ImportLegacyDataCommandTests(TestCase):
    def test_imports_legacy_sqlite_and_json_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp)
            self.write_billing_db(reports / "billing" / "billing.sqlite3")
            self.write_training_db(reports / "training" / "training.sqlite3")
            attempts_dir = reports / "attempts"
            writing_dir = reports / "writing"
            profile_dir = reports / "writing_profiles"
            attempts_dir.mkdir(parents=True)
            writing_dir.mkdir(parents=True)
            profile_dir.mkdir(parents=True)
            (attempts_dir / "attempt_1.json").write_text(
                json.dumps(
                    {
                        "id": "attempt_1",
                        "user_id": "local-default",
                        "mode": "p1",
                        "part": "p1",
                        "status": "scored",
                        "turns": [
                            {
                                "id": "turn_1",
                                "part": "p1",
                                "question": "What is your full name?",
                                "transcript_cleaned": "My full name is LiHua.",
                            }
                        ],
                        "ielts_score": {"overall_band": 5.0, "fluency_coherence": 5.0, "lexical_resource": 5.0, "grammatical_range": 5.0},
                    }
                ),
                encoding="utf-8",
            )
            (writing_dir / "entry_1.json").write_text(
                json.dumps(
                    {
                        "id": "entry_1",
                        "user_id": "local-default",
                        "task_type": "task2",
                        "practice_date": "2026-05-14",
                        "prompt_id": "prompt_1",
                        "title": "Technology",
                        "prompt": "Discuss technology.",
                        "answer": "Technology helps students.",
                        "word_count": 3,
                        "status": "scored",
                        "score": {"overall_band": 4.5, "task_response": 4.5, "feedback_markdown": "- Needs development."},
                    }
                ),
                encoding="utf-8",
            )
            (profile_dir / "local-default.json").write_text(
                json.dumps(
                    {
                        "user_id": "local-default",
                        "total_scored": 1,
                        "average_overall_band": 4.5,
                        "tag_counts": {"under_length": 1},
                        "primary_focus": "under_length",
                    }
                ),
                encoding="utf-8",
            )

            call_command("import_legacy_data", "--reports-dir", str(reports))

        self.assertEqual(LegacyBillingUser.objects.count(), 1)
        self.assertEqual(WalletLedgerEntry.objects.count(), 1)
        self.assertEqual(SpeakingAttempt.objects.count(), 1)
        self.assertEqual(SpeakingTrainingObservation.objects.count(), 1)
        self.assertEqual(WritingEntry.objects.count(), 1)
        self.assertEqual(WritingLearnerProfile.objects.get().total_scored, 1)

    def write_billing_db(self, path: Path) -> None:
        path.parent.mkdir(parents=True)
        conn = sqlite3.connect(path)
        try:
            conn.executescript(
                """
                CREATE TABLE users (
                    user_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    balance_u INTEGER NOT NULL,
                    reserved_u INTEGER NOT NULL DEFAULT 0,
                    carry_numerator_u INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE wallet_ledger_entries (
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
                CREATE TABLE codex_usage_events (
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
                CREATE TABLE price_snapshots (
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
                CREATE TABLE wallet_reservations (
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
            conn.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("local-default", "Local user", 5_000_000, 0, 0, "active", "2026-05-14T00:00:00+00:00", "2026-05-14T00:00:00+00:00"),
            )
            conn.execute(
                "INSERT INTO wallet_ledger_entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("entry_1", "local-default", None, "grant", 5_000_000, None, None, "grant:initial:local-default", "{}", "2026-05-14T00:00:00+00:00"),
            )
            conn.commit()
        finally:
            conn.close()

    def write_training_db(self, path: Path) -> None:
        path.parent.mkdir(parents=True)
        conn = sqlite3.connect(path)
        try:
            conn.executescript(
                """
                CREATE TABLE training_observations (
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
                """
            )
            conn.execute(
                "INSERT INTO training_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "attempt_1_turn_1",
                    "local-default",
                    "attempt_1",
                    "turn_1",
                    "p1_name",
                    "p1",
                    "What is your full name?",
                    "My full name is LiHua.",
                    5.0,
                    5.0,
                    5.0,
                    5.0,
                    None,
                    0.5,
                    1,
                    '["short_answer"]',
                    "fallback",
                    "2026-05-14T00:00:00+00:00",
                    "2026-05-15T00:00:00+00:00",
                ),
            )
            conn.commit()
        finally:
            conn.close()
