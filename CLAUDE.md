# Cornerpin — Claude Code guide

You are working with Scott Shepherd (Gigadev Consulting), a solo developer. Write like a peer,
not a vendor. Keep changes small, tested and reviewable in one sitting.

## What this is
Multi-tenant PWA where land owners and developers manage subdivisions, phases and lots, and the
public browses them: status (available / on hold / sold), price, a map to the subdivision and
the lot, photos and documents. Visitors can sign up, save lots and get notified of changes.
The first tenant is Ricky's subdivision in Idaho, in real use. The project is also Scott's
showcase for a job application, which is why the integrations and the AI features exist.

FastAPI (Python) is the API; Postgres + PostGIS with RLS is the system of record; Next.js
(App Router, TypeScript) is the web app and PWA; REST for writes, GraphQL for public reads.
The plan is docs/IMPLEMENTATION_PLAN.md. Decisions are ADRs in docs/adr/, one file each, indexed in docs/adr/README.md.
Do not re-litigate an ADR in code; propose a new ADR instead.

## Local first, then live (ADR-009)
Everything runs on this machine first: Postgres + PostGIS and Mailpit in Docker, the API via
uvicorn, the web app via `next dev` (or `next build && next start` when testing the PWA).
Production is Cloud Run + Neon + Cloud Storage at cornerpin.app. Anything that needs a
third-party account is wired behind env/config and stays dormant until its credentials exist.

## Layout
apps/api        FastAPI: REST /v1, GraphQL /graphql, webhooks, /internal task handlers;
                modules core, listings, leads, notifications, outreach, decisioning, integrations
apps/web        Next.js PWA (pnpm --filter web <cmd>)
apps/mcp        MCP server over the same tools the outreach agent uses (Phase 4)
evals/          scripted conversations and checks for the outreach agent
infra/          Terraform for Cloud Run, Cloud Tasks, Cloud Storage, secrets
docs/           plan and supporting docs

## Commands (made true by task P1-01)
docker compose up -d                     Postgres + PostGIS, Mailpit
uv run alembic upgrade head              apply migrations
uv run pytest · uv run ruff check · uv run pyright
pnpm lint · pnpm test · pnpm build · pnpm e2e

## Non-negotiables
- Every tenant-owned table: tenant_id uuid not null, RLS enabled and forced, policies in the
  same migration, and a test proving cross-tenant reads return 0 rows.
- The API connects as a non-owner database role and sets app.tenant_id / app.user_id with
  SET LOCAL per transaction from the verified session. Never trust tenant_id or user_id from
  the client. Public reads go through policies that expose only published listings.
- Secrets live in env files locally and Secret Manager in the cloud, never in the web bundle.
- Third-party and model calls (Claude, Twilio, Salesforce, Snowflake, Gmail, Zoom, Slack,
  email) run only in background tasks fed by the outbox, never during a page render.
- Outreach: no message on a channel without recorded consent for that channel; opt-outs are
  honoured before any send; quiet hours use the recipient's time zone; every send is logged.
  The agent states only facts it read through its tools (price, status, availability) and
  hands off to a human when unsure.
- Risk scores are advisory: logged with model version, inputs and reason codes, and a human
  makes the decision. No protected-class attributes or proxies as features.
- PWA: the service worker never caches authenticated or owner-portal responses.
- Typed end to end: Pydantic → OpenAPI → generated TS types; GraphQL codegen; no `any`.
- Tests: pytest for the API and RLS; Vitest for web logic; Playwright smoke for each screen in
  the plan; evals for the agent. Everything green locally before you say a task is done.
- Cost: free tiers first. Before enabling anything paid, or anything that starts a trial
  clock, tell Scott the expected monthly cost and wait for a yes.
- Git is Scott's. Never run git commit, push, branch, stash, reset or checkout. End each task
  with a proposed conventional-commit message in your summary.
- One task at a time. Add an ADR in docs/adr/ when you make a call the plan did not.

## Working agreement
Before a task: restate acceptance criteria. After: run lint/test/build, summarize what changed,
what you are unsure about, and the proposed commit message, then stop for review. If the plan
and the code disagree, ask; do not silently pick one. Do not add features not in the plan.

## Context that saves time
- Domain is cornerpin.app. The .app TLD is HTTPS-only, which the PWA needs anyway.
- Ricky's subdivision: Idaho, 15 lots in phase 1, up to about 75 in total. Never hard-code
  lot or phase counts. Two lots have showcase homes nearly finished, so a lot is either
  land-only or lot + home.
- Ricky does not offer owner financing. The financing module exists only in the demo tenant,
  on synthetic data (ADR-013).
- v1 takes inquiries and hold requests; no online payments (ADR-015).
- Auth is passwordless (magic link + Google) with Cloudflare Turnstile on public forms; never
  add a password field. Locally, Mailpit receives magic links and Turnstile uses Cloudflare's
  always-pass test keys.
- Theme: "survey and land" (ADR-033), sage on sand, Fraunces + Inter, a working identity until
  Scott supplies a real brand. Use the colour tokens, never raw colours.
- Idaho spans the Mountain and Pacific time zones; each subdivision stores its time zone.
