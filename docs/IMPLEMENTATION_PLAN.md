# Cornerpin — Implementation Plan

Oct 1, 2026 · Scott Shepherd

## How to use this doc

This is the working plan for Claude Code. `CLAUDE.md` at the repo root and the ADRs in [`docs/adr/`](adr/README.md) are canonical; if this plan disagrees with them, they win.

**Ground rules**

1. Build and verify locally first; deploy at the end of Phase 1 and keep production current from then on (ADR-009).
2. Scott controls git. Each task ends with a summary and a proposed conventional-commit message.
3. One task at a time; each is sized for a single session and ends with lint, tests and build green.
4. Free tiers first; state the cost before enabling anything paid (ADR-016).

## Roadmap

Hours are rough solo estimates with Claude Code doing most of the typing.

| Phase | Hours | Delivers | Gate to leave it (a real user can…) |
| --- | --- | --- | --- |
| 1 Listings | 40–55 | tenants, lots, map, photos, public pages, sign-up, notifications, PWA, live deploy | scan a lot sign, install the app, save a lot and get an email when Ricky marks it sold |
| 2 Leads + outreach | 35–45 | lead pipeline, outreach agent (email, then SMS), evals, Slack, Salesforce | opt in on the demo tenant and be followed up by the agent, with the lead showing in Slack and Salesforce |
| 3 Risk + warehouse | 40–50 | Snowflake events, lead/deal score, financing demo module, owner dashboard | see a scored lead with reason codes, and walk a synthetic financing application to a logged decision |
| 4 Voice + reach | 30–40 | voice outreach, Zoom tours, Gmail threads, MCP server | book a Zoom tour from a lot page, and ask Claude about availability through MCP |

A gate is passed on the production URL. The next phase does not start until then.

## Data model (Phase 1)

| Table | Holds |
| --- | --- |
| `tenants`, `users`, `memberships` | owner organizations, global users, roles (owner, staff) |
| `subdivisions` | name, slug, location point, boundary polygon, time zone, description, published flag |
| `phases` | name, order, release status, per subdivision |
| `lots` | number, phase, boundary polygon, acreage, price, status, listing type (land-only or lot + home), home details, published flag |
| `lot_status_history`, `lot_price_history` | who changed what and when |
| `lot_media`, `lot_documents` | photos with order and caption; plat, survey, covenants, utilities |
| `saved_lots`, `inquiries`, `hold_requests` | buyer activity |
| `contact_consents` | per user, per channel, with timestamp and source |
| `notification_prefs`, `push_subscriptions` | what each user wants and where to send it |
| `qr_codes` | stable code → lot |
| `outbox` | events awaiting background dispatch |

Later phases add `leads`, `lead_events`, `outreach_messages`, `risk_scores`, `integration_connections` and the financing tables.

## PWA behaviour (ADR-005)

| Concern | Behaviour |
| --- | --- |
| Install | per-subdivision manifest, scope `/{slug}/`; owner portal manifest, scope `/app/` |
| Offline lots | lot summaries for a subdivision precached on first visit; viewed lot pages served stale-while-revalidate |
| Photos | cache-first with an entry cap |
| Map | viewed tiles cached within the tile provider's terms; lot polygons come from the cached summaries |
| Inquiry form | queued and sent when the connection returns |
| Private data | authenticated and `/app` responses are never cached |
| Updates | new version prompts for reload |
| Push | saved-lot alerts for installed users; email remains the default |

## Bootstrap (day zero)

**Scott**

- [x] Folder `C:\git\github\cornerpin` created; domain `cornerpin.app` registered.
- [ ] `git init` and the GitHub repo.
- [x] Frontend framework confirmed: Next.js (ADR-004).
- [ ] Docker Desktop, Node, pnpm, Python and uv installed.
- [ ] Ask Ricky for the plat or survey file and its format.

Cloud accounts (Google Cloud, Neon, Resend, Twilio, Salesforce Developer Edition, Slack, Zoom, Snowflake) are Scott's to create, each when its task comes up.

## Phase 1 tasks

