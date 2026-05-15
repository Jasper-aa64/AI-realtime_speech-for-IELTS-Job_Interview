from django.db import models

from apps.common.models import TimeStampedModel


MICRO_RMB_PER_RMB = 1_000_000


class TokenWallet(TimeStampedModel):
    user = models.OneToOneField("accounts.CustomUser", on_delete=models.CASCADE, related_name="token_wallet")
    balance_u = models.BigIntegerField(default=0)
    reserved_u = models.BigIntegerField(default=0)
    carry_numerator_u = models.BigIntegerField(default=0)
    status = models.CharField(max_length=24, default="active")

    def __str__(self) -> str:
        return f"{self.user} wallet"


class PriceSnapshot(TimeStampedModel):
    snapshot_id = models.CharField(max_length=80, unique=True)
    model = models.CharField(max_length=120)
    input_price_u_per_1m_tokens = models.BigIntegerField()
    cached_input_price_u_per_1m_tokens = models.BigIntegerField()
    output_price_u_per_1m_tokens = models.BigIntegerField()
    reasoning_price_u_per_1m_tokens = models.BigIntegerField(default=0)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=120)

    class Meta:
        indexes = [
            models.Index(fields=["model", "effective_from"]),
        ]

    def __str__(self) -> str:
        return self.snapshot_id


class CodexUsageEvent(TimeStampedModel):
    usage_id = models.CharField(max_length=80, unique=True)
    call_id = models.CharField(max_length=160, unique=True)
    provider = models.CharField(max_length=80, default="codex")
    model = models.CharField(max_length=120, default="codex-cli")
    raw_jsonl_path = models.CharField(max_length=500, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    cached_input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    reasoning_output_tokens = models.PositiveIntegerField(default=0)
    raw_usage = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    semantics_version = models.CharField(max_length=80, default="codex_cli_json_v1")
    captured_at = models.DateTimeField()

    def __str__(self) -> str:
        return self.usage_id


class WalletReservation(TimeStampedModel):
    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        RELEASED = "released", "Released"
        SETTLED = "settled", "Settled"
        EXPIRED = "expired", "Expired"

    reservation_id = models.CharField(max_length=80, unique=True)
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="wallet_reservations")
    call_id = models.CharField(max_length=160, unique=True)
    reserved_u = models.BigIntegerField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.RESERVED)
    expires_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return self.reservation_id


class WalletLedgerEntry(TimeStampedModel):
    class EntryType(models.TextChoices):
        GRANT = "grant", "Grant"
        RESERVE = "reserve", "Reserve"
        SETTLE = "settle", "Settle"
        RELEASE = "release", "Release"
        ADJUST = "adjust", "Adjust"
        REFUND = "refund", "Refund"
        RECHARGE = "recharge", "Recharge"

    entry_id = models.CharField(max_length=80, unique=True)
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="wallet_ledger_entries")
    call_id = models.CharField(max_length=160, blank=True)
    entry_type = models.CharField(max_length=24, choices=EntryType.choices)
    amount_u = models.BigIntegerField()
    snapshot = models.ForeignKey(PriceSnapshot, null=True, blank=True, on_delete=models.SET_NULL)
    usage = models.ForeignKey(CodexUsageEvent, null=True, blank=True, on_delete=models.SET_NULL)
    idempotency_key = models.CharField(max_length=180, unique=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["call_id"]),
        ]

    def __str__(self) -> str:
        return self.entry_id


class PaymentOrder(TimeStampedModel):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    order_id = models.CharField(max_length=80, unique=True)
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="payment_orders")
    provider = models.CharField(max_length=80, blank=True)
    provider_order_id = models.CharField(max_length=160, null=True, blank=True, unique=True)
    amount_u = models.BigIntegerField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.CREATED)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "status", "created_at"]),
        ]

    def __str__(self) -> str:
        return self.order_id


class LegacyBillingUser(TimeStampedModel):
    legacy_user_id = models.CharField(max_length=120, unique=True)
    user = models.OneToOneField("accounts.CustomUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="legacy_billing_user")
    display_name = models.CharField(max_length=120)
    balance_u = models.BigIntegerField(default=0)
    reserved_u = models.BigIntegerField(default=0)
    carry_numerator_u = models.BigIntegerField(default=0)
    status = models.CharField(max_length=24, default="active")
    legacy_created_at = models.DateTimeField(null=True, blank=True)
    legacy_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "updated_at"], name="billing_leg_status_a7ce82_idx"),
        ]

    def __str__(self) -> str:
        return self.legacy_user_id
