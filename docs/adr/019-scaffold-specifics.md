# ADR-019: Scaffold specifics (P1-01)

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-01

## Context

Building the scaffold required several setup calls that the plan did not make.

## Decision

- **Workspace:** a uv workspace at the repo root (members `apps/api`) and `alembic.ini` at the
  root, so the CLAUDE.md commands work from the root.
- **Database port:** the local PostGIS container publishes on port 5434, because native Windows
  Postgres services commonly hold 5432 and 5433.
- **TypeScript:** pinned to 6.0.x, because typescript-eslint does not yet support 7.x.
- **Service worker:** built by `@serwist/turbopack`, served from `/serwist/sw.js` with
  `Service-Worker-Allowed: /` and registered at scope `/`. This keeps ADR-005's single root
  worker without leaving Turbopack.
- **Smoke tests:** Playwright runs against a production build at 390 px and 1280 px.

## Consequences

- Revisit the TypeScript pin when typescript-eslint supports 7.x.

## Related

ADR-004 (Next.js), ADR-005 (PWA), ADR-017 (tooling)
