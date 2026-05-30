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

from apps.ai.http_provider import HttpApiProvider
from apps.ai.models import AITask
from apps.ai.services import create_ai_task, task_payload
from .audio_services import (
    MAX_AUDIO_BYTES,
    get_turn_audio_path,
    transcribe_turn_audio_with_server_asr,
    upload_turn_audio,
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
    delete_language_takeaway,
    delete_p2_corpus,
    get_question_bank,
    language_takeaway_library,
    language_takeaway_payload,
    local_takeaway_translate_text,
    normalize_question_bank_scope,
    p1_corpus_for_turns,
    p1_corpus_library,
    p1_question_id,
    p1_topic_label,
    p2_corpus_entry_payload,
    p2_corpus_extra,
    p2_corpus_for_selection,
    p2_corpus_library,
    p2_entry_id,
    prepared_corpus_for_turns,
    question_bank_sample,
    question_bank_summary,
    save_language_takeaway,
    save_p1_corpus,
    save_p2_corpus,
    save_writing_takeaway,
    takeaway_entry_id,
    writing_takeaway_library,
)
from .exceptions import SpeakingError
from .models import SpeakingAttempt, SpeakingReport, SpeakingTrainingObservation, SpeakingTurn
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
from .scoring_services import (
    band_cap,
    calibrate_realistic_score,
    cap_off_topic_score,
    clamp_band,
    development_markers,
    generic_template_score,
    heuristic_score,
    infer_primary_focus,
    is_template_like_answer,
    part_focus_text,
    prompt_relevance,
    repeated_phrases_from_texts,
    rounded_overall,
    score_prompt_for_part,
    short_question,
    simple_grammar_ratio,
    transcript_word_count,
    turn_habit_tags,
)
from .tts_services import (
    cached_tts_url as _cached_tts_url,
    stable_tts_audio_path,
    tts_audio_path,
    tts_fallback,
    volcengine_tts,
)
from .text_utils import acceptable_coaching_markdown, clean_band7_output, clean_coaching_markdown_text, clean_markdown_text, clean_report_text, concise_coaching_markdown, ensure_grammar_correction_bullet, infer_grammar_corrections, normalize_coaching_markdown, plain_spoken_text, spoken_markdown


# --- Codex Integration ---

CODEX_REASONING_EFFORT = "low"


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract first valid JSON object from text using balanced bracket scanning.

    Handles cases where:
    - Text contains multiple JSON objects
    - Text has Trellis/other content before/after JSON
    - JSON spans multiple lines

    Returns the first complete, parseable JSON object.
    """
    text = str(text or "")

    # Find the first '{' that starts a JSON object
    start = text.find("{")
    if start == -1:
        raise ValueError("model output did not contain a JSON object")

    # Use balanced bracket scanning to find the matching '}'
    depth = 0
    in_string = False
    escape_next = False

    for i, char in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                # Found the closing brace
                json_str = text[start:i + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    # Try finding next JSON object
                    remaining = text[i + 1:]
                    if "{" in remaining:
                        return extract_json_object(remaining)
                    raise ValueError(f"Invalid JSON object: {json_str[:100]}...")

    raise ValueError("model output contained unbalanced JSON braces")


def extract_json_object_with_keys(text: str, required_keys: set[str]) -> dict[str, Any]:
    """Extract the first JSON object containing all required top-level keys."""
    remaining = str(text or "")
    last_error: Exception | None = None
    while "{" in remaining:
        try:
            payload = extract_json_object(remaining)
        except ValueError as exc:
            last_error = exc
            break
        if required_keys.issubset(set(payload.keys())):
            return payload
        start = remaining.find("{")
        if start == -1:
            break
        depth = 0
        in_string = False
        escape_next = False
        end = -1
        for index, char in enumerate(remaining[start:], start):
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        if end == -1:
            break
        remaining = remaining[end + 1:]
    keys = ", ".join(sorted(required_keys))
    raise ValueError(f"model output did not contain a JSON object with required keys: {keys}") from last_error


def extract_codex_json_events(stdout: str) -> tuple[str, dict[str, Any] | None, bool]:
    """Parse codex CLI JSON events from stdout.

    Extracts the final model output text from:
    1. agent_message events (item.completed with type=agent_message)
    2. message.item events with text content
    3. Raw text events

    Skips Trellis injection text and other non-JSON prefixes.

    Returns:
        tuple of (text, usage, has_real_content)
        - text: extracted model output
        - usage: token usage dict or None
        - has_real_content: True if we found actual agent_message content,
          False if only event stream without model output
    """
    events: list[dict[str, Any]] = []
    for line in str(stdout or "").splitlines():
        stripped = line.strip()
        if not stripped or not stripped.startswith("{"):
            continue
        try:
            event = json.loads(stripped)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)

    usage = None
    final_text = ""
    has_real_content = False

    for event in events:
        # Track usage
        event_usage = event.get("usage")
        if isinstance(event_usage, dict):
            usage = event_usage
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]

        # Extract text from various event formats
        # Format 1: item.completed with agent_message (preferred)
        if event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                content_list = item.get("content", [])
                for content_item in content_list:
                    if isinstance(content_item, dict) and content_item.get("type") == "text":
                        text_value = content_item.get("text", "")
                        if text_value:
                            final_text = text_value
                            has_real_content = True

        # Format 2: message/item/response dict
        message = event.get("message") or event.get("item") or event.get("response")
        if isinstance(message, dict):
            content = message.get("content") or message.get("text")
            if isinstance(content, str) and content.strip():
                final_text = content
                has_real_content = True
            elif isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        value = part.get("text") or part.get("content")
                        if isinstance(value, str):
                            parts.append(value)
                    elif isinstance(part, str):
                        parts.append(part)
                if parts:
                    final_text = "\n".join(parts)
                    has_real_content = True

        # Format 3: direct content field
        elif isinstance(event.get("content"), str) and event["content"].strip():
            final_text = event["content"]
            has_real_content = True

    if not events:
        return str(stdout or ""), None, False
    return final_text or str(stdout or ""), usage, has_real_content


def run_codex(prompt: str, call_id: str, timeout: int = 45) -> tuple[str, dict[str, Any] | None]:
    """Call codex CLI and return output and usage.

    The `-` argument is required to make codex exec read from stdin.
    Without it, the model receives 0 tokens and outputs only thread/turn events.

    Raises RuntimeError if the model did not actually process the prompt
    (detected by 0 input tokens, empty output, or event stream without real content).
    """
    if os.environ.get("IELTS_WEB_DISABLE_CODEX") == "1":
        raise RuntimeError("codex disabled by IELTS_WEB_DISABLE_CODEX=1")

    codex = shutil.which("codex") or "/opt/homebrew/bin/codex"
    if not shutil.which(codex) and not Path(codex).exists():
        raise RuntimeError("codex CLI not found")

    config_args = ["-c", f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"']
    codex_cwd = str(Path(settings.BASE_DIR).parent)
    last_error: RuntimeError | None = None
    for _attempt in range(2):
        try:
            result = subprocess.run(
                [codex, "exec", "--json", *config_args, "-"],
                input=prompt,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout,
                check=True,
                cwd=codex_cwd,
            )
            output, usage, has_real_content = extract_codex_json_events(result.stdout)
        except subprocess.TimeoutExpired as exc:
            last_error = RuntimeError(f"codex timed out after {timeout}s for {call_id}")
            continue
        except Exception:
            result = subprocess.run(
                [codex, "exec", *config_args, "-"],
                input=prompt,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout,
                check=True,
                cwd=codex_cwd,
            )
            output, usage, has_real_content = result.stdout, None, bool(result.stdout.strip())

        if usage:
            input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
            if input_tokens == 0:
                last_error = RuntimeError(f"codex returned 0 input tokens for {call_id}: model did not process the prompt")
                continue

        if not output or not output.strip():
            last_error = RuntimeError(f"codex returned empty output for {call_id}")
            continue

        if not has_real_content:
            last_error = RuntimeError(f"codex returned only event stream without model output for {call_id}")
            continue

        return output, usage

    raise last_error or RuntimeError(f"codex returned no usable output for {call_id}")


# --- Overall Review ---


def overall_review_with_codex(
    profile: dict[str, Any],
    attempt: SpeakingAttempt,
    score: dict[str, Any],
    call_id: str,
) -> str:
    """Generate AI-powered personalized overall review using Codex."""
    band = score.get("overall_band")
    band_text = f"Band {band}" if isinstance(band, (int, float)) and not isinstance(band, bool) else "本次练习"
    part = attempt.part or attempt.mode or ""

    turns = list(attempt.turns.all().order_by("sequence")[:5])
    turns_summary = "\n".join(
        f"Q{i+1}: {t.question[:60]}... → {(t.transcript_cleaned or t.transcript_raw or '')[:80]}..."
        for i, t in enumerate(turns)
    )

    prompt = f"""请为这次 IELTS Speaking 练习生成中文总体点评与复盘重点。输出格式为 Markdown，包含两个部分。

要求：
- 第一部分「总体点评」：2-3 句话概括本次表现的核心问题和突破方向，结合用户画像给出针对性建议
- 第二部分「复盘重点」：3-5 个具体可执行的改进建议，用 bullet list 呈现
- 语气要具体、实用、有针对性，避免空泛评价
- 可以稍长，不要限制 AI 内容，让建议充分展开
- 必须结合学习画像进行个性化点评

本次成绩：{band_text}
练习部分：{part}
评分详情：
- Fluency & Coherence: {score.get('fluency_coherence', '—')}
- Lexical Resource: {score.get('lexical_resource', '—')}
- Grammatical Range: {score.get('grammatical_range', '—')}

部分转写样本：
{turns_summary}

学习画像：
{json.dumps(profile)}

