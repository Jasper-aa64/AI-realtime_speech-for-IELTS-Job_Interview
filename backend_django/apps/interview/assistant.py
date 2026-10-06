"""The AI assistant: a chat with the interview coach. In agent mode it also manages the candidate's library.

The model answers the latest message and, in agent mode, returns actions (create / update / delete cards). The server
validates them (ai_schema) and applies them here, so the model never touches the database itself. Every applied
change records how to reverse it, and a reply's changes can be undone as a whole.
"""

from django.conf import settings
from django.db import transaction

from . import ai_services, corpus
from .models import InterviewAssistantMessage as Message
from .models import InterviewAssistantThread as Thread
from .models import InterviewCorpusEntry as Entry
from .validation import InterviewError, text

HISTORY = 16
MODES = {"chat", "agent"}
SNAPSHOT_CARDS = 240
CLIP = 1500  # longer answers reach the model truncated, with their full length
SECTION_KIND = {"project": (Entry.Kind.PROJECT, ""), "intern": (Entry.Kind.PROJECT, "实习"), "award": (Entry.Kind.AWARD, "")}
AREA = {"knowledge": "知识点语料库", "resume": "简历题卡", "jd": "JD 与反问"}
OP_WORD = {"create": "新建", "update": "修改", "delete": "删除"}
SNAPSHOT_FIELDS = ("kind", "group", "title", "question", "corpus_text", "ai_draft", "source", "source_key", "order", "metadata")
UPDATED_FIELDS = ("group", "title", "question", "corpus_text", "metadata")


# ---- What the model sees

def _clip(value):
    return value if len(value) <= CLIP else f"{value[:CLIP]}…(共 {len(value)} 字)"


def _card(entry):
    card = {"id": entry.entry_id, "kind": entry.kind, "group": entry.group, "title": entry.title,
            "question": entry.question, "answer": _clip(entry.corpus_text)}
    if (entry.metadata or {}).get("resume_excerpt"):
        card["resume_excerpt"] = _clip(entry.metadata["resume_excerpt"])
    if entry.parent_id:
        card["parent"] = entry.parent.entry_id
    return card


def _library(user):
    """The candidate's own cards with ids (so the agent can edit and delete them) plus the bank's topic names."""
    own = [e for e in Entry.objects.filter(user=user).select_related("parent") if not (e.metadata or {}).get("orphaned")]
    bank = sorted({f"{e['group']} / {e['title']}" for e in corpus.corpus_listing(user, "knowledge")["entries"] if e["id"] is None})
    profile = corpus.profile_for(user)
    return {"cards": [_card(e) for e in own[:SNAPSHOT_CARDS]], "bank_topics": bank[:150],
            "resume": profile.resume_text[:4000], "jd_summary": profile.jd_summary}


# ---- Labels

def _where(entry):
    if entry.kind in {Entry.Kind.KNOWLEDGE, Entry.Kind.SELF_INTRO}:  # 自我介绍 sits in the knowledge library for now
        return "knowledge"
    if entry.kind in {Entry.Kind.JD_QUESTION, Entry.Kind.REVERSE_QUESTION} and not entry.parent_id:
        return "jd"
    return "resume"


def _name(entry):
    if entry.kind == Entry.Kind.KNOWLEDGE:
        return " / ".join(part for part in (entry.group, entry.title) if part) or entry.question[:24]
    if entry.kind == Entry.Kind.PROJECT_FOLLOWUP or entry.parent_id:
        return f"{entry.parent.title or entry.parent.question[:16]} · {entry.question[:20]}" if entry.parent_id else entry.question[:24]
    if entry.kind in {Entry.Kind.JD_QUESTION, Entry.Kind.REVERSE_QUESTION}:
        return entry.question[:24]
    return entry.title or entry.question[:24]


def _change(op, entry, undo):
    return {"op": op, "where": _where(entry), "label": f"{AREA[_where(entry)]} · {_name(entry)}",
            "entry_id": None if op == "delete" else entry.entry_id}, undo


