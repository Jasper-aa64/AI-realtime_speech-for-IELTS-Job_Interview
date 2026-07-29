from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class CustomUser(AbstractUser):
    legacy_user_id = models.CharField(max_length=120, null=True, blank=True, unique=True)
    display_name = models.CharField(max_length=120, blank=True)
    phone_number = models.CharField(max_length=32, blank=True, db_index=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    wechat_openid = models.CharField(max_length=128, blank=True, db_index=True)
    wechat_unionid = models.CharField(max_length=128, blank=True, db_index=True)

    def mark_phone_verified(self) -> None:
        self.phone_verified_at = timezone.now()

    def __str__(self) -> str:
        return self.display_name or self.username or str(self.pk)


class UserProfile(models.Model):
    REPORT_AI_SOURCE_GPT = "gpt"
    REPORT_AI_SOURCE_CLAUDE = "claude"
    REPORT_AI_SOURCE_CLAUDE_HAIKU = "claude_haiku"
    REPORT_AI_SOURCE_CLAUDE_CLI = "claude_cli"
    REPORT_AI_SOURCE_CLAUDE_CLI_HAIKU = "claude_cli_haiku"
    REPORT_AI_SOURCE_CODEX_CLI = "codex_cli"
    REPORT_AI_SOURCE_GPT_56_TERRA = "gpt-5.6-terra"
    REPORT_AI_SOURCE_GPT_56_LUNA = "gpt-5.6-luna"
    REPORT_AI_SOURCE_GPT_56_SOL = "gpt-5.6-sol"
    REPORT_AI_SOURCE_CHOICES = [
        (REPORT_AI_SOURCE_GPT, "gpt-5.4 mini"),
        (REPORT_AI_SOURCE_GPT_56_TERRA, "gpt-5.6-terra"),
        (REPORT_AI_SOURCE_GPT_56_LUNA, "gpt-5.6-luna"),
        (REPORT_AI_SOURCE_GPT_56_SOL, "gpt-5.6-sol"),
        (REPORT_AI_SOURCE_CLAUDE, "Claude Sonnet"),
        (REPORT_AI_SOURCE_CLAUDE_HAIKU, "Claude Haiku"),
        (REPORT_AI_SOURCE_CLAUDE_CLI, "Claude CLI (Sonnet)"),
        (REPORT_AI_SOURCE_CLAUDE_CLI_HAIKU, "Claude CLI (Haiku)"),
        (REPORT_AI_SOURCE_CODEX_CLI, "Codex CLI (本机)"),
    ]

    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=120, blank=True, default="LiHua")
    english_name = models.CharField(max_length=120, blank=True, default="Jasper")
    target_band = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    timezone = models.CharField(max_length=64, default="Asia/Shanghai")
    report_ai_source = models.CharField(
        max_length=32,
        choices=REPORT_AI_SOURCE_CHOICES,
        default=REPORT_AI_SOURCE_GPT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user} profile"