请输出 Markdown 格式的总体点评与复盘重点。"""

    output, _ = run_codex(prompt, call_id)
    return clean_markdown_text(output)


def build_overall_review(
    profile: dict[str, Any],
    attempt: SpeakingAttempt,
    score: dict[str, Any],
    allow_codex: bool = True,
) -> dict[str, Any]:
    """Build overall review with Codex or fallback."""
    call_id = f"overall_review_{attempt.attempt_id}"
    codex_error = ""

    if allow_codex:
        try:
            markdown = overall_review_with_codex(profile, attempt, score, call_id)
            if markdown and len(markdown) > 50:
                return {
                    "comment": "",
                    "review_points": [],
                    "markdown": markdown,
                    "source": "codex_personalized",
                    "backend": "codex",
                    "status": "ready",
                }
        except Exception as exc:
            codex_error = str(exc)

    score_review = score.get("overall_review")
    if isinstance(score_review, dict):
        band = score.get("overall_band")
        band_text = f"Band {band}" if isinstance(band, (int, float)) and not isinstance(band, bool) else "本次练习"
        markdown = clean_markdown_text(str(score_review.get("markdown") or ""))
        comment = clean_report_text(str(score_review.get("comment") or ""))
        points = [clean_report_text(str(item)) for item in score_review.get("review_points") or []]
        points = [item for item in points if item]
        if markdown:
            return {
                "comment": comment,
                "review_points": points,
                "markdown": markdown,
                "source": score_review.get("source") or "codex_score",
                "backend": "codex" if str(score_review.get("source") or "codex_score").startswith("codex") else score.get("backend", "fallback"),
                "status": "ready",
            }
        if comment or points:
            if not comment:
                comment = f"{band_text} 的主要突破口：先处理最影响分数的说话习惯。"
            markdown_lines = [
                "### 总体点评",
                "",
                comment,
                "",
                "### 复盘重点",
                "",
                *[f"- {point}" for point in points],
            ]
            return {
                "comment": comment,
                "review_points": points,
                "markdown": "\n".join(markdown_lines),
                "source": "codex_score",
                "backend": "codex",
                "status": "ready",
            }

    band = score.get("overall_band")
    band_text = f"Band {band}" if isinstance(band, (int, float)) and not isinstance(band, bool) else "本次练习"
    focus = profile.get("primary_focus_text", "先把答案说完整、说具体。")
    fallback = {
        "comment": f"{band_text} 的主要突破口：{focus}",
        "review_points": ["Complete every answer", "Add reasons and examples", "Review weak short answers first"],
        "markdown": f"### 总体点评\n\n{band_text} 的主要突破口：{focus}\n\n### 复盘重点\n\n- Complete every answer\n- Add reasons and examples\n- Review weak short answers first",
        "source": "fallback",
        "backend": "fallback",
        "status": "fallback",
    }
    if codex_error:
        fallback["error"] = codex_error
    return fallback


def build_personalized_coaching(profile: dict[str, Any], attempt: SpeakingAttempt, score: dict[str, Any]) -> dict[str, Any]:
    """Build personalized coaching from profile and score."""
    tags = profile.get("habit_tags", [])
    evidence = profile.get("evidence", [])
    repeated = profile.get("repeated_phrases", [])

    headline = {
        "task_relevance": "先把题目答准，再去追求更高阶表达",
        "answer_development": "先补答案展开，不要只停在一句点到为止",
        "lexical_variety": "先把模板化表达换掉，改成更自然的说法",
        "abstract_discussion": "P3 先练讨论动作：原因、对比、让步和社会影响",
    }.get(str(profile.get("primary_focus") or ""), "先处理最影响分数的说话习惯")

    focus = profile.get("primary_focus_text", "先把答案说完整、说具体。")

    next_practice: list[str] = []
    if "short_answer" in tags or "limited_development" in tags:
        next_practice.append('每题都按"直接回答 + 原因 + 例子 + 一句收尾"练 2 轮。')
    if "template_language" in tags or repeated:
        next_practice.append("把高频模板词替换成你自己的经历说法，先录 1 次再回听。")
    if "off_topic" in tags:
        next_practice.append("每次开口前先复述题目里的关键词，确认回答没有跑题。")
    if "missing_concession" in tags:
        next_practice.append("每个 P3 主问题都补一句让步：However, some people may think... because...")
    if "limited_abstract_extension" in tags:
        next_practice.append("每个 P3 答案结尾补一句 wider impact：This could affect schools / families / society because...")
    if not next_practice:
        next_practice.extend([
            "先挑一题慢速录音，再对照 Band 7 版本改一遍。",
            "每次练习只修一个问题，避免一次想改太多。",
        ])

    return {
        "headline": headline,
        "focus": focus,
        "evidence": evidence[:5],
        "next_practice": next_practice[:3],
        "habit_tags": tags[:8],
    }


# --- Model Answer Helpers ---


def model_answer_constraints(part: str) -> str:
    """Get part-specific constraints for Band 7 model answer."""
    if part == "p1":
        return (
            "This is IELTS Speaking Part 1. Write a short natural answer, normally 1-3 sentences, maximum 3 sentences. "
            "Do not turn it into a long Part 2-style speech. One concise Markdown paragraph is preferred."
        )
    if part == "p2":
        return (
            "This is IELTS Speaking Part 2. Write a natural long-turn answer in Markdown paragraphs. "
            "Cover the cue-card points without copying the bullet list."
        )
    if part == "p3":
        return (
            "This is IELTS Speaking Part 3. Write a developed discussion answer, about 4-6 sentences, "
            "with an opinion, reasoning, and one concrete example or contrast."
        )
    return "Write an answer appropriate to the IELTS Speaking part shown by the questions."


def target_band_label(attempt: SpeakingAttempt | dict[str, Any]) -> str:
    """Get target band label from attempt."""
    if isinstance(attempt, SpeakingAttempt):
        metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
        value = metadata.get("target_band", 7.0)
    else:
        value = attempt.get("target_band", 7.0)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 7.0
    numeric = max(5.0, min(9.0, round(numeric * 2) / 2))
    return str(int(numeric)) if numeric.is_integer() else f"{numeric:.1f}"


def _model_band7_tts_cache_key(attempt_id: str, turn_id: str, band7_version: str) -> str:
    text_hash = hashlib.sha1(clean_report_text(band7_version).encode("utf-8")).hexdigest()[:12]
    return f"{attempt_id}_{turn_id}_band7_{text_hash}"


# --- Attempt Start ---

P1_TURN_COUNT = 10
P1_FOLLOW_UP_HTTP_TIMEOUT = 8
P1_FOLLOW_UP_CODEX_TIMEOUT = 15
P3_QUICK_FOLLOW_UP_CODEX_MODEL = "gpt-5.4-mini"
P3_QUICK_FOLLOW_UP_HTTP_TIMEOUT = 8
P3_QUICK_FOLLOW_UP_CODEX_TIMEOUT = 12
P3_MAIN_COUNT = 5
P3_TURN_COUNT = 10
P3_DRILL_COUNT = 3
DEFAULT_FULL_NAME = "LiHua"
DEFAULT_ENGLISH_NAME = "Jasper"

P3_FOCUS_OPTIONS: dict[str, dict[str, str]] = {
    "abstract_discussion": {
        "label": "抽象讨论",
        "description": "Move from personal experience to broader social ideas.",
    },
    "cause_effect": {
        "label": "原因影响",
        "description": "Explain reasons, consequences, and priorities.",
    },
    "comparison_concession": {
        "label": "对比让步",
        "description": "Compare groups and add a balanced opposing view.",
    },
    "future_trends": {
        "label": "未来趋势",
        "description": "Predict changes and explain why they may happen.",
    },
    "policy_society": {
        "label": "社会政策",
        "description": "Discuss responsibility, rules, and public impact.",
    },
}

P3_QUESTION_TYPES = [
    "opinion_justify",
    "change_trend",
    "future_prediction",
    "problem_solution",
    "policy_responsibility",
]

P3_TYPE_TARGET_MOVES: dict[str, list[str]] = {
    "opinion_justify": ["先给明确立场", "解释原因", "补一个反方角度"],
    "change_trend": ["过去/现在对比", "指出原因", "说明影响"],
    "future_prediction": ["给出预测", "补充条件", "长期影响"],
    "problem_solution": ["指出问题", "给具体例子", "给现实方案"],
    "policy_responsibility": ["点出相关群体", "讨论责任", "平衡观点"],
    "comparison_concession": ["比较不同群体", "承认反方合理性", "具体例子支撑"],
    "abstract_discussion": ["上升到一般现象", "界定问题", "社会层面影响"],
    "cause_effect": ["主因", "结果影响", "判断优先级"],
    "future_trends": ["未来变化", "变化驱动因素", "风险/好处"],
    "policy_society": ["公共角色", "个人角色", "权衡利弊"],
}

FIXED_EXAMINER_TTS_ITEMS = [
    {
        "key": "fixed_examiner_what_is_your_full_name",
        "text": "What is your full name?",
    },
    {
        "key": "fixed_examiner_do_you_work_or_do_you_study",
        "text": "Do you work or do you study?",
    },
    {
        "key": "fixed_examiner_p2_cue_card_instruction",
        "text": (
            "I'm going to give you a topic and I would like you to talk about it for one to two minutes. "
            "You have one minute to think about what you are going to say. "
            "You can make some notes if you wish."
        ),
    },
]


def _is_p1_work_study_identity_question(question: str) -> bool:
    normalized = "".join(c if c.isalnum() else " " for c in question.lower()).strip()
    phrases = [
        "do you work or are you",
        "are you a student or do you work",
        "do you work or study",
        "are you working or studying",
    ]
    return any(phrase in normalized for phrase in phrases)


def _cue_to_text(topic: dict[str, Any]) -> str:
    bullets = "\n".join(f"- {item}" for item in topic.get("bullets", []))
    return f"{topic.get('title', '')}\n\nYou should say:\n{bullets}\n\n{topic.get('rounding', '')}".strip()


def _cue_examiner_text() -> str:
    return FIXED_EXAMINER_TTS_ITEMS[2]["text"]


def _fallback_p3(theme: str, count: int = P3_MAIN_COUNT) -> dict[str, Any]:
    label = theme.replace("_", " ").strip() or "this topic"
    questions = [
        f"Why do people have different opinions about {label}?",
        f"How has {label} changed in your country in recent years?",
        f"Do you think {label} will become more important in the future?",
        f"What problems can {label} create for ordinary people?",
        f"How should governments or schools respond to changes in {label}?",
    ]
    follow_up = "Could you give a specific example to support that view?"
    return {"questions": questions[:count], "follow_up": follow_up}


def _normalize_p3_focus(value: str | None) -> str:
    focus = str(value or "").strip().lower()
    return focus if focus in P3_FOCUS_OPTIONS else "comparison_concession"


def _normalize_p3_intensity(value: str | None) -> str:
    intensity = str(value or "").strip().lower()
    return intensity if intensity in {"normal", "high", "drill"} else "high"


def _p3_source_type(payload: dict[str, Any], source_hint: str = "") -> str:
    source = str(payload.get("source") or payload.get("p3_source_type") or source_hint or "").strip().lower()
    if source in {"p2_report", "p2_corpus", "custom", "topic", "p2_answer"}:
        return source
    if str(payload.get("p2_corpus_entry_id") or "").strip():
        return "p2_corpus"
    if str(payload.get("prior_answer") or "").strip():
        return "p2_report"
    return "topic"


def _p3_question_type_for_index(index: int, focus: str) -> str:
    focus_to_type = {
        "abstract_discussion": "abstract_discussion",
        "cause_effect": "cause_effect",
        "comparison_concession": "comparison_concession",
        "future_trends": "future_trends",
        "policy_society": "policy_society",
    }
    if index == 0:
        return focus_to_type.get(focus, "comparison_concession")
    return P3_QUESTION_TYPES[(index - 1) % len(P3_QUESTION_TYPES)]


def _p3_follow_up_for_type(question_type: str) -> str:
    follow_ups = {
        "opinion_justify": "What might be the opposite view, and why might some people agree with it?",
        "change_trend": "Which change do you think has had the biggest impact, and why?",
        "future_prediction": "What could change this situation in the next ten years?",
        "problem_solution": "Which solution would be the most realistic for ordinary people?",
        "policy_responsibility": "Should the government be involved, or should individuals decide?",
        "comparison_concession": "How is this different for younger and older people?",
        "abstract_discussion": "Can you explain this at a wider social level rather than as a personal example?",
        "cause_effect": "Which factor matters most, and why?",
        "future_trends": "What might prevent that future change from happening?",
        "policy_society": "Who should take more responsibility for this issue?",
    }
    return follow_ups.get(question_type, "Could you give a specific example to support that view?")


def _dynamic_p3_follow_up(question_type: str, transcript: str, focus: str = "") -> str:
    words = re.findall(r"[A-Za-z']+", str(transcript or "").lower())
    word_count = len(words)
    text = " ".join(words)
    if word_count < 35:
        return "Could you develop that answer with one reason and one specific example?"
    if question_type in {"comparison_concession", "opinion_justify"}:
        if not any(token in text for token in ("however", "although", "whereas", "while", "on the other hand")):
            return "What might be the opposite view, and why might some people agree with it?"
        return "How is this different for younger and older people?"
    if question_type in {"cause_effect", "change_trend"}:
        if not any(token in text for token in ("because", "reason", "cause", "lead", "result", "therefore")):
            return "Which factor do you think matters most, and why?"
        return "What long-term effect could this have on ordinary people?"
    if question_type in {"future_prediction", "future_trends"}:
        return "What could change this situation in the next ten years?"
    if question_type in {"policy_responsibility", "policy_society", "problem_solution"}:
        return "Should the government be involved, or should individuals decide?"
    if focus == "abstract_discussion":
        return "Can you explain this at a wider social level rather than as a personal example?"
    return _p3_follow_up_for_type(question_type)


def _reasonable_p3_follow_up_question(value: str) -> bool:
    question = clean_report_text(value)
    lowered = question.lower()
    if not question.endswith("?") or question.count("?") != 1:
        return False
    if len(question) < 20 or len(question) > 180:
        return False
    if any(marker in lowered for marker in ("```", "{", "}", "as an ai", "here is", "candidate answer", "current question")):
        return False
    starters = (
        "what",
        "why",
        "how",
        "do",
        "does",
        "did",
        "is",
        "are",
        "should",
        "could",
        "would",
        "can",
        "which",
        "who",
        "when",
        "where",
        "in what",
        "to what extent",
    )
    return lowered.startswith(starters)


def _normalize_question_for_match(value: str) -> str:
    return re.sub(r"\s+", " ", clean_report_text(value).strip().lower())


def _extract_single_follow_up_question(output: str, rejected_questions: tuple[str, ...] = ()) -> str:
    text = str(output or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"```(?:[a-zA-Z0-9_-]+)?", "", text).replace("```", "")
    rejected = {_normalize_question_for_match(item) for item in rejected_questions if item}
    candidates: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line)
        line = re.sub(r"^\s*(?:follow[-_ ]?up|question|answer)\s*:\s*", "", line, flags=re.I).strip()
        line = line.strip("\"'“”‘’")
        if line:
            candidates.append(line)
    if not candidates and text:
        candidates.append(text.strip("\"'“”‘’"))
    for candidate in candidates:
        question = clean_report_text(candidate)
        if _normalize_question_for_match(question) in rejected:
            continue
        if _reasonable_p3_follow_up_question(question):
            return question
    raise RuntimeError("codex quick follow-up did not return a usable question")


def _quick_follow_up_prompt(current_question: str, candidate_answer: str, focus: str = "", question_type: str = "") -> str:
    question = clean_report_text(current_question)[:500]
    answer = clean_report_text(candidate_answer)[:2500]
    if not question:
        raise RuntimeError("missing current P3 question")
    if not answer:
        raise RuntimeError("missing candidate answer")
    return f"""You are an IELTS Speaking Part 3 examiner.
