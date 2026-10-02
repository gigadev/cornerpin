# ADR-029: Notifications, the task runner and web push

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-09

## Context

P1-09 sends the owner an email for each inquiry, emails savers when a lot's status or price
changes, and adds web push. The acceptance is exactly one email per saver for a status change.
ADR-010 says a dispatcher turns outbox rows into Cloud Tasks that call `/internal` handlers; it
doesn't say how a retry avoids repeating sends, who reads recipients' addresses (buyers can't see
owners and owners can't see buyers), how Cloud Tasks calls are authenticated, or when push is on.

## Decision

- **Lot changes are queued by the database.** A trigger on `lots` queues `listings.lot_changed`
  when status or price changes, in the same transaction, like the history rows. No code path can
  change a lot without savers hearing about it.
- **Fan out, then send.** An event about something that happened (an inquiry, a hold request, a
  lot change) is handled by queuing one event per recipient: each owner or staff member, each
  saver who wants email, each push subscription of savers who want push. Each of those sends one
  message. A failed send retries for that recipient alone, so a retry never repeats a send that
  already succeeded. Delivery is at least once: a crash between sending and recording it can
  repeat one message.
- **Handlers get the worker's session**, inside a savepoint per event, and read what they need
  at send time: recipients, preferences, and whether the lot is still public. Nothing is sent
  about a lot the public can't see. Events carry ids, not buyers' messages or addresses. The
  worker role gains read access to those tables for this, and nothing else beyond removing dead
  push subscriptions. Modules read each other's data through small functions (`listings.notices`,
  `leads.notices`, `core.directory`), not each other's tables (ADR-011).
- **Owner emails** go to every owner and staff member of the tenant, with Reply-To set to the
  buyer so a reply reaches them. The email says when an address wasn't verified.
- **Saved-lot emails** say what changed and link to the lot and to the account page, where alerts
  can be turned off. They are plain text.
- **Dispatch.** After a commit that queued events from Python, the dispatcher is told. Locally the
  in-process runner wakes at once (it also polls every second, which picks up trigger-queued
  events). With `OUTBOX_RUNNER=cloudtasks`, it creates a Cloud Task that POSTs to
  `/internal/outbox/drain` with an OIDC token for the tasks service account. Cloud Scheduler calls
  the same endpoint every minute for retries and trigger-queued events, and
  `/internal/housekeeping` daily. `/internal/*` checks the Google-signed token's audience and
  service account, and is a 404 until the cloud settings exist. Concurrent drains are safe.
- **Housekeeping** deletes sign-in tokens and sessions a day after they expire, and processed
  outbox events after 30 days. Failed events stay for inspection.
- **Web push** is dormant until `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` are set. The dev
  command `uv run python -m cornerpin.devtools vapid-keys` makes a pair. A signed-in buyer turns
  alerts on per device on the account page; that also sets their push preference. Subscriptions
  must point at a known browser push service (FCM, Mozilla, Apple, Windows), so the worker never
  posts anywhere else. A 404 or 410 from the push service removes the subscription. Signing out
  unsubscribes the device. The service worker shows the notification and opens only same-site
  URLs. The `pywebpush` library sends.

## Consequences

- An approved hold changes the lot to On hold, so savers hear about it like any other change.
- Saved-lot alerts can take up to a minute in the cloud, where trigger-queued events wait for the
  scheduled drain. Sign-in links and owner emails are dispatched immediately.
- Push works only where the service worker runs: production builds, and on iPhone only once the
  app is installed (ADR-005).
- P1-12 provisions the queue, the service account, the Scheduler jobs and the VAPID keys.
  Cloud Tasks (first million operations a month) and Cloud Scheduler (three jobs) are within
  their free tiers at this traffic.

## Related

ADR-005 (PWA), ADR-010 (outbox), ADR-011 (modules), ADR-021 (roles), ADR-023 (first outbox),
ADR-028 (buyer activity)
