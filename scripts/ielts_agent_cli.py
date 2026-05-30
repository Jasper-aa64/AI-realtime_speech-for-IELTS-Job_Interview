#!/usr/bin/env python
"""Agent-facing IELTS locator CLI.

This script intentionally exposes capabilities instead of pretending to be the
agent. It can work from a source checkout, from a copied question-bank bundle,
or against a running IELTS web service.

Examples:
  python scripts/ielts_agent_cli.py manifest
  python scripts/ielts_agent_cli.py bank.search --json '{"query":"computer internet children teachers","scope":"writing"}'
  python scripts/ielts_agent_cli.py bank.get --id cambridge-20-test-1-task-1
  python scripts/ielts_agent_cli.py web.search --query "剑雅20 Test 1 Task 1 line graph"
  python scripts/ielts_agent_cli.py web.fetch --url https://example.com/page
  python scripts/ielts_agent_cli.py report.url --kind writing --id entry-id
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from urllib import error, parse, request


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend_django"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from apps.writing.search_utils import expanded_search_terms, search_normalize

DEFAULT_BASE_URL = os.environ.get("IELTS_BASE_URL", "http://127.0.0.1:8082/").rstrip("/") + "/"
DEFAULT_BANK_DIR = Path(os.environ.get("IELTS_BANK_DIR", ROOT / "data" / "ielts")).expanduser()
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("IELTS_AGENT_TIMEOUT", "12"))
USER_AGENT = "IELTS-Agent-CLI/1.0 (+local study locator)"


def normalize_text(value: str | None) -> str:
    return search_normalize(value)


def score_text(query: str, candidate: str) -> float:
    query_norm = normalize_text(query)
    candidate_norm = normalize_text(candidate)
    query_tokens = set(query_norm.split())
    expanded_tokens = set(expanded_search_terms(query))
    candidate_tokens = set(candidate_norm.split())
    if not (query_tokens or expanded_tokens) or not candidate_tokens:
        return 0.0
    direct_overlap = len(query_tokens & candidate_tokens) / max(len(query_tokens), 1)
    expanded_overlap = len(expanded_tokens & candidate_tokens) / max(len(expanded_tokens), 1)
    sequence = SequenceMatcher(None, query_norm, candidate_norm[: max(240, len(query_norm) * 6)]).ratio()
    phrase_bonus = 0.08 if query_norm and query_norm[:80] in candidate_norm else 0.0
    return round(min(1.0, direct_overlap * 0.42 + expanded_overlap * 0.34 + sequence * 0.18 + phrase_bonus), 4)


def write_json(payload: dict | list, exit_code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


def read_json_arg(value: str | None) -> dict:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("JSON payload must be an object")
    return payload


def http_request_json(url: str, method: str = "GET", payload: dict | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=timeout) as response:
        body = response.read()
    return json.loads(body.decode("utf-8"))


def http_request_text(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> tuple[str, dict[str, str]]:
    req = request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5"})
    with request.urlopen(req, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        body = response.read(1_500_000)
    charset_match = re.search(r"charset=([^;\s]+)", content_type, re.I)
    charset = charset_match.group(1) if charset_match else "utf-8"
    try:
        text = body.decode(charset, errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    return text, {"content_type": content_type, "bytes": str(len(body))}


def strip_html(value: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def writing_prompt_url(prompt_id: str, task_type: str = "task2", base_url: str = DEFAULT_BASE_URL) -> str:
    return f"{base_url}?{parse.urlencode({'view': 'writing', 'task': task_type, 'prompt': prompt_id})}"


def report_url(report_id: str, kind: str, base_url: str = DEFAULT_BASE_URL) -> str:
    if kind == "speaking":
        return f"{base_url}?{parse.urlencode({'view': 'history', 'report': report_id})}"
    return f"{base_url}?{parse.urlencode({'view': 'writingReports', 'writing_report': report_id})}"


def iter_json_files(bank_dir: Path, scope: str = "all"):
    if not bank_dir.exists():
        return
    writing_dir = bank_dir / "writing"
    speaking_dir = bank_dir / "speaking"
    if scope in {"all", "writing"}:
        yield from writing_dir.rglob("*.json")
    if scope in {"all", "speaking"}:
        yield from speaking_dir.rglob("*.json")


def source_line(path: Path, needle: str) -> int | None:
    if not needle:
        return None
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if needle[:80] in line:
                return line_number
    except OSError:
        return None
    return None


def normalize_task_type(value: str | None, fallback: str = "") -> str:
    raw = str(value or fallback or "").strip().lower()
    if raw in {"task1", "task_1", "task1_academic"}:
        return "task1_academic"
    if raw in {"task2", "task_2"}:
        return "task2"
    return raw


def item_from_writing_prompt(path: Path, payload: dict, item: dict, index: int, root: Path) -> dict | None:
    prompt = str(item.get("prompt") or item.get("question") or "").strip()
    if not prompt:
        return None
    task_type = normalize_task_type(item.get("task_type"), payload.get("task_type") or path.stem)
    prompt_id = str(item.get("id") or item.get("prompt_id") or "").strip()
    title = str(item.get("title") or item.get("source_label") or "").strip()
    source_label = str(item.get("source_label") or title or "").strip()
    image = item.get("image") or item.get("image_url") or item.get("chart_image") or ""
    return {
        "kind": "writing_prompt",
        "id": prompt_id,
        "task_type": task_type,
        "title": title,
        "category": item.get("category") or "",
        "prompt": prompt,
        "source": item.get("source") or payload.get("source") or "",
        "source_label": source_label,
        "source_book": item.get("source_book") or payload.get("book"),
        "source_test": item.get("source_test") or payload.get("test"),
        "image": image,
        "url": writing_prompt_url(prompt_id, task_type) if prompt_id else "",
        "evidence": {
            "file": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
            "line": source_line(path, prompt),
            "index": index,
        },
    }


def iter_bank_items(bank_dir: Path, scope: str = "all"):
    for path in iter_json_files(bank_dir, scope) or []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        root = bank_dir.parent if bank_dir.name == "ielts" else bank_dir
        if scope in {"all", "writing"} and "writing" in path.parts:
            items = payload.get("prompts") if isinstance(payload, dict) else payload
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                if isinstance(item, dict):
                    result = item_from_writing_prompt(path, payload if isinstance(payload, dict) else {}, item, index, root)
                    if result:
                        yield result
        elif scope in {"all", "speaking"}:
            items = payload if isinstance(payload, list) else payload.get("items") or payload.get("questions") or payload.get("topics") or []
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                text = str(item.get("question") or item.get("title") or item.get("topic") or "").strip()
                if not text:
                    continue
                yield {
                    "kind": "speaking_item",
                    "id": str(item.get("id") or item.get("topic_id") or "").strip(),
                    "part": item.get("part") or payload.get("part") if isinstance(payload, dict) else "",
                    "title": item.get("title") or item.get("topic") or "",
                    "question": text,
                    "source": item.get("source") or payload.get("source") if isinstance(payload, dict) else "",
                    "evidence": {
                        "file": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
                        "line": source_line(path, text),
                        "index": index,
                    },
                }


def local_bank_search(query: str, bank_dir: Path, scope: str, task: str | None, limit: int) -> list[dict]:
    matches = []
    for item in iter_bank_items(bank_dir, scope):
        if task and normalize_task_type(item.get("task_type")) != normalize_task_type(task):
            continue
        candidate = " ".join(
            str(item.get(key) or "")
            for key in ("id", "title", "source_label", "category", "prompt", "question", "source_book", "source_test")
        )
        score = score_text(query, candidate)
        if score <= 0:
            continue
        result = dict(item)
        result["score"] = score
        matches.append(result)
    matches.sort(key=lambda item: item["score"], reverse=True)
    return matches[:limit]


def local_bank_get(item_id: str, bank_dir: Path, scope: str) -> dict | None:
    for item in iter_bank_items(bank_dir, scope):
        if str(item.get("id") or "") == item_id:
            return item
    return None


def remote_bank_search(query: str, base_url: str, task: str | None, limit: int, timeout: float) -> dict | None:
    params = {"q": query, "limit": str(limit)}
    if task:
        params["task_type"] = normalize_task_type(task)
    url = f"{base_url.rstrip('/')}/api/agent/writing/prompts/search?{parse.urlencode(params)}"
    try:
        return http_request_json(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - CLI should expose failure as data
        return {"error": str(exc), "url": url}


def cmd_manifest(args: argparse.Namespace) -> int:
    return write_json(
        {
            "name": "ielts-agent-cli",
            "purpose": "Expose IELTS bank/report/web lookup capabilities to an external agent.",
            "base_url": args.base_url,
            "bank_dir": str(args.bank_dir),
            "commands": [
                "bank.search",
                "bank.get",
                "bank.list",
                "api.get",
                "web.search",
                "web.fetch",
                "report.url",
                "url-writing-prompt",
                "url-speaking-report",
                "url-writing-report",
            ],
            "json_io": True,
            "agent_policy": "The CLI returns materials and evidence; the agent decides how to reason, verify, and import.",
        }
    )


def cmd_bank_search(args: argparse.Namespace) -> int:
    payload = read_json_arg(args.json_payload)
    query = str(payload.get("query") or args.query or "").strip()
    if not query:
        return write_json({"error": "query required"}, 2)
    scope = str(payload.get("scope") or args.scope or "writing")
    task = payload.get("task") or payload.get("task_type") or args.task
    limit = int(payload.get("limit") or args.limit)
    sources = set(payload.get("sources") or args.sources.split(","))
    result: dict[str, object] = {
        "query": query,
        "scope": scope,
        "task": normalize_task_type(task) if task else "",
        "sources": sorted(sources),
        "items": [],
        "remote": None,
    }
    items: list[dict] = []
    if "local" in sources:
        items.extend(local_bank_search(query, args.bank_dir, scope, task, limit))
    if "remote" in sources:
        remote = remote_bank_search(query, args.base_url, task, limit, args.timeout)
        result["remote"] = remote
        if isinstance(remote, dict) and isinstance(remote.get("items"), list):
            for item in remote["items"]:
                merged = dict(item)
                merged["kind"] = merged.get("kind") or "writing_prompt"
                merged["score"] = merged.get("match_score", merged.get("score", 0))
                merged["source_channel"] = "remote_api"
                items.append(merged)
    items.sort(key=lambda item: float(item.get("score") or item.get("match_score") or 0), reverse=True)
    result["items"] = items[:limit]
    result["count"] = len(result["items"])
    return write_json(result, 0 if items else 1)


def cmd_bank_get(args: argparse.Namespace) -> int:
    item = local_bank_get(args.id, args.bank_dir, args.scope)
    if item:
        return write_json({"id": args.id, "found": True, "item": item})
    return write_json({"id": args.id, "found": False, "message": "not found in local bank; try bank.search with --sources remote,local"}, 1)


def cmd_bank_list(args: argparse.Namespace) -> int:
    items = []
    for item in iter_bank_items(args.bank_dir, args.scope):
        if args.task and normalize_task_type(item.get("task_type")) != normalize_task_type(args.task):
            continue
        if args.source and args.source.lower() not in " ".join(str(item.get(key) or "").lower() for key in ("source", "source_label", "source_book", "id")):
            continue
        items.append(item)
        if len(items) >= args.limit:
            break
    return write_json({"count": len(items), "items": items})


def cmd_api_get(args: argparse.Namespace) -> int:
    path = args.path.strip()
    if not path.startswith("/"):
        path = "/" + path
    url = parse.urljoin(args.base_url, path.lstrip("/"))
    if args.query:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{args.query.lstrip('?')}"
    try:
        payload = http_request_json(url, timeout=args.timeout)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"body": body[:4000]}
        return write_json({"url": url, "status": exc.code, "error": parsed}, 1)
    except Exception as exc:  # noqa: BLE001
        return write_json({"url": url, "error": str(exc)}, 1)
    return write_json({"url": url, "status": 200, "payload": payload})


def cmd_web_search(args: argparse.Namespace) -> int:
    query = args.query
    if args.site:
        query = f"site:{args.site} {query}"
    encoded = parse.urlencode({"q": query})
    engines = {
        "duckduckgo_html": f"https://duckduckgo.com/html/?{encoded}",
        "bing": f"https://www.bing.com/search?{encoded}",
    }
    engine = engines.get(args.engine, engines["duckduckgo_html"])
    try:
        text, meta = http_request_text(engine, args.timeout)
        plain = strip_html(text)
        snippets = []
        for part in re.split(r"(?i)(?:result__title|b_algo)", text)[1: args.limit + 1]:
            snippets.append(strip_html(part)[:700])
        if not snippets:
            snippets = [plain[:1200]]
        return write_json({"query": query, "engine": args.engine, "url": engine, "meta": meta, "snippets": snippets[: args.limit]})
    except Exception as exc:  # noqa: BLE001
        return write_json({"query": query, "engine": args.engine, "url": engine, "error": str(exc)}, 1)


def cmd_web_fetch(args: argparse.Namespace) -> int:
    try:
        text, meta = http_request_text(args.url, args.timeout)
    except Exception as exc:  # noqa: BLE001
        return write_json({"url": args.url, "error": str(exc)}, 1)
    plain = strip_html(text)
    return write_json(
        {
            "url": args.url,
            "meta": meta,
            "title": (re.search(r"(?is)<title[^>]*>(.*?)</title>", text).group(1).strip() if re.search(r"(?is)<title[^>]*>(.*?)</title>", text) else ""),
            "text": plain[: args.max_chars],
        }
    )


def cmd_report_url(args: argparse.Namespace) -> int:
    return write_json({"kind": args.kind, "id": args.id, "url": report_url(args.id, args.kind, args.base_url)})


def cmd_legacy_find_writing(args: argparse.Namespace) -> int:
    args.scope = "writing"
    args.sources = "local,remote"
    args.json_payload = json.dumps({"query": args.query, "task": args.task, "limit": args.limit, "scope": "writing"})
    return cmd_bank_search(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent CLI for IELTS bank, report, and web lookup.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="IELTS website/API base URL.")
    parser.add_argument("--bank-dir", type=Path, default=DEFAULT_BANK_DIR, help="Local IELTS bank directory, default data/ielts or IELTS_BANK_DIR.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("manifest", help="Describe available agent capabilities.").set_defaults(func=cmd_manifest)

    bank_search = subparsers.add_parser("bank.search", help="Search local/remote IELTS bank and return evidence JSON.")
    bank_search.add_argument("query", nargs="?", default="")
    bank_search.add_argument("--json", dest="json_payload", default="", help="JSON payload; keys: query, scope, task, limit, sources.")
    bank_search.add_argument("--scope", choices=["all", "writing", "speaking"], default="writing")
    bank_search.add_argument("--task", choices=["task1_academic", "task2"], default=None)
    bank_search.add_argument("--sources", default="local,remote", help="Comma list: local,remote.")
    bank_search.add_argument("--limit", type=int, default=8)
    bank_search.set_defaults(func=cmd_bank_search)

    bank_get = subparsers.add_parser("bank.get", help="Get one local bank item by id.")
    bank_get.add_argument("--id", required=True)
    bank_get.add_argument("--scope", choices=["all", "writing", "speaking"], default="all")
    bank_get.set_defaults(func=cmd_bank_get)

    bank_list = subparsers.add_parser("bank.list", help="List local bank items with optional source/task filters.")
    bank_list.add_argument("--scope", choices=["all", "writing", "speaking"], default="writing")
    bank_list.add_argument("--task", choices=["task1_academic", "task2"], default=None)
    bank_list.add_argument("--source", default="")
    bank_list.add_argument("--limit", type=int, default=20)
    bank_list.set_defaults(func=cmd_bank_list)

    api_get = subparsers.add_parser("api.get", help="Read a JSON API path from the configured IELTS service.")
    api_get.add_argument("--path", required=True, help="API path, for example /api/writing/prompts")
    api_get.add_argument("--query", default="", help="Raw query string without leading ?, optional.")
    api_get.set_defaults(func=cmd_api_get)

    web_search = subparsers.add_parser("web.search", help="Open-ended web search helper; returns snippets for agent judgment.")
    web_search.add_argument("--query", required=True)
    web_search.add_argument("--site", default="")
    web_search.add_argument("--engine", choices=["duckduckgo_html", "bing"], default="duckduckgo_html")
    web_search.add_argument("--limit", type=int, default=5)
    web_search.set_defaults(func=cmd_web_search)

    web_fetch = subparsers.add_parser("web.fetch", help="Fetch a URL and return extracted text.")
    web_fetch.add_argument("--url", required=True)
    web_fetch.add_argument("--max-chars", type=int, default=12000)
    web_fetch.set_defaults(func=cmd_web_fetch)

    report = subparsers.add_parser("report.url", help="Build a report deep link.")
    report.add_argument("--kind", choices=["speaking", "writing"], required=True)
    report.add_argument("--id", required=True)
    report.set_defaults(func=cmd_report_url)

    legacy_find = subparsers.add_parser("find-writing", help="Compat alias for bank.search --scope writing.")
    legacy_find.add_argument("query")
    legacy_find.add_argument("--task", choices=["task1_academic", "task2"], default=None)
    legacy_find.add_argument("--limit", type=int, default=5)
    legacy_find.add_argument("--open", action="store_true")
    legacy_find.set_defaults(func=cmd_legacy_find_writing)

    prompt_url = subparsers.add_parser("url-writing-prompt", help="Build a writing prompt deep link.")
    prompt_url.add_argument("prompt_id")
    prompt_url.add_argument("--task", choices=["task1_academic", "task2"], default="task2")
    prompt_url.set_defaults(func=lambda args: write_json({"url": writing_prompt_url(args.prompt_id, args.task, args.base_url)}))

    speaking_url = subparsers.add_parser("url-speaking-report", help="Build a speaking report deep link.")
    speaking_url.add_argument("report_id")
    speaking_url.set_defaults(func=lambda args: write_json({"url": report_url(args.report_id, "speaking", args.base_url)}))

    writing_url = subparsers.add_parser("url-writing-report", help="Build a writing report deep link.")
    writing_url.add_argument("entry_id")
    writing_url.set_defaults(func=lambda args: write_json({"url": report_url(args.entry_id, "writing", args.base_url)}))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.bank_dir = Path(args.bank_dir).expanduser()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
