import json
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone

from apps.ai.models import AITask
from apps.ai.provider_adapters import (
    FallbackWritingScoreAdapter,
    MockSuccessWritingScoreAdapter,
    ProviderRunResult,
    apply_provider_run_result,
)
from apps.ai.services import (
    AITaskConflictError,
    AITaskError,
    cancel_ai_task,
    claim_ai_task,
    create_ai_task,
    fail_ai_task,
    fallback_ai_task,
    get_ai_task,
    recover_stale_running_ai_tasks,
    succeed_ai_task,
    task_payload,
    update_ai_task_progress,
)
from apps.ai.orchestration import (
    AIOrchestrationError,
    cancel_billable_ai_task,
    cancel_owned_ai_task,
    create_billable_ai_task,
    fail_billable_ai_task,
    fallback_billable_ai_task,
    recover_stale_ai_tasks,
    succeed_billable_ai_task,
)
from apps.billing.models import TokenWallet, WalletLedgerEntry, WalletReservation
from apps.billing.services import DEFAULT_INITIAL_GRANT_U, ensure_wallet
from apps.writing.models import WritingEntry, WritingLearnerProfile, WritingPrompt, WritingScore
from apps.writing.services import complete_score_task, create_score_task, fallback_score_task


class AITaskServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ai-user", password="test-pass")

    def test_create_ai_task_is_idempotent_for_same_user(self):
        first, first_created = create_ai_task(
            user=self.user,
            task_type="writing_score",
            idempotency_key="writing-score:entry-1",
            related_type="writing_entry",
            related_id="entry-1",
            call_id="call-entry-1",
            request_payload={"entry_id": "entry-1"},
        )
        second, second_created = create_ai_task(
            user=self.user,
            task_type="writing_score",
            idempotency_key="writing-score:entry-1",
            related_type="writing_entry",
            related_id="entry-1",
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.status, AITask.Status.PENDING)
        self.assertEqual(first.call_id, "call-entry-1")

    def test_idempotency_key_cannot_cross_users(self):
        create_ai_task(user=self.user, task_type="report", idempotency_key="shared-key")
        other = get_user_model().objects.create_user(username="ai-other", password="test-pass")

        with self.assertRaises(AITaskError):
            create_ai_task(user=other, task_type="report", idempotency_key="shared-key")

    def test_claim_progress_success_flow(self):
        task, _created = create_ai_task(user=self.user, task_type="speaking_report", idempotency_key="speaking-report:1")

        claimed = claim_ai_task(task.task_id, worker_id="worker-1")
        self.assertEqual(claimed.status, AITask.Status.RUNNING)
        self.assertEqual(claimed.attempt_count, 1)
        self.assertEqual(claimed.worker_id, "worker-1")

        progressed = update_ai_task_progress(task.task_id, 45, {"stage": "scoring"})
        self.assertEqual(progressed.progress_percent, 45)
        self.assertEqual(progressed.metadata["stage"], "scoring")

        succeeded = succeed_ai_task(task.task_id, {"overall_band": 6.0})
        self.assertEqual(succeeded.status, AITask.Status.SUCCEEDED)
        self.assertEqual(succeeded.progress_percent, 100)
        self.assertEqual(succeeded.result_payload["overall_band"], 6.0)
        self.assertIsNotNone(succeeded.finished_at)

    def test_retryable_failure_requeues_until_max_attempts(self):
        task, _created = create_ai_task(user=self.user, task_type="writing_score", idempotency_key="retry-task", max_attempts=2)

        claim_ai_task(task.task_id, worker_id="worker-1")
        retry = fail_ai_task(task.task_id, "provider timeout", error_code="timeout", retryable=True, retry_delay_seconds=30)
        self.assertEqual(retry.status, AITask.Status.PENDING)
        self.assertEqual(retry.error_code, "timeout")
        self.assertIsNotNone(retry.available_at)

        retry.available_at = None
        retry.save(update_fields=["available_at", "updated_at"])
        claim_ai_task(task.task_id, worker_id="worker-2")
        failed = fail_ai_task(task.task_id, "provider timeout", error_code="timeout", retryable=True)
        self.assertEqual(failed.status, AITask.Status.FAILED)
        self.assertIsNotNone(failed.finished_at)

    def test_fallback_marks_task_and_preserves_default_result(self):
        task, _created = create_ai_task(user=self.user, task_type="writing_score", idempotency_key="fallback-task")
        fallback = fallback_ai_task(task.task_id, "AI provider unavailable", {"feedback_markdown": "AI 评分生成失败，以下是系统默认建议。"})

        self.assertEqual(fallback.status, AITask.Status.FALLBACK)
        self.assertEqual(fallback.progress_percent, 100)
        self.assertEqual(fallback.fallback_reason, "AI provider unavailable")
        self.assertIn("AI 评分生成失败", fallback.result_payload["feedback_markdown"])

    def test_get_task_is_user_scoped(self):
        task, _created = create_ai_task(user=self.user, task_type="writing_score", idempotency_key="owned-task")
        other = get_user_model().objects.create_user(username="ai-other-owner", password="test-pass")

        self.assertEqual(get_ai_task(self.user, task.task_id), task)
        with self.assertRaises(AITaskError):
            get_ai_task(other, task.task_id)

    def test_task_payload_contains_refresh_safe_state(self):
        task, _created = create_ai_task(user=self.user, task_type="writing_score", idempotency_key="payload-task", request_payload={"entry_id": "entry-1"})
        payload = task_payload(task)

        self.assertEqual(payload["id"], task.task_id)
        self.assertEqual(payload["status"], AITask.Status.PENDING)
        self.assertEqual(payload["request_payload"]["entry_id"], "entry-1")

    def test_stale_running_task_requeues_when_attempts_remain(self):
        task, _created = create_ai_task(user=self.user, task_type="writing_score", idempotency_key="stale-requeue", max_attempts=3)

        claim_ai_task(task.task_id, worker_id="worker-1")
        AITask.objects.filter(pk=task.pk).update(
            started_at=timezone.now() - timezone.timedelta(seconds=120),
            progress_percent=42,
            updated_at=timezone.now(),
        )

        recovered = recover_stale_running_ai_tasks(60)

        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].status, AITask.Status.PENDING)
        self.assertEqual(recovered[0].error_code, "worker_lease_expired")
        self.assertEqual(recovered[0].progress_percent, 0)
        self.assertEqual(recovered[0].worker_id, "")
        self.assertIsNone(recovered[0].started_at)
        self.assertEqual(recover_stale_running_ai_tasks(60), [])

    def test_cancelling_already_terminal_task_is_safe(self):
        task, _created = create_ai_task(user=self.user, task_type="writing_score", idempotency_key="terminal-cancel")
        succeed_ai_task(task.task_id, {"overall_band": 6.0})

        cancelled = cancel_ai_task(task.task_id, reason="stop this task")

        self.assertEqual(cancelled.status, AITask.Status.SUCCEEDED)
        self.assertEqual(cancelled.result_payload["overall_band"], 6.0)

    def test_cancelling_running_non_billable_task_is_not_allowed(self):
        task, _created = create_ai_task(user=self.user, task_type="speaking_report", idempotency_key="running-non-billable-cancel")
        claim_ai_task(task.task_id, worker_id="worker-1")

        with self.assertRaises(AITaskConflictError):
            cancel_ai_task(task.task_id, reason="user tried to stop running task")

        task.refresh_from_db()
        self.assertEqual(task.status, AITask.Status.RUNNING)
        self.assertEqual(task.worker_id, "worker-1")


class AITaskApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="ai-api-user", password="test-pass")
        self.client.force_login(self.user)

    def test_create_and_get_task_api(self):
        created = self.client.post(
            "/api/ai/tasks/",
            data={
                "task_type": "writing_score",
                "idempotency_key": "api-writing-score:entry-1",
                "related_type": "writing_entry",
                "related_id": "entry-1",
                "request_payload": {"entry_id": "entry-1"},
            },
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        task_id = created.json()["task"]["id"]

        duplicated = self.client.post(
            "/api/ai/tasks/",
            data={"task_type": "writing_score", "idempotency_key": "api-writing-score:entry-1"},
            content_type="application/json",
        )
        self.assertEqual(duplicated.status_code, 200)
        self.assertFalse(duplicated.json()["created"])
        self.assertEqual(duplicated.json()["task"]["id"], task_id)

        detail = self.client.get(f"/api/ai/tasks/{task_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["id"], task_id)

    def test_task_api_requires_login(self):
        self.client.logout()
        response = self.client.post("/api/ai/tasks/", data={"task_type": "writing_score"}, content_type="application/json")
        self.assertEqual(response.status_code, 401)

    def test_cancel_task_api_requires_login(self):
        task, _created = create_ai_task(user=self.user, task_type="writing_score", idempotency_key="api-cancel-auth")
        self.client.logout()

        response = self.client.post(f"/api/ai/tasks/{task.task_id}/cancel/", content_type="application/json")

        self.assertEqual(response.status_code, 401)

    def test_task_api_is_user_scoped(self):
        task, _created = create_ai_task(user=self.user, task_type="writing_score", idempotency_key="api-owned-task")
        other_client = Client()
        other = get_user_model().objects.create_user(username="ai-api-other", password="test-pass")
        other_client.force_login(other)

        response = other_client.get(f"/api/ai/tasks/{task.task_id}")
        self.assertEqual(response.status_code, 404)

    def test_cancel_task_api_is_user_scoped(self):
        task, _created = create_ai_task(user=self.user, task_type="writing_score", idempotency_key="api-cancel-owned-task")
        other_client = Client()
        other = get_user_model().objects.create_user(username="ai-api-cancel-other", password="test-pass")
        other_client.force_login(other)

        response = other_client.post(f"/api/ai/tasks/{task.task_id}/cancel/", content_type="application/json")

        self.assertEqual(response.status_code, 404)

    def test_create_billable_task_api_reserves_wallet(self):
        created = self.client.post(
            "/api/ai/tasks/",
            data={
                "task_type": "writing_score",
                "idempotency_key": "api-billable-writing:entry-1",
                "related_type": "writing_entry",
                "related_id": "entry-1",
                "reserved_u": 250_000,
            },
            content_type="application/json",
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["task"]["billing"]["reservation_id"], WalletReservation.objects.get(user=self.user).reservation_id)
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.reserved_u, 250_000)

    def test_owner_can_cancel_pending_billable_task_and_release_reservation(self):
        task, _created = create_billable_ai_task(
            user=self.user,
            task_type="writing_score",
            reserved_u=250_000,
            idempotency_key="api-cancel-pending-billable",
        )

        response = self.client.post(
            f"/api/ai/tasks/{task.task_id}/cancel/",
            data={"reason": "user cancelled from UI"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], task.task_id)
        self.assertEqual(response.json()["status"], AITask.Status.CANCELLED)
        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.RELEASED)
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.reserved_u, 0)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U)

    def test_running_billable_task_cancel_returns_conflict_and_keeps_reservation(self):
        task, _created = create_billable_ai_task(
            user=self.user,
            task_type="writing_score",
            reserved_u=250_000,
            idempotency_key="api-cancel-running-billable",
        )
        claim_ai_task(task.task_id, worker_id="api-running-worker")

        response = self.client.post(
            f"/api/ai/tasks/{task.task_id}/cancel/",
            data={"reason": "user cancelled running task"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "AI task is already running and cannot be cancelled"})
        task.refresh_from_db()
        self.assertEqual(task.status, AITask.Status.RUNNING)
        self.assertEqual(task.worker_id, "api-running-worker")
        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.RESERVED)
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.reserved_u, 250_000)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U - 250_000)

    def test_running_non_billable_task_cancel_returns_conflict(self):
        task, _created = create_ai_task(user=self.user, task_type="speaking_report", idempotency_key="api-cancel-running-non-billable")
        claim_ai_task(task.task_id, worker_id="api-non-billable-worker")

        response = self.client.post(
            f"/api/ai/tasks/{task.task_id}/cancel/",
            data={"reason": "user cancelled running task"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "AI task is already running and cannot be cancelled"})
        task.refresh_from_db()
        self.assertEqual(task.status, AITask.Status.RUNNING)
        self.assertEqual(task.worker_id, "api-non-billable-worker")

    def test_cancelling_terminal_task_api_is_noop(self):
        task, _created = create_ai_task(user=self.user, task_type="writing_score", idempotency_key="api-terminal-cancel")
        succeed_ai_task(task.task_id, {"overall_band": 6.5})

        response = self.client.post(f"/api/ai/tasks/{task.task_id}/cancel/", content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], AITask.Status.SUCCEEDED)
        self.assertEqual(response.json()["result_payload"]["overall_band"], 6.5)


class AIBillableTaskOrchestrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="billable-ai-user", password="test-pass")

    def test_create_billable_task_reserves_wallet_once(self):
        task, created = create_billable_ai_task(
            user=self.user,
            task_type="writing_score",
            reserved_u=500_000,
            idempotency_key="billable-writing:entry-1",
            related_type="writing_entry",
            related_id="entry-1",
        )
        duplicate, duplicate_created = create_billable_ai_task(
            user=self.user,
            task_type="writing_score",
            reserved_u=500_000,
            idempotency_key="billable-writing:entry-1",
        )

        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(task.pk, duplicate.pk)
        self.assertEqual(task.billing_reservation.status, WalletReservation.Status.RESERVED)
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U - 500_000)
        self.assertEqual(wallet.reserved_u, 500_000)
        self.assertEqual(WalletReservation.objects.filter(user=self.user).count(), 1)
        self.assertEqual(WalletLedgerEntry.objects.filter(user=self.user, entry_type=WalletLedgerEntry.EntryType.RESERVE).count(), 1)

    def test_billable_task_rejects_cross_user_idempotency(self):
        create_billable_ai_task(user=self.user, task_type="writing_score", reserved_u=100_000, idempotency_key="shared-billable-key")
        other = get_user_model().objects.create_user(username="billable-ai-other", password="test-pass")

        with self.assertRaises(AIOrchestrationError):
            create_billable_ai_task(user=other, task_type="writing_score", reserved_u=100_000, idempotency_key="shared-billable-key")

    def test_succeed_billable_task_settles_reservation_and_links_usage(self):
        task, _created = create_billable_ai_task(
            user=self.user,
            task_type="writing_score",
            reserved_u=500_000,
            idempotency_key="billable-success",
        )
        claim_ai_task(task.task_id, worker_id="worker-1")

        succeeded = succeed_billable_ai_task(task.task_id, {"overall_band": 6.0}, {"input_tokens": 1000, "output_tokens": 100})

        self.assertEqual(succeeded.status, AITask.Status.SUCCEEDED)
        self.assertEqual(succeeded.result_payload["overall_band"], 6.0)
        self.assertEqual(succeeded.result_payload["billing"]["status"], "settled")
        self.assertIsNotNone(succeeded.usage)
        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.SETTLED)
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.reserved_u, 0)
        self.assertGreater(wallet.balance_u, DEFAULT_INITIAL_GRANT_U - 500_000)

    def test_fallback_billable_task_releases_reservation(self):
        task, _created = create_billable_ai_task(user=self.user, task_type="writing_score", reserved_u=300_000, idempotency_key="billable-fallback")

        fallback = fallback_billable_ai_task(task.task_id, "provider unavailable", {"feedback_markdown": "AI 评分生成失败，以下是系统默认建议。"})

        self.assertEqual(fallback.status, AITask.Status.FALLBACK)
        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.RELEASED)
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.reserved_u, 0)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U)

    def test_retryable_failure_keeps_reservation_until_terminal_failure(self):
        task, _created = create_billable_ai_task(user=self.user, task_type="speaking_report", reserved_u=300_000, idempotency_key="billable-retry", max_attempts=1)
        claim_ai_task(task.task_id, worker_id="worker-1")

        failed = fail_billable_ai_task(task.task_id, "provider timeout", error_code="timeout", retryable=True)

        self.assertEqual(failed.status, AITask.Status.FAILED)
        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.RELEASED)
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.reserved_u, 0)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U)

    def test_billable_task_rejects_invalid_reservation(self):
        ensure_wallet(self.user)
        with self.assertRaises(AIOrchestrationError):
            create_billable_ai_task(user=self.user, task_type="writing_score", reserved_u=0, idempotency_key="bad-reserve")

    def test_stale_running_task_max_attempt_failure_releases_reservation(self):
        task, _created = create_billable_ai_task(
            user=self.user,
            task_type="writing_score",
            reserved_u=300_000,
            idempotency_key="stale-terminal-release",
            max_attempts=1,
        )
        claim_ai_task(task.task_id, worker_id="worker-1")
        AITask.objects.filter(pk=task.pk).update(started_at=timezone.now() - timezone.timedelta(seconds=120), updated_at=timezone.now())

        recovered = recover_stale_ai_tasks(60)

        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].status, AITask.Status.FAILED)
        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.RELEASED)
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.reserved_u, 0)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U)
        self.assertEqual(
            WalletLedgerEntry.objects.filter(user=self.user, call_id=task.call_id, entry_type=WalletLedgerEntry.EntryType.RELEASE).count(),
            1,
        )
        self.assertEqual(recover_stale_ai_tasks(60), [])

    def test_cancel_pending_billable_task_releases_reservation(self):
        task, _created = create_billable_ai_task(
            user=self.user,
            task_type="writing_score",
            reserved_u=300_000,
            idempotency_key="cancel-pending-billable",
        )

        cancelled = cancel_billable_ai_task(task.task_id, "user cancelled request")

        self.assertEqual(cancelled.status, AITask.Status.CANCELLED)
        self.assertEqual(cancelled.error_code, "cancelled")
        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.RELEASED)
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.reserved_u, 0)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U)

        repeated = cancel_billable_ai_task(task.task_id, "try again")
        self.assertEqual(repeated.status, AITask.Status.CANCELLED)
        self.assertEqual(
            WalletLedgerEntry.objects.filter(user=self.user, call_id=task.call_id, entry_type=WalletLedgerEntry.EntryType.RELEASE).count(),
            1,
        )

    def test_cancel_running_billable_task_is_not_allowed(self):
        task, _created = create_billable_ai_task(
            user=self.user,
            task_type="writing_score",
            reserved_u=300_000,
            idempotency_key="cancel-running-billable-conflict",
        )
        claim_ai_task(task.task_id, worker_id="worker-1")

        with self.assertRaises(AITaskConflictError):
            cancel_billable_ai_task(task.task_id, "user cancelled after scoring started")

        task.refresh_from_db()
        self.assertEqual(task.status, AITask.Status.RUNNING)
        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.RESERVED)
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.reserved_u, 300_000)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U - 300_000)

    def test_cancel_owned_running_billable_task_propagates_conflict_without_release(self):
        task, _created = create_billable_ai_task(
            user=self.user,
            task_type="writing_score",
            reserved_u=300_000,
            idempotency_key="cancel-owned-running-billable-conflict",
        )
        claim_ai_task(task.task_id, worker_id="worker-2")

        with self.assertRaises(AITaskConflictError):
            cancel_owned_ai_task(self.user, task.task_id, reason="user cancelled after worker claim")

        task.refresh_from_db()
        self.assertEqual(task.status, AITask.Status.RUNNING)
        self.assertEqual(task.worker_id, "worker-2")
        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.RESERVED)
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.reserved_u, 300_000)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U - 300_000)

    def test_cancelling_already_terminal_billable_task_is_safe(self):
        task, _created = create_billable_ai_task(
            user=self.user,
            task_type="writing_score",
            reserved_u=300_000,
            idempotency_key="terminal-billable-cancel",
        )
        fallback_billable_ai_task(task.task_id, "provider unavailable", {"feedback_markdown": "fallback"})

        cancelled = cancel_billable_ai_task(task.task_id, "user cancelled request")

        self.assertEqual(cancelled.status, AITask.Status.FALLBACK)
        self.assertEqual(
            WalletLedgerEntry.objects.filter(user=self.user, call_id=task.call_id, entry_type=WalletLedgerEntry.EntryType.RELEASE).count(),
            1,
        )

    def test_cancelled_billable_task_ignores_late_success_callback(self):
        task, _created = create_billable_ai_task(
            user=self.user,
            task_type="writing_score",
            reserved_u=300_000,
            idempotency_key="cancelled-billable-success-noop",
        )
        cancel_billable_ai_task(task.task_id, "user cancelled request")

        succeeded = succeed_billable_ai_task(task.task_id, {"overall_band": 6.0}, {"input_tokens": 1000, "output_tokens": 100})

        self.assertEqual(succeeded.status, AITask.Status.CANCELLED)
        wallet = TokenWallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U)
        self.assertEqual(wallet.reserved_u, 0)
        self.assertEqual(
            WalletLedgerEntry.objects.filter(user=self.user, call_id=task.call_id, entry_type=WalletLedgerEntry.EntryType.SETTLE).count(),
            0,
        )


