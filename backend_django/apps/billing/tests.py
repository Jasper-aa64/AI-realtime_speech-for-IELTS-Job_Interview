from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.billing.models import CodexUsageEvent, LegacyBillingUser, PriceSnapshot, TokenWallet, WalletLedgerEntry, WalletReservation
from apps.billing.services import DEFAULT_INITIAL_GRANT_U, BillingError, ensure_wallet, reserve_usage, settle_usage


class BillingModelTests(TestCase):
    def test_wallet_and_ledger_entry_can_be_created(self):
        user = get_user_model().objects.create_user(username="billing-user", password="test-pass")
        wallet = TokenWallet.objects.create(user=user, balance_u=5_000_000)
        snapshot = PriceSnapshot.objects.create(
            snapshot_id="test-snapshot",
            model="codex-cli",
            input_price_u_per_1m_tokens=12_000_000,
            cached_input_price_u_per_1m_tokens=3_000_000,
            output_price_u_per_1m_tokens=48_000_000,
            reasoning_price_u_per_1m_tokens=0,
            effective_from=timezone.now(),
            source="test",
        )
        entry = WalletLedgerEntry.objects.create(
            entry_id="entry-test",
            user=user,
            entry_type=WalletLedgerEntry.EntryType.GRANT,
            amount_u=5_000_000,
            snapshot=snapshot,
            idempotency_key="grant:test",
        )

        self.assertEqual(wallet.balance_u, 5_000_000)
        self.assertEqual(entry.snapshot, snapshot)

    def test_legacy_billing_user_maps_old_wallet_state(self):
        user = get_user_model().objects.create_user(username="legacy-billing-user", legacy_user_id="local-default", password="test-pass")
        legacy = LegacyBillingUser.objects.create(
            legacy_user_id="local-default",
            user=user,
            display_name="Local user",
            balance_u=5_000_000,
            reserved_u=100_000,
            status="active",
        )

        self.assertEqual(legacy.user, user)
        self.assertEqual(legacy.reserved_u, 100_000)


class BillingServiceTests(TestCase):
    def test_reserve_and_settle_usage_are_idempotent(self):
        user = get_user_model().objects.create_user(username="service-user", password="test-pass")
        wallet = ensure_wallet(user)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U)

        reservation = reserve_usage(user, "call-1", 1_000_000)
        self.assertEqual(reservation["status"], WalletReservation.Status.RESERVED)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U - 1_000_000)
        self.assertEqual(wallet.reserved_u, 1_000_000)

        result = settle_usage(user, "call-1", {"input_tokens": 1000, "cached_input_tokens": 0, "output_tokens": 100, "reasoning_output_tokens": 0})
        self.assertEqual(result["status"], "settled")
        self.assertEqual(result["released_u"], 983_200)
        wallet.refresh_from_db()
        self.assertEqual(wallet.reserved_u, 0)

        again = settle_usage(user, "call-1", {"input_tokens": 1000, "output_tokens": 100})
        self.assertEqual(again["status"], "already_settled")
        self.assertEqual(CodexUsageEvent.objects.count(), 1)
        event = CodexUsageEvent.objects.get(call_id="call-1")
        self.assertEqual(event.provider, "codex")
        self.assertEqual(event.model, "codex-cli")
        self.assertEqual(event.metadata, {})
        self.assertEqual(WalletLedgerEntry.objects.filter(entry_type=WalletLedgerEntry.EntryType.SETTLE).count(), 1)

    def test_settle_usage_can_store_optional_audit_metadata(self):
        user = get_user_model().objects.create_user(username="audit-usage-user", password="test-pass")
        reserve_usage(user, "call-audit", 1_000_000)

        metadata = {
            "task_id": "aitask_audit",
            "task_type": "writing_score",
            "provider": "mock_success",
            "model": "mock-writing-score-v1",
            "prompt_version": "writing_score_v1",
            "related_type": "writing_entry",
            "related_id": "entry-audit",
            "entry_id": "entry-audit",
            "prompt_id": "prompt-audit",
        }
        result = settle_usage(
            user,
            "call-audit",
            {"input_tokens": 1000, "output_tokens": 100},
            provider="mock_success",
            model="mock-writing-score-v1",
            metadata=metadata,
        )

        self.assertEqual(result["status"], "settled")
        event = CodexUsageEvent.objects.get(call_id="call-audit")
        self.assertEqual(event.provider, "mock_success")
        self.assertEqual(event.model, "mock-writing-score-v1")
        self.assertEqual(event.metadata, metadata)

    def test_call_id_cannot_be_reused_by_another_user(self):
        owner = get_user_model().objects.create_user(username="reservation-owner", password="test-pass")
        other = get_user_model().objects.create_user(username="reservation-other", password="test-pass")

        reserve_usage(owner, "shared-call", 100_000)

        with self.assertRaises(BillingError):
            reserve_usage(other, "shared-call", 100_000)
        with self.assertRaises(BillingError):
            settle_usage(other, "shared-call", {"input_tokens": 1000, "output_tokens": 100})

        settle_usage(owner, "shared-call", {"input_tokens": 1000, "output_tokens": 100})
        with self.assertRaises(BillingError):
            settle_usage(other, "shared-call", {"input_tokens": 1000, "output_tokens": 100})

    def test_settlement_rejects_insufficient_balance(self):
        user = get_user_model().objects.create_user(username="poor-user", password="test-pass")
        wallet = ensure_wallet(user)
        wallet.balance_u = 100
        wallet.save(update_fields=["balance_u", "updated_at"])

        with self.assertRaises(BillingError):
            settle_usage(user, "expensive-call", {"input_tokens": 10_000_000, "output_tokens": 10_000_000})

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_u, 100)
        self.assertFalse(WalletLedgerEntry.objects.filter(call_id="expensive-call", entry_type=WalletLedgerEntry.EntryType.SETTLE).exists())

    def test_settlement_rejects_bad_usage_numbers(self):
        user = get_user_model().objects.create_user(username="bad-usage-user", password="test-pass")

        with self.assertRaises(BillingError):
            settle_usage(user, "bad-usage-call", {"input_tokens": "not-a-number"})


class BillingApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="api-user", password="test-pass")
        self.client.force_login(self.user)

    def test_wallet_recharge_reserve_release_and_settle_api(self):
        wallet = self.client.get("/api/billing/wallet/")
        self.assertEqual(wallet.status_code, 200)
        self.assertEqual(wallet.json()["balance_u"], DEFAULT_INITIAL_GRANT_U)

        recharge = self.client.post("/api/billing/recharge/", data={"amount_rmb": 1}, content_type="application/json")
        self.assertEqual(recharge.status_code, 200)
        self.assertEqual(recharge.json()["amount_u"], 1_000_000)

        reserve = self.client.post("/api/billing/reservations/", data={"call_id": "api-call-release", "reserved_u": 500_000}, content_type="application/json")
        self.assertEqual(reserve.status_code, 200)
        self.assertEqual(reserve.json()["status"], WalletReservation.Status.RESERVED)

        release = self.client.post("/api/billing/reservations/release/", data={"call_id": "api-call-release"}, content_type="application/json")
        self.assertEqual(release.status_code, 200)
        self.assertEqual(release.json()["status"], WalletReservation.Status.RELEASED)

        settle = self.client.post(
            "/api/billing/settle/",
            data={"call_id": "api-call-settle", "usage": {"input_tokens": 1000, "output_tokens": 100}},
            content_type="application/json",
        )
        self.assertEqual(settle.status_code, 200)
        self.assertEqual(settle.json()["status"], "settled")

    def test_billing_api_requires_login(self):
        self.client.logout()
        response = self.client.get("/api/billing/wallet/")
        self.assertEqual(response.status_code, 401)

    def test_billing_api_rejects_invalid_payloads(self):
        bad_recharge = self.client.post("/api/billing/recharge/", data={"amount_rmb": "abc"}, content_type="application/json")
        self.assertEqual(bad_recharge.status_code, 400)

        missing_call = self.client.post("/api/billing/reservations/", data={"reserved_u": 100_000}, content_type="application/json")
        self.assertEqual(missing_call.status_code, 400)

        bad_reserve = self.client.post("/api/billing/reservations/", data={"call_id": "bad-reserve", "reserved_u": "abc"}, content_type="application/json")
        self.assertEqual(bad_reserve.status_code, 400)

        bad_usage = self.client.post(
            "/api/billing/settle/",
            data={"call_id": "bad-usage", "usage": {"input_tokens": "abc"}},
            content_type="application/json",
        )
        self.assertEqual(bad_usage.status_code, 400)

        non_object_usage = self.client.post(
            "/api/billing/settle/",
            data={"call_id": "bad-usage-shape", "usage": "not-an-object"},
            content_type="application/json",
        )
        self.assertEqual(non_object_usage.status_code, 400)
