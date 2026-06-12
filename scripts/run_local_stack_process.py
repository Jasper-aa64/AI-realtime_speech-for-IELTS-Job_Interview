#!/usr/bin/env python3
"""Launch one local IELTS process with the same AI env as start-local-stack.

This wrapper is intentionally Python, not shell: macOS launchd can execute the
project venv Python reliably even when direct shell scripts under Desktop are
blocked by privacy controls. It does not print provider secrets.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_STOP_FILE = "/tmp/ielts-ai-worker.stop"
PREFERRED_CC_SWITCH_PROVIDERS = ("Aiapis2", "Aiapis", "Aiaps1")


def _load_aiapis_from_cc_switch() -> None:
    if os.environ.get("AI_HTTP_BASE_URL") and os.environ.get("AI_HTTP_API_KEY") and os.environ.get("AI_HTTP_MODEL"):
        return

    db_path = Path(os.environ.get("CC_SWITCH_DB") or Path.home() / ".cc-switch" / "cc-switch.db")
    if not db_path.exists():
        return

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "select name, settings_config from providers where app_type='codex'"
        ).fetchall()
    finally:
        conn.close()

    by_name = {name: raw for name, raw in rows}
    selected: tuple[str, str] | None = None
    for name in PREFERRED_CC_SWITCH_PROVIDERS:
        if name in by_name:
            selected = (name, by_name[name])
            break
    if selected is None:
        for name, raw in rows:
            if "aiapis" in name.lower() or "aiapis" in raw.lower():
                selected = (name, raw)
                break
    if selected is None:
        return

    _name, raw = selected
    config = json.loads(raw)
    api_key = str((config.get("auth") or {}).get("OPENAI_API_KEY") or "").strip()
    toml_text = str(config.get("config") or "")
    base_match = re.search(r'base_url\s*=\s*"([^"]+)"', toml_text)
    base_url = base_match.group(1).strip() if base_match else ""
    model = os.environ.get("AI_HTTP_PREFERRED_MODEL", "").strip() or "gpt-5.4-mini"
    if not (api_key and base_url):
        return

    os.environ.setdefault("AI_HTTP_BASE_URL", base_url)
    os.environ.setdefault("AI_HTTP_API_KEY", api_key)
    os.environ.setdefault("AI_HTTP_MODEL", model)


def _load_common_env() -> None:
    _load_aiapis_from_cc_switch()
    current_path = os.environ.get("PATH", "")
    extra_paths = ["/opt/homebrew/bin", "/usr/local/bin"]
    additions = [path for path in extra_paths if path not in current_path.split(":")]
    if additions:
        os.environ["PATH"] = ":".join(additions + ([current_path] if current_path else ["/usr/bin:/bin"]))
    os.environ.setdefault("AI_HTTP_TIMEOUT_SECONDS", "60")
    os.environ.setdefault("SPEAKING_AI_CALL_MODE", "chain")
    # Reuse the HTTP model loaded from aiapis; otherwise prefer the fast GPT mini route.
    os.environ.setdefault(
        "SPEAKING_AI_MODEL",
        os.environ.get("AI_HTTP_MODEL") or "gpt-5.4-mini",
    )
    if (ROOT_DIR / "config" / "default_config.json").exists():
        os.environ.setdefault("VOLCENGINE_ASR_ENABLED", "1")
    if Path("/opt/homebrew/bin/ffmpeg").exists():
        os.environ.setdefault("VOLCENGINE_ASR_FFMPEG", "/opt/homebrew/bin/ffmpeg")
    os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")


def _exec_manage(args: list[str]) -> None:
    manage_py = ROOT_DIR / "backend_django" / "manage.py"
    os.chdir(ROOT_DIR)
    os.execv(sys.executable, [sys.executable, str(manage_py), *args])


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in {"django", "worker"}:
        print("Usage: run_local_stack_process.py {django|worker}", file=sys.stderr)
        return 2

    _load_common_env()

    if argv[1] == "django":
        host = os.environ.get("IELTS_DJANGO_HOST", "127.0.0.1")
        port = os.environ.get("IELTS_DJANGO_PORT", "8767")
        _exec_manage(["runserver", f"{host}:{port}", "--noreload"])
    else:
        stop_file = os.environ.get("IELTS_AI_WORKER_STOP_FILE", DEFAULT_STOP_FILE)
        Path(stop_file).unlink(missing_ok=True)
        interval = os.environ.get("IELTS_AI_WORKER_INTERVAL_SECONDS", "2")
        idle_interval = os.environ.get("IELTS_AI_WORKER_IDLE_INTERVAL_SECONDS", "5")
        _exec_manage(
            [
                "run_ai_worker",
                "--interval-seconds",
                interval,
                "--idle-interval-seconds",
                idle_interval,
                "--stop-file",
                stop_file,
            ]
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
