from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from .models import SpeakingTurn
from .text_utils import clean_report_text


def clamp_band(value: float | int | None) -> float:
    """Clamp band score to 0.0-9.0 in 0.5 increments."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(0.0, min(9.0, round(numeric * 2.0) / 2.0))


def rounded_overall(scores: dict[str, float | None]) -> float:
    """Calculate overall band from component scores."""
    values = [
        scores.get("fluency_coherence"),
        scores.get("lexical_resource"),
        scores.get("grammatical_range"),
    ]
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric:
        return 0.0
    average = sum(numeric) / len(numeric)
    return clamp_band(math.floor(average * 2.0 + 0.5) / 2.0)


def band_cap(scores: dict[str, Any], cap: float) -> None:
    """Cap all band scores at the given maximum."""
    for key in ("fluency_coherence", "lexical_resource", "grammatical_range", "overall_band"):
        if isinstance(scores.get(key), (int, float)):
            scores[key] = min(float(scores[key]), cap)


def development_markers(text: str) -> int:
    """Count development markers in text."""
    lowered = text.lower()
    markers = (
        "because",
        "for example",
        "for instance",
        "such as",
        "when ",
        "although",
        "however",
        "whereas",
        "compared",
        "rather than",
        "in contrast",
        "as a result",
        "therefore",
        "so ",
    )
    return sum(1 for marker in markers if marker in lowered)


def generic_template_score(text: str) -> int:
    """Count generic template phrases."""
    lowered = text.lower()
    patterns = (
        "it is very important",
        "it is very convenient",
        "it is good for me",
        "it can improve my",
        "in modern society",
        "with the development of",
        "broaden my horizons",
        "learn more knowledge",
        "make me feel relaxed",
        "leave a deep impression",
        "from my perspective",
        "as far as i am concerned",
        "there are many advantages",
    )
    return sum(1 for pattern in patterns if pattern in lowered)


def simple_grammar_ratio(sentences: list[str]) -> float:
    """Calculate ratio of simple sentences with no complex markers."""
    if not sentences:
        return 1.0
    complex_markers = re.compile(
        r"\b(because|although|though|while|whereas|which|who|that|when|if|unless|since|after|before|so that|even though)\b",
        re.I,
    )
    simple_count = sum(1 for sentence in sentences if not complex_markers.search(sentence))
    return simple_count / max(1, len(sentences))


def is_template_like_answer(text: str) -> bool:
    """Check if answer uses template-like phrases."""
    lowered = text.lower()
    repeated_phrases = (
        "from my perspective",
        "as far as i am concerned",
        "there are many advantages",
        "it is very important",
        "it is very convenient",
        "in modern society",
        "with the development of",
        "broaden my horizons",
        "learn more knowledge",
        "make me feel relaxed",
        "leave a deep impression",
    )
    if sum(1 for phrase in repeated_phrases if phrase in lowered) >= 2:
        return True
    if re.search(r"\b(there are many|it is very|it can)\b.{0,40}\b(there are many|it is very|it can)\b", lowered):
        return True
    return False


def append_calibration_note(scores: dict[str, Any], note: str) -> None:
    """Append calibration note to score feedback."""
    feedback = clean_report_text(str(scores.get("feedback") or ""))
    if note.lower() not in feedback.lower():
        feedback = f"{feedback} {note}".strip()
    scores["feedback"] = feedback[:500]


def calibrate_realistic_score(scores: dict[str, Any], question: str, transcript: str, part: str = "") -> dict[str, Any]:
    """Calibrate score based on word count, template usage, and development markers."""
    words = re.findall(r"[A-Za-z']+", transcript)
    word_count = len(words)
    sentences = [item.strip() for item in re.split(r"[.!?\n]+", transcript) if item.strip()]
    unique_ratio = len(set(word.lower() for word in words)) / max(1, word_count)
    marker_count = development_markers(transcript)
    template_count = generic_template_score(transcript)
    template_like = template_count >= 2 or is_template_like_answer(transcript)
    grammar_simple = simple_grammar_ratio(sentences)
    part = part.lower()

    scores["word_count"] = word_count

    if not words:
        band_cap(scores, 0.0)
        scores["overall_band"] = rounded_overall(scores)
        return scores

    if part == "p2":
        if word_count < 35:
            band_cap(scores, 5.0)
            append_calibration_note(scores, "Calibration: Part 2 is too short for a sustained long-turn score.")
        elif word_count < 80 or template_like:
            band_cap(scores, 5.5)
            append_calibration_note(scores, "Calibration: Part 2 needs fuller cue-card development and clear cue-card coverage.")
        elif word_count < 120 and marker_count < 2:
            band_cap(scores, 6.0)
            append_calibration_note(scores, "Calibration: Part 2 lacks enough supported development for 6.5+.")
    elif part == "p3":
        if word_count < 25:
            band_cap(scores, 5.0)
            append_calibration_note(scores, "Calibration: Part 3 is too brief for abstract discussion.")
        elif word_count < 55 or marker_count < 2 or template_like:
            band_cap(scores, 6.0)
            append_calibration_note(scores, "Calibration: Part 3 needs reasons, examples, comparison, or extension for 6.5+.")
    elif part == "p1":
        if word_count < 8:
            band_cap(scores, 5.0)
            append_calibration_note(scores, "Calibration: the answer is too short to show stable higher-band control.")
    else:
        if word_count < 60:
            band_cap(scores, 5.5)
            append_calibration_note(scores, "Calibration: the sample is too short for a high overall practice score.")

    if template_like or (word_count >= 20 and unique_ratio < 0.48):
        cap = 5.0 if part == "p2" else 5.5 if part == "p3" else 6.0
        band_cap(scores, cap)
        append_calibration_note(scores, "Calibration: generic or repetitive wording limits the score.")

    if grammar_simple >= 0.80 and word_count >= 25 and max(float(scores.get("grammatical_range") or 0.0), 0.0) > 6.0:
        scores["grammatical_range"] = 6.0
        append_calibration_note(scores, "Calibration: mostly simple sentence forms limit grammatical range.")

    scores["overall_band"] = rounded_overall(scores)
    return scores


def prompt_relevance(question: str, transcript: str) -> float:
    """Calculate relevance between question and transcript."""
    q_words = {word.strip(".,?!:;").lower() for word in question.split() if len(word.strip(".,?!:;")) > 3}
    t_words = {word.strip(".,?!:;").lower() for word in transcript.split() if len(word.strip(".,?!:;")) > 3}
    if not q_words or not t_words:
        return 0.0
    return len(q_words & t_words) / max(1, len(q_words))


def cap_off_topic_score(scores: dict[str, Any], question: str, transcript: str) -> dict[str, Any]:
    """Cap score if answer is off-topic."""
    relevance = prompt_relevance(question, transcript)
    feedback = str(scores.get("feedback", ""))
    model_flagged = any(
        marker in feedback.lower()
        for marker in ("off-topic", "does not address", "task relevance", "not address the")
    )
    if relevance >= 0.20 and not model_flagged:
        scores["task_relevance"] = round(relevance, 2)
        return scores
    scores["fluency_coherence"] = min(float(scores.get("fluency_coherence", 0)), 4.0)
    scores["overall_band"] = min(float(scores.get("overall_band", 0)), 4.5)
    if "off-topic" not in feedback.lower():
        feedback = "The response appears off-topic for the prompt. " + feedback
    scores["feedback"] = feedback.strip()
    scores["task_relevance"] = round(relevance, 2)
    return scores


def heuristic_score(transcript: str, reason: str, question: str = "", part: str = "") -> dict[str, Any]:
    """Generate heuristic score based on transcript length and vocabulary."""
    words = re.findall(r"[A-Za-z']+", transcript)
    unique_ratio = len(set(word.lower() for word in words)) / max(1, len(words))
    if not words:
        base = 0.0
    elif part == "p1":
        if len(words) >= 220:
            base = 6.5
        elif len(words) >= 130:
            base = 6.0
        elif len(words) >= 70:
            base = 5.5
        elif len(words) >= 25:
            base = 5.0
        else:
            base = 4.5
    else:
        if len(words) >= 260:
            base = 6.5
        elif len(words) >= 150:
            base = 6.0
        elif len(words) >= 70:
            base = 5.5
        elif len(words) < 20:
            base = 4.0
        else:
            base = 4.5
    lexical = base + (0.5 if unique_ratio > 0.62 and len(words) >= 50 else 0.0)
    scores: dict[str, Any] = {
        "fluency_coherence": clamp_band(base),
        "lexical_resource": clamp_band(lexical),
        "grammatical_range": clamp_band(base),
    }
    scores["overall_band"] = rounded_overall(scores)
    feedback = f"Content score uses fallback estimate: {reason}. Record clear, relevant English answers for a more useful assessment."
    result = {**scores, "feedback": feedback, "backend": "heuristic", "word_count": len(words)}
    return cap_off_topic_score(calibrate_realistic_score(result, question, transcript, part), question, transcript)


def score_prompt_for_part(part: str) -> str:
    """Get part-specific scoring guidance."""
    if part == "p1":
        return (
            "Section type: IELTS Speaking Part 1. Part 1 answers are normally short. "
            "Do not penalize a relevant answer just because it is not a long turn; 3-5 spoken sentences per question is enough. "
            "Score for relevance, clarity, basic sentence control, and natural short-answer development."
        )
    if part == "p2":
        return (
            "Section type: IELTS Speaking Part 2. Score the long-turn response by cue-card coverage, sustained development, "
            "coherence across the story, vocabulary range, and grammar control. Do not award 6.5+ for short, generic, "
            "memorized, or thinly developed long-turn answers."
        )
    if part == "p3":
        return (
            "Section type: IELTS Speaking Part 3. Score abstract discussion quality: clear opinions, reasons, examples, "
            "comparison, concession, speculation, and ability to extend ideas from personal examples to broader social or abstract issues. "
            "Do not award 6.5+ for brief opinions without reasons, examples, comparison, or abstract development. "
            "The most useful feedback should tell the learner which discussion move is missing: position, reason, example, contrast, concession, consequence, or wider implication."
        )
    return "Section type: full/mock IELTS Speaking section. Score the completed section as a whole."


def transcript_word_count(transcript: str) -> int:
    """Count words in transcript."""
    return len(re.findall(r"[A-Za-z']+", transcript))


def short_question(text: str, max_len: int = 80) -> str:
    """Truncate text to max length with ellipsis."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def repeated_phrases_from_texts(texts: list[str]) -> list[str]:
    """Find repeated phrases across texts."""
    all_words: list[str] = []
    for text in texts:
        all_words.extend(re.findall(r"[A-Za-z']+", text.lower()))
    counts = Counter(all_words)
    return [word for word, count in counts.most_common(10) if count >= 3 and len(word) > 4]


