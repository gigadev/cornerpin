# ADR-017: Tooling defaults

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-01

## Context

A consistent tool set keeps tasks small and the code typed end to end.

## Decision

- **Python:** uv, ruff, pyright, pytest; FastAPI, Pydantic, SQLAlchemy 2, Alembic, Strawberry;
  LightGBM for scoring.
- **Web:** a pnpm workspace; Next.js, Tailwind, shadcn/ui, MapLibre GL, Vitest, Playwright.
- **Types:** generated from OpenAPI and the GraphQL schema.
- **Email:** Resend for transactional email, behind an interface.
- **Git:** Scott owns git. Claude Code never commits and ends each task with a proposed commit
  message.

## Consequences

- Setup specifics that follow from these defaults are in ADR-019.

## Related

ADR-002, ADR-004, ADR-007, ADR-019
