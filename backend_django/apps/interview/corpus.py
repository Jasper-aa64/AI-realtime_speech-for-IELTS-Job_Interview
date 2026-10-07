"""Interview profile (resume / JD) and the interview corpus.

Mirrors the IELTS speaking corpora: every practice question can carry "my answer" (corpus_text) and
an AI reference (ai_draft). Material split from a resume or JD is keyed by a stable source_key, so a
re-split refreshes AI drafts and questions but never overwrites what the candidate wrote.
"""

from django.db import transaction
from django.utils import timezone

from . import ai_schema, ai_services
from .ai_schema import digest
from .bank import CATEGORIES, QUESTIONS
from .models import InterviewCorpusEntry as Entry
from .models import InterviewProfile
from .validation import InterviewError, resume_input, text

KINDS = {choice for choice, _ in Entry.Kind.choices}
EDITABLE_QUESTION_SOURCES = {Entry.Source.CUSTOM, Entry.Source.RESUME, Entry.Source.JD, Entry.Source.PRACTICE}
SELF_INTRO_QUESTION = "请先做一个简单的自我介绍。"
FOLLOW_UP_PARENTS = {Entry.Kind.PROJECT, Entry.Kind.SELF_INTRO, Entry.Kind.AWARD}
# A JD card's follow-ups are that role's questions: role questions and questions to ask.
JD_CHILDREN = {Entry.Kind.JD_QUESTION, Entry.Kind.REVERSE_QUESTION}
CURATED = {question["id"]: question for question in QUESTIONS}
CATEGORY_LABELS = {item["id"]: item["label"] for item in CATEGORIES}


def profile_for(user, *, lock=False):
    queryset = InterviewProfile.objects.select_for_update() if lock else InterviewProfile.objects
    profile, _ = queryset.get_or_create(user=user)
    return profile


def profile_payload(profile):
    return {
        "resume": {"text": profile.resume_text, "modules": profile.resume_modules,
                   "updated_at": profile.resume_updated_at.isoformat() if profile.resume_updated_at else None},
        "jd": {"text": profile.jd_text, "summary": profile.jd_summary,
               "updated_at": profile.jd_updated_at.isoformat() if profile.jd_updated_at else None},
    }


def entry_payload(entry):
    return {
        "id": entry.entry_id, "kind": entry.kind, "group": entry.group, "title": entry.title,
        "question": entry.question, "corpus_text": entry.corpus_text, "ai_draft": entry.ai_draft,
        "source": entry.source, "source_key": entry.source_key,
        "parent_id": entry.parent.entry_id if entry.parent_id else None, "order": entry.order,
        "orphaned": bool((entry.metadata or {}).get("orphaned")), "summary": (entry.metadata or {}).get("summary", ""),
        "resume_excerpt": (entry.metadata or {}).get("resume_excerpt", ""),
        "updated_at": entry.updated_at.isoformat(),
    }


def _owned(user, entry_id, *, lock=False):
    queryset = Entry.objects.select_for_update() if lock else Entry.objects
    entry = queryset.select_related("parent").filter(user=user, entry_id=entry_id).first()
    if not entry:
        raise InterviewError("找不到这条语料。", code="not_found", status=404)
    return entry


def _upsert(user, *, source_key, kind, question, source, ai_draft="", group="", title="", parent=None, order=0, metadata=None):
    entry = Entry.objects.select_for_update().filter(user=user, source_key=source_key).first()
    # A re-split refreshes the AI's 简述 / 简历原文 unless the candidate has rewritten them.
    edited = set((entry.metadata or {}).get("user_edited", [])) if entry else set()
    meta = {**(entry.metadata if entry else {}), **{k: v for k, v in (metadata or {}).items() if k not in edited}}
    meta.pop("orphaned", None)
    if entry is None:
        return Entry.objects.create(user=user, source_key=source_key, kind=kind, question=question, source=source,
                                    ai_draft=ai_draft, group=group, title=title, parent=parent, order=order, metadata=meta)
    entry.kind, entry.question, entry.source, entry.group, entry.title = kind, question, source, group, title
    entry.parent, entry.order, entry.metadata = parent, order, meta
    if ai_draft:
        entry.ai_draft = ai_draft
    entry.save()
    return entry


