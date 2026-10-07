# ADR-042: Phase 2 in production: each feature switched on by its secret

- **Status:** Accepted
- **Date:** 2026-10-06
- **Applies from:** P2-10

## Context

Phase 2 adds production secrets:
- the Claude API key (ADR-038);
- Resend's webhook signing secret (ADR-037);
- the Slack app's client secret and signing secret (ADR-040);
- the key that seals tenants' integration credentials (ADR-040, ADR-041).

Cloud Run won't start a revision that names a secret with no version. Re-running the Phase 1
`set-secrets.sh` would make a new `SECRET_KEY`, which signs everyone out and breaks unsubscribe
links. Scott sets secrets himself (CLAUDE.md), and each account (Anthropic, Resend's inbound,
Slack) may be ready at a different time. Salesforce needs no app-level secret, so it can be
connected whenever the API runs.

## Decision

- **Each feature has a switch in `terraform.tfvars`:**
  - `agent_enabled`;
  - `inbound_email_domain`;
  - `slack_client_id`, which is the Slack app's public client ID.

  A feature's secrets are wired to the API and the jobs only while its switch is on. The secret
  containers always exist, so the secrets can go in first. The jobs get the same settings as the
  API, so they pass the same start-up checks.
- **`INTEGRATIONS_KEY` is always required outside local.** The API refuses to start without it,
  whether or not Slack is configured, because an owner can connect Salesforce at any time, and
  a production credential must never be sealed under the public local key. It is generated, not
  typed.
- **`set-secrets.sh <project> phase2` sets only Phase 2's secrets.** Enter skips any of them.
  It generates `integrations-key` only if none exists, because a new key would leave every
  stored credential unreadable.
- **Order:**
  1. create the containers;
  2. set the secrets;
  3. switch on and apply;
  4. merge.

  Applying first is safe because the running Phase 1 code ignores settings it doesn't know.
- **Budget.** The Google Cloud budget stays $5. Phase 2 adds about $0.36 a month there:
  Secret Manager bills $0.06 per active version beyond six free, and Phase 2 adds up to five
  versions to about seven. Scott approved that on 2026-10-06. The Claude API is billed by Anthropic, capped in its Console, and is
  about $2–5 a month at demo volume. Scott approved it on 2026-10-06. Resend's receiving, Slack
  and Salesforce Developer Edition are free.

## Consequences

- Production can go live with any subset of Phase 2's features, and switching one on later is a
  secret, a switch and an apply.
- Losing `integrations-key` means every tenant reconnects Slack and Salesforce. It must not be
  rotated with the script.
- Slack expects a slash command's answer within three seconds. With Cloud Run scaled to zero,
  the first `/lot` after a quiet spell can miss that while two services wake. Minimum instances
  would fix it, at a cost not yet worth paying.

## Related

ADR-016 (free tiers first), ADR-032 (production deployment), ADR-037, ADR-038, ADR-040,
ADR-041
