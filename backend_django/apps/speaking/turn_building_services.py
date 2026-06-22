from __future__ import annotations

import itertools
import random
from collections import Counter
from typing import Any

FIXED_EXAMINER_TTS_ITEMS = [
    {
        "key": "fixed_examiner_what_is_your_full_name",
        "text": "What is your full name?",
    },
    {
        "key": "fixed_examiner_do_you_work_or_do_you_study",
        "text": "Do you work or do you study?",
    },
    {
        "key": "fixed_examiner_p2_cue_card_instruction",
        "text": (
            "I'm going to give you a topic and I would like you to talk about it for one to two minutes. "
            "You have one minute to think about what you are going to say. "
            "You can make some notes if you wish."
        ),
    },
]


def _is_p1_work_study_identity_question(question: str) -> bool:
    normalized = "".join(c if c.isalnum() else " " for c in question.lower()).strip()
    phrases = [
        "do you work or are you",
        "are you a student or do you work",
        "do you work or study",
        "are you working or studying",
    ]
    return any(phrase in normalized for phrase in phrases)


def _cue_to_text(topic: dict[str, Any]) -> str:
    bullets = "\n".join(f"- {item}" for item in topic.get("bullets", []))
    return f"{topic.get('title', '')}\n\nYou should say:\n{bullets}\n\n{topic.get('rounding', '')}".strip()


def _cue_examiner_text() -> str:
    return FIXED_EXAMINER_TTS_ITEMS[2]["text"]


def _timers_for_part(part: str) -> dict[str, Any]:
    defaults = {"prep_seconds": 3, "speak_seconds": 60}
    if part == "p1":
        return {"prep_seconds": 3, "speak_seconds": 35}
    if part == "p2":
        return {"prep_seconds": 60, "speak_seconds": 120}
    if part == "p3":
        return {"prep_seconds": 7, "speak_seconds": 75}
    return defaults


