import json
from functools import wraps

from django.db import OperationalError
from django.http import JsonResponse
from django.middleware.csrf import get_token

from . import services
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
                return JsonResponse({"error": "Session is busy; retry shortly", "code": "session_busy"}, status=409)
        return wrapped
    return decorate


def json_body(request):
    if len(request.body) > 256000:
        raise InterviewError("Request exceeds the supported limit")
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
    return services.history(request.user) if request.method == "GET" else services.create(request.user, json_body(request))


@api("GET")
def session_detail(request, session_id):
    return services.detail(request.user, session_id)


@api("POST")
def answer(request, session_id, turn_id):
    return services.answer(request.user, session_id, turn_id, json_body(request).get("answer"))


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
    return services.coach(request.user, session_id, json_body(request).get("ai_source", ""))
