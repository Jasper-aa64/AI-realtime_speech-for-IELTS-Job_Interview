"""Overall review and coaching helpers for speaking reports."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .ai_runtime import run_codex
from .models import SpeakingAttempt
from .text_utils import clean_markdown_text, clean_report_text, ensure_grammar_correction_bullet

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
                "backend": score.get("backend", "fallback"),
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
                "backend": score.get("backend", "fallback"),
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