Write exactly one natural follow-up question based on the candidate's answer.
Output one line only. Do not include JSON, Markdown, labels, explanations, or quotes.
Do not repeat the current question. Make the follow-up more specific and deeper.

Current Part 3 question:
{question}

Question type: {question_type or "general"}
Training focus: {focus or "general IELTS Part 3 discussion"}

Candidate answer:
{answer}

One follow-up question:
"""


def quick_follow_up_http_runner(
    current_question: str,
    candidate_answer: str,
    focus: str = "",
    question_type: str = "",
) -> dict[str, Any]:
    """Generate one P3 follow-up through an OpenAI-compatible HTTP endpoint."""
    question = clean_report_text(current_question)[:500]
    prompt = _quick_follow_up_prompt(current_question, candidate_answer, focus=focus, question_type=question_type)
    provider = HttpApiProvider()
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
    """Generate one P3 follow-up through HTTP first, then Codex CLI."""
    http_error = ""
    try:
        return quick_follow_up_http_runner(
            current_question,
            candidate_answer,
            focus=focus,
            question_type=question_type,
        )
    except Exception as exc:  # noqa: BLE001 - provider chain must continue to Codex
        http_error = str(exc)

    try:
        follow_up = quick_follow_up_codex_runner(
            current_question,
            candidate_answer,
            focus=focus,
            question_type=question_type,
            timeout=timeout,
        )
        return {"follow_up": follow_up, "backend": "codex_quick", "status": "ready", "provider": "codex_cli"}
    except Exception as exc:  # noqa: BLE001 - caller will emit explicit fallback metadata
        raise RuntimeError(f"http_api: {http_error}; codex_quick: {exc}") from exc


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
) -> dict[str, str]:
    fallback = _dynamic_p3_follow_up(question_type, transcript, focus)
    try:
        result = quick_follow_up_runner_with_metadata(
            current_question,
            transcript,
            focus=focus,
            question_type=question_type,
            timeout=P3_QUICK_FOLLOW_UP_CODEX_TIMEOUT,
        )
        return {key: str(value) for key, value in result.items()}
    except Exception as exc:  # noqa: BLE001 - P3 follow-up must never block the flow
        return {
            "follow_up": fallback,
            "backend": "fallback",
            "status": "fallback",
            "error": f"{call_id}: {exc}" if call_id else str(exc),
        }


def _structured_p3_questions(questions: list[str], source_type: str, focus: str) -> list[dict[str, Any]]:
    structured: list[dict[str, Any]] = []
    for index, question in enumerate(questions):
        clean_question = clean_report_text(str(question))[:260]
        if not clean_question:
            continue
        question_type = _p3_question_type_for_index(index, focus)
        structured.append(
            {
                "id": f"q{index + 1}",
                "type": question_type,
                "question": clean_question,
                "target_moves": P3_TYPE_TARGET_MOVES.get(question_type, P3_TYPE_TARGET_MOVES["opinion_justify"]),
                "source": source_type,
            }
        )
    return structured


def build_p3_plan(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    theme = str(payload.get("theme") or payload.get("topic") or "society and daily life").replace("_", " ").strip()
    theme = theme or "society and daily life"
    focus = _normalize_p3_focus(str(payload.get("p3_focus") or payload.get("focus") or ""))
    intensity = _normalize_p3_intensity(str(payload.get("p3_intensity") or payload.get("intensity") or ""))
    question_count = P3_DRILL_COUNT if intensity == "drill" else P3_MAIN_COUNT
    prior_answer = clean_report_text(str(payload.get("prior_answer") or ""))[:4000]
    p3_follow_up_text = clean_markdown_text(str(payload.get("p3_follow_up_text") or ""))[:8000]
    provided_follow_ups = payload.get("p3_follow_ups")
    cue_questions = [
        clean_report_text(str(item))[:260]
        for item in provided_follow_ups
        if clean_report_text(str(item)) and ("?" in str(item) or "？" in str(item))
    ] if isinstance(provided_follow_ups, list) else []
    material_questions = _p3_questions_from_material(p3_follow_up_text, question_count)

    if cue_questions:
        raw_plan = {
            "questions": cue_questions[:question_count],
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
        )
        source_type = _p3_source_type(payload, "p2_report")
    else:
        raw_plan = {**_fallback_p3(theme, question_count), "backend": "fallback", "status": "fallback"}
        source_type = _p3_source_type(payload, "topic")

    questions = [str(q).strip() for q in raw_plan.get("questions", []) if str(q).strip()][:question_count]
    fallback_questions = _fallback_p3(theme, P3_MAIN_COUNT)["questions"]
    while len(questions) < question_count:
        questions.append(fallback_questions[len(questions) % len(fallback_questions)])

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
            "p2_corpus_entry_id": clean_report_text(str(payload.get("p2_corpus_entry_id") or "")),
            "season": clean_report_text(str(payload.get("season") or "")),
        },
        "questions": structured_questions,
        "question_texts": [item["question"] for item in structured_questions],
        "follow_up": follow_up,
        "backend": str(raw_plan.get("backend") or "fallback"),
        "status": str(raw_plan.get("status") or "fallback"),
        "question_count": len(structured_questions),
        **({"error": str(raw_plan.get("error"))} if raw_plan.get("error") else {}),
    }


def _p3_questions_from_material(value: str, count: int = P3_MAIN_COUNT) -> list[str]:
    questions: list[str] = []
    for line in clean_markdown_text(value).splitlines():
        item = re.sub(r"^\s*(?:[-*]|\d+[.)]|[Qq]\d+[:：])\s*", "", line).strip()
        if not item or ("?" not in item and "？" not in item):
            continue
        questions.append(item[:240])
        if len(questions) >= count:
            break
    return questions


def _generate_p3_from_p2_answer(theme: str, prior_answer: str, call_id: str) -> dict[str, Any]:
    fallback = _fallback_p3(theme, P3_MAIN_COUNT)
    answer = clean_report_text(prior_answer)[:4000]
    if not answer:
        return {**fallback, "backend": "fallback", "status": "fallback"}
    prompt = f"""Return JSON only with keys questions and follow_up.
questions must be an array of exactly 5 natural IELTS Speaking Part 3 examiner questions.
follow_up must be one concise examiner follow-up question.

Generate Part 3 questions based on this Part 2 response. The questions should extend the candidate's ideas into broader social discussion, comparison, reasons, consequences, and future trends.

Theme:
{theme}

