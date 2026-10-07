# ADR-040: Integration credentials live sealed in the database; Slack connects by OAuth

- **Status:** Accepted
- **Date:** 2026-10-06
- **Applies from:** P2-07

## Context

ADR-012 makes integrations per tenant and optional. The plan leaves open where a tenant's
integration credentials live. Each tenant has its own Slack webhook now, and its own Salesforce
org next (P2-08). Credentials arrive at runtime, when an owner connects, so Terraform can't
create them, and Secret Manager would need the API to create secrets at runtime. CLAUDE.md
requires third-party calls to run in outbox handlers, and secrets to stay out of the web bundle.

## Decision

- **Two kinds of secret.**
  - **Cornerpin's own app credentials** come from the environment, and from Secret Manager in
    the cloud, like every other secret: `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`,
    `SLACK_SIGNING_SECRET`, and `INTEGRATIONS_KEY`.
  - **A tenant's credentials** are sealed with AES-256-GCM under `INTEGRATIONS_KEY` and stored in
    `integration_connections.secret`. The tenant and provider are bound in as associated data,
    so a sealed value copied to another row doesn't open. A version byte leaves room to rotate
    the key.
- **Owners never read a secret back.** The portal role has column grants without `secret`, and
  the API returns only the status, the workspace and the channel. The worker unseals credentials
  when it delivers.
- **Slack connects by OAuth, finished in the background.**
  1. "Add to Slack" sends the owner to Slack with a signed state naming the tenant and the owner.
     The scopes are `incoming-webhook` (the owner picks the channel) and `commands`.
  2. The callback checks the state was issued to the same signed-in user within 15 minutes.
  3. It then queues the one-time code. The worker exchanges it for the channel's webhook URL and
     seals it, and the code is scrubbed from the outbox.
- **Alerts are queued by a trigger, only for tenants that want them.** A trigger on the timeline
  queues `integrations.lead_activity` only when the tenant has a connected, enabled integration,
  for:
  - a new lead's first inquiry;
  - a hold request;
  - a handoff.

  A handler fans each activity out, one delivery per integration, so each retries alone. A
  webhook Slack says is gone marks the connection failed, with the reason shown to the owner, and
  isn't retried.
- **What reaches Slack is escaped.** Buyers' words go to Slack with `&`, `<` and `>` escaped, so
  they can't form links or mentions. Alerts carry the buyer's name and message, not their email
  address.
- **`/lot`.**
  - **Signature:** Slack's v0 signature over the raw body is checked first, with a five-minute
    window. Bad or missing signatures get a 401 and are logged.
  - **Answer:** the lot's current status and price, from the database, visible only to the person
    who asked.
  - **Scope:** it covers every lot of the tenants connected to that workspace, unpublished ones
    included (marked as such), because the workspace is the owner's. It works whether or not
    alerts are switched on.
- **Locally, Slack can't finish an install** because Slack requires an HTTPS return address.
  `POST /v1/dev/integrations/slack` (local only) connects a tenant to a webhook made by hand in
  Slack's app settings, and from there the same handlers run.

## Alternatives considered

- **A Secret Manager secret per tenant:** the API would need rights to create secrets, and every
  delivery would pay a lookup. It's worth revisiting if a tenant ever needs a customer-managed
  key.
- **Exchanging the code in the callback request:** simpler, but it's a third-party call during a
  request, which CLAUDE.md rules out.

## Consequences

- Losing `INTEGRATIONS_KEY` means every tenant reconnects. It is required once Slack is
  configured outside local.
- Disconnecting forgets the webhook. Removing the app from the workspace is done in Slack.
- One Slack workspace can be connected to more than one tenant; `/lot` then searches all of
  them.
- Salesforce (P2-08) uses the same table, sealing and fan-out.

## Related

ADR-010 (outbox), ADR-012 (integrations), ADR-016 (free tiers first), ADR-021 (database
roles), ADR-024 (owners and staff have the same rights), ADR-035 (leads and handoffs)
