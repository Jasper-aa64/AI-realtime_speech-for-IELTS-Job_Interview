from django.contrib import admin

from .models import AITask


@admin.register(AITask)
class AITaskAdmin(admin.ModelAdmin):
    list_display = ("task_id", "task_type", "status", "progress_percent", "attempt_count", "provider", "model", "user", "created_at")
    list_filter = ("status", "provider", "task_type")
    search_fields = ("task_id", "idempotency_key", "call_id", "task_type", "related_type", "related_id", "user__username")