def _mark_orphans(user, prefix, kept):
    for entry in Entry.objects.select_for_update().filter(user=user, source_key__startswith=prefix).exclude(source_key__in=kept):
        entry.metadata = {**entry.metadata, "orphaned": True}
        entry.save(update_fields=["metadata", "updated_at"])


def _preview(payload):
    value = payload.get("preview")
    return value is True or str(value).lower() in {"1", "true", "yes"}


def _draft(kind, result):
    """The schema part of an AI result, without task provenance: what the candidate reviews and edits."""
    keys = {"resume_profile": ("self_intro", "projects", "tech_stack", "awards"),
            "jd_profile": ("summary", "questions", "reverse_questions")}[kind]
    return {key: result[key] for key in keys}


def _edited(kind, payload):
    try:
        return ai_schema.validate(kind, payload.get("draft"), {})
    except InterviewError:
        raise
    except (ValueError, TypeError, AttributeError):
        raise InterviewError("草稿里没有可加入语料库的内容。", code="invalid_draft") from None


# Resume / JD 定制: generate a draft first (preview), let the candidate edit it, then commit it to the corpus.
def import_resume(user, payload, upload=None):
    resume = resume_input(payload.get("resume_text", ""), upload)
    result = ai_services.run_generation(user, "resume_profile", {"resume_text": resume}, ai_source=payload.get("ai_source", ""))
    if _preview(payload):
        return {"draft": _draft("resume_profile", result), "resume_text": resume}
    return _apply_resume(user, resume, result)


def commit_resume(user, payload):
    resume = text(payload.get("resume_text"), "resume_text", 24000, required=True)
    return _apply_resume(user, resume, _edited("resume_profile", payload))


def _apply_resume(user, resume, result):
    with transaction.atomic():
        profile = profile_for(user, lock=True)
        kept, modules = [], []
        intro_draft = result["self_intro"]["draft"]
        _upsert(user, source_key="resume:self_intro", kind=Entry.Kind.SELF_INTRO, question=SELF_INTRO_QUESTION,
                source=Entry.Source.RESUME, ai_draft=intro_draft, title="自我介绍")
        kept.append("resume:self_intro")
        modules.append({"key": "self_intro", "kind": "self_intro", "title": "自我介绍", "summary": ""})
        for order, project in enumerate(result["projects"]):
            key = f"resume:project:{project['key']}"
            # Internships are project cards in the 实习 group (the resume screen's 实习 category).
            internship = project.get("type") == "internship"
            question = f"介绍一下你在「{project['title']}」的实习。" if internship else f"介绍一下你的「{project['title']}」项目。"
            parent = _upsert(user, source_key=key, kind=Entry.Kind.PROJECT, question=question, group="实习" if internship else "",
                             source=Entry.Source.RESUME, ai_draft=project["draft"], title=project["title"], order=order,
                             metadata={"summary": project.get("summary", ""), "resume_excerpt": project.get("resume_excerpt", "")})
            kept.append(key)
            modules.append({"key": project["key"], "kind": "project", "title": project["title"], "summary": project["summary"]})
            for index, follow in enumerate(project["followups"]):
                follow_key = f"{key}:fu:{digest(follow['question'])}"
                _upsert(user, source_key=follow_key, kind=Entry.Kind.PROJECT_FOLLOWUP, question=follow["question"],
                        source=Entry.Source.RESUME, ai_draft=follow["draft"], title=project["title"], parent=parent, order=index)
                kept.append(follow_key)
        for group_order, group in enumerate(result["tech_stack"]):
            modules.append({"key": f"tech-{group_order + 1}", "kind": "tech_stack", "title": group["group"], "summary": ""})
            for index, item in enumerate(group["questions"]):
                tech_key = f"resume:tech:{digest(group['group'] + item['question'])}"
                _upsert(user, source_key=tech_key, kind=Entry.Kind.KNOWLEDGE, question=item["question"],
                        source=Entry.Source.RESUME, ai_draft=item["draft"], group=group["group"], order=group_order * 10 + index)
                kept.append(tech_key)
        for order, award in enumerate(result["awards"]):
            key = f"resume:award:{award['key']}"
            _upsert(user, source_key=key, kind=Entry.Kind.AWARD, question=f"讲讲你的「{award['title']}」经历。",
                    source=Entry.Source.RESUME, ai_draft=award["draft"], title=award["title"], order=order,
                    metadata={"summary": award.get("summary", ""), "resume_excerpt": award.get("resume_excerpt", "")})
            kept.append(key)
            modules.append({"key": award["key"], "kind": "award", "title": award["title"], "summary": ""})
        _mark_orphans(user, "resume:", kept)
        profile.resume_text, profile.resume_modules, profile.resume_updated_at = resume, modules, timezone.now()
        profile.save()
    return {"profile": profile_payload(profile), **corpus_listing(user)}


