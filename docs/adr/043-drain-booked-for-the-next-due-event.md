# ADR-043: Each drain books the next one for when the next event is due

- **Status:** Accepted
- **Date:** 2026-10-07
- **Applies from:** the Phase 2 production fixes

## Context

In the cloud, a commit that queues outbox events creates a Cloud Task that drains the outbox
at once (ADR-029). Some events wait instead:
- the agent's follow-up, 15 minutes after a buyer's question (ADR-038);
- a send held until the buyer's quiet hours end;
- a failed event's retry, after a back-off of seconds up to an hour.

Nothing woke the API for them except Cloud Scheduler, which drains hourly to spare Neon's free
compute hours (ADR-032). On the Phase 2 production check, a follow-up due 15 minutes after the
buyer's question waited for the next hourly drain and went out at 12:07.

## Decision

- **After every cloud drain, the API books another for when the earliest waiting event is
  due.** It does this with a Cloud Task carrying a `scheduleTime`. A time already past (a drain
  that stopped with work left) is booked for now.
- **The task is named after its second**, set a second or two after the event is due to allow
  for clock skew. Drains that ask for the same wake-up therefore create it once, and Cloud
  Tasks' "already exists" counts as booked.
- **The hourly scheduled drain stays**, as the safety net for a booking that failed. Failing to
  book is logged, never an error to the caller.
- **Locally nothing changes.** The in-process runner already polls every second.

## Consequences

- A follow-up arrives within seconds of its due time, and retries follow their back-off.
- Neon wakes only when an event is actually due, so the free compute hours hold.
- Each drain makes one more Cloud Tasks call, well inside the free million a month.
- An event that keeps failing stops after eight attempts, as before, so bookings stop too.

## Later

- **2026-10-08:** events a migration queues (migration 0018's backfill) have no drain after
  them to book their wake-up, so they waited for the hourly sweep. The deploy now runs one drain
  after the new API is live. The deployer holds `roles/cloudscheduler.jobRunner` for that.

## Related

ADR-010 (outbox), ADR-023 (local runner), ADR-029 (Cloud Tasks), ADR-032, ADR-038
