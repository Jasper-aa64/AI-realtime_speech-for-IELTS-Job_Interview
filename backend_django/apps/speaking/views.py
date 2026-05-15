from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from .services import (
    SpeakingError,
    delete_attempt,
    detail,
    history,
    question_bank_sample,
    question_bank_summary,
    replay_queue,
    weak_items,
)


def require_user(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "authentication required"}, status=401)
    return None


@require_GET
def history_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    return JsonResponse(history(request.user))


@require_http_methods(["GET", "DELETE"])
def attempt_view(request, attempt_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    if request.method == "DELETE":
        try:
            return JsonResponse(delete_attempt(request.user, attempt_id))
        except SpeakingError as exc:
            return JsonResponse({"error": str(exc)}, status=404)
    try:
        return JsonResponse(detail(request.user, attempt_id))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=404)


@require_GET
def question_bank_summary_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    return JsonResponse(question_bank_summary())


@require_http_methods(["POST"])
def question_bank_sample_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    import json as json_module
    try:
        payload = json_module.loads(request.body or "{}")
    except json_module.JSONDecodeError:
        payload = {}
    p1_count = payload.get("p1_count", 5)
    if isinstance(p1_count, str):
        p1_count = int(p1_count) if p1_count.isdigit() else 5
    return JsonResponse(question_bank_sample(int(p1_count)))


@require_GET
def training_weak_items_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    limit = request.GET.get("limit", "50")
    try:
        limit = max(1, min(int(limit), 100))
    except (ValueError, TypeError):
        limit = 50
    return JsonResponse({"items": weak_items(request.user, limit)})


@require_GET
def training_replay_queue_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    limit = request.GET.get("limit", "10")
    try:
        limit = max(1, min(int(limit), 50))
    except (ValueError, TypeError):
        limit = 10
    return JsonResponse({"items": replay_queue(request.user, limit)})
