# Boot Auto-Start and Stable Public Tunnel

## Goal
Make the IELTS local stack start automatically on Windows boot and expose it publicly with the most stable URL possible.

## Requirements
- Start the local frontend service on boot.
- Start the Django backend on boot.
- Start the public tunnel on boot.
- Keep the public URL stable if named tunnel credentials / hostname are available.
- If stable tunnel credentials are not available yet, provide a fallback quick-tunnel startup path and make the limitation explicit.
- Preserve the current app behavior and avoid unrelated UI or backend changes.

## Constraints
- Do not overwrite unrelated user changes.
- Prefer a lightweight Windows-native startup mechanism.
- Keep the implementation localized to startup / tunnel orchestration files unless a tiny adjacent code change is required.

## Acceptance Criteria
- A single startup entry point can launch the full stack.
- The stack can be triggered automatically at login / boot.
- Public access is restored after reboot.
- If a named tunnel config exists, the same hostname is reused across restarts.
- Documentation explains how to switch between quick tunnel and stable named tunnel modes.