"""Studio sessions: IELTS-shaped interview plans driven by an AI interviewer.

A plan is built up front from the candidate's corpus (self intro -> every project -> knowledge ->
awards -> reverse round). After each answer the interviewer decides, within hard server limits,
whether to follow up (dig deeper), probe (find the limit of a weak answer) or move on. Provider
calls run outside DB transactions under the session lease; their failure never blocks progress.
"""

import random
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.speaking.volcengine_asr import transcribe_audio

from . import ai_services, corpus
from .bank import BY_ID, CATEGORIES, QUESTIONS
from .models import InterviewCorpusEntry as Entry
from .models import InterviewSession, InterviewTurn
from .services import REPORT_LIMITATION, _active, _clear_lease, _not_busy, _owned, _pending, _touch, _turn, detail
from .validation import InterviewError, count, text

STAGES = ("self_intro", "project", "knowledge", "award", "reverse")
STAGE_LABELS = {"self_intro": "自我介绍", "project": "项目", "knowledge": "知识点", "award": "奖项", "reverse": "反问"}
PART_TITLES = {"full": "完整面试", "project": "项目深挖", "knowledge": "知识点练习", "reverse": "反问环节"}
REVERSE_OPEN = "我这边的问题差不多了，你有什么想问我的吗？"
REVERSE_MORE = "还有其他想了解的吗？没有的话我们今天就到这里。"
REVERSE_ROUNDS = 2
FALLBACK_INTRO = "请先做一个简单的自我介绍。"
# Follow-up depth per main question.
# 标准: no follow-ups, the planned questions in order. 追问压力: the interviewer decides when a thread is done; this is only
# a safety stop against an endless chain (never shown to the model).
DEPTH = {"standard": {"default": 0}, "pressure": {"default": 8}}
AUDIO_LIMIT = 15 * 1024 * 1024
# Launch-panel limits: a knowledge pool, questions written for one session, a project text, a JD, planned questions.
PICK_LIMIT = 30
CUSTOM_LIMIT = 10
PROJECT_TEXT_LIMIT = 8000
JD_TEXT_LIMIT = 12000
REVERSE_PLAN = (1, 5)
PROJECT_FROM_TEXT = "结合你写的这段项目描述，完整介绍一下{title}：背景、你负责的部分、技术难点，以及最后的结果。"
SCORE_LIMITATION = "百分制由 AI 根据本次文字回答（含语音转写稿）估计，不评估发音，也不代表真实招聘结果。"


def depth_limit(intensity, stage):
    table = DEPTH.get(intensity, DEPTH["standard"])
    return 0 if stage == "reverse" else table.get(stage, table["default"])


def _main(stage, prompt, *, entry=None, question=None):
    return {"stage": stage, "prompt": prompt, "corpus_entry_id": entry.entry_id if entry else "",
            "question_id": question["id"] if question else "",
            "category": (question or {}).get("category") or (entry.group if entry else "") or stage,
            "difficulty": (question or {}).get("difficulty", "intermediate"),
            "source": "curated" if question else (entry.source if entry else "studio")}


def _strings(value, name, limit, *, item_limit=1500):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit:
        raise InterviewError(f"{name} 最多 {limit} 项")
    return [text(item, name, item_limit, required=True) for item in value]


