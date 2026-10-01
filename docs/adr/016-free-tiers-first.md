# ADR-016: Free tiers first; cost is announced before it is incurred

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** throughout

## Context

This is a solo project with low traffic, and several services have paid plans or trials whose
clock starts on sign-up.

## Decision

- Every service starts on its free tier or trial.
- Before a task enables a paid plan, or starts a trial clock (Snowflake's 30 days, Twilio
  registration fees), the expected monthly cost is stated and Scott approves.

## Consequences

- The Snowflake trial does not start until Phase 3 begins.

Expected running costs are listed in
[the implementation plan](../IMPLEMENTATION_PLAN.md#expected-running-costs).

## Related

ADR-009 (hosting), ADR-012 (integrations), ADR-014 (Twilio)