Candidate Part 2 answer:
{answer}
"""
    try:
        output, _usage = run_codex(prompt, f"{call_id}_p3_from_p2", timeout=45)
        payload = extract_json_object_with_keys(output, {"questions", "follow_up"})
        questions = [clean_report_text(str(item)) for item in payload.get("questions", []) if clean_report_text(str(item))][:P3_MAIN_COUNT]
        if len(questions) < P3_MAIN_COUNT:
            raise RuntimeError("codex p3 generation returned too few questions")
        follow_up = clean_report_text(str(payload.get("follow_up") or fallback["follow_up"]))
        if not follow_up or "?" not in follow_up:
            follow_up = fallback["follow_up"]
        return {"questions": questions, "follow_up": follow_up, "backend": "codex", "status": "ready"}
    except Exception as exc:  # noqa: BLE001 - P3 generation must fall back cleanly
        return {**fallback, "backend": "fallback", "status": "fallback", "error": str(exc)}


def _timers_for_part(part: str) -> dict[str, Any]:
    defaults = {"prep_seconds": 3, "speak_seconds": 60}
    if part == "p1":
        return {"prep_seconds": 3, "speak_seconds": 35}
    if part == "p2":
        return {"prep_seconds": 60, "speak_seconds": 120}
    if part == "p3":
        return {"prep_seconds": 7, "speak_seconds": 75}
    return defaults


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
    ordinary_questions: list[dict[str, Any]] = []
    topic_names = list(topics)
    random.shuffle(topic_names)
    for topic in topic_names:
        if len(ordinary_questions) >= remaining_count:
            break
        topic_items = topics[topic][:]
        random.shuffle(topic_items)
        take = min(len(topic_items), remaining_count - len(ordinary_questions))
        ordinary_questions.extend(topic_items[:take])
    turn_items = uncounted_intro_items + countable_intro_items + ordinary_questions
    turns: list[dict[str, Any]] = []
    display_index = 0
    for index, item in enumerate(turn_items):
        counts_toward_total = bool(item.get("counts_toward_total", True))
        if counts_toward_total:
            display_index += 1
        turn = _create_turn(
            "p1",
            index,
            display_total or total,
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
            }
        )
    plan_questions = plan.get("questions", [])
    structured_questions: list[dict[str, Any]] = []
    if plan_questions and isinstance(plan_questions[0], dict):
        for index, item in enumerate(plan_questions):
            question = clean_report_text(str(item.get("question") or ""))
            if not question:
                continue
            question_type = str(item.get("type") or _p3_question_type_for_index(index, focus))
            structured_questions.append(
                {
                    "id": str(item.get("id") or f"q{index + 1}"),
                    "type": question_type,
                    "question": question,
                    "target_moves": item.get("target_moves") or P3_TYPE_TARGET_MOVES.get(question_type, []),
                    "source": str(item.get("source") or plan.get("source", {}).get("type") or source_type or "topic"),
                }
            )
    else:
        text_questions = [str(q).strip() for q in plan_questions if str(q).strip()]
        structured_questions = _structured_p3_questions(text_questions, source_type or "topic", focus)

    question_count = P3_DRILL_COUNT if intensity == "drill" else P3_MAIN_COUNT
    fallback_questions = _fallback_p3(theme, P3_MAIN_COUNT)["questions"]
    while len(structured_questions) < question_count:
        index = len(structured_questions)
        question_type = _p3_question_type_for_index(index, focus)
        structured_questions.append(
            {
                "id": f"q{index + 1}",
                "type": question_type,
                "question": fallback_questions[index % len(fallback_questions)],
                "target_moves": P3_TYPE_TARGET_MOVES.get(question_type, P3_TYPE_TARGET_MOVES["opinion_justify"]),
                "source": source_type or "topic",
            }
        )
    structured_questions = structured_questions[:question_count]

    use_follow_ups = intensity == "high"
    total = P3_TURN_COUNT if use_follow_ups else len(structured_questions)
    source = str(plan.get("source", {}).get("type") if isinstance(plan.get("source"), dict) else "")
    source = source or source_type or ("p2_answer" if prior_answer.strip() else "topic")
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
            },
        )
        turns.append(main_turn)
        if use_follow_ups:
            follow_up = _p3_follow_up_for_type(str(item.get("type") or ""))
            follow_turn = _create_turn(
                "p3",
                len(turns),
                total,
                str(follow_up),
                {
                    "theme": theme,
                    "question": str(follow_up),
                    "role": "follow_up",
                    "after_main": main_index + 1,
                    "source": source,
                    "question_type": item.get("type"),
                    "target_moves": ["respond directly", "add evidence", "extend the idea"],
                    "plan_question_id": f"{item.get('id', f'q{main_index + 1}')}-follow",
                },
            )
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
        p1_turns = _build_p1_turns(P1_TURN_COUNT, P1_TURN_COUNT + 1, question_bank_scope)
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
        turns = _build_p1_turns(P1_TURN_COUNT, question_bank_scope=question_bank_scope)
        return "p1", "Part 1 practice", turns, None, metadata
    if mode == "p2":
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

def _turn_status(turn: SpeakingTurn) -> str:
    status = str(turn.metadata.get("status") or "").strip()
    if status:
        return status
    if turn.transcript_cleaned or turn.transcript_raw:
        return "completed"
    if turn.audio_path:
        return "audio_uploaded"
    return "pending"


def _spoken_markdown(text: str) -> str:
    cleaned = _clean_report_text(text)
    return cleaned


def _turn_payload(turn: SpeakingTurn, total: int | None = None) -> dict[str, Any]:
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    prompt = metadata.get("prompt") if isinstance(metadata.get("prompt"), dict) else {"question": turn.question}
    cue_card = metadata.get("cue_card") if isinstance(metadata.get("cue_card"), dict) else None
    timers = metadata.get("timers") if isinstance(metadata.get("timers"), dict) else _timers_for_part(turn.part)
    audio = None
    if turn.audio_path:
        audio = {
            "path": str(Path(settings.MEDIA_ROOT) / turn.audio_path),
            "content_type": metadata.get("audio_content_type", "application/octet-stream"),
            "bytes": metadata.get("audio_bytes"),
            "duration_seconds": float(turn.duration_seconds) if turn.duration_seconds is not None else None,
            "url": f"/api/audio/{turn.attempt.attempt_id}/{turn.turn_id}/candidate",
        }
    return {
        "id": turn.turn_id,
        "part": turn.part,
        "index": max(0, int(turn.sequence or 0)),
        "total": total if total is not None else turn.attempt.turns.count(),
        "status": _turn_status(turn),
        "question": turn.question,
        "prompt": prompt,
        "cue_card": cue_card,
        "timers": timers,
        "examiner_text": metadata.get("examiner_text") or turn.question,
        "examiner_behavior": metadata.get("examiner_behavior") or "auto_play_question",
        "examiner_tts": metadata.get("examiner_tts") or {"provider": "volcengine", "status": "pending", "audio_url": None},
        "audio": audio,
        "transcript_raw": turn.transcript_raw,
        "transcript_cleaned": turn.transcript_cleaned,
        "display_transcript": metadata.get("display_transcript", ""),
        "display_transcript_markdown": metadata.get("display_transcript_markdown", ""),
        "transcript_markdown": metadata.get("transcript_markdown") or _spoken_markdown(turn.transcript_cleaned or turn.transcript_raw),
        "transcript_status": metadata.get("transcript_status") or ("captured" if (turn.transcript_cleaned or turn.transcript_raw) else "missing"),
        "duration_seconds": float(turn.duration_seconds) if turn.duration_seconds is not None else None,
        "band7_version": metadata.get("band7_version", ""),
        "band7_markdown": metadata.get("band7_markdown", metadata.get("band7_version", "")),
        "model_audio": metadata.get("model_audio"),
        "upgrade_notes": metadata.get("upgrade_notes", []),
        "ai_coaching": metadata.get("ai_coaching", ""),
        "target_band_version": metadata.get("target_band_version", metadata.get("band7_version", "")),
        "target_band_markdown": metadata.get("target_band_markdown", metadata.get("band7_markdown", metadata.get("band7_version", ""))),
        "target_band": metadata.get("target_band"),
        "feedback_generation_status": metadata.get("feedback_generation_status"),
        "feedback_generation_backend": metadata.get("feedback_generation_backend"),
        "feedback_generation_error": metadata.get("feedback_generation_error"),
        "band7_source": metadata.get("band7_source"),
        "ai_coaching_source": metadata.get("ai_coaching_source"),
        "audio_preprocessing_metrics": metadata.get("audio_preprocessing_metrics") if isinstance(metadata.get("audio_preprocessing_metrics"), dict) else None,
        "counts_toward_total": turn.counts_toward_total,
        "display_index": metadata.get("display_index"),
        "question_id": prompt.get("question_id") or p1_question_id(str(prompt.get("topic") or "general"), turn.question) if turn.part == "p1" else "",
        "topic": prompt.get("topic", ""),
        "p2_corpus_link": metadata.get("p2_corpus_link") if isinstance(metadata.get("p2_corpus_link"), dict) else None,
    }


def _runtime_attempt_payload(attempt: SpeakingAttempt) -> dict[str, Any]:
    turns = list(attempt.turns.all().order_by("sequence"))
    total = len(turns)
    turn_payloads = [_turn_payload(turn, total) for turn in turns]
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    current_turn = metadata.get("current_turn")
    if attempt.status == SpeakingAttempt.Status.STARTED and not current_turn:
        next_turn = next((turn for turn in turn_payloads if turn.get("status") != "completed"), None)
        current_turn = next_turn.get("id") if next_turn else None
    return {
        "id": attempt.attempt_id,
        "timestamp": attempt.created_at.isoformat(),
        "display_time": timezone.localtime(attempt.updated_at).strftime("%Y-%m-%d %H:%M"),
        "status": attempt.status,
        "user_id": str(attempt.user_id),
        "mode": attempt.mode,
        "part": attempt.part,
        "title": attempt.title,
        "question": turn_payloads[0]["question"] if turn_payloads else "",
        "cue_card": metadata.get("cue_card"),
        "turns": turn_payloads,
        "current_turn": current_turn,
        "candidate": attempt.english_name,
        "full_name": attempt.full_name,
        "english_name": attempt.english_name,
        "pronunciation": {"provider": "azure", "status": "pending"},
        "ielts_score": None,
        "feedback_summary": "",
        "criteria_feedback": {},
        "band7_version": "",
        "model_audio": None,
        "upgrade_notes": [],
        "ai_coaching": "",
        **{key: value for key, value in metadata.items() if key.startswith("p3_")},
    }


def _load_attempt_for_user(user, attempt_id: str) -> SpeakingAttempt:
    attempt = (
        SpeakingAttempt.objects.filter(user=user, attempt_id=str(attempt_id or "").strip())
        .prefetch_related("turns")
        .first()
    )
    if not attempt:
        raise SpeakingError("Attempt not found")
    return attempt


def _find_turn(attempt: SpeakingAttempt, turn_id: str) -> SpeakingTurn:
    turn = next((item for item in attempt.turns.all() if item.turn_id == str(turn_id or "").strip()), None)
    if not turn:
        raise SpeakingError("Turn not found")
    return turn


def _is_p1_work_study_turn(turn: SpeakingTurn) -> bool:
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    prompt = metadata.get("prompt") if isinstance(metadata.get("prompt"), dict) else {}
    return turn.part == "p1" and prompt.get("flow") == "intro" and prompt.get("role") == "work_study"


def _fallback_p1_identity_follow_up(answer: str) -> str:
    lowered = answer.lower()
    if any(word in lowered for word in ("intern", "internship", "company")):
        return "How does your internship connect with what you study?"
    if any(word in lowered for word in ("student", "study", "university", "major", "school")):
        return "What do you enjoy most about your studies?"
    if any(word in lowered for word in ("work", "job", "office", "engineer", "business")):
        return "What do you enjoy most about your work?"
    return "Can you tell me a little more about what you do now?"


def _extract_p1_identity_follow_up_output(output: str) -> str:
    try:
        payload = extract_json_object_with_keys(output, {"follow_up"})
        follow_up = clean_report_text(str(payload.get("follow_up") or ""))
    except Exception:  # noqa: BLE001 - HTTP-compatible endpoints may return plain text
        follow_up = _extract_single_follow_up_question(output)
    if not follow_up or len(follow_up) > 160 or "?" not in follow_up:
        raise RuntimeError("p1 follow-up provider did not return a usable question")
    return follow_up


def _p1_identity_follow_up_prompt(answer: str) -> str:
    return f"""Return JSON only with top-level key follow_up.