# ---- Writers: each returns (applied item, undo record)

def _snapshot(entry):
    row = {name: getattr(entry, name) for name in SNAPSHOT_FIELDS}
    return {**row, "entry_id": entry.entry_id, "parent": entry.parent.entry_id if entry.parent_id else None}


def _subtree(entry):
    rows = [_snapshot(entry)]
    for child in entry.children.select_related("parent").order_by("order", "pk"):
        rows += _subtree(child)
    return rows


def _owned(user, entry_id):
    entry = Entry.objects.select_related("parent").filter(user=user, entry_id=entry_id).first()
    if not entry:
        raise InterviewError(f"找不到题卡 {entry_id}")
    return entry


def _knowledge(user, action):
    existing = Entry.objects.filter(user=user, kind=Entry.Kind.KNOWLEDGE, group=action["tag"], question=action["question"]).first()
    if existing:
        # The same question again adds to the answer rather than overwriting what is there.
        before = {name: getattr(existing, name) for name in UPDATED_FIELDS}
        existing.corpus_text = f"{existing.corpus_text}\n\n---\n\n{action['answer']}".strip() if existing.corpus_text else action["answer"]
        existing.title = existing.title or action["topic"]
        existing.save(update_fields=["corpus_text", "title", "updated_at"])
        return _change("update", existing, {"op": "updated", "entry_id": existing.entry_id, "before": before})
    entry = Entry.objects.create(user=user, kind=Entry.Kind.KNOWLEDGE, source=Entry.Source.CUSTOM, group=action["tag"],
                                 title=action["topic"], question=action["question"], corpus_text=action["answer"])
    return _change("create", entry, {"op": "created", "entry_id": entry.entry_id})


def _resume_card(user, action):
    kind, group = SECTION_KIND[action["section"]]
    title = action["title"]
    question = (f"讲讲你的「{title}」经历。" if kind == Entry.Kind.AWARD
                else f"介绍一下你在「{title}」的实习。" if group else f"介绍一下你的「{title}」项目。")
    card = Entry.objects.create(user=user, kind=kind, source=Entry.Source.CUSTOM, group=group, title=title, question=question,
                                corpus_text=action["star"], metadata={"resume_excerpt": action["resume_excerpt"]})
    for order, item in enumerate(action["follow_ups"]):
        Entry.objects.create(user=user, kind=Entry.Kind.PROJECT_FOLLOWUP, source=Entry.Source.CUSTOM, parent=card, title=title,
                             question=item["question"], corpus_text=item["answer"], order=order)
    return _change("create", card, {"op": "created", "entry_id": card.entry_id})


def _jd(user, action):
    card = Entry.objects.create(user=user, kind=Entry.Kind.JD, source=Entry.Source.CUSTOM, title=action["title"],
                                question=f"「{action['title']}」岗位 JD", corpus_text=action["jd"])
    for order, item in enumerate(action["questions"]):
        Entry.objects.create(user=user, kind=item["kind"], source=Entry.Source.CUSTOM, parent=card, group=action["title"],
                             question=item["question"], corpus_text=item["answer"], order=order)
    return _change("create", card, {"op": "created", "entry_id": card.entry_id})


def _jd_question(user, action):
    entry = Entry.objects.create(user=user, kind=action["kind"], source=Entry.Source.CUSTOM, question=action["question"],
                                 corpus_text=action["answer"])
    return _change("create", entry, {"op": "created", "entry_id": entry.entry_id})


