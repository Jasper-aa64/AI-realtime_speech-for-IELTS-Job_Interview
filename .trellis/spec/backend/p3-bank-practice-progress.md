# P3 Fixed-Bank Practice Progress

## 1. Scope / Trigger

Use this contract whenever fixed P3 follow-ups attached to a P2 bank card are grouped, started, counted, or rendered. It does not apply to P2-report or custom-theme AI-generated P3 plans.

## 2. Signatures

```python
p3_bank_practice_rounds(items: list[Any]) -> list[list[Any]]
p3_bank_practice_progress(user, cue_id: str, questions: list[str]) -> dict[str, Any]
p3_bank_next_round_index(round_count: int, completion_counts: dict[int, int] | None = None) -> int
```

`SpeakingTrainingObservation` is the durable counting source. Attempt and round
metadata still identify the started practice, but completion must not depend on
the continued existence of a report.

## 3. Contracts

Grouping is deterministic:

- 3-4 questions: one round containing all questions.
- 5 questions: indexes `[0, 1, 2]` and `[3, 4]`.
- 6 questions: indexes `[0, 1, 2]` and `[3, 4, 5]`.
- Larger future banks: balanced rounds of 3-4 questions.

Attempt metadata:

- `p3_bank_cue_id: str`: canonical P2 cue ID.
- `p3_bank_round_index: int`: zero-based selected round.
- `p3_bank_round_count: int`: number of stable rounds.
- `p3_bank_followup_ids: list[str]`: stable IDs in asked order.

Card response fields:

- `practice_round_count: int`
- `practice_rounds: list[{round_index, question_indexes, followup_ids, is_current_cycle_complete}]`
- `practice_question_counts: dict[str, int]`
- `practice_cycle: int`
- `practice_current_cycle_question_indexes: list[int]`
- `practice_completed_round_indexes: list[int]`
- `practice_completed_round_count: int`
- `practice_is_complete: bool`
- `practice_next_round_index: int`
- `practice_next_question_indexes: list[int]`

The frontend renders these fields but never recomputes completion.

## 4. Validation & Error Matrix

| Condition | Result |
|---|---|
| Attempt is `started`, `ready_to_score`, or `aborted` | Does not count |
| Attempt is `scored` without `SpeakingReport` | Does not count |
| Attempt is `scored` with generated feedback observations | Counts each newly-covered fixed follow-up |
| Report is deleted after feedback observations are written | Count remains |
| Round metadata is missing/invalid | Ignore the row; do not guess |
| A grey/repeated question appears in the same practice session | Do not advance it above lower-count siblings |
| All questions have reached the same count | Next response starts the next `practice_cycle`; card stays selectable and bright again |

## 5. Good / Base / Bad Cases

- Good: a five-question card completes indexes `[0,1,2]`, then renders that left group grey and selects `[3,4]` next.
- Good: after `[3,4]` receives AI feedback, all five questions have count 1, so the next picker open shows cycle 2.
- Base: an untouched card reports zero completed rounds and selects round 0.
- Bad: an abandoned attempt must not dim the card or advance the cycle.

## 6. Tests Required

- Unit-test exact grouping for 3, 4, 5, 6, and a larger bank.
- API-test that only generated `SpeakingTrainingObservation` rows advance progress.
- API-test that deleting a report does not reset progress.
- API-test that repeated/bridge grey questions in the same practice session do not advance ahead of the cycle floor.
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
