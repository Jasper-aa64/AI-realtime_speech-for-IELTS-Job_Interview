# Allow CSRF Trusted Origins for Public Tunnel

## Goal

Allow temporary public tunnel URLs to authenticate against the local Django server without weakening CSRF protection globally.

## Root Cause

The Cloudflare quick tunnel host was added to `DJANGO_ALLOWED_HOSTS`, so GET requests work. Login POST requests still fail because Django also checks `CSRF_TRUSTED_ORIGINS` against the HTTPS origin.

## Requirements

- Add settings support for `DJANGO_CSRF_TRUSTED_ORIGINS`.
- Keep default local behavior unchanged.
- Do not disable CSRF.
- Restart local Django with the active trycloudflare origin included.

## Acceptance Criteria

- [x] `POST /api/accounts/login/` on the public tunnel no longer fails with CSRF origin error.
- [x] Invalid credentials return normal login failure JSON, proving the request reached the login view.
- [x] Django system check passes.
