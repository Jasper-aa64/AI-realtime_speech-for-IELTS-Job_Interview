"""Per-call AI metering: every model call made while serving a signed-in user is charged to that user's wallet.

Most AI work already settles through billable AI tasks (speaking reports, writing scoring, interview generation). The
rest - realtime follow-ups, coaching, band-7 rewrites, plan generation - used to be free. Instead of threading the
user through every helper, the request's user is bound to a context variable (AIMeteringMiddleware) and the low-level
call sites (local Codex / Claude CLI, the HTTP provider) report their usage here. Code that settles through a billable
task wraps itself in `suspended()` so nothing is charged twice. Background workers never see a request user, so they
are not metered here either.
"""

import contextvars
import logging
import uuid
from contextlib import contextmanager

from django.db import transaction

from .services import BillingError, settle_usage

logger = logging.getLogger(__name__)

_user = contextvars.ContextVar("ai_metering_user", default=None)
_suspended = contextvars.ContextVar("ai_metering_suspended", default=False)


def bind(user):
    """Charge AI calls on this thread / generator to `user`; returns a token for unbind()."""
    return _user.set(user if getattr(user, "is_authenticated", False) else None)


def unbind(token):
    try:
        _user.reset(token)
    except ValueError:  # reset from another context (a generator closed elsewhere): just clear it
        _user.set(None)


@contextmanager
def billed_to(user):
    token = bind(user)
    try:
        yield
    finally:
        unbind(token)


@contextmanager
def suspended():
    """For code that settles its own usage through a billable AI task."""
    token = _suspended.set(True)
    try:
        yield
    finally:
        _suspended.reset(token)


def charge(call_id, usage, *, provider, model, purpose=""):
    """Settles one call's usage at the current price snapshot. Never raises: a failed charge is logged, not fatal."""
    user = _user.get()
    if user is None or _suspended.get() or not usage:
        return None
    # Each call is charged once, even when a caller reuses a call id for retries.
    metered_id = f"meter:{str(call_id or 'ai')[:110]}:{uuid.uuid4().hex[:12]}"
    try:
        with transaction.atomic():
            return settle_usage(user, metered_id, usage, provider=provider, model=model or provider,
                                metadata={"source": "metered_ai_call", "purpose": purpose or str(call_id or "")[:120]})
    except BillingError as exc:
        logger.warning("AI call %s not charged for user %s: %s", call_id, getattr(user, "pk", None), exc)
    except Exception:  # noqa: BLE001 - metering must never break the feature that made the call
        logger.exception("AI call %s metering failed", call_id)
    return None


class AIMeteringMiddleware:
    """Binds the signed-in user for the request (after AuthenticationMiddleware)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = bind(getattr(request, "user", None))
        try:
            return self.get_response(request)
        finally:
            unbind(token)
