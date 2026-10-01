# ADR-001: Name Cornerpin, domain cornerpin.app

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** day zero

## Context

The product needs a name, a domain and a repository name.

## Decision

The product is named Cornerpin, for the survey pins that mark a lot's corners. Scott registered
`cornerpin.app` on 2026-10-01. The repository and the local folder are both `cornerpin`.

## Consequences

- `.app` is on the HSTS preload list, so every environment that uses the domain must serve
  HTTPS. The PWA needs HTTPS anyway (ADR-005).