def _picked_knowledge(user, payload, amount):
    """The launch panel's pick: corpus / bank questions and session-only questions, asked up to `amount`.

    A pool larger than the count is sampled (in the order it was picked); a smaller one is topped up from the
    categories the candidate opened, never from elsewhere."""
    entry_ids = _strings(payload.get("entry_ids"), "entry_ids", PICK_LIMIT, item_limit=80)
    question_ids = _strings(payload.get("question_ids"), "question_ids", PICK_LIMIT, item_limit=40)
    customs = _strings(payload.get("custom_questions"), "custom_questions", CUSTOM_LIMIT, item_limit=500)
    categories = _strings(payload.get("categories"), "categories", len(CATEGORIES), item_limit=32)
    if len(entry_ids) + len(question_ids) + len(customs) > PICK_LIMIT:
        raise InterviewError(f"一次最多选 {PICK_LIMIT} 道题。")
    if any(q not in BY_ID for q in question_ids) or len(set(question_ids)) != len(question_ids):
        raise InterviewError("Question IDs must be known and unique")
    if any(c not in {item["id"] for item in CATEGORIES} for c in categories):
        raise InterviewError("未知的题目方向。")
    owned = {e.entry_id: e for e in Entry.objects.filter(user=user, entry_id__in=entry_ids, kind__in=["knowledge", "jd_question"])}
    if len(owned) != len(set(entry_ids)):
        raise InterviewError("Unknown corpus question")
    pool = [_main("knowledge", owned[i].question, entry=owned[i]) for i in dict.fromkeys(entry_ids)]
    pool += [_main("knowledge", BY_ID[q]["prompt"], question=BY_ID[q]) for q in question_ids]
    pool += [{**_main("knowledge", prompt), "category": "knowledge", "source": "custom"} for prompt in dict.fromkeys(customs)]
    if len(pool) > amount:
        keep = sorted(random.sample(range(len(pool)), amount))
        return [pool[index] for index in keep]
    taken = {item["prompt"] for item in pool}
    for question in QUESTIONS:
        if len(pool) >= amount:
            break
        if question["category"] in categories and question["prompt"] not in taken:
            pool.append(_main("knowledge", question["prompt"], question=question))
    return pool


def _knowledge_items(user, material, payload, amount, *, full=False):
    if any(payload.get(key) is not None for key in ("custom_questions", "categories")):
        return _picked_knowledge(user, payload, amount)
    entry_ids = payload.get("entry_ids")
    question_ids = payload.get("question_ids")
    if entry_ids is not None or question_ids is not None:
        entry_ids, question_ids = entry_ids or [], question_ids or []
        if not isinstance(entry_ids, list) or not isinstance(question_ids, list) or not 1 <= len(entry_ids) + len(question_ids) <= 10:
            raise InterviewError("请选择 1 到 10 道题。")
        if any(q not in BY_ID for q in question_ids) or len(set(question_ids)) != len(question_ids):
            raise InterviewError("Question IDs must be known and unique")
        owned = {e.entry_id: e for e in Entry.objects.filter(user=user, entry_id__in=entry_ids, kind__in=["knowledge", "jd_question"])}
        if len(owned) != len(set(entry_ids)):
            raise InterviewError("Unknown corpus question")
        return [_main("knowledge", owned[i].question, entry=owned[i]) for i in entry_ids] + \
               [_main("knowledge", BY_ID[q]["prompt"], question=BY_ID[q]) for q in question_ids]
    category = text(payload.get("category"), "category", 32)
    if category and category not in {c["id"] for c in CATEGORIES}:
        raise InterviewError("未知的题目方向。")
    items = []
    if not category:
        # Resume tech-stack questions first, then the role's own questions, then the curated bank.
        items += [_main("knowledge", e.question, entry=e) for e in material["knowledge"] if e.source == "resume"][:3]
        items += [_main("knowledge", e.question, entry=e) for e in material["jd_question"]][:2]
    taken = {i["prompt"] for i in items}
    if category:
        bank = [q for q in QUESTIONS if q["category"] == category]
    else:
        # In a full interview the resume projects already cover "项目深挖"; keep curated fill to knowledge areas.
        bank = [q for q in QUESTIONS if not (full and q["category"] == "projects")]
    # Spread curated questions across categories so a mixed round is not five C++ questions.
    buckets = {}
    for q in bank:
        buckets.setdefault(q["category"], []).append(q)
    while len(items) < amount and any(buckets.values()):
        for key in list(buckets):
            if buckets[key] and len(items) < amount:
                q = buckets[key].pop(0)
                if q["prompt"] not in taken:
                    items.append(_main("knowledge", q["prompt"], question=q))
    return items[:amount]


