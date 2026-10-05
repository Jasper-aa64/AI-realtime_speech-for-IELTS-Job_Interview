import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from . import ai_services
from .bank import BY_ID, CATEGORIES, QUESTIONS
from .models import InterviewSession, InterviewTurn
from .validation import InterviewError, count, custom_questions, resume_input, text

REPORT_LIMITATION = "仅根据文字回答生成，不含语音、发音或真实岗位能力认证。"


def questions(category=""):
    category = text(category, "category", 32)
    if category and category not in {item["id"] for item in CATEGORIES}:
        raise InterviewError("Unknown question category")
    return {"questions": [dict(q) for q in QUESTIONS if not category or q["category"] == category], "categories": CATEGORIES}


def _owned(user, public_id, *, lock=False):
    query = InterviewSession.objects.filter(user=user, public_id=public_id)
    if lock:
        query = query.select_for_update()
    session = query.first()
    if session is None:
        raise InterviewError("Interview session not found", code="not_found", status=404)
    return session


def _turn(session, public_id):
    turn = session.turns.filter(user=session.user, public_id=public_id).first()
    if turn is None:
        raise InterviewError("Interview turn not found", code="not_found", status=404)
    return turn


def _active(session):
    if session.status != "active":
        raise InterviewError("This session is no longer active", code="session_closed", status=409)


def _not_busy(session):
    if session.ai_busy_since and session.ai_busy_since > timezone.now() - timedelta(seconds=180):
        raise InterviewError("An AI request is still processing; retry shortly", code="ai_busy", status=409)
    # A crashed synchronous request expires; late output is rejected by token.
    if session.ai_busy_since:
        session.ai_busy_since = None
        session.ai_busy_kind = ""
        session.ai_busy_token = ""
        session.save(update_fields=["ai_busy_since", "ai_busy_kind", "ai_busy_token", "updated_at"])


def _pending(session):
    return session.turns.filter(status="pending").order_by("order").first()


def _touch(session):
    session.save(update_fields=["updated_at"])


def turn_payload(turn):
    return {"id": turn.public_id, "order": turn.order, "kind": turn.kind, "question_id": turn.question_id or None,
            "parent_turn_id": turn.parent.public_id if turn.parent_id else None,
            "prompt": turn.prompt, "answer": turn.answer, "status": turn.status, "source": turn.source,
            "category": turn.category, "difficulty": turn.difficulty}


