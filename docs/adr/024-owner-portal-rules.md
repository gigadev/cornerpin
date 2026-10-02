# ADR-024: Owner portal rules for editing, deleting and history

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-04

## Context

P1-04 asks for subdivision, phase and lot management with status and price history. The plan
does not say whether staff differ from owners, what may be deleted, how history shows who made
a change when users can only read their own row (ADR-021), or how lots get a location and
acreage before the map editor (P1-06).

## Decision

- **Owners and staff have the same portal rights.** The plan names both roles but no
  difference; one can be added later.
- **Deleting is refused while something depends on it.** A subdivision or phase with lots
  returns 409. A lot with inquiries or hold requests returns 409: their foreign keys to `lots`
  are `ON DELETE RESTRICT`, so no code path can delete buyer records with a lot. Saved lots
  still go with their lot. Unpublishing is the way to take a lot down.
- **History records the author's email.** The trigger copies the current user's email onto
  each status and price history row, because a later reader cannot look other users up.
- **Prices are whole dollars in the API and the portal.** The column keeps cents.
- **Until P1-06, location and acreage are typed in.** A subdivision takes latitude and
  longitude; a lot takes acreage. P1-06 replaces both with the map and the boundary.
- **Typed ORM models for listings.** SQLAlchemy models map the tables the migrations create; a
  test compares their columns, types and nullability with the database.
- **UI kit.** shadcn/ui (ADR-017) with its neutral palette and the system font stack; no web
  font until there is a brand.
- **Generated request types.** `openapi-typescript` runs with `--default-non-nullable false`,
  so fields with a server default are optional in request bodies, as the API treats them.

## Consequences

- An owner can always see why a delete was refused.
- History reads correctly even after the author's account changes or is removed.
- Portal end-to-end tests reuse one saved session per viewport, signed in by a setup project,
  so parallel tests never read each other's email.

## Related

ADR-003 (tenancy), ADR-017 (tooling), ADR-021 (policies), ADR-023 (sign-in)
