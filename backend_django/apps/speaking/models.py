from django.db import models

from apps.common.models import UserOwnedModel


class SpeakingAttempt(UserOwnedModel):
    class Status(models.TextChoices):
        STARTED = "started", "Started"
        READY_TO_SCORE = "ready_to_score", "Ready to score"
        SCORED = "scored", "Scored"
        ABORTED = "aborted", "Aborted"

    class Mode(models.TextChoices):
        P1 = "p1", "Part 1"
        P2 = "p2", "Part 2"
        P3 = "p3", "Part 3"
        MOCK = "mock", "Mock"

    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="speaking_attempts")
    attempt_id = models.CharField(max_length=80, unique=True, blank=True)
    legacy_attempt_id = models.CharField(max_length=80, blank=True, db_index=True)
    mode = models.CharField(max_length=16, choices=Mode.choices)
    part = models.CharField(max_length=16, blank=True)
    title = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.STARTED)
    full_name = models.CharField(max_length=120, blank=True)
    english_name = models.CharField(max_length=120, blank=True)
    target_band = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["user", "mode", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.mode}:{self.status}:{self.pk}"


class SpeakingTurn(UserOwnedModel):
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="speaking_turns")
    attempt = models.ForeignKey(SpeakingAttempt, on_delete=models.CASCADE, related_name="turns")
    turn_id = models.CharField(max_length=80)
    sequence = models.PositiveIntegerField()
    part = models.CharField(max_length=16, blank=True)
    question = models.TextField()
    transcript_raw = models.TextField(blank=True)
    transcript_cleaned = models.TextField(blank=True)
    transcript_source = models.CharField(max_length=80, blank=True)
    audio_path = models.CharField(max_length=500, blank=True)
    duration_seconds = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    counts_toward_total = models.BooleanField(default=True)
    pronunciation = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["attempt", "turn_id"], name="unique_speaking_turn_per_attempt"),
        ]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["attempt", "sequence"]),
        ]

    def __str__(self) -> str:
        return f"{self.attempt_id}:{self.turn_id}"


class SpeakingReport(UserOwnedModel):
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="speaking_reports")
    attempt = models.OneToOneField(SpeakingAttempt, on_delete=models.CASCADE, related_name="report")
    overall_band = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    fluency_coherence = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    lexical_resource = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    grammar_range_accuracy = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    pronunciation = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    feedback_summary = models.TextField(blank=True)
    report_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["overall_band", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"speaking report:{self.attempt_id}"


class SpeakingTrainingObservation(UserOwnedModel):
    observation_id = models.CharField(max_length=160, unique=True)
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="speaking_training_observations")
    attempt = models.ForeignKey(SpeakingAttempt, null=True, blank=True, on_delete=models.SET_NULL, related_name="training_observations")
    turn = models.ForeignKey(SpeakingTurn, null=True, blank=True, on_delete=models.SET_NULL, related_name="training_observations")
    legacy_attempt_id = models.CharField(max_length=120, db_index=True)
    legacy_turn_id = models.CharField(max_length=120)
    question_id = models.CharField(max_length=160, db_index=True)
    part = models.CharField(max_length=16)
    question = models.TextField()
    transcript = models.TextField(blank=True)
    overall_band = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    fluency_coherence = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    lexical_resource = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    grammar_range_accuracy = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    pronunciation = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    relevance = models.DecimalField(max_digits=4, decimal_places=3)
    weak_item_flag = models.BooleanField(default=False)
    weak_reasons = models.JSONField(default=list, blank=True)
    model_version = models.CharField(max_length=80, blank=True)
    observed_at = models.DateTimeField()
    next_due = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"], name="speaking_sp_user_id_4197c9_idx"),
            models.Index(fields=["user", "next_due", "weak_item_flag"], name="speaking_sp_user_id_ef45e6_idx"),
            models.Index(fields=["question_id"], name="speaking_sp_questio_c54040_idx"),
            models.Index(fields=["user", "part", "weak_item_flag", "observed_at"], name="speaking_sp_user_id_8c53ce_idx"),
        ]

    def __str__(self) -> str:
        return self.observation_id


