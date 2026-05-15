import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import CodexUsageEvent, MICRO_RMB_PER_RMB, PriceSnapshot, TokenWallet, WalletLedgerEntry, WalletReservation


DEFAULT_INITIAL_GRANT_U = 5 * MICRO_RMB_PER_RMB
DEFAULT_PRICE_SNAPSHOT = {
    "snapshot_id": "local_2026_05_default",
    "model": "codex-cli",
    "input_price_u_per_1m_tokens": 12_000_000,
    "cached_input_price_u_per_1m_tokens": 3_000_000,
    "output_price_u_per_1m_tokens": 48_000_000,
    "reasoning_price_u_per_1m_tokens": 0,
    "effective_from": datetime(2026, 5, 10, tzinfo=datetime_timezone.utc),
    "effective_to": None,
    "source": "local_config_snapshot",
}


class BillingError(ValueError):
    pass


def require_call_id(call_id: str) -> str:
    call_id = str(call_id or "").strip()
    if not call_id:
        raise BillingError("call_id is required")
    return call_id


def non_negative_int(value: Any, field_name: str) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise BillingError(f"{field_name} must be a non-negative integer") from exc
    if parsed < 0:
        raise BillingError(f"{field_name} must be a non-negative integer")
    return parsed


@dataclass(frozen=True)
class BillingUsage:
    input_tokens: int
    cached_input_tokens: int
    uncached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int

    def as_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "uncached_input_tokens": self.uncached_input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_output_tokens": self.reasoning_output_tokens,
        }


def ensure_default_price_snapshot() -> PriceSnapshot:
    snapshot, _created = PriceSnapshot.objects.get_or_create(
        snapshot_id=DEFAULT_PRICE_SNAPSHOT["snapshot_id"],
        defaults=DEFAULT_PRICE_SNAPSHOT,
    )
    return snapshot


def append_ledger_entry(
    *,
    user,
    entry_type: str,
    amount_u: int,
    idempotency_key: str,
    call_id: str = "",
    snapshot: PriceSnapshot | None = None,
    usage: CodexUsageEvent | None = None,
    metadata: dict[str, Any] | None = None,
) -> WalletLedgerEntry:
    entry_id = f"entry_{hashlib.sha1(f'{user.pk}:{idempotency_key}'.encode('utf-8')).hexdigest()[:20]}"
    entry, _created = WalletLedgerEntry.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "entry_id": entry_id,
            "user": user,
            "call_id": call_id,
            "entry_type": entry_type,
            "amount_u": amount_u,
            "snapshot": snapshot,
            "usage": usage,
            "metadata": metadata or {},
        },
    )
    return entry


@transaction.atomic
def ensure_wallet(user) -> TokenWallet:
    wallet, created = TokenWallet.objects.select_for_update().get_or_create(user=user)
    if created:
        wallet.balance_u = DEFAULT_INITIAL_GRANT_U
        wallet.status = "active"
        wallet.save(update_fields=["balance_u", "status", "updated_at"])
        append_ledger_entry(
            user=user,
            entry_type=WalletLedgerEntry.EntryType.GRANT,
            amount_u=DEFAULT_INITIAL_GRANT_U,
            idempotency_key=f"grant:initial:{user.pk}",
            metadata={"reason": "initial 5 RMB local balance"},
        )
    return wallet


def wallet_payload(user) -> dict[str, Any]:
    wallet = ensure_wallet(user)
    entries = WalletLedgerEntry.objects.filter(user=user).order_by("-created_at")[:20]
    return {
        "user_id": str(user.pk),
        "username": user.get_username(),
        "balance_u": wallet.balance_u,
        "reserved_u": wallet.reserved_u,
        "balance_rmb": round(wallet.balance_u / MICRO_RMB_PER_RMB, 6),
        "reserved_rmb": round(wallet.reserved_u / MICRO_RMB_PER_RMB, 6),
        "entries": [ledger_entry_payload(entry) for entry in entries],
    }


