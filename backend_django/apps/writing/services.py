import calendar
import hashlib
import json
import random
import re
import sqlite3
import threading
import uuid
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import DateTimeField, Exists, F, Max, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone

from apps.ai.models import AITask
from apps.ai.orchestration import AIOrchestrationError, cancel_billable_ai_task, create_billable_ai_task, fallback_billable_ai_task, succeed_billable_ai_task
from apps.ai.services import task_payload

from .models import WritingEntry, WritingLearnerProfile, WritingPrompt, WritingScore
from .search_utils import QUERY_EXPANSION_LIMIT, QUERY_EXPANSIONS, expanded_search_terms, query_concepts as expanded_query_concepts, search_base_tokens, search_normalize, unique_terms
from .validation import WRITING_TASK_TYPES, WritingEntryDeleted, WritingError, normalize_task_type, paragraph_guidance, validate_answer_paragraphs, word_count, writing_entry_is_scored, writing_paragraphs


DEFAULT_WRITING_SCORE_RESERVATION_U = 1_000_000
DEFAULT_WRITING_REPORT_LIMIT = 50
MAX_WRITING_REPORT_LIMIT = 100
WRITING_TASK_LABELS = {
    WritingPrompt.TaskType.TASK1_ACADEMIC: "Task 1 Academic",
    WritingPrompt.TaskType.TASK2: "Task 2",
}
WRITING_CATEGORY_LABELS = {
    "line_graph": "\u6298\u7ebf\u56fe",
    "bar_chart": "\u67f1\u72b6\u56fe",
    "pie_chart": "\u997c\u56fe",
    "table": "\u8868\u683c",
    "map": "\u5730\u56fe",
    "process": "\u6d41\u7a0b\u56fe",
    "mixed": "\u6df7\u5408\u56fe",
    "opinion": "\u89c2\u70b9\u7c7b",
    "discussion": "\u8ba8\u8bba\u7c7b",
    "problem_solution": "\u95ee\u9898\u89e3\u51b3\u7c7b",
    "causes_solutions": "\u539f\u56e0\u89e3\u51b3\u7c7b",
    "causes_effects": "\u539f\u56e0\u5f71\u54cd\u7c7b",
    "advantages_disadvantages": "\u5229\u5f0a\u7c7b",
    "two_part": "\u53cc\u95ee\u9898\u7c7b",
}
_agent_fts_available: bool | None = None

_seed_prompt_sync_lock = threading.Lock()
_seed_prompt_sync_done = False
_seed_prompt_min_loaded_count = 50
_agent_prompt_snapshot_lock = threading.Lock()
_agent_prompt_snapshot_cache: dict[str, tuple[str, str, list[WritingPrompt]]] = {}
_agent_fts_cache_lock = threading.Lock()
_agent_fts_cache_signature = ""
_agent_fts_cache_conn: sqlite3.Connection | None = None


def data_writing_dir() -> Path:
    return Path(settings.BASE_DIR).parent / "data" / "ielts" / "writing"


def cambridge_manifest_path() -> Path:
    return data_writing_dir() / "cambridge" / "cambridge_1_20_manifest.json"


def stable_prompt_id(task_type: str, prompt: str) -> str:
    digest = hashlib.sha1(f"{task_type}:{prompt}".encode("utf-8")).hexdigest()[:16]
    return f"{task_type}_{digest}"


