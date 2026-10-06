"""The AI assistant: a chat with the interview coach that can write into the candidate's library (agent mode).

The model answers the latest message and, only when asked to save something, returns actions. The server validates
them (ai_schema) and applies them here, so the model never touches the database or files itself.
"""

from django.db import transaction

from . import ai_services, corpus
from .models import InterviewAssistantMessage as Message
from .models import InterviewAssistantThread as Thread
from .models import InterviewCorpusEntry as Entry
from .validation import InterviewError, text

HISTORY = 16
SECTION_KIND = {"project": (Entry.Kind.PROJECT, ""), "intern": (Entry.Kind.PROJECT, "实习"), "award": (Entry.Kind.AWARD, "")}


def _library(user):
    """A compact snapshot so the assistant reuses existing tags / topics / cards instead of inventing parallel ones."""
    entries = [e for e in corpus.corpus_listing(user)["entries"] if not e.get("orphaned")]
    topics = sorted({f"{e['group'] or '自定义'} / {e['title'] or '综合'}" for e in entries if e["kind"] == "knowledge"})
    profile = corpus.profile_for(user)
    return {
        "knowledge_topics": topics[:120],
        "resume_cards": [{"section": "intern" if e["group"] == "实习" else e["kind"], "title": e["title"]}
                         for e in entries if e["kind"] in {"project", "award"}][:40],
        "jd_cards": [e["title"] for e in entries if e["kind"] == "jd"][:20],
        "resume": profile.resume_text[:4000],
        "jd_summary": profile.jd_summary,
    }


def _knowledge(user, action):
    existing = Entry.objects.filter(user=user, kind=Entry.Kind.KNOWLEDGE, group=action["tag"], question=action["question"]).first()
    if existing:
        # Saving the same question again adds to the answer rather than overwriting what is there.
        existing.corpus_text = f"{existing.corpus_text}\n\n---\n\n{action['answer']}".strip() if existing.corpus_text else action["answer"]
        existing.title = existing.title or action["topic"]
        existing.save(update_fields=["corpus_text", "title", "updated_at"])
        return existing
    return Entry.objects.create(user=user, kind=Entry.Kind.KNOWLEDGE, source=Entry.Source.CUSTOM, group=action["tag"],
                                title=action["topic"], question=action["question"], corpus_text=action["answer"])


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
    return card


def _jd(user, action):
    card = Entry.objects.create(user=user, kind=Entry.Kind.JD, source=Entry.Source.CUSTOM, title=action["title"],
                                question=f"「{action['title']}」岗位 JD", corpus_text=action["jd"])
    for order, item in enumerate(action["questions"]):
        Entry.objects.create(user=user, kind=item["kind"], source=Entry.Source.CUSTOM, parent=card, group=action["title"],
                             question=item["question"], corpus_text=item["answer"], order=order)
    return card


def _jd_question(user, action):
    return Entry.objects.create(user=user, kind=action["kind"], source=Entry.Source.CUSTOM, question=action["question"],
                                corpus_text=action["answer"])


APPLY = {
    "knowledge": (_knowledge, "knowledge", lambda a: f"知识点语料库 · {a['tag']}{' / ' + a['topic'] if a['topic'] else ''}"),
    "resume_card": (_resume_card, "resume", lambda a: f"简历题卡 · {a['title']}"),
    "jd": (_jd, "resume", lambda a: f"简历题卡 · JD 与反问 · {a['title']}"),
    "jd_question": (_jd_question, "jd", lambda a: "JD 与反问 · " + ("反问" if a["kind"] == "reverse_question" else "岗位题")),
}


def apply_actions(user, actions):
    applied = []
    with transaction.atomic():
        for action in actions:
            write, where, label = APPLY[action["type"]]
            entry = write(user, action)
            applied.append({"type": action["type"], "where": where, "label": label(action), "entry_id": entry.entry_id})
    return applied


# A save target picked in the composer is passed to the model as an instruction on the latest message.
TARGET_NOTES = {
    "knowledge": "请把要点总结成知识点题卡，保存到「知识点语料库」（沿用已有的 tag 和题卡）。",
    "resume": "请整理成 简述 + 简历原文 + STAR 正文 的题卡，保存到「简历题卡」。",
    "jd": "请整理成 JD 卡（JD 正文）和岗位题 / 反问，保存到「JD 与反问」。",
}


def _thread(user, thread_id):
    thread = Thread.objects.filter(user=user, thread_id=thread_id).first()
    if not thread:
        raise InterviewError("这段对话不存在或已删除。", code="not_found", status=404)
    return thread


def _message_payload(message):
    return {"id": message.message_id, "role": message.role, "content": message.content, "target": message.target,
            "applied": message.applied, "steps": message.steps, "model": message.model, "created_at": message.created_at.isoformat()}


def _thread_payload(thread):
    return {"id": thread.thread_id, "title": thread.title or "新对话", "updated_at": thread.updated_at.isoformat()}


def threads(user):
    return {"threads": [_thread_payload(t) for t in Thread.objects.filter(user=user).order_by("-updated_at")[:100]]}


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


def _steps(library, result, actions, applied):
    """The agent trace shown under a reply: what it read, which model answered, what it wrote."""
    steps = [{"kind": "library", "label": "读取语料库快照",
              "detail": f"知识点题卡 {len(library['knowledge_topics'])} 个 · 简历题卡 {len(library['resume_cards'])} 张 · JD {len(library['jd_cards'])} 张"},
             {"kind": "model", "label": "生成回答", "detail": f"{result.get('model') or 'AI'} · {round((result.get('elapsed_ms') or 0) / 1000, 1)} s"}]
    if actions:
        steps.append({"kind": "validate", "label": "校验写入动作", "detail": f"{len(actions)} 个动作通过校验"})
        steps += [{"kind": "write", "label": item["label"], "where": item["where"], "entry_id": item["entry_id"]} for item in applied]
    return steps


def send(user, payload):
    """Answer the next message in a thread (a new thread when none is given); writes only after the model succeeds."""
    message = text(payload.get("message"), "message", 8000, required=True)
    target = payload.get("target") if payload.get("target") in TARGET_NOTES else ""
    thread = _thread(user, payload["thread_id"]) if payload.get("thread_id") else None
    history = [{"role": m.role, "content": m.content} for m in thread.messages.all()] if thread else []
    asked = f"{message}\n\n{TARGET_NOTES[target]}" if target else message
    conversation = (history + [{"role": "user", "content": asked}])[-HISTORY:]
    library = _library(user)
    result = ai_services.run_generation(user, "assistant", {"conversation": conversation, "library": library},
                                        ai_source=payload.get("ai_source", ""))
    with transaction.atomic():
        if thread is None:
            thread = Thread.objects.create(user=user, title=(result.get("title") or message.splitlines()[0])[:40])
        asked_message = Message.objects.create(thread=thread, role=Message.Role.USER, content=message, target=target)
        applied = apply_actions(user, result["actions"])
        reply = Message.objects.create(thread=thread, role=Message.Role.ASSISTANT, content=result["reply"], applied=applied,
                                       steps=_steps(library, result, result["actions"], applied), model=result.get("model", ""))
        thread.save(update_fields=["updated_at"])
    return {"thread": _thread_payload(thread), "message": _message_payload(asked_message), "reply": _message_payload(reply),
            **corpus.corpus_listing(user)}
