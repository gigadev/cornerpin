# Test accounts and local URLs

Everything here is local test data. There are no passwords anywhere: you sign in with an emailed
link (magic link), and locally every email lands in Mailpit, not a real inbox. Google sign-in
stays switched off until a Google client id exists.

## Local URLs

| What | URL |
| --- | --- |
| Web app | http://localhost:3300 |
| Sign in | http://localhost:3300/signin |
| Help: a tour of the site for buyers and owners | http://localhost:3300/help |
| How Cornerpin is built (services, deploys, languages) | http://localhost:3300/about |
| Owner portal | http://localhost:3300/app |
| Inquiries and hold requests (owner) | Owner portal → Demo Land Co. → Inquiries and holds |
| Leads, one per buyer, with their timeline (owner) | Owner portal → Demo Land Co. → Leads |
| Owner financing, synthetic and demo tenant only (owner, API for now; screens come with P3-06) | http://localhost:8000/docs → `financing`: `/v1/tenants/957ccd5e-b6d1-531f-a102-ddef309c396e/financing/applications` and `/financing/loans`, signed in as the demo owner. Any other tenant gets 404 |
| A lead's advisory risk score and its reasons (owner) | Owner portal → Demo Land Co. → Leads → a lead. Scores appear a moment after the buyer's activity |
| Unsubscribe from an owner's outreach | The "Stop these emails" link in an outreach email (`/unsubscribe?token=…`) |
| Play a buyer replying to outreach (local only) | `POST http://localhost:8000/v1/dev/inbound-email` with `to` set to the email's Reply-To (needs `INBOUND_EMAIL_DOMAIN=reply.cornerpin.test` in `.env`) |
| Send a tenant's Slack alerts to a real channel (local only) | `POST http://localhost:8000/v1/dev/integrations/slack` with `{"tenant_id": "957ccd5e-b6d1-531f-a102-ddef309c396e", "webhook_url": "<an incoming webhook made in the Slack app>"}`; Integrations in the portal then shows it. New leads, hold requests and handoffs post there |
| Sync a tenant to a real Salesforce org (works locally) | Integrations → Salesforce in the owner portal, with a Developer Edition org's My Domain and an External Client App's consumer key and secret; [INTEGRATIONS.md](INTEGRATIONS.md) has the steps. Leads, approved holds and lots then appear in the org |
| Buyer account (saved lots, alerts, contact permissions) | http://localhost:3300/account |
| Public page for the demo subdivision | http://localhost:3300/juniper-bench |
| Public page for a lot | http://localhost:3300/juniper-bench/lots/2-5 |
| Owner map editor | Owner portal → Juniper Bench → Map and lot shapes |
| Printable lot sign with QR code | Owner portal → a lot → **Print a sign** |
| Where a sign's code lands | http://localhost:3300/q/{code} (the code is under the QR on the sign) |
| Mailpit (all local email) | http://localhost:8025 |
| API | http://localhost:8000 |
| API docs (try requests here) | http://localhost:8000/docs |
| Decisioning service (optional locally; the API scores in-process unless `DECISIONING_URL=http://localhost:8200` is in `.env`) | http://localhost:8200/docs, started with `uv run uvicorn cornerpin_decisioning.app:app --port 8200` |
| Public GraphQL explorer (GraphiQL) | http://localhost:8000/graphql |
| Postgres + PostGIS | `localhost:5434`, database `cornerpin` |
| Uploaded photos and documents | the `var/storage` folder in the repo (gitignored) |

## Accounts for smoke testing (dev database)

These exist in the dev database `cornerpin` after `uv run python -m cornerpin.seed`.

| Email | What it is | Can see |
| --- | --- | --- |
| `owner@demo.cornerpin.test` | Owner of **Demo Land Co.** | The owner portal for Demo Land Co. and its subdivision **Juniper Bench** (`/juniper-bench`) |
| Any new address, e.g. `you@example.test` | Created on first sign-in, as a buyer | No portal; lands on `/account`. Can save lots, ask for holds and give contact permission on a lot page |
| No account (signed out) | A visitor | Can send a question from a lot page's "Contact the owner" form; nothing else |

Locally, addresses ending in `.test` are accepted, so you can make up as many as you like.
Elsewhere they are rejected.