def ledger_entry_payload(entry: WalletLedgerEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "call_id": entry.call_id,
        "entry_type": entry.entry_type,
        "amount_u": entry.amount_u,
        "amount_rmb": round(entry.amount_u / MICRO_RMB_PER_RMB, 6),
        "snapshot_id": entry.snapshot.snapshot_id if entry.snapshot_id else None,
        "usage_id": entry.usage.usage_id if entry.usage_id else None,
        "created_at": entry.created_at.isoformat(),
        "metadata": entry.metadata,
    }


@transaction.atomic
def recharge_wallet(user, amount_rmb: float) -> dict[str, Any]:
    if amount_rmb <= 0:
        raise BillingError("Amount must be positive")
    amount_u = int(amount_rmb * MICRO_RMB_PER_RMB)
    wallet = TokenWallet.objects.select_for_update().get(user=ensure_wallet(user).user)
    wallet.balance_u = F("balance_u") + amount_u
    wallet.save(update_fields=["balance_u", "updated_at"])
    wallet.refresh_from_db()
    entry = append_ledger_entry(
        user=user,
        entry_type=WalletLedgerEntry.EntryType.RECHARGE,
        amount_u=amount_u,
        idempotency_key=f"recharge:{user.pk}:{uuid.uuid4().hex}",
        metadata={"reason": f"manual recharge ¥{amount_rmb:.2f}"},
    )
    return {
        "entry_id": entry.entry_id,
        "amount_u": amount_u,
        "amount_rmb": round(amount_u / MICRO_RMB_PER_RMB, 6),
        "new_balance_u": wallet.balance_u,
        "new_balance_rmb": round(wallet.balance_u / MICRO_RMB_PER_RMB, 6),
    }


def normalize_usage(usage: dict[str, Any] | None) -> BillingUsage:
    usage = usage or {}
    if not isinstance(usage, dict):
        raise BillingError("usage must be an object")
    input_details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    output_details = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"), dict) else {}
    input_tokens = non_negative_int(usage.get("input_tokens"), "input_tokens")
    cached = non_negative_int(usage.get("cached_input_tokens") or input_details.get("cached_tokens"), "cached_input_tokens")
    output = non_negative_int(usage.get("output_tokens"), "output_tokens")
    reasoning = non_negative_int(usage.get("reasoning_output_tokens") or output_details.get("reasoning_tokens"), "reasoning_output_tokens")
    cached = max(0, min(cached, input_tokens))
    return BillingUsage(
        input_tokens=input_tokens,
        cached_input_tokens=cached,
        uncached_input_tokens=max(0, input_tokens - cached),
        output_tokens=output,
        reasoning_output_tokens=reasoning,
    )


def latest_price_snapshot(snapshot_id: str | None = None) -> PriceSnapshot:
    if snapshot_id:
        snapshot = PriceSnapshot.objects.filter(snapshot_id=snapshot_id).first()
        if not snapshot:
            raise BillingError("No billing price snapshot configured")
        return snapshot
    snapshot = PriceSnapshot.objects.order_by("-effective_from").first()
    return snapshot or ensure_default_price_snapshot()