class P1CorpusEntry(UserOwnedModel):
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="p1_corpus_entries")
    question_id = models.CharField(max_length=160)
    topic = models.CharField(max_length=120, blank=True)
    question = models.TextField()
    corpus_text = models.TextField(blank=True)
    last_ai_answer = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "question_id"], name="unique_p1_corpus_question_per_user"),
        ]
        indexes = [
            models.Index(fields=["user", "topic"], name="speaking_p1_user_topic_idx"),
            models.Index(fields=["user", "updated_at"], name="speaking_p1_user_updated_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.question_id}"


class P2CorpusEntry(UserOwnedModel):
    class Category(models.TextChoices):
        PERSON = "person", "人物"
        PLACE = "place", "地点"
        EVENT = "event", "事件"
        OBJECT = "object", "物品"
        SPECIAL = "special", "特殊题目"

    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="p2_corpus_entries")
    entry_id = models.CharField(max_length=160)
    category = models.CharField(max_length=32, choices=Category.choices)
    title = models.CharField(max_length=200)
    material_text = models.TextField(blank=True)
    linked_question = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "entry_id"], name="unique_p2_corpus_entry_per_user"),
        ]
        indexes = [
            models.Index(fields=["user", "category"], name="speaking_p2_user_category_idx"),
            models.Index(fields=["user", "updated_at"], name="speaking_p2_user_updated_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.category}:{self.title}"


class P2BankCorpusEntry(UserOwnedModel):
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="p2_bank_corpus_entries")
    question_id = models.CharField(max_length=160)
    question = models.TextField()
    corpus_text = models.TextField(blank=True)
    last_ai_answer = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "question_id"], name="unique_p2_bank_corpus_question_per_user"),
        ]
        indexes = [
            models.Index(fields=["user", "updated_at"], name="speak_p2bank_user_upd_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.question_id}"


class P3BankFollowupCorpusEntry(UserOwnedModel):
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="p3_bank_followup_corpus_entries")
    p2_question_id = models.CharField(max_length=160)
    followup_id = models.CharField(max_length=200)
    followup_question = models.TextField()
    corpus_text = models.TextField(blank=True)
    last_ai_answer = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "followup_id"], name="unique_p3_bank_followup_per_user"),
        ]
        indexes = [
            models.Index(fields=["user", "p2_question_id"], name="speaking_p3bank_user_p2_idx"),
            models.Index(fields=["user", "updated_at"], name="speak_p3bank_user_upd_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.followup_id}"


class LanguageTakeawayEntry(UserOwnedModel):
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="language_takeaway_entries")
    entry_id = models.CharField(max_length=160)
    source_text = models.TextField()
    chinese_text = models.TextField(blank=True)
    source_language = models.CharField(max_length=32, blank=True)
    target_language = models.CharField(max_length=32, default="zh")
    context_url = models.TextField(blank=True)
    context_label = models.CharField(max_length=200, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "entry_id"], name="unique_language_takeaway_per_user"),
        ]
        indexes = [
            models.Index(fields=["user", "updated_at"], name="speaking_lt_user_updated_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.source_text[:40]}"


class TakeawayReviewState(UserOwnedModel):
    class Kind(models.TextChoices):
        LANGUAGE = "language", "Language"
        WRITING = "writing", "Writing"

    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="takeaway_review_states")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    state = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "kind"], name="unique_takeaway_review_state_per_user_kind"),
        ]
        indexes = [
            models.Index(fields=["user", "kind"], name="speaking_trs_user_kind_idx"),
            models.Index(fields=["user", "updated_at"], name="speaking_trs_user_updated_idx"),
        ]


class ExpressionReplacementEntry(UserOwnedModel):
    class Kind(models.TextChoices):
        LANGUAGE = "language", "Language"
        WRITING = "writing", "Writing"

    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="expression_replacement_entries")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    item_id = models.CharField(max_length=160)
    source = models.TextField(blank=True)
    replacements = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "kind", "item_id"], name="unique_expression_replacement_per_user_kind"),
        ]
        indexes = [
            models.Index(fields=["user", "kind"], name="speaking_expr_user_kind_idx"),
            models.Index(fields=["user", "updated_at"], name="speaking_expr_user_updated_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.kind}:{self.source[:40]}"

    def __str__(self) -> str:
        return f"takeaway review:{self.user_id}:{self.kind}"
