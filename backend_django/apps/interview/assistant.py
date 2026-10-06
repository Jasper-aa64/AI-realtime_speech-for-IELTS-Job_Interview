"""The AI assistant: a chat with the interview coach that can write into the candidate's library (agent mode).

The model answers the latest message and, only when asked to save something, returns actions. The server validates
them (ai_schema) and applies them here, so the model never touches the database or files itself.
"""

from django.db import transaction

from . import ai_services, corpus
from .models import InterviewCorpusEntry as Entry
from .validation import InterviewError, text

HISTORY = 16
SECTION_KIND = {"project": (Entry.Kind.PROJECT, ""), "intern": (Entry.Kind.PROJECT, "实习"), "award": (Entry.Kind.AWARD, "")}


def _conversation(payload):
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise InterviewError("请先输入问题。")
    cleaned = []
    for item in messages[-HISTORY:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            raise InterviewError("对话格式不正确。")
        cleaned.append({"role": item["role"], "content": text(item.get("content"), "message", 8000, required=True)})
    if cleaned[-1]["role"] != "user":
        raise InterviewError("最后一条应该是你的问题。")
    return cleaned


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


def chat(user, payload):
    conversation = _conversation(payload)
    result = ai_services.run_generation(user, "assistant", {"conversation": conversation, "library": _library(user)},
                                        ai_source=payload.get("ai_source", ""))
    applied = apply_actions(user, result["actions"])
    return {"reply": result["reply"], "applied": applied, "model": result.get("model", ""), **corpus.corpus_listing(user)}
