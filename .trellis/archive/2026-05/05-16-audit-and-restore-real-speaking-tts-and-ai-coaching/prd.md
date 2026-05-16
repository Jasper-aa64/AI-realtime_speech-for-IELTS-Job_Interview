# PRD: Audit and Restore Real Speaking TTS and AI Coaching

## Status
Implementation Complete - Testing

## Background
The first TTS migration (commit 529cb0a) successfully restored volcengine_tts and ensure_examiner_tts, but a comprehensive audit reveals that **all AI coaching functionality** in the speaking module is still using fallback templates instead of real AI generation.

The old server (`web/ielts_server.py`) has a complete AI pipeline using the Codex CLI for:
- Turn-by-turn feedback generation
- Band 7 model answers
- AI coaching suggestions
- Upgrade notes
- Personalized coaching
- Overall review generation
- Feedback regeneration

Django currently **pretends** these features work by returning fixed templates, which violates the user's requirement: "不要再用固定模板伪装真实 AI" (don't use fixed templates to fake real AI).

## Audit Findings

### 1. TTS Status ✅
**COMPLETE** - First migration successfully restored:
- `volcengine_tts()` - generates TTS audio via VolcEngine API
- `ensure_examiner_tts()` - ensures examiner audio exists for each turn
- Audio caching in `media/tts/examiner/`
- Integration in `start_attempt()` to generate TTS for all turns upfront

### 2. Turn Feedback Generation ❌
**MISSING** - Old server has real AI, Django uses fallback

**Old Server** (`web/ielts_server.py`):
- `turn_feedback_with_codex()` (line 3241-3295): Calls Codex CLI to generate feedback
- `build_turn_feedback()` (line 3297-3340): Orchestrates feedback generation with allow_codex flag
- `build_turn_band7()` (line 3343-3400): Generates Band 7 model answer via Codex
- `build_turn_band7_fallback()` (line 3402-3440): Fallback when Codex unavailable
- Validation: `valid_turn_band7()`, `plausible_spoken_answer()`, `band7_addresses_question()`

**Django** (`backend_django/apps/speaking/services.py`):
- `_band7_fallback()` (line 1157): Returns fixed template "Try to answer: {question}. Add one reason and one example."
- `score_attempt()` (line 1026-1029): Uses `_band7_fallback()` for all turns
- No real AI generation

**Gap**: Django needs to call Codex CLI to generate real turn feedback and band7 versions.

### 3. AI Coaching ❌
**MISSING** - Old server has real AI, Django uses fixed text

**Old Server**:
- `ai_coaching_with_codex()` (line 3751-3850): Calls Codex to generate personalized coaching
- `build_ai_coaching()` (line 3842+): Orchestrates coaching generation with allow_codex flag
- `build_personalized_coaching()` (line 3852-3900): Generates learning profile-based coaching
- `build_upgrade_notes()` (line 3900-3910): Extracts upgrade notes from transcript

**Django**:
- Line 1029: Fixed text "先把答案说完整，再补一个具体例子；这是当前 fallback 报告的练习重点。"
- Line 1028: Fixed array `["Give a direct answer, add a reason, then add one concrete example."]`
- No real AI generation

**Gap**: Django needs to call Codex CLI to generate real AI coaching.

### 4. Scoring ❌
**MISSING** - Old server uses Codex, Django uses heuristic fallback

**Old Server**:
- `score_with_codex()` (line 2983-3022): Calls Codex CLI with scorer_system.md prompt
- `handle_attempt_score()` (line 4519-4546): Tries Codex first, falls back to heuristic on error
- Returns structured score with feedback, overall_review, billing_usage

**Django**:
- `_fallback_score()` (line 1160-1180): Pure heuristic based on word count and length
- No Codex integration
- Always returns fallback

**Gap**: Django needs to try Codex first, fallback to heuristic only on error.

### 5. Feedback Regeneration ❌
**MISSING** - Old server has real implementation, Django returns "not yet implemented"

**Old Server**:
- `handle_turn_feedback_regenerate()` (line 4548-4558): Calls `build_turn_feedback()` with allow_codex=True
- Updates turn metadata and saves

**Django**:
- `regenerate_turn_feedback()` (line 1141-1165): Returns `{"message": "Feedback regeneration is not yet implemented in Django runtime."}`
- No real implementation

**Gap**: Django needs to implement real regeneration by calling Codex.

### 6. Overall Review and Personalized Coaching ❌
**MISSING** - Old server generates via AI, Django uses fixed templates

**Old Server**:
- `build_detailed_report()` (line 3950-3996): Generates complete report with:
  - `build_learning_profile()` - analyzes user's learning patterns
  - `build_personalized_coaching()` - generates coaching based on profile
  - `build_overall_review()` - generates overall review via Codex
  - `build_upgrade_notes()` - extracts specific upgrade suggestions
- All integrated into scoring flow

**Django**:
- Line 1060-1068: Fixed templates:
  - `overall_review.comment`: "Fallback report generated locally..."
  - `overall_review.review_points`: Fixed array
  - `personalized_coaching.focus`: Fixed Chinese text
  - `personalized_coaching.next_practice`: Fixed array
- No real AI generation

**Gap**: Django needs to generate real overall review and personalized coaching.

## Technical Assessment

