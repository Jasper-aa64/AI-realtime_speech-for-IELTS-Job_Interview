"""The AI assistant in IELTS mode: an IELTS coach whose agent mode edits the speaking corpora and Takeaway.

It shares the assistant's threads, trace and undo with interview mode (assistant.py). Writes go through the same
corpus functions the IELTS editors use (apps.speaking.corpus_services), so ids and cleaning rules match; every write
records the row's state before it, so undo puts the row back exactly (or removes it if it did not exist).
"""

from apps.speaking import corpus_services as cs
from apps.speaking.exceptions import SpeakingError
from apps.speaking.models import LanguageTakeawayEntry, P1CorpusEntry, P2BankCorpusEntry, P2CorpusEntry, P3BankFollowupCorpusEntry
from apps.speaking.text_utils import clean_takeaway_text

from .validation import InterviewError

CLIP = 600
SAVED_LIMIT = 260
TAKEAWAY_LIMIT = 150
# id prefix → (model, key field, fields an undo restores)
TABLES = {
    "p1": (P1CorpusEntry, "question_id", ("topic", "question", "corpus_text", "last_ai_answer", "metadata")),
    "p2a": (P2BankCorpusEntry, "question_id", ("question", "corpus_text", "last_ai_answer", "metadata")),
    "p3a": (P3BankFollowupCorpusEntry, "followup_id", ("p2_question_id", "followup_question", "corpus_text", "last_ai_answer", "metadata")),
    "p2m": (P2CorpusEntry, "entry_id", ("category", "title", "material_text", "linked_question", "metadata")),
    "tk": (LanguageTakeawayEntry, "entry_id", ("source_text", "chinese_text", "source_language", "target_language",
                                               "context_url", "context_label", "metadata")),
}
WHERE = {"p1": "p1", "p2a": "p2", "p3a": "p2", "p2m": "p2", "tk": "takeaway"}
CATEGORY_LABEL = {item["category"]: item["label"] for item in cs.P2_CORPUS_CATEGORIES}


def _clip(value):
    value = str(value or "")
    return value if len(value) <= CLIP else f"{value[:CLIP]}…(共 {len(value)} 字)"


# ---- The bank (current season) and the candidate's saved items

def _bank():
    bank = cs.get_question_bank()
    scope = cs.normalize_question_bank_scope(None)
    p1 = [(str(item.get("topic") or "intro"), str(item.get("question") or "")) for item in cs.P1_INTRO_QUESTIONS]
    p1 += [(str(item.get("topic") or "general"), str(item.get("question") or "")) for item in bank.part1_for_scope(scope)]
    p2 = bank.part2_for_scope(scope)
    return [(topic, question) for topic, question in p1 if question], p2


def _p3_questions(topic):
    return [cs.clean_report_text(str(item))[:260] for item in (topic or {}).get("p3_follow_ups", []) if cs.clean_report_text(str(item))]


def library(user, agent):
    p1, p2 = _bank()
    saved = []
    for entry in P1CorpusEntry.objects.filter(user=user).exclude(corpus_text=""):
        saved.append({"id": f"p1:{entry.question_id}", "kind": "p1", "topic": entry.topic, "question": entry.question, "answer": _clip(entry.corpus_text)})
    titles = {}
    for topic in p2:
        titles[str(topic.get("cue_id") or cs.p2_cue_id(topic))] = str(topic.get("title") or "")
    for entry in P2BankCorpusEntry.objects.filter(user=user).exclude(corpus_text=""):
        saved.append({"id": f"p2a:{entry.question_id}", "kind": "p2_answer", "cue_id": entry.question_id,
                      "title": titles.get(entry.question_id) or entry.question[:80], "answer": _clip(entry.corpus_text)})
    for entry in P3BankFollowupCorpusEntry.objects.filter(user=user).exclude(corpus_text=""):
        saved.append({"id": f"p3a:{entry.followup_id}", "kind": "p3_answer", "cue_id": entry.p2_question_id,
                      "question": entry.followup_question, "answer": _clip(entry.corpus_text)})
    for entry in P2CorpusEntry.objects.filter(user=user):
        saved.append({"id": f"p2m:{entry.entry_id}", "kind": "p2_material", "category": entry.category, "title": entry.title,
                      "material": _clip(entry.material_text), "p3_follow_up": _clip((entry.metadata or {}).get("p3_follow_up_text", ""))})
    takeaways = [{"id": f"tk:{entry.entry_id}", "text": entry.source_text, "chinese": entry.chinese_text}
                 for entry in cs.language_takeaway_queryset(user).order_by("-created_at")[:TAKEAWAY_LIMIT]]
    snapshot = {"saved": saved[:SAVED_LIMIT], "takeaways": takeaways}
    if agent:
        grouped = {}
        for topic, question in p1:
            grouped.setdefault(topic, []).append(question)
        snapshot["p1_bank"] = grouped
        snapshot["p2_bank"] = [{"cue_id": str(topic.get("cue_id") or cs.p2_cue_id(topic)), "title": topic.get("title"),
                                "p3": _p3_questions(topic)} for topic in p2]
    return snapshot


