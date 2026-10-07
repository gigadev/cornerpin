# ADR-035: Leads, their stages, and what creates them

- **Status:** Accepted
- **Date:** 2026-10-06
- **Applies from:** P2-01

## Context

Phase 2 follows buyers up. The plan names `leads` and `lead_events` but not what a lead is,
what creates one, or its stages. Buyer activity is written as the buyer (or as
`cornerpin_public` for an anonymous inquiry), and neither may write an owner's data (ADR-021).
Anonymous inquiries carry an email nobody has proved (ADR-028).

## Decision

- **One lead per buyer per tenant, keyed by email.** A signed-in buyer's lead uses their
  verified address and carries their user id. An anonymous inquiry joins the lead for the
  address it typed, so the owner sees one history per person, but it never attaches a user:
  only a signed-in action does.
- **Activity creates and feeds leads:** an inquiry, a hold request, a hold's decision, and a
  consent change each add a timeline event, and create the lead if there isn't one. The lead's
  `source` is its first touch.
- **Triggers do it, in the same transaction.** They run as `cornerpin_leads`, a role that can
  only maintain leads and append events, so every code path, present or future, records the
  activity, and nothing else gains rights over owners' data. Existing activity was replayed in
  time order when the tables were created.
- **Stages:** new, contacted, engaged, holding, won, lost. An approved hold moves a lead to
  holding unless it is already won or lost. The outreach agent will move leads to contacted
  and engaged (P2-05); owners set any stage (P2-02). Every stage change is a timeline event
  with who made it.
- **The timeline is append-only.** Owners and staff may add notes, as themselves; nobody may
  edit or delete an event. Each event records whether the buyer side was verified: an
  anonymous inquiry's is not, and later tasks must not treat it as the buyer's own words or
  consent (the agent replies only on verified ground).
- **Owners and staff read their tenant's leads; buyers never see leads, including their own.**
  Buyers see their own activity, as before.

## Consequences

- A buyer who asks anonymously and later signs in with the same address has one lead.
- Someone can put an inquiry on another person's lead by typing their address. It is marked
  unverified, and consent comes only from signed-in actions, so it can't make anyone
  contactable.
- New kinds of activity add an event kind (an enum value) and a trigger or recorder function,
  owned by `cornerpin_leads`.

## Related

ADR-021 (database roles), ADR-022 (consent per tenant), ADR-028 (buyer activity),
ADR-014 (outreach agent)
