# Language Takeaway Enter to Retranslate

## Goal

Improve the Language Takeaway popup editing flow so pressing Enter in the source text box immediately re-translates the edited phrase instead of inserting a newline.

## Requirements

- Pressing `Enter` in the original/source textarea re-runs translation using the current source text.
- Pressing `Shift+Enter` still inserts a newline for users who intentionally need multiline text.
- Translation status should update visibly while the request is running and after completion/failure.
- Existing popup open, edit Chinese, save to vocabulary, and click-outside close behavior should remain unchanged.

## Acceptance Criteria

- [x] `Enter` in `#languageTakeawaySource` prevents the default newline.
- [x] `Enter` calls `/api/language-takeaways/translate` with the current edited source text.
- [x] Chinese field updates with the returned translation.
- [x] `Shift+Enter` keeps normal textarea newline behavior.
- [x] JS syntax check passes.

## Technical Notes

- Main file: `web/static/app.js`.
- Existing translation logic is currently inline in `openLanguageTakeawayPopup`; extract or reuse it so manual retranslation and initial popup translation share behavior.