Do not repeat the input. Do not include Markdown, explanation, or code fences.

You are an IELTS Speaking Part 1 examiner. Write one natural follow-up question based on the candidate's previous answer.
Use the candidate's real identity details. Do not invent facts.
Keep it short, conversational, and suitable for Part 1.

Candidate answer:
{answer}
"""


def _generate_p1_identity_follow_up(answer: str, call_id: str) -> dict[str, str]:
    fallback = _fallback_p1_identity_follow_up(answer)
    if not answer.strip():
        return {
            "follow_up": fallback,
            "backend": "fallback",
            "status": "fallback",
            "error": "missing_candidate_answer",
        }
    prompt = _p1_identity_follow_up_prompt(answer)
    http_error = ""
    try:
        provider = HttpApiProvider()
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
            "latency_ms": str(int(result.elapsed_seconds * 1000)),
            "model": result.model,
        }
    except Exception as exc:  # noqa: BLE001 - provider chain must continue to Codex
        http_error = str(exc)

    try:
        output, _usage = run_codex(prompt, call_id, timeout=P1_FOLLOW_UP_CODEX_TIMEOUT)
        follow_up = _extract_p1_identity_follow_up_output(output)
        return {"follow_up": follow_up, "backend": "codex", "status": "ready"}
    except Exception as exc:
        return {
            "follow_up": fallback,
            "backend": "fallback",
            "status": "fallback",
            "error": f"http_api: {http_error}; codex: {exc}",
        }


def _insert_p1_identity_follow_up(attempt: SpeakingAttempt, completed_turn: SpeakingTurn, *, stream_pending: bool = False) -> SpeakingTurn | None:
    if not _is_p1_work_study_turn(completed_turn):
        return None
    transcript = (completed_turn.transcript_cleaned or completed_turn.transcript_raw or "").strip()
    existing = attempt.turns.filter(metadata__prompt__after_turn=completed_turn.turn_id).first()
    if existing:
        return existing

    result = (
        {
            "follow_up": _fallback_p1_identity_follow_up(transcript),
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
        follow_up,
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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        return default
    return numeric


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def _sanitize_audio_preprocessing_metrics(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not value.get("enabled"):
        return None
    total_frames = _safe_int(value.get("total_frames"))
    speech_frames = min(total_frames, _safe_int(value.get("speech_frames")))
    silence_frames = min(total_frames, _safe_int(value.get("silence_frames"), total_frames - speech_frames))
    if total_frames and speech_frames + silence_frames != total_frames:
        silence_frames = max(0, total_frames - speech_frames)
    speech_ratio = round(_safe_float(value.get("speech_ratio")), 6)
    silence_ratio = round(_safe_float(value.get("silence_ratio")), 6)
    if total_frames:
        speech_ratio = round(speech_frames / total_frames, 6)
        silence_ratio = round(silence_frames / total_frames, 6)
    return {
        "enabled": True,
        "analyzer": clean_report_text(str(value.get("analyzer") or ""))[:80],
        "fallback_analyzer": clean_report_text(str(value.get("fallback_analyzer") or ""))[:80],
        "fallback_reason": clean_report_text(str(value.get("fallback_reason") or ""))[:300],
        "total_frames": total_frames,
        "speech_frames": speech_frames,
        "silence_frames": silence_frames,
        "speech_ratio": speech_ratio,
        "silence_ratio": silence_ratio,
        "latest_rms": round(_safe_float(value.get("latest_rms")), 6),
        "latest_peak": round(_safe_float(value.get("latest_peak")), 6),
        "latest_speech": bool(value.get("latest_speech")),
        "sample_rate": _safe_int(value.get("sample_rate")),
        "frame_size": _safe_int(value.get("frame_size")),
        "started_at_ms": round(_safe_float(value.get("started_at_ms")), 3),
        "stopped_at_ms": round(_safe_float(value.get("stopped_at_ms")), 3),
        "last_error": clean_report_text(str(value.get("last_error") or ""))[:300],
    }


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
            result = (
                {
                    "follow_up": _dynamic_p3_follow_up(question_type, cleaned, focus),
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
                **({"generation_error": result["error"]} if result.get("error") else {}),
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
    }


def _sse_payload(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _p1_identity_stream_prompt(answer: str) -> str:
    return f"""You are an IELTS Speaking Part 1 examiner.
Write exactly one natural follow-up question based on the candidate's previous answer.
Use the candidate's real identity details. Do not invent facts.
Output one line only. Do not include JSON, Markdown, labels, explanations, or quotes.

Candidate answer:
{clean_report_text(answer)[:1800]}

One follow-up question:
"""


def _follow_up_stream_context(attempt: SpeakingAttempt, source_turn: SpeakingTurn) -> dict[str, Any]:
    source_metadata = source_turn.metadata if isinstance(source_turn.metadata, dict) else {}
    transcript = clean_report_text(source_turn.transcript_cleaned or source_turn.transcript_raw)
    if not transcript:
        raise SpeakingError("Completed turn transcript is required for streaming follow-up.")

    if _is_p1_work_study_turn(source_turn):
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
        return {
            "kind": "p3_dynamic",
            "target_turn": target,
            "prompt": _quick_follow_up_prompt(current_question, transcript, focus=focus, question_type=question_type),
            "fallback": _dynamic_p3_follow_up(question_type, transcript, focus),
            "rejected_questions": (current_question,),
            "extract": lambda output: _extract_single_follow_up_question(output, rejected_questions=(current_question,)),
            "system": "You are an IELTS Speaking Part 3 examiner. Return only one concise follow-up question.",
            "question_type": question_type,
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

    def generate() -> Iterator[str]:
        started = time.monotonic()
        parts: list[str] = []
        yield _sse_payload({"event": "start"})
        try:
            provider = HttpApiProvider()
            for token in provider.stream_tokens(
                [
                    {"role": "system", "content": context["system"]},
                    {"role": "user", "content": context["prompt"]},
                ],
                max_tokens=32,
                temperature=0.2,
                timeout_seconds=P3_QUICK_FOLLOW_UP_HTTP_TIMEOUT,
            ):
                parts.append(token)
                yield _sse_payload({"event": "chunk", "text": token})
            follow_up = context["extract"]("".join(parts))
            _save_streamed_follow_up(
                attempt,
                source_turn,
                target_turn,
                follow_up,
                backend="http_api_stream",
                status="ready",
                question_type=str(context.get("question_type") or ""),
            )
            yield _sse_payload({
                "event": "question_complete",
                "text": follow_up,
                "backend": "http_api_stream",
                "latency_ms": int((time.monotonic() - started) * 1000),
                "turn": _turn_payload(target_turn),
            })
        except Exception as exc:  # noqa: BLE001 - streaming endpoint must keep the practice flow usable
            fallback = str(context["fallback"])
            error = str(exc)
            _save_streamed_follow_up(
                attempt,
                source_turn,
                target_turn,
                fallback,
                backend="fallback",
                status="fallback",
                error=error,
                question_type=str(context.get("question_type") or ""),
            )
            yield _sse_payload({
                "event": "fallback",
                "text": fallback,
                "backend": "fallback",
                "error": clean_report_text(error)[:220],
                "turn": _turn_payload(target_turn),
            })
            yield _sse_payload({"event": "done"})
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


def _word_count(text: str) -> int:
    return len([word for word in text.replace("\n", " ").split(" ") if word.strip()])


def score_with_codex(transcript: str, question: str, part: str, call_id: str) -> dict[str, Any]:
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
    overall_review_prompt = f"""

同时生成 Overall Review & Practice Focus。
overall_review 必须是 object，包含：
- markdown: 中文 Markdown，包含两个部分「总体点评」和「复盘重点」
- comment: 简短中文概括
- review_points: 中文字符串数组

Overall Review 写法要求：
- markdown 必须直接写成旧版报告风格：以「### 总体点评」开头，然后写 2-3 段中文长点评；再写「### 复盘重点」，下面列出多条具体建议。
- 第一部分「总体点评」：不要只写一句短总结，要像真人老师复盘整场练习，概括核心问题、突破方向，并结合学习画像给出针对性建议。
- 第二部分「复盘重点」：不要限制为固定 3 条；根据本次表现列出足够具体、可执行的建议，每条可以包含解释和示范句。
- 语气要具体、实用、有针对性，避免空泛评价
- 可以稍长，不要限制内容，让建议充分展开
- 必须结合学习画像进行个性化点评
- 不要输出类似“回答基本相关，但展开偏短”这种过短 fallback 文案
- 如果练习部分是 p3，必须围绕 Part 3 的抽象讨论能力复盘：观点是否明确、原因链是否完整、是否有对比/让步、是否能从个人例子上升到社会层面、追问是否承接新角度；复盘重点要给出可直接练的 discussion move 和示范句。

