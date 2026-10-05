"""Interview profile (resume / JD) and the interview corpus.

Mirrors the IELTS speaking corpora: every practice question can carry "my answer" (corpus_text) and
an AI reference (ai_draft). Material split from a resume or JD is keyed by a stable source_key, so a
re-split refreshes AI drafts and questions but never overwrites what the candidate wrote.
"""

from django.db import transaction
from django.utils import timezone

from . import ai_services
from .ai_schema import digest
from .bank import CATEGORIES, QUESTIONS
from .models import InterviewCorpusEntry as Entry
from .models import InterviewProfile
from .validation import InterviewError, resume_input, text

KINDS = {choice for choice, _ in Entry.Kind.choices}
EDITABLE_QUESTION_SOURCES = {Entry.Source.CUSTOM, Entry.Source.RESUME, Entry.Source.JD, Entry.Source.PRACTICE}
SELF_INTRO_QUESTION = "请先做一个简单的自我介绍。"
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
    meta = {**(entry.metadata if entry else {}), **(metadata or {})}
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


def import_resume(user, payload, upload=None):
    resume = resume_input(payload.get("resume_text", ""), upload)
    result = ai_services.run_generation(user, "resume_profile", {"resume_text": resume}, ai_source=payload.get("ai_source", ""))
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
            parent = _upsert(user, source_key=key, kind=Entry.Kind.PROJECT, question=f"介绍一下你的「{project['title']}」项目。",
                             source=Entry.Source.RESUME, ai_draft=project["draft"], title=project["title"], order=order,
                             metadata={"summary": project["summary"]})
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
                    source=Entry.Source.RESUME, ai_draft=award["draft"], title=award["title"], order=order)
            kept.append(key)
            modules.append({"key": award["key"], "kind": "award", "title": award["title"], "summary": ""})
        _mark_orphans(user, "resume:", kept)
        profile.resume_text, profile.resume_modules, profile.resume_updated_at = resume, modules, timezone.now()
        profile.save()
    return {"profile": profile_payload(profile), **corpus_listing(user)}


def import_jd(user, payload):
    jd = text(payload.get("job_description"), "job_description", 12000, required=True)
    result = ai_services.run_generation(user, "jd_profile", {"job_description": jd}, ai_source=payload.get("ai_source", ""))
    with transaction.atomic():
        profile = profile_for(user, lock=True)
        kept = []
        for index, item in enumerate(result["questions"]):
            key = f"jd:q:{digest(item['question'])}"
            _upsert(user, source_key=key, kind=Entry.Kind.JD_QUESTION, question=item["question"], source=Entry.Source.JD,
                    ai_draft=item["draft"], group=result["summary"]["role"], order=index)
            kept.append(key)
        for index, item in enumerate(result["reverse_questions"]):
            key = f"jd:reverse:{digest(item['question'])}"
            _upsert(user, source_key=key, kind=Entry.Kind.REVERSE_QUESTION, question=item["question"], source=Entry.Source.JD,
                    ai_draft=item["draft"], order=index)
            kept.append(key)
        _mark_orphans(user, "jd:", kept)
        profile.jd_text, profile.jd_summary, profile.jd_updated_at = jd, result["summary"], timezone.now()
        profile.save()
    return {"profile": profile_payload(profile), **corpus_listing(user)}


def corpus_listing(user, kind=""):
    if kind and kind not in KINDS:
        raise InterviewError("Unknown corpus kind", code="invalid_kind")
    entries = Entry.objects.filter(user=user).select_related("parent")
    if kind:
        entries = entries.filter(kind=kind)
    saved = [entry_payload(entry) for entry in entries]
    # Curated bank questions appear in the knowledge corpus even before the candidate writes an answer.
    curated = []
    if not kind or kind == Entry.Kind.KNOWLEDGE:
        taken = {item["source_key"] for item in saved}
        for question in QUESTIONS:
            key = f"curated:{question['id']}"
            if key not in taken:
                curated.append({"id": None, "kind": "knowledge", "group": CATEGORY_LABELS.get(question["category"], question["category"]),
                                "title": "", "question": question["prompt"], "corpus_text": "", "ai_draft": "",
                                "source": "curated", "source_key": key, "parent_id": None, "order": 0,
                                "orphaned": False, "summary": "", "updated_at": None})
    return {"entries": saved + curated}


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
        if parent.kind != Entry.Kind.PROJECT or kind != Entry.Kind.PROJECT_FOLLOWUP:
            raise InterviewError("追问只能挂在项目下面。", code="invalid_parent")
    with transaction.atomic():
        if curated:
            existing = Entry.objects.select_for_update().filter(user=user, source_key=source_key).first()
            if existing:
                return {"entry": entry_payload(existing)}
            entry = Entry.objects.create(user=user, kind=Entry.Kind.KNOWLEDGE, source=Entry.Source.CURATED, source_key=source_key,
                                         question=curated["prompt"], group=CATEGORY_LABELS.get(curated["category"], ""),
                                         corpus_text=text(payload.get("corpus_text"), "corpus_text", 12000))
        else:
            entry = Entry.objects.create(user=user, kind=kind, source=Entry.Source.CUSTOM,
                                         question=text(payload.get("question"), "question", 1500, required=True),
                                         title=text(payload.get("title"), "title", 200), group=text(payload.get("group"), "group", 80),
                                         corpus_text=text(payload.get("corpus_text"), "corpus_text", 12000), parent=parent)
    return {"entry": entry_payload(entry)}


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