def positive_int(value: Any) -> int | None:
    try:
        number = int(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def seed_prompt_files(task_type: str) -> list[Path]:
    base_dir = data_writing_dir()
    files: list[Path] = []
    main_file = base_dir / f"{task_type}.json"
    if main_file.exists():
        files.append(main_file)
    public_file = base_dir / "public_samples" / f"{task_type}.json"
    if public_file.exists():
        files.append(public_file)
    reported_file = base_dir / "reported_actual" / f"{task_type}.json"
    if reported_file.exists():
        files.append(reported_file)
    cambridge_dir = base_dir / "cambridge" / task_type
    if cambridge_dir.exists():
        files.extend(sorted(path for path in cambridge_dir.rglob("*.json") if path.is_file()))
    return files


def writing_prompt_sort_key(prompt: WritingPrompt) -> tuple:
    task_rank = 0 if prompt.task_type == WritingPrompt.TaskType.TASK1_ACADEMIC else 1
    has_no_book = prompt.source_book is None
    if prompt.source_book:
        source_rank = 0
        sort_order = prompt.sort_order or 999_999
    elif prompt.source.startswith("reported_actual_"):
        source_rank = 1
        sort_order = -(prompt.sort_order or 0)
    elif prompt.source == "public_official_sample":
        source_rank = 2
        sort_order = prompt.sort_order or 999_999
    else:
        source_rank = 3
        sort_order = prompt.sort_order or 999_999
    return (
        task_rank,
        source_rank,
        has_no_book,
        -(prompt.source_book or 0),
        prompt.source_test or 999,
        prompt.source_question or 999,
        sort_order,
        prompt.prompt_id,
    )


def normalize_category(value: str | None) -> str:
    category = str(value or "").strip().lower()
    if category in {"", "all", "*"}:
        return ""
    aliases = {
        "flowchart": "process",
        "flow_chart": "process",
        "maps": "map",
        "mixed_graph": "mixed",
        "mixed-graph": "mixed",
    }
    return aliases.get(category, category)


def cambridge_source_label(task_type: str, source_book: int | None, source_test: int | None, source_question: int | None) -> str:
    if not source_book or not source_test:
        return ""
    task_number = source_question or (1 if task_type == WritingPrompt.TaskType.TASK1_ACADEMIC else 2)
    return f"\u5251\u96c5{source_book}-{source_test} Task {task_number}"


def prompt_source_label(prompt: WritingPrompt) -> str:
    cambridge_label = cambridge_source_label(prompt.task_type, prompt.source_book, prompt.source_test, prompt.source_question)
    if cambridge_label:
        return cambridge_label
    if prompt.source == "public_official_sample":
        return f"\u5b98\u65b9\u516c\u5f00\u6837\u9898 {prompt.sort_order or ''}".strip()
    if prompt.source == "local_sample_bank":
        return f"\u672c\u5730\u6837\u9898 {prompt.sort_order or ''}".strip()
    if prompt.source.startswith("reported_actual_"):
        return prompt.title or "\u4e2d\u56fd\u8003\u533a\u771f\u9898"
    return prompt.title or ""


def cambridge_catalog(task_type: str | None = None) -> list[dict[str, Any]]:
    selected_task_type = normalize_task_type(task_type) if task_type else ""
    path = cambridge_manifest_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WritingError(f"Unable to load Cambridge writing catalog: {path}") from exc
    raw_slots = payload.get("slots") if isinstance(payload, dict) else []
    if not isinstance(raw_slots, list):
        raise WritingError(f"Cambridge writing catalog must contain a slots array: {path}")
    slots: list[dict[str, Any]] = []
    for raw_item in raw_slots:
        if not isinstance(raw_item, dict):
            continue
        slot_task_type = normalize_task_type(str(raw_item.get("task_type") or ""))
        if selected_task_type and slot_task_type != selected_task_type:
            continue
        source_book = positive_int(raw_item.get("source_book"))
        source_test = positive_int(raw_item.get("source_test"))
        source_question = positive_int(raw_item.get("source_question"))
        source_label = str(raw_item.get("source_label") or "").strip() or cambridge_source_label(slot_task_type, source_book, source_test, source_question)
        slots.append(
            {
                "id": str(raw_item.get("id") or "").strip(),
                "task_type": slot_task_type,
                "task_label": WRITING_TASK_LABELS.get(slot_task_type, "Writing"),
                "source_label": source_label,
                "source_book": source_book,
                "source_test": source_test,
                "source_question": source_question,
                "expected_image_url": str(raw_item.get("expected_image_url") or "").strip(),
                "material_status": str(raw_item.get("material_status") or "missing_authorized_material").strip(),
            }
        )
    return sorted(
        slots,
        key=lambda item: (
            0 if item["task_type"] == WritingPrompt.TaskType.TASK1_ACADEMIC else 1,
            -(item.get("source_book") or 0),
            item.get("source_test") or 999,
            item.get("source_question") or 999,
        ),
    )


WRITING_PROMPT_STATUS_LABELS = {
    "unpracticed": "\u672a\u7ec3\u4e60",
    "saved": "\u5df2\u4fdd\u5b58",
    "scored": "\u5df2\u8bc4\u5206",
}


def prompt_status_payload(status: str | None = None) -> dict[str, str]:
    normalized = status if status in WRITING_PROMPT_STATUS_LABELS else "unpracticed"
    return {
        "practice_status": normalized,
        "practice_status_label": WRITING_PROMPT_STATUS_LABELS[normalized],
    }


def prompt_practice_statuses(user, prompts: list[WritingPrompt]) -> dict[str, str]:
    if not prompts or not user or not getattr(user, "is_authenticated", False):
        return {}
    prompt_ids = [prompt.prompt_id for prompt in prompts]
    entries = (
        WritingEntry.objects.filter(user=user, prompt__prompt_id__in=prompt_ids)
        .annotate(has_score=Exists(WritingScore.objects.filter(entry=OuterRef("pk"))))
        .values("prompt__prompt_id", "status", "has_score")
    )
    statuses: dict[str, str] = {}
    for entry in entries:
        prompt_id = entry["prompt__prompt_id"]
        current = statuses.get(prompt_id, "unpracticed")
        if entry["status"] == WritingEntry.Status.SCORED or entry["has_score"]:
            statuses[prompt_id] = "scored"
        elif current != "scored" and entry["status"] == WritingEntry.Status.SAVED:
            statuses[prompt_id] = "saved"
    return statuses


def prompt_payload(prompt: WritingPrompt, practice_status: str | None = None) -> dict[str, Any]:
    source_label = prompt_source_label(prompt)
    return {
        "id": prompt.prompt_id,
        "task_type": prompt.task_type,
        "task_label": WRITING_TASK_LABELS.get(prompt.task_type, "Writing"),
        "title": prompt.title,
        "category": prompt.category,
        "prompt": prompt.prompt,
        "image_url": prompt.image_url,
        "source": prompt.source,
        "source_book": prompt.source_book,
        "source_test": prompt.source_test,
        "source_question": prompt.source_question,
        "source_label": source_label,
        "sort_order": prompt.sort_order,
    } | prompt_status_payload(practice_status)


def agent_search_text(prompt: WritingPrompt) -> str:
    cached = getattr(prompt, "_agent_search_text", None)
    if cached is not None:
        return cached
    return " ".join([
        prompt.title,
        prompt_source_label(prompt),
        prompt.category,
        prompt.prompt,
    ])


def search_normalized_text(prompt: WritingPrompt) -> str:
    cached = getattr(prompt, "_search_normalized_text", None)
    if cached is not None:
        return cached
    return search_normalize(agent_search_text(prompt))


def agent_keyword_search_score(query: str, candidate: str) -> float:
    query_tokens = set(search_base_tokens(query))
    if not query_tokens:
        return 0.0
    candidate_text = search_normalize(candidate)
    candidate_tokens = set(candidate_text.split())
    if not candidate_tokens:
        return 0.0
    overlap = len(query_tokens & candidate_tokens) / len(query_tokens)
    phrase_tokens = list(query_tokens)[:3]
    phrase_bonus = 0.08 if phrase_tokens and " ".join(phrase_tokens) in candidate_text else 0.0
    size_bonus = min(0.06, len(candidate_tokens) / 900)
    return min(1.0, overlap * 0.86 + phrase_bonus + size_bonus)


def agent_keyword_search_score_for_prompt(query: str, prompt: WritingPrompt) -> float:
    query_tokens = set(search_base_tokens(query))
    if not query_tokens:
        return 0.0
    candidate_text = search_normalized_text(prompt)
    candidate_tokens = set(candidate_text.split())
    if not candidate_tokens:
        return 0.0
    overlap = len(query_tokens & candidate_tokens) / len(query_tokens)
    phrase_tokens = list(query_tokens)[:3]
    phrase_bonus = 0.08 if phrase_tokens and " ".join(phrase_tokens) in candidate_text else 0.0
    size_bonus = min(0.06, len(candidate_tokens) / 900)
    return min(1.0, overlap * 0.86 + phrase_bonus + size_bonus)


def agent_query_coverage_score(query_terms: list[str], candidate: str) -> float:
    if not query_terms:
        return 0.0
    candidate_text = f" {search_normalize(candidate)} "
    candidate_tokens = set(candidate_text.split())
    if not candidate_tokens:
        return 0.0
    matched_terms: list[str] = []
    for term in query_terms:
        normalized_term = search_normalize(term)
        if not normalized_term:
            continue
        if " " in normalized_term:
            if f" {normalized_term} " in candidate_text:
                matched_terms.append(normalized_term)
        elif normalized_term in candidate_tokens:
            matched_terms.append(normalized_term)
    if not matched_terms:
        return 0.0
    direct_query_terms = set(search_base_tokens(" ".join(query_terms[:6]))) or set(query_terms)
    direct_matches = len(set(matched_terms) & direct_query_terms)
    expanded_coverage = len(set(matched_terms)) / max(len(set(query_terms)), 1)
    direct_coverage = direct_matches / max(len(direct_query_terms), 1)
    return min(1.0, direct_coverage * 0.62 + expanded_coverage * 0.38)


def agent_query_coverage_score_for_prompt(query_terms: list[str], prompt: WritingPrompt) -> float:
    if not query_terms:
        return 0.0
    candidate_text = f" {search_normalized_text(prompt)} "
    candidate_tokens = set(candidate_text.split())
    if not candidate_tokens:
        return 0.0
    matched_terms: list[str] = []
    for term in query_terms:
        normalized_term = search_normalize(term)
        if not normalized_term:
            continue
        if " " in normalized_term:
            if f" {normalized_term} " in candidate_text:
                matched_terms.append(normalized_term)
        elif normalized_term in candidate_tokens:
            matched_terms.append(normalized_term)
    if not matched_terms:
        return 0.0
    direct_query_terms = set(search_base_tokens(" ".join(query_terms[:6]))) or set(query_terms)
    direct_matches = len(set(matched_terms) & direct_query_terms)
    expanded_coverage = len(set(matched_terms)) / max(len(set(query_terms)), 1)
    direct_coverage = direct_matches / max(len(direct_query_terms), 1)
    return min(1.0, direct_coverage * 0.62 + expanded_coverage * 0.38)


def agent_fuzzy_search_score(query: str, candidate: str) -> float:
    query_text = search_normalize(query)
    candidate_text = search_normalize(candidate)
    if not query_text or not candidate_text:
        return 0.0
    window = candidate_text[: max(280, len(query_text) * 8)]
    return SequenceMatcher(None, query_text, window).ratio()


def agent_fuzzy_search_score_for_prompt(query: str, prompt: WritingPrompt) -> float:
    query_text = search_normalize(query)
    candidate_text = search_normalized_text(prompt)
    if not query_text or not candidate_text:
        return 0.0
    window = candidate_text[: max(280, len(query_text) * 8)]
    return SequenceMatcher(None, query_text, window).ratio()


def agent_match_evidence(query_terms: list[str], candidate: str, limit: int = 8) -> list[str]:
    candidate_text = f" {search_normalize(candidate)} "
    candidate_tokens = set(candidate_text.split())
    matches: list[str] = []
    for term in query_terms:
        normalized_term = search_normalize(term)
        if not normalized_term:
            continue
        if (" " in normalized_term and f" {normalized_term} " in candidate_text) or normalized_term in candidate_tokens:
            matches.append(normalized_term)
    return unique_terms(matches, limit)


def agent_prompt_match_evidence(query_terms: list[str], prompt: WritingPrompt, limit: int = 8) -> list[str]:
    candidate_text = f" {search_normalized_text(prompt)} "
    candidate_tokens = set(candidate_text.split())
    matches: list[str] = []
    for term in query_terms:
        normalized_term = search_normalize(term)
        if not normalized_term:
            continue
        if (" " in normalized_term and f" {normalized_term} " in candidate_text) or normalized_term in candidate_tokens:
            matches.append(normalized_term)
    return unique_terms(matches, limit)


def agent_candidate_concept_matches(concepts: list[str], candidate: str) -> list[str]:
    if not concepts:
        return []
    candidate_text = f" {search_normalize(candidate)} "
    candidate_tokens = set(candidate_text.split())
    matched_concepts: list[str] = []
    for concept in concepts:
        for term in QUERY_EXPANSIONS.get(concept, []):
            if re.search(r"[\u4e00-\u9fff]", term):
                continue
            normalized_term = search_normalize(term)
            if not normalized_term:
                continue
            if (" " in normalized_term and f" {normalized_term} " in candidate_text) or normalized_term in candidate_tokens:
                matched_concepts.append(concept)
                break
    return matched_concepts


def agent_prompt_concept_matches(concepts: list[str], prompt: WritingPrompt) -> list[str]:
    if not concepts:
        return []
    candidate_text = f" {search_normalized_text(prompt)} "
    candidate_tokens = set(candidate_text.split())
    matched_concepts: list[str] = []
    for concept in concepts:
        for term in QUERY_EXPANSIONS.get(concept, []):
            if re.search(r"[\u4e00-\u9fff]", term):
                continue
            normalized_term = search_normalize(term)
            if not normalized_term:
                continue
            if (" " in normalized_term and f" {normalized_term} " in candidate_text) or normalized_term in candidate_tokens:
                matched_concepts.append(concept)
                break
    return matched_concepts


def agent_source_match_score(query: str, prompt: WritingPrompt) -> float:
    query_text = str(query or "").lower()
    source_label = prompt_source_label(prompt).lower()
    prompt_id = prompt.prompt_id.lower()
    if source_label and source_label in query_text:
        return 1.0
    if prompt_id and prompt_id in query_text:
        return 1.0
    cambridge_match = re.search(r"(?:cambridge|剑雅)\s*(\d+)\D+(?:test\s*)?(\d+)", query_text)
    if cambridge_match and prompt.source_book and prompt.source_test:
        book, test = (int(cambridge_match.group(1)), int(cambridge_match.group(2)))
        if book == prompt.source_book and test == prompt.source_test:
            return 1.0
    cambridge_book_match = re.search(r"(?:cambridge|剑雅)\s*(\d+)", query_text)
    if cambridge_book_match and prompt.source_book:
        if int(cambridge_book_match.group(1)) == prompt.source_book:
            return 0.32
    return 0.0


def agent_fts_available() -> bool:
    global _agent_fts_available
    if _agent_fts_available is not None:
        return _agent_fts_available
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE prompt_fts USING fts5(prompt_id UNINDEXED, body, tokenize='unicode61')")
    except sqlite3.Error:
        _agent_fts_available = False
    else:
        _agent_fts_available = True
        conn.close()
    return _agent_fts_available


def agent_prompt_index_signature(prompts: list[WritingPrompt]) -> str:
    digest = hashlib.sha1()
    for prompt in sorted(prompts, key=lambda item: item.prompt_id):
        updated_at = prompt.updated_at.isoformat() if getattr(prompt, "updated_at", None) else ""
        digest.update(f"{prompt.prompt_id}:{updated_at}:{prompt.is_active}\n".encode("utf-8"))
    return digest.hexdigest()


def agent_fts_match_query(query_terms: list[str]) -> str:
    fts_terms: list[str] = []
    for term in query_terms:
        for token in search_base_tokens(term):
            if len(token) >= 2 and not token.isdigit():
                fts_terms.append(f'"{token}"')
    return " OR ".join(unique_terms(fts_terms, limit=32))


def agent_fts_connection(prompts: list[WritingPrompt], index_signature: str | None = None) -> sqlite3.Connection | None:
    global _agent_fts_cache_conn, _agent_fts_cache_signature
    if not prompts or not agent_fts_available():
        return None
    signature = index_signature or agent_prompt_index_signature(prompts)
    with _agent_fts_cache_lock:
        if _agent_fts_cache_conn is not None and _agent_fts_cache_signature == signature:
            return _agent_fts_cache_conn
        if _agent_fts_cache_conn is not None:
            _agent_fts_cache_conn.close()
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.execute("CREATE VIRTUAL TABLE prompt_fts USING fts5(prompt_id UNINDEXED, body, tokenize='unicode61')")
        conn.executemany(
            "INSERT INTO prompt_fts(prompt_id, body) VALUES (?, ?)",
            [(prompt.prompt_id, f"{agent_search_text(prompt)} {search_normalized_text(prompt)}") for prompt in prompts],
        )
        _agent_fts_cache_conn = conn
        _agent_fts_cache_signature = signature
        return conn


def agent_fts_candidate_ranks(prompts: list[WritingPrompt], query_terms: list[str], limit: int = 80, index_signature: str | None = None) -> dict[str, float]:
    if not prompts or not query_terms:
        return {}
    match_query = agent_fts_match_query(query_terms)
    if not match_query:
        return {}
    conn = agent_fts_connection(prompts, index_signature)
    if conn is None:
        return {}
    try:
        with _agent_fts_cache_lock:
            rows = conn.execute(
                "SELECT prompt_id, bm25(prompt_fts, 0.8, 1.0) AS rank FROM prompt_fts WHERE prompt_fts MATCH ? ORDER BY rank LIMIT ?",
                (match_query, limit),
            ).fetchall()
    except sqlite3.Error:
        return {}
    if not rows:
        return {}
    best = min(float(row[1]) for row in rows)
    worst = max(float(row[1]) for row in rows)
    span = max(worst - best, 0.000001)
    return {str(prompt_id): 1.0 - ((float(rank) - best) / span) for prompt_id, rank in rows}


def agent_source_candidate_ids(query: str, prompts: list[WritingPrompt]) -> set[str]:
    query_text = str(query or "").lower()
    if not query_text:
        return set()
    prompt_id_terms = set(re.findall(r"[a-z0-9][a-z0-9_-]{5,}", query_text))
    source_ids: set[str] = set()
    cambridge_match = re.search(r"(?:cambridge|剑雅)\s*(\d+)\D+(?:test\s*)?(\d+)", query_text)
    cambridge_book_match = re.search(r"(?:cambridge|剑雅)\s*(\d+)", query_text)
    for prompt in prompts:
        prompt_id = prompt.prompt_id.lower()
        source_label = prompt_source_label(prompt).lower()
        if prompt_id in query_text or prompt_id in prompt_id_terms or (source_label and source_label in query_text):
            source_ids.add(prompt.prompt_id)
            continue
        if cambridge_match and prompt.source_book and prompt.source_test:
            book, test = (int(cambridge_match.group(1)), int(cambridge_match.group(2)))
            if book == prompt.source_book and test == prompt.source_test:
                source_ids.add(prompt.prompt_id)
                continue
        if cambridge_book_match and prompt.source_book:
            if int(cambridge_book_match.group(1)) == prompt.source_book:
                source_ids.add(prompt.prompt_id)
    return source_ids


def agent_search_score_details(
    query: str,
    prompt: WritingPrompt,
    query_terms: list[str] | None = None,
    fts_score: float = 0.0,
    query_concepts: list[str] | None = None,
) -> dict[str, float | str | list[str]]:
    candidate = agent_search_text(prompt)
    keyword_score = agent_keyword_search_score_for_prompt(query, prompt)
    expanded_terms = query_terms or expanded_search_terms(query)
    concepts = query_concepts if query_concepts is not None else expanded_query_concepts(query)
    matched_concepts = agent_prompt_concept_matches(concepts, prompt)
    concept_score = len(set(matched_concepts)) / max(len(set(concepts)), 1) if concepts else 0.0
    if (
        any(term.isdigit() for term in expanded_terms)
        and any(not term.isdigit() for term in expanded_terms)
        and keyword_score > 0.18
        and agent_prompt_match_evidence([term for term in expanded_terms if not term.isdigit()], prompt, limit=1) == []
    ):
        keyword_score = min(keyword_score, 0.18)
    semantic_score = agent_query_coverage_score_for_prompt(expanded_terms, prompt)
    source_score = agent_source_match_score(query, prompt)
    if len(concepts) >= 2 and concept_score < 0.66 and source_score < 0.95:
        fts_score = min(fts_score, 0.22)
        semantic_score = min(semantic_score, 0.24)
        keyword_score = min(keyword_score, 0.24)
    fuzzy_score = 0.0
    if max(fts_score, semantic_score, keyword_score, source_score) > 0.05:
        fuzzy_score = agent_fuzzy_search_score_for_prompt(query, prompt)
    hybrid_score = min(1.0, fts_score * 0.3 + semantic_score * 0.26 + keyword_score * 0.18 + concept_score * 0.16 + fuzzy_score * 0.06 + source_score * 0.04)
    score = max(keyword_score, semantic_score * 0.92, hybrid_score, source_score)
    if source_score >= 0.95:
        match_type = "source"
    elif fts_score >= 0.5:
        match_type = "bm25"
    elif semantic_score > keyword_score + 0.08:
        match_type = "semantic"
    elif fuzzy_score > keyword_score + 0.15:
        match_type = "fuzzy"
    else:
        match_type = "keyword"
    return {
        "score": score,
        "keyword_score": keyword_score,
        "semantic_score": semantic_score,
        "bm25_score": fts_score,
        "fuzzy_score": fuzzy_score,
        "concept_score": concept_score,
        "source_score": source_score,
        "match_type": match_type,
        "matched_terms": agent_prompt_match_evidence(expanded_terms, prompt),
        "matched_concepts": matched_concepts,
    }


def agent_search_score(query: str, prompt: WritingPrompt) -> float:
    return float(agent_search_score_details(query, prompt)["score"])


def prompt_deep_link(request, prompt: WritingPrompt) -> str:
    path = f"/?view=writing&task={prompt.task_type}&prompt={prompt.prompt_id}"
    forwarded_host = str(request.META.get("HTTP_X_FORWARDED_HOST") or "").strip()
    if forwarded_host:
        forwarded_proto = str(request.META.get("HTTP_X_FORWARDED_PROTO") or "https").strip() or "https"
        return f"{forwarded_proto}://{forwarded_host}{path}"
    return request.build_absolute_uri(path)


def agent_prompt_snapshot(task_type: str = "") -> tuple[str, list[WritingPrompt]]:
    queryset = WritingPrompt.objects.filter(is_active=True)
    if task_type:
        queryset = queryset.filter(task_type=task_type)
    aggregate = queryset.aggregate(max_updated_at=Max("updated_at"))
    count = queryset.count()
    max_updated_at = aggregate["max_updated_at"]
    signature = f"{task_type}:{count}:{max_updated_at.isoformat() if max_updated_at else ''}"
    cache_key = task_type or "__all__"
    with _agent_prompt_snapshot_lock:
        cached = _agent_prompt_snapshot_cache.get(cache_key)
        if cached and cached[0] == signature:
            return cached[1], cached[2]
        prompts = list(queryset)
        for prompt in prompts:
            search_text = " ".join([
                prompt.title,
                prompt_source_label(prompt),
                prompt.category,
                prompt.prompt,
            ])
            setattr(prompt, "_agent_search_text", search_text)
            setattr(prompt, "_search_normalized_text", search_normalize(search_text))
        index_signature = agent_prompt_index_signature(prompts)
        _agent_prompt_snapshot_cache[cache_key] = (signature, index_signature, prompts)
        if len(_agent_prompt_snapshot_cache) > 3:
            for key in list(_agent_prompt_snapshot_cache):
                if key != cache_key:
                    _agent_prompt_snapshot_cache.pop(key, None)
        return index_signature, prompts


def agent_find_writing_prompts(query: str, request, task_type: str | None = None, limit: int = 8) -> dict[str, Any]:
    sync_seed_prompts()
    normalized_task_type = normalize_task_type(task_type) if task_type else ""
    limit = max(1, min(int(limit or 8), 20))
    index_signature, prompts = agent_prompt_snapshot(normalized_task_type)
    query_terms = expanded_search_terms(query)
    query_concept_names = expanded_query_concepts(query)
    fts_scores = agent_fts_candidate_ranks(prompts, query_terms, index_signature=index_signature)
    source_candidate_ids = agent_source_candidate_ids(query, prompts)
    candidate_ids = set(fts_scores) | source_candidate_ids
    candidate_prompts = [prompt for prompt in prompts if prompt.prompt_id in candidate_ids] if candidate_ids else prompts
    scored: list[tuple[float, dict[str, Any], WritingPrompt]] = []
    for prompt in candidate_prompts:
        scores = agent_search_score_details(query, prompt, query_terms, fts_scores.get(prompt.prompt_id, 0.0), query_concept_names)
        score = float(scores["score"])
        if score > 0.1:
            scored.append((score, scores, prompt))
    scored.sort(key=lambda item: (-item[0], writing_prompt_sort_key(item[2])))
    items = []
    for score, scores, prompt in scored[:limit]:
        payload = prompt_payload(prompt)
        payload.update({
            "match_score": round(score, 4),
            "keyword_score": round(float(scores["keyword_score"]), 4),
            "semantic_score": round(float(scores["semantic_score"]), 4),
            "bm25_score": round(float(scores["bm25_score"]), 4),
            "fuzzy_score": round(float(scores["fuzzy_score"]), 4),
            "concept_score": round(float(scores["concept_score"]), 4),
            "source_score": round(float(scores["source_score"]), 4),
            "match_type": scores["match_type"],
            "matched_terms": scores["matched_terms"],
            "matched_concepts": scores["matched_concepts"],
            "url": prompt_deep_link(request, prompt),
        })
        items.append(payload)
    return {
        "query": query,
        "task_type": normalized_task_type,
        "count": len(items),
        "expanded_terms": query_terms[:QUERY_EXPANSION_LIMIT],
        "query_concepts": query_concept_names,
        "items": items,
    }


def sync_seed_prompts() -> None:
    global _seed_prompt_sync_done
    active_prompt_count = WritingPrompt.objects.filter(is_active=True).count()
    if active_prompt_count >= _seed_prompt_min_loaded_count:
        _seed_prompt_sync_done = True
        return
    if _seed_prompt_sync_done and active_prompt_count >= _seed_prompt_min_loaded_count:
        return
    with _seed_prompt_sync_lock:
        active_prompt_count = WritingPrompt.objects.filter(is_active=True).count()
        if active_prompt_count >= _seed_prompt_min_loaded_count:
            _seed_prompt_sync_done = True
            return
        if _seed_prompt_sync_done and active_prompt_count >= _seed_prompt_min_loaded_count:
            return
        _sync_seed_prompts_locked()
        _seed_prompt_sync_done = True


def _sync_seed_prompts_locked() -> None:
    active_reported_prompt_ids: set[str] = set()
    with transaction.atomic():
        for task_type in sorted(WRITING_TASK_TYPES):
            for path in seed_prompt_files(task_type):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise WritingError(f"Unable to load writing prompts: {path}") from exc
                raw_items = payload.get("prompts") if isinstance(payload, dict) else payload
                if not isinstance(raw_items, list):
                    raise WritingError(f"Writing prompt file must contain a prompts array: {path}")
                file_book = positive_int(payload.get("book") if isinstance(payload, dict) else None)
                file_test = positive_int(payload.get("test") if isinstance(payload, dict) else None)
                file_source = str(payload.get("source") or "").strip() if isinstance(payload, dict) else ""
                for index, raw_item in enumerate(raw_items):
                    if not isinstance(raw_item, dict):
                        raise WritingError(f"Writing prompt must be an object in {path}")
                    prompt_text = str(raw_item.get("prompt") or raw_item.get("question") or "").strip()
                    if not prompt_text:
                        continue
                    prompt_task_type = normalize_task_type(str(raw_item.get("task_type") or task_type))
                    prompt_id = str(raw_item.get("id") or "").strip() or stable_prompt_id(prompt_task_type, prompt_text)
                    source_book = positive_int(raw_item.get("source_book") or raw_item.get("book")) or file_book
                    source_test = positive_int(raw_item.get("source_test") or raw_item.get("test")) or file_test
                    source_question = positive_int(raw_item.get("source_question") or raw_item.get("question_number"))
                    source = str(raw_item.get("source") or file_source or "local_seed")[:120]
                    if source.startswith("reported_actual_"):
                        active_reported_prompt_ids.add(prompt_id[:120])
                    WritingPrompt.objects.update_or_create(
                        prompt_id=prompt_id[:120],
                        defaults={
                            "task_type": prompt_task_type,
                            "title": str(raw_item.get("title") or f"{WRITING_TASK_LABELS[prompt_task_type]} {index + 1}")[:200],
                            "category": normalize_category(str(raw_item.get("category") or ""))[:120],
                            "prompt": prompt_text,
                            "image_url": str(raw_item.get("image_url") or raw_item.get("image") or "")[:500],
                            "source": source,
                            "source_book": source_book,
                            "source_test": source_test,
                            "source_question": source_question,
                            "sort_order": positive_int(raw_item.get("sort_order")) or index + 1,
                            "is_active": True,
                        },
                    )
        if active_reported_prompt_ids:
            WritingPrompt.objects.filter(source__startswith="reported_actual_").exclude(prompt_id__in=active_reported_prompt_ids).update(is_active=False)


def prompt_categories(task_type: str | None = None) -> list[dict[str, Any]]:
    sync_seed_prompts()
    queryset = WritingPrompt.objects.filter(is_active=True)
    if task_type:
        queryset = queryset.filter(task_type=normalize_task_type(task_type))
    counts: dict[str, int] = {}
    for category in queryset.exclude(category="").values_list("category", flat=True):
        counts[category] = counts.get(category, 0) + 1
    return [{"category": key, "label": WRITING_CATEGORY_LABELS.get(key, key.replace("_", " ").title()), "count": counts[key]} for key in sorted(counts)]


def list_prompts(task_type: str | None = None, category: str | None = None, user=None) -> list[dict[str, Any]]:
    sync_seed_prompts()
    queryset = WritingPrompt.objects.filter(is_active=True)
    if task_type:
        queryset = queryset.filter(task_type=normalize_task_type(task_type))
    normalized_category = normalize_category(category)
    if normalized_category:
        queryset = queryset.filter(category=normalized_category)
    prompts = sorted(queryset, key=writing_prompt_sort_key)
    statuses = prompt_practice_statuses(user, prompts)
    return [prompt_payload(prompt, statuses.get(prompt.prompt_id)) for prompt in prompts]


def next_default_task_type(date_value=None) -> str:
    today = date_value or timezone.localdate()
    return WritingPrompt.TaskType.TASK1_ACADEMIC if today.toordinal() % 2 == 0 else WritingPrompt.TaskType.TASK2


def random_prompt(user, task_type: str | None = None, category: str | None = None) -> dict[str, Any]:
    selected_type = normalize_task_type(task_type) if task_type else next_default_task_type()
    sync_seed_prompts()
    queryset = WritingPrompt.objects.filter(task_type=selected_type, is_active=True)
    normalized_category = normalize_category(category)
    if normalized_category:
        queryset = queryset.filter(category=normalized_category)
    prompts = sorted(queryset, key=writing_prompt_sort_key)
    if not prompts:
        raise WritingError(f"No writing prompts available for {selected_type}")
    cambridge_prompts = [prompt for prompt in prompts if prompt.source_book and prompt.source_test]
    if cambridge_prompts:
        prompts = cambridge_prompts
    catalog_slots = cambridge_catalog(selected_type)
    scored_ids = set(
        WritingEntry.objects.filter(user=user)
        .filter(Q(status=WritingEntry.Status.SCORED) | Q(score__isnull=False))
        .exclude(prompt__isnull=True)
        .values_list("prompt__prompt_id", flat=True)
    )
    unused = [prompt for prompt in prompts if prompt.prompt_id not in scored_ids]
    pool = unused or prompts
    selected = random.choice(pool)
    statuses = prompt_practice_statuses(user, prompts)
    payload = prompt_payload(selected, statuses.get(selected.prompt_id))
    if not payload.get("source_label") and catalog_slots:
        try:
            selected_index = prompts.index(selected)
        except ValueError:
            selected_index = 0
        slot = catalog_slots[selected_index % len(catalog_slots)]
        payload["display_catalog_id"] = slot.get("id") or ""
        payload["display_source_label"] = slot.get("source_label") or ""
        payload["source_label"] = slot.get("source_label") or ""
        payload["source_book"] = slot.get("source_book")
        payload["source_test"] = slot.get("source_test")
        payload["source_question"] = slot.get("source_question")
        if not payload.get("image_url") and slot.get("expected_image_url"):
            payload["image_url"] = slot.get("expected_image_url") or ""
    return {**payload, "selection": "random", "unwritten": bool(unused)}


def month_bounds(month_value: str | None):
    value = str(month_value or timezone.localdate().strftime("%Y-%m")).strip()
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        value = timezone.localdate().strftime("%Y-%m")
    year, month = [int(part) for part in value.split("-")]
    _, day_count = calendar.monthrange(year, month)
    return timezone.datetime(year, month, 1).date(), timezone.datetime(year, month, day_count).date()


def report_limit(value: Any) -> int:
    try:
        limit = int(str(value or "").strip() or DEFAULT_WRITING_REPORT_LIMIT)
    except (TypeError, ValueError):
        return DEFAULT_WRITING_REPORT_LIMIT
    if limit <= 0:
        return DEFAULT_WRITING_REPORT_LIMIT
    return min(limit, MAX_WRITING_REPORT_LIMIT)


def report_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if not status:
        return ""
    if status not in {WritingEntry.Status.SAVED, WritingEntry.Status.SCORED}:
        raise WritingError("Unknown writing status")
    return status


def spelling_terms_from_summary(value: Any) -> set[str]:
    text = str(value or "")
    return {match.group(1).lower() for match in re.finditer(r"`?([A-Za-z]{2,})`?\s*(?:->|\u2192)", text)}


def looks_like_single_word_spelling_fix(value: str) -> bool:
    compact = value.replace("`", "").strip().strip("。. ")
    arrow = "->" if "->" in compact else ("\u2192" if "\u2192" in compact else "")
    if not arrow:
        return False
    left, right = compact.split(arrow, 1)
    right = right.strip()
    for prefix in ("正确：", "正确:", "correct:", "Correct:"):
        if right.startswith(prefix):
            right = right[len(prefix):].strip()
    right = right.split("（", 1)[0].split("(", 1)[0].strip()
    return bool(re.fullmatch(r"[A-Za-z]{2,}", left.strip()) and re.fullmatch(r"[A-Za-z]{2,}", right))


def strip_spelling_from_language_upgrade(value: Any, *, spelling_summary: Any = "") -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    spelling_keywords = ("拼写", "错拼", "错别字", "spelling", "misspell", "typo")
    spelling_terms = spelling_terms_from_summary(spelling_summary)
    cleaned: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if any(keyword in lowered for keyword in spelling_keywords):
            continue
        if spelling_terms and any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in spelling_terms):
            continue
        compact = line.lstrip("-*• \t")
        if looks_like_single_word_spelling_fix(compact):
            continue
        cleaned.append(raw_line)
    return "\n".join(cleaned).strip()