本次成绩会由你在同一个 JSON 中给出。
练习部分：{part}
学习画像：
{json.dumps(profile, ensure_ascii=False)}
"""

    full_prompt = (
        system_prompt
        + "\n\nReturn JSON only. The top-level object must contain numeric keys fluency_coherence, lexical_resource, "
        "grammatical_range, overall_band, string key feedback, and overall_review object "
        "with string keys markdown and comment plus array key review_points. Do not score pronunciation or reference pronunciation. "
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
        "Write a detailed Simplified Chinese overall_review.markdown in the old report style: ### 总体点评 with 2-3 substantial paragraphs, then ### 复盘重点 with concrete review points. "
        "Do not repeat the input. Do not include Markdown, explanation, or code fences. Do not score pronunciation from text. "
        + score_prompt_for_part(part)
        + "\n\nQuestion or cue card:\n"
        + (question.strip() or "(not provided)")
        + "\n\nTranscript:\n"
        + transcript
        + "\n"
    )

    last_error: Exception | None = None
    for index, prompt in enumerate((full_prompt, compact_prompt), start=1):
        try:
            output, usage = run_codex(prompt, f"{call_id}_p{index}", timeout=180)
            payload = extract_json_object_with_keys(
                output,
                {"fluency_coherence", "lexical_resource", "grammatical_range"},
            )
            break
        except Exception as exc:
            last_error = exc
    else:
        raise RuntimeError(str(last_error or "codex scoring failed"))

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
        "backend": "codex",
        "generation_backend": "codex",
        "generation_status": "ready",
    }

    overall_review = payload.get("overall_review")
    if isinstance(overall_review, dict):
        markdown = clean_markdown_text(str(overall_review.get("markdown") or ""))
        comment = clean_report_text(str(overall_review.get("comment") or ""))
        points = [clean_report_text(str(item)) for item in overall_review.get("review_points") or []]
        points = [item for item in points if item][:4]
        if markdown or comment or points:
            result_payload["overall_review"] = {
                "comment": comment,
                "review_points": points,
                "markdown": markdown,
                "source": "codex_score",
            }

    if usage:
        result_payload["billing_usage"] = usage

    # Apply calibration and off-topic detection
    return cap_off_topic_score(calibrate_realistic_score(result_payload, question, transcript, part), question, transcript)


# --- Additional Missing Functions ---


def attempt_part(attempt: SpeakingAttempt) -> str:
    """Get the part/mode of an attempt."""
    mode = str(attempt.mode or attempt.part or "").lower()
    if mode in {"p1", "p2", "p3", "mock"}:
        return mode
    turns = list(attempt.turns.all())
    parts = {str(t.part or "").lower() for t in turns if t.part}
    if len(parts) == 1:
        return next(iter(parts))
    return ""


def target_band(attempt: SpeakingAttempt) -> float:
    """Get target band from attempt metadata."""
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    try:
        value = float(metadata.get("target_band", 7.0))
    except (TypeError, ValueError):
        value = 7.0
    return max(5.0, min(9.0, round(value * 2) / 2))


def score_for_part(turns: list[SpeakingTurn], part: str, fallback_score: dict[str, Any]) -> dict[str, Any]:
    """Calculate score for a specific part."""
    part_turns = [turn for turn in turns if turn.part == part]
    transcript = "\n".join(turn.transcript_cleaned or turn.transcript_raw or "" for turn in part_turns)
    if not part_turns:
        return {}
    part_score = heuristic_score(
        transcript,
        f"{part.upper()} section estimate",
        "\n".join(turn.question for turn in part_turns),
        part,
    )
    part_score["overall_band"] = rounded_overall(part_score)
    part_score = calibrate_realistic_score(
        part_score,
        "\n".join(turn.question for turn in part_turns),
        transcript,
        part,
    )
    return {
        "part": part,
        "turn_count": len(part_turns),
        "band": part_score.get("overall_band", fallback_score.get("overall_band")),
        "fluency_coherence": part_score.get("fluency_coherence", fallback_score.get("fluency_coherence")),
        "lexical_resource": part_score.get("lexical_resource", fallback_score.get("lexical_resource")),
        "grammatical_range": part_score.get("grammatical_range", fallback_score.get("grammatical_range")),
    }


def build_part_scores(attempt: SpeakingAttempt, score: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build scores for each part in the attempt."""
    turns = list(attempt.turns.all())
    return {
        part: score_for_part(turns, part, score)
        for part in ("p1", "p2", "p3")
        if any(turn.part == part for turn in turns)
    }


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
    }


def build_turn_band7_with_codex(question: str, transcript: str, part: str, call_id: str) -> str:
    """Generate Band 7 model answer using Codex CLI."""
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

    output, _ = run_codex(prompt, call_id)
    return clean_band7_output(output)


def build_ai_coaching_with_codex(question: str, transcript: str, band7: str, part: str, call_id: str, profile: dict[str, Any] | None = None) -> str:
    """Generate natural AI coaching using Codex CLI."""
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

Question:
{question}

Candidate transcript:
{transcript or '(missing)'}

Band 7 spoken version:
{band7}

Learning profile:
{json.dumps(profile or {})}
"""
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


def turn_feedback_with_codex(question: str, transcript: str, part: str, target: str, profile: dict[str, Any] | None, call_id: str, requires_ai_coaching: bool = True) -> dict[str, str]:
    """Generate Band 7 and AI coaching together using Codex CLI.

    This combined generation ensures the Band 7 and coaching are consistent.

    Raises RuntimeError if the output is invalid or missing required fields.
    """
    prompt = f"""Return JSON only. The top-level object must contain keys display_transcript, band7_version and ai_coaching.
Do not repeat the input. Do not include Markdown outside string values, explanation, or code fences.

