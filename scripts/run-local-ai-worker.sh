#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -x "$ROOT_DIR/.venv-django/bin/python" ]]; then
  PYTHON="$ROOT_DIR/.venv-django/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

# shellcheck source=scripts/local-stack-env.sh
source "$ROOT_DIR/scripts/local-stack-env.sh"
load_local_stack_env

STOP_FILE="${IELTS_AI_WORKER_STOP_FILE:-/tmp/ielts-ai-worker.stop}"
rm -f "$STOP_FILE"
cd "$ROOT_DIR"
exec "$PYTHON" "$ROOT_DIR/backend_django/manage.py" run_ai_worker \
  --interval-seconds "${IELTS_AI_WORKER_INTERVAL_SECONDS:-2}" \
  --idle-interval-seconds "${IELTS_AI_WORKER_IDLE_INTERVAL_SECONDS:-5}" \
  --stop-file "$STOP_FILE"
