from django.http import FileResponse, JsonResponse, StreamingHttpResponse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.views.decorators.http import require_GET, require_http_methods

from .services import (
    SpeakingError,
    abort_attempt,
    complete_turn,
    delete_attempt,
    delete_expression_replacement,
    delete_language_takeaway,
    delete_p2_corpus,
    delete_writing_takeaway,
    detail,
    examiner_tts_status,
    expression_replacement_list,
    get_turn_audio_path,
    history,
    caiyun_translate_text,
    language_takeaway_library,
    latest_report,
    p3_fallback,
    p3_follow_up_fallback,
    p1_corpus_library,
    p2_bank_corpus_batch,
    p2_bank_corpus_payload,
    p2_corpus_library,
    p3_bank_corpus_batch,
    p3_bank_followup_list,
    question_bank_sample,
    question_bank_summary,
    regenerate_turn_feedback,
    regenerate_turn_transcript,
    replay_queue,
    save_p1_corpus,
    save_p2_bank_corpus,
    save_p2_corpus,
    save_p3_bank_followup_corpus,
    save_expression_replacement,
    save_language_takeaway,
    save_writing_takeaway,
    save_takeaway_review_state,
    score_attempt,
    start_attempt,
    stream_follow_up_sse_events,
    stable_tts_audio_path,
    tts_audio_path,
    tts_fallback,
    update_language_takeaway,
    update_writing_takeaway,
    upload_turn_audio,
    warm_fixed_examiner_tts,
    weak_items,
    writing_takeaway_library,
)
from .volcengine_asr import realtime_asr_status


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
    return JsonResponse(question_bank_summary(request.GET.get("scope")))


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
    return JsonResponse(question_bank_sample(int(p1_count), payload.get("scope")))


@require_http_methods(["GET", "POST"])
def p1_corpus_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    if request.method == "GET":
        return JsonResponse(p1_corpus_library(request.user, request.GET.get("scope")))
    try:
        return JsonResponse(save_p1_corpus(request.user, _json_payload(request)))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["GET", "POST"])
def p2_corpus_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    if request.method == "GET":
        return JsonResponse(p2_corpus_library(request.user, request.GET.get("scope")))
    try:
        return JsonResponse(save_p2_corpus(request.user, _json_payload(request)))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["DELETE"])
def p2_corpus_detail_view(request, entry_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(delete_p2_corpus(request.user, entry_id))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=404)


@require_http_methods(["POST"])
def p2_bank_corpus_batch_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        payload = _json_payload(request)
        return JsonResponse(p2_bank_corpus_batch(request.user, payload.get("question_ids")))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["POST"])
def p3_bank_corpus_batch_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        payload = _json_payload(request)
        return JsonResponse(p3_bank_corpus_batch(request.user, payload.get("question_ids")))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["GET", "POST", "PUT", "PATCH"])
def p2_bank_corpus_detail_view(request, question_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        if request.method == "GET":
            return JsonResponse(p2_bank_corpus_payload(request.user, question_id))
        return JsonResponse(save_p2_bank_corpus(request.user, question_id, _json_payload(request)))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["GET"])
def p3_bank_corpus_view(request, p2_question_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(p3_bank_followup_list(request.user, p2_question_id))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["POST", "PUT", "PATCH"])
def p3_bank_corpus_item_view(request, followup_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(save_p3_bank_followup_corpus(request.user, followup_id, _json_payload(request)))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["GET", "POST"])
def language_takeaway_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    if request.method == "GET":
        return JsonResponse(language_takeaway_library(request.user))
    try:
        return JsonResponse(save_language_takeaway(request.user, _json_payload(request)))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["DELETE", "PATCH", "POST", "PUT"])
def language_takeaway_detail_view(request, entry_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        if request.method in {"PATCH", "POST", "PUT"}:
            return JsonResponse(update_language_takeaway(request.user, entry_id, _json_payload(request)))
        return JsonResponse(delete_language_takeaway(request.user, entry_id))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=404 if "not found" in str(exc).lower() else 400)


@require_http_methods(["GET", "POST"])
def writing_takeaway_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    if request.method == "GET":
        return JsonResponse(writing_takeaway_library(request.user))
    try:
        return JsonResponse(save_writing_takeaway(request.user, _json_payload(request)))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["DELETE", "PATCH", "POST", "PUT"])
def writing_takeaway_detail_view(request, entry_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        if request.method in {"PATCH", "POST", "PUT"}:
            return JsonResponse(update_writing_takeaway(request.user, entry_id, _json_payload(request)))
        return JsonResponse(delete_writing_takeaway(request.user, entry_id))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=404 if "not found" in str(exc).lower() else 400)


