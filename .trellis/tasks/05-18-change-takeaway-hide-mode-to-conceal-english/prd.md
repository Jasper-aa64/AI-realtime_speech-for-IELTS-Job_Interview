# Change Takeaway Hide Mode To Conceal English

## Goal

Change the Language Takeaway review mode so self-test hides the English source text instead of hiding the Chinese translation.

## Scope

- Rename UI copy from hiding Chinese to hiding English.
- In hidden mode, keep Chinese visible.
- Conceal the English source while preserving card size.
- Clicking a concealed card reveals English and plays TTS.
- Bump static asset version.

## Acceptance Criteria

- [x] Default mode still shows English and Chinese.
- [x] Toggle copy says hiding/showing English.
- [x] Hidden mode conceals English, not Chinese.
- [x] Chinese stays visible in hidden mode.
- [x] Clicking a card reveals English and plays TTS.
- [x] Card dimensions remain stable between concealed/revealed states.
- [x] JS syntax check passes.
