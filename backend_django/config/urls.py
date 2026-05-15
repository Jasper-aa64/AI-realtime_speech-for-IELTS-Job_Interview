from django.contrib import admin
from django.urls import path

from apps.accounts import views as account_views
from apps.ai import views as ai_views
from apps.billing import views as billing_views
from apps.common.views import health
from apps.speaking import views as speaking_views
from apps.writing import views as writing_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/accounts/register/", account_views.register, name="account-register"),
    path("api/accounts/login/", account_views.login_view, name="account-login"),
    path("api/accounts/logout/", account_views.logout_view, name="account-logout"),
    path("api/accounts/me/", account_views.me, name="account-me"),
    path("api/ai/tasks/", ai_views.tasks, name="ai-tasks"),
    path("api/ai/tasks/<str:task_id>", ai_views.task_detail, name="ai-task-detail"),
    path("api/ai/tasks/<str:task_id>/cancel/", ai_views.task_cancel, name="ai-task-cancel"),
    path("api/history", speaking_views.history_view, name="speaking-history"),
    path("api/history/<str:attempt_id>", speaking_views.attempt_view, name="speaking-attempt"),
    path("api/billing/wallet/", billing_views.wallet, name="billing-wallet"),
    path("api/billing/recharge/", billing_views.recharge, name="billing-recharge"),
    path("api/billing/reservations/", billing_views.reserve, name="billing-reserve"),
    path("api/billing/reservations/release/", billing_views.release, name="billing-release"),
    path("api/billing/settle/", billing_views.settle, name="billing-settle"),
    path("api/writing/summary", writing_views.summary, name="writing-summary"),
    path("api/writing/reports", writing_views.reports, name="writing-reports"),
    path("api/writing/prompts", writing_views.prompts, name="writing-prompts"),
    path("api/writing/prompts/random", writing_views.random_prompt_view, name="writing-random-prompt"),
    path("api/writing/entries", writing_views.entries, name="writing-entries"),
    path("api/writing/entries/<str:entry_id>", writing_views.entry_detail, name="writing-entry-detail"),
    path("api/writing/entries/<str:entry_id>/score", writing_views.entry_score, name="writing-entry-score"),
    path("api/writing/entries/<str:entry_id>/score-task", writing_views.entry_score_task, name="writing-entry-score-task"),
]
