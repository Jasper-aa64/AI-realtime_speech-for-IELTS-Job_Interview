import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .services import WritingError, agent_find_writing_prompts, cambridge_catalog, clone_entry_for_revision, create_score_task, delete_entry, get_entry, list_prompts, prompt_categories, random_prompt, save_entry, score_entry, writing_reports, writing_summary


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
    payload = {"error": str(exc), "message": str(exc)}
    extra = getattr(exc, "payload", None)
    if isinstance(extra, dict):
        payload.update(extra)
    return JsonResponse(payload, status=status)


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
            "items": list_prompts(task_type, request.GET.get("category"), request.user),
            "categories": prompt_categories(task_type),
            "catalog": cambridge_catalog(task_type),
        })
    except WritingError as exc:
        return writing_error(exc)


@require_GET
def agent_prompt_search(request):
    query = str(request.GET.get("q") or request.GET.get("query") or "").strip()
    if not query:
        return JsonResponse({"error": "query required", "message": "query required"}, status=400)
    try:
        limit = int(request.GET.get("limit") or 8)
    except (TypeError, ValueError):
        limit = 8
    try:
        return JsonResponse(agent_find_writing_prompts(
            query,
            request,
            task_type=request.GET.get("task_type"),
            limit=limit,
        ))
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


@require_http_methods(["GET", "DELETE"])
def entry_detail(request, entry_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    if request.method == "DELETE":
        try:
            return JsonResponse(delete_entry(request.user, entry_id))
        except WritingError as exc:
            return writing_error(exc, status=404 if "not found" in str(exc).lower() else 400)
    try:
        return JsonResponse(get_entry(request.user, entry_id))
    except WritingError as exc:
        return writing_error(exc, status=404 if "not found" in str(exc).lower() else 400)


@csrf_exempt
@require_http_methods(["POST"])
def entry_clone(request, entry_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(clone_entry_for_revision(request.user, entry_id), status=201)
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
