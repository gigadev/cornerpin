# ADR-007: REST for writes, GraphQL for public reads

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-04 (REST), P1-07 (GraphQL)

## Context

Owners change data through forms; the public browses subdivisions, lots, maps and filters, and
those reads should be cacheable.

## Decision

- The owner portal, forms, webhooks and internal task handlers use REST under `/v1`, with an
  OpenAPI schema.
- Public browsing (subdivision, lots, map, filters) uses GraphQL (Strawberry), read-only. It is
  called server-side by Next.js and over GET from the client so responses can be cached.

## Consequences

- Two schemas to keep typed, each used where it fits.
- No GraphQL mutations.

## Related

ADR-004 (Next.js), ADR-017 (type generation)
