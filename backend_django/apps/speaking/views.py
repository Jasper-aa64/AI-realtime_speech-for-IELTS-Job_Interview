from django.http import FileResponse, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from .services import (
    SpeakingError,
    delete_attempt,
    detail,
    get_turn_audio_path,
    history,
    question_bank_sample,
    question_bank_summary,
    replay_queue,
    start_attempt,
    upload_turn_audio,
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


@require_http_methods(["POST"])
def attempt_start_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    import json as json_module
    try:
        payload = json_module.loads(request.body or "{}")
    except json_module.JSONDecodeError:
        payload = {}
    try:
        attempt = start_attempt(request.user, payload)
        return JsonResponse(attempt)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["POST"])
def turn_audio_upload_view(request, attempt_id: str, turn_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    if not request.FILES.get('audio'):
        audio_file = request.FILES.get('file')
    else:
        audio_file = request.FILES.get('audio')
    if not audio_file:
        return JsonResponse({"error": "No audio file provided"}, status=400)
    try:
        result = upload_turn_audio(request.user, attempt_id, turn_id, audio_file)
        return JsonResponse(result)
    except SpeakingError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            return JsonResponse({"error": msg}, status=404)
        return JsonResponse({"error": msg}, status=400)


@require_GET
def turn_audio_candidate_view(request, attempt_id: str, turn_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    audio_path = get_turn_audio_path(request.user, attempt_id, turn_id)
    if not audio_path or not audio_path.exists():
        return JsonResponse({"error": "Audio not found"}, status=404)
    return FileResponse(open(audio_path, 'rb'), content_type='application/octet-stream')
