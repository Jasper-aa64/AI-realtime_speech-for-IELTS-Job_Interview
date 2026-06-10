#!/usr/bin/env bash

load_aiapis_env_from_cc_switch() {
  if [[ -n "${AI_HTTP_BASE_URL:-}" && -n "${AI_HTTP_API_KEY:-}" && -n "${AI_HTTP_MODEL:-}" ]]; then
    return 0
  fi

  local root_dir="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
  local python_bin="${PYTHON:-}"
  if [[ -z "$python_bin" ]]; then
    if [[ -x "$root_dir/.venv-django/bin/python" ]]; then
      python_bin="$root_dir/.venv-django/bin/python"
    else
      python_bin="python3"
    fi
  fi

  local db="${CC_SWITCH_DB:-$HOME/.cc-switch/cc-switch.db}"
  [[ -f "$db" ]] || return 0

  "$python_bin" - "$db" <<'PY'
import json
import re
import sqlite3
import sys

db = sys.argv[1]
preferred = ("Aiapis2", "Aiapis", "Aiaps1")
conn = sqlite3.connect(db)
rows = conn.execute(
    "select name, settings_config from providers where app_type='codex'"
).fetchall()

by_name = {name: raw for name, raw in rows}
selected = None
for name in preferred:
    if name in by_name:
        selected = (name, by_name[name])
        break
if selected is None:
    for name, raw in rows:
        if "aiapis" in name.lower() or "aiapis" in raw.lower():
            selected = (name, raw)
            break
if selected is None:
    raise SystemExit(0)

_name, raw = selected
config = json.loads(raw)
api_key = (config.get("auth") or {}).get("OPENAI_API_KEY", "").strip()
toml_text = str(config.get("config") or "")
base_match = re.search(r'base_url\s*=\s*"([^"]+)"', toml_text)
model_match = re.search(r'model\s*=\s*"([^"]+)"', toml_text)
base_url = base_match.group(1).strip() if base_match else ""
model = (model_match.group(1).strip() if model_match else "") or "gpt-5.4-mini"

if not (api_key and base_url):
    raise SystemExit(0)

def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"

print(f"export AI_HTTP_BASE_URL={sh_quote(base_url)}")
print(f"export AI_HTTP_API_KEY={sh_quote(api_key)}")
print(f"export AI_HTTP_MODEL={sh_quote(model)}")
PY
}

load_local_stack_env() {
  local aiapis_exports
  aiapis_exports="$(load_aiapis_env_from_cc_switch || true)"
  if [[ -n "$aiapis_exports" ]]; then
    # shellcheck disable=SC1090
    eval "$aiapis_exports"
  fi

  export AI_HTTP_TIMEOUT_SECONDS="${AI_HTTP_TIMEOUT_SECONDS:-60}"
  export SPEAKING_AI_CALL_MODE="${SPEAKING_AI_CALL_MODE:-chain}"
  # If aiapis loaded a specific model, reuse it for speaking AI too.
  export SPEAKING_AI_MODEL="${SPEAKING_AI_MODEL:-${AI_HTTP_MODEL:-gpt-5.5}}"
  if [[ -f "${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}/config/default_config.json" ]]; then
    export VOLCENGINE_ASR_ENABLED="${VOLCENGINE_ASR_ENABLED:-1}"
  fi
  export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"
  if [[ -x /opt/homebrew/bin/ffmpeg ]]; then
    export VOLCENGINE_ASR_FFMPEG="${VOLCENGINE_ASR_FFMPEG:-/opt/homebrew/bin/ffmpeg}"
  fi
  export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-127.0.0.1,localhost}"
  export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
}
