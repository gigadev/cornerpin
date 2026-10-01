# ADR-020: ADRs live in docs/adr, one file per decision

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** now

## Context

Decisions ADR-001 to ADR-019 were kept as one paragraph each in a single `DECISIONS.md` at the
repo root. A single growing file is harder to link to, review in a diff and mark as superseded.
Scott asked for a dedicated folder on 2026-10-01.

## Decision

- Each ADR is its own file in `docs/adr/`, named `NNN-short-slug.md`, with Status, Date,
  Applies from, Context, Decision and Consequences. Alternatives considered and Related are
  optional sections.
- `docs/adr/README.md` is the index and explains the process; `docs/adr/template.md` is the
  starting point for a new ADR.
- ADR-001 to ADR-019 were split into these sections without changing their substance.
- The root `DECISIONS.md` stays as a pointer so existing links keep working.

## Consequences

- CLAUDE.md, the implementation plan and the README point at `docs/adr/`.
- A new decision means a new file and a new row in the index.