def strip_spelling_from_paragraph_coaching(value: Any, *, spelling_summary: Any = "") -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    spelling_terms = spelling_terms_from_summary(spelling_summary)
    text = re.sub(r"[，,；;]?\s*但?有(?:明显)?拼写错误[，,]?\s*而且?", "，", text)
    text = re.sub(r"[，,；;]?\s*存在(?:明显)?拼写错误[，,。；;]?", "。", text)
    text = re.sub(r"[，,；;]?\s*拼写(?:方面)?(?:也)?(?:需要|可以|应当)?(?:再)?(?:检查|注意|修改|纠正)[，,。；;]?", "。", text)
    cleaned: list[str] = []
    for raw_line in text.splitlines():
        lowered = raw_line.lower()
        if spelling_terms and any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in spelling_terms):
            continue
        cleaned.append(raw_line)
    return "\n".join(cleaned).replace("，。", "。").strip(" ，,")


def paragraph_reviews_payload(value: Any, *, spelling_summary: Any = "") -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    reviews: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        review = dict(item)
        review["coaching"] = strip_spelling_from_paragraph_coaching(
            item.get("coaching") or "",
            spelling_summary=spelling_summary,
        )
        review["language_correction_upgrade"] = strip_spelling_from_language_upgrade(
            item.get("language_correction_upgrade") or item.get("expression_upgrade") or "",
            spelling_summary=spelling_summary,
        )
        reviews.append(review)
    return reviews


