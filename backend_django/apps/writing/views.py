import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .services import WritingError, create_score_task, get_entry, list_prompts, prompt_categories, random_prompt, save_entry, score_entry, writing_reports, writing_summary


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


def writing_error(exc: WritingError, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": str(exc)}, status=status)


@require_GET
def summary(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(writing_summary(request.user, request.GET.get("month")))
    except WritingError as exc:
        return writing_error(exc)


@require_GET
def reports(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(writing_reports(request.user, request.GET))
    except WritingError as exc:
        return writing_error(exc)


@require_GET
def prompts(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        task_type = request.GET.get("task_type")
        return JsonResponse({
            "items": list_prompts(task_type, request.GET.get("category")),
            "categories": prompt_categories(task_type),
        })
    except WritingError as exc:
        return writing_error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def random_prompt_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    payload = read_json_body(request)
    try:
        return JsonResponse(random_prompt(
            request.user,
            str(payload.get("task_type") or "").strip() or None,
            str(payload.get("category") or "").strip() or None,
        ))
    except WritingError as exc:
        return writing_error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def entries(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(save_entry(request.user, read_json_body(request)))
    except WritingError as exc:
        return writing_error(exc)


@require_GET
def entry_detail(request, entry_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(get_entry(request.user, entry_id))
    except WritingError as exc:
        return writing_error(exc, status=404 if "not found" in str(exc).lower() else 400)


@csrf_exempt
@require_http_methods(["POST"])
def entry_score(request, entry_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(score_entry(request.user, entry_id, read_json_body(request)))
    except WritingError as exc:
        return writing_error(exc, status=404 if "not found" in str(exc).lower() else 400)


@csrf_exempt
@require_http_methods(["POST"])
def entry_score_task(request, entry_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        result = create_score_task(request.user, entry_id, read_json_body(request))
    except WritingError as exc:
        return writing_error(exc, status=404 if "not found" in str(exc).lower() else 400)
    return JsonResponse(result, status=201 if result.get("created") else 200)