def build_plan(user, payload):
    part = text(payload.get("part"), "part", 16, required=True)
    if part not in PART_TITLES:
        raise InterviewError("part must be full, project, knowledge or reverse")
    intensity = text(payload.get("intensity", "standard"), "intensity", 16) or "standard"
    if intensity not in DEPTH:
        raise InterviewError("intensity must be standard or pressure")
    material = corpus.practice_material(user)
    projects = sorted(material["project"], key=lambda e: e.order)
    project_text = text(payload.get("project_text"), "项目描述", PROJECT_TEXT_LIMIT) if part == "project" else ""
    if part == "project" and (payload.get("project_ids") or project_text):
        wanted = payload.get("project_ids") or []
        if not isinstance(wanted, list) or not all(isinstance(i, str) for i in wanted):
            raise InterviewError("project_ids must be a list of corpus ids")
        projects = [p for p in projects if p.entry_id in set(wanted)]
    if part in {"full", "project"} and not projects and not project_text:
        raise InterviewError("请先上传简历，面试官才能就你的项目提问。", code="resume_required")
    turns = []
    if part == "full":
        intro = next(iter(material["self_intro"]), None)
        turns.append(_main("self_intro", intro.question if intro else FALLBACK_INTRO, entry=intro))
    if part in {"full", "project"}:
        turns += [_main("project", p.question, entry=p) for p in projects]
    if project_text:
        # A project written for this session: the interviewer asks about it and follows up with it as context.
        heading = next((line.strip("# ").strip() for line in project_text.splitlines() if line.strip()), "")
        title = f"「{heading[:30]}」这个项目" if heading and len(heading) <= 30 else "这个项目"
        turns.append({**_main("project", PROJECT_FROM_TEXT.format(title=title)), "source": "custom",
                      "project_context": project_text})
    if part in {"full", "knowledge"}:
        amount = count(payload.get("count"), default=5)
        turns += _knowledge_items(user, material, payload if part == "knowledge" else {}, amount, full=part == "full")
    if part == "full":
        turns += [_main("award", a.question, entry=a) for a in sorted(material["award"], key=lambda e: e.order)[:1]]
    if part in {"full", "reverse"}:
        planned = _strings(payload.get("reverse_questions"), "reverse_questions", REVERSE_PLAN[1], item_limit=300)
        turns.append({**_main("reverse", REVERSE_OPEN), **({"planned_questions": planned} if planned else {})})
    if not turns:
        raise InterviewError("这次练习没有可用的题目。", code="empty_plan")
    return part, intensity, turns


@transaction.atomic
def create(user, payload):
    part, intensity, plan = build_plan(user, payload)
    title = text(payload.get("title"), "title", 160) or PART_TITLES[part]
    session = InterviewSession.objects.create(user=user, mode="studio", part=part, intensity=intensity, title=title,
                                              plan=[s for s in STAGES if any(t["stage"] == s for t in plan)])
    InterviewTurn.objects.bulk_create([
        InterviewTurn(user=user, session=session, order=index, stage=t["stage"], prompt=t["prompt"],
                      corpus_entry_id=t["corpus_entry_id"], question_id=t["question_id"], category=t["category"][:32],
                      difficulty=t["difficulty"], source=t["source"])
        for index, t in enumerate(plan, 1)
    ])
    return detail(user, session.public_id)


def _root(turn):
    depth, node = 0, turn
    while node.parent_id:
        node = node.parent
        depth += 1
    return node, depth


def _lease(session, kind):
    token = uuid.uuid4().hex
    session.ai_busy_since, session.ai_busy_kind, session.ai_busy_token = timezone.now(), kind, token
    session.save(update_fields=["ai_busy_since", "ai_busy_kind", "ai_busy_token", "updated_at"])
    return token


def _insert_after(session, turn, **fields):
    for later in session.turns.filter(order__gt=turn.order).order_by("-order"):
        later.order += 1
        later.save(update_fields=["order", "updated_at"])
    return InterviewTurn.objects.create(user=session.user, session=session, order=turn.order + 1, **fields)


def _record_decision(turn, decision):
    turn.metadata = {**turn.metadata, "decision": decision}
    turn.save(update_fields=["metadata", "updated_at"])


def _recent(session, turn):
    rows = list(session.turns.filter(order__lte=turn.order).exclude(status="pending").order_by("-order")[:4])
    return [{"question": t.prompt, "answer": t.answer[:1200], "stage": t.stage} for t in reversed(rows)]


