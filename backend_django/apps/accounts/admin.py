from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, UserProfile


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("IELTS profile", {"fields": ("legacy_user_id", "display_name", "phone_number", "phone_verified_at", "wechat_openid", "wechat_unionid")}),
    )
    list_display = ("username", "legacy_user_id", "display_name", "phone_number", "is_staff", "is_active")
    search_fields = ("username", "legacy_user_id", "email", "display_name", "phone_number", "wechat_unionid")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "english_name", "target_band", "timezone")
    search_fields = ("user__username", "full_name", "english_name")
