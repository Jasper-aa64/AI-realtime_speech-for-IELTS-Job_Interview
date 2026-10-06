"""Interview sessions on the IELTS speaking runtime.

An interview is a SpeakingAttempt in one of the iv_* modes, so it gets the IELTS flow for free: the examiner
reads each question, the candidate prepares for 3 seconds, recording starts by itself, the server transcribes
it, and reports live in the speaking history. This module supplies what IELTS does not have: the question plan
from the candidate's resume / JD / curated bank, the interviewer's next-or-follow-up decision, and the
100-point report.
"""

from django.conf import settings

from . import engine
from .validation import InterviewError

INTERVIEW_MODES = {"iv_full": "full", "iv_project": "project", "iv_knowledge": "knowledge", "iv_reverse": "reverse"}
ANSWER_SECONDS = {"self_intro": 120, "project": 180, "knowledge": 120, "award": 120, "reverse": 60, "follow_up": 90}
PREP_SECONDS = 3
LANGUAGE = "zh"


def is_interview_mode(mode):
    return str(mode or "") in INTERVIEW_MODES


def examiner_voice():
    return getattr(settings, "INTERVIEW_EXAMINER_VOICE", "zh_male_xiaoming")


def make_turn(index, total, *, question, stage, role="main", extra_prompt=None, speak_seconds=None):
    """A turn dict in the exact shape the IELTS runtime stores and the frontend renders."""
    prompt = {"question": question, "role": role, "stage": stage, "language": LANGUAGE, **(extra_prompt or {})}
    return {
        "id": f"t{index + 1}",
        "part": "interview",
        "index": index,
        "total": total,
        "display_index": index + 1,
        "status": "pending",
        "question": question,
        "prompt": prompt,
        "cue_card": None,
        "timers": {"prep_seconds": PREP_SECONDS, "speak_seconds": speak_seconds or ANSWER_SECONDS.get(stage, 120)},
        "examiner_text": question,
        "examiner_behavior": "auto_play_question",
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
        "counts_toward_total": True,
    }


def build_turns(user, mode, payload):
    """Same return shape as speaking.services._build_turns: (part, title, turns, cue_card, metadata)."""
    part = INTERVIEW_MODES[mode]
    plan_payload = {"part": part, "intensity": payload.get("iv_intensity") or "standard"}
    for key in ("count", "category", "project_ids", "entry_ids", "question_ids"):
        if key in payload:
            plan_payload[key] = payload[key]
    try:
        part, intensity, plan = engine.build_plan(user, plan_payload)
    except InterviewError as exc:
        raise ValueError(str(exc)) from exc
    turns = [
        make_turn(index, len(plan), question=item["prompt"], stage=item["stage"], extra_prompt={
            "corpus_entry_id": item["corpus_entry_id"], "question_id": item["question_id"],
            "category": item["category"], "source": item["source"], "depth": 0,
        })
        for index, item in enumerate(plan)
    ]
    metadata = {"interview": {"part": part, "intensity": intensity,
                              "plan_stages": [s for s in engine.STAGES if any(t["stage"] == s for t in plan)]}}
    return "interview", engine.PART_TITLES[part], turns, None, metadata
