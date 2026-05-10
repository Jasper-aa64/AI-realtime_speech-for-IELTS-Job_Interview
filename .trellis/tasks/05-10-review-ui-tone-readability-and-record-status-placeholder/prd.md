# Review UI tone readability and record status placeholder

## Goal

Review the latest IELTS Web UI tone/text cleanup for two concrete issues and fix them directly if found:

- Mock tone readability on the black sidebar.
- Garbled initial record-status placeholder under the big recording button.

## Scope

- Primary files: `web/static/styles.css`, `web/static/app.js`.
- Verification requested by user:
  - `node --check web/static/app.js`
  - `python -m py_compile web/ielts_server.py`

## Acceptance Criteria

- Mock navigation/status remains visually dark enough while text is legible on the black sidebar.
- Initial record-status placeholder renders as readable text, not garbled/mojibake.
- Requested syntax checks pass.
