# ADR-022: Contact consent is recorded per tenant and append-only

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-02 (table), P1-08 (capture)

## Context

ADR-014 requires consent per channel, with a timestamp, before any outreach. The plan says
`contact_consents` is "per user, per channel" but not whether consent given on one owner's
subdivision covers messages from another owner. Users are global (ADR-003).

## Decision

- Consent is recorded per tenant, user and channel. Agreeing to hear from one owner does not
  allow another owner to contact you.
- The table is append-only: a grant and a later opt-out are separate rows, each with its source
  and time. The latest row per tenant, user and channel is the current state. The API role has
  no `UPDATE` or `DELETE` on it.

This is the stricter of the two readings. Scott confirmed it on 2026-10-01.

## Consequences

- The consent history is a complete audit trail for every send decision.
- A buyer interested in two subdivisions from different owners consents twice.
- Looking up the current consent is an ordered lookup, served by an index on
  `(tenant_id, user_id, channel, recorded_at desc)`.

## Related

ADR-014 (outreach), ADR-021 (policies)
