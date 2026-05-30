#!/usr/bin/env python3
"""Validate that the retired legacy server is not part of production startup."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def normalized_text(value: str) -> str:
    return " ".join(value.split())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def ensure_readme_is_django_only() -> None:
    readme = read_text("README.md")
    require("python3 web/ielts_server.py" not in readme, "README still starts the retired legacy server")
    require("route `/api/*` to `web/ielts_server.py`" not in readme, "README still routes APIs to legacy server")
    require("python backend_django/manage.py runserver" in readme, "README does not document Django runserver")
    require("validate_legacy_server_retirement.py" in readme, "README does not mention legacy retirement validation")


def ensure_retirement_doc_exists() -> None:
    doc = read_text("docs/LEGACY_SERVER_RETIREMENT.md")
    normalized = normalized_text(doc)
    for token in [
        "frozen as a legacy reference artifact",
        "not a production runtime",
        "IELTS_ALLOW_LEGACY_SERVER=1",
        "python scripts/validate_legacy_server_retirement.py",
    ]:
        require(token in normalized, f"retirement doc missing {token!r}")


def ensure_legacy_file_is_frozen() -> None:
    legacy = read_text("web/ielts_server.py")
    require("Frozen legacy web boundary" in legacy, "legacy server header does not mark frozen boundary")
    require("LEGACY_SERVER_ALLOW_ENV" in legacy, "legacy server no longer exposes explicit allow env")
    require("retired and is no longer a production runtime" in legacy, "legacy startup guard message missing retirement wording")


def ensure_django_backend_has_no_legacy_imports() -> None:
    pattern = re.compile(r"^\s*(?:from|import)\s+.*ielts_server", re.MULTILINE)
    for path in (ROOT / "backend_django").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(ROOT)
        require(not pattern.search(path.read_text(encoding="utf-8")), f"Django backend imports retired server in {relative}")


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
        ensure_retirement_doc_exists,
        ensure_legacy_file_is_frozen,
        ensure_django_backend_has_no_legacy_imports,
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
