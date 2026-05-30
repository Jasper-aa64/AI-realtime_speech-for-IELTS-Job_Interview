# Writing App Architecture

`apps.writing.services` remains the compatibility facade used by views, tests,
and AI task callbacks. New production code should avoid adding unrelated logic
to that file.

Current split:

- `validation.py`: task type normalization, paragraph validation, word count,
  and writing-specific service exceptions.
- `search_utils.py`: text normalization, query expansion, and reusable search
  token helpers.
- `prompt_services.py`: prompt seed synchronization, Cambridge catalog
  metadata, prompt payloads, random selection, and agent prompt search.
- `services.py`: persistence orchestration, reports, score task lifecycle, and
  compatibility exports for existing callers.

Refactor rule: move pure helpers and cohesive subdomains out of `services.py`,
then re-export names from `services.py` only when an existing caller depends on
that import path.
