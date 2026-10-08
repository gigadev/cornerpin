# ADR-044: A public page on how Cornerpin is built

- **Status:** Accepted
- **Date:** 2026-10-07
- **Applies from:** after Phase 2

## Context

Cornerpin is also Scott's showcase for job applications (CLAUDE.md). People reviewing it want
to see where it runs, which services and languages it uses, and how it's tested and deployed,
without access to the repository. The plan has a buyer-and-owner guide at `/help`, but nothing
on how the app itself is built. Scott asked for one, public like the guide.

## Decision

- **A static page at `/about`, "How Cornerpin is built".** It covers:
  - the request path;
  - the Google Cloud and outside services;
  - what a merge to `main` does;
  - the languages;
  - the test counts and the main safeguards.
- **`/about` was already reserved** for subdivision web addresses (migration 0002), so no
  subdivision can collide with it and nothing in the database changes.
- **It is linked from the end of `/help` and from the home page.** The site header stays as
  it is, so the phone-width header doesn't get more crowded.
- **It is static and has nobody's data.** The service worker doesn't keep it, like `/help`.
- **It names no account IDs, project IDs, emails or keys.**

## Consequences

- The page is hand-written. When `infra/`, the workflows or the test counts change materially,
  it needs updating; a comment at the top of the page says so.
- The figures on it are a snapshot: 291 API tests, 119 web unit tests, 76 browser tests,
  13 eval scenarios and 44 ADRs on 2026-10-07.

## Related

ADR-032 (production deployment), ADR-042 (Phase 2 in production), ADR-043
