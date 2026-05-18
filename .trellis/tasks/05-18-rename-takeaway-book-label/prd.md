# Rename Takeaway Book Label

## Goal

Rename the learner-facing "生词本" label to "Takeaway" because the feature stores reusable language takeaways, not only vocabulary.

## Scope

- Update visible navigation/card/page/popup copy.
- Update auth/loading text that references the feature.
- Keep route/state/API names unchanged.
- Bump static asset version.

## Acceptance Criteria

- [x] Sidebar uses "Takeaway".
- [x] Corpus card uses "Takeaway".
- [x] Takeaway page heading and aria label use "Takeaway".
- [x] Popup save button no longer says "加入生词本".
- [x] User-facing auth/loading copy no longer says "生词本".
- [x] JS syntax check passes.
