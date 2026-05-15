import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .orchestration import AIOrchestrationError, cancel_owned_ai_task, create_billable_ai_task
from .services import AITaskConflictError, AITaskError, create_ai_task, get_ai_task, task_payload


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


@csrf_exempt
@require_http_methods(["POST"])
def tasks(request):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    payload = read_json_body(request)
    try:
        if "reserved_u" in payload:
            task, created = create_billable_ai_task(
                user=request.user,
                task_type=str(payload.get("task_type") or ""),
                reserved_u=payload.get("reserved_u"),
                idempotency_key=str(payload.get("idempotency_key") or ""),
                provider=str(payload.get("provider") or "codex"),
                model=str(payload.get("model") or ""),
                related_type=str(payload.get("related_type") or ""),
                related_id=str(payload.get("related_id") or ""),
                call_id=str(payload.get("call_id") or ""),
                prompt_version=str(payload.get("prompt_version") or ""),
                request_payload=payload.get("request_payload") if isinstance(payload.get("request_payload"), dict) else {},
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                max_attempts=int(payload.get("max_attempts") or 3),
            )
        else:
            task, created = create_ai_task(
                user=request.user,
                task_type=str(payload.get("task_type") or ""),
                idempotency_key=str(payload.get("idempotency_key") or ""),
                provider=str(payload.get("provider") or "codex"),
                model=str(payload.get("model") or ""),
                related_type=str(payload.get("related_type") or ""),
                related_id=str(payload.get("related_id") or ""),
                call_id=str(payload.get("call_id") or ""),
                prompt_version=str(payload.get("prompt_version") or ""),
                request_payload=payload.get("request_payload") if isinstance(payload.get("request_payload"), dict) else {},
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                max_attempts=int(payload.get("max_attempts") or 3),
            )
    except (AIOrchestrationError, AITaskError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"created": created, "task": task_payload(task)}, status=201 if created else 200)


@require_GET
def task_detail(request, task_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    try:
        return JsonResponse(task_payload(get_ai_task(request.user, task_id)))
    except AITaskError as exc:
        return JsonResponse({"error": str(exc)}, status=404)


@csrf_exempt
@require_http_methods(["POST"])
def task_cancel(request, task_id: str):
    auth_error = require_user(request)
    if auth_error:
        return auth_error
    payload = read_json_body(request)
    try:
        task = cancel_owned_ai_task(
            request.user,
            task_id,
            reason=str(payload.get("reason") or ""),
            error_code=str(payload.get("error_code") or "cancelled"),
        )
    except AITaskConflictError as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    except AITaskError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except AIOrchestrationError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(task_payload(task))