def import_jd(user, payload):
    jd = text(payload.get("job_description"), "job_description", 12000, required=True)
    result = ai_services.run_generation(user, "jd_profile", {"job_description": jd}, ai_source=payload.get("ai_source", ""))
    if _preview(payload):
        return {"draft": _draft("jd_profile", result), "job_description": jd}
    return _apply_jd(user, jd, result)


def commit_jd(user, payload):
    jd = text(payload.get("job_description"), "job_description", 12000, required=True)
    return _apply_jd(user, jd, _edited("jd_profile", payload))


def _apply_jd(user, jd, result):
    with transaction.atomic():
        profile = profile_for(user, lock=True)
        # Every JD is its own card (简述 = role, 正文 = the JD); its questions hang under it, and re-generating the
        # same JD only retires that JD's old questions.
        role = result["summary"]["role"] or "目标岗位"
        prefix = f"jd:{digest(jd)}:"
        card = _upsert(user, source_key=f"{prefix}card", kind=Entry.Kind.JD, question=f"「{role}」岗位 JD", source=Entry.Source.JD,
                       title=role, metadata={"requirements": result["summary"].get("requirements", [])})
        if not card.corpus_text:
            card.corpus_text = jd
            card.save(update_fields=["corpus_text", "updated_at"])
        kept = [f"{prefix}card"]
        for index, item in enumerate(result["questions"]):
            key = f"{prefix}q:{digest(item['question'])}"
            _upsert(user, source_key=key, kind=Entry.Kind.JD_QUESTION, question=item["question"], source=Entry.Source.JD,
                    ai_draft=item["draft"], group=role, parent=card, order=index)
            kept.append(key)
        for index, item in enumerate(result["reverse_questions"]):
            key = f"{prefix}reverse:{digest(item['question'])}"
            _upsert(user, source_key=key, kind=Entry.Kind.REVERSE_QUESTION, question=item["question"], source=Entry.Source.JD,
                    ai_draft=item["draft"], parent=card, order=index)
            kept.append(key)
        _mark_orphans(user, prefix, kept)
        profile.jd_text, profile.jd_summary, profile.jd_updated_at = jd, result["summary"], timezone.now()
        profile.save()
    return {"profile": profile_payload(profile), **corpus_listing(user)}


