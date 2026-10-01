# ADR-023: Sign-in, sessions, and starting the outbox in P1-03

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-03

## Context

P1-03 needs to send magic-link emails, but CLAUDE.md allows email only from background tasks
fed by the outbox, and the plan builds the outbox in P1-09. Sign-in also has to find users by
email before anyone is signed in, which the roles in ADR-021 do not allow. The plan does not say
how the web app and the API share a session cookie, or how the owner portal names a tenant.

## Decision

- **Outbox now, minimal.** P1-03 adds the `outbox` table, typed events and handlers, and an
  in-process runner that polls it inside the API (local only). Magic-link emails go through it.
  P1-09 adds the Cloud Tasks dispatcher and the notification events. Scott chose this on
  2026-10-01.
- **Two more group roles.** `cornerpin_auth` runs sign-in and session lookup: it can read and
  create users and manage login tokens and sessions, and is used only by the auth module.
  `cornerpin_worker` reads and updates the outbox and is used only by the runner. Both are
  reached by `SET LOCAL ROLE` from `cornerpin_api`, like the others.
- **Tokens.** Magic-link and session tokens are 32 random bytes; only their SHA-256 is stored. A
  link works once, for 15 minutes, and at most 5 are sent per address per 15 minutes. The
  outbox removes the link from the event once the email is sent. Sessions last 30 days, in an
  httpOnly, SameSite=Lax cookie that is Secure whenever the site is served over HTTPS.
- **A click to sign in.** The emailed link opens a page with a "Sign in" button; the token is
  spent by that POST, not by opening the link, because mail scanners open links.
- **One origin.** The browser only talks to the web app. A Next.js route handler forwards
  `/v1/*` to the API, so the session cookie is first-party, and API writes are refused when the
  `Origin` header is not the web origin.
- **Owner portal URLs.** The portal for a tenant is `/app/{tenantId}`. A tenant the user is not
  a member of is a 404, the same as one that does not exist.
- **Checks that belong to the request.** Turnstile verification and Google's code exchange call
  third parties during the request. They decide whether the request succeeds, so they are not
  side effects and do not go through the outbox.
- **Test addresses.** Locally, email addresses on `.test` domains are accepted so Mailpit can
  receive them; elsewhere they are rejected.
- **Generated types.** `pnpm gen:api` writes the OpenAPI schema and TypeScript types into
  `apps/web/lib/api/`; CI fails if they are out of date.

## Consequences

- No email is ever sent from a request, from the first email on.
- P1-09 is smaller: the table, runner and retry logic exist.
- The web app and API can stay separate Cloud Run services without sharing a domain for cookies.
- The `cornerpin_auth` role can read every user, so its use stays inside the auth module.

## Related

ADR-008 (passwordless auth), ADR-010 (outbox), ADR-021 (roles)
