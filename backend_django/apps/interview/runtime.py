"""Interview sessions on the IELTS speaking runtime.

An interview is a SpeakingAttempt in one of the iv_* modes, so it gets the IELTS flow for free: the examiner
reads each question, the candidate prepares for 3 seconds, recording starts by itself, the server transcribes
it, and reports live in the speaking history. This module supplies what IELTS does not have: the question plan
from the candidate's resume / JD / curated bank, the interviewer's next-or-follow-up decision, and the
100-point report.
"""

from django.conf import settings

from . import ai_services, corpus, engine
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


# ---- After each answer: the interviewer decides (inside speaking.services.complete_turn).

SKIP_MESSAGE = "没有检测到回答，已跳过追问。"


def _prompt(turn):
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    return metadata.get("prompt") if isinstance(metadata.get("prompt"), dict) else {}


def _record(turn, **values):
    turn.metadata = {**(turn.metadata or {}), **values}
    turn.save(update_fields=["metadata", "updated_at"])


def _chain(attempt, turn):
    """(root turn, depth): follow-ups point at the turn they follow up via prompt.parent_turn_id."""
    by_id = {item.turn_id: item for item in attempt.turns.all()}
    node, depth = turn, 0
    while _prompt(node).get("parent_turn_id") in by_id:
        node = by_id[_prompt(node)["parent_turn_id"]]
        depth += 1
    return node, depth


def _answer(turn):
    return (turn.transcript_cleaned or turn.transcript_raw or "").strip()


def _insert_after(attempt, turn, *, question, stage, role, extra_prompt, speak_seconds=None, examiner_text=None):
    from apps.speaking.models import SpeakingTurn
    from apps.speaking.services import _generate_remaining_examiner_tts_after_commit

    for later in attempt.turns.filter(sequence__gt=turn.sequence).order_by("-sequence"):
        later.sequence += 1
        later.save(update_fields=["sequence"])
    taken = set(attempt.turns.values_list("turn_id", flat=True))
    suffix = 1
    while f"{turn.turn_id}_{role[0]}{suffix}" in taken:
        suffix += 1
    turn_id = f"{turn.turn_id}_{role[0]}{suffix}"
    data = make_turn(turn.sequence + 1, attempt.turns.count() + 1, question=question, stage=stage, role=role,
                     extra_prompt=extra_prompt, speak_seconds=speak_seconds)
    spoken = examiner_text or question
    inserted = SpeakingTurn.objects.create(
        user=attempt.user, attempt=attempt, turn_id=turn_id, sequence=turn.sequence + 1, part="interview",
        question=question, counts_toward_total=True,
        metadata={"prompt": data["prompt"], "cue_card": None, "timers": data["timers"], "examiner_text": spoken,
                  "examiner_behavior": "auto_play_question", "display_index": (turn.metadata or {}).get("display_index"),
                  "examiner_tts": {"provider": "volcengine", "status": "pending", "audio_url": None}},
    )
    # The frontend refreshes pending examiner audio itself; warming it now saves that round trip.
    _generate_remaining_examiner_tts_after_commit(attempt.attempt_id, [turn_id])
    return inserted


def after_answer(attempt, turn, ai_source=""):
    """Returns {"inserted": SpeakingTurn | None, "skipped": {"message"} | None}."""
    prompt = _prompt(turn)
    stage = prompt.get("stage") or "knowledge"
    value = _answer(turn)
    if not value:
        _record(turn, decision={"status": "skipped", "action": "next", "reason": "empty_answer"})
        return {"inserted": None, "skipped": {"reason": "missing_candidate_answer", "message": SKIP_MESSAGE}}
    meta = attempt.metadata.get("interview") if isinstance(attempt.metadata, dict) else None
    intensity = (meta or {}).get("intensity") or "standard"
    user = attempt.user
    profile = corpus.profile_for(user)
    if stage == "reverse":
        reverse_turns = [item for item in attempt.turns.all() if _prompt(item).get("stage") == "reverse"]
        inputs = {"candidate_question": value, "jd_summary": profile.jd_summary, "has_jd": bool(profile.jd_text)}
        try:
            result = ai_services.run_generation(user, "reverse_reply", inputs, ai_source=ai_source, related_id=attempt.attempt_id)
        except InterviewError as exc:
            _record(turn, decision={"status": "failed", "action": "next", "error": str(exc), "code": exc.code})
            result = None
        if result:
            _record(turn, decision={"status": "ready", "action": "reply", "signal": result["signal"], "evidence": result["evidence"]},
                    reply=result["reply"])
        if len(reverse_turns) < engine.REVERSE_ROUNDS:
            reply = (result or {}).get("reply", "")
            inserted = _insert_after(attempt, turn, question=engine.REVERSE_MORE, stage="reverse", role="main",
                                     extra_prompt={"reply": reply, "depth": 0},
                                     examiner_text=f"{reply}\n{engine.REVERSE_MORE}" if reply else None)
            return {"inserted": inserted, "skipped": None}
        return {"inserted": None, "skipped": None}
    root, depth = _chain(attempt, turn)
    limit = engine.depth_limit(intensity, stage)
    if depth >= limit:
        _record(turn, decision={"status": "ready", "action": "next", "reason": "depth_limit", "depth": depth})
        return {"inserted": None, "skipped": None}
    recent = [item for item in attempt.turns.filter(sequence__lte=turn.sequence).order_by("-sequence")[:4] if _answer(item)]
    inputs = {"stage": engine.STAGE_LABELS.get(stage, stage), "intensity": intensity, "question": turn.question,
              "answer": value[:6000], "depth": depth, "max_depth": limit, "root_question": root.question,
              "recent": [{"question": item.question, "answer": _answer(item)[:1200], "stage": _prompt(item).get("stage", "")}
                         for item in reversed(recent)],
              "asked": list(attempt.turns.values_list("question", flat=True)),
              "jd_role": (profile.jd_summary or {}).get("role", "")}
    try:
        result = ai_services.run_generation(user, "next_step", inputs, ai_source=ai_source, related_id=attempt.attempt_id)
    except InterviewError as exc:
        _record(turn, decision={"status": "failed", "action": "next", "error": str(exc), "code": exc.code})
        return {"inserted": None, "skipped": None}
    _record(turn, decision={"status": "ready", "depth": depth,
                            **{key: result[key] for key in ("action", "signal", "evidence", "boundary")}})
    if result["action"] not in {"follow_up", "probe"}:
        return {"inserted": None, "skipped": None}
    inserted = _insert_after(attempt, turn, question=result["prompt"], stage=stage, role="follow_up",
                             extra_prompt={"parent_turn_id": turn.turn_id, "action": result["action"], "depth": depth + 1},
                             speak_seconds=ANSWER_SECONDS["follow_up"])
    return {"inserted": inserted, "skipped": None}