class AIProviderAdapterTests(TestCase):
    def test_apply_provider_run_result_returns_pending_summary_for_retryable_failure(self):
        user = get_user_model().objects.create_user(username="provider-retry-user", password="test-pass")
        prompt = WritingPrompt.objects.create(
            prompt_id="provider-retry-prompt",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Provider retry prompt",
            prompt="Some people think universities should offer more practical courses. Discuss.",
        )
        entry = WritingEntry.objects.create(
            user=user,
            prompt=prompt,
            task_type=WritingPrompt.TaskType.TASK2,
            practice_date=timezone.localdate(),
            title=prompt.title,
            prompt_text=prompt.prompt,
            answer="Practical courses can improve employability, but theory still supports long-term learning.",
            word_count=12,
        )
        created = create_score_task(user, entry.entry_id, {"reserved_u": 300_000})
        claimed = claim_ai_task(created["task"]["id"], worker_id="provider-retry-worker")

        applied = apply_provider_run_result(
            claimed,
            ProviderRunResult.retryable_failure(
                "provider timed out",
                error_code="provider_timeout",
                retry_delay_seconds=45,
            ),
        )

        self.assertEqual(applied.summary_status, AITask.Status.PENDING)
        self.assertEqual(applied.task.status, AITask.Status.PENDING)
        self.assertEqual(applied.task.error_code, "provider_timeout")
        self.assertIsNotNone(applied.task.available_at)
        reservation = WalletReservation.objects.get(pk=applied.task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.RESERVED)
        self.assertFalse(WritingScore.objects.filter(entry=entry).exists())

    def test_apply_provider_run_result_returns_failed_summary_for_terminal_failure(self):
        user = get_user_model().objects.create_user(username="provider-terminal-user", password="test-pass")
        prompt = WritingPrompt.objects.create(
            prompt_id="provider-terminal-prompt",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Provider terminal prompt",
            prompt="Some people think young people should work before university. Discuss.",
        )
        entry = WritingEntry.objects.create(
            user=user,
            prompt=prompt,
            task_type=WritingPrompt.TaskType.TASK2,
            practice_date=timezone.localdate(),
            title=prompt.title,
            prompt_text=prompt.prompt,
            answer="A gap before university can build maturity, but it may also delay academic momentum.",
            word_count=14,
        )
        created = create_score_task(user, entry.entry_id, {"reserved_u": 300_000})
        claimed = claim_ai_task(created["task"]["id"], worker_id="provider-terminal-worker")

        applied = apply_provider_run_result(
            claimed,
            ProviderRunResult.terminal_failure(
                "provider rejected the request",
                error_code="provider_rejected",
            ),
        )

        self.assertEqual(applied.summary_status, AITask.Status.FAILED)
        self.assertEqual(applied.task.status, AITask.Status.FAILED)
        self.assertEqual(applied.task.error_code, "provider_rejected")
        reservation = WalletReservation.objects.get(pk=applied.task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.RELEASED)
        self.assertFalse(WritingScore.objects.filter(entry=entry).exists())


