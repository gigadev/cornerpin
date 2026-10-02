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

## Phases 2–4 (outline; tasks are written when each phase starts)

**Phase 2** — lead pipeline and timeline; outreach agent with tools and consent checks, email first; eval suite in CI; Slack alerts and `/lot`; Salesforce lead and status sync; SMS once registration clears.

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