@require_http_methods(["POST"])
def takeaway_review_state_view(request, kind: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(save_takeaway_review_state(request.user, kind, _json_payload(request)))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["GET"])
def expression_replacements_view(request, kind: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(expression_replacement_list(request.user, kind))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["PUT", "DELETE"])
def expression_replacement_detail_view(request, kind: str, item_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        if request.method == "DELETE":
            return JsonResponse(delete_expression_replacement(request.user, kind, item_id))
        return JsonResponse(save_expression_replacement(request.user, kind, item_id, _json_payload(request)))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["POST"])
def language_takeaway_translate_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(caiyun_translate_text(str(_json_payload(request).get("text") or "")))
    except SpeakingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


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
    audio_file = request.FILES.get('audio') or request.FILES.get('file')
    if not audio_file and request.body:
        content_type = request.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip()
        audio_file = SimpleUploadedFile("audio.webm", request.body, content_type=content_type)
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


@require_GET
def turn_examiner_tts_view(request, attempt_id: str, turn_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(examiner_tts_status(request.user, attempt_id, turn_id))
    except SpeakingError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg.lower() else 400
        return JsonResponse({"error": msg}, status=status)


@require_http_methods(["POST"])
def turn_complete_view(request, attempt_id: str, turn_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    import json as json_module
    try:
        payload = json_module.loads(request.body or "{}")
    except json_module.JSONDecodeError:
        payload = {}
    try:
        return JsonResponse(complete_turn(request.user, attempt_id, turn_id, payload))
    except SpeakingError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg.lower() else 400
        return JsonResponse({"error": msg}, status=status)


@require_GET
def turn_follow_up_stream_view(request, attempt_id: str, turn_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        response = StreamingHttpResponse(
            stream_follow_up_sse_events(request.user, attempt_id, turn_id),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
    except SpeakingError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg.lower() else 400
        return JsonResponse({"error": msg}, status=status)


@require_GET
def realtime_asr_status_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    return JsonResponse(realtime_asr_status())


@require_http_methods(["POST"])
def attempt_abort_view(request, attempt_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(abort_attempt(request.user, attempt_id))
    except SpeakingError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg.lower() else 400
        return JsonResponse({"error": msg}, status=status)


@require_http_methods(["POST"])
def attempt_score_view(request, attempt_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    import json as json_module
    try:
        payload = json_module.loads(request.body or "{}")
    except json_module.JSONDecodeError:
        payload = {}
    try:
        return JsonResponse(score_attempt(request.user, attempt_id, payload))
    except SpeakingError as exc:
        msg = str(exc)
        lower_msg = msg.lower()
        if msg == "ai_quota_exhausted":
            return JsonResponse({
                "error": "ai_quota_exhausted",
                "error_code": "ai_quota_exhausted",
                "contact": "18728445038",
            }, status=402)
        if "not found" in lower_msg:
            status = 404
        elif "ai analysis failed" in lower_msg or "ai report regeneration failed" in lower_msg:
            status = 503
        else:
            status = 400
        return JsonResponse({"error": msg}, status=status)


@require_http_methods(["POST"])
def turn_feedback_regenerate_view(request, attempt_id: str, turn_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        result = regenerate_turn_feedback(request.user, attempt_id, turn_id)
        return JsonResponse(result)
    except SpeakingError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg.lower() else 400
        return JsonResponse({"error": msg}, status=status)


@require_http_methods(["POST"])
def turn_transcript_regenerate_view(request, attempt_id: str, turn_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        result = regenerate_turn_transcript(request.user, attempt_id, turn_id)
        return JsonResponse(result)
    except SpeakingError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg.lower() else 400
        return JsonResponse({"error": msg}, status=status)


def _json_payload(request) -> dict:
    import json as json_module
    try:
        payload = json_module.loads(request.body or "{}")
    except json_module.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


@require_http_methods(["POST"])
def p3_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    payload = _json_payload(request)
    try:
        payload.setdefault("ai_source", getattr(request.user.profile, "report_ai_source", "") or "")
    except Exception:
        pass
    result = p3_fallback(payload)
    return JsonResponse(result)


@require_http_methods(["POST"])
def p3_follow_up_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    return JsonResponse(p3_follow_up_fallback(_json_payload(request)))


@require_http_methods(["POST"])
def tts_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    return JsonResponse(tts_fallback(_json_payload(request)))


@require_http_methods(["POST"])
def tts_warmup_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    return JsonResponse(warm_fixed_examiner_tts())


@require_GET
def tts_audio_view(request, role: str, filename: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    if request.GET.get("stable") == "1":
        path, content_type = stable_tts_audio_path(role, filename)
    else:
        path = tts_audio_path(role, filename)
        content_type = "audio/mpeg"
    if not path:
        return JsonResponse({"error": "Audio not available"}, status=404)
    return FileResponse(open(path, "rb"), content_type=content_type)


@require_GET
def latest_report_view(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    return JsonResponse(latest_report(request.user))
