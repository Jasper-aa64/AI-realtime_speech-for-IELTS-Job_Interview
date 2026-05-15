from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from .services import SpeakingError, delete_attempt, detail, history


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
