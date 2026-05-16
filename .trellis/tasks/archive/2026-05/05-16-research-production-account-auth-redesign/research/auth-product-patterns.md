# Auth product patterns research

## Sources

* Apple Human Interface Guidelines, Sign in with Apple:
  https://developer.apple.com/design/human-interface-guidelines/sign-in-with-apple
* Material Design, Settings pattern:
  https://m1.material.io/patterns/settings.html
* Material Design, Text fields:
  https://m1.material.io/components/text-fields.html
* Material Design, Errors:
  https://m1.material.io/patterns/errors.html
* Auth0 Universal Login:
  https://auth0.com/docs/authenticate/login/auth0-universal-login/new-experience
* Auth0 signup/login prompt customization:
  https://auth0.com/docs/customize/login-pages/universal-login/customize-signup-and-login-prompts
* Clerk custom email/password flow:
  https://clerk.com/docs/custom-flows/email-password/
* Django 5.2 auth docs via Context7:
  `/django/django/5_2_6`, query `Django authentication sessions password reset csrf login logout current documentation`

## Findings

### Sign-in timing and product trust

Apple's guidance is useful even if this app does not implement Apple login yet:

* Ask users to sign in only when they understand the value.
* Delay sign-in until the user is about to save, synchronize, pay, or access personal data.
* After sign-in, do not block users with unnecessary profile fields.
* Account/settings pages should clearly show the current sign-in method and account state.

For this IELTS app, that means:

* Browsing prompts and trying a limited practice flow can remain visible.
* Saving writing, scoring, wallet, history, and personalized weak training should require login.
* The auth page should explain concrete value: reports, wallet, practice history, personalized training.

### Separate auth from app settings

Material's settings pattern treats settings as a navigable system area for current configuration/status, not as the primary authentication form. Auth0 and Clerk both model authentication as a dedicated flow with focused screens: sign in, sign up, verification, password reset, and account/security management.

For this app:

* Login/register should be an auth route/surface, not a card inside Settings.
* Settings should not host primary authentication.
* Account settings should be a separate authenticated area with profile and security sections.
* App settings can hold local preferences and non-sensitive controls.

### Form quality

Material form/error guidance maps directly to this app:

* Labels must be explicit; placeholders should not replace labels.
* Each field needs field-level helper/error text.
* Submission errors need a visible summary.
* Preserve user-entered values where safe.
* Password fields need visibility toggle and autocomplete attributes.
* Buttons should clearly distinguish sign in, create account, forgot password, and continue as current user.

### Hosted/centralized auth lesson

Auth0 Universal Login is not necessarily the implementation choice, but the pattern is relevant:

* The login flow is a security boundary.
* It should be centralized and consistent, not duplicated inside random app pages.
* It should support localization, MFA/passkeys/social later, and password reset without changing core app screens.

### Django implementation lesson

Django 5.2 provides standard login/logout/password change/password reset flows with CSRF-protected forms. The current code uses JSON endpoints with `csrf_exempt`, which was useful for migration but is not the right end-state for a production account surface.

Production direction:

* Keep Django session auth unless there is a strong reason to adopt a hosted provider.
* Add a CSRF-aware JSON strategy or server-rendered auth routes.
* Add password reset and password change.
* Add password validation and field-level error payloads.
* Add rate limiting for login/register/reset.
* Do not show unavailable flows such as SMS OTP unless a real SMS provider exists.

## Recommendation

Use a first-party Django session-auth rebuild now, designed like a proper auth product:

* Dedicated `/login`, `/register`, `/forgot-password`, `/account`, `/account/security` frontend surfaces.
* JSON APIs remain under `/api/accounts/*`, but become CSRF-aware and return structured field errors.
* Account menu/avatar opens a compact user menu, not a raw form.
* Settings no longer means account. Settings is for app preferences and operational panels.
* Add provider-ready slots later for Apple/Google/WeChat/passkeys, but do not fake them.

Do not adopt Auth0/Clerk immediately unless the product needs third-party identity, passkeys, MFA, and hosted recovery now. They are useful references, but this codebase already has Django auth, session cookies, and user-owned domain data.
