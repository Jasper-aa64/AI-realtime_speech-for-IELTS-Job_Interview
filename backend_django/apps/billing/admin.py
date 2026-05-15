from django.contrib import admin

from .models import CodexUsageEvent, LegacyBillingUser, PaymentOrder, PriceSnapshot, TokenWallet, WalletLedgerEntry, WalletReservation


@admin.register(TokenWallet)
class TokenWalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance_u", "reserved_u", "status", "updated_at")
    search_fields = ("user__username",)


@admin.register(WalletLedgerEntry)
class WalletLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("entry_id", "user", "entry_type", "amount_u", "call_id", "created_at")
    list_filter = ("entry_type",)
    search_fields = ("entry_id", "idempotency_key", "call_id", "user__username")


@admin.register(PriceSnapshot)
class PriceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("snapshot_id", "model", "effective_from", "effective_to", "source")
    search_fields = ("snapshot_id", "model")


@admin.register(CodexUsageEvent)
class CodexUsageEventAdmin(admin.ModelAdmin):
    list_display = ("usage_id", "call_id", "provider", "model", "captured_at")
    search_fields = ("usage_id", "call_id")


@admin.register(WalletReservation)
class WalletReservationAdmin(admin.ModelAdmin):
    list_display = ("reservation_id", "user", "call_id", "reserved_u", "status", "expires_at")
    list_filter = ("status",)
    search_fields = ("reservation_id", "call_id", "user__username")


@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
    list_display = ("order_id", "user", "provider", "amount_u", "status", "created_at")
    list_filter = ("status", "provider")
    search_fields = ("order_id", "provider_order_id", "user__username")


@admin.register(LegacyBillingUser)
class LegacyBillingUserAdmin(admin.ModelAdmin):
    list_display = ("legacy_user_id", "user", "display_name", "balance_u", "reserved_u", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("legacy_user_id", "display_name", "user__username")
