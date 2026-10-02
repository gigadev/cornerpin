# ADR-005: The web app is a PWA built for use on site

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-01 (shell), P1-10 (caching rules)

## Context

Buyers will open a lot page from a QR code on a sign, often with weak signal.

## Decision

- The app is installable.
- It precaches a subdivision's lot summaries on first visit, serves previously viewed lot pages
  and photos offline, and queues an inquiry until the connection returns.
- Web push is offered for saved-lot alerts. Email stays the primary channel because iOS only
  allows push for installed apps.
- Each subdivision has its own manifest (id and scope `/{slug}/`); the owner portal has its own
  (`/app/`). One service worker at the root serves both.

## Consequences

- The service worker never caches authenticated or owner-portal responses.
- The owner portal is online-only in v1.

The detailed caching behaviour is in the PWA table in
[the implementation plan](../IMPLEMENTATION_PLAN.md#pwa-behaviour-adr-005).

## Related

ADR-001 (HTTPS), ADR-006 (URLs), ADR-019 (service worker setup)
