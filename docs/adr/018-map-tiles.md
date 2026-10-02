# ADR-018: Map tiles: OpenFreeMap now, satellite behind config

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-06 (lot geometry), P1-07 (public map)

## Context

Buyers of bare land want an aerial view, but the plan names no tile provider.

## Decision

- The base map is OpenFreeMap vector tiles, which need no account or key.
- A satellite layer from MapTiler's free tier is wired behind config and stays dormant until a
  key exists, following ADR-012's dormant-integration pattern.

Scott chose this on 2026-10-01.

## Alternatives considered

- **MapTiler from the start.** Rejected for now: needs an account and key before maps work.
- **OpenFreeMap only.** Rejected: no satellite view, ever.

## Consequences

- Phase 1 ships without satellite unless a MapTiler key is added.
- Switching providers is a style URL change.

## Related

ADR-012 (dormant without credentials), ADR-016 (free tiers)