def library_detail(snapshot):
    detail = f"你的语料 {len(snapshot['saved'])} 条 · Takeaway {len(snapshot['takeaways'])} 条"
    if "p1_bank" in snapshot:
        detail += f" · 题库 P1 {sum(len(items) for items in snapshot['p1_bank'].values())} 题 / P2 {len(snapshot['p2_bank'])} 张"
    return detail


# ---- Undo: a row's state before the write (None = it did not exist)

def _state(user, prefix, key):
    model, field, fields = TABLES[prefix]
    row = model.objects.filter(user=user, **{field: key}).first()
    return {name: getattr(row, name) for name in fields} if row else None


def restore(user, record):
    model, field, _fields = TABLES[record["table"]]
    if record["before"] is None:
        model.objects.filter(user=user, **{field: record["key"]}).delete()
    else:
        model.objects.update_or_create(user=user, **{field: record["key"]}, defaults=record["before"])


def _change(op, prefix, key, label, before):
    item = {"op": op, "where": WHERE[prefix], "label": label, "entry_id": None if op == "delete" else f"{prefix}:{key}"}
    return item, {"table": prefix, "key": key, "before": before}


def _joined(existing, addition):
    return f"{existing}\n\n{addition}".strip() if existing else addition


# ---- Writers

def _p1_target(user, question):
    wanted = cs.stable_question_text(question)
    p1, _p2 = _bank()
    for topic, text in p1:
        if cs.stable_question_text(text) == wanted:
            return topic, text
    # A question saved earlier (an older season) can still be answered.
    entry = P1CorpusEntry.objects.filter(user=user, question__iexact=question.strip()).first()
    if entry:
        return entry.topic, entry.question
    raise InterviewError(f"题库里没有这道 P1 题：{question[:40]}")


def _p1(user, topic, question, text, append):
    key = cs.p1_question_id(topic, question)
    before = _state(user, "p1", key)
    new_text = _joined((before or {}).get("corpus_text", ""), text) if append else text
    payload = {"topic": topic, "question": question, "corpus_text": new_text, "source": "assistant"}
    if before:
        payload["last_ai_answer"] = before["last_ai_answer"]
    cs.save_p1_corpus(user, payload)
    return _change("update" if before else "create", "p1", key, f"P1 语料 · {cs.p1_topic_label(topic)} · {question[:36]}", before)


def _cue(cue_id):
    topic = cs.p2_bank_topic_for_question_id(cue_id)
    if not topic:
        raise InterviewError(f"题库里没有这张 P2 题卡：{cue_id}")
    return topic


def _p2_answer(user, cue_id, text, append):
    topic = _cue(cue_id)
    before = _state(user, "p2a", cue_id)
    cs.save_p2_bank_corpus(user, cue_id, {"corpus_text": _joined((before or {}).get("corpus_text", ""), text) if append else text})
    return _change("update" if before else "create", "p2a", cue_id, f"P2 题卡 · {topic.get('title', '')[:40]}", before)


def _p3_answer(user, cue_id, index, text, append):
    questions = _p3_questions(_cue(cue_id))
    if not 0 <= index < len(questions):
        raise InterviewError(f"这张 P2 题卡没有第 {index + 1} 道 P3 追问")
    question = questions[index]
    key = cs.p3_bank_followup_id(cue_id, question, index)
    before = _state(user, "p3a", key)
    cs.save_p3_bank_followup_corpus(user, key, {
        "p2_question_id": cue_id, "followup_question": question,
        "corpus_text": _joined((before or {}).get("corpus_text", ""), text) if append else text,
        "last_ai_answer": (before or {}).get("last_ai_answer", ""), "metadata": (before or {}).get("metadata") or {},
    })
    return _change("update" if before else "create", "p3a", key, f"P3 追问 · {question[:40]}", before)


def _p2_material(user, fields, entry_id=""):
    key = entry_id or cs.p2_entry_id(fields["category"], fields["title"], "")
    before = _state(user, "p2m", key)
    cs.save_p2_corpus(user, {**fields, "entry_id": key, "source": "assistant"})
    label = f"P2 素材 · {CATEGORY_LABEL.get(fields['category'], '素材')} · {fields['title'][:36]}"
    return _change("update" if before else "create", "p2m", key, label, before)


