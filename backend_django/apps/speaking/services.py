from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import threading
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.utils import DatabaseError
from django.utils import timezone

from apps.ai.http_provider import HttpApiProvider, HttpApiProviderConfig
from apps.ai.models import AITask
from apps.ai.services import create_ai_task, task_payload
from .ai_config import (
    SPEAKING_AI_CALL_MODE_HTTP,
    SPEAKING_AI_DEFAULT_HTTP_MODEL,
    _float_setting_or_env,
    _mode_allows_codex,
    _mode_allows_http,
    _mode_is_fallback_only,
    _setting_or_env,
    speaking_ai_call_mode,
    speaking_ai_http_model,
)
from .ai_runtime import (
    CODEX_REASONING_EFFORT,
    ClaudeCliQuotaError,
    run_claude_cli,
    run_codex,
)
from .audio_services import (
    MAX_AUDIO_BYTES,
    get_turn_audio_path,
    transcribe_turn_audio_with_server_asr,
    upload_turn_audio,
)
from .coaching_services import (
    _model_band7_tts_cache_key,
    build_overall_review,
    build_personalized_coaching,
    model_answer_constraints,
    overall_review_with_codex,
    target_band_label,
)
from .corpus_services import (
    CAIYUN_COMPAT_DEVICE_ID,
    CAIYUN_COMPAT_TOKEN,
    LOCAL_TAKEAWAY_PHRASE_TRANSLATIONS,
    LOCAL_TAKEAWAY_WORD_TRANSLATIONS,
    P1_INTRO_QUESTIONS,
    P2_CORPUS_CATEGORIES,
    QuestionBank,
    caiyun_translate_text,
    delete_expression_replacement,
    delete_language_takeaway,
    delete_p2_corpus,
    delete_writing_takeaway,
    get_question_bank,
    expression_replacement_list,
    language_takeaway_library,
    language_takeaway_payload,
    local_takeaway_translate_text,
    normalize_question_bank_scope,
    p1_corpus_for_turns,
    p1_corpus_library,
    p1_question_id,
    p1_topic_label,
    p2_bank_corpus_batch,
    p2_bank_corpus_payload,
    p2_bank_topic_for_question_id,
    p2_corpus_entry_payload,
    p2_corpus_extra,
    p2_corpus_for_selection,
    p2_corpus_library,
    p2_entry_id,
    p3_bank_corpus_batch,
    p3_bank_followup_id,
    p3_bank_followup_list,
    prepared_corpus_for_turns,
    question_bank_sample,
    question_bank_summary,
    save_p2_bank_corpus,
    save_p3_bank_followup_corpus,
    save_expression_replacement,
    save_language_takeaway,
    save_p1_corpus,
    save_p2_corpus,
    save_writing_takeaway,
    save_takeaway_review_state,
    takeaway_entry_id,
    update_language_takeaway,
    update_writing_takeaway,
    writing_takeaway_library,
)
from .exceptions import SpeakingError
from .models import SpeakingAttempt, SpeakingReport, SpeakingTrainingObservation, SpeakingTurn
from .p1_followup_services import (
    _fallback_p1_identity_follow_up,
    _extract_p1_identity_follow_up_output,
    _is_p1_work_study_turn,
    _p1_generic_follow_up_angle,
    _p1_identity_follow_up_prompt,
    _p1_identity_stream_prompt,
)
from .p3_services import (
    P3_FOCUS_OPTIONS,
    P3_MAIN_COUNT,
    P3_TYPE_TARGET_MOVES,
    _failed_p3_plan,
    _fallback_p3,
    _dynamic_p3_follow_up,
    _extract_single_follow_up_question,
    _normalize_p3_focus,
    _normalize_p3_intensity,
    _p3_follow_up_for_type,
    _p3_questions_from_ai_payload,
    _p3_questions_from_material,
    _p3_question_type_for_index,
    _p3_source_type,
    _quick_follow_up_prompt,
    _structured_p3_questions,
)
from .report_services import (
    delete_attempt,
    detail,
    history,
    history_item,
    latest_speaking_report_task,
    normalize_p1_report_turn_corpus_keys,
    replay_queue,
    report_is_valid,
    report_payload,
    speaking_task_summary_payload,
    weak_items,
)
from .runtime_utils import (
    _safe_float,
    _safe_int,
    _sanitize_audio_preprocessing_metrics,
    _sanitize_realtime_asr_metrics,
    _sse_payload,
)
from .runtime_payload_services import (
    _find_turn,
    _load_attempt_for_user,
    _runtime_attempt_payload,
    _spoken_markdown,
    _turn_payload,
    _turn_status,
)
from .scoring_services import (
    _criteria_feedback,
    _p1_question_only_answer,
    _word_count,
    attempt_part,
    band_cap,
    build_part_scores,
    build_turn_band7_fallback,
    calibrate_realistic_score,
    cap_off_topic_score,
    clamp_band,
    development_markers,
    generic_template_score,
    heuristic_score,
    infer_primary_focus,
    is_p1_name_intro_turn,
    is_p1_work_study_intro_turn,
    is_template_like_answer,
    p1_name_answer,
    part_focus_text,
    prompt_relevance,
    repeated_phrases_from_texts,
    rounded_overall,
    score_for_part,
    score_prompt_for_part,
    scoring_turns_have_answer_text,
    short_question,
    simple_grammar_ratio,
    target_band,
    transcript_word_count,
    turn_counts_for_scoring,
    turn_display_transcript,
    turn_habit_tags,
    turn_needs_ai_coaching,
)
from .tts_services import (
    cached_tts_url as _cached_tts_url,
    stable_tts_audio_path,
    tts_audio_path,
    tts_fallback,
    volcengine_tts,
)
from .text_utils import (
    acceptable_coaching_markdown,
    clean_band7_output,
    clean_coaching_markdown_text,
    clean_markdown_text,
    clean_report_text,
    concise_coaching_markdown,
    ensure_grammar_correction_bullet,
    extract_codex_json_events,
    extract_json_object,
    extract_json_object_with_keys,
    infer_grammar_corrections,
    normalize_coaching_markdown,
    plain_spoken_text,
    spoken_markdown,
)
from .turn_building_services import (
    FIXED_EXAMINER_TTS_ITEMS,
    _cue_examiner_text,
    _cue_to_text,
    _is_p1_work_study_identity_question,
    _normalize_question_text,
    _p1_topic_practice_counts,
    _p3_question_practice_counts,
    _question_practice_counts,
    _select_least_practiced_items,
    _select_p3_followups,
    _timers_for_part,
    _weighted_topic_order,
)


# --- Codex Integration ---

# ── Claude CLI runner ─────────────────────────────────────────────────────────

# --- Overall Review ---








# --- Model Answer Helpers ---








# --- Attempt Start ---

P1_TURN_COUNT = 10
# A P1 session mirrors the real exam: the examiner covers a few separate topic
# "frames", asking a handful of questions on each — never one giant topic, and
# never a single topic for the whole part. So we draw several DISTINCT topics and
# a capped slice of each, instead of dumping a whole 18-question bank topic.
P1_TOPICS_PER_SESSION = 3      # at least this many distinct topics per session
P1_QUESTIONS_PER_TOPIC = 4     # typical questions drawn from one topic
P1_QUESTIONS_PER_TOPIC_MAX = 6 # hard cap per topic (a topic never exceeds this)
STREAM_PENDING_FOLLOW_UP_PLACEHOLDER = "Generating follow-up question..."
P1_FOLLOW_UP_HTTP_TIMEOUT = 8
P1_FOLLOW_UP_CODEX_TIMEOUT = 15
# Claude CLI (headless) one-shot budget for a single live follow-up question. Much
# smaller than the report budget — it's one short question, but Claude still has cold
# start + reasoning overhead, so give it more room than the 8s HTTP path.
FOLLOW_UP_CLAUDE_TIMEOUT = 60
P3_QUICK_FOLLOW_UP_CODEX_MODEL = SPEAKING_AI_DEFAULT_HTTP_MODEL
P3_QUICK_FOLLOW_UP_HTTP_TIMEOUT = 8
P3_QUICK_FOLLOW_UP_CODEX_TIMEOUT = 12
SPEAKING_REPORT_HTTP_TIMEOUT = 60
# Claude CLI (headless) reasons before answering, so a full scoring + overall-review
# prompt routinely needs more than the 60s HTTP budget. A too-short timeout makes the
# claude path silently time out and fall back to codex (the "never see a Claude report"
# bug), so give Claude its own, larger budget.
SPEAKING_REPORT_CLAUDE_TIMEOUT = 180
SPEAKING_TURN_FEEDBACK_HTTP_TIMEOUT = 90
P3_TURN_COUNT = 8
DEFAULT_FULL_NAME = "LiHua"
DEFAULT_ENGLISH_NAME = "Jasper"


def _speaking_http_provider(kind: str = "speaking", timeout_seconds: float | None = None) -> HttpApiProvider:
    base_url = _setting_or_env("AI_HTTP_BASE_URL")
    api_key = _setting_or_env("AI_HTTP_API_KEY")
    missing = [name for name, value in (("AI_HTTP_BASE_URL", base_url), ("AI_HTTP_API_KEY", api_key)) if not value]
    if missing:
        raise RuntimeError(f"HTTP speaking AI provider is not configured: missing {', '.join(missing)}")
    timeout = timeout_seconds or _float_setting_or_env("AI_HTTP_TIMEOUT_SECONDS", 8.0)
    return HttpApiProvider(
        HttpApiProviderConfig(
            base_url=base_url,
            api_key=api_key,
            model=speaking_ai_http_model(kind),
            timeout_seconds=timeout,
        )
    )


def _raise_report_provider_chain_error(
    *,
    http_error: Exception | None = None,
    codex_error: Exception | None = None,
    claude_error: Exception | None = None,
    fallback_message: str,
) -> None:
    """Raise the most useful report-provider error instead of masking HTTP failures.

    In chain mode the HTTP provider is the primary route for GPT. If it returns a
    real upstream error such as 401 and the optional Codex fallback is simply not
    installed on the worker, surfacing "codex CLI not found" sends debugging in
    the wrong direction. Prefer the HTTP error in that case.
    """
    codex_text = str(codex_error or "")
    if http_error and ("codex CLI not found" in codex_text or not codex_error):
        raise RuntimeError(str(http_error)) from http_error
    if codex_error:
        raise RuntimeError(str(codex_error)) from codex_error
    if http_error:
        raise RuntimeError(str(http_error)) from http_error
    if claude_error:
        raise RuntimeError(str(claude_error)) from claude_error
    raise RuntimeError(fallback_message)


def _http_backend_name(stream: bool = False) -> str:
    return "http_api_stream" if stream else "http_api"


def _follow_up_generation_provenance(result: dict[str, Any]) -> dict[str, Any]:
    provenance: dict[str, Any] = {}
    for key in ("provider", "model"):
        value = _clean_report_text(str(result.get(key) or ""))[:120]
        if value:
            provenance[key] = value
    usage = result.get("usage")
    if isinstance(usage, dict) and usage:
        provenance["usage"] = usage
    latency_ms = result.get("latency_ms")
    if latency_ms not in (None, ""):
        provenance["latency_ms"] = _safe_int(latency_ms)
    return provenance





































def quick_follow_up_http_runner(
    current_question: str,
    candidate_answer: str,
    focus: str = "",
    question_type: str = "",
) -> dict[str, Any]:
    """Generate one P3 follow-up through an OpenAI-compatible HTTP endpoint."""
    question = clean_report_text(current_question)[:500]
    prompt = _quick_follow_up_prompt(current_question, candidate_answer, focus=focus, question_type=question_type)
    provider = _speaking_http_provider("followup", timeout_seconds=P3_QUICK_FOLLOW_UP_HTTP_TIMEOUT)
    result = provider.complete_chat(
        [
            {
                "role": "system",
                "content": "You are an IELTS Speaking examiner. Return only one concise follow-up question.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=80,
        temperature=0.2,
        timeout_seconds=P3_QUICK_FOLLOW_UP_HTTP_TIMEOUT,
        stream=True,
    )
    follow_up = _extract_single_follow_up_question(result.text, rejected_questions=(question,))
    return {
        "follow_up": follow_up,
        "backend": "http_api",
        "status": "ready",
        "provider": "openai_compatible_http",
        "latency_ms": int(result.elapsed_seconds * 1000),
        "model": result.model,
        "usage": getattr(result, "usage", None) or {},
    }


def quick_follow_up_codex_runner(
    current_question: str,
    candidate_answer: str,
    focus: str = "",
    question_type: str = "",
    timeout: int = P3_QUICK_FOLLOW_UP_CODEX_TIMEOUT,
) -> str:
    """Generate one P3 follow-up through the legacy low-overhead Codex exec call."""
    if os.environ.get("IELTS_WEB_DISABLE_CODEX") == "1":
        raise RuntimeError("codex disabled by IELTS_WEB_DISABLE_CODEX=1")
    question = clean_report_text(current_question)[:500]
    answer = clean_report_text(candidate_answer)[:2500]
    if not question:
        raise RuntimeError("missing current P3 question")
    if not answer:
        raise RuntimeError("missing candidate answer")

    codex = shutil.which("codex") or "/opt/homebrew/bin/codex"
    if not shutil.which(codex) and not Path(codex).exists():
        raise RuntimeError("codex CLI not found")

    prompt = _quick_follow_up_prompt(current_question, candidate_answer, focus=focus, question_type=question_type)
    cmd = [
        codex,
        "exec",
        "--skip-git-repo-check",
        "--ignore-rules",
        "--ignore-user-config",
        "--ephemeral",
        "--cd",
        "/tmp",
        "-m",
        P3_QUICK_FOLLOW_UP_CODEX_MODEL,
        "-c",
        f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"',
        "-",
    ]
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=True,
            cwd="/tmp",
        )
        return _extract_single_follow_up_question(str(result.stdout or ""), rejected_questions=(question,))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"codex quick follow-up timed out after {timeout}s") from exc
    except subprocess.CalledProcessError as exc:
        stderr = clean_report_text(str(exc.stderr or ""))[:180]
        raise RuntimeError(f"codex quick follow-up failed{f': {stderr}' if stderr else ''}") from exc


def quick_follow_up_runner_with_metadata(
    current_question: str,
    candidate_answer: str,
    focus: str = "",
    question_type: str = "",
    timeout: int = P3_QUICK_FOLLOW_UP_CODEX_TIMEOUT,
) -> dict[str, Any]:
    """Generate one P3 follow-up through the configured speaking AI route."""
    if _mode_is_fallback_only("followup"):
        raise RuntimeError("speaking follow-up provider disabled by SPEAKING_AI_CALL_MODE=fallback")

    http_error = ""
    if _mode_allows_http("followup"):
        try:
            return quick_follow_up_http_runner(
                current_question,
                candidate_answer,
                focus=focus,
                question_type=question_type,
            )
        except Exception as exc:  # noqa: BLE001 - provider chain may continue to Codex
            http_error = str(exc)
            if speaking_ai_call_mode("followup") == SPEAKING_AI_CALL_MODE_HTTP:
                raise RuntimeError(f"http_api: {http_error}") from exc

    if _mode_allows_codex("followup"):
        try:
            follow_up = quick_follow_up_codex_runner(
                current_question,
                candidate_answer,
                focus=focus,
                question_type=question_type,
                timeout=timeout,
            )
            return {
                "follow_up": follow_up,
                "backend": "codex_quick",
                "status": "ready",
                "provider": "codex_cli",
                "model": P3_QUICK_FOLLOW_UP_CODEX_MODEL,
            }
        except Exception as exc:  # noqa: BLE001 - caller will emit explicit fallback metadata
            if http_error:
                raise RuntimeError(f"http_api: {http_error}; codex_quick: {exc}") from exc
            raise RuntimeError(f"codex_quick: {exc}") from exc

    raise RuntimeError(f"speaking follow-up provider disabled by SPEAKING_AI_CALL_MODE={speaking_ai_call_mode('followup')}")


def quick_follow_up_runner(
    current_question: str,
    candidate_answer: str,
    focus: str = "",
    question_type: str = "",
    timeout: int = P3_QUICK_FOLLOW_UP_CODEX_TIMEOUT,
) -> str:
    """Backward-compatible follow-up API returning only the generated question."""
    return str(
        quick_follow_up_runner_with_metadata(
            current_question,
            candidate_answer,
            focus=focus,
            question_type=question_type,
            timeout=timeout,
        )["follow_up"]
    )


def _generate_p3_dynamic_follow_up(
    current_question: str,
    question_type: str,
    transcript: str,
    focus: str = "",
    call_id: str = "",
) -> dict[str, Any]:
    fallback = _dynamic_p3_follow_up(question_type, transcript, focus)
    try:
        result = quick_follow_up_runner_with_metadata(
            current_question,
            transcript,
            focus=focus,
            question_type=question_type,
            timeout=P3_QUICK_FOLLOW_UP_CODEX_TIMEOUT,
        )
        return result
    except Exception as exc:  # noqa: BLE001 - P3 follow-up must never block the flow
        return {
            "follow_up": fallback,
            "backend": "fallback",
            "status": "fallback",
            "error": f"{call_id}: {exc}" if call_id else str(exc),
        }




