# Legacy Server Retirement

## Status

`web/ielts_server.py` is frozen as a legacy reference artifact. It is not a
production runtime, and normal local/public startup must use Django.

Frozen means:

- Do not add features to `web/ielts_server.py`.
- Do not route `/api/*` traffic to `web/ielts_server.py`.
- Do not use it for local demo, public tunnel, or production startup.
- Only inspect it to compare historical behavior while migrating or debugging.
- Any behavior still needed by the product must be migrated into Django or
  `web/static/`, then validated on the Django runtime.

Current production runtime:

```bash
python backend_django/manage.py runserver 127.0.0.1:8767 --noreload
```

Optional worker for queued AI tasks:

```bash
python backend_django/manage.py run_ai_worker --interval-seconds 2 --idle-interval-seconds 5
```

## Why It Is Retired

The product has migrated the browser frontend, API surface, reports, writing,
speaking runtime, billing, AI tasks, corpus, Takeaway, audio, and TTS routes to
Django. Keeping the old server executable made the architecture ambiguous and
allowed scripts/docs to accidentally route production traffic through the wrong
process.

## What Remains

The old file remains in place only so historical behavior can be inspected and
compared during debugging. It should not receive new features.

Direct startup is blocked by default. To inspect the old runtime intentionally:

```bash
IELTS_ALLOW_LEGACY_SERVER=1 python web/ielts_server.py --host 127.0.0.1 --port 8765
```

Use that only for short-lived reference checks. Do not use it for public
tunnels, demos, production, or new feature work.

## Production Invariants

- Django serves `web/static/index.html`, `app.js`, `styles.css`, and assets.
- Django owns `/api/*`.
- Public tunnels point at the Django port.
- The Windows launcher starts Django only.
- Legacy tests are reference-only and must not define production behavior.
- New feature work belongs in `backend_django/` and `web/static/`, not in the
  retired server.

## Validation

Run:

```bash
python scripts/validate_legacy_server_retirement.py
```

The script checks that docs/scripts do not route production to the old server,
that Django still exposes the current app surface, that Django does not import
the retired server, that the frozen file still carries its startup guard, and
that accidental legacy startup is blocked.
