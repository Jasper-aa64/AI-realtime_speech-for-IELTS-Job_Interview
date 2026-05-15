import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .services import BillingError, recharge_wallet, release_reservation, reserve_usage, settle_usage, wallet_payload


def read_json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def require_user(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "authentication required"}, status=401)
    return None


def parse_float(payload: dict, field_name: str) -> float:
    try:
        return float(payload.get(field_name) or 0)
    except (TypeError, ValueError) as exc:
        raise BillingError(f"{field_name} must be numeric") from exc


def parse_int(payload: dict, field_name: str, default: int = 0) -> int:
    try:
        return int(payload.get(field_name) or default)
    except (TypeError, ValueError) as exc:
        raise BillingError(f"{field_name} must be an integer") from exc


@require_GET
def wallet(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    return JsonResponse(wallet_payload(request.user))


@csrf_exempt
@require_http_methods(["POST"])
def recharge(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    payload = read_json_body(request)
    try:
        result = recharge_wallet(request.user, parse_float(payload, "amount_rmb"))
    except BillingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(result)


@csrf_exempt
@require_http_methods(["POST"])
def reserve(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    payload = read_json_body(request)
    try:
        result = reserve_usage(
            request.user,
            str(payload.get("call_id") or ""),
            parse_int(payload, "reserved_u"),
            str(payload.get("snapshot_id") or "") or None,
            parse_int(payload, "ttl_seconds", 24 * 60 * 60),
        )
    except BillingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(result)


@csrf_exempt
@require_http_methods(["POST"])
def release(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    payload = read_json_body(request)
    try:
        result = release_reservation(request.user, str(payload.get("call_id") or ""))
    except BillingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(result)


@csrf_exempt
@require_http_methods(["POST"])
def settle(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    payload = read_json_body(request)
    try:
        result = settle_usage(request.user, str(payload.get("call_id") or ""), payload.get("usage"), str(payload.get("snapshot_id") or "") or None)
    except BillingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(result)
