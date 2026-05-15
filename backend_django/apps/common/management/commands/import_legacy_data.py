import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.billing.models import CodexUsageEvent, LegacyBillingUser, PriceSnapshot, TokenWallet, WalletLedgerEntry, WalletReservation
from apps.ai.models import AITask
from apps.speaking.models import SpeakingAttempt, SpeakingReport, SpeakingTrainingObservation, SpeakingTurn
from apps.writing.models import WritingEntry, WritingLearnerProfile, WritingPrompt, WritingScore


DEFAULT_LEGACY_USER_ID = "local-default"


def parse_datetime(value: Any):
    if not value:
        return None
    try:
        parsed = timezone.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def parse_date(value: Any):
    if not value:
        return timezone.localdate()
    try:
        return timezone.datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return timezone.datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError:
            return timezone.localdate()


def decimal_or_none(value: Any, places: str = "0.1"):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal(places))
    except Exception:
        return None


def choice_or_default(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


def read_json_file(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


class Command(BaseCommand):
    help = "Import legacy reports/ SQLite and JSON data into the Django database."

    def add_arguments(self, parser):
        parser.add_argument("--reports-dir", default="reports", help="Path to the legacy reports directory.")
        parser.add_argument("--username", default="local-default", help="Django username for single-user legacy data.")
        parser.add_argument("--dry-run", action="store_true", help="Parse and count records without writing database rows.")

    def handle(self, *args, **options):
        reports_dir = Path(options["reports_dir"]).resolve()
        if not reports_dir.exists():
            raise CommandError(f"reports directory does not exist: {reports_dir}")
        self.dry_run = bool(options["dry_run"])
        self.user_cache: dict[str, Any] = {}
        username = str(options["username"] or DEFAULT_LEGACY_USER_ID)
        self.default_user = self.get_or_create_user(DEFAULT_LEGACY_USER_ID, username, "Local user")

        counts = {
            "billing_users": self.import_billing_users(reports_dir),
            "price_snapshots": self.import_price_snapshots(reports_dir),
            "usage_events": self.import_usage_events(reports_dir),
            "wallet_reservations": self.import_wallet_reservations(reports_dir),
            "wallet_ledger_entries": self.import_wallet_ledger_entries(reports_dir),
            "speaking_attempts": self.import_speaking_attempts(reports_dir),
            "training_observations": self.import_training_observations(reports_dir),
            "writing_entries": self.import_writing_entries(reports_dir),
            "writing_profiles": self.import_writing_profiles(reports_dir),
            "ai_tasks": self.import_ai_tasks(reports_dir),
        }
        self.stdout.write(self.style.SUCCESS(json.dumps(counts, ensure_ascii=False, sort_keys=True)))

    def get_or_create_user(self, legacy_user_id: str, username: str | None = None, display_name: str = ""):
        cache_key = legacy_user_id or DEFAULT_LEGACY_USER_ID
        if cache_key in self.user_cache:
            return self.user_cache[cache_key]
        user_model = get_user_model()
        if self.dry_run:
            self.user_cache[cache_key] = self.default_user if hasattr(self, "default_user") else None
            return self.user_cache[cache_key]
        safe_username = (username or cache_key).replace(" ", "_")[:150]
        user, _created = user_model.objects.get_or_create(
            legacy_user_id=cache_key,
            defaults={
                "username": safe_username,
                "display_name": display_name or username or cache_key,
            },
        )
        if display_name and not user.display_name:
            user.display_name = display_name
            user.save(update_fields=["display_name"])
        self.user_cache[cache_key] = user
        return user

    def sqlite_rows(self, db_path: Path, table: str) -> list[sqlite3.Row]:
        if not db_path.exists():
            return []
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(f"SELECT * FROM {table}").fetchall()
        finally:
            conn.close()

    def import_billing_users(self, reports_dir: Path) -> int:
        rows = self.sqlite_rows(reports_dir / "billing" / "billing.sqlite3", "users")
        if self.dry_run:
            return len(rows)
        count = 0
        with transaction.atomic():
            for row in rows:
                user = self.get_or_create_user(row["user_id"], row["user_id"], row["display_name"])
                LegacyBillingUser.objects.update_or_create(
                    legacy_user_id=row["user_id"],
                    defaults={
                        "user": user,
                        "display_name": row["display_name"],
                        "balance_u": int(row["balance_u"] or 0),
                        "reserved_u": int(row["reserved_u"] or 0),
                        "carry_numerator_u": int(row["carry_numerator_u"] or 0),
                        "status": row["status"],
                        "legacy_created_at": parse_datetime(row["created_at"]),
                        "legacy_updated_at": parse_datetime(row["updated_at"]),
                    },
                )
                TokenWallet.objects.update_or_create(
                    user=user,
                    defaults={
                        "balance_u": int(row["balance_u"] or 0),
                        "reserved_u": int(row["reserved_u"] or 0),
                        "carry_numerator_u": int(row["carry_numerator_u"] or 0),
                        "status": row["status"],
                    },
                )
                count += 1
        return count

    def import_price_snapshots(self, reports_dir: Path) -> int:
        rows = self.sqlite_rows(reports_dir / "billing" / "billing.sqlite3", "price_snapshots")
        if self.dry_run:
            return len(rows)
        count = 0
        for row in rows:
            PriceSnapshot.objects.update_or_create(
                snapshot_id=row["snapshot_id"],
                defaults={
                    "model": row["model"],
                    "input_price_u_per_1m_tokens": int(row["input_price_u_per_1m_tokens"] or 0),
                    "cached_input_price_u_per_1m_tokens": int(row["cached_input_price_u_per_1m_tokens"] or 0),
                    "output_price_u_per_1m_tokens": int(row["output_price_u_per_1m_tokens"] or 0),
                    "reasoning_price_u_per_1m_tokens": int(row["reasoning_price_u_per_1m_tokens"] or 0),
                    "effective_from": parse_datetime(row["effective_from"]) or timezone.now(),
                    "effective_to": parse_datetime(row["effective_to"]),
                    "source": row["source"],
                },
            )
            count += 1
        return count

    def import_usage_events(self, reports_dir: Path) -> int:
        rows = self.sqlite_rows(reports_dir / "billing" / "billing.sqlite3", "codex_usage_events")
        if self.dry_run:
            return len(rows)
        count = 0
        for row in rows:
            CodexUsageEvent.objects.update_or_create(
                usage_id=row["usage_id"],
                defaults={
                    "call_id": row["call_id"],
                    "provider": row["provider"],
                    "model": row["model"],
                    "raw_jsonl_path": row["raw_jsonl_path"] or "",
                    "input_tokens": int(row["input_tokens"] or 0),
                    "cached_input_tokens": int(row["cached_input_tokens"] or 0),
                    "output_tokens": int(row["output_tokens"] or 0),
                    "reasoning_output_tokens": int(row["reasoning_output_tokens"] or 0),
                    "raw_usage": json.loads(row["raw_usage_json"] or "{}"),
                    "semantics_version": row["semantics_version"],
                    "captured_at": parse_datetime(row["captured_at"]) or timezone.now(),
                },
            )
            count += 1
        return count

    def import_wallet_reservations(self, reports_dir: Path) -> int:
        rows = self.sqlite_rows(reports_dir / "billing" / "billing.sqlite3", "wallet_reservations")
        if self.dry_run:
            return len(rows)
        count = 0
        for row in rows:
            user = self.get_or_create_user(row["user_id"], row["user_id"], row["user_id"])
            WalletReservation.objects.update_or_create(
                reservation_id=row["reservation_id"],
                defaults={
                    "user": user,
                    "call_id": row["call_id"],
                    "reserved_u": int(row["reserved_u"] or 0),
                    "status": choice_or_default(row["status"], {"reserved", "released", "settled", "expired"}, "reserved"),
                    "expires_at": parse_datetime(row["expires_at"]) or timezone.now(),
                    "released_at": parse_datetime(row["released_at"]),
                },
            )
            count += 1
        return count

    def import_wallet_ledger_entries(self, reports_dir: Path) -> int:
        rows = self.sqlite_rows(reports_dir / "billing" / "billing.sqlite3", "wallet_ledger_entries")
        if self.dry_run:
            return len(rows)
        count = 0
        for row in rows:
            user = self.get_or_create_user(row["user_id"], row["user_id"], row["user_id"])
            snapshot = PriceSnapshot.objects.filter(snapshot_id=row["snapshot_id"]).first() if row["snapshot_id"] else None
            usage = CodexUsageEvent.objects.filter(usage_id=row["usage_id"]).first() if row["usage_id"] else None
            WalletLedgerEntry.objects.update_or_create(
                entry_id=row["entry_id"],
                defaults={
                    "user": user,
                    "call_id": row["call_id"] or "",
                    "entry_type": choice_or_default(row["entry_type"], {"grant", "reserve", "settle", "release", "adjust", "refund", "recharge"}, "adjust"),
                    "amount_u": int(row["amount_u"] or 0),
                    "snapshot": snapshot,
                    "usage": usage,
                    "idempotency_key": row["idempotency_key"],
                    "metadata": json.loads(row["metadata_json"] or "{}"),
                },
            )
            count += 1
        return count

    def import_speaking_attempts(self, reports_dir: Path) -> int:
        paths = sorted((reports_dir / "attempts").glob("*.json")) if (reports_dir / "attempts").exists() else []
        if self.dry_run:
            return len(paths)
        count = 0
        for path in paths:
            payload = read_json_file(path)
            user = self.get_or_create_user(str(payload.get("user_id") or DEFAULT_LEGACY_USER_ID), display_name=str(payload.get("candidate") or ""))
            mode = str(payload.get("mode") or payload.get("part") or "mock")
            if mode == "full":
                mode = "mock"
            mode = choice_or_default(mode, {"p1", "p2", "p3", "mock"}, "mock")
            attempt, _created = SpeakingAttempt.objects.update_or_create(
                legacy_attempt_id=str(payload.get("id") or path.stem),
                defaults={
                    "user": user,
                    "attempt_id": str(payload.get("id") or path.stem),
                    "mode": mode,
                    "part": str(payload.get("part") or ""),
                    "title": str(payload.get("title") or payload.get("question") or "")[:200],
                    "status": choice_or_default(payload.get("status"), {"started", "ready_to_score", "scored", "aborted"}, "started"),
                    "full_name": str(payload.get("full_name") or ""),
                    "english_name": str(payload.get("english_name") or payload.get("candidate") or ""),
                    "target_band": decimal_or_none(payload.get("target_band")),
                    "metadata": {"legacy_payload_path": str(path), "payload": payload},
                },
            )
            for index, turn_payload in enumerate(payload.get("turns") or [], start=1):
                turn_id = str(turn_payload.get("id") or turn_payload.get("turn_id") or index)
                SpeakingTurn.objects.update_or_create(
                    attempt=attempt,
                    turn_id=turn_id,
                    defaults={
                        "user": user,
                        "sequence": int(turn_payload.get("sequence") or turn_payload.get("display_index") or index),
                        "part": str(turn_payload.get("part") or payload.get("part") or ""),
                        "question": str(turn_payload.get("question") or ""),
                        "transcript_raw": str(turn_payload.get("transcript_raw") or ""),
                        "transcript_cleaned": str(turn_payload.get("transcript_cleaned") or ""),
                        "transcript_source": str(turn_payload.get("transcript_source") or ""),
                        "audio_path": str(turn_payload.get("audio_path") or turn_payload.get("audio_url") or ""),
                        "duration_seconds": decimal_or_none(turn_payload.get("duration_seconds"), "0.01"),
                        "counts_toward_total": bool(turn_payload.get("counts_toward_total", True)),
                        "pronunciation": turn_payload.get("pronunciation") if isinstance(turn_payload.get("pronunciation"), dict) else {},
                        "metadata": turn_payload,
                    },
                )
            score = payload.get("ielts_score") if isinstance(payload.get("ielts_score"), dict) else {}
            if score:
                SpeakingReport.objects.update_or_create(
                    attempt=attempt,
                    defaults={
                        "user": user,
                        "overall_band": decimal_or_none(score.get("overall_band")),
                        "fluency_coherence": decimal_or_none(score.get("fluency_coherence")),
                        "lexical_resource": decimal_or_none(score.get("lexical_resource")),
                        "grammar_range_accuracy": decimal_or_none(score.get("grammatical_range")),
                        "pronunciation": decimal_or_none(score.get("pronunciation_estimate")),
                        "feedback_summary": str(score.get("feedback") or ""),
                        "report_payload": payload,
                    },
                )
            count += 1
        return count

    def import_training_observations(self, reports_dir: Path) -> int:
        rows = self.sqlite_rows(reports_dir / "training" / "training.sqlite3", "training_observations")
        if self.dry_run:
            return len(rows)
        count = 0
        for row in rows:
            user = self.get_or_create_user(row["user_id"], row["user_id"], row["user_id"])
            attempt = SpeakingAttempt.objects.filter(legacy_attempt_id=row["attempt_id"]).first()
            turn = SpeakingTurn.objects.filter(attempt=attempt, turn_id=row["turn_id"]).first() if attempt else None
            SpeakingTrainingObservation.objects.update_or_create(
                observation_id=row["observation_id"],
                defaults={
                    "user": user,
                    "attempt": attempt,
                    "turn": turn,
                    "legacy_attempt_id": row["attempt_id"],
                    "legacy_turn_id": row["turn_id"],
                    "question_id": row["question_id"],
                    "part": row["part"],
                    "question": row["question"],
                    "transcript": row["transcript"],
                    "overall_band": decimal_or_none(row["overall_band"]),
                    "fluency_coherence": decimal_or_none(row["fluency_coherence"]),
                    "lexical_resource": decimal_or_none(row["lexical_resource"]),
                    "grammar_range_accuracy": decimal_or_none(row["grammatical_range"]),
                    "pronunciation": decimal_or_none(row["pronunciation_estimate"]),
                    "relevance": decimal_or_none(row["relevance"], "0.001") or Decimal("0.000"),
                    "weak_item_flag": bool(row["weak_item_flag"]),
                    "weak_reasons": json.loads(row["weak_reason_json"] or "[]"),
                    "model_version": row["model_version"],
                    "observed_at": parse_datetime(row["observed_at"]) or timezone.now(),
                    "next_due": parse_datetime(row["next_due"]) or timezone.now(),
                },
            )
            count += 1
        return count

    def import_ai_tasks(self, reports_dir: Path) -> int:
        jsonl_dir = reports_dir / "billing" / "codex_jsonl"
        paths = sorted(jsonl_dir.glob("*.jsonl")) if jsonl_dir.exists() else []
        if self.dry_run:
            return len(paths)
        count = 0
        for path in paths:
            call_id = path.stem
            usage = CodexUsageEvent.objects.filter(call_id=call_id).first()
            status = AITask.Status.SUCCEEDED if usage else AITask.Status.FAILED
            AITask.objects.update_or_create(
                provider="codex",
                related_type="legacy_call",
                related_id=call_id,
                defaults={
                    "user": self.default_user,
                    "task_type": self.infer_ai_task_type(call_id),
                    "model": usage.model if usage else "codex-cli",
                    "status": status,
                    "prompt_version": "legacy_codex_jsonl",
                    "fallback_reason": "" if usage else "legacy JSONL has no captured usage event",
                    "metadata": {"legacy_jsonl_path": str(path), "usage_id": usage.usage_id if usage else ""},
                },
            )
            count += 1
        return count

    def infer_ai_task_type(self, call_id: str) -> str:
        for prefix in ("writing_score", "overall_review", "score", "band7", "p3", "tts", "asr"):
            if call_id.startswith(prefix):
                return prefix
        return "legacy_codex"

    def import_writing_entries(self, reports_dir: Path) -> int:
        paths = sorted((reports_dir / "writing").glob("*.json")) if (reports_dir / "writing").exists() else []
        if self.dry_run:
            return len(paths)
        count = 0
        for path in paths:
            payload = read_json_file(path)
            user = self.get_or_create_user(str(payload.get("user_id") or DEFAULT_LEGACY_USER_ID), display_name="Local user")
            prompt_obj = None
            prompt_id = str(payload.get("prompt_id") or "")
            if prompt_id:
                prompt_obj, _created = WritingPrompt.objects.update_or_create(
                    prompt_id=prompt_id,
                    defaults={
                        "task_type": choice_or_default(payload.get("task_type"), {"task1_academic", "task2"}, "task2"),
                        "title": str(payload.get("title") or "")[:200] or "Legacy writing prompt",
                        "category": str(payload.get("category") or ""),
                        "prompt": str(payload.get("prompt") or ""),
                        "source": "legacy_reports",
                        "is_active": True,
                    },
                )
            entry, _created = WritingEntry.objects.update_or_create(
                legacy_entry_id=str(payload.get("id") or path.stem),
                defaults={
                    "user": user,
                    "entry_id": str(payload.get("id") or path.stem),
                    "prompt": prompt_obj,
                    "task_type": choice_or_default(payload.get("task_type"), {"task1_academic", "task2"}, "task2"),
                    "practice_date": parse_date(payload.get("practice_date") or payload.get("saved_at") or payload.get("created_at")),
                    "title": str(payload.get("title") or "")[:200],
                    "prompt_text": str(payload.get("prompt") or ""),
                    "answer": str(payload.get("answer") or ""),
                    "word_count": int(payload.get("word_count") or 0),
                    "status": choice_or_default(payload.get("status"), {"saved", "scored"}, "saved"),
                    "saved_at": parse_datetime(payload.get("saved_at")),
                    "metadata": {"legacy_payload_path": str(path), "payload": payload},
                },
            )
            score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
            if score:
                WritingScore.objects.update_or_create(
                    entry=entry,
                    defaults={
                        "user": user,
                        "overall_band": decimal_or_none(score.get("overall_band")),
                        "task_response": decimal_or_none(score.get("task_response")),
                        "coherence_cohesion": decimal_or_none(score.get("coherence_cohesion")),
                        "lexical_resource": decimal_or_none(score.get("lexical_resource")),
                        "grammar_range_accuracy": decimal_or_none(score.get("grammatical_range_accuracy")),
                        "feedback_markdown": str(score.get("feedback_markdown") or ""),
                        "grammar_corrections": score.get("grammar_corrections") if isinstance(score.get("grammar_corrections"), list) else [],
                        "source": str(score.get("backend") or "legacy"),
                        "billing_metadata": score.get("billing_usage") if isinstance(score.get("billing_usage"), dict) else {},
                        "scored_at": parse_datetime(payload.get("scored_at")),
                    },
                )
            count += 1
        return count

    def import_writing_profiles(self, reports_dir: Path) -> int:
        paths = sorted((reports_dir / "writing_profiles").glob("*.json")) if (reports_dir / "writing_profiles").exists() else []
        if self.dry_run:
            return len(paths)
        count = 0
        for path in paths:
            payload = read_json_file(path)
            user_id = str(payload.get("user_id") or path.stem or DEFAULT_LEGACY_USER_ID)
            user = self.get_or_create_user(user_id, user_id, user_id)
            WritingLearnerProfile.objects.update_or_create(
                user=user,
                defaults={
                    "total_scored": int(payload.get("total_scored") or 0),
                    "task_counts": payload.get("task_counts") if isinstance(payload.get("task_counts"), dict) else {},
                    "average_overall_band": decimal_or_none(payload.get("average_overall_band"), "0.01"),
                    "criterion_averages": payload.get("criterion_averages") if isinstance(payload.get("criterion_averages"), dict) else {},
                    "tag_counts": payload.get("tag_counts") if isinstance(payload.get("tag_counts"), dict) else {},
                    "primary_focus": str(payload.get("primary_focus") or "insufficient_data"),
                    "primary_focus_text": str(payload.get("primary_focus_text") or ""),
                    "recent_evidence": payload.get("recent_evidence") if isinstance(payload.get("recent_evidence"), list) else [],
                    "profile_payload": payload,
                },
            )
            count += 1
        return count