def build_p3_plan(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    theme = str(payload.get("theme") or payload.get("topic") or "society and daily life").replace("_", " ").strip()
    theme = theme or "society and daily life"
    focus = _normalize_p3_focus(str(payload.get("p3_focus") or payload.get("focus") or ""))
    intensity = _normalize_p3_intensity(str(payload.get("p3_intensity") or payload.get("intensity") or ""))
    question_count = P3_MAIN_COUNT
    requested_source = _p3_source_type(payload)
    prior_answer = clean_report_text(str(payload.get("prior_answer") or ""))[:4000]
    p3_follow_up_text = clean_markdown_text(str(payload.get("p3_follow_up_text") or ""))[:8000]
    ai_source = str(payload.get("ai_source") or "").strip()
    provided_follow_ups = payload.get("p3_follow_ups")
    cue_questions = [
        clean_report_text(str(item))[:260]
        for item in provided_follow_ups
        if clean_report_text(str(item)) and ("?" in str(item) or "？" in str(item))
    ] if isinstance(provided_follow_ups, list) else []
    # A bank card may hold more follow-ups than one session should drill. Draw
    # `question_count` of them, least-practiced first, so each session is ~3
    # questions and repeats rotate through the rest. (<=count is left untouched.)
    if len(cue_questions) > question_count:
        cue_questions = _select_p3_followups(cue_questions, question_count, payload.get("_user"))
    material_questions = _p3_questions_from_material(p3_follow_up_text, question_count)

    if cue_questions:
        raw_plan = {
            "questions": cue_questions,
            "follow_up": _p3_follow_up_for_type(_p3_question_type_for_index(0, focus)),
            "backend": "season_bank",
            "status": "ready",
        }
        source_type = "season_bank"
    elif material_questions:
        raw_plan = {
            "questions": material_questions,
            "follow_up": _p3_follow_up_for_type(_p3_question_type_for_index(0, focus)),
            "backend": "p2_corpus",
            "status": "ready",
        }
        source_type = "p2_corpus"
    elif prior_answer.strip():
        raw_plan = _generate_p3_from_p2_answer(
            theme,
            prior_answer,
            f"p3_from_p2_{hashlib.sha1(prior_answer.encode('utf-8')).hexdigest()[:16]}",
            ai_source=ai_source,
        )
        source_type = _p3_source_type(payload, "p2_report")
    elif requested_source == "custom":
        raw_plan = _generate_p3_from_theme(
            theme,
            f"p3_custom_{hashlib.sha1(theme.encode('utf-8')).hexdigest()[:16]}",
            ai_source=ai_source,
        )
        source_type = "custom"
    else:
        raw_plan = _failed_p3_plan(
            theme,
            requested_source or "bank",
            "No fixed P3 question-bank follow-ups were provided, and no AI generation source was selected.",
        )
        source_type = requested_source or "bank"

    fixed_bank_questions = source_type in {"season_bank", "bank"}
    questions = [str(q).strip() for q in raw_plan.get("questions", []) if str(q).strip()]
    if not fixed_bank_questions:
        questions = questions[:question_count]

    structured_questions = _structured_p3_questions(questions, source_type, focus)
    first_type = structured_questions[0]["type"] if structured_questions else _p3_question_type_for_index(0, focus)
    follow_up = clean_report_text(str(raw_plan.get("follow_up") or _p3_follow_up_for_type(first_type)))
    if not follow_up or "?" not in follow_up:
        follow_up = _p3_follow_up_for_type(first_type)

    return {
        "version": 1,
        "theme": theme,
        "focus": focus,
        "focus_label": P3_FOCUS_OPTIONS[focus]["label"],
        "intensity": intensity,
        "source": {
            "type": source_type,
            "theme": theme,
            "p2_attempt_id": clean_report_text(str(payload.get("p2_attempt_id") or "")),
            "p2_question_id": clean_report_text(str(payload.get("p2_question_id") or payload.get("cue_id") or "")),
            "p2_corpus_entry_id": clean_report_text(str(payload.get("p2_corpus_entry_id") or "")),
            "season": clean_report_text(str(payload.get("season") or "")),
        },
        "questions": structured_questions,
        "question_texts": [item["question"] for item in structured_questions],
        "follow_up": follow_up,
        "backend": str(raw_plan.get("backend") or "fallback"),
        "status": str(raw_plan.get("status") or "fallback"),
        "question_count": len(structured_questions),
        **({"model": str(raw_plan.get("model"))} if raw_plan.get("model") else {}),
        **({"usage": raw_plan.get("usage")} if raw_plan.get("usage") else {}),
        **({"error": str(raw_plan.get("error"))} if raw_plan.get("error") else {}),
    }






def _p3_ai_json_from_prompt(
    *,
    prompt: str,
    call_id: str,
    max_tokens: int,
    ai_source: str = "",
) -> tuple[str, str, str, dict[str, Any]]:
    if ai_source == "claude_cli":
        output, usage = run_claude_cli(prompt, f"{call_id}_claude", timeout=SPEAKING_REPORT_CLAUDE_TIMEOUT)
        return output, "claude_cli", "claude", usage or {}
    if _mode_is_fallback_only("followup"):
        raise RuntimeError("speaking follow-up provider disabled by SPEAKING_AI_CALL_MODE=fallback")
    if _mode_allows_http("followup"):
        result = _speaking_http_provider("followup", timeout_seconds=45).complete_chat(
            [
                {"role": "system", "content": f"You are an IELTS Speaking Part 3 examiner. Return JSON only, with exactly {P3_MAIN_COUNT} questions and no extra text."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.15,
            timeout_seconds=45,
            stream=True,
        )
        return result.text, "http_api", result.model, getattr(result, "usage", None) or {}
    if _mode_allows_codex("followup"):
        output, usage = run_codex(prompt, call_id, timeout=45)
        return output, "codex", "", usage or {}
    raise RuntimeError(f"speaking follow-up provider disabled by SPEAKING_AI_CALL_MODE={speaking_ai_call_mode('followup')}")


def _generate_p3_from_p2_answer(theme: str, prior_answer: str, call_id: str, *, ai_source: str = "") -> dict[str, Any]:
    answer = clean_report_text(prior_answer)[:4000]
    if not answer:
        return _failed_p3_plan(theme, "p2_report", "P2 answer is required before generating AI P3 questions.")
    prompt = f"""Return ONLY this JSON shape:
{{
  "questions": ["question 1?", "question 2?", "question 3?"],
  "follow_up": "one concise examiner follow-up question?"
}}

Hard rules:
- The questions array MUST contain exactly {P3_MAIN_COUNT} items.
- Do NOT create Q4, Q5, extra questions, bullet lists, explanations, labels, markdown, or commentary.
- Each question must be a natural IELTS Speaking Part 3 examiner question.

Generate Part 3 questions based on this Part 2 response. The questions should extend the candidate's ideas into broader social discussion, comparison, reasons, consequences, and future trends.

Theme:
{theme}

    Candidate Part 2 answer:
{answer}
"""
    try:
        output, backend, provider_model, usage = _p3_ai_json_from_prompt(
            prompt=prompt,
            call_id=f"{call_id}_p3_from_p2",
            max_tokens=420,
            ai_source=ai_source,
        )
        payload = extract_json_object_with_keys(output, {"questions", "follow_up"})
        questions = _p3_questions_from_ai_payload(payload, P3_MAIN_COUNT)
        if len(questions) < P3_MAIN_COUNT:
            raise RuntimeError("P3 generation returned too few questions")
        follow_up = clean_report_text(str(payload.get("follow_up") or ""))
        if not follow_up or "?" not in follow_up:
            follow_up = _p3_follow_up_for_type(_p3_question_type_for_index(0, "comparison_concession"))
        return {
            "questions": questions,
            "follow_up": follow_up,
            "backend": backend,
            "status": "ready",
            **({"model": provider_model} if provider_model else {}),
            **({"usage": usage} if usage else {}),
        }
    except Exception as exc:  # noqa: BLE001 - caller must expose real AI failure, not fake questions
        return _failed_p3_plan(theme, "p2_report", str(exc))


def _generate_p3_from_theme(theme: str, call_id: str, *, ai_source: str = "") -> dict[str, Any]:
    clean_theme = clean_report_text(theme)[:500] or "society and daily life"
    prompt = f"""Return ONLY this JSON shape:
{{
  "questions": ["question 1?", "question 2?", "question 3?"],
  "follow_up": "one concise examiner follow-up question?"
}}

Hard rules:
- The questions array MUST contain exactly {P3_MAIN_COUNT} items.
- Do NOT create Q4, Q5, extra questions, bullet lists, explanations, labels, markdown, or commentary.
- Each question must be a natural IELTS Speaking Part 3 examiner question.

Generate IELTS Speaking Part 3 questions for this custom discussion theme. The questions should move from opinion to reasons, comparison, social impact, and future development. Do not write answers.

Theme:
{clean_theme}
"""
    try:
        output, backend, provider_model, usage = _p3_ai_json_from_prompt(
            prompt=prompt,
            call_id=f"{call_id}_p3_custom",
            max_tokens=360,
            ai_source=ai_source,
        )
        payload = extract_json_object_with_keys(output, {"questions", "follow_up"})
        questions = _p3_questions_from_ai_payload(payload, P3_MAIN_COUNT)
        if len(questions) < P3_MAIN_COUNT:
            raise RuntimeError("P3 custom generation returned too few questions")
        follow_up = clean_report_text(str(payload.get("follow_up") or ""))
        if not follow_up or "?" not in follow_up:
            follow_up = _p3_follow_up_for_type(_p3_question_type_for_index(0, "comparison_concession"))
        return {
            "questions": questions,
            "follow_up": follow_up,
            "backend": backend,
            "status": "ready",
            **({"model": provider_model} if provider_model else {}),
            **({"usage": usage} if usage else {}),
        }
    except Exception as exc:  # noqa: BLE001 - caller must expose real AI failure, not fake questions
        return _failed_p3_plan(clean_theme, "custom", str(exc))




def _create_turn(
    part: str,
    index: int,
    total: int,
    question: str,
    prompt: dict[str, Any] | None = None,
    cue_card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    turn_id = f"t{index + 1}"
    examiner_text = _cue_examiner_text() if part == "p2" and cue_card else question
    examiner_behavior = "auto_play_instruction_only" if part == "p2" and cue_card else "auto_play_question"
    return {
        "id": turn_id,
        "part": part,
        "index": index,
        "total": total,
        "status": "pending",
        "question": question,
        "prompt": prompt or {"question": question},
        "cue_card": cue_card,
        "timers": _timers_for_part(part),
        "examiner_text": examiner_text,
        "examiner_behavior": examiner_behavior,
        "examiner_tts": {"provider": "volcengine", "status": "pending", "audio_url": None},
        "audio": None,
        "transcript_raw": "",
        "transcript_cleaned": "",
        "transcript_markdown": "",
        "transcript_status": "missing",
        "duration_seconds": None,
        "band7_version": "",
        "band7_markdown": "",
        "model_audio": None,
        "upgrade_notes": [],
        "ai_coaching": "",
    }
















def _build_p1_turns(
    total: int = P1_TURN_COUNT,
    display_total: int | None = None,
    question_bank_scope: str | None = None,
    user: Any = None,
) -> list[dict[str, Any]]:
    bank = get_question_bank()
    p1_bank = bank.part1_for_scope(question_bank_scope)
    countable_intro_items = [item for item in P1_INTRO_QUESTIONS if item.get("counts_toward_total", True)]
    uncounted_intro_items = [item for item in P1_INTRO_QUESTIONS if not item.get("counts_toward_total", True)]
    remaining_count = max(0, total - len(countable_intro_items))
    ordinary_pool = [
        item for item in p1_bank if not _is_p1_work_study_identity_question(str(item.get("question") or ""))
    ]
    if len(ordinary_pool) < remaining_count:
        ordinary_pool = p1_bank
    if not ordinary_pool:
        ordinary_pool = [
            {"topic": "general", "question": "What do you like to do in your free time?"},
            {"topic": "general", "question": "Do you prefer mornings or evenings?"},
            {"topic": "general", "question": "Tell me about your hometown."},
            {"topic": "general", "question": "What kind of music do you enjoy?"},
            {"topic": "general", "question": "Do you like traveling?"},
            {"topic": "general", "question": "What is your favorite food?"},
            {"topic": "general", "question": "How do you usually spend your weekends?"},
            {"topic": "general", "question": "Do you prefer reading or watching movies?"},
            {"topic": "general", "question": "What is the weather like in your country?"},
            {"topic": "general", "question": "Do you have any hobbies?"},
        ]
    topics: dict[str, list[dict[str, Any]]] = {}
    for item in ordinary_pool:
        topics.setdefault(str(item.get("topic") or "general"), []).append(item)
    # Mirror the real P1: cover several DISTINCT topics, a capped handful of
    # questions each — never one giant topic, never a single topic for the whole
    # part. Topics are ordered least-practiced first; within each topic the
    # questions are also chosen least-practiced first, so a deep bank topic (e.g.
    # 18 questions) is walked through across sessions instead of dumped at once,
    # and no question is ever starved.
    topic_counts = _p1_topic_practice_counts(user, topics)
    topic_order = _weighted_topic_order(list(topics), topic_counts)
    available = len(topic_order)

    # How many questions this session should serve, and across how many topics.
    target_total = max(remaining_count, min(available, P1_TOPICS_PER_SESSION))
    min_topics = min(available, P1_TOPICS_PER_SESSION)
    # Enough topics that no topic has to exceed its per-topic cap.
    n_by_cap = -(-target_total // P1_QUESTIONS_PER_TOPIC_MAX)  # ceil division
    n_topics = min(available, max(min_topics, n_by_cap))
    selected = topic_order[:n_topics]

    # Distribute the target evenly across the selected topics (round-robin),
    # capped per topic at the smaller of the topic size and the hard cap.
    caps = [min(len(topics[t]), P1_QUESTIONS_PER_TOPIC_MAX) for t in selected]
    quota = [0] * n_topics
    target = min(target_total, sum(caps))
    assigned = 0
    while assigned < target:
        progressed = False
        for j in range(n_topics):
            if quota[j] < caps[j]:
                quota[j] += 1
                assigned += 1
                progressed = True
                if assigned >= target:
                    break
        if not progressed:
            break

    question_counts = _question_practice_counts(user, "p1")
    ordinary_questions: list[dict[str, Any]] = []
    for topic, want in zip(selected, quota):
        if want <= 0:
            continue
        ordinary_questions.extend(_select_least_practiced_items(topics[topic], want, question_counts))
    turn_items = uncounted_intro_items + countable_intro_items + ordinary_questions
    # The counted length is dynamic now, so derive the displayed "of N" total from
    # the actual questions. display_total carried an offset over `total` at the call
    # site (e.g. mock adds +1 for the upcoming P2 turn); preserve that offset.
    display_offset = (display_total - total) if display_total is not None else 0
    counted_total = len(countable_intro_items) + len(ordinary_questions)
    effective_display_total = counted_total + display_offset
    turns: list[dict[str, Any]] = []
    display_index = 0
    for index, item in enumerate(turn_items):
        counts_toward_total = bool(item.get("counts_toward_total", True))
        if counts_toward_total:
            display_index += 1
        turn = _create_turn(
            "p1",
            index,
            effective_display_total,
            item["question"],
            {
                "topic": item["topic"],
                "question": item["question"],
                "question_id": str(item.get("question_id") or p1_question_id(str(item["topic"]), str(item["question"]))),
                "counts_toward_total": counts_toward_total,
                **{
                    key: item[key]
                    for key in ("season", "status", "region", "source", "source_url")
                    if item.get(key)
                },
                **({"flow": item["flow"], "role": item["role"]} if item.get("flow") else {}),
            },
        )
        turn["counts_toward_total"] = counts_toward_total
        turn["display_index"] = display_index if counts_toward_total else 0
        turns.append(turn)
    return turns


def _build_p3_turns(
    theme: str,
    intensity: str = "high",
    prior_answer: str = "",
    p3_follow_up_text: str = "",
    focus: str = "comparison_concession",
    source_type: str = "",
    plan_payload: dict[str, Any] | None = None,
    season_bank_follow_ups: list[str] | None = None,
    season: str = "",
    p2_question_id: str = "",
    p2_corpus_entry_id: str = "",
    user: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    focus = _normalize_p3_focus(focus)
    intensity = _normalize_p3_intensity(intensity)
    plan = plan_payload if isinstance(plan_payload, dict) else None
    if not plan or not isinstance(plan.get("questions"), list):
        plan = build_p3_plan(
            {
                "theme": theme,
                "p3_intensity": intensity,
                "p3_focus": focus,
                "prior_answer": prior_answer,
                "p3_follow_up_text": p3_follow_up_text,
                "p3_follow_ups": season_bank_follow_ups or [],
                "source": source_type,
                "season": season,
                "p2_question_id": p2_question_id,
                "p2_corpus_entry_id": p2_corpus_entry_id,
                "_user": user,
            }
        )
    plan_questions = plan.get("questions", [])
    plan_source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    plan_source_type = str(plan_source.get("type") or source_type or "")
    bank_p2_question_id = clean_report_text(str(
        plan_source.get("p2_question_id")
        or plan_source.get("cue_id")
        or plan_source.get("question_id")
        or p2_question_id
        or ""
    ))
    linked_p2_corpus_entry_id = clean_report_text(str(plan_source.get("p2_corpus_entry_id") or p2_corpus_entry_id or ""))
    structured_questions: list[dict[str, Any]] = []
    if plan_questions and isinstance(plan_questions[0], dict):
        for index, item in enumerate(plan_questions):
            question = clean_report_text(str(item.get("question") or ""))
            if not question:
                continue
            question_type = str(item.get("type") or _p3_question_type_for_index(index, focus))
            item_source = str(item.get("source") or plan_source_type or source_type or "topic")
            p2_question_id = clean_report_text(str(item.get("p2_question_id") or bank_p2_question_id))
            followup_id = clean_report_text(str(item.get("followup_id") or ""))
            if not followup_id and item_source in {"season_bank", "bank"} and p2_question_id:
                followup_id = p3_bank_followup_id(p2_question_id, question, index)
            structured_questions.append(
                {
                    "id": str(item.get("id") or f"q{index + 1}"),
                    "type": question_type,
                    "question": question,
                    "target_moves": item.get("target_moves") or P3_TYPE_TARGET_MOVES.get(question_type, []),
                    "source": item_source,
                    "p2_question_id": p2_question_id,
                    "followup_id": followup_id,
                }
            )
    else:
        text_questions = [str(q).strip() for q in plan_questions if str(q).strip()]
        structured_questions = _structured_p3_questions(text_questions, source_type or "topic", focus)
        if (plan_source_type or source_type) in {"season_bank", "bank"} and bank_p2_question_id:
            for index, item in enumerate(structured_questions):
                item["p2_question_id"] = bank_p2_question_id
                item["followup_id"] = p3_bank_followup_id(bank_p2_question_id, item["question"], index)

    source = str(plan.get("source", {}).get("type") if isinstance(plan.get("source"), dict) else "")
    source = source or source_type or ("p2_answer" if prior_answer.strip() else "bank")
    fixed_bank_questions = source in {"season_bank", "bank"} and bool(structured_questions)
    question_count = len(structured_questions) if fixed_bank_questions else P3_MAIN_COUNT
    if not fixed_bank_questions:
        structured_questions = structured_questions[:question_count]

    use_follow_ups = intensity == "high"
    total = len(structured_questions) * 2 if use_follow_ups else len(structured_questions)
    turns: list[dict[str, Any]] = []
    for main_index, item in enumerate(structured_questions):
        question = item["question"]
        main_turn = _create_turn(
            "p3",
            len(turns),
            total,
            question,
            {
                "theme": theme,
                "question": question,
                "role": "main",
                "source": source,
                "question_type": item.get("type"),
                "target_moves": item.get("target_moves", []),
                "plan_question_id": item.get("id"),
                "p2_question_id": item.get("p2_question_id") or "",
                "p2_corpus_entry_id": linked_p2_corpus_entry_id,
                "p3_bank_followup_id": item.get("followup_id") or "",
                "followup_question": question,
            },
        )
        turns.append(main_turn)
        if use_follow_ups:
            follow_turn = _create_turn(
                "p3",
                len(turns),
                total,
                "",
                {
                    "theme": theme,
                    "question": "",
                    "role": "follow_up",
                    "after_main": main_index + 1,
                    "source": source,
                    "question_type": item.get("type"),
                    "target_moves": ["respond directly", "add evidence", "extend the idea"],
                    "plan_question_id": f"{item.get('id', f'q{main_index + 1}')}-follow",
                    "p2_question_id": item.get("p2_question_id") or "",
                    "p2_corpus_entry_id": linked_p2_corpus_entry_id,
                    "backend": "pending_ai_follow_up",
                    "generation_status": "pending",
                    "p3_bank_followup_id": "",
                    "followup_question": question,
                },
            )
            follow_turn["examiner_text"] = ""
            follow_turn["examiner_tts"] = {
                "provider": "volcengine",
                "status": "not_started",
                "audio_url": None,
                "message": "P3 follow-up question has not been generated yet.",
            }
            turns.append(follow_turn)
    plan = {
        **plan,
        "theme": theme,
        "focus": focus,
        "focus_label": P3_FOCUS_OPTIONS[focus]["label"],
        "intensity": intensity,
        "questions": structured_questions,
        "question_texts": [item["question"] for item in structured_questions],
        "question_count": len(structured_questions),
    }
    metadata = {
        "p3_generation_status": str(plan.get("status") or "fallback"),
        "p3_generation_source": source,
        "p3_generation_backend": str(plan.get("backend") or "fallback"),
        "p3_theme": theme,
        "p3_intensity": intensity,
        "p3_focus": focus,
        "p3_plan": plan,
    }
    if plan.get("error"):
        metadata["p3_generation_error"] = str(plan.get("error"))
    return turns, metadata




def _sample_p2_cue(question_bank_scope: str | None = None) -> dict[str, Any]:
    bank = get_question_bank()
    p2_bank = bank.part2_for_scope(question_bank_scope)
    if p2_bank:
        return random.choice(p2_bank)
    return {"title": "Describe a person you admire", "bullets": [], "rounding": ""}


def _build_turns(mode: str, payload: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
    question_bank_scope = normalize_question_bank_scope(str(payload.get("question_bank_scope") or payload.get("bank_scope") or ""))
    metadata: dict[str, Any] = {"question_bank_scope": question_bank_scope}
    if mode == "mock":
        cue = _sample_p2_cue(question_bank_scope)
        p1_turns = _build_p1_turns(P1_TURN_COUNT, P1_TURN_COUNT + 1, question_bank_scope, user=payload.get("_user"))
        p2_turn = _create_turn("p2", len(p1_turns), P1_TURN_COUNT + 1, _cue_to_text(cue), cue, cue)
        turns = p1_turns + [p2_turn]
        metadata = {
            **metadata,
            "p3_generation_status": "pending_after_p2",
            "p3_generation_source": "p2_answer",
            "p3_theme": str(cue.get("p3_theme") or cue.get("title") or "general speaking"),
        }
        if isinstance(cue.get("p3_follow_ups"), list):
            metadata["p3_follow_ups"] = cue["p3_follow_ups"]
        return "mock", "Full mock exam", turns, cue, metadata
    if mode == "p1":
        turns = _build_p1_turns(P1_TURN_COUNT, question_bank_scope=question_bank_scope, user=payload.get("_user"))
        return "p1", "Part 1 practice", turns, None, metadata
    if mode == "p2":
        p2_cue_id = str(payload.get("p2_cue_id") or "").strip()
        if p2_cue_id:
            cue = p2_bank_topic_for_question_id(p2_cue_id) or _sample_p2_cue(question_bank_scope)
        else:
            cue = _sample_p2_cue(question_bank_scope)
        turns = [_create_turn("p2", 0, 1, _cue_to_text(cue), cue, cue)]
        return "p2", str(cue.get("title", "Part 2 practice")), turns, cue, metadata
    if mode == "p3":
        theme = str(payload.get("theme") or payload.get("topic") or "society and daily life").strip()
        intensity = _normalize_p3_intensity(str(payload.get("p3_intensity") or payload.get("intensity") or "high"))
        focus = _normalize_p3_focus(str(payload.get("p3_focus") or payload.get("focus") or ""))
        prior_answer = clean_report_text(str(payload.get("prior_answer") or ""))[:4000]
        p3_follow_up_text = clean_markdown_text(str(payload.get("p3_follow_up_text") or ""))[:8000]
        p2_corpus_entry_id = clean_report_text(str(payload.get("p2_corpus_entry_id") or ""))
        if p2_corpus_entry_id and not p3_follow_up_text:
            entry = p2_corpus_for_selection(payload.get("_user"), p2_corpus_entry_id) if payload.get("_user") else None
            p3_follow_up_text = str(entry.get("p3_follow_up_text") or "") if entry else ""
        if not payload.get("p3_follow_ups"):
            for cue in get_question_bank().part2_for_scope(question_bank_scope):
                if str(cue.get("p3_theme") or "") == theme and isinstance(cue.get("p3_follow_ups"), list):
                    payload["p3_follow_ups"] = cue["p3_follow_ups"]
                    payload.setdefault("season", cue.get("season"))
                    break
        source_type = _p3_source_type(payload)
        plan_payload = payload.get("p3_plan") if isinstance(payload.get("p3_plan"), dict) else None
        turns, metadata = _build_p3_turns(
            theme,
            intensity,
            prior_answer,
            p3_follow_up_text,
            focus,
            source_type,
            plan_payload,
            payload.get("p3_follow_ups") if isinstance(payload.get("p3_follow_ups"), list) else None,
            str(payload.get("season") or ""),
            clean_report_text(str(payload.get("p2_question_id") or payload.get("cue_id") or "")),
            p2_corpus_entry_id,
            user=payload.get("_user"),
        )
        if p2_corpus_entry_id:
            metadata["p2_corpus_entry_id"] = p2_corpus_entry_id
        metadata["question_bank_scope"] = question_bank_scope
        if str(payload.get("source") or "") == "p2_report":
            metadata["p3_generation_entry"] = "p2_report"
        return "p3", f"Part 3 discussion: {theme}", turns, None, metadata
    raise ValueError(f"Unsupported mode: {mode}")


def _candidate_names_from_payload(payload: dict[str, Any]) -> tuple[str, str]:
    full_name = str(payload.get("full_name") or payload.get("fullname") or DEFAULT_FULL_NAME).strip() or DEFAULT_FULL_NAME
    english_name = str(
        payload.get("english_name") or payload.get("englishName") or payload.get("candidate") or DEFAULT_ENGLISH_NAME
    ).strip() or DEFAULT_ENGLISH_NAME
    return full_name, english_name


def _clean_report_text(text: str) -> str:
    return "".join(c for c in text if c.isprintable() or c in "\n\t").strip()


def start_attempt(user, payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode") or payload.get("part") or "p1").lower().strip()
    if mode == "full":
        mode = "mock"
    if mode not in {"p1", "p2", "p3", "mock"}:
        raise ValueError(f"Invalid mode: {mode}")
    attempt_id = uuid.uuid4().hex
    full_name, english_name = _candidate_names_from_payload(payload)
    part, title, turns, cue_card, metadata = _build_turns(mode, {**payload, "_user": user})
    attempt = SpeakingAttempt.objects.create(
        user=user,
        attempt_id=attempt_id,
        mode=mode,
        part=part,
        title=title,
        status=SpeakingAttempt.Status.STARTED,
        full_name=full_name,
        english_name=english_name,
        metadata={
            "cue_card": cue_card,
            **metadata,
        },
    )
    for index, turn_data in enumerate(turns):
        SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id=turn_data["id"],
            sequence=index,
            part=turn_data["part"],
            question=turn_data["question"],
            counts_toward_total=turn_data.get("counts_toward_total", True),
            metadata={
                "prompt": turn_data.get("prompt"),
                "cue_card": turn_data.get("cue_card"),
                "timers": turn_data.get("timers"),
                "examiner_text": turn_data.get("examiner_text"),
                "examiner_tts": turn_data.get("examiner_tts"),
                "examiner_behavior": turn_data.get("examiner_behavior"),
                "display_index": turn_data.get("display_index"),
            },
        )

    if turns:
        ensure_examiner_tts(attempt_id, turns[0])
        db_turn = SpeakingTurn.objects.get(attempt=attempt, turn_id=turns[0]["id"])
        turn_metadata = db_turn.metadata if isinstance(db_turn.metadata, dict) else {}
        turn_metadata["examiner_tts"] = turns[0].get("examiner_tts")
        db_turn.metadata = turn_metadata
        db_turn.save(update_fields=["metadata"])
        if len(turns) > 1:
            _generate_remaining_examiner_tts_after_commit(attempt_id, [turn["id"] for turn in turns[1:]])

    response = {
        "id": attempt_id,
        "timestamp": attempt.created_at.isoformat(),
        "status": "started",
        "user_id": str(user.id),
        "mode": mode,
        "part": part,
        "title": title,
        "question": turns[0]["question"] if turns else "",
        "cue_card": cue_card,
        "turns": turns,
        "current_turn": turns[0]["id"] if turns else None,
        "candidate": english_name,
        "full_name": full_name,
        "english_name": english_name,
        "pronunciation": {"provider": "azure", "status": "pending"},
        "ielts_score": None,
        "feedback_summary": "",
        "criteria_feedback": {},
        "band7_version": "",
        "model_audio": None,
        "upgrade_notes": [],
        "ai_coaching": "",
        **metadata,
    }
    return response


# --- Runtime completion and scoring ---





















def _generate_p1_identity_follow_up(answer: str, call_id: str) -> dict[str, Any]:
    fallback = _fallback_p1_identity_follow_up(answer)
    if not answer.strip():
        return {
            "follow_up": "",
            "backend": "skipped",
            "status": "skipped",
            "error": "missing_candidate_answer",
        }
    prompt = _p1_identity_follow_up_prompt(answer)
    http_error = ""
    if _mode_is_fallback_only("followup"):
        return {
            "follow_up": fallback,
            "backend": "fallback",
            "status": "fallback",
            "error": "speaking follow-up provider disabled by SPEAKING_AI_CALL_MODE=fallback",
        }
    if _mode_allows_http("followup"):
        try:
            provider = _speaking_http_provider("followup", timeout_seconds=P1_FOLLOW_UP_HTTP_TIMEOUT)
            result = provider.complete_chat(
                [
                    {
                        "role": "system",
                        "content": "You are an IELTS Speaking Part 1 examiner. Return JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=80,
                temperature=0.2,
                timeout_seconds=P1_FOLLOW_UP_HTTP_TIMEOUT,
                stream=True,
            )
            follow_up = _extract_p1_identity_follow_up_output(result.text)
            return {
                "follow_up": follow_up,
                "backend": "http_api",
                "status": "ready",
                "provider": "openai_compatible_http",
                "latency_ms": int(result.elapsed_seconds * 1000),
                "model": result.model,
                "usage": getattr(result, "usage", None) or {},
            }
        except Exception as exc:  # noqa: BLE001 - provider chain may continue to Codex
            http_error = str(exc)
            if speaking_ai_call_mode("followup") == SPEAKING_AI_CALL_MODE_HTTP:
                return {
                    "follow_up": fallback,
                    "backend": "fallback",
                    "status": "fallback",
                    "error": f"http_api: {http_error}",
                }

    if _mode_allows_codex("followup"):
        try:
            output, _usage = run_codex(prompt, call_id, timeout=P1_FOLLOW_UP_CODEX_TIMEOUT)
            follow_up = _extract_p1_identity_follow_up_output(output)
            return {
                "follow_up": follow_up,
                "backend": "codex",
                "status": "ready",
                "provider": "codex_cli",
                "model": "codex-cli",
                "usage": _usage or {},
            }
        except Exception as exc:
            error = f"codex: {exc}"
            if http_error:
                error = f"http_api: {http_error}; {error}"
            return {
                "follow_up": fallback,
                "backend": "fallback",
                "status": "fallback",
                "error": error,
            }

    return {
        "follow_up": fallback,
        "backend": "fallback",
        "status": "fallback",
        "error": f"speaking follow-up provider disabled by SPEAKING_AI_CALL_MODE={speaking_ai_call_mode('followup')}",
    }


def _insert_p1_identity_follow_up(attempt: SpeakingAttempt, completed_turn: SpeakingTurn, *, stream_pending: bool = False) -> SpeakingTurn | None:
    if not _is_p1_work_study_turn(completed_turn):
        return None
    transcript = (completed_turn.transcript_cleaned or completed_turn.transcript_raw or "").strip()
    if not transcript:
        return None
    existing = attempt.turns.filter(metadata__prompt__after_turn=completed_turn.turn_id).first()
    if existing:
        return existing

    result = (
        {
            "follow_up": "",
            "backend": "stream_pending",
            "status": "pending",
        }
        if stream_pending
        else _generate_p1_identity_follow_up(transcript, f"p1_follow_up_{attempt.attempt_id}_{completed_turn.turn_id}")
    )
    follow_up = result["follow_up"]
    for item in attempt.turns.filter(sequence__gt=completed_turn.sequence).order_by("-sequence"):
        item.sequence += 1
        item.save(update_fields=["sequence"])

    turn_id = f"{completed_turn.turn_id}_followup"
    turn_data = _create_turn(
        "p1",
        completed_turn.sequence + 1,
        attempt.turns.count() + 1,
        follow_up or "Generating follow-up question...",
        {
            "topic": "intro",
            "question": follow_up,
            "flow": "intro",
            "role": "follow_up",
            "after_role": "work_study",
            "after_turn": completed_turn.turn_id,
            "source": "identity_answer",
            "backend": result["backend"],
            "generation_status": result["status"],
            **({"generation_error": result["error"]} if result.get("error") else {}),
            **_follow_up_generation_provenance(result),
            "counts_toward_total": False,
        },
    )
    turn_data["id"] = turn_id
    turn_data["counts_toward_total"] = False

    # Codex success preserves the legacy synchronous server TTS behavior. HTTP
    # success and fallback return the question first, then warm server TTS in the
    # background so the live practice flow is not held by a second network call.
    if result["backend"] == "codex":
        ensure_examiner_tts(attempt.attempt_id, turn_data)
    else:
        turn_data["examiner_tts"] = {
            "provider": "volcengine",
            "status": "pending",
            "audio_url": None,
            "message": "Follow-up returned immediately; server TTS will be generated in the background.",
        }

    follow_up_turn = SpeakingTurn.objects.create(
        user=attempt.user,
        attempt=attempt,
        turn_id=turn_id,
        sequence=completed_turn.sequence + 1,
        part="p1",
        question=follow_up,
        counts_toward_total=False,
        metadata={
            "prompt": turn_data.get("prompt"),
            "cue_card": None,
            "timers": turn_data.get("timers"),
            "examiner_text": follow_up,
            "examiner_behavior": "auto_play_question",
            "display_index": completed_turn.metadata.get("display_index") if isinstance(completed_turn.metadata, dict) else None,
            "examiner_tts": turn_data.get("examiner_tts")
            or {"provider": "volcengine", "status": "pending", "audio_url": None},
        },
    )
    if result["backend"] not in {"codex", "stream_pending"}:
        _generate_remaining_examiner_tts_after_commit(attempt.attempt_id, [follow_up_turn.turn_id])
    return follow_up_turn










def _reopen_turn_for_rerecord(attempt: SpeakingAttempt, turn: SpeakingTurn) -> SpeakingTurn:
    """Reset a just-completed turn back to a recordable state.

    Used when an answer came back empty and there is nothing to build on (e.g. a
    P3 main question whose follow-up cannot be generated). Clears the transcript,
    marks the turn pending, and points the attempt back at it so the learner can
    simply re-record this question instead of dead-ending on a follow-up that can
    never be generated.
    """
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    metadata = {
        **metadata,
        "status": "pending",
        "transcript_status": "missing",
        "transcript_markdown": "",
        "feedback_generation_status": "pending",
        "re_record_required": True,
        "re_record_reason": "empty_answer",
    }
    turn.transcript_raw = ""
    turn.transcript_cleaned = ""
    turn.metadata = metadata
    turn.save(update_fields=["transcript_raw", "transcript_cleaned", "metadata", "updated_at"])

    attempt_metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    attempt_metadata["current_turn"] = turn.turn_id
    attempt.metadata = attempt_metadata
    if attempt.status != SpeakingAttempt.Status.STARTED:
        attempt.status = SpeakingAttempt.Status.STARTED
    attempt.save(update_fields=["metadata", "status", "updated_at"])
    return turn


def complete_turn(user, attempt_id: str, turn_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    attempt = _load_attempt_for_user(user, attempt_id)
    if attempt.status == SpeakingAttempt.Status.ABORTED:
        raise SpeakingError("Aborted attempts cannot be completed.")
    if attempt.status == SpeakingAttempt.Status.SCORED:
        raise SpeakingError("Scored attempts cannot be completed.")
    turn = _find_turn(attempt, turn_id)

    client_transcript = str(payload.get("transcript_raw") or payload.get("transcript") or "").strip()
    transcript = client_transcript
    transcript_status = str(payload.get("transcript_status") or ("captured" if transcript else "missing")).strip()
    if transcript_status not in {"captured", "interim_fallback", "missing"}:
        transcript_status = "captured" if transcript else "missing"
    source = str(payload.get("transcript_source") or "browser_dictation").strip() or "browser_dictation"
    browser_transcript = client_transcript if source == "browser_dictation" else ""
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    audio_preprocessing_metrics = _sanitize_audio_preprocessing_metrics(payload.get("audio_preprocessing_metrics"))
    if audio_preprocessing_metrics:
        metadata["audio_preprocessing_metrics"] = audio_preprocessing_metrics
    realtime_asr_metrics = _sanitize_realtime_asr_metrics(payload.get("realtime_asr_metrics"))
    if realtime_asr_metrics:
        metadata["realtime_asr_metrics"] = realtime_asr_metrics
    p2_link = payload.get("p2_corpus_link") if isinstance(payload.get("p2_corpus_link"), dict) else None
    if turn.part == "p2" and p2_link:
        selected_entry = p2_corpus_for_selection(user, str(p2_link.get("entry_id") or ""))
        if selected_entry:
            metadata["p2_corpus_link"] = {
                "entry_id": selected_entry["entry_id"],
                "category": selected_entry["category"],
                "label": selected_entry["label"],
                "title": selected_entry["title"],
                "p3_follow_up_text": selected_entry.get("p3_follow_up_text", ""),
                "linked_at": timezone.now().isoformat(),
            }
    if client_transcript:
        skipped_status = (
            "skipped_browser_transcript_available"
            if source == "browser_dictation"
            else "skipped_client_transcript_available"
        )
        server_asr = {
            "ok": False,
            "status": skipped_status,
            "transcript": "",
            "error": f"Skipped during turn completion because {source} transcript is already available.",
        }
    else:
        server_asr = transcribe_turn_audio_with_server_asr(turn)
    metadata["server_asr"] = {key: value for key, value in server_asr.items() if key != "transcript"}
    if server_asr.get("ok") and str(server_asr.get("transcript") or "").strip():
        transcript = str(server_asr["transcript"]).strip()
        transcript_status = "captured"
        source = str(server_asr.get("provider") or "volcengine_realtime_asr")
    cleaned = _clean_report_text(transcript)
    p1_identity_follow_up_skipped = _is_p1_work_study_turn(turn) and not bool(cleaned.strip())
    duration = payload.get("duration_seconds")

    turn.transcript_raw = transcript
    turn.transcript_cleaned = cleaned
    turn.transcript_source = source
    if duration not in (None, ""):
        try:
            turn.duration_seconds = Decimal(str(duration))
        except Exception:
            turn.duration_seconds = None
    turn.pronunciation = turn.pronunciation or {
        "provider": "azure",
        "status": "fallback_browser_dictation" if transcript else "missing_audio",
        "pron_score": None,
        "accuracy": None,
        "fluency": None,
        "prosody": None,
        "issues": [],
        "message": "Pronunciation is not assessed by Django fallback turn completion.",
    }
    turn.metadata = {
        **metadata,
        "status": "completed",
        "transcript_status": transcript_status,
        "transcript_markdown": _spoken_markdown(cleaned),
        "cleaning_notes": [],
        "feedback_generation_status": "pending",
        "browser_transcript_raw": browser_transcript,
        "client_transcript_raw": client_transcript,
        "transcript_source": source,
    }
    turn.save()

    # Source interception: a P3 main answer that came back empty cannot seed a
    # dynamic follow-up (there is nothing to adapt from). Previously this
    # dead-ended the practice at "追问生成失败" with a useless retry. Reopen the
    # main turn for re-record ONLY when a follow-up actually follows it — that is
    # the case the re-record was meant to rescue. P3 sets without a following
    # follow_up turn (e.g. 3-main sessions) have nothing to dead-end, so an empty
    # main must proceed and be scored as "为空" instead of trapping the learner
    # in an inescapable re-record loop when dictation keeps coming back empty.
    turn_prompt = turn.metadata.get("prompt") if isinstance(turn.metadata.get("prompt"), dict) else {}
    if turn.part == "p3" and turn_prompt.get("role") == "main" and not cleaned.strip():
        upcoming = (
            attempt.turns.filter(sequence__gt=turn.sequence).order_by("sequence").first()
        )
        upcoming_role = ""
        if upcoming is not None and isinstance(upcoming.metadata, dict):
            upcoming_prompt = upcoming.metadata.get("prompt")
            if isinstance(upcoming_prompt, dict):
                upcoming_role = str(upcoming_prompt.get("role") or "")
        follow_up_would_dead_end = (
            upcoming is not None and upcoming.part == "p3" and upcoming_role == "follow_up"
        )
        if follow_up_would_dead_end:
            reopened = _reopen_turn_for_rerecord(attempt, turn)
            attempt.refresh_from_db()
            total = attempt.turns.count()
            return {
                "attempt": _runtime_attempt_payload(attempt),
                "turn": _turn_payload(reopened, total),
                "next_turn": _turn_payload(reopened, total),
                "re_record_required": True,
                "re_record_reason": "empty_answer",
                "re_record_message": "没有检测到你的回答，请重录这道题，开始后尽快开口。",
            }

    stream_follow_up = bool(payload.get("stream_follow_up"))
    inserted_follow_up = _insert_p1_identity_follow_up(attempt, turn, stream_pending=stream_follow_up)
    turns = list(attempt.turns.all().order_by("sequence"))
    next_turn = next((item for item in turns if item.sequence > turn.sequence and _turn_status(item) != "completed"), None)
    if inserted_follow_up is not None:
        next_turn = inserted_follow_up
    if (
        turn.part == "p3"
        and isinstance(turn.metadata, dict)
        and (turn.metadata.get("prompt") or {}).get("role") == "main"
        and next_turn is not None
        and next_turn.part == "p3"
    ):
        next_metadata = next_turn.metadata if isinstance(next_turn.metadata, dict) else {}
        next_prompt = next_metadata.get("prompt") if isinstance(next_metadata.get("prompt"), dict) else {}
        if next_prompt.get("role") == "follow_up":
            turn_prompt = turn.metadata.get("prompt") if isinstance(turn.metadata.get("prompt"), dict) else {}
            attempt_metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
            question_type = str(turn_prompt.get("question_type") or next_prompt.get("question_type") or "")
            focus = str(attempt_metadata.get("p3_focus") or "")
            current_question = str(turn_prompt.get("question") or turn.question or "")
            fallback_question = _dynamic_p3_follow_up(question_type, cleaned, focus)
            result = (
                {
                    "follow_up": STREAM_PENDING_FOLLOW_UP_PLACEHOLDER,
                    "fallback_question": fallback_question,
                    "backend": "stream_pending",
                    "status": "pending",
                }
                if stream_follow_up
                else _generate_p3_dynamic_follow_up(
                    current_question,
                    question_type,
                    cleaned,
                    focus,
                    f"p3_follow_up_{attempt.attempt_id}_{turn.turn_id}",
                )
            )
            follow_up = result["follow_up"]
            next_turn.question = follow_up
            next_prompt = {
                **next_prompt,
                "question": follow_up,
                "source": "adaptive_answer",
                "adapted_from_turn": turn.turn_id,
                "backend": result["backend"],
                "generation_status": result["status"],
                **({"fallback_question": result["fallback_question"]} if result.get("fallback_question") else {}),
                **({"generation_error": result["error"]} if result.get("error") else {}),
                **_follow_up_generation_provenance(result),
            }
            next_metadata = {
                **next_metadata,
                "prompt": next_prompt,
                "examiner_text": follow_up,
                "examiner_tts": {"provider": "volcengine", "status": "pending", "audio_url": None},
                "p3_dynamic_follow_up": True,
                "p3_dynamic_follow_up_backend": result["backend"],
                "p3_dynamic_follow_up_status": result["status"],
                **({"p3_dynamic_follow_up_error": result["error"]} if result.get("error") else {}),
            }
            next_turn.metadata = next_metadata
            next_turn.save(update_fields=["question", "metadata", "updated_at"])
            if not stream_follow_up:
                _generate_remaining_examiner_tts_after_commit(attempt.attempt_id, [next_turn.turn_id])
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    metadata["current_turn"] = next_turn.turn_id if next_turn else None
    attempt.metadata = metadata
    if next_turn is None:
        attempt.status = SpeakingAttempt.Status.READY_TO_SCORE
    attempt.save()
    attempt.refresh_from_db()

    return {
        "attempt": _runtime_attempt_payload(attempt),
        "turn": _turn_payload(turn, len(turns)),
        "next_turn": _turn_payload(next_turn, len(turns)) if next_turn else None,
        **(
            {
                "follow_up_skipped": {
                    "reason": "missing_candidate_answer",
                    "message": "没有检测到回答，已跳过追问。",
                }
            }
            if p1_identity_follow_up_skipped
            else {}
        ),
    }










def _follow_up_stream_context(attempt: SpeakingAttempt, source_turn: SpeakingTurn) -> dict[str, Any]:
    source_metadata = source_turn.metadata if isinstance(source_turn.metadata, dict) else {}
    transcript = clean_report_text(source_turn.transcript_cleaned or source_turn.transcript_raw)

    if _is_p1_work_study_turn(source_turn):
        if not transcript:
            raise SpeakingError("No answer was detected, so a follow-up question was skipped.")
        target = attempt.turns.filter(metadata__prompt__after_turn=source_turn.turn_id).first()
        if target is None:
            target = _insert_p1_identity_follow_up(attempt, source_turn, stream_pending=True)
        if target is None:
            raise SpeakingError("Follow-up turn could not be prepared.")
        return {
            "kind": "p1_identity",
            "target_turn": target,
            "prompt": _p1_identity_stream_prompt(transcript),
            "fallback": _fallback_p1_identity_follow_up(transcript),
            "rejected_questions": (),
            "extract": _extract_p1_identity_follow_up_output,
            "system": "You are an IELTS Speaking Part 1 examiner. Return only one concise follow-up question.",
            # P1 practice mode does not record audio, so transcript is often empty.
            # A generic prompt is used in that case — never skip the provider for P1.
            # Use higher temperature when there's no transcript so each call yields a different angle.
            "skip_provider": False,
            "skip_reason": "",
            "temperature": 0.2 if transcript else 0.8,
        }

    prompt = source_metadata.get("prompt") if isinstance(source_metadata.get("prompt"), dict) else {}
    if source_turn.part == "p3" and prompt.get("role") == "main":
        target = (
            attempt.turns
            .filter(sequence__gt=source_turn.sequence, part="p3")
            .order_by("sequence")
            .first()
        )
        if target is None:
            raise SpeakingError("P3 follow-up turn not found.")
        target_metadata = target.metadata if isinstance(target.metadata, dict) else {}
        target_prompt = target_metadata.get("prompt") if isinstance(target_metadata.get("prompt"), dict) else {}
        if target_prompt.get("role") != "follow_up":
            raise SpeakingError("Next P3 turn is not a follow-up turn.")
        attempt_metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
        question_type = str(prompt.get("question_type") or target_prompt.get("question_type") or "")
        focus = str(attempt_metadata.get("p3_focus") or "")
        current_question = str(prompt.get("question") or source_turn.question or "")
        fallback = _dynamic_p3_follow_up(question_type, transcript, focus)
        return {
            "kind": "p3_dynamic",
            "target_turn": target,
            "prompt": _quick_follow_up_prompt(current_question, transcript, focus=focus, question_type=question_type) if transcript else "",
            "fallback": fallback,
            "rejected_questions": (current_question,),
            "extract": lambda output: _extract_single_follow_up_question(output, rejected_questions=(current_question,)),
            "system": "You are an IELTS Speaking Part 3 examiner. Return only one concise follow-up question.",
            "question_type": question_type,
            "skip_provider": not bool(transcript),
            "skip_reason": "missing_transcript" if not transcript else "",
        }

    raise SpeakingError("This turn does not support streaming follow-up generation.")


def _save_streamed_follow_up(
    attempt: SpeakingAttempt,
    source_turn: SpeakingTurn,
    target_turn: SpeakingTurn,
    question: str,
    *,
    backend: str,
    status: str,
    error: str = "",
    question_type: str = "",
    provider: str = "",
    model: str = "",
    usage: dict[str, Any] | None = None,
    latency_ms: int | None = None,
) -> dict[str, Any]:
    metadata = target_turn.metadata if isinstance(target_turn.metadata, dict) else {}
    prompt = metadata.get("prompt") if isinstance(metadata.get("prompt"), dict) else {}
    updated_prompt = {
        **prompt,
        "question": question,
        "source": "streaming_follow_up",
        "adapted_from_turn": source_turn.turn_id,
        "backend": backend,
        "generation_status": status,
        **({"generation_error": error} if error else {}),
        **_follow_up_generation_provenance(
            {
                "provider": provider,
                "model": model,
                "usage": usage or {},
                "latency_ms": latency_ms,
            }
        ),
    }
    metadata = {
        **metadata,
        "prompt": updated_prompt,
        "examiner_text": question,
        "examiner_tts": {"provider": "volcengine", "status": "pending", "audio_url": None},
        "streaming_follow_up": True,
        "streaming_follow_up_backend": backend,
        "streaming_follow_up_status": status,
        **({"streaming_follow_up_error": error} if error else {}),
    }
    if question_type:
        metadata["p3_dynamic_follow_up"] = True
        metadata["p3_dynamic_follow_up_backend"] = backend
        metadata["p3_dynamic_follow_up_status"] = status
    target_turn.question = question
    target_turn.metadata = metadata
    target_turn.save(update_fields=["question", "metadata", "updated_at"])

    attempt_metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    attempt_metadata["current_turn"] = target_turn.turn_id
    attempt.metadata = attempt_metadata
    attempt.save(update_fields=["metadata", "updated_at"])
    return metadata


def _mark_streamed_follow_up_failed(
    attempt: SpeakingAttempt,
    source_turn: SpeakingTurn,
    target_turn: SpeakingTurn,
    error: str,
    *,
    question_type: str = "",
) -> dict[str, Any]:
    metadata = target_turn.metadata if isinstance(target_turn.metadata, dict) else {}
    prompt = metadata.get("prompt") if isinstance(metadata.get("prompt"), dict) else {}
    clean_error = clean_report_text(error)[:220]
    updated_prompt = {
        **prompt,
        "question": "",
        "source": "streaming_follow_up",
        "adapted_from_turn": source_turn.turn_id,
        "backend": "stream_failed",
        "generation_status": "failed",
        "generation_error": clean_error,
    }
    metadata = {
        **metadata,
        "prompt": updated_prompt,
        "examiner_text": "",
        "examiner_tts": {
            "provider": "volcengine",
            "status": "not_started",
            "audio_url": None,
            "message": "Follow-up generation failed before a finalized question was available.",
        },
        "streaming_follow_up": True,
        "streaming_follow_up_backend": "stream_failed",
        "streaming_follow_up_status": "failed",
        "streaming_follow_up_error": clean_error,
    }
    if question_type:
        metadata["p3_dynamic_follow_up"] = True
        metadata["p3_dynamic_follow_up_backend"] = "stream_failed"
        metadata["p3_dynamic_follow_up_status"] = "failed"
    target_turn.question = ""
    target_turn.metadata = metadata
    target_turn.save(update_fields=["question", "metadata", "updated_at"])

    attempt_metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    attempt_metadata["current_turn"] = target_turn.turn_id
    attempt.metadata = attempt_metadata
    attempt.save(update_fields=["metadata", "updated_at"])
    return metadata


def _generate_streamed_follow_up_tts(attempt: SpeakingAttempt, target_turn: SpeakingTurn) -> dict[str, Any]:
    target_turn.refresh_from_db()
    metadata = target_turn.metadata if isinstance(target_turn.metadata, dict) else {}
    turn_data = {
        "id": target_turn.turn_id,
        "question": target_turn.question,
        "examiner_text": metadata.get("examiner_text") or target_turn.question,
        "examiner_tts": metadata.get("examiner_tts") if isinstance(metadata.get("examiner_tts"), dict) else {
            "provider": "volcengine",
            "status": "pending",
            "audio_url": None,
        },
    }
    ensure_examiner_tts(attempt.attempt_id, turn_data)
    metadata["examiner_tts"] = turn_data.get("examiner_tts") or metadata.get("examiner_tts")
    target_turn.metadata = metadata
    target_turn.save(update_fields=["metadata", "updated_at"])
    return metadata["examiner_tts"]


def stream_follow_up_sse_events(user, attempt_id: str, turn_id: str) -> Iterator[str]:
    attempt = _load_attempt_for_user(user, attempt_id)
    if attempt.status == SpeakingAttempt.Status.ABORTED:
        raise SpeakingError("Aborted attempts cannot stream follow-up questions.")
    if attempt.status == SpeakingAttempt.Status.SCORED:
        raise SpeakingError("Scored attempts cannot stream follow-up questions.")
    source_turn = _find_turn(attempt, turn_id)
    context = _follow_up_stream_context(attempt, source_turn)
    target_turn = context["target_turn"]
    profile = getattr(user, "profile", None)
    ai_source = str(getattr(profile, "report_ai_source", "") or "").strip() if profile is not None else ""

    def generate() -> Iterator[str]:
        started = time.monotonic()
        parts: list[str] = []
        usage: dict[str, Any] = {}
        yield _sse_payload({"event": "start"})
        try:
            if context.get("skip_provider"):
                raise RuntimeError(str(context.get("skip_reason") or "follow-up provider skipped"))
            # Claude CLI is one-shot (no token stream): generate the whole question,
            # then emit it as a single chunk so the live UI still renders progressively.
            # This is what makes follow-ups work when the account AI source is Claude —
            # the HTTP relay is never touched.
            if ai_source == "claude_cli":
                combined_prompt = f"{context['system']}\n\n{context['prompt']}".strip()
                output, claude_usage = run_claude_cli(
                    combined_prompt,
                    f"follow_up_{attempt.attempt_id}_{source_turn.turn_id}_claude",
                    timeout=FOLLOW_UP_CLAUDE_TIMEOUT,
                )
                follow_up = context["extract"](output)
                yield _sse_payload({"event": "chunk", "text": follow_up})
                latency_ms = int((time.monotonic() - started) * 1000)
                _save_streamed_follow_up(
                    attempt,
                    source_turn,
                    target_turn,
                    follow_up,
                    backend="claude_cli_stream",
                    status="ready",
                    question_type=str(context.get("question_type") or ""),
                    provider="claude_cli",
                    model="claude",
                    usage=claude_usage or {},
                    latency_ms=latency_ms,
                )
                yield _sse_payload({
                    "event": "question_complete",
                    "text": follow_up,
                    "backend": "claude_cli_stream",
                    "latency_ms": latency_ms,
                    "provider": "claude_cli",
                    "model": "claude",
                    "usage": claude_usage or {},
                    "turn": _turn_payload(target_turn),
                })
            else:
                yield from _stream_http_follow_up(
                    attempt, source_turn, target_turn, context, started, parts, usage,
                )
        except Exception as exc:  # noqa: BLE001 - streaming endpoint must keep the practice flow usable
            # No fabricated fallback. If the configured provider fails we surface an empty
            # failed turn (frontend shows "点击重录"), never a canned imitation question.
            error = str(exc)
            _mark_streamed_follow_up_failed(
                attempt,
                source_turn,
                target_turn,
                error=error,
                question_type=str(context.get("question_type") or ""),
            )
            yield _sse_payload({
                "event": "failed",
                "backend": "stream_failed",
                "error": clean_report_text(error)[:220],
                "turn": _turn_payload(target_turn),
            })
            target_turn.refresh_from_db()
            yield _sse_payload({"event": "done", "turn": _turn_payload(target_turn)})
            return

        try:
            tts = _generate_streamed_follow_up_tts(attempt, target_turn)
        except Exception as exc:  # noqa: BLE001 - TTS failure should not block the next question
            tts = {
                "provider": "volcengine",
                "status": "failed",
                "audio_url": None,
                "error": clean_report_text(str(exc))[:220],
            }
        if tts.get("audio_url"):
            yield _sse_payload({"event": "tts_ready", "audio_url": tts["audio_url"], "examiner_tts": tts})
        else:
            yield _sse_payload({"event": "tts_timeout", "examiner_tts": tts})
        target_turn.refresh_from_db()
        yield _sse_payload({"event": "done", "turn": _turn_payload(target_turn)})

    return generate()


def _stream_http_follow_up(
    attempt: SpeakingAttempt,
    source_turn: SpeakingTurn,
    target_turn: SpeakingTurn,
    context: dict[str, Any],
    started: float,
    parts: list[str],
    usage: dict[str, Any],
) -> Iterator[str]:
    if not _mode_allows_http("followup") or _mode_is_fallback_only("followup"):
        raise RuntimeError(f"speaking follow-up HTTP provider disabled by SPEAKING_AI_CALL_MODE={speaking_ai_call_mode('followup')}")
    provider = _speaking_http_provider("followup", timeout_seconds=P3_QUICK_FOLLOW_UP_HTTP_TIMEOUT)
    for token in provider.stream_tokens(
        [
            {"role": "system", "content": context["system"]},
            {"role": "user", "content": context["prompt"]},
        ],
        max_tokens=40,
        temperature=float(context.get("temperature") or 0.2),
        timeout_seconds=P3_QUICK_FOLLOW_UP_HTTP_TIMEOUT,
        on_usage=lambda value: usage.update(value),
    ):
        parts.append(token)
        yield _sse_payload({"event": "chunk", "text": token})
    follow_up = context["extract"]("".join(parts))
    latency_ms = int((time.monotonic() - started) * 1000)
    model = speaking_ai_http_model("followup")
    _save_streamed_follow_up(
        attempt,
        source_turn,
        target_turn,
        follow_up,
        backend="http_api_stream",
        status="ready",
        question_type=str(context.get("question_type") or ""),
        provider="openai_compatible_http",
        model=model,
        usage=usage,
        latency_ms=latency_ms,
    )
    yield _sse_payload({
        "event": "question_complete",
        "text": follow_up,
        "backend": "http_api_stream",
        "latency_ms": latency_ms,
        "provider": "openai_compatible_http",
        "model": model,
        "usage": usage,
        "turn": _turn_payload(target_turn),
    })


def abort_attempt(user, attempt_id: str) -> dict[str, Any]:
    attempt = _load_attempt_for_user(user, attempt_id)
    if attempt.status == SpeakingAttempt.Status.SCORED:
        raise SpeakingError("Scored attempts cannot be aborted.")
    if attempt.status != SpeakingAttempt.Status.ABORTED:
        metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
        metadata["aborted_at"] = timezone.now().isoformat()
        metadata["current_turn"] = None
        attempt.metadata = metadata
        attempt.status = SpeakingAttempt.Status.ABORTED
        attempt.save()
    return _runtime_attempt_payload(attempt)




def score_with_codex(transcript: str, question: str, part: str, call_id: str, ai_source: str = "gpt") -> dict[str, Any]:
    """Score transcript using Codex CLI with full part-specific guidance.

    Raises RuntimeError if the model output is invalid or missing required fields.
    The caller should fall back to heuristic scoring on error.
    """
    data_dir = Path(settings.BASE_DIR).parent / "data" / "ielts"
    prompt_path = data_dir / "prompts" / "scorer_system.md"

    if prompt_path.exists():
        system_prompt = prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = (
            "You are an IELTS Speaking examiner. Score the transcript using the official IELTS band descriptors. "
            "Consider fluency and coherence, lexical resource, and grammatical range and accuracy."
        )

    profile = build_scoring_learning_profile(transcript, part)
    overall_review_profile = {
        key: value
        for key, value in profile.items()
        if key != "primary_focus_text"
    }
    overall_review_prompt = f"""

同时生成 Overall Review & Practice Focus。
overall_review 必须是 object，包含：
- markdown: 中文 Markdown，包含两个部分「总体点评」和「复盘重点」
- comment: 简短中文概括
- review_points: 中文字符串数组

Overall Review 写法要求：
- markdown 必须直接写成旧版报告风格：以「### 总体点评」开头，写 1-2 段即可；再写「### 复盘重点」，下面列出 3-5 条具体建议。
- 第一部分「总体点评」：必须引用本次转写中学员的真实原话，至少 1-2 处用中文引号标出具体片段，并围绕这些原话分析本次问题。不要写适用于任何人的通用建议。
- 第二部分「复盘重点」：必须 3-5 条，不少于 3、不多于 5；每条 1-2 句，聚焦本次最关键问题。可以带一个简短示范句，但不要长篇展开。
- 语气要具体、实用、有针对性，避免空泛评价
- 学习画像只作内部参考，严禁在输出里复述画像标签名（如 answer_development、short_answer、limited_development）或照搬通用结论句；不要写“你的学习画像里提到”这类话。
- 不要输出类似“回答基本相关，但展开偏短”这种过短 fallback 文案
- 如果练习部分是 p2，必须结合 cue card 与学员长回答的真实片段，指出内容组织、细节展开和可迁移到 P3 的讨论角度；不要只写“长回答不够展开”这类模板句。
- 如果练习部分是 p3，必须围绕 Part 3 的抽象讨论能力复盘：观点是否明确、原因链是否完整、是否有对比/让步、是否能从个人例子上升到社会层面、追问是否承接新角度；复盘重点要给出可直接练的 discussion move 和示范句。

本次成绩会由你在同一个 JSON 中给出。
练习部分：{part}
学习画像（仅供内部判断，不得原样复述）：
{json.dumps(overall_review_profile, ensure_ascii=False)}
"""

    full_prompt = (
        system_prompt
        + "\n\nReturn JSON only. The top-level object must contain numeric keys fluency_coherence, lexical_resource, "
        "grammatical_range, overall_band, string key feedback, and overall_review object "
        "with string keys markdown and comment plus array key review_points. Do not score pronunciation or reference pronunciation. "
        "Transcript note: answers may come from ASR and may still contain a few machine mis-recognitions. "
        "If a word is clearly an ASR error in context, do not count that word as a GRA/LR mistake; score real learner grammar, vocabulary, content, and fluency evidence. "
        + score_prompt_for_part(part)
        + overall_review_prompt
        + "\n\nPrompt(s):\n"
        + (question.strip() or "(not provided)")
        + "\n\nTranscript:\n"
        + transcript
        + "\n"
    )
    compact_prompt = (
        "Return JSON only. The top-level object must contain numeric keys fluency_coherence, lexical_resource, grammatical_range, "
        "overall_band, string key feedback, and overall_review object with string key comment and array "
        "key review_points and optional string key markdown. Score this IELTS Speaking response using the official IELTS Speaking criteria. "
        "Write Simplified Chinese overall_review.markdown in the old report style: ### 总体点评 with 1-2 focused paragraphs that quote 1-2 exact learner transcript fragments as evidence, then ### 复盘重点 with 3-5 concrete review points. "
        "Do not mention or repeat learning-profile tag names such as answer_development, short_answer, or limited_development. Each review point must be 1-2 sentences. "
        "Do not repeat the input. Do not include Markdown, explanation, or code fences. Do not score pronunciation from text. "
        "Transcript note: ASR may leave obvious machine mis-recognitions; do not count clearly machine-heard words as learner GRA/LR mistakes. "
        + score_prompt_for_part(part)
        + "\n\nQuestion or cue card:\n"
        + (question.strip() or "(not provided)")
        + "\n\nTranscript:\n"
        + transcript
        + "\n\nLearning profile for internal reference only; do not quote tag names or generic profile wording:\n"
        + json.dumps(overall_review_profile, ensure_ascii=False)
        + "\n"
    )

    last_error: Exception | None = None
    http_error: Exception | None = None
    codex_error: Exception | None = None
    claude_error: Exception | None = None
    provider_backend = ""
    provider_model = ""
    usage: dict[str, Any] | None = None
    for index, prompt in enumerate((full_prompt, compact_prompt), start=1):
        if _mode_is_fallback_only("report"):
            last_error = RuntimeError("speaking report provider disabled by SPEAKING_AI_CALL_MODE=fallback")
            continue

        # ── Claude CLI path ──────────────────────────────────────────────────
        if ai_source == "claude_cli":
            try:
                output, usage = run_claude_cli(prompt, f"{call_id}_claude_p{index}", timeout=SPEAKING_REPORT_CLAUDE_TIMEOUT)
                payload = extract_json_object_with_keys(
                    output,
                    {"fluency_coherence", "lexical_resource", "grammatical_range"},
                )
                provider_backend = "claude_cli"
                provider_model = "claude"
                break
            except Exception as exc:
                last_error = exc
                claude_error = exc
                # Claude CLI is an optional user preference, not a hard stop for
                # durable reports. If HTTP/Codex is available, continue through
                # the normal provider chain instead of leaving the report stuck
                # in analysis_failed after a Claude API/403/quota issue.

        # ── GPT / HTTP path ──────────────────────────────────────────────────
        if _mode_allows_http("report"):
            try:
                result = _speaking_http_provider("report", timeout_seconds=SPEAKING_REPORT_HTTP_TIMEOUT).complete_chat(
                    [
                        {"role": "system", "content": "You are an IELTS Speaking examiner. Return JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=1800 if index == 1 else 1200,
                    temperature=0.15,
                    timeout_seconds=SPEAKING_REPORT_HTTP_TIMEOUT,
                    stream=True,
                )
                payload = extract_json_object_with_keys(
                    result.text,
                    {"fluency_coherence", "lexical_resource", "grammatical_range"},
                )
                usage = getattr(result, "usage", None)
                provider_backend = "http_api"
                provider_model = result.model
                break
            except Exception as exc:
                last_error = exc
                http_error = exc
                if speaking_ai_call_mode("report") == SPEAKING_AI_CALL_MODE_HTTP:
                    continue
        if _mode_allows_codex("report"):
            try:
                output, usage = run_codex(prompt, f"{call_id}_p{index}", timeout=180)
                payload = extract_json_object_with_keys(
                    output,
                    {"fluency_coherence", "lexical_resource", "grammatical_range"},
                )
                provider_backend = "codex"
                provider_model = ""
                break
            except Exception as exc:
                last_error = exc
                codex_error = exc
    else:
        _raise_report_provider_chain_error(
            http_error=http_error,
            codex_error=codex_error,
            claude_error=claude_error,
            fallback_message=str(last_error or "speaking report scoring failed"),
        )

    # Validate required fields are present and numeric
    fc_raw = payload.get("fluency_coherence")
    lr_raw = payload.get("lexical_resource")
    gra_raw = payload.get("grammatical_range")

    # Check if all required fields are missing or invalid
    fc_valid = isinstance(fc_raw, (int, float)) and fc_raw > 0
    lr_valid = isinstance(lr_raw, (int, float)) and lr_raw > 0
    gra_valid = isinstance(gra_raw, (int, float)) and gra_raw > 0

    if not (fc_valid and lr_valid and gra_valid):
        raise RuntimeError(
            f"codex score missing or invalid fields: FC={fc_raw}, LR={lr_raw}, GRA={gra_raw}"
        )

    scores: dict[str, Any] = {
        "fluency_coherence": clamp_band(fc_raw),
        "lexical_resource": clamp_band(lr_raw),
        "grammatical_range": clamp_band(gra_raw),
    }
    scores["overall_band"] = rounded_overall(scores)

    result_payload = {
        **scores,
        "feedback": str(payload.get("feedback", "")),
        "backend": provider_backend or "unknown",
        "generation_backend": provider_backend or "unknown",
        "generation_status": "ready",
        **({"model": provider_model} if provider_model else {}),
    }

    overall_review = payload.get("overall_review")
    if isinstance(overall_review, dict):
        markdown = clean_markdown_text(str(overall_review.get("markdown") or ""))
        comment = clean_report_text(str(overall_review.get("comment") or ""))
        points = [clean_report_text(str(item)) for item in overall_review.get("review_points") or []]
        points = [item for item in points if item][:5]
        if markdown or comment or points:
            result_payload["overall_review"] = {
                "comment": comment,
                "review_points": points,
                "markdown": markdown,
                "source": f"{provider_backend or 'unknown'}_score",
            }

    if usage:
        result_payload["billing_usage"] = usage

    # Apply calibration and off-topic detection
    return cap_off_topic_score(calibrate_realistic_score(result_payload, question, transcript, part), question, transcript)


# --- Additional Missing Functions ---










def build_p3_discussion_skills(attempt: SpeakingAttempt) -> dict[str, Any] | None:
    """Build an explainable Part 3 discussion skill map from completed turns."""
    turns = [turn for turn in attempt.turns.all().order_by("sequence") if turn.part == "p3" and turn_counts_for_scoring(turn)]
    if not turns:
        return None
    main_turns = []
    follow_turns = []
    all_words = 0
    concession_hits = 0
    reason_hits = 0
    example_hits = 0
    abstract_hits = 0
    for turn in turns:
        metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
        prompt = metadata.get("prompt") if isinstance(metadata.get("prompt"), dict) else {}
        transcript = turn_display_transcript(turn)
        text = transcript.lower()
        words = re.findall(r"[A-Za-z']+", text)
        all_words += len(words)
        if prompt.get("role") == "follow_up":
            follow_turns.append(turn)
        else:
            main_turns.append(turn)
        if any(token in text for token in ("however", "although", "whereas", "on the other hand", "while some")):
            concession_hits += 1
        if any(token in text for token in ("because", "reason", "therefore", "as a result", "lead to", "due to")):
            reason_hits += 1
        if any(token in text for token in ("for example", "for instance", "such as", "in my city", "in china")):
            example_hits += 1
        if any(token in text for token in ("society", "people", "government", "public", "community", "generation")):
            abstract_hits += 1
    main_count = max(1, len(main_turns))
    average_words = round(all_words / max(1, len(turns)))

    def status(hit_count: int, threshold: float) -> str:
        return "strong" if hit_count / main_count >= threshold else ("developing" if hit_count else "weak")

    dimensions = [
        {
            "key": "abstract_extension",
            "label": "抽象展开",
            "status": status(abstract_hits, 0.45),
            "evidence": f"{abstract_hits}/{main_count} 个主问题有社会/群体层面的表达。",
            "next_action": "每题至少补一句“对社会/年轻人/普通家庭意味着什么”。",
        },
        {
            "key": "reasoning",
            "label": "原因与影响",
            "status": status(reason_hits, 0.6),
            "evidence": f"{reason_hits}/{main_count} 个主问题出现原因或结果连接。",
            "next_action": "先说观点，再用 because / as a result 明确解释因果。",
        },
        {
            "key": "comparison_concession",
            "label": "对比让步",
            "status": status(concession_hits, 0.35),
            "evidence": f"{concession_hits}/{main_count} 个主问题有让步或对比结构。",
            "next_action": "练习 however / whereas / on the other hand 承接反方观点。",
        },
        {
            "key": "specific_support",
            "label": "具体支撑",
            "status": status(example_hits, 0.45),
            "evidence": f"{example_hits}/{main_count} 个主问题用了例子或具体场景。",
            "next_action": "每个抽象观点后面补一个生活场景，不要只停在大词。",
        },
        {
            "key": "follow_up_handling",
            "label": "追问承接",
            "status": "strong" if len(follow_turns) >= main_count and average_words >= 35 else ("developing" if follow_turns else "weak"),
            "evidence": f"完成 {len(follow_turns)} 个追问，平均回答约 {average_words} 词。",
            "next_action": "追问不要重复主问题答案，直接回应新角度后再补理由。",
        },
    ]
    weakest = next((item for item in dimensions if item["status"] == "weak"), None) or next((item for item in dimensions if item["status"] == "developing"), dimensions[0])
    best = next((item for item in dimensions if item["status"] == "strong"), None)
    return {
        "title": "P3 Discussion Skills",
        "summary": f"这次 P3 平均每题约 {average_words} 词。P3 的关键不是讲个人经历，而是把观点扩展成原因、对比、社会影响和追问承接。",
        "dimensions": dimensions,
        "best_moment": best["label"] if best else "回答完整度",
        "fix_next": weakest["next_action"],
        "next_drill": [
            "选 1 道主问题，先用一句话直接表态。",
            "连续补两句：一个 because 原因，一个 for example / whereas 支撑。",
            "最后加一句 wider impact：对社会、学校、家庭或年轻人意味着什么。",
        ],
        "generation_backend": "heuristic",
        "generation_status": "fallback",
    }


def _p3_turn_context(attempt: SpeakingAttempt) -> list[dict[str, str]]:
    turns = [turn for turn in attempt.turns.all().order_by("sequence") if turn.part == "p3" and turn_counts_for_scoring(turn)]
    context: list[dict[str, str]] = []
    for turn in turns:
        metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
        prompt = metadata.get("prompt") if isinstance(metadata.get("prompt"), dict) else {}
        role = str(prompt.get("role") or "main")
        context.append(
            {
                "role": "follow_up" if role == "follow_up" else "main",
                "question": clean_report_text(turn.question or ""),
                "answer": clean_report_text(turn_display_transcript(turn)),
            }
        )
    return context


def _report_provider_json(
    prompt: str,
    required_keys: set[str],
    call_id: str,
    ai_source: str = "gpt",
    *,
    max_tokens: int = 1400,
    temperature: float = 0.15,
) -> tuple[dict[str, Any], str, str, dict[str, Any] | None]:
    last_error: Exception | None = None
    http_error: Exception | None = None
    codex_error: Exception | None = None
    claude_error: Exception | None = None

    if _mode_is_fallback_only("report"):
        raise RuntimeError("speaking report provider disabled by SPEAKING_AI_CALL_MODE=fallback")

    if ai_source == "claude_cli":
        try:
            output, usage = run_claude_cli(prompt, f"{call_id}_claude", timeout=SPEAKING_REPORT_CLAUDE_TIMEOUT)
            return extract_json_object_with_keys(output, required_keys), "claude_cli", "claude", usage
        except Exception as exc:
            last_error = exc
            claude_error = exc

    if _mode_allows_http("report"):
        try:
            result = _speaking_http_provider("report", timeout_seconds=SPEAKING_REPORT_HTTP_TIMEOUT).complete_chat(
                [
                    {"role": "system", "content": "You are an IELTS Speaking coach. Return JSON only."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_seconds=SPEAKING_REPORT_HTTP_TIMEOUT,
                stream=True,
            )
            usage = getattr(result, "usage", None)
            return extract_json_object_with_keys(result.text, required_keys), "http_api", result.model, usage
        except Exception as exc:
            last_error = exc
            http_error = exc

    if _mode_allows_codex("report"):
        try:
            output, usage = run_codex(prompt, call_id, timeout=180)
            return extract_json_object_with_keys(output, required_keys), "codex", "", usage
        except Exception as exc:
            last_error = exc
            codex_error = exc

    _raise_report_provider_chain_error(
        http_error=http_error,
        codex_error=codex_error,
        claude_error=claude_error,
        fallback_message=str(last_error or "speaking report provider unavailable"),
    )


def enrich_p3_discussion_skills_with_ai(
    attempt: SpeakingAttempt,
    base_skills: dict[str, Any] | None,
    score: dict[str, Any],
    learning_profile: dict[str, Any],
    call_id: str,
    ai_source: str = "gpt",
) -> dict[str, Any] | None:
    """Use the report AI provider to write P3 skill text while preserving heuristic statuses."""
    if not base_skills:
        return base_skills
    base_skills = json.loads(json.dumps(base_skills, ensure_ascii=False))
    base_skills["generation_backend"] = "heuristic"
    base_skills["generation_status"] = "fallback"
    context = _p3_turn_context(attempt)
    if not context:
        return base_skills

    dimension_contract = [
        {
            "key": item.get("key"),
            "label": item.get("label"),
            "status": item.get("status"),
            "heuristic_evidence": item.get("evidence"),
            "heuristic_next_action": item.get("next_action"),
        }
        for item in base_skills.get("dimensions", [])
        if isinstance(item, dict) and item.get("key")
    ]
    prompt = f"""
你是雅思口语 Part 3 教练。请根据学员本次真实 P3 回答，为「P3 Discussion Skills」生成个性化中文文本。

硬性规则：
- 只返回严格 JSON，不要 Markdown 代码块。
- 不要新增、删除或重命名维度；dimensions 只能使用给定 key。
- 不要改 status；status 已由程序按真实关键词命中计算。
- 只写文本字段：summary、best_moment、fix_next、next_drill，以及每个维度的 evidence、next_action。
- 内容必须针对学员原话和本次问题，具体、可执行，避免空泛套话。
- next_drill 必须正好 3 条。
- 如果学员回答很短，也要基于短答指出下一步练法，不要编造不存在的内容。

返回 JSON 结构：
{{
  "summary": "...",
  "best_moment": "...",
  "fix_next": "...",
  "next_drill": ["...", "...", "..."],
  "dimensions": {{
    "abstract_extension": {{"evidence": "...", "next_action": "..."}},
    "reasoning": {{"evidence": "...", "next_action": "..."}},
    "comparison_concession": {{"evidence": "...", "next_action": "..."}},
    "specific_support": {{"evidence": "...", "next_action": "..."}},
    "follow_up_handling": {{"evidence": "...", "next_action": "..."}}
  }}
}}

维度状态和启发式证据：
{json.dumps(dimension_contract, ensure_ascii=False)}

本次 P3 问答：
{json.dumps(context, ensure_ascii=False)}

分数：
{json.dumps(score, ensure_ascii=False)}

学习画像：
{json.dumps(learning_profile, ensure_ascii=False)}
"""
    try:
        payload, backend, model, usage = _report_provider_json(
            prompt,
            {"summary", "best_moment", "fix_next", "next_drill", "dimensions"},
            f"{call_id}_p3_discussion_skills",
            ai_source=ai_source,
            max_tokens=1500,
            temperature=0.2,
        )
        dimensions_payload = payload.get("dimensions")
        if not isinstance(dimensions_payload, dict):
            raise ValueError("P3 skills AI payload dimensions must be an object")
        base_keys = {str(item.get("key")) for item in base_skills.get("dimensions", []) if isinstance(item, dict)}
        missing = base_keys - set(dimensions_payload.keys())
        if missing:
            raise ValueError(f"P3 skills AI payload missing dimensions: {', '.join(sorted(missing))}")

        for key in ("summary", "best_moment", "fix_next"):
            text_value = clean_report_text(str(payload.get(key) or ""))
            if text_value:
                base_skills[key] = text_value

        drill_items = [clean_report_text(str(item)) for item in payload.get("next_drill") or []]
        drill_items = [item for item in drill_items if item][:3]
        if len(drill_items) == 3:
            base_skills["next_drill"] = drill_items

        for item in base_skills.get("dimensions", []):
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "")
            enrich = dimensions_payload.get(key)
            if not isinstance(enrich, dict):
                continue
            evidence = clean_report_text(str(enrich.get("evidence") or ""))
            next_action = clean_report_text(str(enrich.get("next_action") or ""))
            if evidence:
                item["evidence"] = evidence
            if next_action:
                item["next_action"] = next_action

        base_skills["generation_backend"] = backend
        base_skills["generation_status"] = "ready"
        if model:
            base_skills["generation_model"] = model
        if usage:
            base_skills["billing_usage"] = usage
        return base_skills
    except Exception as exc:
        base_skills["generation_backend"] = "heuristic"
        base_skills["generation_status"] = "fallback"
        base_skills["generation_error"] = clean_report_text(str(exc))[:240]
        return base_skills


def build_turn_band7_with_codex(question: str, transcript: str, part: str, call_id: str) -> str:
    """Generate Band 7 model answer using the configured speaking AI route."""
    part_constraints = ""
    if part == "p1":
        part_constraints = (
            "This is IELTS Speaking Part 1. Write a short natural answer, normally 1-3 sentences, maximum 3 sentences. "
            "Do not turn it into a long Part 2-style speech. One concise Markdown paragraph is preferred."
        )
    elif part == "p2":
        part_constraints = (
            "This is IELTS Speaking Part 2. Write a natural long-turn answer in Markdown paragraphs. "
            "Cover the cue-card points without copying the bullet list."
        )
    elif part == "p3":
        part_constraints = (
            "This is IELTS Speaking Part 3. Write a developed discussion answer, about 4-6 sentences, "
            "with a clear position, reasoning, one concrete example or contrast, and a wider social implication. "
            "Do not make it a Part 2 personal story."
        )
    else:
        part_constraints = "Write an answer appropriate to the IELTS Speaking part shown by the questions."

    prompt = (
        f"Write a natural IELTS Speaking Band 7 spoken version. Preserve the candidate's core ideas, "
        "but improve cohesion, vocabulary, and grammar. Do not include the original question or cue-card bullets. "
        "Format the answer as concise Markdown paragraphs with blank lines between paragraphs. "
        "Use Markdown bold on 2-5 high-value upgraded chunks such as natural collocations, topic-specific phrases, "
        "or useful sentence frames. Bold only the key phrases, not whole sentences. "
        "Example style: Well, **as a tech enthusiast**, I **usually spend** my evenings coding or **unwinding with** video games. "
        + part_constraints
        + "\n\nQuestion:\n"
        + question
        + "\n\nCandidate transcript:\n"
        + transcript
        + "\n\nBand 7 spoken version:"
    )

    if _mode_allows_http("report") and not _mode_is_fallback_only("report"):
        try:
            result = _speaking_http_provider("report", timeout_seconds=SPEAKING_TURN_FEEDBACK_HTTP_TIMEOUT).complete_chat(
                [
                    {"role": "system", "content": "You are an IELTS Speaking coach. Return only the answer text."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=700,
                temperature=0.25,
                timeout_seconds=SPEAKING_TURN_FEEDBACK_HTTP_TIMEOUT,
                stream=True,
            )
            return clean_band7_output(result.text)
        except Exception:
            if speaking_ai_call_mode("report") == SPEAKING_AI_CALL_MODE_HTTP:
                raise
    if not _mode_allows_codex("report"):
        raise RuntimeError(f"speaking report provider disabled by SPEAKING_AI_CALL_MODE={speaking_ai_call_mode('report')}")
    output, _ = run_codex(prompt, call_id)
    return clean_band7_output(output)


def build_ai_coaching_with_codex(question: str, transcript: str, band7: str, part: str, call_id: str, profile: dict[str, Any] | None = None) -> str:
    """Generate natural AI coaching using the configured speaking AI route."""
    prompt = f"""请为这一段 IELTS Speaking 回答生成中文 coaching。只输出 Markdown，不要标题。
请结合当前题目、用户转写、Band 7 参考答案和学习画像，自主判断该怎么评价。
不要套固定模板，不要强制写成固定几条，也不要按“问题/原因/替代表达/下一步”这种固定栏目组织。
你可以自由决定分点数量、分点顺序、是否给示范句，以及每一点的详略。重点是像真人老师一样评价这一次回答。
最后必须保留一个独立的语法纠错部分，格式为：
语法错误纠正：无
或：
语法错误纠正：
1. `原表达` -> `更自然的表达`

语法纠错只处理影响口语表达的语法或搭配问题；不要纠结句末标点、大小写或书面格式。
不要点评和真实口语表现无关的内容，例如大小写、标点、转写显示格式、ASR 噪声或浏览器转写造成的拼写/格式问题。
反例：如果 display_transcript 已经是 "at university"，不要说 raw transcript 里的 "at University" 不需要大写。
如果转写里存在明显机器听错并已在 display_transcript 层纠正的词，不要把这些 ASR 纠正词写进语法或表达纠错；只纠正用户真实说出的语法、搭配和表达问题。

Question:
{question}

Candidate transcript:
{transcript or '(missing)'}

Band 7 spoken version:
{band7}

Learning profile:
{json.dumps(profile or {})}
"""
    if _mode_allows_http("report") and not _mode_is_fallback_only("report"):
        try:
            result = _speaking_http_provider("report", timeout_seconds=SPEAKING_TURN_FEEDBACK_HTTP_TIMEOUT).complete_chat(
                [
                    {"role": "system", "content": "你是 IELTS Speaking 中文教练。只输出 Markdown 正文。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=900,
                temperature=0.2,
                timeout_seconds=SPEAKING_TURN_FEEDBACK_HTTP_TIMEOUT,
                stream=True,
            )
            output = result.text
        except Exception:
            if speaking_ai_call_mode("report") == SPEAKING_AI_CALL_MODE_HTTP:
                raise
            output, _ = run_codex(prompt, call_id)
    else:
        if not _mode_allows_codex("report"):
            raise RuntimeError(f"speaking report provider disabled by SPEAKING_AI_CALL_MODE={speaking_ai_call_mode('report')}")
        output, _ = run_codex(prompt, call_id)
    coaching = normalize_coaching_markdown(output)
    coaching = ensure_grammar_correction_bullet(coaching, transcript)
    if not acceptable_coaching_markdown(coaching):
        raise RuntimeError("codex coaching was missing meaningful feedback or grammar correction")
    return coaching

def coaching_prompt_constraints(part: str) -> str:
    if part == "p1":
        return """你是 IELTS Speaking 真人教练。
请用中文给这一次回答做简短口语反馈，只输出正文，不要标题。

正文要求：
- 先用 1-2 句话说清楚这次回答最大的问题。
- 然后用分点方式给出立即改进点；每一点内部直接说明问题和改法，不要套用固定模板。
- 不要使用“→ 改法：”这类固定结构。
- 立即改进点可以包含逻辑连贯、连接词、内容展开、表达自然度等问题，由你根据回答自行决定数量和顺序。

**语法 & 表达纠正：**
分点列出；每点按内容自然表达，不限制固定格式。
如无错误，写：无。

**亮点**（如有）：简短肯定 1 句用得好的地方

不要输出【】占位符；不要为了凑格式拆成“问题/改法”两行；根据这次回答决定立即改进点和语法表达纠正的数量。"""
    if part == "p3":
        return """你是 IELTS Speaking Part 3 真人教练。
请用中文给这一次回答做简短但有帮助的口语反馈，只输出正文，不要标题。

重点判断这次回答在 P3 真实考试里最影响分数的 discussion 问题：
- 有没有直接表达观点
- 有没有解释原因和影响
- 有没有对比、让步或反方角度
- 有没有从个人经历上升到更 general / social / abstract 的讨论
- 追问是否直接回应了新角度，而不是重复主问题

反馈可以自由分点，不要套固定模板，也不要限制点数。每一点都要具体指出这次回答缺了哪个讨论动作，并给一个可以马上照着说的改法或句型。
最后保留「语法 & 表达纠正」部分；如无错误，写：无。
不要点评大小写、标点、ASR 噪声或转写显示格式。"""
    return """请用中文给这一次回答做简短 IELTS Speaking 口语反馈，只输出正文，不要标题。
先判断真实考试里最影响分数的问题，只讲最值得改的 1-2 点，具体、短、能马上照着改。
最后保留「语法 & 表达纠正」部分；如无错误，写：无。"""


DISPLAY_TRANSCRIPT_ASR_RULES = """display_transcript is an ASR-corrected transcript for display and scoring:
- Fix confident ASR mis-recognition only when the ASR word is semantically unnatural in this exact question context and a phonetically similar correction is clearly natural.
- Examples of confident ASR fixes: for a science question, "Songs plays a vital role" -> "Science plays a vital role"; "sync my teeth into" -> "sink my teeth into"; "I'm a big fellows long holidays" -> "I'm a big fan of long holidays"; "Do the future" -> "In the future".
- Do not fix learner errors that the candidate probably really said. Keep grammar/collocation mistakes such as "I'm a university student major in software engineering" unchanged for coaching to correct.
- If uncertain, keep the ASR word. Do not guess content, add ideas, upgrade vocabulary, improve grammar, or turn display_transcript into a Band 7 answer.
- ASR-corrected words must not appear in ai_coaching as grammar/expression mistakes. ai_coaching must only correct learner errors that remain in display_transcript.
- Do not mention or correct words that are absent from display_transcript, and do not bring removed ASR noise back into coaching.
- Do not comment on capitalization, punctuation, written formatting, display formatting, ASR noise, or browser transcription artifacts."""

DISPLAY_TRANSCRIPT_MARKDOWN_RULES = """Also produce display_transcript_markdown:
- It must contain the same ASR-corrected wording as display_transcript.
- Split it into short spoken sentences, one sentence per paragraph, separated by blank lines.
- Do not add bullets, labels, quotes, or Markdown headings."""


def display_transcript_markdown_from_payload(value: Any, display_transcript: str, part: str = "") -> str:
    markdown = clean_markdown_text(str(value or ""))
    if markdown:
        return markdown
    return spoken_markdown(display_transcript, part)


def turn_feedback_with_codex(question: str, transcript: str, part: str, target: str, profile: dict[str, Any] | None, call_id: str, requires_ai_coaching: bool = True, ai_source: str = "") -> dict[str, str]:
    """Generate Band 7 and AI coaching together using Codex CLI.

    This combined generation ensures the Band 7 and coaching are consistent.

    Raises RuntimeError if the output is invalid or missing required fields.
    """
    prompt = f"""Return JSON only. The top-level object must contain keys display_transcript, display_transcript_markdown, band7_version and ai_coaching.
Do not repeat the input. Do not include Markdown outside string values, explanation, or code fences.

Task:
- First produce display_transcript and display_transcript_markdown: correct confident ASR mis-recognitions while preserving the learner's actual wording and errors.
- Then write one natural IELTS Speaking Band {target} spoken version based on display_transcript.
- Write Chinese Markdown coaching for this same turn only if requires_ai_coaching is true.
- Answer the exact examiner question directly and preserve the candidate's likely intent.
- Reuse the candidate's concrete idea when it is relevant; improve cohesion, vocabulary, and grammar.
- Do not include the original question, cue-card bullets, titles, labels, code fences, or logs.
- Base band7_version and ai_coaching on display_transcript, not noisy candidate transcript.
- Bad example: if display_transcript says "at university", do not say the raw phrase "at University" should not be capitalized.
- If requires_ai_coaching is false, set ai_coaching to an empty string.

{DISPLAY_TRANSCRIPT_ASR_RULES}

{DISPLAY_TRANSCRIPT_MARKDOWN_RULES}

Band 7 version constraints:
{model_answer_constraints(part)}
- For Part 1, write only 1-3 natural spoken sentences.
- Use Markdown bold inside band7_version to mark the phrases the learner should notice and reuse.
- Bold 2-5 useful upgraded chunks, such as natural collocations, idiomatic spoken links, or topic-specific phrases.
- Do not bold the whole answer or full sentences.
- Example style: Well, **as a tech enthusiast**, I **usually spend** my evenings coding or **unwinding with** video games.
- Do not use generic template lines such as "this is quite easy for me to answer", "connects with my daily life", or "closer to Band 7".
- If the transcript is weak, infer a sensible direct answer from the question type instead of writing a vague template.

Coaching constraints:
{coaching_prompt_constraints(part)}
- Do not explain how the Band 7 version was rewritten.
- Do not create a long line-by-line correction list outside the grammar/expression correction section.

Question:
{question}

Candidate transcript:
{transcript or "(missing)"}

requires_ai_coaching:
{json.dumps(bool(requires_ai_coaching))}

Learning profile:
{json.dumps(profile or {})}
"""
    compact_prompt = f"""Return JSON only. The top-level object must contain keys display_transcript, display_transcript_markdown, band7_version and ai_coaching.
Do not repeat the input. Do not include Markdown outside string values, explanation, or code fences.

First produce display_transcript and display_transcript_markdown with confident ASR mis-recognition fixes only, then write a natural IELTS Speaking Band {target} answer for the question.
If requires_ai_coaching is true, write Chinese coaching based only on display_transcript.
If requires_ai_coaching is false, set ai_coaching to an empty string.
In band7_version, use Markdown bold on 2-5 reusable upgraded phrases, not whole sentences.
The coaching format is up to you, but when coaching is required it must include a final section named "语法错误纠正：".
Do not use fixed labels or templates. Use the candidate's real meaning and do not invent facts.
Bad example: if display_transcript says "at university", do not say the raw phrase "at University" should not be capitalized.

{DISPLAY_TRANSCRIPT_ASR_RULES}

{DISPLAY_TRANSCRIPT_MARKDOWN_RULES}

Question:
{question}

Candidate transcript:
{transcript or "(missing)"}

requires_ai_coaching:
{json.dumps(bool(requires_ai_coaching))}
"""
    last_error: Exception | None = None
    for index, candidate_prompt in enumerate((prompt, compact_prompt), start=1):
        try:
            if ai_source == "claude_cli":
                output, usage = run_claude_cli(candidate_prompt, f"{call_id}_claude_p{index}", timeout=SPEAKING_REPORT_CLAUDE_TIMEOUT)
            else:
                output, usage = run_codex(candidate_prompt, f"{call_id}_p{index}")
            payload = extract_json_object_with_keys(output, {"display_transcript", "band7_version", "ai_coaching"})
            break
        except Exception as exc:
            last_error = exc
    else:
        raise RuntimeError(str(last_error or "turn feedback failed"))

    # Validate required fields exist
    band7_raw = payload.get("band7_version")
    coaching_raw = payload.get("ai_coaching")

    if not band7_raw or not str(band7_raw).strip():
        raise RuntimeError(f"codex turn feedback missing band7_version for {call_id}")

    if requires_ai_coaching and (not coaching_raw or not str(coaching_raw).strip()):
        raise RuntimeError(f"codex turn feedback missing ai_coaching for {call_id}")

    display_transcript = clean_report_text(str(payload.get("display_transcript") or ""))
    display_transcript_markdown = display_transcript_markdown_from_payload(
        payload.get("display_transcript_markdown"),
        display_transcript,
        part,
    )
    band7 = clean_band7_output(str(band7_raw))
    coaching = clean_coaching_markdown_text(str(coaching_raw))
    if not clean_report_text(band7):
        raise RuntimeError(f"codex turn feedback returned empty band7_version for {call_id}")

    if requires_ai_coaching:
        coaching = ensure_grammar_correction_bullet(coaching, display_transcript or transcript)
    if requires_ai_coaching and not acceptable_coaching_markdown(coaching):
        raise RuntimeError("codex turn feedback did not include usable coaching with grammar correction")

    return {
        "display_transcript": display_transcript,
        "display_transcript_markdown": display_transcript_markdown,
        "band7_version": band7,
        "ai_coaching": coaching if requires_ai_coaching else "",
        "usage": usage,
        "generation_backend": "claude_cli" if ai_source == "claude_cli" else "codex",
    }


def turn_feedback_batch_with_codex(
    turns: list[SpeakingTurn],
    attempt: SpeakingAttempt,
    target: str,
    profile: dict[str, Any] | None,
    call_id: str,
    prepared_corpus_by_turn: dict[str, str] | None = None,
    ai_source: str = "",
) -> dict[str, dict[str, str]]:
    """Generate Band 7 answers and coaching for all completed turns in one AI call.

    Honors the account AI source: when ai_source is "claude_cli" the whole batch is
    produced by the Claude CLI (same as the Overall review), instead of silently
    falling back to the HTTP relay / Codex — which is why per-turn Band 7 + coaching
    used to fail while the Claude Overall succeeded.
    """
    items: list[dict[str, str]] = []
    for turn in turns:
        if is_p1_name_intro_turn(turn):
            continue
        # Empty answers are still included so the AI writes a Band 7 model answer
        # from the question alone; coaching is suppressed (requires_ai_coaching=no).
        transcript = (turn.transcript_cleaned or turn.transcript_raw or "").strip()
        items.append(
            {
                "turn_id": turn.turn_id,
                "part": turn.part or "p1",
                "question": turn.question,
                "candidate_transcript": transcript,
                "prepared_corpus": (prepared_corpus_by_turn or {}).get(turn.turn_id, ""),
                "requires_ai_coaching": "yes" if turn_needs_ai_coaching(turn) else "no",
            }
        )
    if not items:
        return {}

    parts = sorted({item["part"] for item in items})
    coaching_constraints = "\n\n".join(
        f"For {part.upper()} coaching:\n{coaching_prompt_constraints(part)}"
        for part in parts
    )
    prompt = f"""Return JSON only. The top-level object must contain key turns.
Do not repeat the input JSON. Do not include Markdown outside string values, explanation, or code fences.
turns must be an array with one item for every input turn.
Each item must contain string keys turn_id, display_transcript, display_transcript_markdown, band7_version, and ai_coaching.

Task:
- For each turn, first produce display_transcript and display_transcript_markdown: correct confident ASR mis-recognitions while preserving the learner's actual wording and errors.
- Then write one natural IELTS Speaking Band {target} spoken version based on that display_transcript.
- Preserve the candidate's likely meaning and answer the exact examiner question directly.
- Write Chinese coaching only when requires_ai_coaching is "yes".
- Do not include the original question, cue-card bullets, titles, labels, code fences, or logs.
- If requires_ai_coaching is "no", set ai_coaching to an empty string.

prepared_corpus usage:
- Some P2 turns include prepared_corpus from the learner's P2 串题素材库 only when the learner explicitly linked a material during preparation.
- P1 语料库 content is not passed into this prompt.
- When prepared_corpus is present and relevant to the P2 cue card, build the Band 7 version on top of the prepared material: reuse it as much as possible with minimal changes to its storyline, ideas, and reusable chunks, then combine it with what the candidate actually said this time so the answer still directly fits this exact cue card.
- Do not throw the material away and write a fresh unrelated answer; do not invent facts beyond the prepared material plus the candidate_transcript.
- When prepared_corpus is present, the coaching should also help the learner reuse it as 串题素材 — for example how to keep most of it and stretch the same material onto this cue card and nearby P2 topics. Decide the angle, wording, and depth yourself; do not follow a fixed checklist, fixed labels, or a template.

display_transcript constraints:
{DISPLAY_TRANSCRIPT_ASR_RULES}

{DISPLAY_TRANSCRIPT_MARKDOWN_RULES}

Use display_transcript as the source of truth:
- band7_version and ai_coaching must be based on display_transcript, not noisy candidate_transcript.
- Do not mention or correct words that are absent from display_transcript.
- If display_transcript removes an ASR noise word, do not bring that removed word back in coaching.
- ai_coaching must comment on the answer as represented by display_transcript.
- Do not mention raw ASR noise or words removed during cleanup in coaching.
- Do not comment on capitalization, punctuation, written formatting, display formatting, ASR noise, or browser transcription artifacts.
- Bad example: if display_transcript says "at university", do not say the raw phrase "at University" should not be capitalized.

Band 7 version constraints:
- For Part 1, write only 1-3 natural spoken sentences.
- For Part 2, write a natural long-turn answer in Markdown paragraphs and cover the cue-card points.
- For Part 3, write a developed discussion answer with a clear position, reasoning, one concrete example or contrast, and a wider social implication. Do not make it a Part 2 personal story.
- Use Markdown bold inside band7_version to mark the phrases the learner should notice and reuse.
- Bold 2-5 useful upgraded chunks per answer, such as natural collocations, idiomatic spoken links, or topic-specific phrases.
- Do not bold the whole answer or full sentences.
- Example style: Well, **as a tech enthusiast**, I **usually spend** my evenings coding or **unwinding with** video games.
- Do not use generic template lines such as "this is quite easy for me to answer", "connects with my daily life", or "closer to Band 7".
- If the transcript is weak, infer a sensible direct answer from the question type instead of writing a vague template.

Coaching constraints:
{coaching_constraints}
- Do not explain how the Band 7 version was rewritten.
- Do not create a long line-by-line correction list outside the grammar/expression correction section.

Learning profile:
{json.dumps(profile or {})}

Input turns:
{json.dumps(items, ensure_ascii=False)}
"""
    if _mode_is_fallback_only("report"):
        raise RuntimeError("speaking report provider disabled by SPEAKING_AI_CALL_MODE=fallback")

    last_error: Exception | None = None
    usage: dict[str, Any] | None = None
    provider_backend = ""
    provider_model = ""
    payload: dict[str, Any] | None = None
    # Claude-source accounts: generate the whole batch with the Claude CLI only. Do
    # not fall through to HTTP/Codex — that would silently answer with a different
    # provider than the user picked (and is exactly the bug that left every turn's
    # Band 7 + coaching "生成失败" while the Claude Overall came through fine).
    if ai_source == "claude_cli":
        try:
            output, usage = run_claude_cli(prompt, f"{call_id}_claude", timeout=SPEAKING_REPORT_CLAUDE_TIMEOUT)
            provider_backend = "claude_cli"
            provider_model = "claude"
            payload = extract_json_object_with_keys(output, {"turns"})
        except Exception as exc:
            last_error = exc
        if payload is None:
            raise RuntimeError(str(last_error or "claude turn feedback provider failed"))
    if payload is None and ai_source != "claude_cli" and _mode_allows_http("report"):
        try:
            result = _speaking_http_provider("report", timeout_seconds=SPEAKING_TURN_FEEDBACK_HTTP_TIMEOUT).complete_chat(
                [
                    {"role": "system", "content": "You are an IELTS Speaking coach. Return JSON only."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2600,
                temperature=0.2,
                timeout_seconds=SPEAKING_TURN_FEEDBACK_HTTP_TIMEOUT,
                stream=True,
            )
            usage = getattr(result, "usage", None)
            provider_backend = "http_api"
            provider_model = result.model
            payload = extract_json_object_with_keys(result.text, {"turns"})
        except Exception as exc:
            last_error = exc
            if speaking_ai_call_mode("report") == SPEAKING_AI_CALL_MODE_HTTP:
                raise
    if payload is None and ai_source != "claude_cli" and _mode_allows_codex("report"):
        try:
            output, usage = run_codex(prompt, call_id, timeout=180)
            provider_backend = "codex"
            payload = extract_json_object_with_keys(output, {"turns"})
        except Exception as exc:
            last_error = exc
    if payload is None:
        raise RuntimeError(str(last_error or "speaking turn feedback provider failed"))
    raw_turns = payload.get("turns")
    if not isinstance(raw_turns, list):
        raise RuntimeError(f"codex batch turn feedback missing turns for {call_id}")

    by_id: dict[str, dict[str, str]] = {}
    for item in raw_turns:
        if not isinstance(item, dict):
            continue
        turn_id = clean_report_text(str(item.get("turn_id") or ""))
        display_transcript = clean_report_text(str(item.get("display_transcript") or ""))
        source_item = next((source for source in items if source["turn_id"] == turn_id), {})
        # Empty answers must stay empty: never let the model invent a transcript
        # for a turn the learner did not actually answer.
        if not source_item.get("candidate_transcript"):
            display_transcript = ""
        display_transcript_markdown = display_transcript_markdown_from_payload(
            item.get("display_transcript_markdown"),
            display_transcript,
            source_item.get("part", ""),
        )
        if not source_item.get("candidate_transcript"):
            display_transcript_markdown = ""
        band7 = clean_band7_output(str(item.get("band7_version") or ""))
        coaching = clean_coaching_markdown_text(str(item.get("ai_coaching") or ""))
        requires_ai_coaching = source_item.get("requires_ai_coaching") != "no"
        if not turn_id or not clean_report_text(band7):
            continue
        if requires_ai_coaching:
            coaching = ensure_grammar_correction_bullet(
                coaching,
                display_transcript or source_item.get("candidate_transcript", ""),
            )
            if not acceptable_coaching_markdown(coaching):
                coaching = ensure_grammar_correction_bullet(
                    "这次回答已经生成了参考答案；这条即时 coaching 先以语法纠错和 Band 7 版本对照为主。",
                    display_transcript or source_item.get("candidate_transcript", ""),
                )
        by_id[turn_id] = {
            "display_transcript": display_transcript,
            "display_transcript_markdown": display_transcript_markdown,
            "band7_version": band7,
            "ai_coaching": coaching if requires_ai_coaching else "",
            "usage": usage or {},
            "generation_backend": provider_backend or "unknown",
            **({"model": provider_model} if provider_model else {}),
        }
    if len(by_id) != len(items):
        # Only hard-fail when a turn the learner actually answered is missing usable
        # output. An empty-answer turn that fails to get a model answer is tolerated
        # (it stays without a Band 7 version) so it cannot sink the whole report.
        required_missing = [
            item["turn_id"]
            for item in items
            if item["turn_id"] not in by_id and item.get("candidate_transcript")
        ]
        if required_missing:
            raise RuntimeError(f"codex batch turn feedback missing usable output for turns: {', '.join(required_missing)}")
    return by_id


def build_upgrade_notes(transcript: str) -> list[str]:
    """Keep legacy table shape without rule-heavy vocabulary diagnostics."""
    return []


def _fallback_score(transcript: str, part: str) -> dict[str, Any]:
    words = _word_count(transcript)
    if words >= 220:
        base = 6.0
    elif words >= 120:
        base = 5.5
    elif words >= 60:
        base = 5.0
    elif words >= 25:
        base = 4.5
    else:
        base = 4.0
    if part == "p2" and words < 80:
        base = min(base, 5.0)
    if part == "p3" and words < 100:
        base = min(base, 5.0)
    return {
        "overall_band": base,
        "fluency_coherence": base,
        "lexical_resource": max(4.0, base - 0.5),
        "grammatical_range": max(4.0, base - 0.5),
        "pronunciation_estimate": None,
        "feedback": "Fallback score generated from completed browser transcripts. Configure the full AI scorer for richer feedback.",
        "backend": "fallback",
        "word_count": words,
    }


def fallback_score_for_report(transcript: str, questions_text: str, part: str, exc: Exception, call_id: str) -> dict[str, Any]:
    """Build an explicit fallback score after a real Codex scoring failure."""
    reason = f"Codex scoring failed: {exc}"
    score = _fallback_score(transcript, part)
    score["feedback"] = f"{score['feedback']} Fallback reason: {reason}"
    score["backend"] = "fallback"
    score["generation_backend"] = "fallback"
    score["generation_status"] = "fallback"
    score["fallback_reason"] = reason
    score["codex_call_id"] = call_id
    return cap_off_topic_score(calibrate_realistic_score(score, questions_text, transcript, part), questions_text, transcript)


def mark_attempt_analysis_failed(attempt: SpeakingAttempt, exc: Exception, call_id: str) -> None:
    """Persist a failed AI-analysis state without publishing a fake report."""
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    metadata.update(
        {
            "analysis_status": "failed",
            "analysis_backend": "codex",
            "analysis_error": str(exc),
            "analysis_call_id": call_id,
            "analysis_failed_at": timezone.now().isoformat(),
            "score_generation_backend": "codex",
            "score_generation_status": "failed",
            "score_generation_error": str(exc),
            "report_generation_backend": "codex",
            "report_generation_status": "failed",
        }
    )
    attempt.metadata = metadata
    if attempt.status != SpeakingAttempt.Status.SCORED:
        attempt.status = SpeakingAttempt.Status.READY_TO_SCORE
        attempt.save(update_fields=["status", "metadata", "updated_at"])
    else:
        attempt.save(update_fields=["metadata", "updated_at"])


def mark_attempt_analysis_ready(attempt: SpeakingAttempt, score: dict[str, Any], call_id: str) -> None:
    """Persist successful AI-analysis state so polling never shows stale queued/failed status."""
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    backend = str(score.get("generation_backend") or score.get("backend") or "codex")
    status = str(score.get("generation_status") or ("ready" if backend in {"codex", "http_api", "claude_cli"} else "fallback"))
    metadata.update(
        {
            "analysis_status": "ready",
            "analysis_backend": backend,
            "analysis_error": "",
            "analysis_call_id": call_id,
            "analysis_ready_at": timezone.now().isoformat(),
            "score_generation_backend": backend,
            "score_generation_status": status,
            "score_generation_error": str(score.get("fallback_reason") or ""),
            "report_generation_backend": str(score.get("backend") or backend),
            "report_generation_status": "ready" if status == "ready" else status,
        }
    )
    attempt.metadata = metadata




# --- P1 Name/Identity Helpers ---


DEFAULT_FULL_NAME = "Li Hua"
DEFAULT_ENGLISH_NAME = "Jasper"





















# --- Learning Profile ---


def build_learning_profile(user, attempt: SpeakingAttempt) -> dict[str, Any]:
    """Build learning profile from user's attempt history."""
    turns = list(attempt.turns.all().order_by("sequence"))
    completed_turns = [t for t in turns if _turn_status(t) == "completed" and turn_counts_for_scoring(t)]

    evidence: list[str] = []
    tags: list[str] = []
    repeated_phrases: list[str] = []

    for turn in completed_turns:
        transcript = turn_display_transcript(turn)
        if not transcript:
            continue
        word_count = _word_count(transcript)
        part = turn.part or ""
        if part == "p2":
            evidence.append(f"P2 回答约 {word_count} 词，需要继续拉长展开。")
        elif part == "p3":
            evidence.append(f"P3 回答约 {word_count} 词，需要补上原因、对比或例子。")
        elif part == "p1":
            evidence.append(f"P1 回答约 {word_count} 词，需要更直接、更自然。")

        # Check for short answers
        if word_count < 20:
            tags.append("short_answer")
        if word_count < 35:
            tags.append("limited_development")

    # Get weak items from training
    weak_obs = SpeakingTrainingObservation.objects.filter(user=user, weak_item_flag=True).order_by("-observed_at")[:10]
    for obs in weak_obs:
        if obs.weak_reasons:
            tags.extend(obs.weak_reasons)

    tags = sorted(set(tags))[:8]

    return {
        "primary_focus": "answer_development" if "short_answer" in tags or "limited_development" in tags else "task_relevance",
        "primary_focus_text": "这次主要卡在回答展开不够，不是题目完全不会。" if "limited_development" in tags else "这次主要问题是没有完全扣住题目，先把回答方向答准。",
        "habit_tags": tags,
        "repeated_phrases": repeated_phrases[:6],
        "evidence": evidence[:8],
    }


def build_scoring_learning_profile(transcript: str, part: str) -> dict[str, Any]:
    answers = [line[2:].strip() for line in transcript.splitlines() if line.startswith("A:")]
    word_counts = [_word_count(answer) for answer in answers if answer]
    tags: list[str] = []
    evidence: list[str] = []
    if word_counts:
        short_count = sum(1 for count in word_counts if count < 25)
        if short_count:
            tags.append("short_answer")
            evidence.append(f"{short_count} 个回答少于 25 词，需要展开。")
        if part == "p1" and sum(word_counts) / max(1, len(word_counts)) < 30:
            tags.append("limited_development")
            evidence.append("P1 平均回答偏短，需要稳定扩展到 2-3 句。")
        if part == "p2" and max(word_counts) < 90:
            tags.append("limited_development")
            evidence.append("P2 长回答长度不足，需要覆盖 cue card 并展开细节。")
        if part == "p3" and sum(word_counts) / max(1, len(word_counts)) < 55:
            tags.append("limited_development")
            evidence.append("P3 回答需要补充原因、对比和例子。")
    if part == "p3":
        lowered = transcript.lower()
        if not any(token in lowered for token in ("however", "although", "whereas", "on the other hand", "while some")):
            tags.append("missing_concession")
            evidence.append("P3 缺少对比或让步，观点容易显得单薄。")
        if not any(token in lowered for token in ("society", "government", "public", "community", "generation", "families", "schools")):
            tags.append("limited_abstract_extension")
            evidence.append("P3 还需要从个人想法上升到社会/群体层面。")
    focus = "answer_development" if any(tag in tags for tag in ("short_answer", "limited_development")) else "task_relevance"
    if part == "p3" and any(tag in tags for tag in ("missing_concession", "limited_abstract_extension")):
        focus = "abstract_discussion"
    return {
        "primary_focus": focus,
        "primary_focus_text": (
            "这次 P3 主要要补 discussion move：观点后面要有原因、对比/让步和社会层面的影响。"
            if focus == "abstract_discussion"
            else "这次主要卡在回答展开不够，不是题目完全不会。" if focus == "answer_development" else "这次主要问题是先把回答方向答准。"
        ),
        "habit_tags": sorted(set(tags)),
        "evidence": evidence[:8],
    }


# --- Build Turn Feedback (Complete) ---


def build_turn_feedback(
    turn: SpeakingTurn,
    attempt: SpeakingAttempt,
    user_profile: dict[str, Any] | None = None,
    allow_codex: bool = True,
    generated_feedback: dict[str, str] | None = None,
    ai_source: str = "",
) -> dict[str, Any]:
    """Build complete turn feedback with Band 7 and AI coaching.

    This is the complete migration from old server's build_turn_feedback.
    Returns a dict of fields to update in turn.metadata.
    """
    transcript = (turn.transcript_cleaned or turn.transcript_raw or "").strip()
    target = target_band_label(attempt)
    part = turn.part or "p1"

    # Get user profile for personalization
    profile = user_profile or {}
    full_name = profile.get("full_name")
    english_name = profile.get("english_name")

    # Result dict
    result: dict[str, Any] = {}

    # Try Codex generation first
    generated: dict[str, str] = dict(generated_feedback or {})
    if allow_codex and transcript and not generated:
        try:
            generated = turn_feedback_with_codex(
                turn.question,
                transcript,
                part,
                target,
                profile,
                f"turn_feedback_{attempt.attempt_id}_{turn.turn_id}",
                turn_needs_ai_coaching(turn),
                ai_source=ai_source,
            )
        except Exception as exc:
            result["feedback_generation_error"] = str(exc)

    # Build Band 7 version. Do not replace a failed AI answer with hardcoded
    # personal content unless this is the deterministic name-intro turn.
    band7 = generated.get("band7_version") or ""
    prompt = turn.metadata.get("prompt") if isinstance(turn.metadata, dict) else {}
    is_name_intro = part == "p1" and isinstance(prompt, dict) and prompt.get("flow") == "intro" and prompt.get("role") == "name"
    if not band7 and is_name_intro:
        band7 = build_turn_band7_fallback(
            turn.question,
            part,
            transcript,
            full_name,
            english_name,
            turn.metadata if isinstance(turn.metadata, dict) else None,
        )
    elif not band7:
        result["feedback_generation_status"] = "failed" if result.get("feedback_generation_error") else "pending"
        result["feedback_generation_error"] = result.get("feedback_generation_error") or "AI turn feedback has not been generated yet."

    result["band7_version"] = plain_spoken_text(band7)
    result["band7_markdown"] = spoken_markdown(band7, part)
    result["target_band_version"] = result["band7_version"]
    result["target_band_markdown"] = result["band7_markdown"]
    result["target_band"] = target
    display_transcript = clean_report_text(generated.get("display_transcript") or "")
    if display_transcript:
        result["display_transcript"] = display_transcript
        result["display_transcript_markdown"] = display_transcript_markdown_from_payload(
            generated.get("display_transcript_markdown"),
            display_transcript,
            part,
        )

    if result["band7_version"]:
        result["model_audio"] = volcengine_tts(
            result["band7_version"],
            role="model",
            cache_key=_model_band7_tts_cache_key(attempt.attempt_id, turn.turn_id, result["band7_version"]),
        )
    else:
        result["model_audio"] = {"provider": "none", "status": "empty_text", "audio_url": None}

    # Upgrade notes
    feedback_transcript = result.get("display_transcript") or transcript
    result["upgrade_notes"] = build_upgrade_notes(feedback_transcript)

    # Build AI coaching
    if turn_needs_ai_coaching(turn):
        coaching = generated.get("ai_coaching") or ""
        if not acceptable_coaching_markdown(coaching):
            # Fallback coaching
            coaching = build_ai_coaching_fallback(
                turn.question,
                feedback_transcript,
                result["band7_version"],
                part,
                profile,
            )
        result["ai_coaching"] = clean_markdown_text(coaching)
    else:
        result["ai_coaching"] = ""

    # Status fields. Keep provenance precise: batch report feedback can come
    # from the HTTP provider, while direct regeneration still returns a plain
    # generated dict from the Codex path.
    generated_backend = clean_report_text(str(generated.get("generation_backend") or generated.get("backend") or ""))
    if generated and generated_backend not in {"http_api", "codex", "claude_cli"}:
        generated_backend = "codex"
    result["feedback_generation_backend"] = generated_backend if generated else "fallback"
    if "feedback_generation_status" not in result:
        result["feedback_generation_status"] = "ready" if generated else "fallback"

    return result


def build_ai_coaching_fallback(
    question: str,
    transcript: str,
    band7: str,
    part: str,
    profile: dict[str, Any] | None = None,
) -> str:
    """Build transparent fallback coaching when Codex fails."""
    lines: list[str] = []
    lines.append("AI 辅导生成失败，当前没有展示伪 AI 建议。请点击重新生成，让系统重新调用 AI 分析这一次回答。")
    lines.append("")
    return ensure_grammar_correction_bullet("\n".join(lines), transcript)


def mark_missing_turn_feedback_pending(turns: list[SpeakingTurn]) -> None:
    """Keep report payloads honest when turn-level AI feedback is not ready."""
    for turn in turns:
        transcript = (turn.transcript_cleaned or turn.transcript_raw or "").strip()
        if not transcript or is_p1_name_intro_turn(turn):
            continue
        metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
        if metadata.get("feedback_generation_backend") in {"codex", "http_api"} and metadata.get("feedback_generation_status") == "ready":
            continue
        metadata.update(
            {
                "band7_version": "",
                "band7_markdown": "",
                "target_band_version": "",
                "target_band_markdown": "",
                "model_audio": {"provider": "none", "status": "pending", "audio_url": None},
                "ai_coaching": "",
                "feedback_generation_backend": "codex",
                "feedback_generation_status": "pending",
                "band7_source": "pending",
                "ai_coaching_source": "pending",
            }
        )
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])


def _turn_feedback_ready(turn: SpeakingTurn) -> bool:
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    return (
        metadata.get("feedback_generation_backend") in {"codex", "http_api"}
        and metadata.get("feedback_generation_status") == "ready"
        and bool(clean_report_text(metadata.get("band7_version") or metadata.get("band7_markdown") or ""))
    )


def _mark_turn_feedback_failed(turns: list[SpeakingTurn], exc: Exception) -> None:
    error = str(exc or "AI turn feedback generation failed")
    for turn in turns:
        transcript = (turn.transcript_cleaned or turn.transcript_raw or "").strip()
        if not transcript or is_p1_name_intro_turn(turn):
            continue
        metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
        metadata.update(
            {
                "band7_version": "",
                "band7_markdown": "",
                "target_band_version": "",
                "target_band_markdown": "",
                "model_audio": {"provider": "none", "status": "empty_text", "audio_url": None},
                "ai_coaching": "",
                "feedback_generation_backend": "codex",
                "feedback_generation_status": "failed",
                "feedback_generation_error": error,
                "band7_source": "failed",
                "ai_coaching_source": "failed",
            }
        )
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])


def generate_turn_feedback_for_report(
    attempt: SpeakingAttempt,
    scoring_turns: list[SpeakingTurn],
    learning_profile: dict[str, Any],
    call_id: str,
) -> None:
    """Generate per-turn Band 7 answers and coaching before publishing report payload."""
    pending_turns = [
        turn
        for turn in scoring_turns
        if not is_p1_name_intro_turn(turn)
        and not _turn_feedback_ready(turn)
    ]
    if not pending_turns:
        return

    profile_obj = getattr(attempt.user, "profile", None)
    ai_source = str(getattr(profile_obj, "report_ai_source", "") or "").strip() if profile_obj is not None else ""
    try:
        prepared_corpus_by_turn = prepared_corpus_for_turns(attempt.user, pending_turns)
        generated_by_turn = turn_feedback_batch_with_codex(
            pending_turns,
            attempt,
            target_band_label(attempt),
            learning_profile,
            f"{call_id}_turn_feedback_batch",
            prepared_corpus_by_turn=prepared_corpus_by_turn,
            ai_source=ai_source,
        )
    except Exception as exc:
        # Phase 1 (per-turn ASR cleanup + Band 7 + coaching) failed. Mark the turns and
        # propagate so the caller can abort the whole report instead of building the
        # Overall summary on raw ASR text. See the callers for why a half-report is worse
        # than no report.
        _mark_turn_feedback_failed(pending_turns, exc)
        raise

    for turn in pending_turns:
        generated = generated_by_turn.get(turn.turn_id) or {}
        feedback = build_turn_feedback(
            turn,
            attempt,
            learning_profile,
            allow_codex=False,
            generated_feedback=generated,
        )
        metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
        metadata.update(feedback)
        generation_backend = str(generated.get("generation_backend") or feedback.get("feedback_generation_backend") or "")
        if generation_backend in {"codex", "http_api", "claude_cli"}:
            metadata["band7_source"] = f"{generation_backend}_report_batch"
            metadata["ai_coaching_source"] = f"{generation_backend}_report_batch"
            metadata["feedback_generation_backend"] = generation_backend
            metadata["feedback_generation_status"] = "ready"
            if generated.get("model"):
                metadata["feedback_generation_model"] = generated["model"]
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])


def _training_relevance(question: str, transcript: str) -> Decimal:
    q_words = {word.strip(".,?!:;").lower() for word in question.split() if len(word.strip(".,?!:;")) > 3}
    t_words = {word.strip(".,?!:;").lower() for word in transcript.split() if len(word.strip(".,?!:;")) > 3}
    if not q_words or not t_words:
        return Decimal("0.000")
    return Decimal(str(round(len(q_words & t_words) / max(1, len(q_words)), 3)))


def score_attempt_sync(user, attempt_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    attempt = _load_attempt_for_user(user, attempt_id)
    if report_is_valid(attempt):
        return report_payload(attempt)
    if attempt.status == SpeakingAttempt.Status.ABORTED:
        raise SpeakingError("Aborted attempts cannot be scored.")
    turns = list(attempt.turns.all().order_by("sequence"))
    incomplete = [turn for turn in turns if _turn_status(turn) != "completed"]
    if incomplete:
        raise SpeakingError("Complete all speaking turns before generating the section report.")
    call_id = f"score_attempt_{attempt_id}"
    part = attempt.part or attempt.mode or ""

    mark_missing_turn_feedback_pending(turns)
    attempt.refresh_from_db()
    turns = list(attempt.turns.all().order_by("sequence"))
    scoring_turns = [turn for turn in turns if turn_counts_for_scoring(turn)]
    if not scoring_turns_have_answer_text(scoring_turns):
        raise SpeakingError("Missing transcript")

    learning_profile = build_learning_profile(user, attempt)
    # Phase 1: per-turn ASR cleanup (display_transcript) + Band 7 + coaching. The Overall
    # summary below is built from turn_display_transcript(), so if this fails the summary
    # would be scored on raw ASR and "correct" transcription noise as if it were the
    # learner's grammar (e.g. "where I was a child" when they clearly said "when"). Per
    # the rule "if the first pass fails, don't run the second", abort the whole report so
    # the user retries cleanly instead of getting a misleading half-report.
    try:
        generate_turn_feedback_for_report(attempt, scoring_turns, learning_profile, call_id)
    except ClaudeCliQuotaError as exc:
        raise SpeakingError("ai_quota_exhausted") from exc
    except Exception as exc:
        mark_attempt_analysis_failed(attempt, exc, call_id)
        raise SpeakingError(f"AI analysis failed: {exc}") from exc
    attempt.refresh_from_db()
    turns = list(attempt.turns.all().order_by("sequence"))
    scoring_turns = [turn for turn in turns if turn_counts_for_scoring(turn)]
    questions_text = "\n".join(f"Q{i + 1}: {turn.question}" for i, turn in enumerate(scoring_turns))
    transcript = "\n".join(
        f"Q{index + 1}: {turn.question}\nA: {turn_display_transcript(turn)}"
        for index, turn in enumerate(scoring_turns)
    )

    # Resolve per-user AI source preference
    try:
        _ai_source = (getattr(user, "profile", None) and user.profile.report_ai_source) or "gpt"
    except Exception:
        _ai_source = "gpt"

    try:
        score = score_with_codex(transcript, questions_text, part, call_id, ai_source=_ai_source)
        score = calibrate_realistic_score(score, questions_text, transcript, part)
    except ClaudeCliQuotaError as exc:
        raise SpeakingError("ai_quota_exhausted") from exc
    except Exception as exc:
        mark_attempt_analysis_failed(attempt, exc, call_id)
        raise SpeakingError(f"AI analysis failed: {exc}") from exc

    criteria = _criteria_feedback(score, transcript)

    attempt.status = SpeakingAttempt.Status.SCORED
    mark_attempt_analysis_ready(attempt, score, call_id)
    attempt.metadata = {
        **(attempt.metadata if isinstance(attempt.metadata, dict) else {}),
        "current_turn": None,
        "scored_at": timezone.now().isoformat(),
    }
    attempt.save()
    attempt.refresh_from_db()
    turns = list(attempt.turns.all().order_by("sequence"))
    scoring_turns = [turn for turn in turns if turn_counts_for_scoring(turn)]

    runtime = _runtime_attempt_payload(attempt)
    overall_review = build_overall_review(learning_profile, attempt, score, allow_codex=False)

    # Build personalized coaching
    personalized_coaching = build_personalized_coaching(learning_profile, attempt, score)
    p3_discussion_skills = enrich_p3_discussion_skills_with_ai(
        attempt,
        build_p3_discussion_skills(attempt),
        score,
        learning_profile,
        call_id,
        ai_source=_ai_source,
    )

    runtime.update(
        {
            "status": "scored",
            "transcript_cleaned": transcript,
            "ielts_score": score,
            "score_generation_backend": score.get("generation_backend", score.get("backend")),
            "score_generation_status": score.get("generation_status", "ready" if score.get("backend") in {"codex", "http_api"} else "fallback"),
            "score_generation_error": score.get("fallback_reason", ""),
            "report_generation_backend": score.get("backend"),
            "report_generation_status": "ready" if score.get("backend") in {"codex", "http_api"} else "fallback",
            "feedback_summary": score["feedback"],
            "criteria_feedback": criteria,
            "part_scores": {
                attempt.part or attempt.mode: {
                    "part": attempt.part or attempt.mode,
                    "turn_count": len(scoring_turns),
                    "band": score["overall_band"],
                    "fluency_coherence": score["fluency_coherence"],
                    "lexical_resource": score["lexical_resource"],
                    "grammatical_range": score["grammatical_range"],
                }
            },
            "overall_review": overall_review,
            "personalized_coaching": personalized_coaching,
            "p3_discussion_skills": p3_discussion_skills,
        }
    )

    report, _created = SpeakingReport.objects.update_or_create(
        user=user,
        attempt=attempt,
        defaults={
            "overall_band": Decimal(str(score["overall_band"])),
            "fluency_coherence": Decimal(str(score["fluency_coherence"])),
            "lexical_resource": Decimal(str(score["lexical_resource"])),
            "grammar_range_accuracy": Decimal(str(score["grammatical_range"])),
            "pronunciation": None,
            "feedback_summary": score["feedback"],
            "report_payload": runtime,
        },
    )

    observations = []
    for turn in scoring_turns:
        turn_text = turn_display_transcript(turn)
        word_count = _word_count(turn_text)
        reasons = []
        if score["overall_band"] < 5.5:
            reasons.append("low_band")
        if word_count < 25:
            reasons.append("short_answer")
        relevance = _training_relevance(turn.question, turn_text)
        if relevance < Decimal("0.200"):
            reasons.append("off_topic")
        observation, _ = SpeakingTrainingObservation.objects.update_or_create(
            user=user,
            observation_id=f"{attempt.attempt_id}_{turn.turn_id}",
            defaults={
                "attempt": attempt,
                "turn": turn,
                "legacy_attempt_id": attempt.attempt_id,
                "legacy_turn_id": turn.turn_id,
                "question_id": f"{turn.part}:{hashlib.md5(turn.question.encode()).hexdigest()[:12]}",
                "part": turn.part,
                "question": turn.question,
                "transcript": turn_text,
                "overall_band": Decimal(str(score["overall_band"])),
                "fluency_coherence": Decimal(str(score["fluency_coherence"])),
                "lexical_resource": Decimal(str(score["lexical_resource"])),
                "grammar_range_accuracy": Decimal(str(score["grammatical_range"])),
                "pronunciation": None,
                "relevance": relevance,
                "weak_item_flag": bool(reasons),
                "weak_reasons": reasons,
                "model_version": f"django_{score.get('backend', 'unknown')}",
                "observed_at": timezone.now(),
                "next_due": timezone.now() + timezone.timedelta(days=1 if reasons else 14),
            },
        )
        observations.append(
            {
                "observation_id": observation.observation_id,
                "question_id": observation.question_id,
                "part": observation.part,
                "weak_item_flag": observation.weak_item_flag,
                "weak_reasons": observation.weak_reasons,
            }
        )
    runtime["training_observations"] = observations
    report.report_payload = runtime
    report.save(update_fields=["report_payload", "updated_at"])
    return runtime


@transaction.atomic
def create_speaking_report_task(user, attempt_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    attempt = _load_attempt_for_user(user, attempt_id)
    if report_is_valid(attempt):
        report = report_payload(attempt)
        report["ai_task"] = speaking_task_summary_payload(latest_speaking_report_task(attempt))
        return report
    if attempt.status == SpeakingAttempt.Status.ABORTED:
        raise SpeakingError("Aborted attempts cannot be scored.")
    turns = list(attempt.turns.all().order_by("sequence"))
    incomplete = [turn for turn in turns if _turn_status(turn) != "completed"]
    if incomplete:
        raise SpeakingError("Complete all speaking turns before generating the section report.")
    scoring_turns = [turn for turn in turns if turn_counts_for_scoring(turn)]
    if not scoring_turns_have_answer_text(scoring_turns):
        raise SpeakingError("录音已保存，但没有拿到文字稿；请先重新转写录音或重录。")

    transcript_hash = hashlib.sha1(
        "\n".join(f"{turn.turn_id}:{turn.transcript_cleaned or turn.transcript_raw}" for turn in turns).encode("utf-8")
    ).hexdigest()[:16]
    idempotency_key = f"speaking_report:{attempt.attempt_id}:{transcript_hash}"
    latest_task = latest_speaking_report_task(attempt)
    if latest_task and latest_task.status in {AITask.Status.PENDING, AITask.Status.RUNNING}:
        return {
            "id": attempt.attempt_id,
            "status": "analysis_pending",
            "mode": attempt.mode,
            "part": attempt.part,
            "title": attempt.title,
            "created": False,
            "ai_task": task_payload(latest_task),
        }
    if latest_task and latest_task.status in {AITask.Status.FAILED, AITask.Status.FALLBACK, AITask.Status.CANCELLED}:
        idempotency_key = f"{idempotency_key}:retry:{uuid.uuid4().hex[:8]}"
    requested_provider = str(payload.get("provider") or "").strip()
    requested_model = str(payload.get("model") or "").strip()
    task, created = create_ai_task(
        user=user,
        task_type="speaking_report",
        idempotency_key=idempotency_key,
        provider="codex",
        model="",
        related_type="speaking_attempt",
        related_id=attempt.attempt_id,
        call_id=f"speaking_report_{attempt.attempt_id}",
        prompt_version=str(payload.get("prompt_version") or "speaking_report_v1"),
        request_payload={
            "attempt_id": attempt.attempt_id,
            "mode": attempt.mode,
            "part": attempt.part,
            "title": attempt.title,
            "transcript_hash": transcript_hash,
            "requested_provider": requested_provider,
            "requested_model": requested_model,
        },
        metadata={
            "source": "speaking_report_task",
            "requested_provider": requested_provider,
            "requested_model": requested_model,
        },
        max_attempts=int(payload.get("max_attempts") or 1),
    )
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    metadata.update(
        {
            "analysis_status": "queued" if task.status == AITask.Status.PENDING else task.status,
            "analysis_task_id": task.task_id,
            "analysis_queued_at": timezone.now().isoformat(),
        }
    )
    attempt.metadata = metadata
    if attempt.status != SpeakingAttempt.Status.READY_TO_SCORE:
        attempt.status = SpeakingAttempt.Status.READY_TO_SCORE
    attempt.save(update_fields=["status", "metadata", "updated_at"])

    return {
        "id": attempt.attempt_id,
        "status": "analysis_pending",
        "mode": attempt.mode,
        "part": attempt.part,
        "title": attempt.title,
        "created": created,
        "ai_task": task_payload(task),
    }


def score_attempt(user, attempt_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return create_speaking_report_task(user, attempt_id, payload)


# --- Regenerate ---


def regenerate_turn_feedback(user, attempt_id: str, turn_id: str) -> dict[str, Any]:
    """Regenerate AI feedback for a completed turn.

    This is the complete migration from old server's handle_turn_feedback_regenerate.
    Uses build_turn_feedback for consistent logic.

    Args:
        user: The authenticated user
        attempt_id: The attempt ID
        turn_id: The turn ID

    Returns:
        dict with 'ok', 'attempt', 'turn' keys

    Raises:
        SpeakingError: If validation fails or turn not found
    """
    attempt = _load_attempt_for_user(user, attempt_id)
    turn = SpeakingTurn.objects.filter(attempt=attempt, turn_id=turn_id).first()
    if not turn:
        raise SpeakingError("Turn not found")
    if _turn_status(turn) != "completed":
        raise SpeakingError("Only completed turns can regenerate AI feedback.")

    turn_transcript = turn.transcript_cleaned or turn.transcript_raw
    if not turn_transcript.strip():
        raise SpeakingError("Cannot regenerate feedback for empty transcript.")

    # Get user profile for personalization
    from apps.accounts.models import UserProfile
    profile_obj, _ = UserProfile.objects.get_or_create(user=user)
    user_profile = {
        "full_name": profile_obj.full_name,
        "english_name": profile_obj.english_name,
    }

    # Build learning profile
    learning_profile = build_learning_profile(user, attempt)

    # Honor the account AI source (Claude CLI vs HTTP/Codex) when regenerating.
    ai_source = str(getattr(profile_obj, "report_ai_source", "") or "").strip()

    # Use the complete build_turn_feedback logic
    feedback = build_turn_feedback(turn, attempt, user_profile, allow_codex=True, ai_source=ai_source)

    # Update turn metadata
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    metadata.update(feedback)
    metadata["feedback_regenerated_at"] = timezone.now().isoformat()

    # Track regeneration source
    feedback_backend = str(feedback.get("feedback_generation_backend") or "")
    if feedback_backend in {"codex", "http_api", "claude_cli"}:
        metadata["band7_source"] = f"{feedback_backend}_regenerated"
        metadata["ai_coaching_source"] = f"{feedback_backend}_regenerated"
    else:
        metadata["band7_source"] = "fallback_regenerated"
        metadata["ai_coaching_source"] = "fallback_regenerated"

    turn.metadata = metadata
    turn.save(update_fields=["metadata"])

    attempt.updated_at = timezone.now()
    attempt.save(update_fields=["updated_at"])

    # Update report payload if exists
    if hasattr(attempt, "report") and attempt.report:
        report = attempt.report
        payload = report.report_payload if isinstance(report.report_payload, dict) else {}
        turns_payload = payload.get("turns", [])
        for i, t in enumerate(turns_payload):
            if t.get("id") == turn_id:
                turns_payload[i]["band7_version"] = metadata.get("band7_version", "")
                turns_payload[i]["band7_markdown"] = metadata.get("band7_markdown", "")
                turns_payload[i]["target_band_version"] = metadata.get("target_band_version", "")
                turns_payload[i]["target_band_markdown"] = metadata.get("target_band_markdown", "")
                turns_payload[i]["target_band"] = metadata.get("target_band", "7")
                turns_payload[i]["display_transcript"] = metadata.get("display_transcript", "")
                turns_payload[i]["display_transcript_markdown"] = metadata.get("display_transcript_markdown", "")
                turns_payload[i]["upgrade_notes"] = metadata.get("upgrade_notes", [])
                turns_payload[i]["ai_coaching"] = metadata.get("ai_coaching", "")
                turns_payload[i]["model_audio"] = metadata.get("model_audio", {})
                turns_payload[i]["feedback_generation_status"] = metadata.get("feedback_generation_status", "ready")
                turns_payload[i]["feedback_generation_backend"] = metadata.get("feedback_generation_backend", "fallback")
        report.report_payload = payload
        report.save(update_fields=["report_payload", "updated_at"])

    return {
        "ok": True,
        "attempt": _runtime_attempt_payload(attempt),
        "turn": _turn_payload(turn),
    }


def regenerate_attempt_report(user, attempt_id: str) -> dict[str, Any]:
    """Regenerate the entire report for an already-scored attempt.

    This is used to fix reports that were incorrectly generated
    (e.g., due to codex returning 0 tokens or missing fields).

    Args:
        user: The authenticated user
        attempt_id: The attempt ID

    Returns:
        dict with 'ok', 'attempt' keys

    Raises:
        SpeakingError: If attempt not found or not in scored status
    """
    attempt = _load_attempt_for_user(user, attempt_id)
    if attempt.status != SpeakingAttempt.Status.SCORED:
        raise SpeakingError("Only scored attempts can be regenerated.")

    turns = list(attempt.turns.all().order_by("sequence"))
    incomplete = [turn for turn in turns if _turn_status(turn) != "completed"]
    if incomplete:
        raise SpeakingError("Cannot regenerate: attempt has incomplete turns.")

    call_id = f"regenerate_{attempt_id}"
    part = attempt.part or attempt.mode or ""

    mark_missing_turn_feedback_pending(turns)
    attempt.refresh_from_db()
    turns = list(attempt.turns.all().order_by("sequence"))
    scoring_turns = [turn for turn in turns if turn_counts_for_scoring(turn)]
    if not scoring_turns_have_answer_text(scoring_turns):
        raise SpeakingError("Missing transcript")

    learning_profile = build_learning_profile(user, attempt)
    # Phase 1 gate (same rule as score_attempt_sync): if per-turn ASR cleanup + Band 7 +
    # coaching fails, abort instead of regenerating the Overall on raw ASR text.
    try:
        generate_turn_feedback_for_report(attempt, scoring_turns, learning_profile, call_id)
    except ClaudeCliQuotaError as exc:
        raise SpeakingError("ai_quota_exhausted") from exc
    except Exception as exc:
        mark_attempt_analysis_failed(attempt, exc, call_id)
        raise SpeakingError(f"AI report regeneration failed: {exc}") from exc
    attempt.refresh_from_db()
    turns = list(attempt.turns.all().order_by("sequence"))
    scoring_turns = [turn for turn in turns if turn_counts_for_scoring(turn)]
    questions_text = "\n".join(f"Q{i + 1}: {turn.question}" for i, turn in enumerate(scoring_turns))
    transcript = "\n".join(
        f"Q{index + 1}: {turn.question}\nA: {turn_display_transcript(turn)}"
        for index, turn in enumerate(scoring_turns)
    )

    # Resolve per-user AI source preference
    try:
        _ai_source = (getattr(user, "profile", None) and user.profile.report_ai_source) or "gpt"
    except Exception:
        _ai_source = "gpt"

    try:
        score = score_with_codex(transcript, questions_text, part, call_id, ai_source=_ai_source)
        score = calibrate_realistic_score(score, questions_text, transcript, part)
    except ClaudeCliQuotaError as exc:
        raise SpeakingError("ai_quota_exhausted") from exc
    except Exception as exc:
        mark_attempt_analysis_failed(attempt, exc, call_id)
        raise SpeakingError(f"AI report regeneration failed: {exc}") from exc

    criteria = _criteria_feedback(score, transcript)

    mark_attempt_analysis_ready(attempt, score, call_id)
    attempt.updated_at = timezone.now()
    attempt.save(update_fields=["metadata", "updated_at"])
    attempt.refresh_from_db()
    turns = list(attempt.turns.all().order_by("sequence"))
    scoring_turns = [turn for turn in turns if turn_counts_for_scoring(turn)]

    runtime = _runtime_attempt_payload(attempt)
    overall_review = build_overall_review(learning_profile, attempt, score, allow_codex=False)

    # Build personalized coaching
    personalized_coaching = build_personalized_coaching(learning_profile, attempt, score)
    p3_discussion_skills = enrich_p3_discussion_skills_with_ai(
        attempt,
        build_p3_discussion_skills(attempt),
        score,
        learning_profile,
        call_id,
        ai_source=_ai_source,
    )

    runtime.update(
        {
            "status": "scored",
            "transcript_cleaned": transcript,
            "ielts_score": score,
            "score_generation_backend": score.get("generation_backend", score.get("backend")),
            "score_generation_status": score.get("generation_status", "ready" if score.get("backend") in {"codex", "http_api"} else "fallback"),
            "score_generation_error": score.get("fallback_reason", ""),
            "report_generation_backend": score.get("backend"),
            "report_generation_status": "ready" if score.get("backend") in {"codex", "http_api"} else "fallback",
            "feedback_summary": score["feedback"],
            "criteria_feedback": criteria,
            "part_scores": {
                attempt.part or attempt.mode: {
                    "part": attempt.part or attempt.mode,
                    "turn_count": len(scoring_turns),
                    "band": score["overall_band"],
                    "fluency_coherence": score["fluency_coherence"],
                    "lexical_resource": score["lexical_resource"],
                    "grammatical_range": score["grammatical_range"],
                }
            },
            "overall_review": overall_review,
            "personalized_coaching": personalized_coaching,
            "p3_discussion_skills": p3_discussion_skills,
            "regenerated_at": timezone.now().isoformat(),
        }
    )

    report, _created = SpeakingReport.objects.update_or_create(
        user=user,
        attempt=attempt,
        defaults={
            "overall_band": Decimal(str(score["overall_band"])),
            "fluency_coherence": Decimal(str(score["fluency_coherence"])),
            "lexical_resource": Decimal(str(score["lexical_resource"])),
            "grammar_range_accuracy": Decimal(str(score["grammatical_range"])),
            "pronunciation": None,
            "feedback_summary": score["feedback"],
            "report_payload": runtime,
        },
    )

    # Update training observations
    for turn in scoring_turns:
        turn_text = turn_display_transcript(turn)
        word_count = _word_count(turn_text)
        reasons = []
        if score["overall_band"] < 5.5:
            reasons.append("low_band")
        if word_count < 25:
            reasons.append("short_answer")
        relevance = _training_relevance(turn.question, turn_text)
        if relevance < Decimal("0.200"):
            reasons.append("off_topic")
        SpeakingTrainingObservation.objects.update_or_create(
            user=user,
            observation_id=f"{attempt.attempt_id}_{turn.turn_id}",
            defaults={
                "attempt": attempt,
                "turn": turn,
                "legacy_attempt_id": attempt.attempt_id,
                "legacy_turn_id": turn.turn_id,
                "question_id": f"{turn.part}:{hashlib.md5(turn.question.encode()).hexdigest()[:12]}",
                "part": turn.part,
                "question": turn.question,
                "transcript": turn_text,
                "overall_band": Decimal(str(score["overall_band"])),
                "fluency_coherence": Decimal(str(score["fluency_coherence"])),
                "lexical_resource": Decimal(str(score["lexical_resource"])),
                "grammar_range_accuracy": Decimal(str(score["grammatical_range"])),
                "pronunciation": None,
                "relevance": relevance,
                "weak_item_flag": bool(reasons),
                "weak_reasons": reasons,
                "model_version": f"django_{score.get('backend', 'unknown')}",
                "observed_at": timezone.now(),
                "next_due": timezone.now() + timezone.timedelta(days=1 if reasons else 14),
            },
        )

    return {"ok": True, "attempt": runtime, "report": report_payload(attempt)}


def regenerate_turn_transcript(user, attempt_id: str, turn_id: str) -> dict[str, Any]:
    """Re-transcribe audio and regenerate feedback for a turn.

    Since we don't have real Azure Speech integration, this fallback
    reuses existing transcript and regenerates feedback.

    Args:
        user: The authenticated user
        attempt_id: The attempt ID
        turn_id: The turn ID

    Returns:
        dict with 'ok', 'attempt', 'turn' keys

    Raises:
        SpeakingError: If validation fails or turn/audio not found
    """
    attempt = _load_attempt_for_user(user, attempt_id)
    turn = SpeakingTurn.objects.filter(attempt=attempt, turn_id=turn_id).first()
    if not turn:
        raise SpeakingError("Turn not found")
    if _turn_status(turn) != "completed":
        raise SpeakingError("Only completed turns can regenerate transcript.")

    if not turn.audio_path:
        raise SpeakingError("重新转写失败：这题没有可用录音文件。")

    audio_path = Path(settings.MEDIA_ROOT) / turn.audio_path
    if not audio_path.exists():
        raise SpeakingError("重新转写失败：这题没有可用录音文件。")

    server_asr = transcribe_turn_audio_with_server_asr(turn)
    if not server_asr.get("ok") or not str(server_asr.get("transcript") or "").strip():
        detail = str(server_asr.get("error") or server_asr.get("status") or "unknown error")
        raise SpeakingError(f"重新转写失败：服务端 ASR 没有返回可用文本。{detail}")

    transcript = str(server_asr["transcript"]).strip()

    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    metadata["server_asr"] = {key: value for key, value in server_asr.items() if key != "transcript"}
    metadata["transcript_status"] = "captured"
    metadata["transcript_source"] = str(server_asr.get("provider") or "volcengine_realtime_asr")
    metadata["transcript_markdown"] = _spoken_markdown(_clean_report_text(transcript))
    turn.transcript_raw = transcript
    turn.transcript_cleaned = _clean_report_text(transcript)
    turn.transcript_source = metadata["transcript_source"]
    feedback = build_turn_feedback(turn, attempt, {}, allow_codex=True)
    metadata.update(feedback)
    metadata["transcript_regenerated_at"] = timezone.now().isoformat()
    turn.metadata = metadata
    turn.save(update_fields=["transcript_raw", "transcript_cleaned", "transcript_source", "metadata"])

    attempt.updated_at = timezone.now()
    attempt.save(update_fields=["updated_at"])

    if hasattr(attempt, "report") and attempt.report:
        report = attempt.report
        payload = report.report_payload if isinstance(report.report_payload, dict) else {}
        turns_payload = payload.get("turns", [])
        for i, t in enumerate(turns_payload):
            if t.get("id") == turn_id:
                turns_payload[i]["transcript_status"] = "captured"
                turns_payload[i]["transcript_source"] = "fallback_retranscribe"
                turns_payload[i]["band7_version"] = metadata["band7_version"]
                turns_payload[i]["band7_markdown"] = metadata["band7_markdown"]
                turns_payload[i]["upgrade_notes"] = metadata["upgrade_notes"]
                turns_payload[i]["ai_coaching"] = metadata["ai_coaching"]
        report.report_payload = payload
        report.save(update_fields=["report_payload", "updated_at"])

    return {
        "ok": True,
        "attempt": _runtime_attempt_payload(attempt),
        "turn": _turn_payload(turn),
    }


def p3_fallback(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    plan = build_p3_plan(payload)
    follow_up = plan["follow_up"]
    if len(str(payload.get("prior_answer") or "").split()) > 40 and plan["backend"] == "fallback":
        follow_up = "What might be the opposite argument, and why might some people agree with it?"
        plan = {**plan, "follow_up": follow_up}
    return {
        "questions": plan["question_texts"],
        "structured_questions": plan["questions"],
        "follow_up": follow_up,
        "backend": plan["backend"],
        "status": plan["status"],
        **({"error": plan["error"]} if plan.get("error") else {}),
        "plan": plan,
    }


def p3_follow_up_fallback(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    prior_answer = str(payload.get("prior_answer") or "")
    current_question = str(payload.get("current_question") or payload.get("question") or payload.get("p3_question") or "")
    question_type = str(payload.get("question_type") or payload.get("type") or "")
    focus = _normalize_p3_focus(str(payload.get("p3_focus") or payload.get("focus") or ""))
    if current_question.strip() and prior_answer.strip():
        result = _generate_p3_dynamic_follow_up(
            current_question,
            question_type,
            prior_answer,
            focus,
            f"p3_follow_up_api_{hashlib.sha1((current_question + prior_answer).encode('utf-8')).hexdigest()[:16]}",
        )
        return {key: value for key, value in result.items() if value}

    follow_up = "Could you give a specific example to support that view?"
    if len(prior_answer.split()) > 40:
        follow_up = "What might be the opposite argument, and why might some people agree with it?"
    return {"follow_up": follow_up, "backend": "fallback", "status": "fallback"}


def _fixed_examiner_item_for_text(text: str) -> dict[str, str] | None:
    normalized = " ".join(str(text or "").strip().lower().split())
    for item in FIXED_EXAMINER_TTS_ITEMS:
        if normalized == " ".join(item["text"].lower().split()):
            return item
    return None


def _fixed_examiner_pending_state(item: dict[str, str]) -> dict[str, Any]:
    return {
        "provider": "volcengine",
        "status": "warming",
        "audio_url": None,
        "message": f"Fixed examiner audio is warming in the background: {item['key']}",
    }


def _fixed_examiner_fallback(cache_key: str) -> dict[str, Any]:
    return {
        "provider": "browser",
        "status": "fallback",
        "audio_url": None,
        "message": f"Fixed examiner audio is using browser fallback for now: {cache_key}",
    }


def _warm_fixed_examiner_tts_item(item: dict[str, str]) -> dict[str, Any]:
    return volcengine_tts(item["text"], role="examiner", cache_key=item["key"])


def _warm_fixed_examiner_tts_item_background(item: dict[str, str]) -> None:
    if _cached_tts_url("examiner", item["key"]):
        return
    threading.Thread(target=_warm_fixed_examiner_tts_item, args=(item,), daemon=True).start()


def _examiner_tts_text_hash(examiner_text: str) -> str:
    normalized = clean_report_text(examiner_text)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def _examiner_tts_cache_key(attempt_id: str, turn_id: str, examiner_text: str) -> str:
    return f"{attempt_id}_{turn_id}_examiner_{_examiner_tts_text_hash(examiner_text)}"


def _examiner_tts_identity(examiner_text: str, cache_key: str) -> dict[str, str]:
    return {
        "text_hash": _examiner_tts_text_hash(examiner_text),
        "cache_key": cache_key,
        # Exact text this audio was synthesized for. The client compares this
        # against the currently displayed question and refuses to play audio
        # that does not match — so a streamed AI follow-up can never be voiced
        # with a stale/template clip, regardless of any race or leftover payload.
        "tts_source_text": clean_report_text(examiner_text),
    }


def _with_examiner_tts_identity(tts: dict[str, Any], examiner_text: str, cache_key: str) -> dict[str, Any]:
    return {
        **(tts or {}),
        **_examiner_tts_identity(examiner_text, cache_key),
    }


def _examiner_tts_not_started(message: str = "Examiner text is not ready yet.") -> dict[str, Any]:
    return {
        "provider": "volcengine",
        "status": "not_started",
        "audio_url": None,
        "message": message,
    }


def _examiner_tts_matches_text(tts: dict[str, Any], examiner_text: str) -> bool:
    if not isinstance(tts, dict) or not examiner_text:
        return False
    fixed_item = _fixed_examiner_item_for_text(examiner_text)
    if fixed_item and tts.get("cache_key") == fixed_item["key"]:
        return True
    return tts.get("text_hash") == _examiner_tts_text_hash(examiner_text)


def ensure_examiner_tts(attempt_id: str, turn: dict[str, Any]) -> None:
    """Ensure turn has examiner TTS audio_url generated."""
    current = turn.get("examiner_tts") or {}
    examiner_text = str(turn.get("examiner_text") or turn.get("question") or "")
    if not clean_report_text(examiner_text):
        turn["examiner_tts"] = _examiner_tts_not_started()
        return
    if current.get("audio_url") or current.get("status") not in (None, "pending"):
        if _examiner_tts_matches_text(current, examiner_text):
            return
    try:
        fixed_item = _fixed_examiner_item_for_text(examiner_text)
        if fixed_item:
            cached_url = _cached_tts_url("examiner", fixed_item["key"])
            if cached_url:
                turn["examiner_tts"] = _with_examiner_tts_identity(
                    {
                        "provider": "volcengine",
                        "status": "cached",
                        "audio_url": cached_url,
                        "content_type": "audio/mpeg",
                    },
                    examiner_text,
                    fixed_item["key"],
                )
                return
            _warm_fixed_examiner_tts_item_background(fixed_item)
            turn["examiner_tts"] = _with_examiner_tts_identity(
                _fixed_examiner_pending_state(fixed_item),
                examiner_text,
                fixed_item["key"],
            )
            return
        cache_key = _examiner_tts_cache_key(attempt_id, str(turn["id"]), examiner_text)
        turn["examiner_tts"] = _with_examiner_tts_identity(
            volcengine_tts(
                examiner_text,
                role="examiner",
                cache_key=cache_key,
            ),
            examiner_text,
            cache_key,
        )
    except Exception as exc:
        cache_key = _examiner_tts_cache_key(attempt_id, str(turn["id"]), examiner_text)
        turn["examiner_tts"] = _with_examiner_tts_identity(
            {
                "provider": "volcengine",
                "status": "fallback",
                "audio_url": None,
                "message": f"Server TTS unavailable: {exc}",
            },
            examiner_text,
            cache_key,
        )


def _cached_examiner_tts_for_turn(attempt_id: str, turn_id: str, examiner_text: str) -> dict[str, Any] | None:
    fixed_item = _fixed_examiner_item_for_text(examiner_text)
    if fixed_item:
        cached_url = _cached_tts_url("examiner", fixed_item["key"])
        if cached_url:
            return _with_examiner_tts_identity(
                {
                    "provider": "volcengine",
                    "status": "cached",
                    "audio_url": cached_url,
                    "content_type": "audio/mpeg",
                },
                examiner_text,
                fixed_item["key"],
            )
    cache_key = _examiner_tts_cache_key(attempt_id, turn_id, examiner_text)
    cached_url = _cached_tts_url("examiner", cache_key)
    if cached_url:
        return _with_examiner_tts_identity(
            {
                "provider": "volcengine",
                "status": "cached",
                "audio_url": cached_url,
                "content_type": "audio/mpeg",
            },
            examiner_text,
            cache_key,
        )
    return None


def warm_fixed_examiner_tts() -> dict[str, Any]:
    """Ensure fixed examiner prompts are cached before the learner starts."""
    items = []
    for item in FIXED_EXAMINER_TTS_ITEMS:
        tts = _warm_fixed_examiner_tts_item(item)
        items.append({
            "key": item["key"],
            "status": tts.get("status"),
            "audio_url": tts.get("audio_url"),
            "provider": tts.get("provider"),
        })
    ready_urls = [item["audio_url"] for item in items if item.get("audio_url")]
    return {
        "items": items,
        "audio_urls": ready_urls,
        "ready_count": len(ready_urls),
    }


def _generate_remaining_examiner_tts_after_commit(attempt_id: str, turn_ids: list[str]) -> None:
    clean_turn_ids = [str(turn_id) for turn_id in turn_ids if turn_id]
    if not clean_turn_ids:
        return

    def start_background_tts() -> None:
        threading.Thread(
            target=_generate_remaining_examiner_tts,
            args=(str(attempt_id), clean_turn_ids),
            daemon=True,
        ).start()

    transaction.on_commit(start_background_tts)


def _generate_remaining_examiner_tts(attempt_id: str, turn_ids: list[str]) -> None:
    close_old_connections()
    try:
        attempt = SpeakingAttempt.objects.filter(attempt_id=attempt_id).first()
        if not attempt:
            return
        for db_turn in attempt.turns.filter(turn_id__in=turn_ids).order_by("sequence"):
            metadata = db_turn.metadata if isinstance(db_turn.metadata, dict) else {}
            current = metadata.get("examiner_tts") if isinstance(metadata.get("examiner_tts"), dict) else {}
            examiner_text = str(metadata.get("examiner_text") or db_turn.question)
            if not clean_report_text(examiner_text):
                metadata["examiner_tts"] = _examiner_tts_not_started()
                db_turn.metadata = metadata
                db_turn.save(update_fields=["metadata", "updated_at"])
                continue
            if (
                (current.get("audio_url") or current.get("status") not in (None, "pending"))
                and _examiner_tts_matches_text(current, examiner_text)
            ):
                continue
            cache_key = (
                (_fixed_examiner_item_for_text(examiner_text) or {}).get("key")
                or _examiner_tts_cache_key(attempt_id, db_turn.turn_id, examiner_text)
            )
            generating_state = {
                **(current or {}),
                "provider": "volcengine",
                "status": "generating",
                "audio_url": None,
                **_examiner_tts_identity(examiner_text, cache_key),
            }
            metadata["examiner_tts"] = generating_state
            db_turn.metadata = metadata
            db_turn.save(update_fields=["metadata", "updated_at"])
            turn_data = {
                "id": db_turn.turn_id,
                "question": db_turn.question,
                "examiner_text": examiner_text,
                "examiner_tts": {"provider": "volcengine", "status": "pending", "audio_url": None},
            }
            ensure_examiner_tts(attempt_id, turn_data)
            metadata["examiner_tts"] = turn_data.get("examiner_tts")
            db_turn.metadata = metadata
            db_turn.save(update_fields=["metadata"])
    except DatabaseError:
        return
    finally:
        close_old_connections()


def _is_stream_pending_follow_up_metadata(metadata: dict[str, Any]) -> bool:
    prompt = metadata.get("prompt") if isinstance(metadata.get("prompt"), dict) else {}
    return (
        prompt.get("role") == "follow_up"
        and (
            prompt.get("backend") == "stream_pending"
            or prompt.get("generation_status") == "pending"
        )
    )


def examiner_tts_status(user, attempt_id: str, turn_id: str) -> dict[str, Any]:
    """Return the latest examiner TTS state, generating it once when pending."""
    started = time.monotonic()
    attempt = _load_attempt_for_user(user, attempt_id)
    turn = _find_turn(attempt, turn_id)
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    current = metadata.get("examiner_tts") if isinstance(metadata.get("examiner_tts"), dict) else {}
    tts = current or {"provider": "volcengine", "status": "pending", "audio_url": None}
    if _is_stream_pending_follow_up_metadata(metadata):
        tts = {
            "provider": "volcengine",
            "status": "pending",
            "audio_url": None,
            "message": "Follow-up text is still generating; server TTS waits for the finalized question.",
        }
        metadata["examiner_tts"] = tts
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])
        return {
            "attempt_id": attempt.attempt_id,
            "turn_id": turn.turn_id,
            "examiner_tts": {
                **tts,
                "refresh_latency_ms": int((time.monotonic() - started) * 1000),
            },
        }
    examiner_text = str(metadata.get("examiner_text") or turn.question)
    if not clean_report_text(examiner_text):
        tts = _examiner_tts_not_started()
        metadata["examiner_tts"] = tts
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])
        return {
            "attempt_id": attempt.attempt_id,
            "turn_id": turn.turn_id,
            "examiner_tts": {
                **tts,
                "refresh_latency_ms": int((time.monotonic() - started) * 1000),
            },
        }
    if tts and not _examiner_tts_matches_text(tts, examiner_text):
        tts = {
            "provider": "volcengine",
            "status": "pending",
            "audio_url": None,
            **_examiner_tts_identity(
                examiner_text,
                (_fixed_examiner_item_for_text(examiner_text) or {}).get("key")
                or _examiner_tts_cache_key(attempt.attempt_id, turn.turn_id, examiner_text),
            ),
        }
        metadata["examiner_tts"] = tts
    cached_tts = _cached_examiner_tts_for_turn(attempt.attempt_id, turn.turn_id, examiner_text)
    if cached_tts:
        tts = cached_tts
        metadata["examiner_tts"] = tts
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])
    elif not tts.get("audio_url"):
        # Self-heal: regenerate whenever there is no audio yet, regardless of the
        # last status. Background warming can leave a run of turns in "fallback"
        # / "failed" / "generating" after a transient volcengine hiccup; without
        # this, those turns would stay permanently silent because the old guard
        # only retried "pending". ensure_examiner_tts is idempotent (returns the
        # cached clip if it already exists).
        turn_data = {
            "id": turn.turn_id,
            "question": turn.question,
            "examiner_text": examiner_text,
            "examiner_tts": {"provider": "volcengine", "status": "pending", "audio_url": None, **_examiner_tts_identity(examiner_text, (_fixed_examiner_item_for_text(examiner_text) or {}).get("key") or _examiner_tts_cache_key(attempt.attempt_id, turn.turn_id, examiner_text))},
        }
        ensure_examiner_tts(attempt.attempt_id, turn_data)
        tts = turn_data.get("examiner_tts") or tts
        metadata["examiner_tts"] = tts
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])
    return {
        "attempt_id": attempt.attempt_id,
        "turn_id": turn.turn_id,
        "examiner_tts": {
            **tts,
            "refresh_latency_ms": int((time.monotonic() - started) * 1000),
        },
    }


def latest_report(user) -> dict[str, Any]:
    attempts = (
        SpeakingAttempt.objects.filter(user=user, status=SpeakingAttempt.Status.SCORED)
        .select_related("report")
        .prefetch_related("turns")
        .order_by("-updated_at")
    )
    for attempt in attempts:
        if report_is_valid(attempt):
            return report_payload(attempt)
    return {"report": None}
