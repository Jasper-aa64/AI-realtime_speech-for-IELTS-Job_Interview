import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .dictionary_services import is_single_dictionary_word, lookup_word
from .models import WritingFrameTemplate
from .spelling_services import add_manual_spelling_word, complete_spelling_daily_batch, delete_spelling_word, record_spelling_attempt, spelling_drill_library, spelling_word_for_lookup, update_spelling_word
from .services import WritingError, agent_find_writing_prompts, cambridge_catalog, clone_entry_for_revision, create_score_task, delete_entry, delete_entry_report, entry_for_prompt, get_entry, list_prompts, prompt_categories, prompt_patterns, random_prompt, save_entry, score_entry, writing_reports, writing_summary


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


def _frame_payload(row: WritingFrameTemplate) -> dict:
    return {
        "frame_key": row.frame_key,
        "template_text": row.template_text,
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


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


@csrf_exempt
@require_http_methods(["GET", "PUT"])
def writing_frames(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    if request.method == "GET":
        rows = WritingFrameTemplate.objects.filter(user=request.user).order_by("frame_key")
        return JsonResponse({"items": [_frame_payload(row) for row in rows]})
    payload = read_json_body(request)
    frame_key = str(payload.get("frame_key") or "").strip()
    template_text = str(payload.get("template_text") or "")
    if not frame_key:
        return JsonResponse({"error": "frame_key required", "message": "frame_key required"}, status=400)
    if len(frame_key) > 120:
        return JsonResponse({"error": "frame_key too long", "message": "frame_key too long"}, status=400)
    row, _created = WritingFrameTemplate.objects.update_or_create(
        user=request.user,
        frame_key=frame_key,
        defaults={"template_text": template_text},
    )
    return JsonResponse(_frame_payload(row))


@csrf_exempt
@require_http_methods(["DELETE"])
def writing_frame_detail(request, frame_key: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    WritingFrameTemplate.objects.filter(user=request.user, frame_key=str(frame_key or "").strip()).delete()
    return JsonResponse({"ok": True, "frame_key": frame_key})


@require_GET
def spelling_words(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(spelling_drill_library(request.user, scope=request.GET.get("scope") or "due"))
    except WritingError as exc:
        return writing_error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def spelling_word_add(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    body = read_json_body(request)
    try:
        return JsonResponse(add_manual_spelling_word(
            request.user,
            word=body.get("word") or body.get("text") or "",
            chinese_gloss=body.get("chinese_gloss") or body.get("gloss") or "",
            replace_existing_gloss=body.get("replace_existing_gloss") is True,
        ))
    except WritingError as exc:
        return writing_error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def spelling_daily_batch_complete(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(complete_spelling_daily_batch(request.user))
    except WritingError as exc:
        return writing_error(exc)


@require_GET
def dictionary_lookup(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    word = (request.GET.get("word") or request.GET.get("text") or "").strip()
    if not is_single_dictionary_word(word):
        return JsonResponse({"ok": True, "found": False, "entry": None, "word": word})
    entry = lookup_word(word)
    return JsonResponse({
        "ok": True,
        "found": bool(entry),
        "entry": entry,
        "word": word,
        "spelling_word": spelling_word_for_lookup(request.user, word),
    })


@csrf_exempt
@require_http_methods(["POST"])
def spelling_word_attempt(request, word_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(record_spelling_attempt(request.user, word_id, read_json_body(request).get("typed")))
    except WritingError as exc:
        return writing_error(exc, status=404 if "not found" in str(exc).lower() else 400)


@csrf_exempt
@require_http_methods(["PATCH", "DELETE"])
def spelling_word_detail(request, word_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        if request.method == "PATCH":
            return JsonResponse(update_spelling_word(request.user, word_id, read_json_body(request)))
        return JsonResponse(delete_spelling_word(request.user, word_id))
    except WritingError as exc:
        return writing_error(exc, status=404 if "not found" in str(exc).lower() else 400)


@require_GET
def prompts(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        task_type = request.GET.get("task_type")
        return JsonResponse({
            "items": list_prompts(task_type, request.GET.get("category"), request.user, request.GET.get("prompt_pattern")),
            "categories": prompt_categories(task_type),
            "prompt_patterns": prompt_patterns(task_type, request.GET.get("category")),
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
            str(payload.get("prompt_pattern") or "").strip() or None,
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
def entry_for_prompt_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(entry_for_prompt(
            request.user,
            task_type=request.GET.get("task_type", ""),
            prompt_id=request.GET.get("prompt_id", ""),
            prompt_text=request.GET.get("prompt", ""),
        ))
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


@require_http_methods(["DELETE"])
def entry_report(request, entry_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(delete_entry_report(request.user, entry_id))
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