def _takeaway(user, text, chinese, entry_id=""):
    key = entry_id or cs.takeaway_entry_id(clean_takeaway_text(text)[:1000])
    before = _state(user, "tk", key)
    payload = {"source_text": text, "chinese_text": chinese, "entry_id": key, "source": "assistant"}
    if before:
        payload.update({k: before[k] for k in ("source_language", "target_language", "context_url", "context_label")})
        payload["source"] = (before.get("metadata") or {}).get("saved_from") or "assistant"
    cs.save_language_takeaway(user, payload)
    return _change("update" if before else "create", "tk", key, f"Takeaway · {text[:40]}", before)


def _split(item_id):
    prefix, _, key = str(item_id or "").partition(":")
    if prefix not in TABLES or not key:
        raise InterviewError(f"不认识的语料 id：{item_id}")
    return prefix, key


def _update(user, action):
    prefix, key = _split(action["id"])
    before = _state(user, prefix, key)
    if before is None:
        raise InterviewError(f"找不到这条语料：{action['id']}")
    answer, append = (action["append_answer"], True) if "append_answer" in action else (action.get("answer"), False)
    if prefix == "p1":
        if answer is None:
            raise InterviewError("P1 语料只能改答法")
        return _p1(user, before["topic"], before["question"], answer, append)
    if prefix == "p2a":
        if answer is None:
            raise InterviewError("P2 题卡只能改答法")
        return _p2_answer(user, key, answer, append)
    if prefix == "p3a":
        if answer is None:
            raise InterviewError("P3 追问只能改答法")
        topic = _cue(before["p2_question_id"])
        questions = _p3_questions(topic)
        index = next((i for i, q in enumerate(questions) if cs.p3_bank_followup_id(before["p2_question_id"], q, i) == key), -1)
        return _p3_answer(user, before["p2_question_id"], index, answer, append)
    if prefix == "p2m":
        meta = before.get("metadata") or {}
        material = action.get("material", before["material_text"])
        if "append_material" in action:
            material = _joined(before["material_text"], action["append_material"])
        return _p2_material(user, {
            "category": action["category"] if action.get("category") in CATEGORY_LABEL else before["category"],
            "title": action.get("title", before["title"]),
            "material_text": material, "p3_follow_up_text": action.get("p3_follow_up", meta.get("p3_follow_up_text", "")),
            "linked_question": before["linked_question"],
        }, entry_id=key)
    return _takeaway(user, action.get("text", before["source_text"]), action.get("chinese", before["chinese_text"]), entry_id=key)


def _delete(user, action):
    prefix, key = _split(action["id"])
    before = _state(user, prefix, key)
    if before is None:
        raise InterviewError(f"找不到这条语料：{action['id']}")
    model, field, _fields = TABLES[prefix]
    label = {
        "p1": lambda: f"P1 语料 · {before['question'][:36]}",
        "p2a": lambda: f"P2 题卡答法 · {before['question'][:36]}",
        "p3a": lambda: f"P3 追问 · {before['followup_question'][:36]}",
        "p2m": lambda: f"P2 素材 · {before['title'][:36]}",
        "tk": lambda: f"Takeaway · {before['source_text'][:36]}",
    }[prefix]()
    model.objects.filter(user=user, **{field: key}).delete()
    return _change("delete", prefix, key, label, before)


def _write(user, action):
    kind = action["type"]
    if kind == "p1_answer":
        topic, question = _p1_target(user, action["question"])
        return _p1(user, topic, question, action["answer"], action["append"])
    if kind == "p2_answer":
        return _p2_answer(user, action["cue_id"], action["answer"], action["append"])
    if kind == "p3_answer":
        return _p3_answer(user, action["cue_id"], action["index"], action["answer"], action["append"])
    if kind == "p2_material":
        return _p2_material(user, {"category": action["category"], "title": action["title"], "material_text": action["material"],
                                   "p3_follow_up_text": action["p3_follow_up"], "linked_question": ""})
    if kind == "takeaway":
        return _takeaway(user, action["text"], action["chinese"])
    if kind == "update":
        return _update(user, action)
    return _delete(user, action)


def write(user, action):
    """One action → (applied item, undo record); corpus-rule violations become InterviewError (skipped, not fatal)."""
    try:
        return _write(user, action)
    except SpeakingError as exc:
        raise InterviewError(str(exc)) from None