| Task | Scope | Acceptance |
| --- | --- | --- |
| P1-01 Scaffold | pnpm workspace; `apps/api` (FastAPI hello, uv, ruff, pyright, pytest); `apps/web` (Next.js, TS strict, Tailwind, manifest, empty service worker); docker compose with PostGIS and Mailpit; CI workflow written | lint, test, build green; web shell renders at 390 px and 1280 px with a valid manifest |
| P1-02 Schema + RLS | Phase 1 tables, policies, non-owner API role, seed with a synthetic subdivision | cross-tenant read test returns 0 rows for every tenant-owned table |
| P1-03 Auth | magic link, Google (dormant), sessions, Turnstile, memberships | sign in through Mailpit; an owner cannot reach another tenant's portal |
| P1-04 Owner portal | subdivision, phase and lot CRUD; status and price changes with history | Playwright: create a lot, change status, see the history |
| P1-05 Media | photo and document upload behind a storage interface (local disk, Cloud Storage) | upload, reorder and caption photos; documents download |
| P1-06 Lot geometry | draw and edit lot polygons on the map; GeoJSON import; optional plat image overlay | a drawn lot round-trips through PostGIS and renders on the public map |
| P1-07 Public pages | subdivision page with map coloured by status; lot list and filters; lot detail with price, status, photos, documents and a directions link; SSR and link previews; GraphQL | pages render without JavaScript; unpublished lots never appear |
| P1-08 Buyer features | sign-up, saved lots, inquiry and hold request forms, consent capture, notification preferences | inquiry reaches the owner; consent rows carry channel and timestamp |
| P1-09 Notifications | outbox, task runner, email to owner on inquiry, email to savers on status or price change, web push | status change produces exactly one email per saver, visible in Mailpit |
| P1-10 PWA | caching rules above, offline fallback, queued inquiry, update prompt | installable; a viewed lot opens offline; no `/app` response in any cache |
| P1-11 QR codes | `/q/{code}` redirect and a printable sign sheet per lot | scanning a printed code opens the right lot after a slug rename |
| P1-12 Deploy | Terraform, Cloud Run, Neon, Cloud Storage, `cornerpin.app`, CI deploy, demo tenant seed | production URL serves the demo subdivision; Ricky's tenant created |

Twilio SMS registration is started during Phase 1 because approval takes days to weeks; it has fees, so ADR-016 applies.

## Phase 2 tasks

Written 2026-10-02, when Phase 1 reached production. Phase 2 starts once the Phase 1 gate has
been walked on cornerpin.app.

| Task | Scope | Acceptance |
| --- | --- | --- |
| P2-01 Leads schema | `leads` (one per tenant and buyer: stage, source, notes), `lead_events` (the timeline: inquiry, hold, consent change, message, stage change, handoff), `outreach_messages` (every send and reply, with channel and provider id), `integration_connections` (per-tenant adapter settings); RLS forced with policies in the same migration; an inquiry or hold request creates or updates the lead and its event in the same transaction; an ops command backfills production's existing inquiries and holds | cross-tenant read returns 0 rows for every new table; an inquiry from a consented buyer shows as a lead with a timeline event |
| P2-02 Leads in the portal | "Leads" list by stage with filters; a lead page with the timeline, consent per channel, notes and stage changes; a "needs a human" inbox for handoffs | Playwright: an inquiry appears as a lead; the owner changes its stage and sees it on the timeline |
| P2-03 Outreach core | `outreach` module: a channel adapter interface, email first (the Phase 1 backend); before every send: current consent for that channel, opt-out, quiet hours in the recipient's time zone (the subdivision's when unknown), and per-lead and per-tenant daily caps; every send written to `outreach_messages`; an unsubscribe link that appends an opt-out consent row; sends happen only in outbox handlers | tests: no send without consent; a send in quiet hours waits for the next window; after an opt-out the next send is refused and logged as refused; every send has a row |
| P2-04 Replies on the timeline | inbound email from buyers lands on the lead timeline: a signed provider webhook under `/webhooks`, matched to the lead by a token in the reply address; outreach email carries that reply-to; locally a dev route feeds the same handler | a signed webhook appends the reply to the right lead; an unsigned or unknown one is rejected and logged; a reply triggers the agent (P2-05) |
| P2-05 Outreach agent | the Claude agent in `outreach`, with tools `lookup_lot`, `check_availability`, `request_tour` (logs and hands off until Zoom arrives in Phase 4), `log_timeline` and `handoff_to_human`; runs only in outbox handlers, never during a request; first follow-up to a consented lead after a delay, then one turn per reply; stops on opt-out, handoff, won or lost, or a touch cap; the prompt states only facts read through tools and hands off when unsure; dormant until `ANTHROPIC_API_KEY` is set | on the demo tenant a consented inquiry produces a follow-up in Mailpit quoting the lot's real price; every tool call is on the timeline; with no key, nothing runs |
| P2-06 Eval suite | `evals/`: scripted conversations with checks for lot facts, invented prices, opt-out handling, handoff and quiet hours; a runner that reports cost; CI runs it on every PR (how, without spending on every push, is an ADR) | a planted regression (an invented price) fails the suite; the real-model run passes locally; CI is green on main |
| P2-07 Slack | `integrations.slack` adapter behind the ADR-012 interface, enabled per tenant from the portal; alerts for a new lead, a hold request and a handoff; `/lot <subdivision> <number>` answering status and price; request signatures checked | on the demo tenant a new inquiry posts to the channel; `/lot` answers with the current price; a bad signature is rejected; a tenant without Slack sends nothing |
| P2-08 Salesforce | `integrations.salesforce` adapter on Developer Edition with server-to-server auth; a lead becomes a Salesforce Lead on creation, stage changes set its status, an approved hold opens an Opportunity; lot status and price sync; idempotent through external ids, retried from the outbox | on the demo tenant a new lead appears in Salesforce after one drain; a stage change syncs; a failed call retries without a duplicate |
| P2-09 SMS | Twilio adapter for the outreach channel: sends only with SMS consent and a phone on the profile; STOP, START and HELP handled by a signed webhook that appends consent rows; quiet hours apply; starts after 10DLC registration clears (ADR-016) | with Twilio's test credentials an SMS follow-up is logged; STOP appends an opt-out row and blocks the next send; a buyer without a phone gets email only |
| P2-10 Live + gate | Terraform and `set-secrets.sh` for the new secrets; the demo tenant connected to Slack and Salesforce; budget check; docs (TEST_ACCOUNTS, WALKTHROUGH, DEPLOY, `/help`); the gate walked on cornerpin.app | opt in on the demo tenant and be followed up by the agent, with the lead showing in Slack and Salesforce |

