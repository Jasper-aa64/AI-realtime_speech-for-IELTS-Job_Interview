#!/usr/bin/env python3
"""Validate that the retired legacy server is not part of production startup."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def ensure_readme_is_django_only() -> None:
    readme = read_text("README.md")
    require("python3 web/ielts_server.py" not in readme, "README still starts the retired legacy server")
    require("route `/api/*` to `web/ielts_server.py`" not in readme, "README still routes APIs to legacy server")
    require("python backend_django/manage.py runserver" in readme, "README does not document Django runserver")


def ensure_windows_launcher_is_django_only() -> None:
    start_script = read_text("scripts/windows/start-ielts-stack.ps1")
    require("ielts_server.py" not in start_script, "Windows start script still references legacy server")
    require("DjangoPort" in start_script, "Windows start script lost Django port configuration")
    require("--url\", \"http://127.0.0.1:$DjangoPort" in start_script, "Cloudflare quick tunnel is not pointed at Django")


def ensure_django_url_surface_exists() -> None:
    urls = read_text("backend_django/config/urls.py")
    for token in [
        'path("", frontend_asset',
        'path("shared-ui.js", frontend_asset',
        'path("app.js", frontend_asset',
        'path("api/attempts/start"',
        'path("api/writing/',
        'path("api/history"',
        'path("api/billing/',
    ]:
        require(token in urls, f"Django URL surface missing {token!r}")


def ensure_legacy_startup_is_blocked() -> None:
    env = os.environ.copy()
    env.pop("IELTS_ALLOW_LEGACY_SERVER", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "web" / "ielts_server.py"), "--host", "127.0.0.1", "--port", "0"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
    )
    require(result.returncode == 78, f"legacy server startup returned {result.returncode}, expected 78")
    require("retired" in result.stderr.lower(), "legacy startup failure did not explain retirement")


def main() -> int:
    checks = [
        ensure_readme_is_django_only,
        ensure_windows_launcher_is_django_only,
        ensure_django_url_surface_exists,
        ensure_legacy_startup_is_blocked,
    ]
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
