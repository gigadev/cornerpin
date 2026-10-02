# ADR-011: Modular monolith with service boundaries drawn now

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-01; decisioning split in Phase 3

## Context

The API covers several areas that may need to be deployed separately later, but one deployable
is simpler to run now.

## Decision

- `listings`, `leads`, `notifications`, `outreach`, `decisioning` and `integrations` are modules
  in one API container.
- Modules talk through function interfaces and the outbox, never through each other's tables.
- Decisioning moves to its own Cloud Run service in Phase 3, when the ML dependencies would
  otherwise bloat the API image.

## Consequences

- One deployable until there is a reason for two.

## Related

ADR-010 (outbox), ADR-013 (decisioning)