# ---- The 100-point report, stored as a SpeakingReport so history, detail and delete are the IELTS ones.

SIGNAL_LABELS = {"strong": "答得扎实", "adequate": "基本到位", "weak": "还有缺口"}


def _coaching(turn, comment):
    """The interviewer's view of one answer, as the Markdown the IELTS report puts in the coaching row."""
    metadata = turn.metadata if isinstance(turn.metadata, dict) else {}
    decision = metadata.get("decision") if isinstance(metadata.get("decision"), dict) else {}
    lines = []
    if metadata.get("reply"):
        lines.append(f"**面试官的回答**：{metadata['reply']}")
    if decision.get("signal") in SIGNAL_LABELS:
        lines.append(f"**面试官判断**：{SIGNAL_LABELS[decision['signal']]}" + (f"——{decision['evidence']}" if decision.get("evidence") else ""))
    if decision.get("boundary"):
        lines.append(f"**能力边界**：{decision['boundary']}")
    if comment:
        lines.append(f"**点评**：{comment}")
    return "\n\n".join(lines)


def score(user, attempt, ai_source=""):
    from apps.speaking.models import SpeakingAttempt, SpeakingReport
    from apps.speaking.report_services import report_payload

    turns = list(attempt.turns.all().order_by("sequence"))
    answered = [turn for turn in turns if _answer(turn)]
    if not answered:
        raise ValueError("至少回答一道题才能评分。")
    meta = attempt.metadata.get("interview") if isinstance(attempt.metadata, dict) else {}
    profile = corpus.profile_for(user)
    inputs = {"part": (meta or {}).get("part", ""), "intensity": (meta or {}).get("intensity", "standard"),
              "has_jd": bool(profile.jd_text), "jd_summary": profile.jd_summary,
              "turn_ids": [turn.turn_id for turn in answered],
              "transcript": [{"turn_id": turn.turn_id, "stage": engine.STAGE_LABELS.get(_prompt(turn).get("stage"), ""),
                              "kind": _prompt(turn).get("role", "main"), "question": turn.question,
                              "answer": _answer(turn)[:2000],
                              "decision": {k: ((turn.metadata or {}).get("decision") or {}).get(k) for k in ("signal", "evidence", "boundary")},
                              "reply": (turn.metadata or {}).get("reply", "")} for turn in answered]}
    try:
        result = ai_services.run_generation(user, "score_report", inputs, ai_source=ai_source, related_id=attempt.attempt_id)
    except InterviewError as exc:
        raise ValueError(str(exc)) from exc
    per_turn = {item["turn_id"]: item for item in result.get("per_turn", [])}
    payload_turns = []
    for turn in turns:
        note = per_turn.get(turn.turn_id, {})
        reference = note.get("reference_answer", "")
        payload_turns.append({
            "id": turn.turn_id, "part": "interview", "question": turn.question, "prompt": _prompt(turn),
            "transcript_raw": turn.transcript_raw, "transcript_cleaned": turn.transcript_cleaned,
            "display_transcript": "", "display_transcript_markdown": "",
            "transcript_status": "captured" if _answer(turn) else "missing",
            "audio": {"url": f"/api/audio/{attempt.attempt_id}/{turn.turn_id}/candidate"} if turn.audio_path else None,
            "pronunciation": turn.pronunciation, "status": "completed",
            "band7_version": reference, "band7_markdown": reference, "upgrade_notes": [],
            "ai_coaching": _coaching(turn, note.get("comment", "")),
            "decision": (turn.metadata or {}).get("decision") or {}, "reply": (turn.metadata or {}).get("reply", ""),
        })
    interview_score = {key: result[key] for key in ("total", "dimensions", "summary", "boundary", "next_steps")}
    interview_score["limitations"] = engine.SCORE_LIMITATION
    payload = {"id": attempt.attempt_id, "mode": attempt.mode, "part": attempt.part, "title": attempt.title,
               "interview_score": interview_score, "ielts_score": None, "turns": payload_turns,
               "overall_review": {"comment": result.get("summary", ""), "review_points": result.get("next_steps", [])}}
    SpeakingReport.objects.update_or_create(
        attempt=attempt, defaults={"user": user, "report_payload": payload, "feedback_summary": result.get("summary", "")},
    )
    attempt.status = SpeakingAttempt.Status.SCORED
    attempt.save(update_fields=["status", "updated_at"])
    attempt.refresh_from_db()
    return report_payload(attempt)


def has_answers(attempt):
    return any((turn.transcript_cleaned or turn.transcript_raw or "").strip() for turn in attempt.turns.all())
