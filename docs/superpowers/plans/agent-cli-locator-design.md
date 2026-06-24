# IELTS Agent Locator CLI Design

## Purpose

This document records the current direction for the agent-facing IELTS locator CLI so the work is not lost in chat history.

The CLI is **not** intended to be a keyword-only search tool. The agent is already capable of reasoning, query rewriting, source comparison, and ambiguity handling. The CLI should expose stable capabilities and evidence, then let the agent decide how to locate, verify, or report a missing IELTS prompt/report.

## Product Goal

An agent running on a machine without the project source code should still be able to help the user locate a prompt or report when the user gives an incomplete or fuzzy description.

Example user input:

> the Task 2 question about computers and the Internet being more important for children than schools and teachers

The agent should be able to:

- Query the local bank if a copied bank bundle exists.
- Query a running IELTS web service through a base URL.
- Fetch JSON APIs from the service when useful.
- Search the web when the local/remote bank does not contain the prompt.
- Fetch candidate web pages for its own reasoning.
- Build deep links to prompts and reports.
- Return evidence and confidence instead of pretending a weak match is certain.

## Current Implementation

Main script:

- `scripts/ielts_agent_cli.py`

Current state:

- New file / untracked at the time this document was written.
- Designed as a JSON-capable agent toolbox.
- Can run from a source checkout.
- Can run against a copied bank directory via `IELTS_BANK_DIR`.
- Can run against a public or local website via `IELTS_BASE_URL`.

## Implemented Commands

### `manifest`

Describes the CLI capabilities for an agent.

```bash
python scripts/ielts_agent_cli.py manifest
```

### `bank.search`

Searches local bank data and/or the remote service API. This is still useful, but it is just one tool. The agent decides whether the results are good enough.

```bash
python scripts/ielts_agent_cli.py bank.search "computer internet children education teachers schools" --scope writing --task task2 --sources local --limit 3
```

JSON payload form:

```bash
python scripts/ielts_agent_cli.py bank.search --json "{\"query\":\"computer internet children teachers\",\"scope\":\"writing\",\"task\":\"task2\",\"sources\":[\"local\",\"remote\"],\"limit\":5}"
```

Output includes:

- `items[]`
- `id`
- `prompt`
- `source_label`
- `url`
- `evidence.file`
- `evidence.line`
- `score`

Verified example:

- Query: `computer internet children education teachers schools`
- Best local match: `reported-cn-task2-2015-05-30-20`
- Prompt: `Some people think computers and the Internet are more important in child's education...`

### `bank.get`

Gets one local bank item by ID.

```bash
python scripts/ielts_agent_cli.py bank.get --id cambridge-20-test-1-task-1
```

Verified result:

- `cambridge-20-test-1-task-1`
- `剑雅20-1 Task 1`
- image path: `/assets/writing/task1/cambridge/20/test_1_task_1.png`

### `bank.list`

Lists local bank items with optional filters.

```bash
python scripts/ielts_agent_cli.py bank.list --scope writing --task task1_academic --source cambridge --limit 3
```

### `api.get`

Reads JSON from a running IELTS service. This is important for machines without source code.

```bash
python scripts/ielts_agent_cli.py --base-url https://example.trycloudflare.com/ api.get --path /api/question-bank/summary
```

Verified locally:

```bash
python scripts/ielts_agent_cli.py api.get --path /api/question-bank/summary
```

returned the speaking question-bank summary from `http://127.0.0.1:8082/`.

### `web.search`

Performs an open-ended web search helper and returns snippets for the agent to judge.

```bash
python scripts/ielts_agent_cli.py web.search --query "剑雅20 Test 1 Task 1 line graph"
```

The CLI does not decide truth here. It exposes snippets; the agent must inspect and compare.

### `web.fetch`

Fetches a candidate URL and returns extracted page text.

```bash
python scripts/ielts_agent_cli.py web.fetch --url https://example.com/page
```

### `report.url`

Builds report deep links.

```bash
python scripts/ielts_agent_cli.py report.url --kind writing --id demo-entry
python scripts/ielts_agent_cli.py report.url --kind speaking --id attempt-id
```

### Legacy Compatibility Commands

These remain as aliases for older workflows:

- `find-writing`
- `url-writing-prompt`
- `url-speaking-report`
- `url-writing-report`

## Environment Variables

### `IELTS_BASE_URL`

Base URL for the running service.

```bash
set IELTS_BASE_URL=https://your-public-url/
python scripts/ielts_agent_cli.py api.get --path /api/question-bank/summary
```

### `IELTS_BANK_DIR`

Path to a copied IELTS bank bundle. This enables no-source machines to search a local exported bank.

```bash
set IELTS_BANK_DIR=C:\ielts-bank
python scripts/ielts_agent_cli.py bank.search "New York population table" --scope writing
```

### `IELTS_AGENT_TIMEOUT`

Network timeout in seconds.

## Design Principle

Wrong direction:

> Build a CLI that only keyword-searches and returns one "best" result.

Correct direction:

> Expose permissions and raw capabilities. Let the agent search, fetch, compare, reason, and report uncertainty.

The CLI should return evidence, not overconfident conclusions.

## No-Source Machine Strategy

There are two supported no-source modes:

1. Remote API mode:
   - Agent only needs the CLI and `IELTS_BASE_URL`.
   - Uses `api.get`, remote `bank.search`, and deep-link builders.

2. Copied bank bundle mode:
   - Agent needs the CLI plus an exported/copyable IELTS bank directory.
   - Uses `IELTS_BANK_DIR` and local `bank.search`, `bank.get`, `bank.list`.

These can be combined: remote service first, copied bank as fallback, then web search.

## Remaining Work

- Package the script so it can be installed without source checkout.
- Add an explicit bank export command or document the bank bundle format.
- Add remote `bank.get` if the service exposes a stable prompt-detail API.
- Add authenticated API support if report lookup needs user session cookies.
- Add tests for:
  - `bank.search`
  - `bank.get`
  - `api.get`
  - malformed JSON payloads
  - unavailable remote API
- Decide whether web search should stay in the CLI or be delegated to the agent runtime when the runtime already has a browser/search tool.

## Verification Already Run

```bash
python -m py_compile scripts\ielts_agent_cli.py
python scripts\ielts_agent_cli.py manifest
python scripts\ielts_agent_cli.py bank.search "computer internet children education teachers schools" --scope writing --task task2 --sources local --limit 3
python scripts\ielts_agent_cli.py bank.get --id cambridge-20-test-1-task-1
python scripts\ielts_agent_cli.py api.get --path /api/question-bank/summary
python scripts\ielts_agent_cli.py report.url --kind writing --id demo-entry
git diff --check -- scripts\ielts_agent_cli.py
```