def session_payload(session, turns=None, *, summary=False):
    turns = list(session.turns.all()) if turns is None else turns
    current = next((turn for turn in turns if turn.status == "pending"), None) if session.status == "active" else None
    report = session.report or None
    if summary and report:
        report = {key: report[key] for key in ("status", "completed_count", "skipped_count", "limitations") if key in report}
        report["ai_feedback_status"] = (session.report.get("ai_feedback") or {}).get("status")
    return {"id": session.public_id, "mode": session.mode, "title": session.title, "status": session.status,
            "current_turn_id": current.public_id if current else None, "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(), "report": report}


def detail(user, public_id):
    session = _owned(user, public_id)
    turns = list(session.turns.select_related("parent").all())
    payload = session_payload(session, turns)
    current = next((turn for turn in turns if turn.public_id == payload["current_turn_id"]), None)
    return {"session": payload, "turns": [turn_payload(turn) for turn in turns],
            "current_turn": turn_payload(current) if current else None}


def history(user):
    sessions = InterviewSession.objects.filter(user=user).prefetch_related("turns")[:100]
    return {"sessions": [session_payload(session, summary=True) for session in sessions]}


@transaction.atomic
def create(user, payload):
    mode = text(payload.get("mode", "general"), "mode", 16)
    if mode not in {"general", "custom"}:
        raise InterviewError("mode must be general or custom")
    title = text(payload.get("title"), "title", 160) or ("题库面试练习" if mode == "general" else "定制面试")
    if mode == "custom":
        selected = custom_questions(payload.get("questions"))
    else:
        ids = payload.get("question_ids")
        if ids is not None:
            if not isinstance(ids, list) or not 1 <= len(ids) <= 10 or any(not isinstance(q, str) for q in ids):
                raise InterviewError("Provide between 1 and 10 question IDs")
            if len(set(ids)) != len(ids) or any(q not in BY_ID for q in ids):
                raise InterviewError("Question IDs must be known and unique")
            selected = [BY_ID[q] for q in ids]
        else:
            bank = questions(payload.get("category", ""))["questions"]
            amount = count(payload.get("count"), default=min(5, len(bank)))
            if amount > len(bank):
                raise InterviewError("Requested count exceeds available questions in this category")
            # Stable curriculum ordering makes reloads/replays reproducible.
            selected = bank[:amount]
    session = InterviewSession.objects.create(user=user, mode=mode, title=title)
    InterviewTurn.objects.bulk_create([
        InterviewTurn(user=user, session=session, order=index, question_id=q.get("id", ""), prompt=q["prompt"],
                      category=q["category"], difficulty=q["difficulty"], source=q["source"])
        for index, q in enumerate(selected, 1)
    ])
    return detail(user, session.public_id)


@transaction.atomic
def answer(user, session_id, turn_id, value, *, skip=False):
    session = _owned(user, session_id, lock=True)
    turn = _turn(session, turn_id)
    value = "" if skip else text(value, "answer", 6000, required=True)
    expected = "skipped" if skip else "completed"
    if turn.status == expected and turn.answer == value:
        return detail(user, session_id)
    _active(session)
    _not_busy(session)
    current = _pending(session)
    if current is None or current.pk != turn.pk or turn.status != "pending":
        raise InterviewError("This turn is no longer current", code="stale_turn", status=409)
    turn.answer = value
    turn.status = expected
    turn.save(update_fields=["answer", "status", "updated_at"])
    _touch(session)
    return detail(user, session_id)


def _report(session):
    turns = list(session.turns.all())
    return {"status": "ready", "title": session.title, "limitations": REPORT_LIMITATION,
            "answer_mode": "text", "completed_count": sum(t.status == "completed" for t in turns),
            "skipped_count": sum(t.status == "skipped" for t in turns),
            "transcript": [turn_payload(t) for t in turns], "generated_at": timezone.now().isoformat()}


@transaction.atomic
def finish(user, public_id, *, abort=False):
    session = _owned(user, public_id, lock=True)
    final = "aborted" if abort else "completed"
    if session.status == final:
        return detail(user, public_id)
    _active(session)
    _not_busy(session)
    session.turns.filter(status="pending").update(status="skipped", updated_at=timezone.now())
    session.status = final
    if not abort:
        session.report = _report(session)
    session.save(update_fields=["status", "report", "updated_at"])
    return detail(user, public_id)


def generate_custom(user, payload, upload=None):
    resume = resume_input(payload.get("resume_text", ""), upload)
    job = text(payload.get("job_description"), "job_description", 12000, required=True)
    amount = count(payload.get("count"), default=5)
    result = ai_services.run_generation(user, "custom_questions", {"resume_text": resume, "job_description": job, "count": amount},
                                        ai_source=payload.get("ai_source", ""))
    return {"questions": result["questions"], "generation": {key: result[key] for key in ("provider", "model", "ai_source", "task_id")}}


def _lease(user, public_id, kind, parent_id=""):
    with transaction.atomic():
        session = _owned(user, public_id, lock=True)
        _not_busy(session)
        if kind == "follow_up":
            _active(session)
            parent = _turn(session, parent_id)
            if parent.kind != "main" or parent.status != "completed":
                raise InterviewError("Follow-up requires an answered main question", code="invalid_follow_up", status=409)
            child = session.turns.filter(parent=parent).first()
            if child:
                return None, None
            if session.turns.filter(order__gt=parent.order).exclude(status="pending").exists():
                raise InterviewError("Later answers have already advanced the interview", code="stale_turn", status=409)
            inputs = {"prompt": parent.prompt, "answer": parent.answer, "category": parent.category}
        else:
            if session.status != "completed":
                raise InterviewError("Finish the interview before requesting coaching", code="session_not_completed", status=409)
            completed = list(session.turns.filter(status="completed"))
            if not completed:
                raise InterviewError("At least one written answer is required for AI coaching")
            if (session.report or {}).get("ai_feedback", {}).get("status") == "ready":
                return None, None
            inputs = {"transcript": [{"question": t.prompt, "answer": t.answer[:1500]} for t in completed],
                      "limitations": REPORT_LIMITATION, "answer_excerpts": True}
        token = uuid.uuid4().hex
        session.ai_busy_since = timezone.now()
        session.ai_busy_kind = kind
        session.ai_busy_token = token
        session.save(update_fields=["ai_busy_since", "ai_busy_kind", "ai_busy_token", "updated_at"])
        return token, inputs


def _clear_lease(user, public_id, token):
    InterviewSession.objects.filter(user=user, public_id=public_id, ai_busy_token=token).update(
        ai_busy_since=None, ai_busy_kind="", ai_busy_token="")


def follow_up(user, public_id, parent_id, ai_source=""):
    token, inputs = _lease(user, public_id, "follow_up", parent_id)
    if token is None:
        return detail(user, public_id)
    try:
        result = ai_services.run_generation(user, "follow_up", inputs, ai_source=ai_source, related_id=public_id)
        with transaction.atomic():
            session = _owned(user, public_id, lock=True)
            _active(session)
            if session.ai_busy_token != token:
                raise InterviewError("This generation belongs to an older request", code="stale_generation", status=409)
            parent = _turn(session, parent_id)
            for turn in session.turns.filter(order__gt=parent.order).order_by("-order"):
                turn.order += 1
                turn.save(update_fields=["order", "updated_at"])
            InterviewTurn.objects.create(user=user, session=session, parent=parent, order=parent.order + 1,
                                         kind="follow_up", prompt=result["prompt"], category=parent.category,
                                         difficulty=parent.difficulty, source="ai_generated",
                                         metadata={key: result[key] for key in ("provider", "model", "task_id")})
            _touch(session)
    finally:
        _clear_lease(user, public_id, token)
    return detail(user, public_id)


def coach(user, public_id, ai_source=""):
    token, inputs = _lease(user, public_id, "report")
    if token is None:
        return detail(user, public_id)
    try:
        result = ai_services.run_generation(user, "report", inputs, ai_source=ai_source, related_id=public_id)
        with transaction.atomic():
            session = _owned(user, public_id, lock=True)
            if session.ai_busy_token != token or session.status != "completed":
                raise InterviewError("This generation belongs to an older request", code="stale_generation", status=409)
            session.report = {**session.report, "ai_feedback": {"status": "ready", **result, "limitations": REPORT_LIMITATION}}
            session.save(update_fields=["report", "updated_at"])
    except InterviewError as exc:
        with transaction.atomic():
            session = _owned(user, public_id, lock=True)
            if session.ai_busy_token == token:
                session.report = {**session.report, "ai_feedback": {"status": "failed", "error": str(exc),
                                  "code": exc.code, "limitations": REPORT_LIMITATION}}
                session.save(update_fields=["report", "updated_at"])
        raise
    finally:
        _clear_lease(user, public_id, token)
    return detail(user, public_id)
