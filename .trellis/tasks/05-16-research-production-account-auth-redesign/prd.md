# Research production account auth redesign

## Goal

Redesign the account/login experience as a production-quality product surface instead of a test-account card inside the app. The next implementation should replace the current account UI and tighten the Django account API enough that login, registration, account settings, and recovery feel trustworthy.

## What I Already Know

* The user rejected the current login UI as too toy-like.
* The current frontend has an account panel, but it is still an in-app card with login/register controls.
* Settings should not be the account surface.
* Current backend account endpoints are:
  * `POST /api/accounts/register/`
  * `POST /api/accounts/login/`
  * `POST /api/accounts/logout/`
  * `GET/PATCH /api/accounts/me/`
* Current backend uses Django session auth but marks account views `csrf_exempt`.
* `CustomUser` already has email, phone, verification, and WeChat identifier fields, so the model anticipates a more serious account system.
* There is no password reset, password change, email/phone verification, account deletion, rate limiting, or structured field-error contract.

## Research

* `research/current-account-surface.md`
* `research/auth-product-patterns.md`

## Product Direction

Build a dedicated first-party auth system using Django session auth, not a fake MVP:

* Public auth shell:
  * `/login`
  * `/register`
  * `/forgot-password`
* Authenticated account area:
  * `/account/profile`
  * `/account/security`
  * `/account/billing` or link to wallet
* App Settings remains separate from account:
  * local UI preferences
  * wallet if the user wants wallet there
  * weak training records
* Avatar opens a user menu:
  * current user identity
  * account settings
  * billing/wallet
  * sign out

## Requirements For Implementation

### Frontend

* Replace the current account card with dedicated auth pages/surfaces.
* Add a polished login page:
  * phone/email/username field
  * password field with reveal toggle
  * remember/current session language
  * forgot password link
  * create account link
  * clear field-level errors
* Add a polished registration page:
  * account identifier
  * password and confirmation
  * full name / English name as profile fields, but not mixed into login
  * explicit value proposition for saved reports, wallet, and personalized training
* Add an account settings page:
  * Profile section
  * Security section
  * Session/sign-out controls
  * Billing/wallet link or section
* Keep app settings free of primary login/register controls.

### Backend

* Replace `csrf_exempt` account endpoints with a deliberate CSRF strategy.
* Return structured field errors:
  * `{"errors": {"username": ["..."], "password": ["..."]}, "message": "..."}`
* Add password confirmation during registration.
* Use Django password validation.
* Add password change for authenticated users.
* Add password reset design:
  * Real email-backed reset if SMTP exists.
  * If no email provider is configured, do not pretend reset works; show a clear unavailable state.
* Add login/register throttling.
* Preserve existing session-cookie auth for API ownership checks.

## Acceptance Criteria

* [ ] The old in-app account card is removed or no longer reachable as the primary auth UI.
* [ ] Login, register, forgot password, account profile, and account security have dedicated surfaces.
* [ ] Settings no longer contains primary auth forms.
* [ ] Registration validates password confirmation and Django password rules.
* [ ] Account API returns structured field errors.
* [ ] Login/register/password reset are rate-limited or explicitly protected.
* [ ] CSRF handling is deliberate and tested.
* [ ] Existing app flows still work after login: wallet, writing, speaking history, scoring.
* [ ] Tests cover auth success, invalid credentials, duplicate account, password validation, password change, and unauthenticated access.

## Out Of Scope

* Fake SMS OTP.
* Fake email verification.
* Fake social login.
* Real Apple/Google/WeChat login unless provider credentials and redirect config are ready.
* Full multi-device session management.

## Recommended Implementation Sequence

1. Auth contract PRD and UI wireframe pass.
2. Backend account API hardening:
   * CSRF strategy
   * structured errors
   * password validation/confirmation
   * password change
   * reset availability contract
   * throttling
3. Frontend auth shell:
   * login/register/forgot password pages
   * user menu
   * account settings sections
4. Regression:
   * wallet
   * writing
   * speaking history
   * smoke verification

## Decision

Recommended path: first-party Django session auth rebuild.

Reason: The app already depends on Django sessions for ownership-scoped APIs, and the immediate need is a trustworthy integrated account experience. Auth0/Clerk are good references, but adopting them now adds provider configuration, callback handling, account-linking, and billing identity migration work before the product needs it.