def score_payload(score: WritingScore | None) -> dict[str, Any] | None:
    if not score:
        return None
    analysis = score.analysis_payload or {}
    return {
        "overall_band": float(score.overall_band) if score.overall_band is not None else None,
        "task_response": float(score.task_response) if score.task_response is not None else None,
        "task_achievement": float(score.task_response) if score.task_response is not None else None,
        "coherence_cohesion": float(score.coherence_cohesion) if score.coherence_cohesion is not None else None,
        "lexical_resource": float(score.lexical_resource) if score.lexical_resource is not None else None,
        "grammatical_range_accuracy": float(score.grammar_range_accuracy) if score.grammar_range_accuracy is not None else None,
        "feedback_markdown": score.feedback_markdown,
        "grammar_corrections": score.grammar_corrections,
        "inline_annotations": analysis.get("inline_annotations", []),
        "spelling_correction_summary": analysis.get("spelling_correction_summary", ""),
        "expression_upgrade_summary": analysis.get("expression_upgrade_summary", ""),
        "overall_review": analysis.get("overall_review", ""),
        "practice_focus": analysis.get("practice_focus", ""),
        "model_answer": analysis.get("model_answer", ""),
        "paragraph_reviews": paragraph_reviews_payload(
            analysis.get("paragraph_reviews"),
            spelling_summary=analysis.get("spelling_correction_summary", ""),
        ),
        "structure_advice_only": bool(analysis.get("structure_advice_only")),
        "structure_advice": analysis.get("structure_advice", ""),
        "analysis_backend": analysis.get("analysis_backend", score.source),
        "fallback_reason": analysis.get("fallback_reason", ""),
        "backend": score.source,
        "billing_usage": score.billing_metadata,
        "scored_at": score.scored_at.isoformat() if score.scored_at else None,
    }


