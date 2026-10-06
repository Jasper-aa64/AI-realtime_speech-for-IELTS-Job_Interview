import json
from functools import wraps

from django.db import OperationalError
from django.http import JsonResponse
from django.middleware.csrf import get_token

from . import assistant, corpus, engine, services
from .models import InterviewSession
from .validation import InterviewError


def api(*methods):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({"error": "authentication required", "code": "authentication_required"}, status=401)
            if request.method not in methods:
                response = JsonResponse({"error": "method not allowed", "code": "method_not_allowed"}, status=405)
                response["Allow"] = ", ".join(methods)
                return response
            try:
                return JsonResponse(view(request, *args, **kwargs))
            except InterviewError as exc:
                return JsonResponse({"error": str(exc), "code": exc.code}, status=exc.status)
            except OperationalError:
                return JsonResponse({"error": "面试正忙，请稍后重试。", "code": "session_busy"}, status=409)
        return wrapped
    return decorate


def json_body(request):
    if len(request.body) > 256000:
        raise InterviewError("内容超出长度限制。")
    try:
        value = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise InterviewError("Provide a valid JSON object") from None
    if not isinstance(value, dict):
        raise InterviewError("Provide a valid JSON object")
    return value


@api("GET")
def questions(request):
    get_token(request)
    return services.questions(request.GET.get("category", ""))


@api("POST")
def custom_questions(request):
    payload = json_body(request) if request.content_type == "application/json" else request.POST.dict()
    return services.generate_custom(request.user, payload, request.FILES.get("resume_file"))


@api("GET", "POST")
def sessions(request):
    if request.method == "GET":
        return services.history(request.user)
    payload = json_body(request)
    return engine.create(request.user, payload) if "part" in payload else services.create(request.user, payload)


@api("GET")
def session_detail(request, session_id):
    return services.detail(request.user, session_id)


def _studio(request, session_id):
    return InterviewSession.objects.filter(user=request.user, public_id=session_id, mode="studio").exists()


@api("POST")
def answer(request, session_id, turn_id):
    payload = json_body(request)
    if _studio(request, session_id):
        return engine.answer(request.user, session_id, turn_id, payload.get("answer"),
                             answer_source=payload.get("answer_source", "typed"), ai_source=payload.get("ai_source", ""))
    return services.answer(request.user, session_id, turn_id, payload.get("answer"))


@api("POST")
def audio(request, session_id, turn_id):
    return engine.upload_audio(request.user, session_id, turn_id, request.FILES.get("audio"))


@api("POST")
def save_corpus(request, session_id, turn_id):
    return engine.save_to_corpus(request.user, session_id, turn_id)


@api("POST")
def skip(request, session_id, turn_id):
    return services.answer(request.user, session_id, turn_id, "", skip=True)


@api("POST")
def follow_up(request, session_id, turn_id):
    return services.follow_up(request.user, session_id, turn_id, json_body(request).get("ai_source", ""))


@api("POST")
def finish(request, session_id):
    return services.finish(request.user, session_id)


@api("POST")
def abort(request, session_id):
    return services.finish(request.user, session_id, abort=True)


@api("POST")
def report(request, session_id):
    ai_source = json_body(request).get("ai_source", "")
    if _studio(request, session_id):
        return engine.score(request.user, session_id, ai_source)
    return services.coach(request.user, session_id, ai_source)


def form_or_json(request):
    return json_body(request) if request.content_type == "application/json" else request.POST.dict()


@api("GET")
def profile(request):
    get_token(request)
    return {"profile": corpus.profile_payload(corpus.profile_for(request.user))}


@api("POST")
def profile_resume(request):
    return corpus.import_resume(request.user, form_or_json(request), request.FILES.get("resume_file"))


@api("POST")
def profile_jd(request):
    return corpus.import_jd(request.user, json_body(request))


@api("POST")
def assistant_chat(request):
    return assistant.send(request.user, json_body(request))


@api("GET")
def assistant_threads(request):
    return assistant.threads(request.user)


@api("GET", "PATCH", "DELETE")
def assistant_thread(request, thread_id):
    if request.method == "PATCH":
        return assistant.rename(request.user, thread_id, json_body(request))
    if request.method == "DELETE":
        return assistant.delete(request.user, thread_id)
    return assistant.thread_detail(request.user, thread_id)


@api("POST")
def assistant_undo(request, message_id):
    return assistant.undo(request.user, message_id)


@api("POST")
def profile_resume_commit(request):
    return corpus.commit_resume(request.user, json_body(request))


@api("POST")
def profile_jd_commit(request):
    return corpus.commit_jd(request.user, json_body(request))


@api("GET", "POST")
def corpus_entries(request):
    if request.method == "GET":
        get_token(request)
        return corpus.corpus_listing(request.user, request.GET.get("kind", ""))
    return corpus.create_entry(request.user, json_body(request))


@api("PATCH", "DELETE")
def corpus_entry(request, entry_id):
    if request.method == "DELETE":
        return corpus.delete_entry(request.user, entry_id)
    return corpus.update_entry(request.user, entry_id, json_body(request))


@api("POST")
def corpus_draft(request, entry_id):
    return corpus.generate_draft(request.user, entry_id, json_body(request).get("ai_source", ""))
