# ADR-021: Database roles and the shape of RLS policies

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-02

## Context

ADR-003 says the API connects as a non-owner role and sets the tenant and user per transaction.
It does not say how signed-in and anonymous traffic differ, what happens if the API sets the
wrong tenant, or how buyers, who belong to no tenant, see their own activity.

## Decision

- **Three roles.** `cornerpin_api` is the only login role. It is `NOINHERIT` and holds no
  privileges itself. Each transaction runs `SET LOCAL ROLE` to one of two group roles:
  `cornerpin_user` for signed-in users and `cornerpin_public` for anonymous visitors. The
  helpers in `cornerpin.core.db` do this; a connection used without them can read nothing.
- **Membership is checked in SQL.** `app_tenant_id()` returns `app.tenant_id` only if the
  current user is a member of that tenant. A wrong tenant id from an API bug exposes nothing.
- **Two ways to see a row.** Tenant rows are visible to the tenant's members. Buyer activity
  (saved lots, inquiries, hold requests, consents) is also visible to the buyer who created it,
  by `app.user_id`. Users, notification preferences and push subscriptions are visible only to
  their own user.
- **Public reads.** `cornerpin_public` sees published subdivisions, their phases, published lots
  in them, and those lots' media, documents and QR codes. It has no grant on anything else.
- **Tenant consistency.** Child tables carry composite foreign keys such as
  `(lot_id, tenant_id) → lots (id, tenant_id)`, so a row cannot name a different tenant than its
  parent.
- **History by trigger.** Status and price history is written by a trigger on `lots`, recording
  `app.user_id` as the author.
- **Owner role.** Migrations and the seed run as the database owner. Locally the migration sets
  the `cornerpin_api` password from `API_DATABASE_URL`; in the cloud it is provisioned with the
  infrastructure.

## Consequences

- One connection pool and one credential serve both kinds of traffic.
- Policies on `memberships` may not query `memberships`, so members can see only their own
  membership row. Listing a tenant's members needs a security-definer function when a task
  calls for it.
- Sign-up (creating `users` rows) and anonymous inquiries need their own policies, added in
  P1-03 and P1-08.
- Creating tenants is an owner-role operation; how that runs in production is settled in P1-12.

## Related

ADR-003 (tenancy), ADR-008 (sessions), ADR-022 (consent)
