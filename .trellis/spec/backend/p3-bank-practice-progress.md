# P3 Fixed-Bank Practice Progress

## 1. Scope / Trigger

Use this contract whenever fixed P3 follow-ups attached to a P2 bank card are grouped, started, counted, or rendered. It does not apply to P2-report or custom-theme AI-generated P3 plans.

## 2. Signatures

```python
p3_bank_practice_rounds(items: list[Any]) -> list[list[Any]]
p3_bank_practice_completion_counts(user, cue_ids: list[str]) -> dict[str, dict[int, int]]
p3_bank_next_round_index(round_count: int, completion_counts: dict[int, int] | None = None) -> int
```

No new database model is used. Round identity is stored in `SpeakingAttempt.metadata`.

## 3. Contracts

Grouping is deterministic:

- 3-4 questions: one round containing all questions.
- 5 questions: indexes `[0, 1, 2]` and `[3, 4, 2]`.
- 6 questions: indexes `[0, 1, 2]` and `[3, 4, 5]`.
- Larger future banks: balanced rounds of 3-4 questions.

Attempt metadata:

- `p3_bank_cue_id: str`: canonical P2 cue ID.
- `p3_bank_round_index: int`: zero-based selected round.
- `p3_bank_round_count: int`: number of stable rounds.
- `p3_bank_followup_ids: list[str]`: stable IDs in asked order.

Card response fields:

- `practice_round_count: int`
- `practice_completed_round_indexes: list[int]`
- `practice_completed_round_count: int`
- `practice_is_complete: bool`
- `practice_next_round_index: int`

The frontend renders these fields but never recomputes completion.

## 4. Validation & Error Matrix

| Condition | Result |
|---|---|
| Attempt is `started`, `ready_to_score`, or `aborted` | Does not count |
| Attempt is `scored` without `SpeakingReport` | Does not count |
| Attempt is `scored` with `SpeakingReport` | Counts its persisted round |
| Round metadata is missing/invalid | Ignore the row; do not guess |
| All rounds have completed at least once | `practice_is_complete=true`; card stays selectable |

## 5. Good / Base / Bad Cases

- Good: a five-question card completes rounds 0 and 1 through two report-backed attempts, then renders `已完成`.
- Base: an untouched card reports zero completed rounds and selects round 0.
- Bad: an abandoned attempt must not dim the card or advance `已练 1/2`.

## 6. Tests Required

- Unit-test exact grouping for 3, 4, 5, 6, and a larger bank.
- API-test that only report-backed scored attempts advance progress.
- API-test theme-matched bank starts persist the canonical cue ID.
- Test least-practised round selection and stable follow-up IDs.
- Frontend-test partial/completed labels, dim styling, pointer selection, and Enter/Space activation.

## 7. Wrong vs Correct

### Wrong

```python
# Merely assigning questions makes them look practised.
SpeakingAttempt.objects.filter(metadata__p3_bank_cue_id=cue_id).count()
```

### Correct

```python
SpeakingAttempt.objects.filter(
    status=SpeakingAttempt.Status.SCORED,
    report__isnull=False,
    metadata__p3_bank_cue_id=cue_id,
)
```

Grouping and progress remain backend-owned; the UI consumes the returned contract.

