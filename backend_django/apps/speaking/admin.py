from django.contrib import admin

from .models import LanguageTakeawayEntry, P1CorpusEntry, P2CorpusEntry, SpeakingAttempt, SpeakingReport, SpeakingTrainingObservation, SpeakingTurn


@admin.register(SpeakingAttempt)
class SpeakingAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "mode", "status", "target_band", "created_at")
    list_filter = ("mode", "status")
    search_fields = ("legacy_attempt_id", "user__username", "full_name", "english_name")


@admin.register(SpeakingTurn)
class SpeakingTurnAdmin(admin.ModelAdmin):
    list_display = ("attempt", "turn_id", "sequence", "part", "user", "created_at")
    search_fields = ("turn_id", "question", "transcript_cleaned", "user__username")


@admin.register(SpeakingReport)
class SpeakingReportAdmin(admin.ModelAdmin):
    list_display = ("attempt", "user", "overall_band", "created_at")
    search_fields = ("attempt__legacy_attempt_id", "user__username", "feedback_summary")


@admin.register(SpeakingTrainingObservation)
class SpeakingTrainingObservationAdmin(admin.ModelAdmin):
    list_display = ("observation_id", "user", "part", "weak_item_flag", "overall_band", "next_due")
    list_filter = ("part", "weak_item_flag", "model_version")
    search_fields = ("observation_id", "legacy_attempt_id", "legacy_turn_id", "question_id", "question", "user__username")


@admin.register(P1CorpusEntry)
class P1CorpusEntryAdmin(admin.ModelAdmin):
    list_display = ("question_id", "topic", "user", "updated_at")
    search_fields = ("question_id", "topic", "question", "corpus_text", "user__username")


@admin.register(P2CorpusEntry)
class P2CorpusEntryAdmin(admin.ModelAdmin):
    list_display = ("entry_id", "category", "title", "user", "updated_at")
    list_filter = ("category",)
    search_fields = ("entry_id", "title", "material_text", "linked_question", "user__username")


@admin.register(LanguageTakeawayEntry)
class LanguageTakeawayEntryAdmin(admin.ModelAdmin):
    list_display = ("entry_id", "source_text", "chinese_text", "user", "updated_at")
    search_fields = ("entry_id", "source_text", "chinese_text", "user__username")