Task:
- First produce display_transcript: lightly format the ASR transcript for display only.
- Then write one natural IELTS Speaking Band {target} spoken version based on display_transcript.
- Write Chinese Markdown coaching for this same turn only if requires_ai_coaching is true.
- Answer the exact examiner question directly and preserve the candidate's likely intent.
- Reuse the candidate's concrete idea when it is relevant; improve cohesion, vocabulary, and grammar.
- Do not include the original question, cue-card bullets, titles, labels, code fences, or logs.
- Base band7_version and ai_coaching on display_transcript, not noisy candidate transcript.
- display_transcript is only for noise cleanup and formatting.
- Do not change the candidate's original meaning, answer direction, or level of detail when producing display_transcript.
- Only fix obvious ASR noise: spacing, capitalization, punctuation, repeated fragments, and broken sentence boundaries.
- If a word is uncertain, keep the original ASR word instead of guessing a better one.
- Do not upgrade display_transcript into a better answer.
- Do not mention or correct words that are absent from display_transcript.
- ai_coaching must comment on the answer as represented by display_transcript.
- Do not mention raw ASR noise or words removed during cleanup in coaching.
- Do not comment on capitalization, punctuation, written formatting, display formatting, ASR noise, or browser transcription artifacts.
- Bad example: if display_transcript says "at university", do not say the raw phrase "at University" should not be capitalized.
- If requires_ai_coaching is false, set ai_coaching to an empty string.

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
    compact_prompt = f"""Return JSON only. The top-level object must contain keys display_transcript, band7_version and ai_coaching.
Do not repeat the input. Do not include Markdown outside string values, explanation, or code fences.

First lightly format the ASR transcript as display_transcript, then write a natural IELTS Speaking Band {target} answer for the question.
If requires_ai_coaching is true, write Chinese coaching based only on display_transcript.
If requires_ai_coaching is false, set ai_coaching to an empty string.
In band7_version, use Markdown bold on 2-5 reusable upgraded phrases, not whole sentences.
The coaching format is up to you, but when coaching is required it must include a final section named "语法错误纠正：".
Do not use fixed labels or templates. Use the candidate's real meaning and do not invent facts.
display_transcript is only for noise cleanup and formatting.
Do not change the candidate's original meaning, answer direction, or level of detail when producing display_transcript.
Only fix obvious ASR noise: spacing, capitalization, punctuation, repeated fragments, and broken sentence boundaries.
If a word is uncertain, keep the original ASR word instead of guessing a better one.
Do not upgrade display_transcript into a better answer.
Do not mention or correct words that are absent from display_transcript.
Do not comment on capitalization, punctuation, written formatting, display formatting, ASR noise, or browser transcription artifacts.
Bad example: if display_transcript says "at university", do not say the raw phrase "at University" should not be capitalized.

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
            output, usage = run_codex(candidate_prompt, f"{call_id}_p{index}")
            payload = extract_json_object_with_keys(output, {"display_transcript", "band7_version", "ai_coaching"})
            break
        except Exception as exc:
            last_error = exc
    else:
        raise RuntimeError(str(last_error or "codex turn feedback failed"))

    # Validate required fields exist
    band7_raw = payload.get("band7_version")
    coaching_raw = payload.get("ai_coaching")

    if not band7_raw or not str(band7_raw).strip():
        raise RuntimeError(f"codex turn feedback missing band7_version for {call_id}")

    if requires_ai_coaching and (not coaching_raw or not str(coaching_raw).strip()):
        raise RuntimeError(f"codex turn feedback missing ai_coaching for {call_id}")

    display_transcript = clean_report_text(str(payload.get("display_transcript") or ""))
    band7 = clean_band7_output(str(band7_raw))
    coaching = clean_coaching_markdown_text(str(coaching_raw))
    if not clean_report_text(band7):
        raise RuntimeError(f"codex turn feedback returned empty band7_version for {call_id}")

    if requires_ai_coaching:
        coaching = ensure_grammar_correction_bullet(coaching, display_transcript or transcript)
    if requires_ai_coaching and not acceptable_coaching_markdown(coaching):
        raise RuntimeError("codex turn feedback did not include usable coaching with grammar correction")

    return {"display_transcript": display_transcript, "band7_version": band7, "ai_coaching": coaching if requires_ai_coaching else "", "usage": usage}


def turn_feedback_batch_with_codex(
    turns: list[SpeakingTurn],
    attempt: SpeakingAttempt,
    target: str,
    profile: dict[str, Any] | None,
    call_id: str,
    prepared_corpus_by_turn: dict[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    """Generate Band 7 answers and coaching for all completed turns in one Codex call."""
    items: list[dict[str, str]] = []
    for turn in turns:
        if is_p1_name_intro_turn(turn):
            continue
        transcript = (turn.transcript_cleaned or turn.transcript_raw or "").strip()
        if not transcript:
            continue
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
Each item must contain string keys turn_id, display_transcript, band7_version, and ai_coaching.

Task:
- For each turn, first produce display_transcript: lightly format the ASR transcript for display only.
- Then write one natural IELTS Speaking Band {target} spoken version based on that display_transcript.
- Preserve the candidate's likely meaning and answer the exact examiner question directly.
- Write Chinese coaching only when requires_ai_coaching is "yes".
- Do not include the original question, cue-card bullets, titles, labels, code fences, or logs.
- If requires_ai_coaching is "no", set ai_coaching to an empty string.

prepared_corpus usage:
- Some P2 turns include prepared_corpus from the learner's P2 串题素材库 only when the learner explicitly linked a material during preparation.
- P1 语料库 content is not passed into this prompt.
- If prepared_corpus is present and relevant to the cue card, use it as preferred personal material for the Band 7 version and coaching.
- If prepared_corpus is present, ai_coaching must include concrete guidance on how to use that material as a reusable 串题素材: which parts fit this cue card, what to keep, what to adjust, and how to adapt it for nearby P2 topics.
- Do not copy it blindly, do not invent facts beyond it, and do not let it override the candidate_transcript when they clearly answered differently this time.

display_transcript constraints:
- Keep the candidate's original wording and expression. Do not upgrade vocabulary, grammar, ideas, or logic.
- Only fix obvious ASR formatting problems: spacing, capitalization, repeated filler fragments, and sentence breaks.
- If a word is uncertain, keep the ASR word instead of guessing a better answer.
- Do not turn it into a Band 7 answer.

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
    output, usage = run_codex(prompt, call_id, timeout=180)
    payload = extract_json_object_with_keys(output, {"turns"})
    raw_turns = payload.get("turns")
    if not isinstance(raw_turns, list):
        raise RuntimeError(f"codex batch turn feedback missing turns for {call_id}")

    by_id: dict[str, dict[str, str]] = {}
    for item in raw_turns:
        if not isinstance(item, dict):
            continue
        turn_id = clean_report_text(str(item.get("turn_id") or ""))
        display_transcript = clean_report_text(str(item.get("display_transcript") or ""))
        band7 = clean_band7_output(str(item.get("band7_version") or ""))
        coaching = clean_coaching_markdown_text(str(item.get("ai_coaching") or ""))
        source_item = next((source for source in items if source["turn_id"] == turn_id), {})
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
            "band7_version": band7,
            "ai_coaching": coaching if requires_ai_coaching else "",
            "usage": usage or {},
        }
    if len(by_id) != len(items):
        missing = [item["turn_id"] for item in items if item["turn_id"] not in by_id]
        raise RuntimeError(f"codex batch turn feedback missing usable output for turns: {', '.join(missing)}")
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


def _criteria_feedback(score: dict[str, Any], transcript: str) -> dict[str, Any]:
    """Build criteria feedback based on score and transcript.

    This is the complete version from old server with band-based advice.
    """
    def band_advice(band: float | None, low: str, mid: str, high: str) -> str:
        if band is None:
            return low
        if band < 5.5:
            return low
        if band < 7.0:
            return mid
        return high

    standards = {
        "fluency and coherence": (
            "Assesses whether answers are developed, logically connected, and spoken without excessive hesitation or repetition."
        ),
        "lexical resource": (
            "Assesses range and precision of vocabulary, including natural collocations and the ability to paraphrase."
        ),
        "grammar": (
            "Assesses sentence control, tense accuracy, clause variety, and whether errors reduce clarity."
        ),
    }

    fc_band = score.get("fluency_coherence", 5.0)
    lr_band = score.get("lexical_resource", 5.0)
    gr_band = score.get("grammatical_range", 5.0)

    advice = {
        "fluency and coherence": band_advice(
            fc_band,
            "Build each answer with a direct point, one reason, and one concrete example before closing.",
            "Add contrast, consequence, and smoother linking so ideas feel connected rather than listed.",
            "Refine pacing and use clearer signposting when moving from reason to example to conclusion.",
        ),
        "lexical resource": band_advice(
            lr_band,
            "Replace repeated basic words with topic-specific phrases copied from your Band 7 version.",
            "Paraphrase the question and add two or three natural collocations for the topic.",
            "Use more precise topic vocabulary while keeping the answer conversational.",
        ),
        "grammar": band_advice(
            gr_band,
            "Prioritise complete simple sentences first, then add one because/when/although clause.",
            "Vary sentence openings and check tense consistency when giving examples.",
            "Reduce small accuracy slips in longer complex sentences.",
        ),
    }

    words = len(re.findall(r"[A-Za-z']+", transcript))
    sample_note = (
        "The sample is short or incomplete, so the advice focuses on building enough answer content."
        if words < 20
        else "The advice is a static IELTS reference for the current band range, not live AI-generated feedback."
    )

    return {
        "fluency_coherence": {
            "band": fc_band,
            "standard": standards["fluency and coherence"],
            "focus": sample_note,
            "advice": advice["fluency and coherence"],
            "strengths": [standards["fluency and coherence"]],
            "problems": [sample_note],
            "suggestion": advice["fluency and coherence"],
        },
        "lexical_resource": {
            "band": lr_band,
            "standard": standards["lexical resource"],
            "focus": sample_note,
            "advice": advice["lexical resource"],
            "strengths": [standards["lexical resource"]],
            "problems": [sample_note],
            "suggestion": advice["lexical resource"],
        },
        "grammatical_range_accuracy": {
            "band": gr_band,
            "standard": standards["grammar"],
            "focus": sample_note,
            "advice": advice["grammar"],
            "strengths": [standards["grammar"]],
            "problems": [sample_note],
            "suggestion": advice["grammar"],
        },
    }


# --- P1 Name/Identity Helpers ---


DEFAULT_FULL_NAME = "Li Hua"
DEFAULT_ENGLISH_NAME = "Jasper"


def is_p1_name_intro_turn(turn: dict[str, Any] | SpeakingTurn) -> bool:
    """Check if turn is a P1 name introduction."""
    if isinstance(turn, SpeakingTurn):
        prompt = turn.metadata.get("prompt", {}) if isinstance(turn.metadata, dict) else {}
        return turn.part == "p1" and prompt.get("flow") == "intro" and prompt.get("role") == "name"
    prompt = turn.get("prompt") or {}
    return turn.get("part") == "p1" and prompt.get("flow") == "intro" and prompt.get("role") == "name"


def is_p1_work_study_intro_turn(turn: dict[str, Any] | SpeakingTurn) -> bool:
    """Check if turn is the fixed P1 work/study identity question."""
    if isinstance(turn, SpeakingTurn):
        prompt = turn.metadata.get("prompt", {}) if isinstance(turn.metadata, dict) else {}
        return turn.part == "p1" and prompt.get("flow") == "intro" and prompt.get("role") == "work_study"
    prompt = turn.get("prompt") or {}
    return turn.get("part") == "p1" and prompt.get("flow") == "intro" and prompt.get("role") == "work_study"


def turn_needs_ai_coaching(turn: SpeakingTurn) -> bool:
    return not (is_p1_name_intro_turn(turn) or is_p1_work_study_intro_turn(turn))


def turn_counts_for_scoring(turn: SpeakingTurn) -> bool:
    return not is_p1_name_intro_turn(turn)


def turn_display_transcript(turn: SpeakingTurn) -> str:
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    return (metadata.get("display_transcript") or turn.transcript_cleaned or turn.transcript_raw or "").strip()


def p1_name_answer(full_name: str | None, english_name: str | None) -> str:
    """Generate P1 name answer from profile."""
    full = clean_report_text(str(full_name or DEFAULT_FULL_NAME)) or DEFAULT_FULL_NAME
    english = clean_report_text(str(english_name or DEFAULT_ENGLISH_NAME)) or DEFAULT_ENGLISH_NAME
    if full.lower() == english.lower():
        return f"My full name is {full}."
    return f"My full name is {full}, but you can call me {english}."


def _p1_question_only_answer(question: str, answer_lower: str = "") -> str:
    """Minimal P1 identity fallback for work/study only.

    General Band 7 answers should come from Codex. This helper exists only to
    avoid inventing the wrong identity if a work/study fallback is explicitly
    requested by older paths or tests.
    """
    lowered = question.lower()
    if ("work" in lowered or "study" in lowered or "student" in lowered) and "prefer" not in lowered:
        has_student = any(w in answer_lower for w in ("student", "study", "studying", "university", "school", "major"))
        has_internship = any(w in answer_lower for w in ("intern", "internship", "company"))
        has_software = any(w in answer_lower for w in ("software", "computer", "code", "coding", "engineering"))
        if has_student and has_internship:
            major = "software engineering" if has_software else "my major"
            return (
                f"I'm a university student majoring in {major}, and I'm also doing an internship at a company. "
                "I enjoy it because I can connect what I learn in class with real practical work."
            )
        if has_student:
            major = "software engineering" if has_software else "my major"
            return f"I'm a university student majoring in {major}. I enjoy it because I can learn practical skills and solve real problems."
        if any(w in answer_lower for w in ("work", "job", "office", "engineer", "business")):
            return "I work at the moment. I enjoy it because the work is practical and I get to solve real problems every day."
        return "I'm a university student at the moment, majoring in computer science. I chose it because I enjoy building things and solving practical problems."
    topic_hint = "this topic"
    if "hobby" in lowered or "free time" in lowered or "relax" in lowered:
        topic_hint = "hobbies and free time"
    elif "holiday" in lowered or "vacation" in lowered:
        topic_hint = "holidays"
    elif "country" in lowered:
        topic_hint = "the situation in my country"
    return (
        f"Yes, I think {topic_hint} is quite important in daily life. "
        "For me, it is not only about enjoyment, but also about having a healthy balance after studying or working. "
        "For example, when I have some spare time, I prefer doing something simple and relaxing, like taking a walk, listening to music, or focusing on a personal interest. "
        "It helps me clear my mind and return to my routine with more energy."
    )


def build_turn_band7_fallback(
    question: str,
    part: str,
    transcript: str = "",
    full_name: str | None = None,
    english_name: str | None = None,
    turn_metadata: dict[str, Any] | None = None,
) -> str:
    """Generate a rule-based Band 7 answer. Never quotes raw transcript — only uses it to detect intent direction."""
    question_clean = clean_report_text(question) or "this question"
    answer_lower = clean_report_text(transcript).lower() if transcript else ""
    turn_metadata = turn_metadata or {}

    if part == "p1":
        # Check if it's a name intro turn
        if turn_metadata.get("prompt", {}).get("flow") == "intro" and turn_metadata.get("prompt", {}).get("role") == "name":
            return p1_name_answer(full_name, english_name)
        return _p1_question_only_answer(question_clean, answer_lower)

    if part == "p2":
        cue = turn_metadata.get("cue_card") if isinstance(turn_metadata.get("cue_card"), dict) else {}
        cue_title = clean_report_text(str(cue.get("title") or question_clean))
        return (
            f"I would like to talk about {cue_title.lower()}. It is something I remember clearly because it was connected with a real moment in my life, "
            "not just a general idea. At first, I did not pay much attention to it, but later I realized that it affected the way I handled similar situations. "
            "What made it meaningful was the combination of the people involved, the pressure at the time, and the result afterwards. "
            "For example, I had to make a practical decision instead of waiting for everything to be perfect, and that taught me to be more organized and patient. "
            "Overall, I would say this experience was valuable because it gave me a clearer understanding of myself and helped me respond more confidently next time."
        )

    if part == "p3":
        return (
            f"That's an interesting question. In my view, {question_clean.rstrip('?').lower()} depends a lot on the situation and on people's personal priorities. "
            "On the one hand, there are clear practical benefits, because people usually want something efficient, affordable and easy to manage. "
            "On the other hand, we should not ignore the long-term effects, especially when a decision influences families, schools, workplaces or the wider community. "
            "For instance, a choice that looks convenient in the short term may create extra pressure later if people do not think about responsibility and balance. "
            "So I would say the best approach is not to choose one extreme, but to look at the purpose, the people affected, and the possible consequences."
        )

    return ""


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
        result["display_transcript_markdown"] = _spoken_markdown(display_transcript)

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

    # Status fields
    result["feedback_generation_backend"] = "codex" if generated else "fallback"
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
        if metadata.get("feedback_generation_backend") == "codex" and metadata.get("feedback_generation_status") == "ready":
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
        metadata.get("feedback_generation_backend") == "codex"
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
        and (turn.transcript_cleaned or turn.transcript_raw or "").strip()
        and not _turn_feedback_ready(turn)
    ]
    if not pending_turns:
        return

    try:
        generated_by_turn = turn_feedback_batch_with_codex(
            pending_turns,
            attempt,
            target_band_label(attempt),
            learning_profile,
            f"{call_id}_turn_feedback_batch",
        )
    except Exception as exc:
        _mark_turn_feedback_failed(pending_turns, exc)
        return

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
        if feedback.get("feedback_generation_backend") == "codex":
            metadata["band7_source"] = "codex_report_batch"
            metadata["ai_coaching_source"] = "codex_report_batch"
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
    questions_text = "\n".join(f"Q{i + 1}: {turn.question}" for i, turn in enumerate(scoring_turns))
    transcript = "\n".join(
        f"Q{index + 1}: {turn.question}\nA: {turn_display_transcript(turn)}"
        for index, turn in enumerate(scoring_turns)
    )
    if not transcript.strip():
        raise SpeakingError("Missing transcript")

    try:
        score = score_with_codex(transcript, questions_text, part, call_id)
        score = calibrate_realistic_score(score, questions_text, transcript, part)
    except Exception as exc:
        mark_attempt_analysis_failed(attempt, exc, call_id)
        raise SpeakingError(f"AI analysis failed: {exc}") from exc

    criteria = _criteria_feedback(score, transcript)

    attempt.status = SpeakingAttempt.Status.SCORED
    attempt.metadata = {
        **(attempt.metadata if isinstance(attempt.metadata, dict) else {}),
        "current_turn": None,
        "scored_at": timezone.now().isoformat(),
    }
    attempt.save()
    learning_profile = build_learning_profile(user, attempt)
    generate_turn_feedback_for_report(attempt, scoring_turns, learning_profile, call_id)
    attempt.refresh_from_db()
    turns = list(attempt.turns.all().order_by("sequence"))
    scoring_turns = [turn for turn in turns if turn_counts_for_scoring(turn)]

    runtime = _runtime_attempt_payload(attempt)
    overall_review = build_overall_review(learning_profile, attempt, score, allow_codex=False)

    # Build personalized coaching
    personalized_coaching = build_personalized_coaching(learning_profile, attempt, score)

    runtime.update(
        {
            "status": "scored",
            "transcript_cleaned": transcript,
            "ielts_score": score,
            "score_generation_backend": score.get("generation_backend", score.get("backend")),
            "score_generation_status": score.get("generation_status", "ready" if score.get("backend") == "codex" else "fallback"),
            "score_generation_error": score.get("fallback_reason", ""),
            "report_generation_backend": score.get("backend"),
            "report_generation_status": "ready" if score.get("backend") == "codex" else "fallback",
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
            "p3_discussion_skills": build_p3_discussion_skills(attempt),
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
    task, created = create_ai_task(
        user=user,
        task_type="speaking_report",
        idempotency_key=idempotency_key,
        provider=payload.get("provider"),
        model=str(payload.get("model") or ""),
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
        },
        metadata={"source": "speaking_report_task"},
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

    # Use the complete build_turn_feedback logic
    feedback = build_turn_feedback(turn, attempt, user_profile, allow_codex=True)

    # Update turn metadata
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    metadata.update(feedback)
    metadata["feedback_regenerated_at"] = timezone.now().isoformat()

    # Track regeneration source
    if feedback.get("feedback_generation_backend") == "codex":
        metadata["band7_source"] = "codex_regenerated"
        metadata["ai_coaching_source"] = "codex_regenerated"
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
    questions_text = "\n".join(f"Q{i + 1}: {turn.question}" for i, turn in enumerate(scoring_turns))
    transcript = "\n".join(
        f"Q{index + 1}: {turn.question}\nA: {turn_display_transcript(turn)}"
        for index, turn in enumerate(scoring_turns)
    )
    if not transcript.strip():
        raise SpeakingError("Missing transcript")

    try:
        score = score_with_codex(transcript, questions_text, part, call_id)
        score = calibrate_realistic_score(score, questions_text, transcript, part)
    except Exception as exc:
        mark_attempt_analysis_failed(attempt, exc, call_id)
        raise SpeakingError(f"AI report regeneration failed: {exc}") from exc

    criteria = _criteria_feedback(score, transcript)

    attempt.updated_at = timezone.now()
    attempt.save(update_fields=["updated_at"])
    attempt.refresh_from_db()

    learning_profile = build_learning_profile(user, attempt)
    generate_turn_feedback_for_report(attempt, scoring_turns, learning_profile, call_id)
    attempt.refresh_from_db()
    turns = list(attempt.turns.all().order_by("sequence"))
    scoring_turns = [turn for turn in turns if turn_counts_for_scoring(turn)]

    runtime = _runtime_attempt_payload(attempt)
    overall_review = build_overall_review(learning_profile, attempt, score, allow_codex=False)

    # Build personalized coaching
    personalized_coaching = build_personalized_coaching(learning_profile, attempt, score)

    runtime.update(
        {
            "status": "scored",
            "transcript_cleaned": transcript,
            "ielts_score": score,
            "score_generation_backend": score.get("generation_backend", score.get("backend")),
            "score_generation_status": score.get("generation_status", "ready" if score.get("backend") == "codex" else "fallback"),
            "score_generation_error": score.get("fallback_reason", ""),
            "report_generation_backend": score.get("backend"),
            "report_generation_status": "ready" if score.get("backend") == "codex" else "fallback",
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
            "p3_discussion_skills": build_p3_discussion_skills(attempt),
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


def _examiner_tts_cache_key(attempt_id: str, turn_id: str) -> str:
    return f"{attempt_id}_{turn_id}_examiner"


def ensure_examiner_tts(attempt_id: str, turn: dict[str, Any]) -> None:
    """Ensure turn has examiner TTS audio_url generated."""
    current = turn.get("examiner_tts") or {}
    if current.get("audio_url") or current.get("status") not in (None, "pending"):
        return
    examiner_text = str(turn.get("examiner_text") or turn.get("question") or "")
    cache_key = _examiner_tts_cache_key(attempt_id, str(turn["id"]))
    try:
        fixed_item = _fixed_examiner_item_for_text(examiner_text)
        if fixed_item:
            cached_url = _cached_tts_url("examiner", fixed_item["key"])
            if cached_url:
                turn["examiner_tts"] = {
                    "provider": "volcengine",
                    "status": "cached",
                    "audio_url": cached_url,
                    "content_type": "audio/mpeg",
                }
                return
            _warm_fixed_examiner_tts_item_background(fixed_item)
            turn["examiner_tts"] = _fixed_examiner_pending_state(fixed_item)
            return
        turn["examiner_tts"] = volcengine_tts(
            examiner_text,
            role="examiner",
            cache_key=cache_key,
        )
    except Exception as exc:
        turn["examiner_tts"] = {
            "provider": "volcengine",
            "status": "fallback",
            "audio_url": None,
            "message": f"Server TTS unavailable; use browser fallback: {exc}",
        }


def _cached_examiner_tts_for_turn(attempt_id: str, turn_id: str, examiner_text: str) -> dict[str, Any] | None:
    fixed_item = _fixed_examiner_item_for_text(examiner_text)
    if fixed_item:
        cached_url = _cached_tts_url("examiner", fixed_item["key"])
        if cached_url:
            return {
                "provider": "volcengine",
                "status": "cached",
                "audio_url": cached_url,
                "content_type": "audio/mpeg",
            }
    cached_url = _cached_tts_url("examiner", _examiner_tts_cache_key(attempt_id, turn_id))
    if cached_url:
        return {
            "provider": "volcengine",
            "status": "cached",
            "audio_url": cached_url,
            "content_type": "audio/mpeg",
        }
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
            if current.get("audio_url") or current.get("status") not in (None, "pending"):
                continue
            generating_state = {
                **(current or {}),
                "provider": "volcengine",
                "status": "generating",
                "audio_url": None,
            }
            metadata["examiner_tts"] = generating_state
            db_turn.metadata = metadata
            db_turn.save(update_fields=["metadata", "updated_at"])
            turn_data = {
                "id": db_turn.turn_id,
                "question": db_turn.question,
                "examiner_text": metadata.get("examiner_text") or db_turn.question,
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


def examiner_tts_status(user, attempt_id: str, turn_id: str) -> dict[str, Any]:
    """Return the latest examiner TTS state, generating it once when pending."""
    started = time.monotonic()
    attempt = _load_attempt_for_user(user, attempt_id)
    turn = _find_turn(attempt, turn_id)
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    current = metadata.get("examiner_tts") if isinstance(metadata.get("examiner_tts"), dict) else {}
    tts = current or {"provider": "volcengine", "status": "pending", "audio_url": None}
    examiner_text = str(metadata.get("examiner_text") or turn.question)
    cached_tts = _cached_examiner_tts_for_turn(attempt.attempt_id, turn.turn_id, examiner_text)
    if cached_tts:
        tts = cached_tts
        metadata["examiner_tts"] = tts
        turn.metadata = metadata
        turn.save(update_fields=["metadata", "updated_at"])
    elif not tts.get("audio_url") and tts.get("status") in (None, "pending"):
        turn_data = {
            "id": turn.turn_id,
            "question": turn.question,
            "examiner_text": examiner_text,
            "examiner_tts": tts,
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
