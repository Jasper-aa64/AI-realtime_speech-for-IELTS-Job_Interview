import json

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import UserProfile
from apps.billing.services import ensure_wallet


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


@csrf_exempt
@require_http_methods(["POST"])
def register(request):
    payload = read_json_body(request)
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not username or not password:
        return JsonResponse({"error": "username and password are required"}, status=400)
    user_model = get_user_model()
    if user_model.objects.filter(username=username).exists():
        return JsonResponse({"error": "username already exists"}, status=409)
    legacy_user_id = str(payload.get("legacy_user_id") or "").strip() or None
    if legacy_user_id and user_model.objects.filter(legacy_user_id=legacy_user_id).exists():
        return JsonResponse({"error": "legacy_user_id already exists"}, status=409)
    try:
        user = user_model.objects.create_user(
            username=username,
            password=password,
            email=str(payload.get("email") or ""),
            display_name=str(payload.get("display_name") or username),
            legacy_user_id=legacy_user_id,
        )
    except IntegrityError:
        return JsonResponse({"error": "user already exists"}, status=409)
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


@csrf_exempt
@require_http_methods(["POST"])
def login_view(request):
    payload = read_json_body(request)
    user = authenticate(request, username=str(payload.get("username") or ""), password=str(payload.get("password") or ""))
    if user is None:
        return JsonResponse({"error": "invalid username or password"}, status=401)
    login(request, user)
    ensure_wallet(user)
    return JsonResponse({"user": user_payload(user)})


@csrf_exempt
@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
def me(request):
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False}, status=401)
    if request.method == "PATCH":
        payload = read_json_body(request)
        profile, _created = UserProfile.objects.get_or_create(user=request.user)
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
