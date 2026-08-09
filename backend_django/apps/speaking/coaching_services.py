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

def p3_model_answer_constraints() -> str:
    """Shared quality contract for every generated Part 3 model answer."""
    return """This is IELTS Speaking Part 3. Produce one Band 7.5+ spoken answer that lasts about 45-70 seconds
at a natural speaking pace (normally about 130-175 English words). This is a conversation, not a miniature Task 2 essay.

Question-type choice (make this choice before writing the answer):
- Opinion / comparison: questions such as "Do you think...", "Which is more...", or "Should A or B..." need a clear
  answer with nuance. Use the six-step opinion route below.
- Listing Group A: questions such as "What sports / factors / ways / things do..." ask for concrete things that exist.
  Select the listing route that fits the amount of believable detail you have: Parallel explanation, Two-camp contrast,
  or Hourglass.
- Category Group B: "What kind(s) of..." asks for types or styles, not named examples. Use one of the same three listing
  routes, but keep the examples at category level (for example, "comedies" or "feel-good films"), never individual
  film, video, book, or celebrity names.

Why these choices matter: forcing every question through one opinion structure produces the polished but artificial
answers learners often memorise. A real speaker answers the question that was asked: they take a position when a position
is needed, list naturally when the question asks for a range, and classify when the question asks for types.

Return band7_version in this exact Markdown study format. Start with one concise Chinese study line, then keep every
answer section as spoken English answer only:

**题目分析：** <一两句中文：题型、所选骨架，以及为什么这个骨架适合这道题>

**Q: <question>**

For Opinion / comparison, use this six-step route:
**1. 接题（复述/改写题目本身）**
- <spoken opening>
**2. 观点**
- <clear but qualified position>
**3.1 原因/背景**
- <reason or background>
**3.2 现实观察**
- <specific observation>
**3.3 让步限定**
- <concession or exception>
**4. 个人评价（可选）**
- <only when it genuinely adds a new angle>
**5. 自然收尾**
- <light ending>

For Listing Group A or Category Group B, choose exactly one route and use its labels instead of empty opinion slots:
- Parallel explanation: 1. 接题; 2. 选项一 + 半句原因; 3. 选项二 + 半句原因; 4. 选项三 + 半句原因;
  5. 分寸/让步; 6. 自然收尾. Use it when several points are useful but none has credible depth.
- Two-camp contrast: 1. 接题 + 分类信号; 2. 阵营A; 3. 阵营B + 轻微让步; 4. 微观视角（可选）;
  5. 分布判断收尾. Use it when two groups create a natural contrast.
- Hourglass: 1. 接题; 2. S1 列举（快速带过3-4项）; 3. S2 聚焦（用 especially / actually 自然收窄）;
  4. S3 证据; 5. S4 个人评价; 6. 自然收尾. Use it only when one point has a credible detail, scene, or number.
  Do not announce a plan such as "let me focus on..."; let the focus happen in the flow instead.

Answer-quality rules, with the reason for each:
- Open by restating or lightly rephrasing the actual question, never by announcing an answer plan. Why: this is active listening:
  it shows the examiner that the speaker is engaging with the question; explaining an exam strategy exposes
  rehearsal and does not answer anything.
- Keep natural conversation rather than writing prose. Avoid "rapid development", "plays a vital role", "with the advent
  of", "it is widely believed", "moreover", "furthermore", and "in conclusion". Why: these are writing connectors;
  spoken logic is usually carried by simple links such as and, but, so, actually, and that said.
- Include one small self-correction or thinking trace when it sounds natural, and never pile up hesitations. Why: one
  genuine adjustment makes the answer sound live; repeated performance of hesitation sounds insecure rather than natural.
- Ground the answer in a credible China context and one small personal lens (self, friend, classmate, neighbour, or family;
  vary the lens when possible). Why: a specific human observation is more believable and discussable than abstract claims
  about "people in China". Do not invent a detailed personal fact merely to fill a slot.
- For evidence, use one specific detail plus one qualitative observation, not two precise statistics. Why: a single detail
  anchors a real observation, while stacked exact figures sound fabricated or pre-written.
- Include a diplomatic limitation with varied language such as "I wouldn't go so far as to say...", "It's not always the
  case...", or "That said, I wouldn't write off...". Why: Part 3 rewards measured judgement, while a single repetitive
  "but" makes the reasoning sound flat.
- End by reframing the judgement or giving a conditional distribution, not "To sum up" or "In conclusion". Why: a live
  discussion should leave a useful opening for the examiner's next question instead of closing like an essay.
- Do not mechanically recycle the same opener, concession, personal lens, or ending across answers. Why: fluent speakers
  adapt the same discussion moves to the question in front of them, whereas repeated wording makes good ideas sound learnt.

After the spoken answer, add:
**本题新增的可复用表达**
- <3-5 bolded expressions copied exactly from the answer, no translations or Chinese explanations>

Bold 3-5 reusable spoken expressions inside the English answer itself, then repeat only those chunks in the final list.
Choose natural collocations, diplomatic qualifiers, conversational links, or topic-specific chunks; never bold headings,
whole sentences, or generic filler. Why: the learner needs a few clear retrieval anchors for exam pressure, but too many
highlighted items or competing alternative versions make recall slower and the answer look mechanically taught.

The Markdown labels, Chinese question analysis, expression list, and timing footer are visual study scaffolding only.
TTS reads only the spoken English answer. This distinction matters because the learner can study the reasoning path on
screen without hearing a lesson plan instead of an answer. Do not add Chinese difficulty analysis. End with
*(≈N词/X-Y秒)*."""


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
            "Cover the cue-card points without copying the bullet list. Aim for 180-230 English words, "
            "roughly 1.5-2 minutes at a natural speaking pace. Do not shorten it into a Part 1/Part 3 "
            "answer or inflate it into a written essay."
        )
    if part == "p3":
        return p3_model_answer_constraints()
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


def model_band7_tts_status(user, attempt_id: str, turn_id: str) -> dict[str, Any]:
    """Return a report turn's band7 model-answer TTS, regenerating it once when the
    server synthesis failed at scoring time.

    The band7 text is already saved; only the audio is missing (a flaky upstream can
    drop a few turns during a report-sized burst). Opening the report calls this so
    the missing 朗读 audio fills itself in with the real VolcEngine voice instead of
    staying blank forever.
    """
    from .runtime_payload_services import _find_turn, _load_attempt_for_user
    from .tts_services import volcengine_tts

    attempt = _load_attempt_for_user(user, attempt_id)
    turn = _find_turn(attempt, turn_id)
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    band7_version = metadata.get("band7_version") or ""
    current = metadata.get("model_audio") if isinstance(metadata.get("model_audio"), dict) else {}

    if not clean_report_text(band7_version):
        return {
            "attempt_id": attempt.attempt_id,
            "turn_id": turn.turn_id,
            "model_audio": {"provider": "none", "status": "empty_text", "audio_url": None},
        }
    if current.get("audio_url"):
        return {
            "attempt_id": attempt.attempt_id,
            "turn_id": turn.turn_id,
            "model_audio": current,
        }

    model_audio = volcengine_tts(
        band7_version,
        role="model",
        cache_key=_model_band7_tts_cache_key(attempt.attempt_id, turn.turn_id, band7_version),
        retries=2,
        timeout=8.0,
    )
    metadata["model_audio"] = model_audio
    turn.metadata = metadata
    turn.save(update_fields=["metadata", "updated_at"])
    return {
        "attempt_id": attempt.attempt_id,
        "turn_id": turn.turn_id,
        "model_audio": model_audio,
    }


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
