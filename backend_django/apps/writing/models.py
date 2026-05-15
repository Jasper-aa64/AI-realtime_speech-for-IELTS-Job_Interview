from django.db import models

from apps.common.models import UserOwnedModel


class WritingPrompt(models.Model):
    class TaskType(models.TextChoices):
        TASK1_ACADEMIC = "task1_academic", "Task 1 Academic"
        TASK2 = "task2", "Task 2"

    prompt_id = models.CharField(max_length=120, unique=True)
    task_type = models.CharField(max_length=32, choices=TaskType.choices)
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=120, blank=True)
    prompt = models.TextField()
    source = models.CharField(max_length=120, default="local_seed")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["task_type", "is_active"]),
        ]

    def __str__(self) -> str:
        return self.title


class WritingEntry(UserOwnedModel):
    class Status(models.TextChoices):
        SAVED = "saved", "Saved"
        SCORED = "scored", "Scored"

    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="writing_entries")
    entry_id = models.CharField(max_length=80, unique=True, blank=True)
    prompt = models.ForeignKey(WritingPrompt, null=True, blank=True, on_delete=models.SET_NULL, related_name="entries")
    legacy_entry_id = models.CharField(max_length=80, blank=True, db_index=True)
    task_type = models.CharField(max_length=32, choices=WritingPrompt.TaskType.choices)
    practice_date = models.DateField()
    title = models.CharField(max_length=200, blank=True)
    prompt_text = models.TextField()
    answer = models.TextField()
    word_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.SAVED)
    saved_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["user", "practice_date"]),
            models.Index(fields=["user", "task_type", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.task_type}:{self.practice_date}:{self.user_id}"


class WritingScore(UserOwnedModel):
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="writing_scores")
    entry = models.OneToOneField(WritingEntry, on_delete=models.CASCADE, related_name="score")
    overall_band = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    task_response = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    coherence_cohesion = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    lexical_resource = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    grammar_range_accuracy = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    feedback_markdown = models.TextField(blank=True)
    grammar_corrections = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=32, default="ai")
    billing_metadata = models.JSONField(default=dict, blank=True)
    scored_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["overall_band", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"writing score:{self.entry_id}"


class WritingLearnerProfile(UserOwnedModel):
    user = models.OneToOneField("accounts.CustomUser", on_delete=models.CASCADE, related_name="writing_learner_profile")
    total_scored = models.PositiveIntegerField(default=0)
    task_counts = models.JSONField(default=dict, blank=True)
    average_overall_band = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    criterion_averages = models.JSONField(default=dict, blank=True)
    tag_counts = models.JSONField(default=dict, blank=True)
    primary_focus = models.CharField(max_length=80, default="insufficient_data")
    primary_focus_text = models.TextField(blank=True)
    recent_evidence = models.JSONField(default=list, blank=True)
    profile_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"], name="writing_wri_user_id_282f13_idx"),
            models.Index(fields=["primary_focus", "updated_at"], name="writing_wri_primary_4c3efc_idx"),
        ]

    def __str__(self) -> str:
        return f"writing profile:{self.user_id}"