def task_summary_payload(task: AITask | None) -> dict[str, Any] | None:
    if not task:
        return None
    return {
        "id": task.task_id,
        "task_type": task.task_type,
        "provider": task.provider,
        "model": task.model,
        "status": task.status,
        "progress_percent": task.progress_percent,
        "attempt_count": task.attempt_count,
        "max_attempts": task.max_attempts,
        "related_type": task.related_type,
        "related_id": task.related_id,
        "error_code": task.error_code,
        "error_message": task.error_message,
        "fallback_reason": task.fallback_reason,
        "available_at": task.available_at.isoformat() if task.available_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def profile_snapshot(profile: WritingLearnerProfile | None) -> dict[str, Any] | None:
    if not profile:
        return None
    tag_counts = profile.tag_counts if isinstance(profile.tag_counts, dict) else {}
    top_tags = sorted(tag_counts.items(), key=lambda item: (-int(item[1] or 0), str(item[0])))[:5]
    return {
        "total_scored": profile.total_scored,
        "average_overall_band": float(profile.average_overall_band) if profile.average_overall_band is not None else None,
        "primary_focus": profile.primary_focus,
        "primary_focus_text": profile.primary_focus_text,
        "top_issues": [{"tag": tag, "label": writing_tag_text(tag), "count": count} for tag, count in top_tags],
        "recent_evidence": list(profile.recent_evidence or [])[:4],
        "updated_at": profile.updated_at.isoformat() if profile.pk else None,
    }


def writing_score_task_payload(entry: WritingEntry) -> dict[str, Any] | None:
    task = (
        AITask.objects.filter(
            user=entry.user,
            task_type="writing_score",
            related_type="writing_entry",
            related_id=entry.entry_id,
        )
        .order_by("-created_at")
        .first()
    )
    return task_payload(task) if task else None


def entry_payload(entry: WritingEntry, include_answer: bool = True) -> dict[str, Any]:
    score = getattr(entry, "score", None)
    source_label = prompt_source_label(entry.prompt) if entry.prompt_id else str(entry.metadata.get("source_label") or "")
    prompt_highlights = normalize_prompt_highlights(entry.metadata.get("prompt_highlights"), entry.prompt_text)
    payload = {
        "id": entry.entry_id,
        "user_id": str(entry.user_id),
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
        "saved_at": entry.saved_at.isoformat() if entry.saved_at else None,
        "practice_date": entry.practice_date.isoformat(),
        "status": entry.status,
        "task_type": entry.task_type,
        "task_label": WRITING_TASK_LABELS.get(entry.task_type, "Writing"),
        "prompt_id": entry.prompt.prompt_id if entry.prompt_id else "",
        "title": entry.title,
        "category": entry.prompt.category if entry.prompt_id else entry.metadata.get("category", ""),
        "prompt": entry.prompt_text,
        "image_url": entry.prompt.image_url if entry.prompt_id else entry.metadata.get("image_url", ""),
        "source": entry.prompt.source if entry.prompt_id else entry.metadata.get("source", ""),
        "source_book": entry.prompt.source_book if entry.prompt_id else entry.metadata.get("source_book"),
        "source_test": entry.prompt.source_test if entry.prompt_id else entry.metadata.get("source_test"),
        "source_question": entry.prompt.source_question if entry.prompt_id else entry.metadata.get("source_question"),
        "source_label": source_label,
        "prompt_highlights": prompt_highlights,
        "word_count": entry.word_count,
        "score": score_payload(score),
        "ai_task": writing_score_task_payload(entry),
        "writing_profile": profile_snapshot(getattr(entry.user, "writing_learner_profile", None)),
    }
    if include_answer:
        payload["answer"] = entry.answer
    return payload


def compact_entry_payload(entry: WritingEntry) -> dict[str, Any]:
    score = getattr(entry, "score", None)
    display_at = getattr(entry, "latest_activity_at", None) or entry.updated_at
    source_label = prompt_source_label(entry.prompt) if entry.prompt_id else str(entry.metadata.get("source_label") or "")
    return {
        "id": entry.entry_id,
        "practice_date": entry.practice_date.isoformat(),
        "display_time": display_at.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%d %H:%M"),
        "task_type": entry.task_type,
        "task_label": WRITING_TASK_LABELS.get(entry.task_type, "Writing"),
        "prompt_id": entry.prompt.prompt_id if entry.prompt_id else "",
        "title": entry.title or (entry.prompt.title if entry.prompt_id else "Writing"),
        "category": entry.prompt.category if entry.prompt_id else entry.metadata.get("category", ""),
        "prompt": entry.prompt_text,
        "source": entry.prompt.source if entry.prompt_id else entry.metadata.get("source", ""),
        "source_book": entry.prompt.source_book if entry.prompt_id else entry.metadata.get("source_book"),
        "source_test": entry.prompt.source_test if entry.prompt_id else entry.metadata.get("source_test"),
        "source_question": entry.prompt.source_question if entry.prompt_id else entry.metadata.get("source_question"),
        "source_label": source_label,
        "prompt_highlights": normalize_prompt_highlights(entry.metadata.get("prompt_highlights"), entry.prompt_text),
        "word_count": entry.word_count,
        "status": entry.status,
        "overall_band": float(score.overall_band) if score and score.overall_band is not None else None,
    }


def report_entry_payload(entry: WritingEntry, ai_task: AITask | None = None) -> dict[str, Any]:
    return {
        **compact_entry_payload(entry),
        "ai_task": task_summary_payload(ai_task),
    }


def latest_writing_tasks_for_entries(user, entry_ids: list[str]) -> dict[str, AITask]:
    if not entry_ids:
        return {}
    tasks = (
        AITask.objects.select_related("billing_reservation", "usage")
        .filter(
            user=user,
            task_type="writing_score",
            related_type="writing_entry",
            related_id__in=entry_ids,
        )
        .order_by("related_id", "-created_at", "-updated_at")
    )
    latest: dict[str, AITask] = {}
    for task in tasks:
        latest.setdefault(task.related_id, task)
    return latest


def writing_summary(user, month_value: str | None = None) -> dict[str, Any]:
    start, end = month_bounds(month_value)
    today = timezone.localdate()
    entries = list(
        WritingEntry.objects.filter(user=user)
        .select_related("prompt", "score")
        .order_by("-updated_at")
    )
    day_map: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if start <= entry.practice_date <= end:
            key = entry.practice_date.isoformat()
            status = "scored" if entry.status == WritingEntry.Status.SCORED else "saved"
            current = day_map.get(key)
            if not current or (status == "scored" and current.get("status") != "scored"):
                day_map[key] = {**compact_entry_payload(entry), "date": key, "status": status, "entry_id": entry.entry_id}
    days = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        days.append(day_map.get(key) or {"date": key, "status": "empty"})
        cursor += timezone.timedelta(days=1)
    practiced_dates = {item["date"] for item in day_map.values() if item.get("status") in {"saved", "scored"}}
    all_practiced_dates = {
        entry.practice_date.isoformat()
        for entry in entries
        if entry.status in {WritingEntry.Status.SAVED, WritingEntry.Status.SCORED}
    }
    streak = 0
    cursor = today
    while cursor.isoformat() in all_practiced_dates:
        streak += 1
        cursor -= timezone.timedelta(days=1)
    today_entry = next((entry_payload(entry) for entry in entries if entry.practice_date == today), None)
    return {
        "month": start.strftime("%Y-%m"),
        "today": today.isoformat(),
        "days": days,
        "stats": {
            "practiced_days": len(practiced_dates),
            "scored_entries": sum(1 for item in day_map.values() if item.get("status") == "scored"),
            "streak_days": streak,
            "total_entries": len(entries),
        },
        "recent_entries": [compact_entry_payload(entry) for entry in entries[:20]],
        "today_entry": today_entry,
    }


def writing_reports(user, query: dict[str, Any] | None = None) -> dict[str, Any]:
    query = query or {}
    limit = report_limit(query.get("limit"))
    status = report_status(query.get("status"))
    task_type_value = str(query.get("task_type") or "").strip()
    task_type = normalize_task_type(task_type_value) if task_type_value else ""

    latest_task_updated_at = Subquery(
        AITask.objects.filter(
            user=user,
            task_type="writing_score",
            related_type="writing_entry",
            related_id=OuterRef("entry_id"),
        )
        .order_by("-created_at", "-updated_at")
        .values("updated_at")[:1],
        output_field=DateTimeField(),
    )
    queryset = (
        WritingEntry.objects.filter(user=user)
        .select_related("prompt", "score")
        .annotate(latest_task_updated_at=latest_task_updated_at)
        .annotate(
            latest_activity_at=Greatest(
                F("updated_at"),
                Coalesce("latest_task_updated_at", F("updated_at")),
            )
        )
    )
    if status:
        queryset = queryset.filter(status=status)
    if task_type:
        queryset = queryset.filter(task_type=task_type)
    queryset = queryset.order_by("-latest_activity_at", "-updated_at", "-created_at")

    count = queryset.count()
    entries = list(queryset[:limit])
    task_map = latest_writing_tasks_for_entries(user, [entry.entry_id for entry in entries])
    return {
        "items": [report_entry_payload(entry, task_map.get(entry.entry_id)) for entry in entries],
        "count": count,
    }


def parse_practice_date(value: str | None):
    if not value:
        return timezone.localdate()
    try:
        return timezone.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise WritingError("Invalid practice_date") from exc


def normalize_prompt_highlights(value: Any, source_text: str = "") -> list[dict[str, int]]:
    text_len = len(str(source_text or ""))
    if not isinstance(value, list):
        return []
    ranges: list[dict[str, int]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            start = int(item.get("start", 0))
            end = int(item.get("end", 0))
        except (TypeError, ValueError):
            continue
        start = max(0, min(text_len, start))
        end = max(0, min(text_len, end))
        if end > start:
            ranges.append({"start": start, "end": end})
    ranges.sort(key=lambda item: (item["start"], item["end"]))
    return ranges


@transaction.atomic
def save_entry(user, payload: dict[str, Any]) -> dict[str, Any]:
    answer = str(payload.get("answer") or "")
    task_type = normalize_task_type(str(payload.get("task_type") or ""))
    prompt_id = str(payload.get("prompt_id") or "").strip()
    prompt = WritingPrompt.objects.filter(prompt_id=prompt_id, task_type=task_type, is_active=True).first() if prompt_id else None
    prompt_text = str(payload.get("prompt") or (prompt.prompt if prompt else "")).strip()
    if not prompt_text:
        raise WritingError("Missing writing prompt")
    entry_id = str(payload.get("id") or "").strip()
    existing = WritingEntry.objects.select_related("prompt", "score").filter(user=user, entry_id=entry_id).first() if entry_id else None
    if not entry_id:
        entry_id = uuid.uuid4().hex
    title = str(payload.get("title") or (prompt.title if prompt else "") or WRITING_TASK_LABELS[task_type])[:200]
    now = timezone.now()
    answer_changed = bool(existing and existing.answer != answer)
    create_revision = bool(answer_changed and existing and writing_entry_is_scored(existing))
    entry = WritingEntry(
        user=user,
        entry_id=uuid.uuid4().hex,
        task_type=task_type,
    ) if create_revision else (existing or WritingEntry(user=user, entry_id=entry_id, task_type=task_type))
    entry.prompt = prompt
    entry.task_type = task_type
    entry.practice_date = parse_practice_date(str(payload.get("practice_date") or "") or None)
    entry.title = title
    entry.prompt_text = prompt_text
    entry.answer = answer
    entry.word_count = word_count(answer)
    entry.status = WritingEntry.Status.SAVED if create_revision or answer_changed or not existing else entry.status
    entry.saved_at = now
    base_metadata = entry.metadata if not create_revision else (existing.metadata if existing else {})
    entry.metadata = {
        **(base_metadata or {}),
        "category": str(payload.get("category") or (prompt.category if prompt else "")),
        "image_url": str(payload.get("image_url") or (prompt.image_url if prompt else "")),
        "prompt_highlights": normalize_prompt_highlights(
            payload.get("prompt_highlights") if "prompt_highlights" in payload else (base_metadata or {}).get("prompt_highlights"),
            prompt_text,
        ),
    }
    if create_revision and existing:
        entry.metadata.update({
            "revision_parent_entry_id": existing.entry_id,
            "revision_source": "scored_entry_edit",
        })
    entry.save()
    if answer_changed and not create_revision:
        WritingScore.objects.filter(entry=entry).delete()
    return entry_payload(entry)


def get_entry(user, entry_id: str) -> dict[str, Any]:
    entry = (
        WritingEntry.objects.select_related("user", "prompt", "score")
        .filter(user=user, entry_id=str(entry_id or "").strip())
        .first()
    )
    if not entry:
        raise WritingError("Writing entry not found")
    return entry_payload(entry)


@transaction.atomic
def clone_entry_for_revision(user, entry_id: str) -> dict[str, Any]:
    source = (
        WritingEntry.objects.select_related("prompt", "score")
        .filter(user=user, entry_id=str(entry_id or "").strip())
        .first()
    )
    if not source:
        raise WritingError("Writing entry not found")
    if not writing_entry_is_scored(source):
        raise WritingError("Only scored writing entries can be cloned for revision")
    now = timezone.now()
    clone = WritingEntry.objects.create(
        user=user,
        entry_id=uuid.uuid4().hex,
        prompt=source.prompt,
        task_type=source.task_type,
        practice_date=timezone.localdate(),
        title=source.title,
        prompt_text=source.prompt_text,
        answer=source.answer,
        word_count=word_count(source.answer),
        status=WritingEntry.Status.SAVED,
        saved_at=now,
        metadata={
            **(source.metadata or {}),
            "revision_parent_entry_id": source.entry_id,
            "revision_source": "writing_report_edit",
        },
    )
    return entry_payload(clone)


@transaction.atomic
def delete_entry(user, entry_id: str) -> dict[str, Any]:
    entry = WritingEntry.objects.filter(user=user, entry_id=str(entry_id or "").strip()).first()
    if not entry:
        raise WritingError("Writing entry not found")
    pending_tasks = AITask.objects.filter(
        user=user,
        task_type="writing_score",
        related_type="writing_entry",
        related_id=entry.entry_id,
        status=AITask.Status.PENDING,
    )
    for task in pending_tasks:
        if task.billing_reservation_id:
            cancel_billable_ai_task(task.task_id, reason="Writing entry deleted", error_code="writing_entry_deleted")
        else:
            task.status = AITask.Status.CANCELLED
            task.error_code = "writing_entry_deleted"
            task.error_message = "Writing entry deleted"
            task.available_at = None
            task.finished_at = timezone.now()
            task.save(update_fields=["status", "error_code", "error_message", "available_at", "finished_at", "updated_at"])
    entry.delete()
    return {"ok": True}


@transaction.atomic
def create_score_task(user, entry_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    entry = (
        WritingEntry.objects.select_related("user", "prompt", "score")
        .filter(user=user, entry_id=str(entry_id or "").strip())
        .first()
    )
    if not entry:
        raise WritingError("Writing entry not found")
    if not entry.answer.strip():
        raise WritingError("Write an answer before requesting AI scoring.")
    validate_answer_paragraphs(entry.task_type, entry.answer)
    try:
        reserved_u = int(payload.get("reserved_u") or DEFAULT_WRITING_SCORE_RESERVATION_U)
    except (TypeError, ValueError) as exc:
        raise WritingError("reserved_u must be a positive integer") from exc
    answer_hash = hashlib.sha1(entry.answer.encode("utf-8")).hexdigest()[:16]
    idempotency_key = f"writing_score:{entry.entry_id}:{answer_hash}"
    try:
        task, created = create_billable_ai_task(
            user=user,
            task_type="writing_score",
            reserved_u=reserved_u,
            idempotency_key=idempotency_key,
            provider=payload.get("provider"),
            model=str(payload.get("model") or ""),
            related_type="writing_entry",
            related_id=entry.entry_id,
            prompt_version=str(payload.get("prompt_version") or "writing_score_v1"),
            request_payload={
                "entry_id": entry.entry_id,
                "task_type": entry.task_type,
                "prompt_id": entry.prompt.prompt_id if entry.prompt_id else "",
                "prompt": entry.prompt_text,
                "answer": entry.answer,
                "word_count": entry.word_count,
                "answer_hash": answer_hash,
            },
            metadata={"source": "writing_score_task"},
        )
    except AIOrchestrationError as exc:
        raise WritingError(str(exc)) from exc
    return {"created": created, "task": task_payload(task), "entry": entry_payload(entry)}


def decimal_band(value: float) -> Decimal:
    return Decimal(str(round(float(value) * 2) / 2)).quantize(Decimal("0.1"))


def task_score_key(task_type: str) -> str:
    return "task_achievement" if task_type == WritingPrompt.TaskType.TASK1_ACADEMIC else "task_response"


def fallback_analysis_payload(entry: WritingEntry, reason: str = "") -> dict[str, Any]:
    paragraphs = writing_paragraphs(entry.answer)
    message = reason or "AI writing report analysis is unavailable."
    return {
        "overall_review": "AI 写作报告暂不可用，当前结果是本地兜底评分。",
        "practice_focus": "请稍后重新生成 AI 报告；本地兜底不会判断你的逻辑分段。",
        "model_answer": "",
        "paragraph_reviews": [
            {
                "index": index + 1,
                "learner": paragraph,
                "model": "",
                "coaching": "本段尚未经过 AI 逻辑分析。",
            }
            for index, paragraph in enumerate(paragraphs)
        ],
        "inline_annotations": [],
        "spelling_correction_summary": "",
        "expression_upgrade_summary": "",
        "structure_advice_only": True,
        "structure_advice": message,
        "analysis_backend": "fallback",
        "fallback_reason": reason,
    }


def normalize_paragraph_reviews(value: Any, *, require_model: bool, spelling_summary: Any = "") -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise WritingError("AI structured analysis must include paragraph_reviews")
    reviews: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise WritingError("AI paragraph review rows must be objects")
        learner = str(item.get("learner") or "").strip()
        model = str(item.get("model") or "").strip()
        coaching = str(item.get("coaching") or "").strip()
        if not learner or not coaching or (require_model and not model):
            raise WritingError("AI paragraph review rows must include learner, model, and coaching")
        reviews.append(
            {
                "index": int(item.get("index") or index),
                "learner": learner,
                "model": model,
                "coaching": strip_spelling_from_paragraph_coaching(coaching, spelling_summary=spelling_summary),
                "language_correction_upgrade": strip_spelling_from_language_upgrade(
                    item.get("language_correction_upgrade") or item.get("expression_upgrade") or "",
                    spelling_summary=spelling_summary,
                ),
            }
        )
    return reviews


def normalize_inline_annotations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    allowed_types = {"spelling", "punctuation", "format", "grammar", "word_choice", "missing_word", "extra_word"}
    annotations: list[dict[str, Any]] = []
    for item in value[:40]:
        if not isinstance(item, dict):
            continue
        original = str(item.get("original") or "").strip()
        if not original:
            continue
        annotation_type = str(item.get("type") or item.get("category") or "grammar").strip().lower()
        if annotation_type not in allowed_types:
            annotation_type = "grammar"
        paragraph_index = item.get("paragraph_index")
        try:
            paragraph_index = int(paragraph_index) if paragraph_index not in (None, "") else None
        except (TypeError, ValueError):
            paragraph_index = None
        annotations.append(
            {
                "paragraph_index": paragraph_index,
                "original": original[:300],
                "type": annotation_type,
                "suggestion": str(item.get("suggestion") or "").strip()[:300],
                "explanation": str(item.get("explanation") or item.get("reason") or "").strip()[:500],
                "severity": str(item.get("severity") or "medium").strip().lower()[:40],
            }
        )
    return annotations


def normalize_analysis_payload(entry: WritingEntry, score: dict[str, Any]) -> dict[str, Any]:
    backend = str(score.get("backend") or "ai")
    if backend == "fallback":
        supplied = score.get("analysis_payload")
        if isinstance(supplied, dict):
            return {**supplied, "analysis_backend": "fallback"}
        return fallback_analysis_payload(entry, str(score.get("fallback_reason") or ""))

    overall_review = str(score.get("overall_review") or "").strip()
    practice_focus = str(score.get("practice_focus") or "").strip()
    if not overall_review or not practice_focus:
        raise WritingError("AI structured analysis must include overall_review and practice_focus")

    advice_only = bool(score.get("structure_advice_only"))
    structure_advice = str(score.get("structure_advice") or "").strip()
    spelling_summary = str(score.get("spelling_correction_summary") or "").strip()
    if advice_only:
        if not structure_advice:
            raise WritingError("AI structure-advice-only reports must include structure_advice")
        paragraph_reviews = normalize_paragraph_reviews(
            score.get("paragraph_reviews"),
            require_model=False,
            spelling_summary=spelling_summary,
        ) if isinstance(score.get("paragraph_reviews"), list) else []
        model_answer = ""
    else:
        paragraph_reviews = normalize_paragraph_reviews(
            score.get("paragraph_reviews"),
            require_model=True,
            spelling_summary=spelling_summary,
        )
        model_answer = str(score.get("model_answer") or "").strip()

    return {
        "overall_review": overall_review,
        "practice_focus": practice_focus,
        "model_answer": model_answer,
        "paragraph_reviews": paragraph_reviews,
        "inline_annotations": normalize_inline_annotations(score.get("inline_annotations")),
        "spelling_correction_summary": spelling_summary,
        "expression_upgrade_summary": str(score.get("expression_upgrade_summary") or "").strip(),
        "structure_advice_only": advice_only,
        "structure_advice": structure_advice,
        "analysis_backend": "ai",
    }


def persist_score(entry: WritingEntry, score: dict[str, Any]) -> None:
    task_response_value = score.get(task_score_key(entry.task_type))
    analysis_payload = normalize_analysis_payload(entry, score)
    WritingScore.objects.update_or_create(
        entry=entry,
        defaults={
            "user": entry.user,
            "overall_band": decimal_band(score["overall_band"]),
            "task_response": decimal_band(task_response_value),
            "coherence_cohesion": decimal_band(score["coherence_cohesion"]),
            "lexical_resource": decimal_band(score["lexical_resource"]),
            "grammar_range_accuracy": decimal_band(score["grammatical_range_accuracy"]),
            "feedback_markdown": score["feedback_markdown"],
            "grammar_corrections": score.get("grammar_corrections") or [],
            "analysis_payload": analysis_payload,
            "source": str(score.get("backend") or "ai"),
            "billing_metadata": score.get("billing_usage") or {},
            "scored_at": timezone.now(),
        },
    )
    entry.status = WritingEntry.Status.SCORED
    entry.saved_at = entry.saved_at or timezone.now()
    entry.practice_date = entry.practice_date or timezone.localdate()
    entry.save(update_fields=["status", "saved_at", "practice_date", "updated_at"])


def fallback_score(task_type: str, answer: str, reason: str = "") -> dict[str, Any]:
    count = word_count(answer)
    if count >= 250:
        base = 5.5
    elif count >= 150:
        base = 5.0
    elif count >= 80:
        base = 4.5
    else:
        base = 4.0
    task_key = "task_achievement" if task_type == WritingPrompt.TaskType.TASK1_ACADEMIC else "task_response"
    task_label = "Task Achievement" if task_type == WritingPrompt.TaskType.TASK1_ACADEMIC else "Task Response"
    feedback = "\n".join(
        [
            "AI 评分生成失败，以下是系统默认建议。",
            "",
            f"- 先按 {task_label} 检查是否完整回应题目要求。",
            "- 每个主体段保留一个清楚中心句，再用具体细节或数据支持。",
            "- 写完后优先检查句子结构、连接词和重复用词。",
            "- 语法错误纠正：",
            "  1. 无",
        ]
    )
    return {
        "overall_band": base,
        task_key: base,
        "coherence_cohesion": base,
        "lexical_resource": base,
        "grammatical_range_accuracy": base,
        "feedback_markdown": feedback,
        "grammar_corrections": [],
        "backend": "fallback",
        "billing_usage": {},
        "fallback_reason": reason,
    }


def writing_tag_text(tag: str) -> str:
    return {
        "under_length": "字数偏短，展开和论证材料还不够。",
        "weak_task_achievement": "Task 1 对题目/图表信息覆盖不够稳定。",
        "weak_task_response": "Task 2 观点回应和论证深度需要加强。",
        "coherence_issue": "段落衔接和中心句组织需要更清楚。",
        "weak_lexical_resource": "词汇变化和准确度还可以继续提升。",
        "grammar_accuracy": "句子结构和语法准确度是当前重点。",
        "fallback_scoring": "本次使用系统默认评分，画像证据权重较低。",
    }.get(tag, tag.replace("_", " "))


def profile_tags(entry: WritingEntry, score: dict[str, Any]) -> list[str]:
    task_key = "task_achievement" if entry.task_type == WritingPrompt.TaskType.TASK1_ACADEMIC else "task_response"
    tags = []
    if (entry.task_type == WritingPrompt.TaskType.TASK1_ACADEMIC and entry.word_count < 150) or (entry.task_type == WritingPrompt.TaskType.TASK2 and entry.word_count < 250):
        tags.append("under_length")
    if float(score.get(task_key) or 0) <= 5.0:
        tags.append("weak_task_achievement" if entry.task_type == WritingPrompt.TaskType.TASK1_ACADEMIC else "weak_task_response")
    if float(score.get("coherence_cohesion") or 0) <= 5.0:
        tags.append("coherence_issue")
    if float(score.get("lexical_resource") or 0) <= 5.0:
        tags.append("weak_lexical_resource")
    if float(score.get("grammatical_range_accuracy") or 0) <= 5.0 or score.get("grammar_corrections"):
        tags.append("grammar_accuracy")
    if score.get("backend") == "fallback":
        tags.append("fallback_scoring")
    return sorted(dict.fromkeys(tags))


def infer_primary_focus(tag_counts: dict[str, int]) -> str:
    priority = ["weak_task_response", "weak_task_achievement", "under_length", "coherence_issue", "grammar_accuracy", "weak_lexical_resource"]
    ranked = sorted(tag_counts.items(), key=lambda item: (-int(item[1] or 0), priority.index(item[0]) if item[0] in priority else 99))
    return ranked[0][0] if ranked else "insufficient_data"


def update_profile(entry: WritingEntry, score: dict[str, Any]) -> dict[str, Any]:
    profile, _created = WritingLearnerProfile.objects.get_or_create(user=entry.user)
    previous_total = profile.total_scored
    new_total = previous_total + 1
    profile.total_scored = new_total
    task_counts = dict(profile.task_counts or {})
    task_counts[entry.task_type] = int(task_counts.get(entry.task_type) or 0) + 1
    profile.task_counts = task_counts
    band = float(score.get("overall_band") or 0)
    previous_average = float(profile.average_overall_band) if profile.average_overall_band is not None else band
    profile.average_overall_band = Decimal(str(round(((previous_average * previous_total) + band) / new_total, 2))).quantize(Decimal("0.01"))
    averages = dict(profile.criterion_averages or {})
    for key in ("task_achievement", "task_response", "coherence_cohesion", "lexical_resource", "grammatical_range_accuracy"):
        if score.get(key) is None:
            continue
        value = float(score[key])
        previous_value = float(averages.get(key)) if averages.get(key) is not None else value
        averages[key] = round(((previous_value * previous_total) + value) / new_total, 2)
    profile.criterion_averages = averages
    tags = profile_tags(entry, score)
    tag_counts = dict(profile.tag_counts or {})
    for tag in tags:
        tag_counts[tag] = int(tag_counts.get(tag) or 0) + 1
    profile.tag_counts = tag_counts
    primary_focus = infer_primary_focus({tag: count for tag, count in tag_counts.items() if tag != "fallback_scoring"})
    profile.primary_focus = primary_focus
    profile.primary_focus_text = writing_tag_text(primary_focus) if primary_focus != "insufficient_data" else "还需要更多已评分作文来形成稳定画像。"
    evidence_item = f"{WRITING_TASK_LABELS[entry.task_type]} · Band {score.get('overall_band', '—')} · {entry.word_count} words · {', '.join(writing_tag_text(tag) for tag in tags[:3]) or '暂无明显弱项'}"
    profile.recent_evidence = ([evidence_item] + [str(item) for item in profile.recent_evidence or [] if str(item) != evidence_item])[:8]
    profile.profile_payload = {"last_entry_id": entry.entry_id, "last_score_source": score.get("backend")}
    profile.save()
    score["profile_tags"] = tags
    score["personalization_note"] = "本次 AI 评分与辅导已用于更新你的写作画像。"
    return profile_snapshot(profile) or {}


@transaction.atomic
def score_entry(user, entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    entry = WritingEntry.objects.select_related("user", "prompt").filter(user=user, entry_id=str(entry_id or "").strip()).first()
    if not entry:
        raise WritingError("Writing entry not found")
    if payload.get("answer") is not None:
        entry.answer = str(payload.get("answer") or "")
        entry.word_count = word_count(entry.answer)
    if not entry.answer.strip():
        raise WritingError("Write an answer before requesting AI scoring.")
    validate_answer_paragraphs(entry.task_type, entry.answer)
    entry.saved_at = entry.saved_at or timezone.now()
    entry.practice_date = entry.practice_date or timezone.localdate()
    score = fallback_score(entry.task_type, entry.answer)
    persist_score(entry, score)
    entry.save(update_fields=["answer", "word_count", "updated_at"])
    score["writing_profile"] = update_profile(entry, score)
    entry.refresh_from_db()
    return entry_payload(entry)


def normalize_score_payload(entry: WritingEntry, payload: dict[str, Any]) -> dict[str, Any]:
    score = payload.get("score") if isinstance(payload.get("score"), dict) else payload
    if not isinstance(score, dict):
        raise WritingError("score must be an object")
    task_key = task_score_key(entry.task_type)
    required = ["overall_band", task_key, "coherence_cohesion", "lexical_resource", "grammatical_range_accuracy"]
    missing = [key for key in required if score.get(key) is None]
    if missing:
        raise WritingError(f"Missing score fields: {', '.join(missing)}")
    return {
        "overall_band": float(score["overall_band"]),
        task_key: float(score[task_key]),
        "coherence_cohesion": float(score["coherence_cohesion"]),
        "lexical_resource": float(score["lexical_resource"]),
        "grammatical_range_accuracy": float(score["grammatical_range_accuracy"]),
        "feedback_markdown": str(score.get("feedback_markdown") or ""),
        "grammar_corrections": score.get("grammar_corrections") if isinstance(score.get("grammar_corrections"), list) else [],
        "overall_review": str(score.get("overall_review") or payload.get("overall_review") or ""),
        "practice_focus": str(score.get("practice_focus") or payload.get("practice_focus") or ""),
        "model_answer": str(score.get("model_answer") or payload.get("model_answer") or ""),
        "paragraph_reviews": score.get("paragraph_reviews") if isinstance(score.get("paragraph_reviews"), list) else payload.get("paragraph_reviews"),
        "inline_annotations": score.get("inline_annotations") if isinstance(score.get("inline_annotations"), list) else payload.get("inline_annotations"),
        "spelling_correction_summary": str(score.get("spelling_correction_summary") or payload.get("spelling_correction_summary") or ""),
        "expression_upgrade_summary": str(score.get("expression_upgrade_summary") or payload.get("expression_upgrade_summary") or ""),
        "structure_advice_only": bool(score.get("structure_advice_only") or payload.get("structure_advice_only")),
        "structure_advice": str(score.get("structure_advice") or payload.get("structure_advice") or ""),
        "backend": str(score.get("backend") or "ai"),
        "billing_usage": payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
    }


def get_writing_score_task_and_entry(task_id: str) -> tuple[AITask, WritingEntry]:
    task = (
        AITask.objects.select_for_update()
        .select_related("user")
        .filter(task_id=str(task_id or "").strip(), task_type="writing_score", related_type="writing_entry")
        .first()
    )
    if not task:
        raise WritingError("Writing score task not found")
    entry = WritingEntry.objects.select_related("user", "prompt", "score").filter(user=task.user, entry_id=task.related_id).first()
    if not entry:
        raise WritingEntryDeleted("Writing entry was deleted")
    return task, entry


@transaction.atomic
def complete_score_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    task, entry = get_writing_score_task_and_entry(task_id)
    if task.is_terminal:
        return entry_payload(entry)
    score = normalize_score_payload(entry, payload)
    persist_score(entry, score)
    score["writing_profile"] = update_profile(entry, score)
    try:
        succeed_billable_ai_task(task.task_id, {"entry_id": entry.entry_id, "score": score}, payload.get("usage") if isinstance(payload.get("usage"), dict) else {})
    except AIOrchestrationError as exc:
        raise WritingError(str(exc)) from exc
    entry.refresh_from_db()
    return entry_payload(entry)


@transaction.atomic
def fallback_score_task(task_id: str, reason: str = "") -> dict[str, Any]:
    task, entry = get_writing_score_task_and_entry(task_id)
    if task.is_terminal:
        return entry_payload(entry)
    score = fallback_score(entry.task_type, entry.answer, reason=reason)
    persist_score(entry, score)
    score["writing_profile"] = update_profile(entry, score)
    try:
        fallback_billable_ai_task(task.task_id, reason or "AI scoring unavailable", {"entry_id": entry.entry_id, "score": score})
    except AIOrchestrationError as exc:
        raise WritingError(str(exc)) from exc
    entry.refresh_from_db()
    return entry_payload(entry)
