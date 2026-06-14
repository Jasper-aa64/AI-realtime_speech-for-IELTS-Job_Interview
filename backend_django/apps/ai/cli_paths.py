from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_claude_cli_path(explicit: str | None = None) -> str:
    """Resolve Claude Code CLI across Windows services and user shells."""
    candidates: list[str] = []
    for value in (explicit, os.environ.get("CLAUDE_CLI_PATH")):
        value = str(value or "").strip()
        if value:
            candidates.append(value)

    for name in ("claude", "claude.cmd", "claude.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(found)

    roaming = os.environ.get("APPDATA")
    if roaming:
        candidates.append(
            str(Path(roaming) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe")
        )

    profile = os.environ.get("USERPROFILE")
    if profile:
        candidates.append(
            str(
                Path(profile)
                / "AppData"
                / "Roaming"
                / "npm"
                / "node_modules"
                / "@anthropic-ai"
                / "claude-code"
                / "bin"
                / "claude.exe"
            )
        )

    for candidate in candidates:
        if shutil.which(candidate) or Path(candidate).exists():
            return candidate
    return candidates[0] if candidates else "claude"

