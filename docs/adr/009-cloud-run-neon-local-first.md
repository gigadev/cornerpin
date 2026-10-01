# ADR-009: Cloud Run + Neon + Cloud Storage, built locally first

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-01 (local), P1-12 (deploy)

## Context

The job posting asks for cloud deployment and a live link, and names no cloud. Traffic will be
low.

## Decision

- API and web are separate Cloud Run services.
- Postgres is Neon, with PostGIS.
- Photos and documents are in Cloud Storage.
- Terraform and GitHub Actions define and deploy it.
- Development runs entirely on the dev machine with Docker.

Cloud Run and Neon both scale to zero, so a low-traffic production site costs close to nothing.

## Consequences

- Phase gates are passed on the production URL, not locally.
- Cold starts of a second or so are accepted.

## Related

ADR-010 (Cloud Tasks), ADR-016 (cost)