def corpus_listing(user, kind=""):
    if kind and kind not in KINDS:
        raise InterviewError("Unknown corpus kind", code="invalid_kind")
    entries = Entry.objects.filter(user=user).select_related("parent")
    if kind:
        entries = entries.filter(kind=kind)
    entries = list(entries)
    added = {entry.entry_id: entry.pk for entry in entries}
    saved = [entry_payload(entry) for entry in entries]
    # A bank question's topic is its card; rows saved before topics existed get it from the bank.
    for item in saved:
        curated = CURATED.get(str(item["source_key"] or "").removeprefix("curated:")) if str(item["source_key"] or "").startswith("curated:") else None
        if curated and not item["title"]:
            item["title"] = curated["topic"]
    # Curated bank questions appear in the knowledge corpus even before the candidate writes an answer.
    curated = []
    if not kind or kind == Entry.Kind.KNOWLEDGE:
        taken = {item["source_key"] for item in saved}
        for question in QUESTIONS:
            key = f"curated:{question['id']}"
            if key not in taken:
                curated.append({"id": None, "kind": "knowledge", "group": CATEGORY_LABELS.get(question["category"], question["category"]),
                                "title": question["topic"], "question": question["prompt"], "corpus_text": "", "ai_draft": "",
                                "source": "curated", "source_key": key, "parent_id": None, "order": 0,
                                "orphaned": False, "summary": "", "updated_at": None})
    # Knowledge keeps one stable order, so nothing jumps around: bank questions in bank order whether or not they have an
    # answer yet, then the candidate's own questions in the order they were added (a new direction / topic goes last).
    bank_rank = {f"curated:{question['id']}": index for index, question in enumerate(QUESTIONS)}

    def knowledge_rank(item):
        key = str(item.get("source_key") or "")
        return (0, bank_rank[key]) if key in bank_rank else (1, added.get(item.get("id"), 0))

    listing = saved + curated
    knowledge = sorted((item for item in listing if item["kind"] == Entry.Kind.KNOWLEDGE), key=knowledge_rank)
    profile = InterviewProfile.objects.filter(user=user).only("knowledge_layout").first()
    knowledge = apply_layout(knowledge, profile.knowledge_layout if profile else {})
    return {"entries": [item for item in listing if item["kind"] != Entry.Kind.KNOWLEDGE] + knowledge}


def _tag(item):
    return item.get("group") or "自定义"


def _topic(item):
    return item.get("title") or "综合"


def knowledge_outline(knowledge):
    """[(direction, [topic, ...]), ...] in the order the entries come (first appearance)."""
    outline = {}
    for item in knowledge:
        topics = outline.setdefault(_tag(item), [])
        if _topic(item) not in topics:
            topics.append(_topic(item))
    return list(outline.items())


def _ordered(names, preferred):
    preferred = [name for name in dict.fromkeys(preferred or []) if name in names]
    return preferred + [name for name in names if name not in preferred]


def apply_layout(knowledge, layout):
    """Reorders knowledge entries by the candidate's layout: directions, then topic cards inside each; questions keep their order."""
    if not layout:
        return knowledge
    buckets = {}
    for item in knowledge:
        buckets.setdefault((_tag(item), _topic(item)), []).append(item)
    outline = dict(knowledge_outline(knowledge))
    ordered = []
    for tag in _ordered(list(outline), layout.get("tags")):
        for topic in _ordered(outline[tag], (layout.get("topics") or {}).get(tag)):
            ordered += buckets[(tag, topic)]
    return ordered