def _update(user, action):
    entry = _owned(user, action["id"])
    before = {name: getattr(entry, name) for name in UPDATED_FIELDS}
    payload = {name: action[name] for name in ("group", "title", "question", "resume_excerpt") if name in action}
    if "answer" in action:
        payload["corpus_text"] = action["answer"]
    if "append_answer" in action:
        base = payload.get("corpus_text", entry.corpus_text)
        payload["corpus_text"] = f"{base}\n\n{action['append_answer']}".strip() if base else action["append_answer"]
    corpus.update_entry(user, entry.entry_id, payload)  # same rules as the editor (bank questions stay read-only)
    entry.refresh_from_db()
    return _change("update", entry, {"op": "updated", "entry_id": entry.entry_id, "before": before})


def _delete(user, action):
    entry = _owned(user, action["id"])
    change = _change("delete", entry, {"op": "deleted", "rows": _subtree(entry)})
    entry.delete()
    return change


WRITERS = {"knowledge": _knowledge, "resume_card": _resume_card, "jd": _jd, "jd_question": _jd_question,
           "update": _update, "delete": _delete}


def apply_actions(user, actions):
    """Applies what it can: an action naming a missing card (or breaking a rule) is skipped, not fatal."""
    applied, skipped, undo = [], [], []
    for action in actions:
        try:
            with transaction.atomic():
                item, record = WRITERS[action["type"]](user, action)
        except InterviewError as exc:
            skipped.append({"kind": "skip", "label": f"跳过{OP_WORD.get(action['type'], '新建')}", "detail": str(exc)})
            continue
        applied.append(item)
        undo.append(record)
    return applied, skipped, undo


# ---- Threads

def _thread(user, thread_id):
    thread = Thread.objects.filter(user=user, thread_id=thread_id).first()
    if not thread:
        raise InterviewError("这段对话不存在或已删除。", code="not_found", status=404)
    return thread


def _message_payload(message):
    return {"id": message.message_id, "role": message.role, "content": message.content, "mode": message.mode,
            "applied": message.applied, "steps": message.steps, "model": message.model,
            "undoable": bool(message.undo) and not message.undone, "undone": message.undone,
            "created_at": message.created_at.isoformat()}


def _thread_payload(thread):
    return {"id": thread.thread_id, "title": thread.title or "新对话", "updated_at": thread.updated_at.isoformat()}


def _engine():
    """What answers, for the chip in the assistant's corner: the local Codex model and its reasoning effort."""
    if getattr(settings, "INTERVIEW_AI_SOURCE", "") != "codex_cli":
        return ""
    return " · ".join(part for part in ("本机 Codex", settings.CODEX_MODEL, getattr(settings, "CODEX_INTERVIEW_EFFORT", "")) if part)


def threads(user):
    return {"threads": [_thread_payload(t) for t in Thread.objects.filter(user=user).order_by("-updated_at")[:100]], "engine": _engine()}


def thread_detail(user, thread_id):
    thread = _thread(user, thread_id)
    return {"thread": _thread_payload(thread), "messages": [_message_payload(m) for m in thread.messages.all()]}


def rename(user, thread_id, payload):
    thread = _thread(user, thread_id)
    thread.title = text(payload.get("title"), "title", 80, required=True)
    thread.save(update_fields=["title", "updated_at"])
    return {"thread": _thread_payload(thread)}


def delete(user, thread_id):
    _thread(user, thread_id).delete()
    return {"deleted": thread_id}


def _history_entry(message):
    """An assistant turn carries a note of what it changed, so the model knows its own past actions."""
    content = message.content
    if message.role == Message.Role.ASSISTANT and message.applied:
        done = "；".join(f"{OP_WORD[item['op']]} {item['label']}" for item in message.applied)
        content += f"\n\n[本轮已执行：{done}{'（用户已撤销）' if message.undone else ''}]"
    return {"role": message.role, "content": content}


