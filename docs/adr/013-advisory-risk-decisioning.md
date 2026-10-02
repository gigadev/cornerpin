# ADR-013: Risk decisioning is advisory, logged and explainable

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** Phase 3

## Context

Owners benefit from knowing which inquiries or holds are likely to fall through. Ricky does not
offer financing, and real credit decisions carry fair-lending and adverse-action obligations.

## Decision

- Every tenant gets a lead and deal score: the likelihood an inquiry or hold falls through, with
  reason codes.
- The owner-financing module (application, decision, loan, schedule, payments, delinquency)
  exists only in the demo tenant, on synthetic data.
- Models are gradient-boosted trees.
- Every score is stored with model version, inputs and reasons.
- A human makes every decision.

## Consequences

- No protected-class attributes or obvious proxies as features.
- No automated approval or denial.

## Related

ADR-011 (decisioning service), ADR-017 (LightGBM)
