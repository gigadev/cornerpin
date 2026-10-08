# ADR-047: Scores in the portal, and decisions logged with the score the owner saw

- **Status:** Accepted
- **Date:** 2026-10-08
- **Applies from:** P3-03

## Context

ADR-013 makes scores advisory and puts a person behind every decision. ADR-045 created the
`decisions` table and left writing it to P3-03. Three questions remained:
- where owners see a score;
- how it's labelled;
- how a decision records *the score the owner saw* rather than whatever is newest when the
  request arrives.

## Decision

- **Where scores show:**
  - the lead list, as a badge;
  - each pending hold on Inquiries and holds, as a badge with a "Why this risk?" link to the
    lead;
  - the lead page, as a panel with every reason.

  Won and lost leads show none, since they aren't scored (ADR-045).
- **How it reads:**
  - "Risk of falling through", marked **Advisory**;
  - a band (low below a third, high above two thirds) and a percentage;
  - each reason with whether it raised or lowered the risk;
  - a line saying where it came from, for example "a model (lead-v1) trained on synthetic
    data", and that the owner makes the decision.

  The bands use the theme's status colours, green to amber to red. They signal attention, not
  a verdict.
- **The client names the score it showed.** Deciding a hold and changing a stage send the
  `score_id` on screen. The API checks it belongs to that lead, refusing it with 422
  otherwise, and logs it. A decision made with no score on screen is logged with none, so the
  log never claims the owner saw a score they didn't.
- **What counts as a decision:**
  - approving or declining a hold;
  - marking a lead won or lost, only when the stage actually changes to it.

  Other stage changes stay ordinary timeline events.
- **Decisions appear on the timeline as their own entries**, sorted with the lead's events and
  just above the event they caused. Each shows:
  - what was decided, and on which lot for a hold;
  - who decided, and when;
  - the risk shown, with its top three reasons.

  They are kept apart from the hold and stage events the triggers write, because those don't
  know about scores.
- **The decisioning module owns its tables.** The lead and hold routes get scores through
  `latest_score_sql`, and record decisions through `decisions.record`, from
  `cornerpin.decisioning.decisions`. They never touch `risk_scores` or `decisions` directly.

## Consequences

- An owner's decision and the advice in front of them are tied together for later review,
  which is the point of ADR-013.
- A page left open shows an older score than the newest. The log records the older one, which
  is what the owner saw.
- Scores are written in the background, so a brand-new lead may show "Not scored yet" for a
  second or two.

## Related

ADR-013, ADR-035 (leads), ADR-045, ADR-046