def _steps(library, result, actions, applied, skipped):
    """The agent trace shown under a reply: what it read, which model answered, what it changed."""
    effort = f" · 推理 {result['effort']}" if result.get("effort") else ""
    steps = [{"kind": "library", "label": "读取语料库快照", "detail": f"你的题卡 {len(library['cards'])} 张 · 题库方向 {len(library['bank_topics'])} 个"},
             {"kind": "model", "label": "生成回答", "detail": f"{result.get('model') or 'AI'}{effort} · {round((result.get('elapsed_ms') or 0) / 1000, 1)} s"}]
    rejected = result.get("rejected") or 0
    if actions or rejected:
        detail = f"{len(actions)} 个动作通过校验" + (f"，{rejected} 个格式不对已丢弃" if rejected else "")
        steps.append({"kind": "validate", "label": "校验动作", "detail": detail})
    steps += [{"kind": item["op"], "label": f"{OP_WORD[item['op']]} {item['label']}", "where": item["where"], "entry_id": item["entry_id"]}
              for item in applied]
    return steps + skipped


def send(user, payload):
    """Answer the next message in a thread (a new thread when none is given); writes only after the model succeeds."""
    message = text(payload.get("message"), "message", 8000, required=True)
    mode = payload.get("mode") if payload.get("mode") in MODES else "chat"
    thread = _thread(user, payload["thread_id"]) if payload.get("thread_id") else None
    history = [_history_entry(m) for m in thread.messages.all()] if thread else []
    conversation = (history + [{"role": "user", "content": message}])[-HISTORY:]
    library = _library(user)
    result = ai_services.run_generation(user, "assistant", {"mode": mode, "conversation": conversation, "library": library},
                                        ai_source=payload.get("ai_source", ""))
    actions = result["actions"] if mode == "agent" else []
    with transaction.atomic():
        if thread is None:
            thread = Thread.objects.create(user=user, title=(result.get("title") or message.splitlines()[0])[:40])
        asked = Message.objects.create(thread=thread, role=Message.Role.USER, content=message, mode=mode)
        applied, skipped, undo = apply_actions(user, actions)
        reply = Message.objects.create(thread=thread, role=Message.Role.ASSISTANT, content=result["reply"], mode=mode,
                                       applied=applied, undo=undo, steps=_steps(library, result, actions, applied, skipped),
                                       model=result.get("model", ""))
        thread.save(update_fields=["updated_at"])
    return {"thread": _thread_payload(thread), "message": _message_payload(asked), "reply": _message_payload(reply),
            **corpus.corpus_listing(user)}


def undo(user, message_id):
    """Reverses everything one reply changed, newest change first."""
    message = Message.objects.select_related("thread").filter(message_id=message_id, thread__user=user).first()
    if not message:
        raise InterviewError("找不到这条回复。", code="not_found", status=404)
    if message.undone or not message.undo:
        raise InterviewError("这条回复没有可撤销的修改。", code="nothing_to_undo", status=409)
    with transaction.atomic():
        for record in reversed(message.undo):
            if record["op"] == "created":
                Entry.objects.filter(user=user, entry_id=record["entry_id"]).delete()
            elif record["op"] == "updated":
                entry = Entry.objects.filter(user=user, entry_id=record["entry_id"]).first()
                if entry:
                    for name, value in record["before"].items():
                        setattr(entry, name, value)
                    entry.save()
            elif record["op"] == "deleted":
                _restore(user, record["rows"])
        message.undone = True
        message.save(update_fields=["undone"])
    return {"message": _message_payload(message), **corpus.corpus_listing(user)}


def _restore(user, rows):
    restored = {}
    for row in rows:  # parents come before their follow-ups
        if Entry.objects.filter(entry_id=row["entry_id"]).exists() or \
                (row["source_key"] and Entry.objects.filter(user=user, source_key=row["source_key"]).exists()):
            continue
        parent = restored.get(row["parent"]) or (Entry.objects.filter(user=user, entry_id=row["parent"]).first() if row["parent"] else None)
        if row["parent"] and parent is None:
            continue
        fields = {name: row[name] for name in SNAPSHOT_FIELDS}
        restored[row["entry_id"]] = Entry.objects.create(user=user, entry_id=row["entry_id"], parent=parent, **fields)