class AIWorkerCommandTests(TestCase):
    def test_run_ai_tasks_processes_pending_writing_score_with_fallback(self):
        user = get_user_model().objects.create_user(username="worker-writing-user", password="test-pass")
        prompt = WritingPrompt.objects.create(
            prompt_id="worker-writing-prompt",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Worker writing prompt",
            prompt="Some people think children should learn coding at school. Discuss.",
        )
        entry = WritingEntry.objects.create(
            user=user,
            prompt=prompt,
            task_type=WritingPrompt.TaskType.TASK2,
            practice_date=timezone.localdate(),
            title=prompt.title,
            prompt_text=prompt.prompt,
            answer="Coding can help children think logically, but schools should balance it with reading and communication.",
            word_count=15,
        )
        created = create_score_task(user, entry.entry_id, {"reserved_u": 300_000})
        out = StringIO()

        call_command("run_ai_tasks", "--limit", "5", "--worker-id", "test-worker", stdout=out)

        summary = json.loads(out.getvalue())
        self.assertEqual(summary["claimed"], 1)
        self.assertEqual(summary["completed"], 1)
        task = AITask.objects.get(task_id=created["task"]["id"])
        self.assertEqual(task.status, AITask.Status.FALLBACK)
        self.assertEqual(task.worker_id, "test-worker")
        self.assertTrue(WritingScore.objects.filter(entry=entry, source="fallback").exists())
        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.RELEASED)
        wallet = TokenWallet.objects.get(user=user)
        self.assertEqual(wallet.balance_u, DEFAULT_INITIAL_GRANT_U)
        self.assertEqual(wallet.reserved_u, 0)

    def test_run_ai_tasks_processes_mock_success_provider_and_settles_usage(self):
        user = get_user_model().objects.create_user(username="worker-mock-success-user", password="test-pass")
        prompt = WritingPrompt.objects.create(
            prompt_id="worker-mock-success-prompt",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Worker mock success prompt",
            prompt="Some people think governments should spend more money on public libraries. Discuss.",
        )
        entry = WritingEntry.objects.create(
            user=user,
            prompt=prompt,
            task_type=WritingPrompt.TaskType.TASK2,
            practice_date=timezone.localdate(),
            title=prompt.title,
            prompt_text=prompt.prompt,
            answer="Public libraries can support equal access to learning, but investment should also consider digital services and local demand.",
            word_count=18,
        )
        created = create_score_task(
            user,
            entry.entry_id,
            {"reserved_u": 300_000, "provider": "mock_success", "model": "mock-writing-score-v1"},
        )
        out = StringIO()

        call_command("run_ai_tasks", "--limit", "5", "--worker-id", "mock-success-worker", stdout=out)

        summary = json.loads(out.getvalue())
        self.assertEqual(summary["claimed"], 1)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["skipped"], 0)
        self.assertEqual(summary["items"], [{"task_id": created["task"]["id"], "task_type": "writing_score", "status": AITask.Status.SUCCEEDED}])

        task = AITask.objects.select_related("usage").get(task_id=created["task"]["id"])
        self.assertEqual(task.status, AITask.Status.SUCCEEDED)
        self.assertEqual(task.provider, "mock_success")
        self.assertEqual(task.model, "mock-writing-score-v1")
        self.assertIsNotNone(task.usage)
        self.assertGreater(task.usage.input_tokens, 0)
        self.assertEqual(task.result_payload["billing"]["status"], "settled")

        score = WritingScore.objects.get(entry=entry)
        self.assertEqual(score.source, "ai")
        self.assertEqual(score.billing_metadata, task.usage.raw_usage)
        profile = WritingLearnerProfile.objects.get(user=user)
        self.assertEqual(profile.total_scored, 1)

        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.SETTLED)
        wallet = TokenWallet.objects.get(user=user)
        self.assertEqual(wallet.reserved_u, 0)

        repeated = complete_score_task(task.task_id, {"score": task.result_payload["score"], "usage": task.usage.raw_usage})
        self.assertEqual(repeated["ai_task"]["status"], AITask.Status.SUCCEEDED)
        profile.refresh_from_db()
        self.assertEqual(profile.total_scored, 1)
        self.assertEqual(
            WalletLedgerEntry.objects.filter(user=user, call_id=task.call_id, entry_type=WalletLedgerEntry.EntryType.SETTLE).count(),
            1,
        )

    def test_run_ai_tasks_can_recover_stale_running_task_before_claiming(self):
        user = get_user_model().objects.create_user(username="worker-recover-user", password="test-pass")
        prompt = WritingPrompt.objects.create(
            prompt_id="worker-recover-prompt",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Worker recovery prompt",
            prompt="Some people think university should be free for everyone. Discuss both views and give your opinion.",
        )
        entry = WritingEntry.objects.create(
            user=user,
            prompt=prompt,
            task_type=WritingPrompt.TaskType.TASK2,
            practice_date=timezone.localdate(),
            title=prompt.title,
            prompt_text=prompt.prompt,
            answer="Free university can widen access, but governments still need a sustainable way to fund quality teaching.",
            word_count=16,
        )
        created = create_score_task(user, entry.entry_id, {"reserved_u": 300_000})
        task = AITask.objects.get(task_id=created["task"]["id"])
        claim_ai_task(task.task_id, worker_id="stale-worker")
        AITask.objects.filter(pk=task.pk).update(started_at=timezone.now() - timezone.timedelta(seconds=120), updated_at=timezone.now())
        out = StringIO()

        call_command(
            "run_ai_tasks",
            "--limit",
            "5",
            "--worker-id",
            "recovery-worker",
            "--recover-stale-seconds",
            "60",
            stdout=out,
        )

        summary = json.loads(out.getvalue())
        self.assertEqual(summary["recovered"]["requeued"], 1)
        self.assertEqual(summary["recovered"]["failed"], 0)
        self.assertEqual(summary["claimed"], 1)
        self.assertEqual(summary["completed"], 1)
        task.refresh_from_db()
        self.assertEqual(task.status, AITask.Status.FALLBACK)
        self.assertEqual(task.worker_id, "recovery-worker")

    def test_run_ai_tasks_does_not_claim_cancelled_task(self):
        user = get_user_model().objects.create_user(username="worker-cancelled-user", password="test-pass")
        prompt = WritingPrompt.objects.create(
            prompt_id="worker-cancelled-prompt",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Worker cancelled prompt",
            prompt="Some people think universities should focus only on job skills. Discuss.",
        )
        entry = WritingEntry.objects.create(
            user=user,
            prompt=prompt,
            task_type=WritingPrompt.TaskType.TASK2,
            practice_date=timezone.localdate(),
            title=prompt.title,
            prompt_text=prompt.prompt,
            answer="Universities should teach job skills, but they should also develop wider thinking and research abilities.",
            word_count=15,
        )
        created = create_score_task(user, entry.entry_id, {"reserved_u": 300_000})
        cancel_billable_ai_task(created["task"]["id"], "user cancelled before worker claim")
        out = StringIO()

        call_command("run_ai_tasks", "--limit", "5", "--worker-id", "cancel-aware-worker", stdout=out)

        summary = json.loads(out.getvalue())
        self.assertEqual(summary["claimed"], 0)
        self.assertEqual(summary["completed"], 0)
        self.assertEqual(summary["failed"], 0)
        self.assertFalse(WritingScore.objects.filter(entry=entry).exists())

    def test_run_ai_tasks_skips_unsupported_task_without_crashing_batch(self):
        user = get_user_model().objects.create_user(username="worker-unsupported-user", password="test-pass")
        prompt = WritingPrompt.objects.create(
            prompt_id="worker-unsupported-prompt",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Worker unsupported prompt",
            prompt="Some people think all city centres should be car free. Discuss.",
        )
        entry = WritingEntry.objects.create(
            user=user,
            prompt=prompt,
            task_type=WritingPrompt.TaskType.TASK2,
            practice_date=timezone.localdate(),
            title=prompt.title,
            prompt_text=prompt.prompt,
            answer="Car-free centres can improve air quality, but delivery access and public transport still need careful planning.",
            word_count=16,
        )
        created = create_score_task(user, entry.entry_id, {"reserved_u": 300_000})
        unsupported, _created = create_billable_ai_task(
            user=user,
            task_type="speaking_report",
            reserved_u=250_000,
            idempotency_key="unsupported-billable-worker-task",
        )
        out = StringIO()

        call_command("run_ai_tasks", "--limit", "5", "--worker-id", "unsupported-worker", stdout=out)

        summary = json.loads(out.getvalue())
        self.assertEqual(summary["claimed"], 2)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(len(summary["items"]), 2)
        self.assertIn({"task_id": unsupported.task_id, "task_type": "speaking_report", "status": "skipped"}, summary["items"])
        self.assertIn({"task_id": created["task"]["id"], "task_type": "writing_score", "status": AITask.Status.FALLBACK}, summary["items"])

        unsupported.refresh_from_db()
        self.assertEqual(unsupported.status, AITask.Status.FAILED)
        self.assertEqual(unsupported.error_code, "unsupported_task_type")
        unsupported_reservation = WalletReservation.objects.get(pk=unsupported.billing_reservation_id)
        self.assertEqual(unsupported_reservation.status, WalletReservation.Status.RELEASED)

        supported = AITask.objects.get(task_id=created["task"]["id"])
        self.assertEqual(supported.status, AITask.Status.FALLBACK)
        self.assertTrue(WritingScore.objects.filter(entry=entry, source="fallback").exists())

    def test_run_ai_tasks_completes_mock_success_when_cancel_attempt_happens_after_claim(self):
        user = get_user_model().objects.create_user(username="worker-cancel-race-user", password="test-pass")
        prompt = WritingPrompt.objects.create(
            prompt_id="worker-cancel-race-prompt",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Worker cancel race prompt",
            prompt="Some people think museums should be free to enter. Discuss.",
        )
        entry = WritingEntry.objects.create(
            user=user,
            prompt=prompt,
            task_type=WritingPrompt.TaskType.TASK2,
            practice_date=timezone.localdate(),
            title=prompt.title,
            prompt_text=prompt.prompt,
            answer="Museums can become more accessible if they are free, but funding still needs support from public budgets or donations.",
            word_count=19,
        )
        created = create_score_task(user, entry.entry_id, {"reserved_u": 300_000, "provider": "mock_success"})
        out = StringIO()
        original_run = MockSuccessWritingScoreAdapter.run

        def cancel_before_success(adapter, task):
            with self.assertRaises(AITaskConflictError):
                cancel_billable_ai_task(task.task_id, "user cancelled after worker claim")
            return original_run(adapter, task)

        with patch.object(MockSuccessWritingScoreAdapter, "run", autospec=True, side_effect=cancel_before_success):
            call_command("run_ai_tasks", "--limit", "5", "--worker-id", "cancel-race-worker", stdout=out)

        summary = json.loads(out.getvalue())
        self.assertEqual(summary["claimed"], 1)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["skipped"], 0)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["items"], [{"task_id": created["task"]["id"], "task_type": "writing_score", "status": AITask.Status.SUCCEEDED}])
        task = AITask.objects.get(task_id=created["task"]["id"])
        self.assertEqual(task.status, AITask.Status.SUCCEEDED)
        self.assertTrue(WritingScore.objects.filter(entry=entry, source="ai").exists())
        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.SETTLED)

    def test_run_ai_tasks_completes_fallback_when_cancel_attempt_happens_after_claim(self):
        user = get_user_model().objects.create_user(username="worker-fallback-cancel-race-user", password="test-pass")
        prompt = WritingPrompt.objects.create(
            prompt_id="worker-fallback-cancel-race-prompt",
            task_type=WritingPrompt.TaskType.TASK2,
            title="Worker fallback cancel race prompt",
            prompt="Some people think public parks should receive more funding. Discuss.",
        )
        entry = WritingEntry.objects.create(
            user=user,
            prompt=prompt,
            task_type=WritingPrompt.TaskType.TASK2,
            practice_date=timezone.localdate(),
            title=prompt.title,
            prompt_text=prompt.prompt,
            answer="Public parks improve health and community life, but city budgets still need balanced priorities.",
            word_count=15,
        )
        created = create_score_task(user, entry.entry_id, {"reserved_u": 300_000})
        out = StringIO()
        original_run = FallbackWritingScoreAdapter.run

        def cancel_before_fallback(adapter, task):
            with self.assertRaises(AITaskConflictError):
                cancel_billable_ai_task(task.task_id, "user cancelled after worker claim")
            return original_run(adapter, task)

        with patch.object(FallbackWritingScoreAdapter, "run", autospec=True, side_effect=cancel_before_fallback):
            call_command("run_ai_tasks", "--limit", "5", "--worker-id", "fallback-cancel-race-worker", stdout=out)

        summary = json.loads(out.getvalue())
        self.assertEqual(summary["claimed"], 1)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["skipped"], 0)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["items"], [{"task_id": created["task"]["id"], "task_type": "writing_score", "status": AITask.Status.FALLBACK}])
        task = AITask.objects.get(task_id=created["task"]["id"])
        self.assertEqual(task.status, AITask.Status.FALLBACK)
        self.assertTrue(WritingScore.objects.filter(entry=entry, source="fallback").exists())
        reservation = WalletReservation.objects.get(pk=task.billing_reservation_id)
        self.assertEqual(reservation.status, WalletReservation.Status.RELEASED)
