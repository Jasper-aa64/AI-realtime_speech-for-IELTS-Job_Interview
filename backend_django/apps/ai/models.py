import hashlib
import uuid

from django.db import models

from apps.common.models import UserOwnedModel


class AITask(UserOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        FALLBACK = "fallback", "Fallback"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="ai_tasks")
    task_id = models.CharField(max_length=80, unique=True, null=True, blank=True)
    idempotency_key = models.CharField(max_length=180, unique=True, null=True, blank=True)
    call_id = models.CharField(max_length=160, blank=True, db_index=True)
    task_type = models.CharField(max_length=80)
    provider = models.CharField(max_length=80, default="codex")
    model = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    related_type = models.CharField(max_length=80, blank=True)
    related_id = models.CharField(max_length=80, blank=True)
    prompt_version = models.CharField(max_length=80, blank=True)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    available_at = models.DateTimeField(null=True, blank=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    worker_id = models.CharField(max_length=120, blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    result_payload = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)
    fallback_reason = models.TextField(blank=True)
    billing_reservation = models.ForeignKey(
        "billing.WalletReservation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ai_tasks",
    )
    usage = models.ForeignKey(
        "billing.CodexUsageEvent",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ai_tasks",
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "task_type", "status", "created_at"]),
            models.Index(fields=["user", "status", "available_at"]),
            models.Index(fields=["related_type", "related_id"]),
            models.Index(fields=["call_id"]),
        ]

    @property
    def is_terminal(self) -> bool:
        return self.status in {self.Status.SUCCEEDED, self.Status.FAILED, self.Status.FALLBACK, self.Status.CANCELLED}

    def save(self, *args, **kwargs):
        if not self.task_id:
            if self.idempotency_key:
                seed = f"{self.user_id}:{self.idempotency_key}"
            else:
                seed = f"{self.user_id}:{self.task_type}:{self.related_type}:{self.related_id}:{uuid.uuid4().hex}"
            self.task_id = f"aitask_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:24]}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.task_type}:{self.status}:{self.task_id or self.pk}"