def answer(user, session_id, turn_id, value, *, answer_source="typed", ai_source=""):
    value = text(value, "answer", 6000, required=True)
    if answer_source not in {"typed", "voice"}:
        raise InterviewError("answer_source must be typed or voice")
    with transaction.atomic():
        session = _owned(user, session_id, lock=True)
        turn = _turn(session, turn_id)
        if turn.status == "completed" and turn.answer == value:
            return detail(user, session_id)
        _active(session)
        _not_busy(session)
        current = _pending(session)
        if current is None or current.pk != turn.pk:
            raise InterviewError("这道题已经不是当前题目了，请刷新后继续。", code="stale_turn", status=409)
        turn.answer, turn.status, turn.answer_source = value, "completed", answer_source
        turn.save(update_fields=["answer", "status", "answer_source", "updated_at"])
        root, depth = _root(turn)
        limit = depth_limit(session.intensity, turn.stage)
        reverse_rounds = session.turns.filter(stage="reverse").count()
        if turn.stage != "reverse" and depth >= limit:
            _record_decision(turn, {"status": "ready", "action": "next", "reason": "depth_limit", "depth": depth})
            _touch(session)
            return detail(user, session_id)
        kind = "reverse_reply" if turn.stage == "reverse" else "next_step"
        token = _lease(session, kind)
        profile = corpus.profile_for(user)
        if kind == "reverse_reply":
            inputs = {"candidate_question": value, "jd_summary": profile.jd_summary, "has_jd": bool(profile.jd_text)}
        else:
            asked = list(session.turns.values_list("prompt", flat=True))
            inputs = {"stage": STAGE_LABELS.get(turn.stage, turn.stage), "intensity": session.intensity,
                      "question": turn.prompt, "answer": value, "depth": depth,
                      **({} if session.intensity == "pressure" else {"max_depth": limit}),
                      "root_question": root.prompt, "recent": _recent(session, turn), "asked": asked,
                      "jd_role": (profile.jd_summary or {}).get("role", "")}
    try:
        result = ai_services.run_generation(user, kind, inputs, ai_source=ai_source, related_id=session_id)
        failure = None
    except InterviewError as exc:
        result, failure = None, exc
    try:
        with transaction.atomic():
            session = _owned(user, session_id, lock=True)
            if session.ai_busy_token != token:
                raise InterviewError("面试官的判断已过期，请刷新后继续。", code="stale_generation", status=409)
            turn = _turn(session, turn_id)
            if failure is not None:
                _record_decision(turn, {"status": "failed", "action": "next", "error": str(failure), "code": failure.code})
            elif kind == "reverse_reply":
                _record_decision(turn, {"status": "ready", "action": "reply", **{k: result[k] for k in ("signal", "evidence")}})
                turn.metadata = {**turn.metadata, "reply": result["reply"]}
                turn.save(update_fields=["metadata", "updated_at"])
                if reverse_rounds < REVERSE_ROUNDS and session.status == "active":
                    _insert_after(session, turn, stage="reverse", prompt=REVERSE_MORE, category="reverse", source="studio")
            else:
                decision = {"status": "ready", "depth": depth, **{k: result[k] for k in ("action", "signal", "evidence", "boundary")}}
                _record_decision(turn, decision)
                if result["action"] in {"follow_up", "probe"} and session.status == "active":
                    _insert_after(session, turn, kind="follow_up", parent=turn, stage=turn.stage, prompt=result["prompt"],
                                  category=turn.category, difficulty=turn.difficulty, source="ai_generated",
                                  corpus_entry_id="", metadata={"action": result["action"], "task_id": result.get("task_id", "")})
            _touch(session)
    finally:
        _clear_lease(user, session_id, token)
    return detail(user, session_id)


