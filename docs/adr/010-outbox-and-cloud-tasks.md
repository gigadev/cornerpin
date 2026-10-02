# ADR-010: Transactional outbox and Cloud Tasks for background work

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-09

## Context

State changes trigger side effects (email, push, integrations, outreach, scoring) that call
third parties and must not be lost or slow down a request.

## Decision

- A state change writes an `outbox` row in the same transaction.
- A dispatcher turns rows into Cloud Tasks that call `/internal` handlers on the API. Locally an
  in-process runner does the same.
- Notifications, integrations, outreach and scoring all run there.

## Consequences

- No third-party or model call happens during a request.
- A failed side effect retries without losing the event.

## Related

ADR-011 (modules talk through the outbox), ADR-012, ADR-013, ADR-014
