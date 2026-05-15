from django.contrib import admin

from .models import WritingEntry, WritingLearnerProfile, WritingPrompt, WritingScore


@admin.register(WritingPrompt)
class WritingPromptAdmin(admin.ModelAdmin):
    list_display = ("prompt_id", "task_type", "title", "category", "is_active")
    list_filter = ("task_type", "is_active", "category")
    search_fields = ("prompt_id", "title", "prompt")


@admin.register(WritingEntry)
class WritingEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "task_type", "practice_date", "status", "word_count", "created_at")
    list_filter = ("task_type", "status", "practice_date")
    search_fields = ("legacy_entry_id", "title", "answer", "user__username")


@admin.register(WritingScore)
class WritingScoreAdmin(admin.ModelAdmin):
    list_display = ("entry", "user", "overall_band", "source", "scored_at")
    list_filter = ("source",)
    search_fields = ("entry__title", "feedback_markdown", "user__username")


@admin.register(WritingLearnerProfile)
class WritingLearnerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "total_scored", "average_overall_band", "primary_focus", "updated_at")
    list_filter = ("primary_focus",)
    search_fields = ("user__username", "user__legacy_user_id", "primary_focus_text")
