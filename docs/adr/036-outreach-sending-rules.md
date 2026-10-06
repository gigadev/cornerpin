# ADR-036: Outreach sending rules: consent, quiet hours, caps and unsubscribing

- **Status:** Accepted
- **Date:** 2026-10-06
- **Applies from:** P2-03

## Context

ADR-014 says outreach needs recorded consent per channel, honours opt-outs before every send,
respects quiet hours in the recipient's time zone and logs every send. It doesn't say what the
hours are, how often a buyer may hear from an owner, what happens to a message that can't go
yet, or how a buyer stops it. The email provider's free plan allows 100 emails a day, shared
with sign-in links and alerts.

## Decision

- **Sends happen only in an outbox handler.** Asking for a send records an `outreach_messages`
  row (`queued`) and queues its delivery in the same transaction, so every message has a row
  whatever happens to it.
- **Every check happens when the message goes, not when it was asked for:**
  1. **Consent:** the latest consent row for that owner, buyer and channel must grant it. No
     row is `no_consent`; a withdrawn one is `opted_out`. An anonymous inquirer can't consent
     (ADR-028), so is never contacted.
  2. **Quiet hours:** messages go between 9:00 and 20:00 in the buyer's time zone, or the time
     zone of the subdivision they last asked about, or America/Boise. Outside those hours the
     message isn't refused: its delivery is queued again for 9:00.
  3. **Caps:** at most 2 sends to one buyer and 40 from one owner in any 24 hours. Over a cap
     the message is refused (`lead_daily_cap`, `tenant_daily_cap`), not delayed, so the agent
     never piles up a backlog.
- **Refusals are recorded** with their reason. Sent and refused messages appear on the lead's
  timeline.
- **A delivery is idempotent.** A message that is no longer `queued` is skipped, so a retried
  event never sends twice. A failed send stays `queued` and the outbox retries it with back-off.
- **Every outreach email says who is writing and why, and how to stop**, and carries one-click
  unsubscribe headers (RFC 8058), which Gmail and Yahoo expect. The link is signed (HMAC with the
  app's secret), names one owner, buyer and channel, and works for five years without signing
  in. Opening it only shows a page, because mail scanners open links; the page's button, or a
  mail provider's one-click POST, appends a consent row withdrawing that channel, with source
  `unsubscribe`.
- **Replies** go to the owner's address until Cornerpin reads replies itself (P2-04).
- **Channels are adapters** behind one interface. Email is the only one until SMS (P2-09); a
  message on a channel without an adapter is refused as `channel_unavailable`.

## Consequences

- A burst of activity can't exhaust the shared email allowance through outreach alone.
- Quiet hours apply to email too, which the law doesn't require; it's what a buyer would expect
  from an owner.
- `/unsubscribe` is a reserved address: no subdivision may use it.
- A send that fails eight times stays `queued` with the outbox's last error; nothing alerts on it
  yet.

## Related

ADR-014 (outreach agent), ADR-022 (consent per tenant), ADR-028 (buyer activity), ADR-029
(notifications and the task runner), ADR-035 (leads)
