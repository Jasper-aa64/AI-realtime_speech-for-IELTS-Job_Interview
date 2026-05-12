# Personalized Coaching Design Notes

## Current State

The existing `ai_coaching` chain is turn-local:

- Input: current question, current transcript, Band 7 version.
- Output: short Markdown coaching.
- Fallback: answer length bucket and a generic next-step pattern.

This is useful for one answer, but it does not remember the learner's repeated habits.

## Upgrade Direction

Professional language products usually personalize from observed behavior:

- Writing assistants use local context and user goals to select the highest-value suggestion.
- Speaking products emphasize specific evidence, repeated error categories, and practice loops.
- Spaced practice systems use history to decide what should reappear.

For this repo, the pragmatic version is:

- Build a compact `learning_profile` from current attempt + weak-item history.
- Feed that profile into Codex per-turn coaching.
- Render a report-level plan that tells the user what to fix first.
- Keep hidden scheduling data internal, but use it as evidence for coaching.

## Data Shape

Suggested report additions:

```json
{
  "learning_profile": {
    "primary_focus": "answer_development",
    "habit_tags": ["short_answer", "generic_language"],
    "recurring_weak_reasons": ["short_answer", "pronunciation_unreliable"],
    "repeated_phrases": ["it is very important"],
    "part_focus": {"p2": "sustained long-turn development"},
    "evidence": ["P2 answer has 28 words"]
  },
  "personalized_coaching": {
    "headline": "...",
    "focus": "...",
    "evidence": ["..."],
    "next_practice": ["..."],
    "habit_tags": ["..."]
  }
}
```

## Guardrails

- Do not show raw weak-item scheduler internals as a separate report module.
- Do not claim medical/psychological learner traits.
- Keep advice concrete and evidence-backed.
- Preserve older history rendering when fields are absent.