def calculate_charge(usage: dict[str, Any], snapshot_id: str | None = None) -> dict[str, Any]:
    normalized = normalize_usage(usage)
    snapshot = latest_price_snapshot(snapshot_id)
    numerator = (
        normalized.uncached_input_tokens * snapshot.input_price_u_per_1m_tokens
        + normalized.cached_input_tokens * snapshot.cached_input_price_u_per_1m_tokens
        + normalized.output_tokens * snapshot.output_price_u_per_1m_tokens
        + normalized.reasoning_output_tokens * snapshot.reasoning_price_u_per_1m_tokens
    )
    return {
        "amount_u": int(numerator // 1_000_000),
        "carry_numerator_u": int(numerator % 1_000_000),
        "charge_numerator_u": int(numerator),
        "usage": normalized.as_dict(),
        "snapshot": snapshot,
    }


def capture_usage(call_id: str, usage: dict[str, Any], provider: str = "codex", model: str = "codex-cli", raw_jsonl_path: str = "") -> CodexUsageEvent:
    call_id = require_call_id(call_id)
    normalized = normalize_usage(usage)
    event, _created = CodexUsageEvent.objects.get_or_create(
        call_id=call_id,
        defaults={
            "usage_id": f"usage_{hashlib.sha1(call_id.encode('utf-8')).hexdigest()[:20]}",
            "provider": provider,
            "model": model,
            "raw_jsonl_path": raw_jsonl_path,
            "input_tokens": normalized.input_tokens,
            "cached_input_tokens": normalized.cached_input_tokens,
            "output_tokens": normalized.output_tokens,
            "reasoning_output_tokens": normalized.reasoning_output_tokens,
            "raw_usage": usage,
            "captured_at": timezone.now(),
        },
    )
    return event


@transaction.atomic
def reserve_usage(user, call_id: str, reserved_u: int, snapshot_id: str | None = None, ttl_seconds: int = 24 * 60 * 60) -> dict[str, Any]:
    call_id = require_call_id(call_id)
    reserved_u = non_negative_int(reserved_u, "reserved_u")
    if reserved_u <= 0:
        raise BillingError("reserved_u must be greater than zero")
    snapshot = latest_price_snapshot(snapshot_id) if snapshot_id else None
    existing = WalletReservation.objects.filter(call_id=call_id).first()
    if existing:
        if existing.user_id != user.pk:
            raise BillingError("call_id already belongs to another user")
        return reservation_payload(existing)
    wallet = TokenWallet.objects.select_for_update().get(user=ensure_wallet(user).user)
    if wallet.balance_u < reserved_u:
        raise BillingError("Insufficient balance for reservation")
    expires_at = timezone.now() + timezone.timedelta(seconds=max(60, int(ttl_seconds)))
    reservation = WalletReservation.objects.create(
        reservation_id=f"reservation_{hashlib.sha1(call_id.encode('utf-8')).hexdigest()[:20]}",
        user=user,
        call_id=call_id,
        reserved_u=reserved_u,
        expires_at=expires_at,
    )
    wallet.balance_u = F("balance_u") - reserved_u
    wallet.reserved_u = F("reserved_u") + reserved_u
    wallet.save(update_fields=["balance_u", "reserved_u", "updated_at"])
    append_ledger_entry(
        user=user,
        call_id=call_id,
        entry_type=WalletLedgerEntry.EntryType.RESERVE,
        amount_u=-reserved_u,
        snapshot=snapshot,
        idempotency_key=f"reserve:{call_id}",
        metadata={"reserved_u": reserved_u, "expires_at": expires_at.isoformat()},
    )
    reservation.refresh_from_db()
    return reservation_payload(reservation)


def reservation_payload(reservation: WalletReservation) -> dict[str, Any]:
    return {
        "reservation_id": reservation.reservation_id,
        "user_id": str(reservation.user_id),
        "call_id": reservation.call_id,
        "reserved_u": reservation.reserved_u,
        "reserved_rmb": round(reservation.reserved_u / MICRO_RMB_PER_RMB, 6),
        "status": reservation.status,
        "expires_at": reservation.expires_at.isoformat(),
        "created_at": reservation.created_at.isoformat(),
        "released_at": reservation.released_at.isoformat() if reservation.released_at else None,
    }


@transaction.atomic
def release_reservation(user, call_id: str) -> dict[str, Any]:
    call_id = require_call_id(call_id)
    reservation = WalletReservation.objects.select_for_update().filter(call_id=call_id, user=user).first()
    if not reservation:
        raise BillingError("Reservation not found")
    if reservation.status != WalletReservation.Status.RESERVED:
        return reservation_payload(reservation)
    wallet = TokenWallet.objects.select_for_update().get(user=user)
    wallet.balance_u = F("balance_u") + reservation.reserved_u
    wallet.reserved_u = F("reserved_u") - reservation.reserved_u
    wallet.save(update_fields=["balance_u", "reserved_u", "updated_at"])
    append_ledger_entry(
        user=user,
        call_id=call_id,
        entry_type=WalletLedgerEntry.EntryType.RELEASE,
        amount_u=reservation.reserved_u,
        idempotency_key=f"release:{call_id}",
        metadata={"released_u": reservation.reserved_u, "reservation_id": reservation.reservation_id},
    )
    reservation.status = WalletReservation.Status.RELEASED
    reservation.released_at = timezone.now()
    reservation.save(update_fields=["status", "released_at", "updated_at"])
    return reservation_payload(reservation)


@transaction.atomic
def settle_usage(user, call_id: str, usage: dict[str, Any] | None, snapshot_id: str | None = None) -> dict[str, Any]:
    call_id = require_call_id(call_id)
    if not usage:
        return {"status": "pending_reconciliation", "charged_u": 0, "reason": "missing authoritative usage"}
    existing = WalletLedgerEntry.objects.filter(idempotency_key=f"settle:{call_id}").first()
    if existing:
        if existing.user_id != user.pk:
            raise BillingError("call_id already belongs to another user")
        return {
            "status": "already_settled",
            "charged_u": abs(existing.amount_u),
            "usage_id": existing.usage.usage_id if existing.usage_id else None,
                "snapshot_id": existing.snapshot.snapshot_id if existing.snapshot_id else None,
            }
    reservation = WalletReservation.objects.select_for_update().filter(call_id=call_id).first()
    if reservation and reservation.user_id != user.pk:
        raise BillingError("call_id already belongs to another user")
    event = capture_usage(call_id, usage)
    charge = calculate_charge(usage, snapshot_id)
    snapshot = charge["snapshot"]
    wallet = TokenWallet.objects.select_for_update().get(user=ensure_wallet(user).user)
    reserved_u = reservation.reserved_u if reservation and reservation.status == WalletReservation.Status.RESERVED else 0
    released_from_reservation = max(0, reserved_u - charge["amount_u"])
    extra_charged = max(0, charge["amount_u"] - reserved_u)
    if extra_charged and wallet.balance_u < extra_charged:
        raise BillingError("Insufficient balance for settlement")
    if not reserved_u and wallet.balance_u < charge["amount_u"]:
        raise BillingError("Insufficient balance for settlement")
    if reserved_u:
        wallet.reserved_u = F("reserved_u") - reserved_u
        wallet.carry_numerator_u = F("carry_numerator_u") + charge["carry_numerator_u"]
        wallet.save(update_fields=["reserved_u", "carry_numerator_u", "updated_at"])
        if extra_charged:
            TokenWallet.objects.filter(pk=wallet.pk).update(balance_u=F("balance_u") - extra_charged)
        if released_from_reservation:
            TokenWallet.objects.filter(pk=wallet.pk).update(balance_u=F("balance_u") + released_from_reservation)
            append_ledger_entry(
                user=user,
                call_id=call_id,
                entry_type=WalletLedgerEntry.EntryType.RELEASE,
                amount_u=released_from_reservation,
                snapshot=snapshot,
                usage=event,
                idempotency_key=f"release:{call_id}",
                metadata={"released_u": released_from_reservation, "reservation_id": reservation.reservation_id},
            )
        reservation.status = WalletReservation.Status.SETTLED
        reservation.released_at = timezone.now()
        reservation.save(update_fields=["status", "released_at", "updated_at"])
    else:
        wallet.balance_u = F("balance_u") - charge["amount_u"]
        wallet.carry_numerator_u = F("carry_numerator_u") + charge["carry_numerator_u"]
        wallet.save(update_fields=["balance_u", "carry_numerator_u", "updated_at"])
    append_ledger_entry(
        user=user,
        call_id=call_id,
        entry_type=WalletLedgerEntry.EntryType.SETTLE,
        amount_u=-charge["amount_u"],
        snapshot=snapshot,
        usage=event,
        idempotency_key=f"settle:{call_id}",
        metadata={
            "usage": charge["usage"],
            "charge_numerator_u": charge["charge_numerator_u"],
            "carry_numerator_u": charge["carry_numerator_u"],
            "reserved_u": reserved_u,
            "released_from_reservation_u": released_from_reservation,
            "extra_charged_u": extra_charged,
        },
    )
    return {
        "status": "settled",
        "charged_u": charge["amount_u"],
        "usage_id": event.usage_id,
        "snapshot_id": snapshot.snapshot_id,
        "usage": charge["usage"],
        "reserved_u": reserved_u,
        "released_u": released_from_reservation,
        "extra_charged_u": extra_charged,
    }
