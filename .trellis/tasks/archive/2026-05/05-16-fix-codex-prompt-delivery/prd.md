# Fix Django Speaking Codex Prompt Delivery

## Goal

Fix the root cause of AI coaching not working: `run_codex()` not properly delivering prompt to Codex CLI. Then migrate all missing helper functions from old server to achieve feature parity.

## Root Cause Analysis

Django `run_codex()` calls:
```python
[codex, "exec", "--json", *config_args]
input=prompt
```

This does NOT deliver prompt to the model. Verified output:
```
thread.started
turn.started
turn.completed usage input_tokens=0 output_tokens=0
```

Model receives 0 tokens → no real AI output → all coaching/scores fallback.

**Fix:** Add `-` argument to read from stdin:
```python
[codex, "exec", "--json", *config_args, "-"]
```

## Missing Functions in Django (16 functions)

### Text Processing (6)
| Function | Purpose | Status |
|----------|---------|--------|
| `clean_markdown_text()` | Clean and normalize markdown | Missing |
| `clean_report_text()` | Clean report text for display | Missing |
| `normalize_coaching_markdown()` | Normalize coaching format | Missing |
| `concise_coaching_markdown()` | Validate coaching format (has grammar bullet, not too long) | Missing |
| `ensure_grammar_correction_bullet()` | Ensure grammar correction bullet exists | Missing |
| `infer_grammar_corrections()` | Infer grammar corrections from transcript | Missing |
| `spoken_markdown()` | Format spoken text with paragraphs | Missing |

### Model Answer (3)
| Function | Purpose | Status |
|----------|---------|--------|
| `model_answer_constraints()` | Get part-specific constraints for Band 7 | Missing |
| `target_band_label()` | Get target band label | Missing |
| `_transcript_usable_for_band7()` | Check if transcript is usable | Missing |

### Coaching (4)
| Function | Purpose | Status |
|----------|---------|--------|
| `build_learning_profile()` | Build learning profile from attempt history | Missing |
| `build_ai_coaching()` | Full fallback coaching builder | Missing |
| `_coaching_reason_for_question()` | Get coaching reason for question type | Missing |
| `_coaching_next_action()` | Get next action suggestion | Missing |

### Scoring (3)
| Function | Purpose | Status |
|----------|---------|--------|
| `turn_feedback_with_codex()` | Combined band7 + coaching generation | Missing |
| `ai_coaching_with_codex()` | AI coaching with full prompt | Simplified |
| `overall_review_with_codex()` | Overall review generation | Missing |

## Prompt Comparison

### Django `build_ai_coaching_with_codex` (simplified, ~10 lines)
```python
prompt = (
    "You are an IELTS Speaking coach. Compare the candidate's answer with the Band 7 version. "
    "Give 2-3 specific, actionable coaching points in Chinese. Focus on what to change and how. "
    "Be encouraging but direct. Use bullet points.\n\n"
    f"Question: {question}\n\n"
    f"Candidate answer:\n{transcript}\n\n"
    f"Band 7 version:\n{band7}\n\n"
    "Coaching (in Chinese, 2-3 bullet points):"
)
```

### Old Server `ai_coaching_with_codex` (full, ~50 lines)
- Part-specific hints (P1/P2/P3 different guidance)
- Grammar correction requirements (mandatory bullet)
- Learning profile integration
- Format validation constraints
- Detailed output format rules

## Requirements

### P0: Fix run_codex() prompt delivery
1. Add `-` argument to both JSON and non-JSON calls
2. Preserve `input=prompt`
3. Add error detection when `input_tokens=0` → raise error, don't silent fallback

### P1: Migrate missing helper functions
1. `clean_markdown_text()` - remove control chars, normalize whitespace
2. `clean_report_text()` - clean for display
3. `normalize_coaching_markdown()` - fix markdown formatting
4. `concise_coaching_markdown()` - validate coaching has grammar bullet
5. `ensure_grammar_correction_bullet()` - add grammar correction if missing
6. `infer_grammar_corrections()` - pattern-based grammar fixes
7. `spoken_markdown()` - paragraph formatting for spoken text
8. `model_answer_constraints()` - P1/P2/P3 specific constraints
9. `target_band_label()` - get target band from attempt metadata
10. `_transcript_usable_for_band7()` - relevance check
11. `build_learning_profile()` - aggregate user history
12. `build_ai_coaching()` - fallback coaching generator
13. `_coaching_reason_for_question()` - question-type advice
14. `_coaching_next_action()` - next practice suggestions
15. `turn_feedback_with_codex()` - combined band7 + coaching
16. `ai_coaching_with_codex()` - full coaching prompt

### P2: Update prompts to match old server
1. Part-specific hints in coaching prompt
2. Grammar correction requirements
3. Learning profile integration
4. Format validation

## Acceptance Criteria

- [ ] `run_codex()` delivers prompt to model (input_tokens > 0)
- [ ] Score attempt produces `ielts_score.backend == "codex"` or clear error
- [ ] Turn metadata has `band7_source == "codex"` or clear error
- [ ] Turn metadata has `ai_coaching_source == "codex"` or clear error
- [ ] No silent fallback without error indication
- [ ] All 16 helper functions migrated
- [ ] All Django tests pass
- [ ] Smoke tests pass

## Definition of Done

- Tests added for `run_codex()` with mock subprocess
- Tests for error detection when 0 tokens
- Full test suite passes
- Lint/typecheck clean
- Business commit, archive, journal

## Technical Approach

1. Fix `run_codex()` first (highest priority)
2. Migrate helper functions in groups:
   - Text processing functions
   - Coaching functions
   - Profile functions
3. Update prompts
4. Add tests

## Out of Scope

- Azure Speech integration
- Volcengine TTS integration
- Writing endpoints
- UI changes
