# ADR-006: Path-based public URLs on one origin

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-07 (public pages), P1-11 (QR codes)

## Context

Each subdivision needs public addresses that buyers can share and that printed signs can point
at.

## Decision

- Public pages are `cornerpin.app/{subdivision-slug}` and
  `/{subdivision-slug}/lots/{lot-number}`. The owner portal is `/app`.
- Slugs are globally unique, with a reserved-word list.
- Sign QR codes point at `/q/{code}`, a stable redirect, so a printed sign survives a rename.

## Alternatives considered

- **Wildcard subdomains and custom domains.** Deferred: they need a load balancer.

## Consequences

- One certificate, one service worker, no per-tenant DNS.

## Related

ADR-005 (PWA scopes)