**Order.** P2-01 → P2-02. P2-03 → P2-04 → P2-05 → P2-06. P2-07 and P2-08 need only P2-01 and
can be slotted in anywhere. P2-09 waits for Twilio and can land whenever registration clears.
On 2026-10-06 Scott deferred P2-09 to avoid Twilio's fees for now: Phase 2 ships email-only
outreach, and P2-10 goes ahead without it.
P2-10 is last.

**Costs (ADR-016).** Slack and Salesforce Developer Edition are free. The Claude API is pay as
you go, likely a few dollars a month at demo volume; the key goes in only after a yes, before
P2-05. Twilio registration (one-time, roughly $20–60) plus about $5–15 a month needs a yes
before it starts, and it takes weeks to clear, so it should start at the beginning of the phase
if SMS is wanted in it. Whether inbound email is on Resend's free tier is checked in P2-04.

**Decisions this phase will need (one ADR each).** What creates a lead and its stages; the
follow-up cadence and caps; the model, prompt and tool contract; how evals run in CI without
spending on every push; the inbound email path; where per-tenant integration credentials live;
the 10DLC campaign details.

## Phases 3–4 (outline; tasks are written when each phase starts)

**Phase 3** — outbox events exported to Snowflake; SQL models for funnel and sales pace; lead/deal score with reason codes and a decision log; decisioning split into its own service; financing demo module on synthetic data; owner dashboard. The Snowflake trial starts here, not before.

**Phase 4** — voice outreach through Twilio; Zoom tour booking; Gmail thread sync onto the lead timeline; MCP server exposing the agent's tools.

## Expected running costs

Approximate and unverified; each is checked against the provider's pricing page in the task that enables it.

| Service | To start | Once live |
| --- | --- | --- |
| Cloud Run | free tier | about $0 at this traffic |
| Neon Postgres | free tier | $0 until it outgrows the free tier, then roughly $5–20/mo |
| Cloud Storage | free tier | under $1/mo |
| Domain | registered | about $12–15/yr |
| Email (Resend) | free tier | $0 at this volume |
| Map tiles | free tier | $0 at this volume |
| Twilio | trial credit | about $5–15/mo plus one-time registration of roughly $20–60 |
| Claude API | pay as you go | likely a few dollars a month; to be measured |
| Salesforce Developer Edition, Slack, Zoom, Gmail APIs | free | free |
| Snowflake | 30-day trial | roughly $10–30/mo if the warehouse suspends when idle |

## Open items

- Ricky's plat or survey file; until it arrives, development uses a synthetic subdivision.
- Brand: wordmark, colours, typeface.
- Sending domain DNS for email, and the business details Twilio registration needs.
