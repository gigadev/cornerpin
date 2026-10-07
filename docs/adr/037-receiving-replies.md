# ADR-037: Receiving replies to outreach

- **Status:** Accepted
- **Date:** 2026-10-06
- **Applies from:** P2-04

## Context

The outreach agent (P2-05) needs a buyer's replies, and the owner should see them on the lead.
Until now outreach replied to the owner's own address, which Cornerpin never sees. The plan left
the inbound path open, and whether it fits Resend's free plan. Resend's pricing lists inbound
email on every plan, the free one included. Its `email.received` webhook carries only metadata
(sender, recipients, subject, an id); the body is fetched from `GET /emails/receiving/{id}`.
Webhooks are signed by Svix. The API is private (ADR-032), so anything from outside reaches it
through the web app's `/v1` proxy.

## Decision

- **Replies go to a subdomain**, `reply.cornerpin.app` in production, whose MX points at Resend.
  Mail to `cornerpin.app` itself is untouched.
- **Each outreach email replies to `reply+<message id><mac>@<domain>`.** The address names the
  message it answers, so the reply lands on that lead even if the buyer writes from another
  address; the 16-hex-character HMAC (keyed with the app secret) means nobody can make up an
  address that lands on someone's lead. It fits the 64-character limit, in lowercase.
- **The webhook is `POST /v1/webhooks/resend`.** It checks the Svix signature over the raw body
  (five minutes' tolerance), rejects and logs anything unsigned or badly signed (401), and
  queues the email's metadata. It is dormant (404) until `RESEND_WEBHOOK_SECRET` is set. The
  proxy forwards the `svix-*` headers.
- **The handler does the rest, in the background:** it fetches the body from Resend (the HTML
  as text when there's no text part), keeps only what the buyer wrote (dropping quoted history
  and "Sent from my phone"), and records an inbound `outreach_messages` row. Resend's email id
  makes a retried webhook a no-op. The buyer's words are removed from the outbox payload once
  recorded.
- **A reply to an address that isn't ours, or doesn't match a sent message, is logged and
  dropped.**
- **A reply goes on the timeline**, verified only when it came from the lead's own address; one
  from elsewhere (a spouse, a forward) is kept but marked unverified. It makes the lead
  `engaged` (from new or contacted) and queues `outreach.reply_received` for the agent.
- **Locally**, `INBOUND_EMAIL_DOMAIN` alone turns reply addresses on, and
  `POST /v1/dev/inbound-email` plays the provider through the same handler. It doesn't exist
  outside local.
- **Outside local, an inbound domain needs `RESEND_WEBHOOK_SECRET` and `RESEND_API_KEY`**, or the
  API refuses to start.

## Consequences

- Without the domain configured, nothing changes: replies go to the owner, as before.
- Going live needs an MX record for `reply.cornerpin.app` at GoDaddy, the Resend webhook, and the
  secret in Secret Manager (P2-10).
- Resend's documentation doesn't say whether received email counts towards the free plan's 100
  emails a day; check the dashboard's usage after the first replies.
- Attachments are ignored for now.

## Related

ADR-012 (optional integrations), ADR-014 (outreach agent), ADR-032 (production deployment),
ADR-035 (leads), ADR-036 (sending rules)