def upload_audio(user, session_id, turn_id, upload):
    if upload is None or not 0 < upload.size <= AUDIO_LIMIT:
        raise InterviewError("请上传 15 MB 以内的录音。", code="invalid_audio")
    with transaction.atomic():
        session = _owned(user, session_id, lock=True)
        _active(session)
        turn = _turn(session, turn_id)
        current = _pending(session)
        if current is None or current.pk != turn.pk:
            raise InterviewError("这道题已经不是当前题目了，请刷新后继续。", code="stale_turn", status=409)
        relative = Path("interview_audio") / str(user.pk) / session.public_id / f"{turn.public_id}-{uuid.uuid4().hex[:8]}.webm"
        target = Path(settings.MEDIA_ROOT) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            for chunk in upload.chunks():
                handle.write(chunk)
        turn.audio_path = str(relative)
        turn.save(update_fields=["audio_path", "updated_at"])
    result = transcribe_audio(target)
    transcript = text(result.get("transcript") or "", "transcript", 6000)
    if not result.get("ok") or not transcript:
        raise InterviewError("没有识别出文字，请重录或改为打字作答。", code="asr_failed", status=502)
    return {"transcript": transcript, "turn_id": turn_id}


def save_to_corpus(user, session_id, turn_id):
    session = _owned(user, session_id)
    turn = _turn(session, turn_id)
    if turn.status != "completed" or not turn.answer:
        raise InterviewError("只有已回答的题目才能存进语料库。")
    if turn.stage == "reverse":
        return corpus.create_entry(user, {"kind": "reverse_question", "question": turn.answer,
                                          "corpus_text": (turn.metadata or {}).get("reply", "")})
    if turn.corpus_entry_id:
        return corpus.update_entry(user, turn.corpus_entry_id, {"corpus_text": turn.answer})
    if turn.question_id:
        created = corpus.create_entry(user, {"kind": "knowledge", "source_key": f"curated:{turn.question_id}"})
        return corpus.update_entry(user, created["entry"]["id"], {"corpus_text": turn.answer})
    root, _ = _root(turn)
    if turn.kind == "follow_up" and root.stage == "project" and root.corpus_entry_id:
        return corpus.create_entry(user, {"kind": "project_followup", "question": turn.prompt, "corpus_text": turn.answer,
                                          "parent_id": root.corpus_entry_id})
    kind = {"self_intro": "self_intro", "award": "award", "project": "project"}.get(turn.stage, "knowledge")
    return corpus.create_entry(user, {"kind": kind, "question": turn.prompt, "corpus_text": turn.answer})


def score(user, session_id, ai_source=""):
    with transaction.atomic():
        session = _owned(user, session_id, lock=True)
        if session.status != "completed":
            raise InterviewError("请先完成面试，再生成评分。", code="session_not_completed", status=409)
        if (session.score or {}).get("status") == "ready":
            return detail(user, session_id)
        _not_busy(session)
        turns = list(session.turns.filter(status="completed"))
        if not turns:
            raise InterviewError("至少回答一道题才能评分。")
        profile = corpus.profile_for(user)
        inputs = {"part": session.part, "intensity": session.intensity, "has_jd": bool(profile.jd_text),
                  "jd_summary": profile.jd_summary, "turn_ids": [t.public_id for t in turns],
                  "transcript": [{"turn_id": t.public_id, "stage": STAGE_LABELS.get(t.stage, t.stage), "kind": t.kind,
                                  "question": t.prompt, "answer": t.answer[:2000],
                                  "decision": {k: (t.metadata.get("decision") or {}).get(k) for k in ("signal", "evidence", "boundary")},
                                  "reply": (t.metadata or {}).get("reply", "")} for t in turns]}
        token = _lease(session, "score")
    try:
        result = ai_services.run_generation(user, "score_report", inputs, ai_source=ai_source, related_id=session_id)
        state = {"status": "ready", **result, "limitations": SCORE_LIMITATION, "generated_at": timezone.now().isoformat()}
        failure = None
    except InterviewError as exc:
        state = {"status": "failed", "error": str(exc), "code": exc.code, "limitations": SCORE_LIMITATION}
        failure = exc
    try:
        with transaction.atomic():
            session = _owned(user, session_id, lock=True)
            if session.ai_busy_token == token:
                session.score = state
                session.save(update_fields=["score", "updated_at"])
    finally:
        _clear_lease(user, session_id, token)
    if failure is not None:
        raise failure
    return detail(user, session_id)
