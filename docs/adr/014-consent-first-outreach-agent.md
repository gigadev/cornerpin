# ADR-014: The outreach agent is consent-first, tool-bound and evaluated

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** Phase 2 (email, then SMS); Phase 4 (voice, MCP server)

## Context

Following up on inquiries quickly matters, and an AI agent can do it, but it must not contact
people without consent or state things that are not true.

## Decision

- A Claude agent follows up on inquiries by email, SMS and later voice (Twilio).
- It can act only through tools: look up a lot, check availability, book a tour, log to the lead
  timeline, hand off to a human.
- Consent is captured per channel at sign-up, with a timestamp.
- Opt-outs are checked before every send.
- Quiet hours follow the recipient's time zone.
- An eval suite of scripted conversations checks lot facts, no invented prices, opt-out handling
  and handoff, and runs in CI.
- The same tools are exposed through an MCP server in Phase 4.

## Consequences

- SMS waits on carrier registration, so email ships first.

## Related

ADR-010 (runs from the outbox), ADR-016 (Twilio fees)
