#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DJANGO_HOST="${IELTS_DJANGO_HOST:-127.0.0.1}"
DJANGO_PORT="${IELTS_DJANGO_PORT:-8767}"
STOP_FILE="${IELTS_AI_WORKER_STOP_FILE:-/tmp/ielts-ai-worker.stop}"
RUNLOG_DIR="$ROOT_DIR/.runlogs"
mkdir -p "$RUNLOG_DIR"

if [[ -x "$ROOT_DIR/.venv-django/bin/python" ]]; then
  PYTHON="$ROOT_DIR/.venv-django/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

load_aiapis_env_from_cc_switch() {
  if [[ -n "${AI_HTTP_BASE_URL:-}" && -n "${AI_HTTP_API_KEY:-}" && -n "${AI_HTTP_MODEL:-}" ]]; then
    return 0
  fi

  local db="${CC_SWITCH_DB:-$HOME/.cc-switch/cc-switch.db}"
  [[ -f "$db" ]] || return 0

  "$PYTHON" - "$db" <<'PY'
import json
import re
import sqlite3
import sys

db = sys.argv[1]
preferred = ("Aiaps1", "Aiapis")
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

name, raw = selected
config = json.loads(raw)
api_key = (config.get("auth") or {}).get("OPENAI_API_KEY", "").strip()
toml_text = str(config.get("config") or "")
base_match = re.search(r'base_url\s*=\s*"([^"]+)"', toml_text)
model_match = re.search(r'model\s*=\s*"([^"]+)"', toml_text)
base_url = base_match.group(1).strip() if base_match else ""
model = (model_match.group(1).strip() if model_match else "") or "gpt-5.4-mini"

# The project defaults to the cheaper fast model for product AI calls even when
# the Codex provider profile itself uses another model.
model = "gpt-5.4-mini"

if not (api_key and base_url):
    raise SystemExit(0)

def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"

print(f"export AI_HTTP_BASE_URL={sh_quote(base_url)}")
print(f"export AI_HTTP_API_KEY={sh_quote(api_key)}")
print(f"export AI_HTTP_MODEL={sh_quote(model)}")
PY
}

AIAPIS_EXPORTS="$(load_aiapis_env_from_cc_switch || true)"
if [[ -n "$AIAPIS_EXPORTS" ]]; then
  # shellcheck disable=SC1090
  eval "$AIAPIS_EXPORTS"
fi

export AI_HTTP_TIMEOUT_SECONDS="${AI_HTTP_TIMEOUT_SECONDS:-60}"
export SPEAKING_AI_CALL_MODE="${SPEAKING_AI_CALL_MODE:-chain}"
export SPEAKING_AI_MODEL="${SPEAKING_AI_MODEL:-${AI_HTTP_MODEL:-gpt-5.4-mini}}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-127.0.0.1,localhost}"

port_is_open() {
  "$PYTHON" - "$DJANGO_HOST" "$DJANGO_PORT" <<'PY'
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
sock = socket.socket()
sock.settimeout(0.25)
try:
    sock.connect((host, port))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
}

start_django() {
  if port_is_open; then
    echo "Django already listening at http://$DJANGO_HOST:$DJANGO_PORT"
    return 0
  fi
  echo "Starting Django at http://$DJANGO_HOST:$DJANGO_PORT"
  (
    cd "$ROOT_DIR"
    exec "$PYTHON" backend_django/manage.py runserver "$DJANGO_HOST:$DJANGO_PORT" --noreload
  ) >"$RUNLOG_DIR/django.out.log" 2>"$RUNLOG_DIR/django.err.log" &
}

start_worker() {
  rm -f "$STOP_FILE"
  if pgrep -f "backend_django/manage.py run_ai_worker" >/dev/null 2>&1; then
    echo "AI worker already running"
    return 0
  fi
  if [[ -z "${AI_HTTP_BASE_URL:-}" || -z "${AI_HTTP_API_KEY:-}" || -z "${AI_HTTP_MODEL:-}" ]]; then
    echo "Warning: AI_HTTP_* is incomplete; worker may fall back to Codex/fallback." >&2
  fi
  echo "Starting AI worker"
  (
    cd "$ROOT_DIR"
    exec "$PYTHON" backend_django/manage.py run_ai_worker \
      --interval-seconds 2 \
      --idle-interval-seconds 5 \
      --stop-file "$STOP_FILE"
  ) >"$RUNLOG_DIR/ai-worker.out.log" 2>"$RUNLOG_DIR/ai-worker.err.log" &
}

start_tunnel() {
  if [[ "${IELTS_PUBLIC:-0}" != "1" ]]; then
    return 0
  fi
  if pgrep -f "cloudflared tunnel.*127.0.0.1:$DJANGO_PORT" >/dev/null 2>&1; then
    echo "cloudflared quick tunnel already running"
    return 0
  fi
  if ! command -v cloudflared >/dev/null 2>&1; then
    echo "Warning: IELTS_PUBLIC=1 but cloudflared is not on PATH." >&2
    return 0
  fi
  echo "Starting cloudflared quick tunnel"
  cloudflared tunnel --url "http://127.0.0.1:$DJANGO_PORT" --no-autoupdate \
    >"$RUNLOG_DIR/cloudflared.out.log" 2>"$RUNLOG_DIR/cloudflared.err.log" &
}

start_django
start_worker
start_tunnel

cat >"$RUNLOG_DIR/stack-status.json" <<EOF
{"app":"http://$DJANGO_HOST:$DJANGO_PORT","django":"http://$DJANGO_HOST:$DJANGO_PORT","worker":"run_ai_worker","logs":"$RUNLOG_DIR","public":"${IELTS_PUBLIC:-0}"}
EOF

echo "IELTS stack requested."
echo "App: http://$DJANGO_HOST:$DJANGO_PORT"
echo "Logs: $RUNLOG_DIR"
if [[ "${IELTS_PUBLIC:-0}" == "1" ]]; then
  echo "Public tunnel log: $RUNLOG_DIR/cloudflared.err.log"
fi
