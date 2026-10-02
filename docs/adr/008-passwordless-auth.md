# ADR-008: Passwordless auth owned by the API

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-03

## Context

Owners and buyers need to sign in, and public forms need protection from bots.

## Decision

- Magic link plus Google sign-in.
- Sessions are httpOnly cookies.
- Cloudflare Turnstile guards sign-up, magic-link requests and public forms.
- No password provider.

## Consequences

- There is never a password field.
- Google sign-in stays dormant until a client id exists.
- Locally, Mailpit receives magic links and Turnstile uses Cloudflare's always-pass test keys.

## Related

ADR-003 (session sets tenant and user)
