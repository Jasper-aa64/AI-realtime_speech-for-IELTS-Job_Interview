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

DJANGO_HOST="${IELTS_DJANGO_HOST:-127.0.0.1}"
DJANGO_PORT="${IELTS_DJANGO_PORT:-8767}"
cd "$ROOT_DIR"
exec "$PYTHON" "$ROOT_DIR/backend_django/manage.py" runserver "$DJANGO_HOST:$DJANGO_PORT" --noreload
