"""Regenerate web/static/assets/guest-samples.js from the demo account.

Emits default seed data in the SAME payload shapes the real render pipeline
consumes (applyLanguageTakeawaysPayload / applyP1CorpusPayload /
applyP2CorpusPayload + history list/detail), so guests and empty accounts get
fully-functional cards (TTS, click, review) — NOT hand-drawn HTML.

Run:  python scripts/_emit_guest_samples.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend_django"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

from apps.speaking import corpus_services, report_services  # noqa: E402
from apps.speaking.models import SpeakingAttempt  # noqa: E402

User = get_user_model()
user = User.objects.filter(pk=7).first() or User.objects.order_by("pk").first()
print(f"using user id={user.pk} username={user.username}", file=sys.stderr)


def trim_text(value, limit=900):
    text = str(value or "")
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


# ── Takeaways (library item shape: {items, count}) ────────────────────────────
def takeaway_items(library, want):
    items = library.get("items") or []
    picked = []
    for item in items:
        if item.get("source_text") and item.get("chinese_text"):
            picked.append(
                {
                    "entry_id": item.get("entry_id"),
                    "source_text": item.get("source_text"),
                    "chinese_text": item.get("chinese_text"),
                    "source_language": item.get("source_language") or "en",
                    "target_language": item.get("target_language") or "zh",
                    "context_url": item.get("context_url") or "",
                    "context_label": item.get("context_label") or "",
                    "updated_at": item.get("updated_at") or "",
                }
            )
        if len(picked) >= want:
            break
    return {"items": picked, "count": len(picked)}


def is_replacement(item):
    return any(sep in str(item.get("source_text") or "") for sep in ("→", "->", "=>", "—>"))


def split_takeaways(library, replacements_want, phrases_want):
    """Default takeaway seed: a few expression-replacement cards + a few plain
    phrase cards, so the book shows both card styles out of the box."""
    items = (library.get("items") or [])

    def shape(item):
        return {
            "entry_id": item.get("entry_id"),
            "source_text": item.get("source_text"),
            "chinese_text": item.get("chinese_text"),
            "source_language": item.get("source_language") or "en",
            "target_language": item.get("target_language") or "zh",
            "context_url": item.get("context_url") or "",
            "context_label": item.get("context_label") or "",
            "updated_at": item.get("updated_at") or "",
        }

    replacements, phrases = [], []
    for item in items:
        if not (item.get("source_text") and item.get("chinese_text")):
            continue
        if is_replacement(item) and len(replacements) < replacements_want:
            replacements.append(shape(item))
        elif not is_replacement(item) and len(phrases) < phrases_want:
            phrases.append(shape(item))
    return replacements + phrases


# Language Takeaway book: 3 expression-replacement cards + 3 plain phrases.
language_seed = split_takeaways(corpus_services.language_takeaway_library(user), 3, 3)
# Pull replacement defaults from the writing library too if the language book
# has none, so the 表达替换 card style always shows.
if sum(1 for it in language_seed if is_replacement(it)) < 3:
    extra = [it for it in split_takeaways(corpus_services.writing_takeaway_library(user), 3, 0)]
    seen = {it["source_text"] for it in language_seed}
    for it in extra:
        if it["source_text"] not in seen and sum(1 for x in language_seed if is_replacement(x)) < 3:
            language_seed.insert(0, it)
language_takeaways = {"items": language_seed, "count": len(language_seed)}
writing_takeaways = takeaway_items(corpus_services.writing_takeaway_library(user), 5)

# ── P1 corpus: FULL bank (all topics + questions) so every 题卡 shows, but only
#   "What is your full name?" carries default content. ─────────────────────────
p1_full = corpus_services.p1_corpus_library(user)
p1_topics = []
p1_saved = 0
for topic in p1_full.get("topics") or []:
    questions = []
    for q in topic.get("questions") or []:
        qtext = str(q.get("question") or "").strip().lower()
        keep = "full name" in qtext
        corpus_text = trim_text(q.get("corpus_text"), 1100) if (keep and q.get("corpus_text")) else ""
        if corpus_text:
            p1_saved += 1
        questions.append(
            {
                "question_id": q.get("question_id"),
                "topic": q.get("topic"),
                "question": q.get("question"),
                "corpus_text": corpus_text,
                "last_ai_answer": "",
                "updated_at": (q.get("updated_at") or "") if corpus_text else "",
            }
        )
    p1_topics.append({"topic": topic.get("topic"), "label": topic.get("label"), "questions": questions})

p1_question_count = sum(len(t["questions"]) for t in p1_topics)
p1_corpus = {
    "topics": p1_topics,
    "question_count": p1_question_count,
    "saved_count": p1_saved,
    "active_season": p1_full.get("active_season"),
    "active_region": p1_full.get("active_region"),
    "active_scope": p1_full.get("active_scope"),
    "active_scope_label": p1_full.get("active_scope_label") or "",
}

# ── P2 corpus: ALL category groups (种类给全); only 人物 keeps one material item.
#   ALL current_part2_cards (题卡给全); strip saved long-text from cards. ───────
p2_full = corpus_services.p2_corpus_library(user)
p2_categories = []
for cat in p2_full.get("categories") or []:
    label = str(cat.get("label") or "")
    items = cat.get("items") or []
    kept = []
    if "人物" in label and items:
        entry = dict(items[0])
        if entry.get("material_text"):
            entry["material_text"] = trim_text(entry["material_text"], 1200)
        if entry.get("p3_follow_up_text"):
            entry["p3_follow_up_text"] = trim_text(entry["p3_follow_up_text"], 900)
        kept = [entry]
    p2_categories.append(
        {
            "category": cat.get("category"),
            "label": cat.get("label"),
            "items": kept,
            "material_count": len(kept),
        }
    )

# All seasonal P2 题卡, with saved long-text cleared so the bank shows clean
# default cards (cue card + P3 structure). Counts kept so progress bars render.
p2_cards = []
for card in p2_full.get("current_part2_cards") or []:
    clone = dict(card)
    for key in ("material_text", "corpus_text", "p3_follow_up_text", "brainstorm_idea"):
        if key in clone:
            clone[key] = ""
    clone["has_material"] = False
    clone["has_brainstorm_idea"] = False
    p2_cards.append(clone)

p2_material_count = sum(c["material_count"] for c in p2_categories)
p2_corpus = {
    "categories": p2_categories,
    "category_count": len(p2_categories),
    "material_count": p2_material_count,
    "active_season": p2_full.get("active_season"),
    "active_region": p2_full.get("active_region"),
    "active_scope": p2_full.get("active_scope"),
    "active_scope_label": p2_full.get("active_scope_label") or "",
    "scope": p2_full.get("scope"),
    "current_part2_count": len(p2_cards),
    "current_part2_categories": p2_full.get("current_part2_categories") or [],
    "current_part2_cards": p2_cards,
}

# ── Speaking reports (real history item + real report_payload detail) ──────────
attempts = (
    SpeakingAttempt.objects.filter(user=user)
    .exclude(status=SpeakingAttempt.Status.ABORTED)
    .select_related("report")
    .prefetch_related("turns")
    .order_by("-created_at")
)
history = []
for attempt in attempts:
    if not report_services.report_is_valid(attempt):
        continue
    item = dict(report_services.history_item(attempt))
    item["is_sample"] = True
    detail = dict(report_services.report_payload(attempt))
    detail["is_sample"] = True
    history.append({**item, "detail": detail})
    if len(history) >= 3:
        break

# ── Writing reports (real compact item + real entry_payload detail) ───────────
from apps.writing import report_services as writing_report_services  # noqa: E402
from apps.writing.models import WritingEntry  # noqa: E402

writing_reports_seed = []
writing_entries = (
    WritingEntry.objects.filter(user=user)
    .select_related("prompt", "score")
    .order_by("-updated_at")
)
for entry in writing_entries:
    score = getattr(entry, "score", None)
    if not (score and score.overall_band is not None):
        continue
    item = dict(writing_report_services.compact_entry_payload(entry))
    item["is_sample"] = True
    detail = dict(writing_report_services.entry_payload(entry))
    detail["is_sample"] = True
    writing_reports_seed.append({**item, "detail": detail})
    if len(writing_reports_seed) >= 1:
        break

out = {
    "languageTakeaways": language_takeaways["items"],
    "writingTakeaways": writing_takeaways["items"],
    "p1Corpus": p1_corpus,
    "p2Corpus": p2_corpus,
    "history": history,
    "writingReports": writing_reports_seed,
}

body = json.dumps(out, ensure_ascii=False, indent=2)
js = (
    "/* guest-samples.js — default seed content for the studio.\n"
    " * Real data from the demo account, in the SAME payload shapes the live\n"
    " * render pipeline consumes, so signed-out visitors and brand-new accounts\n"
    " * see fully-functional default cards (TTS / click / review all work).\n"
    " * Only the speaking reports are flagged is_sample (shown with a 示例 badge).\n"
    " * Generated by scripts/_emit_guest_samples.py — do not edit by hand. */\n"
    "(function () {\n"
    "  window.IELTSGuestSamples = " + body + ";\n"
    "})();\n"
)

out_path = os.path.join(ROOT, "web", "static", "assets", "guest-samples.js")
with open(out_path, "w", encoding="utf-8") as handle:
    handle.write(js)

print(
    "wrote {path}\n  language={lt} writing={wt} p1_topics={p1} p1_saved={p1s} p2_cards={p2c} p2_cats={p2g} reports={h} writing_reports={wr}".format(
        path=out_path,
        lt=len(language_takeaways["items"]),
        wt=len(writing_takeaways["items"]),
        p1=len(p1_topics),
        p1s=p1_saved,
        p2c=len(p2_cards),
        p2g=len(p2_categories),
        h=len(history),
        wr=len(writing_reports_seed),
    ),
    file=sys.stderr,
)
