# ADR-012: Integrations are per-tenant, optional and dormant without credentials

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** Phase 2 (Slack, Salesforce), Phase 3 (Snowflake), Phase 4 (Gmail, Zoom)

## Context

The project shows a range of integrations, but the first real tenant needs none of them.

## Decision

Each integration is an adapter behind an interface, enabled per tenant and exercised in the
demo tenant:

- **Salesforce:** inquiries as Leads/Opportunities, lot status sync.
- **Slack:** alerts and a `/lot` lookup.
- **Gmail:** inquiry threads on the lead timeline.
- **Zoom:** virtual lot tours.
- **Snowflake:** event warehouse feeding features and dashboards.

## Consequences

- Ricky's tenant runs with none of them configured.

## Related

ADR-002 (Snowflake is analytics only), ADR-010 (run from the outbox), ADR-016 (cost)
