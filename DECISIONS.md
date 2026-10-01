# Cornerpin — Architecture Decision Records

One paragraph each: context, decision, consequence. Add a new ADR rather than editing an old one; mark superseded ones.

## ADR-001 · Name Cornerpin, domain cornerpin.app
Named for the survey pins that mark a lot's corners. Scott registered `cornerpin.app` on 2026-10-01. Repo and folder `cornerpin`. Consequence: `.app` is on the HSTS preload list, so every environment that uses the domain must serve HTTPS.

## ADR-002 · FastAPI is the API; Postgres + PostGIS is the system of record
The target stack is Python, SQL and REST/GraphQL, and lot boundaries are polygons. FastAPI with SQLAlchemy 2, GeoAlchemy2 and Alembic sits on Postgres with PostGIS. Consequence: geometry and distance queries live in SQL; Snowflake (ADR-012) is analytics only and never serves a page.

## ADR-003 · Tenancy = organizations, isolated by row-level security
A tenant is an owner organization; it owns subdivisions, which own phases, which own lots. Users are global and join tenants through `memberships` with a role (owner, staff). Buyers are users with no membership. The API connects as a non-owner role and sets `app.tenant_id` and `app.user_id` with `SET LOCAL` per transaction; RLS is enabled and forced on every tenant-owned table. Consequence: a bug in a query cannot leak another tenant's rows; every such table ships with its policies and a cross-tenant test.

## ADR-004 · Next.js (App Router, TypeScript) for the web app
Public lot pages must be server-rendered for search and link previews, and the job posting asks for "modern JS/TS" without naming a framework. Levelward already shows Angular; Next.js shows range and has SSR built in. Angular SSR was the alternative; Scott chose Next.js on 2026-10-01. Consequence: Tailwind + shadcn/ui, Vitest, Playwright, MapLibre GL; the service worker is built with Serwist.

## ADR-005 · The web app is a PWA built for use on site
Buyers will open a lot page from a QR code on a sign, often with weak signal. The app is installable, precaches a subdivision's lot summaries on first visit, serves previously viewed lot pages and photos offline, and queues an inquiry until the connection returns. Web push is offered for saved-lot alerts; email stays the primary channel because iOS only allows push for installed apps. Each subdivision has its own manifest (id and scope `/{slug}/`); the owner portal has its own (`/app/`); one service worker at the root serves both. Consequence: the service worker never caches authenticated or owner-portal responses, and the owner portal is online-only in v1.

## ADR-006 · Path-based public URLs on one origin
Public pages are `cornerpin.app/{subdivision-slug}` and `/{subdivision-slug}/lots/{lot-number}`; the owner portal is `/app`. Slugs are globally unique with a reserved-word list. Sign QR codes point at `/q/{code}`, a stable redirect, so a printed sign survives a rename. Wildcard subdomains and custom domains need a load balancer and are deferred. Consequence: one certificate, one service worker, no per-tenant DNS.

## ADR-007 · REST for writes, GraphQL for public reads
The owner portal, forms, webhooks and internal task handlers use REST under `/v1` with an OpenAPI schema. Public browsing (subdivision, lots, map, filters) uses GraphQL (Strawberry), read-only, called server-side by Next.js and over GET from the client so responses can be cached. Consequence: two schemas to keep typed, each used where it fits; no GraphQL mutations.

## ADR-008 · Passwordless auth owned by the API
Magic link plus Google sign-in; sessions are httpOnly cookies; Cloudflare Turnstile guards sign-up, magic-link requests and public forms. No password provider. Consequence: no password field ever; Google sign-in stays dormant until a client id exists.

## ADR-009 · Cloud Run + Neon + Cloud Storage, built locally first
The job posting asks for cloud deployment and a live link, and names no cloud. Cloud Run and Neon both scale to zero, so a low-traffic production site costs close to nothing. API and web are separate Cloud Run services; Postgres is Neon with PostGIS; photos and documents are in Cloud Storage; Terraform and GitHub Actions define and deploy it. Development runs entirely on the dev machine with Docker. Consequence: gate 1 is passed on the production URL, not locally; cold starts of a second or so are accepted.

## ADR-010 · Transactional outbox and Cloud Tasks for background work
A state change writes an `outbox` row in the same transaction. A dispatcher turns rows into Cloud Tasks that call `/internal` handlers on the API; locally an in-process runner does the same. Notifications, integrations, outreach and scoring all run there. Consequence: no third-party or model call happens during a request; a failed side effect retries without losing the event.

## ADR-011 · Modular monolith with service boundaries drawn now
`listings`, `leads`, `notifications`, `outreach`, `decisioning` and `integrations` are modules in one API container. Modules talk through function interfaces and the outbox, never through each other's tables. Decisioning moves to its own Cloud Run service in Phase 3, when the ML dependencies would otherwise bloat the API image. Consequence: one deployable until there is a reason for two.

## ADR-012 · Integrations are per-tenant, optional and dormant without credentials
Salesforce (inquiries as Leads/Opportunities, lot status sync), Slack (alerts and a `/lot` lookup), Gmail (inquiry threads on the lead timeline), Zoom (virtual lot tours) and Snowflake (event warehouse feeding features and dashboards). Each is an adapter behind an interface, enabled per tenant, exercised in the demo tenant. Consequence: Ricky's tenant runs with none of them configured.

## ADR-013 · Risk decisioning is advisory, logged and explainable
Every tenant gets a lead and deal score: the likelihood an inquiry or hold falls through, with reason codes. The owner-financing module (application, decision, loan, schedule, payments, delinquency) exists only in the demo tenant on synthetic data, because Ricky does not offer financing and real credit decisions carry fair-lending and adverse-action obligations. Models are gradient-boosted trees; every score is stored with model version, inputs and reasons; a human makes every decision. Consequence: no protected-class attributes or obvious proxies as features; no automated approval or denial.

## ADR-014 · The outreach agent is consent-first, tool-bound and evaluated
A Claude agent follows up on inquiries by email, SMS and later voice (Twilio). It can only act through tools: look up a lot, check availability, book a tour, log to the lead timeline, hand off to a human. Consent is captured per channel at sign-up with a timestamp; opt-outs are checked before every send; quiet hours follow the recipient's time zone. An eval suite of scripted conversations checks lot facts, no invented prices, opt-out handling and handoff, and runs in CI. The same tools are exposed through an MCP server in Phase 4. Consequence: SMS waits on carrier registration, so email ships first.

## ADR-015 · Inquiries and hold requests only in v1
Scott is open to deposits either way. v1 lets a buyer inquire or request a hold, which the owner approves; no money moves online. Consequence: no payment provider, no refund handling; a deposit flow would be a new ADR.

## ADR-016 · Free tiers first; cost is announced before it is incurred
Every service starts on its free tier or trial. Before a task enables a paid plan, or starts a trial clock (Snowflake's 30 days, Twilio registration fees), the expected monthly cost is stated and Scott approves. Consequence: the Snowflake trial does not start until Phase 3 begins.

## ADR-017 · Tooling defaults
Python with uv, ruff, pyright, pytest; FastAPI, Pydantic, SQLAlchemy 2, Alembic, Strawberry; LightGBM for scoring. pnpm workspace; Next.js, Tailwind, shadcn/ui, MapLibre GL, Vitest, Playwright; types generated from OpenAPI and the GraphQL schema. Resend for transactional email behind an interface. Scott owns git: Claude Code never commits and ends each task with a proposed commit message.
