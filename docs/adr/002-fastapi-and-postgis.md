# ADR-002: FastAPI is the API; Postgres + PostGIS is the system of record

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-01

## Context

The target stack is Python, SQL and REST/GraphQL, and lot boundaries are polygons.

## Decision

The API is FastAPI with SQLAlchemy 2, GeoAlchemy2 and Alembic, on Postgres with the PostGIS
extension.

## Consequences

- Geometry and distance queries live in SQL.
- Snowflake (ADR-012) is for analytics only and never serves a page.

## Related

ADR-003 (tenancy), ADR-012 (integrations), ADR-017 (tooling)
