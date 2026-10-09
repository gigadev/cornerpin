# ADR-051: The owner dashboard: Postgres views read as the owner, one hue, and a believable demo past

- **Status:** Accepted
- **Date:** 2026-10-09
- **Applies from:** P3-07

## Context

P3-07 gives each tenant a dashboard, read from Postgres (ADR-002), that works for Ricky's
tenant from day one. It covers:
- the funnel by stage, with conversion;
- sales pace: lots sold per month, and the median days from listing to sold by phase;
- inventory by status and phase;
- lead sources;
- outreach;
- the score distribution.

The plan left open:
- how the views respect tenancy;
- what "listed" means;
- how to show figures accessibly;
- how the demo gets a history worth charting, since its seed creates every lot already sold or
  on hold.

## Decision

- **Seven views in migration 0021, each `security_invoker`.** A view runs with the reader's
  rights, so the tables' row-level security applies exactly as if the owner queried them. A
  test reads every view as one tenant's owner and finds no other tenant's rows. The API route
  (`GET /tenants/{id}/dashboard`) also filters by `app_tenant_id()`.
- **What each figure is:**
  - **Funnel.** How far each lead got is the higher of its current stage and every stage it
    was moved to (`stage_changed` events), on the ladder new, contacted, engaged, holding,
    won. "Reached" counts leads that got at least that far. Conversion is reached ÷ the
    previous stage's reached. Lost is reported apart, as a current count.
  - **Sales by month.** Distinct lots with a move to "sold" in each calendar month, for the
    last 12 months, zeros included.
  - **From listing to sold.** For lots sold now, the median days from when the lot was added
    to Cornerpin to its latest sale, by phase. "Listed" means added to Cornerpin, because no
    publish date is kept; the page says so.
  - **Inventory.** Current lots by status, per phase.
  - **Sources.** Leads by their first touch.
  - **Outreach.** Messages sent, replies received, and handoffs to a person.
  - **Scores.** Open leads by their latest score's band (ADR-047's thirds), plus those not
    scored yet.
- **The page uses one hue and words throughout.** The validator showed the app's lot-status
  colours can't carry categories on their own: green and amber are 5.9 apart for protanopia.
  So nothing depends on telling colours apart:
  - funnel, sources and scores are single-series bars in the primary sage, each labelled with
    its words and number;
  - monthly sales are bars with an "As a table" view;
  - inventory and pace are tables.

  Every bar has a hover title. A tenant with nothing yet gets empty states and zeros, never
  errors.
- **The demo seed gets a past.** Phase 1 lots are listed 600 days ago and phase 2 120 days
  ago. The twelve sold lots' sales are spread over the past year, and the three holds fall in
  the last few weeks. This is written straight into the status and price history, not by
  re-saving lots, so no change notices are queued. Real tenants' history is their own.
- **Testing in two layers.** pytest checks every figure against independent queries on the
  raw tables. Playwright checks that the page shows exactly what the API returns, retrying
  until it sees a consistent snapshot, since other tests add leads and holds alongside it. Two
  e2e owners of the empty tenant, one per viewport, check the empty states.

## Consequences

- The dashboard is always live and needs no warehouse. The Snowflake models (P3-08, P3-09)
  reproduce the funnel and pace separately, and a reconciliation checks they agree.
- Each view is computed on every visit. That's fine at a subdivision's scale (tens of lots,
  hundreds of leads); a materialized view would be the step if that changed.
- "Listed" will be wrong for a lot added long before it went on sale. A publish date would fix
  that, but none is kept today.

## Related

ADR-002 (Postgres is the system of record), ADR-003 (RLS), ADR-047