Demo Land Co.'s tenant id is `957ccd5e-b6d1-531f-a102-ddef309c396e`, so its portal is
http://localhost:3300/app/957ccd5e-b6d1-531f-a102-ddef309c396e.

### Signing in

1. Open http://localhost:3300/signin and enter an address from the table.
2. The Turnstile box shows Cloudflare's red "testing only" note. That's expected locally; the
   button unlocks on its own.
3. Open Mailpit (http://localhost:8025) and open the "Your Cornerpin sign-in link" email.
4. Open the link and click **Sign in**. Each link works once and expires after 15 minutes.

Up to 5 links per address are sent every 15 minutes. If more are requested, the page still
says "Check your email" but nothing arrives; wait, or use another address.

### Making another address an owner

There's no invite screen yet. To make an address an owner of Demo Land Co., sign in with it
once (so the account exists), then run:

```bash
docker compose exec db psql -U cornerpin -d cornerpin -c "INSERT INTO memberships (tenant_id, user_id, role) SELECT '957ccd5e-b6d1-531f-a102-ddef309c396e', id, 'owner' FROM users WHERE email = 'you@example.test'"
```

Use `'staff'` instead of `'owner'` for a staff member. Right now both have the same rights
(ADR-024).

### Emails you should see in Mailpit

| When | Who gets it | Subject |
| --- | --- | --- |
| Someone asks for a sign-in link | That address | Your Cornerpin sign-in link |
| Someone sends a question from a lot page | Every owner and staff member of the lot's organization | New question about Lot 2-5 at Juniper Bench |
| A signed-in buyer asks to hold a lot | Every owner and staff member | Hold request for Lot 2-5 at Juniper Bench |
| An owner changes a published lot's status or price (or approves a hold) | Each buyer who saved the lot and kept email alerts on | Lot 2-5 at Juniper Bench is now on hold |
| The outreach agent's follow-up to a signed-in buyer who asked about a lot and allowed email (only with `ANTHROPIC_API_KEY` in `.env`; `AGENT_FOLLOW_UP_MINUTES` after the question) | That buyer, between 9:00 and 20:00 their time | About Lot 2-5 at Juniper Bench; ends with an automated-assistant sign-off and a "Stop these emails" link |
| The agent's answer to a buyer's reply (play one with the dev inbound route above) | That buyer | Re: About Lot 2-5 at Juniper Bench |

To try the status-change email: sign in as a new buyer, save a lot, then sign in as the owner
(another browser or a private window) and change that lot's status. Owner emails go to
`owner@demo.cornerpin.test`; replying goes to the buyer.

To try the agent: put the key in `.env` and restart the API. Then sign in as a new buyer and ask
about a lot with "Email" ticked. The follow-up arrives after `AGENT_FOLLOW_UP_MINUTES`, if it's
between 9:00 and 20:00 in Boise. Its lookups show on the lead's timeline in the owner portal.

### Web push (optional)

Push is off until it has keys, and the service worker only runs in a production build:

1. `uv run python -m cornerpin.devtools vapid-keys` and paste the two lines into `.env`.
2. Restart the API, then run the web app as a production build:
   `pnpm --filter web build` and `pnpm --filter web exec next start --port 3300`.
3. Sign in as a buyer, open `/account` and click **Also alert me on this device**.
4. Save a lot and change its status as the owner; Chrome shows the alert.

### Offline and installing (production build only)

The service worker doesn't run under `next dev`. To try offline behaviour and installing:

1. `pnpm --filter web build`, then `pnpm --filter web exec next start --port 3300` (stop the dev
   server first; the API stays on 8000).
2. Open http://localhost:3300/juniper-bench/lots/2-5 in Chrome and wait a few seconds.
3. In DevTools → Network, choose **Offline**. Lot 2-5 and the Juniper Bench page still open; a lot
   you haven't opened shows "You're offline" with links to the pages this browser has kept.
4. Still offline, send a question from lot 2-5. Switch back to **No throttling**: a banner sends
   it, and it shows up in the owner portal.
5. Chrome's address bar offers to install "Juniper Bench · Cornerpin" on that subdivision's
   pages, and "Cornerpin owner portal" under `/app`.

### Trying a lot sign

Open a lot in the owner portal and click **Print a sign**; the first time creates the lot's code.
A phone can't reach `localhost`, so locally open the short URL printed under the code
(`localhost:3300/q/…`) instead of scanning it. To see a sign
survive a rename, change the subdivision's web address and open the same `/q/…` link again.
Printing uses the browser's print dialog (letter paper).

### Resetting the demo data

```bash
uv run python -m cornerpin.seed
```

This rebuilds Demo Land Co. and Juniper Bench from scratch: 48 lots in three blocks, the 32 in
phase 1 published and the 16 in phase 2 not. It also switches on the synthetic owner-financing demo (ADR-049):
twelve made-up applicants, named "… (synthetic)" with `@synthetic.example` addresses, six of
them with loans (two behind on payments), three declined and three waiting for a decision. Accounts you created stay, but everything attached to Demo Land Co. is removed:
lots and subdivisions you added, and owners you added with the SQL above (run it again).

## Accounts used only by automated tests

You don't need these for smoke testing, and they don't exist in the dev database. Signing in
with one on the dev site just creates a new buyer account with no portal.

**Playwright** (`pnpm e2e`) uses a separate database, `cornerpin_e2e`, rebuilt on every run, and
web port 3310. If something else is using 3310, pick another, e.g. `E2E_WEB_PORT=3320 pnpm e2e`.
The sign test creates a subdivision called `Sign Ridge <viewport>` and renames its slug.

| Email | Role |
| --- | --- |
| `owner+mobile@demo.cornerpin.test`, `owner+desktop@demo.cornerpin.test` | Owners of Demo Land Co.; the sign-in tests use them |
| `portal+mobile@demo.cornerpin.test`, `portal+desktop@demo.cornerpin.test` | Owners of Demo Land Co.; the portal tests use them |
| `owner@other.cornerpin.test` | Owner of **Other Land Co.** (tenant `1aca3c52-936f-5fd9-8a5b-aa1b6e00ae2e`); used to prove one owner can't open another's portal |
| `buyer+mobile@buyers.cornerpin.test`, `buyer+desktop@buyers.cornerpin.test` | Buyers; the buyer tests use them (they ask to hold lots 12 and 13, which the owner approves, and save lots 10 and 15, which the owner puts on hold) |
| `walkin+mobile@example.test`, `walkin+desktop@example.test` | Not accounts: the email typed into a signed-out question |
| `visitor+<project>-<time>@cornerpin.test` | Made up per run; a new buyer account |
| `scored+<viewport>-<time>@buyers.cornerpin.test` | Made up per run; a new buyer who asks to hold lot 3-8 (mobile) or 3-10 (desktop), whose score the owner sees before approving (P3-03) |

Its uploads go to `var/e2e-storage`, emptied at the start of each run.

**pytest** (`uv run pytest`) uses another separate database, `cornerpin_test`, rebuilt on every
run, and a temporary folder for uploads. It has two tenants, `alpha` and `bravo`, each with `owner@<tenant>.test` and
`buyer@<tenant>.test`.

**Agent evals** (`uv run python -m evals`, also run by pytest) use `cornerpin_evals`, rebuilt on
every run with the demo seed. Each scenario signs in a new buyer,
`<scenario>-<random>@buyers.cornerpin.test`. Its email is captured in memory and never reaches
Mailpit. By default the model's replies come from `evals/recordings/`, which costs nothing.
`--live` calls Claude with your `ANTHROPIC_API_KEY`, about 16 cents a run.

## Production

Production (https://cornerpin.app) has no test accounts and refuses `.test` addresses. How it's
set up, and the commands for seeding the demo and creating tenants, are in
[DEPLOY.md](DEPLOY.md). Its Phase 2 gate uses a buyer address of your own; the dev-only routes
(`/v1/dev/inbound-email`, `/v1/dev/integrations/slack`) don't exist there.

## Keys and settings that are test-only

These are already the defaults locally (see `.env.example`). The API refuses to start with them
outside local.

| Setting | Local value |
| --- | --- |
| Turnstile site key | `1x00000000000000000000AA` (Cloudflare's always-pass test key) |
| Turnstile secret | `1x0000000000000000000000000000000AA` |
| Turnstile token for API calls without the widget | any value, e.g. `XXXX.DUMMY.TOKEN.XXXX` |
| `SECRET_KEY` | `local-development-only-not-a-secret` |
| Database owner | `cornerpin` / `cornerpin` |
| API database role | `cornerpin_api` / `cornerpin_api` |
