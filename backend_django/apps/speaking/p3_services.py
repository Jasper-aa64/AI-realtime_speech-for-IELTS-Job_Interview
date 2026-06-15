"""Pure P3 planning rules and text helpers for speaking practice."""

from __future__ import annotations

import re
from typing import Any

from .text_utils import clean_report_text

P3_MAIN_COUNT = 3

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

def _failed_p3_plan(theme: str, source_type: str, error: str) -> dict[str, Any]:
    return {
        "questions": [],
        "follow_up": "",
        "backend": "failed",
        "status": "failed",
        "error": error,
        "source_type": source_type,
    }

def _normalize_p3_focus(value: str | None) -> str:
    focus = str(value or "").strip().lower()
    return focus if focus in P3_FOCUS_OPTIONS else "comparison_concession"

def _normalize_p3_intensity(value: str | None) -> str:
    intensity = str(value or "").strip().lower()
    return intensity if intensity in {"normal", "high"} else "normal"

def _p3_source_type(payload: dict[str, Any], source_hint: str = "") -> str:
    source = str(payload.get("source") or payload.get("p3_source_type") or source_hint or "").strip().lower()
    if source == "season_bank":
        return "bank"
    if source in {"bank", "p2_report", "custom", "p2_answer"}:
        return source
    if str(payload.get("p2_corpus_entry_id") or "").strip():
        return "p2_corpus"
    if str(payload.get("prior_answer") or "").strip():
        return "p2_report"
    return "bank"

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
