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


language_takeaways = takeaway_items(corpus_services.language_takeaway_library(user), 6)
writing_takeaways = takeaway_items(corpus_services.writing_takeaway_library(user), 5)

# ── P1 corpus (full library payload, trimmed to filled topics) ────────────────
p1_full = corpus_services.p1_corpus_library(user)
p1_topics = []
for topic in p1_full.get("topics") or []:
    filled = [q for q in (topic.get("questions") or []) if q.get("corpus_text")]
    if not filled:
        continue
    p1_topics.append(
        {
            "topic": topic.get("topic"),
            "label": topic.get("label"),
            "questions": [
                {
                    "question_id": q.get("question_id"),
                    "topic": q.get("topic"),
                    "question": q.get("question"),
                    "corpus_text": trim_text(q.get("corpus_text")),
                    "last_ai_answer": "",
                    "updated_at": q.get("updated_at") or "",
                }
                for q in filled[:3]
            ],
        }
    )
    if len(p1_topics) >= 4:
        break

p1_question_count = sum(len(t["questions"]) for t in p1_topics)
p1_corpus = {
    "topics": p1_topics,
    "question_count": p1_question_count,
    "saved_count": p1_question_count,
    "active_season": p1_full.get("active_season"),
    "active_region": p1_full.get("active_region"),
    "active_scope": p1_full.get("active_scope"),
    "active_scope_label": p1_full.get("active_scope_label") or "",
}

# ── P2 corpus (full library payload, trimmed) ─────────────────────────────────
p2_full = corpus_services.p2_corpus_library(user)
p2_categories = []
for cat in p2_full.get("categories") or []:
    items = cat.get("items") or []
    if not items:
        continue
    trimmed = []
    for entry in items[:2]:
        clone = dict(entry)
        if clone.get("material_text"):
            clone["material_text"] = trim_text(clone["material_text"], 1200)
        if clone.get("p3_follow_up_text"):
            clone["p3_follow_up_text"] = trim_text(clone["p3_follow_up_text"], 900)
        trimmed.append(clone)
    p2_categories.append(
        {
            "category": cat.get("category"),
            "label": cat.get("label"),
            "items": trimmed,
            "material_count": len(trimmed),
        }
    )
    if len(p2_categories) >= 3:
        break

# current_part2_cards: prefer cards that already carry material / P3 progress.
all_cards = p2_full.get("current_part2_cards") or []
ranked = sorted(
    all_cards,
    key=lambda c: (
        bool(c.get("material_text")),
        (c.get("p3_follow_up_saved_count") or 0),
        bool(c.get("corpus_text")),
    ),
    reverse=True,
)
p2_cards = []
for card in ranked[:6]:
    clone = dict(card)
    for key in ("material_text", "corpus_text", "p3_follow_up_text"):
        if clone.get(key):
            clone[key] = trim_text(clone[key], 1200)
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

out = {
    "languageTakeaways": language_takeaways["items"],
    "writingTakeaways": writing_takeaways["items"],
    "p1Corpus": p1_corpus,
    "p2Corpus": p2_corpus,
    "history": history,
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
    "wrote {path}\n  language={lt} writing={wt} p1_topics={p1} p2_cards={p2c} p2_cats={p2g} reports={h}".format(
        path=out_path,
        lt=len(language_takeaways["items"]),
        wt=len(writing_takeaways["items"]),
        p1=len(p1_topics),
        p2c=len(p2_cards),
        p2g=len(p2_categories),
        h=len(history),
    ),
    file=sys.stderr,
)
