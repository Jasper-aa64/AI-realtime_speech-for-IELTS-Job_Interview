# Django-only Runtime Smoke Verification

## Goal

Verify that Django can serve as the sole runtime backend for the IELTS Speaking Simulator by running smoke tests on all main user flows. This task validates the migration is complete and identifies any remaining issues.

## Scope

### Main Flows to Test

1. **Authentication**
   - Register new user
   - Login existing user
   - Logout
   - Get current user info

2. **Speaking Practice**
   - Start attempt (p1, p2, p3, mock modes)
   - Upload audio to turn
   - Complete turn
   - Score attempt
   - View history list
   - View history detail
   - Delete history item

3. **Training**
   - Get weak items
   - Get replay queue

4. **Question Bank**
   - Get summary
   - Sample questions

5. **Billing**
   - View wallet
   - Recharge (mock)

6. **Writing**
   - Get summary
   - Get reports
   - Get prompts
   - Save entry
   - Score entry

### Verification Method

- Use Django test client to simulate API calls
- Or use curl/requests to hit running Django server
- No real Azure Speech, Codex, or Volcengine TTS calls
- All AI operations use fallback behavior

## Acceptance Criteria

* [x] Authentication flow works
* [x] Start attempt for all modes works
* [x] Audio upload and retrieval works
* [x] Turn complete works
* [x] Score attempt works
* [x] History list/detail/delete works
* [x] Training endpoints work
* [x] Question bank endpoints work
* [x] Billing endpoints work
* [x] Writing endpoints work
* [x] All 141 tests pass (including 7 new smoke tests)

## Definition of Done

* [x] All smoke tests pass
* [x] Tests added for coverage
* [x] Business commit made
* [x] Task archived

## Out of Scope

* Real Azure Speech integration
* Real Codex integration
* Real Volcengine TTS integration
* Delete old server
* Push to remote
