# ADR-045: Decisioning: what a score is, what it may look at, and where it's kept

- **Status:** Accepted
- **Date:** 2026-10-07
- **Applies from:** P3-01

## Context

ADR-013 says every tenant gets a lead and deal score, the likelihood an inquiry or hold falls
through, with reason codes, and that a person makes every decision. It leaves open:
- what the score is on;
- which facts it may use;
- where scores and decisions are kept;
- when scoring runs.

The model (P3-02) and its own service (P3-04) come later, so the portal and the tables need a
contract that holds before the model exists.

## Decision

- **A score is a lead's risk of falling through**, from 0 to 1, where higher means more likely
  to fall through. It is shown as advice, never acted on automatically.
  - Each score is stored with:
    - its model version;
    - the exact inputs it saw;
    - its reasons, each with a code, plain words and a signed weight (positive raises the
      risk).
  - Scores are append-only. A new score is written only when the inputs or the model version
    differ from the lead's latest, so the history shows real changes.
- **Leads now; holds and financing applications later.** `risk_scores` and `decisions` always
  carry the lead, plus the hold where it applies. P3-05 adds the financing application the
  same way. These are real foreign keys, not a polymorphic id, so a score can't outlive or
  miss its subject.
- **The features come from the lead's own history and the lot it asked about, nothing else:**
  - `stage`;
  - `touches`, the messages sent to the buyer;
  - `replies`, verified replies from the buyer;
  - `hold_requests`;
  - `hold_approved`;
  - `days_since_first_contact`;
  - `days_since_buyer_activity`, counting verified inquiries, hold requests and replies;
  - `opted_out` (email);
  - `lot_price_band`, where the lot's price sits among its subdivision's lots: low, mid or
    high;
  - `listing_type`;
  - `phase_release`.

  Unverified activity (an anonymous inquiry) doesn't count as the buyer's own (ADR-035).
- **Excluded, and checked by a test:** anything about the person. That means name, email
  address or domain, phone, address, location, time zone, IP, device, and the words they
  wrote. It also means anything that could stand in for a protected class (ADR-013). A lot's
  price band describes the property, not the buyer. The test lists the allowed features and
  fails when one is added, and fails on any feature whose name looks personal.
- **`rules-v1` is the baseline scorer.** It starts at 0.5 and adds plain-word reasons, for
  example:
  - replied: lowers the risk;
  - asked to hold a lot: lowers it;
  - several messages with no reply: raises it;
  - quiet for a month: raises it;
  - opted out: raises it.

  It sits behind a `Scorer` interface: features in, a score with reasons out. The LightGBM
  model (P3-02) and the decisioning service (P3-04) implement the same interface.
- **Won and lost leads aren't scored.** The question no longer applies.
- **Scoring runs from the outbox, never during a request.** A trigger on `lead_events`, owned
  by `cornerpin_leads` like the integrations trigger, queues `decisioning.score_lead` for:
  - inquiries;
  - hold requests and their decisions;
  - consent changes;
  - stage changes;
  - messages sent and received.

  Every tenant is scored, Ricky's included. The rules baseline makes no outside call, so there
  is nothing to switch on. The migration queues every open lead once, so existing leads get a
  first score. Those events wait ten minutes, because a deploy migrates before the new API
  revision serves, and the old revision has no handler for them: it would use up their
  retries.
- **The features are read with SQL from the leads tables in the worker's session**, as the
  integrations module does (ADR-040). This bends ADR-011's "never through each other's
  tables". It's kept read-only and in one function, `lead_features`. When scoring moves to its
  own service, the service receives these features and never reads the tables.
- **`decisions`** record who decided what about which lead or hold, when, and which score they
  saw. They are append-only, written by an owner or staff member as themselves, and never by
  the worker. P3-03 writes them. P3-01 creates the table, its policies and the proof that it
  can't be edited.

## Consequences

- The portal (P3-03) can show scores before any model is trained, and swapping in the model
  changes the version on new scores, not the shape.
- Re-scoring is driven by the timeline. A lead that goes quiet keeps its last score until
  something happens; an aging score is a later task's concern, perhaps the dashboard's.
- The feature list is the place to argue about fairness. Changing it means changing the test
  and this ADR.
- Changing consent and declining a hold now wake the outbox, which they didn't need to before.

## Related

ADR-011 (modules), ADR-013 (advisory decisioning), ADR-035 (leads, verified activity),
ADR-040 (the integrations trigger pattern), ADR-043