def _normalize_question_text(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _completed_answered_practice_rows(user: Any, part: str) -> list[tuple[str, Any]]:
    """Return durable question/timestamp pairs after AI feedback completed.

    A selected question is not practice yet: the learner may leave immediately,
    abort the attempt, or submit no recording. Training observations are the
    durable source because report deletion is a user-facing management action and
    must not erase scheduling history. Existing scored report turns supplement old
    or test data that predates observations. Attempt/turn identities deduplicate
    the two sources.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    try:
        from .models import SpeakingAttempt, SpeakingTrainingObservation, SpeakingTurn

        events: list[tuple[str, Any]] = []
        observed_turns: set[tuple[str, str]] = set()
        observation_rows = (
            SpeakingTrainingObservation.objects.filter(user=user, part="p1").values_list(
                "question",
                "observed_at",
                "transcript",
                "legacy_attempt_id",
                "legacy_turn_id",
            )
            if part == "p1"
            else []
        )
        for question, observed_at, transcript, attempt_id, turn_id in observation_rows:
            if not str(transcript or "").strip():
                continue
            events.append((question, observed_at))
            if attempt_id and turn_id:
                observed_turns.add((str(attempt_id), str(turn_id)))

        turn_rows = SpeakingTurn.objects.filter(
            user=user,
            part=part,
            attempt__status=SpeakingAttempt.Status.SCORED,
            attempt__report__isnull=False,
        ).values_list(
            "question",
            "created_at",
            "transcript_cleaned",
            "transcript_raw",
            "attempt__attempt_id",
            "turn_id",
        )
        for question, created_at, transcript_cleaned, transcript_raw, attempt_id, turn_id in turn_rows:
            if not str(transcript_cleaned or transcript_raw or "").strip():
                continue
            if (str(attempt_id), str(turn_id)) in observed_turns:
                continue
            events.append((question, created_at))
        events.sort(key=lambda row: (row[1] is None, row[1]))
        return events
    except Exception:
        return []


def _p1_balanced_practice_ledger(
    user: Any,
    topics: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, int], dict[str, float]]:
    """Build coverage-round counts for current P1 bank questions.

    A split topic always repeats its opener for conversational flow. That repeated
    opener advances only when it is on the topic's current minimum count tier. If
    some sibling questions are still on a lower tier, the opener remains unchanged
    while those new questions catch up. Thus one complete pass leaves every bank
    question at one instead of letting the opener race ahead.
    """
    topic_norms: dict[str, list[str]] = {}
    norm_topic: dict[str, str] = {}
    for topic, items in topics.items():
        norms = list(dict.fromkeys(
            _normalize_question_text(str(item.get("question") or ""))
            for item in items
            if _normalize_question_text(str(item.get("question") or ""))
        ))
        topic_norms[topic] = norms
        for norm in norms:
            norm_topic.setdefault(norm, topic)

    counts: Counter[str] = Counter()
    last_seen: dict[str, float] = {}
    for question, created_at in _completed_answered_practice_rows(user, "p1"):
        norm = _normalize_question_text(question)
        topic = norm_topic.get(norm)
        if not topic:
            continue
        siblings = topic_norms.get(topic) or []
        floor = min((counts.get(sibling, 0) for sibling in siblings), default=0)
        if counts.get(norm, 0) > floor:
            continue
        counts[norm] += 1
        if created_at is not None:
            last_seen[norm] = created_at.timestamp()
    return dict(counts), last_seen


def _p1_balanced_practice_counts(
    user: Any,
    topics: dict[str, list[dict[str, Any]]],
) -> dict[str, int]:
    counts, _last_seen = _p1_balanced_practice_ledger(user, topics)
    return counts


def _p1_topic_practice_counts(
    user: Any, topics: dict[str, list[dict[str, Any]]]
) -> dict[str, int]:
    """Per-topic practice count for this user, summed over the topic's questions.

    Counts come from the user's historical P1 turns (matched on question text),
    so "least-practiced first" needs no extra schema. Returns {} when there is no
    authenticated user or on any query error, which makes topic selection fall
    back to plain random.
    """
    practiced_counts = _p1_balanced_practice_counts(user, topics)
    if not practiced_counts:
        return {}
    topic_counts: dict[str, int] = {}
    for topic, items in topics.items():
        topic_counts[topic] = sum(
            practiced_counts.get(_normalize_question_text(str(it.get("question") or "")), 0)
            for it in items
        )
    return topic_counts


def _p1_topic_practice_debt(
    user: Any, topics: dict[str, list[dict[str, Any]]]
) -> dict[str, dict[str, Any]]:
    """Per-topic practice debt used to prioritise the least-practiced material.

    For every topic returns:
      - unpracticed:    how many of its bank questions the user has never done,
      - total_practice: the sum of practice counts over its questions,
      - last_ts:        epoch seconds of the most recent time any of its questions
                        was practised, or None if never.

    Anonymous users / query errors fall back to "all unpracticed, never seen", so a
    fresh user's selection is driven purely by coverage + randomness.
    """
    base = {
        name: {"unpracticed": len(items), "total_practice": 0, "last_ts": None}
        for name, items in topics.items()
    }
    counts, last_seen = _p1_balanced_practice_ledger(user, topics)
    if not counts:
        return base
    debt: dict[str, dict[str, Any]] = {}
    for name, items in topics.items():
        norms = [_normalize_question_text(str(it.get("question") or "")) for it in items]
        debt[name] = {
            "unpracticed": sum(1 for n in norms if counts.get(n, 0) == 0),
            "total_practice": sum(counts.get(n, 0) for n in norms),
            "last_ts": max((last_seen[n] for n in norms if n in last_seen), default=None),
        }
    return debt


def _weighted_topic_order(topic_names: list[str], counts: dict[str, int]) -> list[str]:
    """Permutation of topics biased toward least-practiced (weight 1/(count+1)).

    Unpractised topics are most likely to lead, but every ordering stays possible
    so sessions are not identical. With no counts this is a plain shuffle.
    """
    pool = list(topic_names)
    random.shuffle(pool)
    if not counts:
        return pool
    order: list[str] = []
    while pool:
        weights = [1.0 / (counts.get(name, 0) + 1) for name in pool]
        pick = random.choices(pool, weights=weights, k=1)[0]
        order.append(pick)
        pool.remove(pick)
    return order


def _question_practice_counts(user: Any, part: str) -> dict[str, int]:
    """Per-question practice counts for this user within one part, keyed by
    normalized text. Returns {} for anonymous users or on error, so selection
    falls back to plain random.
    """
    practiced = [question for question, _created_at in _completed_answered_practice_rows(user, part)]
    if not practiced:
        return {}
    return dict(Counter(_normalize_question_text(q) for q in practiced))


def _p3_question_practice_counts(user: Any) -> dict[str, int]:
    """Per-question P3 practice counts (thin wrapper over the generic helper)."""
    return _question_practice_counts(user, "p3")


def _select_least_practiced_items(
    items: list[dict[str, Any]],
    count: int,
    counts: dict[str, int],
    pin_first: bool = False,
) -> list[dict[str, Any]]:
    """Pick `count` bank items favouring the least-practiced (weight 1/(n+1)),
    then restore their original bank order so the questions still flow naturally.

    This is the per-topic coverage guard: questions the user has never practised
    carry count 0 (max weight) and are drawn first, so repeated sessions walk
    through a topic's whole question list before any question repeats — no item
    is ever starved. With no history it degrades to a plain sample.

    `pin_first` always keeps the topic's first bank question — its natural opener
    (e.g. "Where are you living at the moment?"). Without this, the most-practiced
    opener gets starved out by the least-practiced weighting, so the session starts
    mid-topic ("What kind of area is it?") with no context. The remaining slots are
    still filled least-practiced first.
    """
    if count >= len(items):
        return list(items)
    indexed = list(enumerate(items))
    chosen: list[tuple[int, dict[str, Any]]] = []
    pool = list(indexed)
    if pin_first and count >= 1 and pool:
        chosen.append(pool.pop(0))  # the opener (original index 0)
    random.shuffle(pool)
    if not counts:
        chosen.extend(pool[: count - len(chosen)])
    else:
        # Shuffle first to vary ties, then exhaust each lower-count tier before
        # admitting any more-practised question. This makes coverage a hard
        # priority instead of the old probabilistic weight that could repeat a
        # question while an unseen one was still available.
        pool.sort(
            key=lambda pair: counts.get(
                _normalize_question_text(str(pair[1].get("question") or "")), 0
            )
        )
        chosen.extend(pool[: count - len(chosen)])
    chosen.sort(key=lambda pair: pair[0])
    return [it for _, it in chosen]


def _p1_topic_want_options(
    size: int, split_threshold: int, split_min: int, split_max: int
) -> list[int]:
    """Allowed pick counts for one topic given its bank size.

    Small topics (< split_threshold, e.g. 1-7 questions) are taken WHOLE — the whole
    group rides together. Big topics (>= split_threshold, e.g. 8+) are never dumped
    whole; they are split into split_min..split_max questions and the rest is left for
    a later session. Returns the candidate pick counts to enumerate.
    """
    if size <= 0:
        return []
    if size >= split_threshold:
        hi = min(split_max, size)
        return [w for w in range(split_min, hi + 1)] or [hi]
    return [size]


def _p1_body_fallback(
    topics: dict[str, list[dict[str, Any]]],
    ranked: list[str],
    question_counts: dict[str, int],
    body_min: int,
    body_max: int,
    split_threshold: int,
    split_max: int,
) -> list[dict[str, Any]]:
    """Degenerate path when no 2-/3-topic combo can total body_min..body_max (a tiny
    bank). Walk the most-due topics, take each whole (small) or capped (big), and stop
    once we have enough; keeps the opener-first + contiguous guarantees."""
    body: list[dict[str, Any]] = []
    for name in ranked:
        size = len(topics[name])
        want = min(split_max, size) if size >= split_threshold else size
        body.extend(_select_least_practiced_items(topics[name], want, question_counts, pin_first=True))
        if len(body) >= body_min:
            break
    return body


def _p1_selected_practice_values(
    items: list[dict[str, Any]],
    count: int,
    counts: dict[str, int],
    *,
    pin_first: bool = True,
) -> list[int]:
    """Return count values for the questions a topic slice will really select."""
    values = [
        counts.get(_normalize_question_text(str(item.get("question") or "")), 0)
        for item in items
    ]
    if count >= len(values):
        return values
    selected: list[int] = []
    pool = list(values)
    if pin_first and count >= 1 and pool:
        selected.append(pool.pop(0))
    pool.sort()
    selected.extend(pool[: count - len(selected)])
    return selected


def select_p1_body_questions(
    topics: dict[str, list[dict[str, Any]]],
    topic_debt: dict[str, dict[str, Any]],
    question_counts: dict[str, int],
    *,
    body_min: int = 9,
    body_max: int = 12,
    split_threshold: int = 8,
    split_min: int = 3,
    split_max: int = 6,
    candidate_topics: int = 16,
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    """Assemble the P1 body (the real topic questions, no openers/follow-ups).

    Strategy (see the product spec):
      - Rank topics by practice DEBT — most unpracticed questions first, then fewest
        total practices, then least-recently seen. Practice debt is the top priority:
        it is never sacrificed just to make two tidy whole topics.
      - From the most-due candidates, enumerate every 2- and 3-topic combination and,
        per topic, every allowed pick count (whole for small topics; 3-6 for big
        topics that must be split). Keep only combos whose total lands in
        [body_min, body_max].
      - Score each surviving combo with practice coverage first: most
        never-practiced questions actually asked, then least total historical
        practice. Only after that consider target length, whole-topic completion,
        2-vs-3 topic shape, and random tie-breaking.
      - Materialize the winner: each topic contributes `want` least-practiced
        questions with its opener pinned; topics are emitted most-due first and stay
        contiguous.
    """
    rng = rng or random
    names = [n for n in topics if topics[n]]
    if not names:
        return []

    def debt_of(name: str) -> dict[str, Any]:
        return topic_debt.get(name) or {}

    def debt_key(name: str) -> tuple:
        d = debt_of(name)
        last = d.get("last_ts")
        recency = last if last is not None else -1.0  # never practiced -> oldest -> most due
        size = len(topics[name]) or 1
        # Most-due first: fewest total practices, then the highest unpracticed FRACTION
        # (so a big topic doesn't dominate just by holding more questions), then least
        # recently seen. Random breaks ties, so a brand-new user (everything zero)
        # rotates across topics of all sizes instead of always drilling the largest.
        return (
            int(d.get("total_practice", 0)),
            -int(d.get("unpracticed", 0)) / size,
            recency,
            rng.random(),
        )

    ranked = sorted(names, key=debt_key)
    candidates = ranked[: max(2, min(len(ranked), candidate_topics))]
    sizes = {n: len(topics[n]) for n in candidates}
    want_opts = {
        n: _p1_topic_want_options(sizes[n], split_threshold, split_min, split_max) for n in candidates
    }

    # This session's target body length, random in [min, max], so the part length
    # visibly varies instead of being a fixed number; the scorer prefers combos that
    # hit it, but only after practice debt is satisfied within that length.
    target_len = rng.randint(body_min, body_max)
    # Default to 2 topics ("two complete topics fit"), but ~30% of sessions aim for 3
    # — used to pad up to the target or to split a big topic — so the topic count is
    # not mechanically fixed. Two complete topics still outrank this preference.
    desired_topics = 3 if rng.random() < 0.3 else 2

    best: tuple | None = None
    best_pick: tuple[tuple[str, ...], tuple[int, ...]] | None = None
    for k in (2, 3):
        if len(candidates) < k:
            continue
        for combo in itertools.combinations(candidates, k):
            opt_lists = [want_opts[n] for n in combo]
            if any(not opts for opts in opt_lists):
                continue
            combo_unprac = sum(int(debt_of(n).get("unpracticed", 0)) for n in combo)
            combo_total = sum(int(debt_of(n).get("total_practice", 0)) for n in combo)
            for wants in itertools.product(*opt_lists):
                total = sum(wants)
                if total < body_min or total > body_max:
                    continue
                selected_values = [
                    value
                    for name, want in zip(combo, wants)
                    for value in _p1_selected_practice_values(
                        topics[name], want, question_counts, pin_first=True
                    )
                ]
                sel_unprac = sum(1 for value in selected_values if value == 0)
                sel_total = sum(selected_values)
                full_small = sum(
                    1 for n, w in zip(combo, wants) if sizes[n] < split_threshold and w == sizes[n]
                )
                two_full = 1 if (k == 2 and full_small == 2) else 0
                score = (
                    sel_unprac,     # 0 most never-practiced questions actually asked
                    -sel_total,      # 1 then least practice on the questions actually asked
                    combo_unprac,   # 2 prefer topics with more remaining coverage debt
                    -combo_total,   # 3 then lower overall topic history
                    int(total == target_len),  # 4 then hit this session's random length
                    int(k == desired_topics),  # 5 then prefer this session's 2/3-topic shape
                    two_full,       # 6 then two complete small topics
                    full_small,     # 7 then finish other whole small topics
                    rng.random(),   # 8 vary only among equivalent coverage choices
                )
                if best is None or score > best:
                    best = score
                    best_pick = (combo, wants)

    if best_pick is None:
        return _p1_body_fallback(
            topics, ranked, question_counts, body_min, body_max, split_threshold, split_max
        )

    combo, wants = best_pick
    order = sorted(zip(combo, wants), key=lambda cw: debt_key(cw[0]))
    body: list[dict[str, Any]] = []
    for name, want in order:
        body.extend(_select_least_practiced_items(topics[name], want, question_counts, pin_first=True))
    return body


def _select_p3_followups(followups: list[str], count: int, user: Any = None) -> list[str]:
    """Pick `count` follow-ups, least-practiced first (weight 1/(count+1)).

    A card may carry more bank follow-ups (e.g. 6) than a session should drill;
    this draws `count` of them favouring the ones the user has practised least, so
    repeat sessions rotate through the rest. When there are at most `count`
    follow-ups the list is returned unchanged (callers rely on the order).
    """
    items = [f for f in followups if str(f).strip()]
    if len(items) <= count:
        return items
    counts = _p3_question_practice_counts(user)
    pool = list(items)
    random.shuffle(pool)
    if not counts:
        return pool[:count]
    chosen: list[str] = []
    while pool and len(chosen) < count:
        weights = [1.0 / (counts.get(_normalize_question_text(q), 0) + 1) for q in pool]
        pick = random.choices(pool, weights=weights, k=1)[0]
        chosen.append(pick)
        pool.remove(pick)
    return chosen
