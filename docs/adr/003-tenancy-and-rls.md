# ADR-003: Tenancy = organizations, isolated by row-level security

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-02

## Context

Several owners share one deployment, and one owner must never see another owner's data.

## Decision

- A tenant is an owner organization. It owns subdivisions, which own phases, which own lots.
- Users are global and join tenants through `memberships` with a role (owner, staff). Buyers
  are users with no membership.
- The API connects as a non-owner database role and sets `app.tenant_id` and `app.user_id`
  with `SET LOCAL` per transaction.
- Row-level security is enabled and forced on every tenant-owned table.

## Consequences

- A bug in a query cannot leak another tenant's rows.
- Every tenant-owned table ships with its policies and a cross-tenant test.

## Related

ADR-002 (Postgres), ADR-008 (auth)
