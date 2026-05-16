# Current Account Surface Audit

## Backend

* `backend_django/apps/accounts/models.py` defines `CustomUser` with username, email, phone fields, phone verification timestamp, WeChat identifiers, and a separate `UserProfile` for IELTS names/target band/timezone.
* `backend_django/apps/accounts/views.py` exposes only four endpoints: register, login, logout, and me.
* Auth is session-based via Django `authenticate`, `login`, and `logout`.
* Registration creates a wallet immediately and logs the user in.
* There is no password reset, password change, phone verification, email verification, MFA, account deletion, rate limiting, or explicit CSRF strategy beyond `csrf_exempt` on auth endpoints.

## Frontend

* `web/static/index.html` currently has a dedicated account panel, but it is still a simple card inside the app shell.
* The account UI mixes identity/profile fields with login/register controls.
* Error handling is a single status line.
* Registration is still labeled like a test-account action in places.
* Avatar opens account, while Settings holds wallet and weak-training records.

## Product Problem

This is adequate for local Django migration smoke testing, but it feels like an internal tool. A production-grade account system should have a dedicated auth experience, clear account settings, and security/recovery flows.
