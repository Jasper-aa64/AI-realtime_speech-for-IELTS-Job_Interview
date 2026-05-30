"""Writing prompt catalog, seed synchronization, and agent search services.

This module owns the writing prompt bank boundary. `apps.writing.services`
re-exports these functions as a compatibility facade for views, tests, and
existing scripts.
"""

import hashlib
import json
import random
import re
import sqlite3
import threading
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, Max, OuterRef, Q
from django.utils import timezone

from .models import WritingEntry, WritingPrompt, WritingScore
from .search_utils import (
    QUERY_EXPANSION_LIMIT,
    QUERY_EXPANSIONS,
    expanded_search_terms,
    query_concepts as expanded_query_concepts,
    search_base_tokens,
    search_normalize,
    unique_terms,
)
from .validation import WRITING_TASK_TYPES, WritingError, normalize_task_type


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
