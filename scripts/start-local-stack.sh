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

# shellcheck source=scripts/local-stack-env.sh
source "$ROOT_DIR/scripts/local-stack-env.sh"
load_local_stack_env

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

ensure_migrations() {
  echo "Checking Django migrations"
  if "$PYTHON" "$ROOT_DIR/backend_django/manage.py" migrate --check >/dev/null 2>&1; then
    return 0
  fi
  echo "Applying pending Django migrations"
  "$PYTHON" "$ROOT_DIR/backend_django/manage.py" migrate
}

ensure_image_thumbnails() {
  if [[ ! -x "$ROOT_DIR/scripts/generate_image_thumbs.sh" ]]; then
    return 0
  fi
  echo "Checking writing image thumbnails"
  if ! "$ROOT_DIR/scripts/generate_image_thumbs.sh"; then
    echo "Warning: writing image thumbnail generation failed; continuing startup." >&2
  fi
}

start_django() {
  ensure_image_thumbnails
  ensure_migrations
  if port_is_open; then
    echo "Django already listening at http://$DJANGO_HOST:$DJANGO_PORT"
    return 0
  fi
  echo "Starting Django at http://$DJANGO_HOST:$DJANGO_PORT"
  nohup "$PYTHON" "$ROOT_DIR/scripts/run_local_stack_process.py" django \
    >"$RUNLOG_DIR/django.out.log" 2>"$RUNLOG_DIR/django.err.log" &
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
  nohup "$PYTHON" "$ROOT_DIR/scripts/run_local_stack_process.py" worker \
    >"$RUNLOG_DIR/ai-worker.out.log" 2>"$RUNLOG_DIR/ai-worker.err.log" &
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
