import json
import time
from collections import defaultdict
from typing import Optional

from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_http_methods

from .models import UserProfile
from apps.billing.services import ensure_wallet


# Simple in-memory throttle for login/register/password operations
_throttle_store = defaultdict(list)
_THROTTLE_WINDOW = 300  # 5 minutes
_THROTTLE_LIMIT = 10  # max attempts per window


def _throttle_key(request, action: str) -> str:
    """Generate throttle key from IP and action."""
    ip = request.META.get("REMOTE_ADDR", "unknown")
    return f"{action}:{ip}"


def _check_throttle(request, action: str) -> Optional[str]:
    """Check if request should be throttled. Returns error message if throttled, None otherwise."""
    key = _throttle_key(request, action)
    now = time.time()
    # Clean old entries
    _throttle_store[key] = [ts for ts in _throttle_store[key] if now - ts < _THROTTLE_WINDOW]
    if len(_throttle_store[key]) >= _THROTTLE_LIMIT:
        return f"Too many {action} attempts. Please try again later."
    _throttle_store[key].append(now)
    return None


def error_response(message: str, errors: Optional[dict] = None, status: int = 400) -> JsonResponse:
    """Return structured error response."""
    payload = {"message": message}
    if errors:
        payload["errors"] = errors
    return JsonResponse(payload, status=status)


def user_payload(user) -> dict:
    profile, _created = UserProfile.objects.get_or_create(user=user)
    return {
        "id": user.pk,
        "username": user.get_username(),
        "display_name": user.display_name,
        "email": user.email,
        "phone_number": user.phone_number,
        "legacy_user_id": user.legacy_user_id,
        "profile": {
            "full_name": profile.full_name,
            "english_name": profile.english_name,
            "target_band": str(profile.target_band) if profile.target_band is not None else None,
            "timezone": profile.timezone,
        },
    }


def read_json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


@require_http_methods(["GET"])
def csrf_token(request):
    """Return CSRF token for client-side requests."""
    return JsonResponse({"csrfToken": get_token(request)})


@require_http_methods(["POST"])
def register(request):
    throttle_error = _check_throttle(request, "register")
    if throttle_error:
        return error_response(throttle_error, status=429)

    payload = read_json_body(request)
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    password_confirm = str(payload.get("password_confirm") or "")

    errors = {}
    if not username:
        errors["username"] = ["Username is required"]
    if not password:
        errors["password"] = ["Password is required"]
    if password and password != password_confirm:
        errors["password_confirm"] = ["Passwords do not match"]

    if errors:
        return error_response("Registration failed", errors=errors, status=400)

    user_model = get_user_model()
    if user_model.objects.filter(username=username).exists():
        return error_response("Registration failed", errors={"username": ["Username already exists"]}, status=409)

    legacy_user_id = str(payload.get("legacy_user_id") or "").strip() or None
    if legacy_user_id and user_model.objects.filter(legacy_user_id=legacy_user_id).exists():
        return error_response("Registration failed", errors={"legacy_user_id": ["Legacy user ID already exists"]}, status=409)

    # Validate password using Django validators
    try:
        validate_password(password, user=None)
    except ValidationError as e:
        return error_response("Registration failed", errors={"password": list(e.messages)}, status=400)

    try:
        user = user_model.objects.create_user(
            username=username,
            password=password,
            email=str(payload.get("email") or ""),
            display_name=str(payload.get("display_name") or username),
            legacy_user_id=legacy_user_id,
        )
    except IntegrityError:
        return error_response("Registration failed", errors={"username": ["User already exists"]}, status=409)

    UserProfile.objects.update_or_create(
        user=user,
        defaults={
            "full_name": str(payload.get("full_name") or "LiHua"),
            "english_name": str(payload.get("english_name") or "Jasper"),
        },
    )
    ensure_wallet(user)
    login(request, user)
    return JsonResponse({"user": user_payload(user)}, status=201)


@require_http_methods(["POST"])
def login_view(request):
    throttle_error = _check_throttle(request, "login")
    if throttle_error:
        return error_response(throttle_error, status=429)

    payload = read_json_body(request)
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")

    if not username or not password:
        return error_response("Login failed", errors={"username": ["Username and password are required"]}, status=400)

    user = authenticate(request, username=username, password=password)
    if user is None:
        return error_response("Login failed", errors={"username": ["Invalid username or password"]}, status=401)

    login(request, user)
    ensure_wallet(user)
    return JsonResponse({"user": user_payload(user)})


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return JsonResponse({"ok": True})


@require_http_methods(["GET", "PATCH"])
def me(request):
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False}, status=401)

    if request.method == "PATCH":
        payload = read_json_body(request)
        profile, _created = UserProfile.objects.get_or_create(user=request.user)

        errors = {}
        # Validate email format if provided
        email = payload.get("email")
        if email is not None:
            email_str = str(email).strip()
            if email_str and "@" not in email_str:
                errors["email"] = ["Invalid email format"]

        if errors:
            return error_response("Profile update failed", errors=errors, status=400)

        for field in ("display_name", "phone_number", "email"):
            if field in payload:
                setattr(request.user, field, str(payload.get(field) or ""))
        request.user.save(update_fields=["display_name", "phone_number", "email"])

        for field in ("full_name", "english_name", "timezone"):
            if field in payload:
                setattr(profile, field, str(payload.get(field) or ""))
        if "target_band" in payload:
            profile.target_band = payload.get("target_band") or None
        profile.save()

    return JsonResponse({"authenticated": True, "user": user_payload(request.user)})


@require_http_methods(["POST"])
def password_change(request):
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False}, status=401)

    throttle_error = _check_throttle(request, "password_change")
    if throttle_error:
        return error_response(throttle_error, status=429)

    payload = read_json_body(request)
    current_password = str(payload.get("current_password") or "")
    new_password = str(payload.get("new_password") or "")
    new_password_confirm = str(payload.get("new_password_confirm") or "")

    errors = {}
    if not current_password:
        errors["current_password"] = ["Current password is required"]
    if not new_password:
        errors["new_password"] = ["New password is required"]
    if new_password and new_password != new_password_confirm:
        errors["new_password_confirm"] = ["Passwords do not match"]

    if errors:
        return error_response("Password change failed", errors=errors, status=400)

    # Verify current password
    if not request.user.check_password(current_password):
        return error_response("Password change failed", errors={"current_password": ["Current password is incorrect"]}, status=400)

    # Validate new password
    try:
        validate_password(new_password, user=request.user)
    except ValidationError as e:
        return error_response("Password change failed", errors={"new_password": list(e.messages)}, status=400)

    request.user.set_password(new_password)
    request.user.save()
    update_session_auth_hash(request, request.user)
    return JsonResponse({"ok": True, "message": "Password changed successfully"})


@require_http_methods(["GET"])
def password_reset_availability(request):
    """Return whether password reset is available. Honest unavailable state if no email provider configured."""
    # Check if email backend is configured (not console backend)
    from django.conf import settings
    email_backend = getattr(settings, "EMAIL_BACKEND", "")
    is_available = email_backend and "console" not in email_backend.lower()

    return JsonResponse({
        "available": is_available,
        "message": "Password reset via email is not configured" if not is_available else "Password reset is available"
    })
