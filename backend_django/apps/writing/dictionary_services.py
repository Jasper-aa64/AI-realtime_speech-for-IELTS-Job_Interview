"""Offline English-Chinese dictionary lookup.

Backs the single-word path of the 划词 popup: when the selection is one English
word we show a compact dictionary card (phonetic + Chinese senses + English
definition) instead of running a full-sentence online translation.

Data source: a compact SQLite built from ECDICT, filtered to common / exam
vocabulary (Collins / Oxford / BNC / COCA frequency or zk/gk/cet/ky/ielts/toefl/
gre tags). Regenerate with `manage.py build_offline_dictionary <ecdict.csv>`.
The DB is read-only at runtime and bundled in the repo, separate from the
mutable runtime db.sqlite3.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

from django.conf import settings

_DICT_PATH = Path(settings.BASE_DIR).parent / "data" / "dictionary" / "offline_dict.sqlite3"

_conn_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_conn_failed = False

_SINGLE_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]*$")


def normalize_lookup_word(text: str) -> str:
    return (text or "").strip().lower()


def is_single_dictionary_word(text: str) -> bool:
    """A lookup candidate: one English token (letters, internal '/-' allowed)."""
    word = (text or "").strip()
    if not word or len(word) > 32:
        return False
    return bool(_SINGLE_WORD_RE.match(word))


def _get_conn() -> sqlite3.Connection | None:
    global _conn, _conn_failed
    if _conn is not None:
        return _conn
    if _conn_failed:
        return None
    with _conn_lock:
        if _conn is not None:
            return _conn
        if _conn_failed:
            return None
        if not _DICT_PATH.exists():
            _conn_failed = True
            return None
        try:
            _conn = sqlite3.connect(
                f"file:{_DICT_PATH.as_posix()}?mode=ro",
                uri=True,
                check_same_thread=False,
            )
        except sqlite3.Error:
            _conn_failed = True
            return None
        return _conn


def _split_senses(translation: str) -> list[str]:
    if not translation:
        return []
    # ECDICT separates senses with the literal two-character sequence "\n"
    # (backslash + n), and occasionally real newlines or ';'.
    parts = re.split(r"\\n|[\n;]+", translation)
    return [p.strip() for p in parts if p.strip()]


def lookup_word(text: str) -> dict | None:
    """Return a dictionary entry for an exact (case-insensitive) word, or None."""
    word = normalize_lookup_word(text)
    if not word:
        return None
    conn = _get_conn()
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT word, phonetic, translation, definition FROM entries WHERE word = ? LIMIT 1",
            (word,),
        ).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    db_word, phonetic, translation, definition = row
    return {
        "word": db_word or word,
        "phonetic": (phonetic or "").strip(),
        "translation": (translation or "").strip(),
        "senses": _split_senses(translation or ""),
        "definition": (definition or "").strip(),
    }


def dictionary_available() -> bool:
    return _get_conn() is not None