def turn_habit_tags(turn: dict[str, Any] | SpeakingTurn, score: dict[str, Any] | None = None) -> list[str]:
    """Identify habit tags for a turn based on transcript and score."""
    if isinstance(turn, SpeakingTurn):
        transcript = (turn.transcript_cleaned or turn.transcript_raw or "").strip()
        part = turn.part or ""
    else:
        transcript = str(turn.get("transcript_cleaned") or turn.get("transcript_raw") or "").strip()
        part = str(turn.get("part") or "").lower()

    tags: set[str] = set()
    word_count = transcript_word_count(transcript)

    if not transcript:
        tags.add("missing_transcript")
    if word_count and word_count < 25:
        tags.add("short_answer")
    if part == "p2" and word_count and word_count < 90:
        tags.add("limited_development")
    if part == "p3" and word_count and word_count < 55:
        tags.add("limited_development")

    lowered = transcript.lower()
    if any(phrase in lowered for phrase in ("it is very important", "it is very convenient", "in modern society", "from my perspective", "as far as i am concerned")):
        tags.add("template_language")

    if transcript and len(set(re.findall(r"[A-Za-z']+", lowered))) < max(8, word_count // 2 or 8):
        tags.add("repeated_phrases")

    if score and isinstance(score.get("overall_band"), (int, float)) and float(score["overall_band"]) < 5.5:
        tags.add("low_band")

    if isinstance(turn, SpeakingTurn):
        question = turn.question
    else:
        question = str(turn.get("question") or "")
    if transcript and prompt_relevance(question, transcript) < 0.20:
        tags.add("off_topic")

    if part == "p1" and word_count < 15:
        tags.add("too_short_p1")

    return sorted(tags)


def part_focus_text(part: str, tags: list[str], score: dict[str, Any] | None = None) -> str:
    """Get focus text for a part based on tags."""
    if part == "p2":
        if "short_answer" in tags or "limited_development" in tags:
            return "Part 2 需要先覆盖 cue card，并把答案展开到接近两分钟。"
        if "template_language" in tags:
            return "Part 2 模板痕迹偏重，先换成自己的经历说法。"
        return "Part 2 重点是把经历、细节和感受说完整。"
    if part == "p3":
        if "short_answer" in tags or "limited_development" in tags:
            return "Part 3 需要补上观点背后的原因、对比和例子。"
        return "Part 3 重点是做抽象讨论，不只停留在个人经历。"
    if part == "p1":
        return "Part 1 先做到直接回答，再补一个自然的小细节。"
    if score and isinstance(score.get("overall_band"), (int, float)) and float(score["overall_band"]) < 5.5:
        return "先把答案说完整、说具体，再追求高级表达。"
    return "先处理最影响分数的表达习惯。"


def infer_primary_focus(tags: list[str]) -> str:
    """Infer primary focus from habit tags."""
    if "off_topic" in tags:
        return "task_relevance"
    if "short_answer" in tags or "limited_development" in tags:
        return "answer_development"
    if "template_language" in tags or "repeated_phrases" in tags:
        return "lexical_variety"
    if "low_band" in tags:
        return "answer_development"
    return "answer_development"