### Available Resources ✅
1. **Codex CLI**: Available at `/opt/homebrew/bin/codex`
2. **Django Settings**: `AI_PROVIDER_ENABLE_CODEX = True` (default)
3. **API Key**: Configured via `CODEX_API_KEY` environment variable
4. **Prompts**: Old server uses `data/prompts/scorer_system.md` and inline prompts
5. **Billing**: Old server has BillingStore for usage tracking

### Migration Strategy
The old server's `run_codex()` function (line 2426-2449) is a simple subprocess wrapper:
```python
def run_codex(prompt: str, call_id: str, billing: BillingStore | None = None):
    codex = shutil.which("codex") or "/opt/homebrew/bin/codex"
    config_args = ["-c", f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"']
    result = subprocess.run(
        [codex, "exec", "--json", *config_args],
        input=prompt, text=True, capture_output=True,
        timeout=45, check=True
    )
    output, usage = extract_codex_json_events(result.stdout, raw_path)
    if billing:
        billing.settle_usage(DEFAULT_USER_ID, call_id, usage)
    return output, usage
```

**Django can use the same approach**: Call codex CLI via subprocess, parse JSON output, track usage.

### What NOT to Migrate
1. **BillingStore**: Django doesn't have this yet, can skip usage tracking for now
2. **Learning Profile**: Complex feature, can use simplified version or skip
3. **Pronunciation**: Already handled separately, not part of this task

## Implementation Plan

### Phase 1: Core Codex Integration
1. Add `run_codex()` helper to `backend_django/apps/speaking/services.py`
2. Add `extract_codex_json_events()` and `extract_json_object()` helpers
3. Add environment variable check for `IELTS_WEB_DISABLE_CODEX`

### Phase 2: Scoring
1. Add `score_with_codex()` function
2. Update `score_attempt()` to try Codex first, fallback to heuristic on error
3. Copy `data/prompts/scorer_system.md` if needed, or use inline prompt
4. Add `calibrate_realistic_score()` and `cap_off_topic_score()` helpers

### Phase 3: Turn Feedback
1. Add `turn_feedback_with_codex()` function
2. Add `build_turn_band7()` function with Codex integration
3. Add validation helpers: `valid_turn_band7()`, `plausible_spoken_answer()`, `band7_addresses_question()`
4. Update `score_attempt()` to generate real turn feedback for each turn

### Phase 4: AI Coaching
1. Add `ai_coaching_with_codex()` function
2. Add `build_upgrade_notes()` function
3. Update `score_attempt()` to generate real AI coaching
4. Replace fixed templates with real AI results

### Phase 5: Regeneration
1. Implement `regenerate_turn_feedback()` with real Codex calls
2. Add status tracking (generating, success, error)
3. Update turn metadata with regenerated feedback

### Phase 6: Overall Review (Optional)
1. Add `build_overall_review()` function with Codex integration
2. Add simplified `build_personalized_coaching()` (without full learning profile)
3. Integrate into `score_attempt()`

## Acceptance Criteria

### Must Have
- [x] `run_codex()` helper function works and calls codex CLI
- [x] `score_attempt()` tries Codex scoring first, falls back to heuristic on error
- [x] Each turn gets real Band 7 version via `build_turn_band7_with_codex()` with Codex
- [x] Each turn gets real AI coaching via `build_ai_coaching_with_codex()`
- [x] Each turn gets real upgrade notes via `build_upgrade_notes()`
- [x] `regenerate_turn_feedback()` actually regenerates feedback via Codex
- [x] All fixed templates removed from `score_attempt()` (now only used as fallback)
- [x] Status fields clearly indicate "codex" vs "fallback" source (band7_source, ai_coaching_source)

### Should Have
- [x] Overall review generated via Codex (uses overall_review from score_with_codex)
- [x] Personalized coaching generated (simplified version kept for now)
- [x] Validation functions prevent bad Band 7 outputs (valid_turn_band7, plausible_spoken_answer, etc.)

### Nice to Have
- [ ] Usage tracking (skipped - no billing system in Django yet)
- [ ] Full learning profile integration (skipped - complex feature)
- [ ] Prompt caching for repeated calls (not needed yet)

## Testing Strategy
1. **Unit Tests**: Test each Codex function with mock subprocess
2. **Integration Tests**: Test full scoring flow with real Codex CLI
3. **Fallback Tests**: Test that heuristic fallback works when Codex disabled
4. **Validation Tests**: Test Band 7 validation logic
5. **Manual Tests**: Run full speaking attempt and verify real AI in report

## Risks and Mitigations
1. **Risk**: Codex CLI might fail or timeout
   - **Mitigation**: Always have heuristic fallback, catch exceptions
2. **Risk**: Codex might return invalid JSON
   - **Mitigation**: Parse with try/except, fallback on parse error
3. **Risk**: Codex might generate off-topic Band 7 answers
   - **Mitigation**: Use validation functions from old server
4. **Risk**: Migration might break existing tests
   - **Mitigation**: Update tests to mock Codex calls

## Success Metrics
- All speaking tests pass (currently 61/61)
- Full test suite passes (currently 147/147)
- Manual test shows real AI feedback in report (not fixed templates)
- Regenerate feedback actually changes the feedback content
- Status fields clearly show "codex" when real AI used, "fallback" when not

## Out of Scope
- Writing module AI (separate system, already has provider adapters)
- Pronunciation scoring (separate feature)
- BillingStore integration (no billing system in Django yet)
- Full learning profile system (complex, can simplify)
- Frontend changes (backend-only task)
