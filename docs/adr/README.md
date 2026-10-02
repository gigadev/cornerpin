# Architecture decision records

Each file here records one decision that shapes Cornerpin: the context, what was decided, and
what follows from it. They are the canonical source for how the system is built. If the
[implementation plan](../IMPLEMENTATION_PLAN.md) disagrees with an ADR, the ADR wins.

"Applies from" says when a decision starts to show in the code. An accepted ADR whose phase has
not started yet is still binding: it describes how that part will be built.

## Index

| ADR | Decision | Applies from | Status |
| --- | --- | --- | --- |
| [001](001-name-and-domain.md) | Name Cornerpin, domain cornerpin.app | day zero | Accepted |
| [002](002-fastapi-and-postgis.md) | FastAPI is the API; Postgres + PostGIS is the system of record | P1-01 | Accepted |
| [003](003-tenancy-and-rls.md) | Tenancy = organizations, isolated by row-level security | P1-02 | Accepted |
| [004](004-nextjs-web-app.md) | Next.js (App Router, TypeScript) for the web app | P1-01 | Accepted |
| [005](005-pwa-for-on-site-use.md) | The web app is a PWA built for use on site | P1-01, P1-10 | Accepted |
| [006](006-path-based-urls.md) | Path-based public URLs on one origin | P1-07, P1-11 | Accepted |
| [007](007-rest-writes-graphql-reads.md) | REST for writes, GraphQL for public reads | P1-04, P1-07 | Accepted |
| [008](008-passwordless-auth.md) | Passwordless auth owned by the API | P1-03 | Accepted |
| [009](009-cloud-run-neon-local-first.md) | Cloud Run + Neon + Cloud Storage, built locally first | P1-01, P1-12 | Accepted |
| [010](010-outbox-and-cloud-tasks.md) | Transactional outbox and Cloud Tasks for background work | P1-09 | Accepted |
| [011](011-modular-monolith.md) | Modular monolith with service boundaries drawn now | P1-01 | Accepted |
| [012](012-optional-integrations.md) | Integrations are per-tenant, optional and dormant without credentials | Phases 2–4 | Accepted |
| [013](013-advisory-risk-decisioning.md) | Risk decisioning is advisory, logged and explainable | Phase 3 | Accepted |
| [014](014-consent-first-outreach-agent.md) | The outreach agent is consent-first, tool-bound and evaluated | Phase 2 | Accepted |
| [015](015-inquiries-and-holds-only.md) | Inquiries and hold requests only in v1 | P1-08 | Accepted |
| [016](016-free-tiers-first.md) | Free tiers first; cost is announced before it is incurred | throughout | Accepted |
| [017](017-tooling-defaults.md) | Tooling defaults | P1-01 | Accepted |
| [018](018-map-tiles.md) | Map tiles: OpenFreeMap now, satellite behind config | P1-06, P1-07 | Accepted |
| [019](019-scaffold-specifics.md) | Scaffold specifics (P1-01) | P1-01 | Accepted |
| [020](020-adrs-in-docs-folder.md) | ADRs live in docs/adr, one file per decision | now | Accepted |
| [021](021-database-roles-and-policies.md) | Database roles and the shape of RLS policies | P1-02 | Accepted |
| [022](022-consent-per-tenant.md) | Contact consent is recorded per tenant and append-only | P1-02, P1-08 | Accepted |
| [023](023-sign-in-sessions-and-outbox-start.md) | Sign-in, sessions, and starting the outbox in P1-03 | P1-03 | Accepted |
| [024](024-owner-portal-rules.md) | Owner portal rules for editing, deleting and history | P1-04 | Accepted |
| [025](025-photo-and-document-storage.md) | Photo and document storage | P1-05 | Accepted |
| [026](026-lot-geometry-and-public-map.md) | Lot geometry, the plat overlay and the first public map | P1-06 | Accepted |
| [027](027-public-pages.md) | Public pages: rendering, filters, files and link previews | P1-07 | Accepted |
| [028](028-buyer-activity.md) | Buyer activity: who may do what, consent capture and hold approval | P1-08 | Accepted |
| [029](029-notifications-and-task-runner.md) | Notifications, the task runner and web push | P1-09 | Accepted |
| [030](030-pwa-caching-and-offline.md) | PWA caching, offline questions and updates | P1-10 | Accepted |
| [031](031-qr-codes-and-signs.md) | QR codes and lot signs | P1-11 | Accepted |
| [032](032-production-deployment.md) | Production deployment on Google Cloud and Neon | P1-12 | Accepted |
| [033](033-visual-theme.md) | The "survey and land" visual theme | P1-12 | Accepted |

## Adding a decision

Write an ADR when a task makes a call the plan did not, or when a choice would be expensive to
reverse.

1. Copy [template.md](template.md) to `NNN-short-slug.md`, using the next free number.
2. Fill in Context, Decision and Consequences. Keep it short; one screen is plenty.
3. Add a row to the index above.
4. Mention the new ADR in the task summary, so it is reviewed with the code.

## Changing a decision

ADRs are not rewritten once accepted. To change one:

1. Write a new ADR that states the new decision and names the one it replaces.
2. In the old ADR, change only the status line to `Superseded by ADR-NNN`.
3. Update both rows in the index.

Code and docs refer to ADRs by number (for example `ADR-005` in a code comment), so numbers are
never reused.
