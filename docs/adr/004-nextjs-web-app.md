# ADR-004: Next.js (App Router, TypeScript) for the web app

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-01

## Context

Public lot pages must be server-rendered for search and link previews. The job posting asks
for "modern JS/TS" without naming a framework. Levelward already shows Angular; Next.js shows
range and has SSR built in.

## Decision

The web app is Next.js with the App Router and TypeScript. Scott chose it on 2026-10-01.

## Alternatives considered

- **Angular SSR.** Rejected: Levelward already shows Angular, and Next.js shows range.

## Consequences

- Tailwind and shadcn/ui for UI, Vitest for unit tests, Playwright for end-to-end tests,
  MapLibre GL for maps.
- The service worker is built with Serwist.

## Related

ADR-005 (PWA), ADR-007 (GraphQL reads), ADR-019 (Serwist setup)
