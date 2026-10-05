import uuid

from django.db import models

from apps.common.models import UserOwnedModel


def session_id():
    return f"int_{uuid.uuid4().hex}"


def turn_id():
    return f"itr_{uuid.uuid4().hex}"


class InterviewSession(UserOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ABORTED = "aborted", "Aborted"

    public_id = models.CharField(max_length=40, unique=True, default=session_id)
    mode = models.CharField(max_length=16, choices=[("general", "General"), ("custom", "Custom")])
    title = models.CharField(max_length=160)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    report = models.JSONField(default=dict, blank=True)
    # Request lease prevents inserting a follow-up while another answer advances.
    ai_busy_since = models.DateTimeField(null=True, blank=True)
    ai_busy_kind = models.CharField(max_length=32, blank=True)
    ai_busy_token = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["user", "status", "created_at"])]


class InterviewTurn(UserOwnedModel):
    public_id = models.CharField(max_length=40, unique=True, default=turn_id)
    session = models.ForeignKey(InterviewSession, related_name="turns", on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=16, choices=[("main", "Main"), ("follow_up", "Follow up")], default="main")
    parent = models.OneToOneField("self", related_name="follow_up", null=True, blank=True, on_delete=models.CASCADE)
    question_id = models.CharField(max_length=80, blank=True)
    prompt = models.TextField()
    category = models.CharField(max_length=32, blank=True)
    difficulty = models.CharField(max_length=16, default="intermediate")
    source = models.CharField(max_length=32, default="curated")
    answer = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=[("pending", "Pending"), ("completed", "Completed"), ("skipped", "Skipped")], default="pending")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["order", "pk"]
        constraints = [models.UniqueConstraint(fields=["session", "order"], name="interview_unique_turn_order")]
