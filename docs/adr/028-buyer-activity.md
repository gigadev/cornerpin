# ADR-028: Buyer activity: who may do what, consent capture and hold approval

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-08

## Context

P1-08 adds sign-up, saved lots, inquiry and hold request forms, consent capture and
notification preferences. ADR-015 says buyers inquire or request a hold, which the owner
approves; ADR-022 records consent per tenant, user and channel. Neither says whether a visitor
must sign in, what approving a hold does to the lot, or how a buyer may act on a lot their RLS
role can't see, since `cornerpin_user` sees only its own tenants' lots.

## Decision

- **Anyone may ask a question; everything else needs sign-in.** A signed-out visitor sends an
  inquiry with name, email, optional phone and message, behind Turnstile. Saving a lot, asking
  for a hold and giving contact consent need a signed-in, so verified, email address. Scott
  chose this on 2026-10-01. Anonymous inquiries carry their contact details on the row and no
  user, so no consent row ever belongs to an unverified address.
- **Consent is asked where the owner is known.** The contact form asks whether the owner may
  also email or text the buyer; voice waits for Phase 4. The boxes start from the buyer's current
  answer, and a row is added only for a channel whose answer changed, with the form as its
  `source` (`inquiry`, `hold_request`, or `account` from the account page). Replying to an
  inquiry needs no consent. Text messages need a phone number on the profile.
- **Only public lots.** Every buyer action looks the lot up as `cornerpin_public` first. The
  database checks it again on insert with `app_lot_is_public(lot)`, a security-definer function
  owned by `cornerpin_public`: it sees exactly what an anonymous visitor sees and returns only a
  boolean. Saved lots that are unpublished stay saved but drop out of the list until they are
  published again.
- **Holds.** Only an available lot can be held, and a buyer has at most one pending request per
  lot (a partial unique index). The owner approves or declines. Approving puts an available lot
  on hold in the same transaction, so the history trigger records it; a sold lot can't be
  approved. Scott chose this on 2026-10-01.
- **Profiles.** A signed-in user may change only their name, phone and time zone (a column
  grant); the email is the one they signed in with. A form fills an empty name or phone on the
  profile but never overwrites one. Phones are stored as E.164; without a leading `+` only US
  numbers are accepted.
- **Buyer state comes from the browser.** The lot page renders the same for everyone and never
  reads the session. The Save button and the contact form ask `/v1/me/lots/{id}` from the
  browser, so the page can be cached in P1-10 without holding anyone's data. The service worker
  must not cache `/v1/me/*` or `/account`.
- **Where buyers land.** Sign-in still defaults to `/app`; someone who manages nothing is sent
  on to `/account`. A signed-in buyer may read the name of a tenant they have answered for
  consent, so the account page can say who may contact them.
- **Owners see it in the portal.** "Inquiries and holds" lists both, newest first with pending
  holds on top, and shows which channels each buyer allows. The email to the owner is P1-09.

## Consequences

- An owner learns of a new inquiry only by opening the portal until P1-09 adds the email.
- An anonymous inquirer can't be followed up by the Phase 2 agent unless they later sign in
  and give consent; that is the point of requiring a verified address.
- The contact form needs JavaScript (Turnstile does anyway). Offline queueing is P1-10.

## Related

ADR-008 (sign-in), ADR-014 (outreach), ADR-015 (inquiries and holds), ADR-021 (policies),
ADR-022 (consent), ADR-027 (public pages)