def create_entry(user, payload):
    kind = text(payload.get("kind"), "kind", 24, required=True)
    if kind not in KINDS:
        raise InterviewError("Unknown corpus kind", code="invalid_kind")
    source_key = text(payload.get("source_key"), "source_key", 160)
    if source_key and not source_key.startswith("curated:"):
        raise InterviewError("Only curated questions can be referenced by key", code="invalid_source_key")
    curated = CURATED.get(source_key.removeprefix("curated:")) if source_key else None
    if source_key and not curated:
        raise InterviewError("Unknown curated question", code="invalid_source_key")
    parent = None
    if payload.get("parent_id"):
        parent = _owned(user, text(payload.get("parent_id"), "parent_id", 40))
        # Resume cards (a project, the self intro, an award) each keep their own follow-ups, like P2 cards keep P3;
        # a JD card keeps its role questions and questions to ask.
        allowed = (parent.kind in FOLLOW_UP_PARENTS and kind == Entry.Kind.PROJECT_FOLLOWUP) or \
                  (parent.kind == Entry.Kind.JD and kind in JD_CHILDREN)
        if not allowed:
            raise InterviewError("追问只能挂在项目、实习、奖项或 JD 题卡下面。", code="invalid_parent")
    with transaction.atomic():
        if curated:
            existing = Entry.objects.select_for_update().filter(user=user, source_key=source_key).first()
            if existing:
                return {"entry": entry_payload(existing)}
            entry = Entry.objects.create(user=user, kind=Entry.Kind.KNOWLEDGE, source=Entry.Source.CURATED, source_key=source_key,
                                         question=curated["prompt"], group=CATEGORY_LABELS.get(curated["category"], ""), title=curated["topic"],
                                         corpus_text=text(payload.get("corpus_text"), "corpus_text", 12000))
        else:
            entry = Entry.objects.create(user=user, kind=kind, source=Entry.Source.CUSTOM,
                                         question=text(payload.get("question"), "question", 1500, required=True),
                                         title=text(payload.get("title"), "title", 200), group=text(payload.get("group"), "group", 80),
                                         corpus_text=text(payload.get("corpus_text"), "corpus_text", 12000), parent=parent,
                                         metadata=_card_fields(payload))
    return {"entry": entry_payload(entry)}


# A resume card's 简述 and 简历原文 (the STAR body is corpus_text).
CARD_FIELDS = (("summary", 400), ("resume_excerpt", 3000))


def _card_fields(payload):
    return {name: text(payload.get(name), name, limit) for name, limit in CARD_FIELDS if name in payload}


def update_entry(user, entry_id, payload):
    with transaction.atomic():
        entry = _owned(user, entry_id, lock=True)
        fields = []
        if "corpus_text" in payload:
            entry.corpus_text = text(payload.get("corpus_text"), "corpus_text", 12000)
            fields.append("corpus_text")
        if "question" in payload:
            if entry.source not in EDITABLE_QUESTION_SOURCES:
                raise InterviewError("精选题库的题目不能改写。", code="read_only_question")
            entry.question = text(payload.get("question"), "question", 1500, required=True)
            fields.append("question")
        for name, limit in (("title", 200), ("group", 80)):
            if name in payload:
                setattr(entry, name, text(payload.get(name), name, limit))
                fields.append(name)
        card = _card_fields(payload)
        if card:
            edited = sorted(set((entry.metadata or {}).get("user_edited", [])) | set(card))
            entry.metadata = {**(entry.metadata or {}), **card, "user_edited": edited}
            fields.append("metadata")
        if not fields:
            raise InterviewError("Nothing to update")
        entry.save(update_fields=[*fields, "updated_at"])
    return {"entry": entry_payload(entry)}


def delete_entry(user, entry_id):
    with transaction.atomic():
        _owned(user, entry_id, lock=True).delete()
    return {"deleted": entry_id}


def generate_draft(user, entry_id, ai_source=""):
    entry = _owned(user, entry_id)
    profile = profile_for(user)
    context = {"question": entry.question, "kind": entry.kind, "title": entry.title,
               "resume_excerpt": profile.resume_text[:6000], "jd_summary": profile.jd_summary}
    if entry.parent_id:
        context["project"] = {"title": entry.parent.title, "story": (entry.parent.corpus_text or entry.parent.ai_draft)[:3000]}
    result = ai_services.run_generation(user, "corpus_draft", context, ai_source=ai_source, related_id=entry.entry_id)
    with transaction.atomic():
        entry = _owned(user, entry_id, lock=True)
        entry.ai_draft = result["draft"]
        entry.save(update_fields=["ai_draft", "updated_at"])
    return {"entry": entry_payload(entry)}


def practice_material(user):
    """What a session plan can draw on: projects with their stories, awards, knowledge and JD items."""
    # Filtered in Python: a JSON-key exclude also drops rows that simply lack the key (NULL comparison).
    entries = [e for e in Entry.objects.filter(user=user).select_related("parent") if not (e.metadata or {}).get("orphaned")]
    return {kind: [e for e in entries if e.kind == kind] for kind in KINDS}
