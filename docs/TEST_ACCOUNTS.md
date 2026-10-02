# Test accounts and local URLs

Everything here is local test data. There are no passwords anywhere: you sign in with an emailed
link (magic link), and locally every email lands in Mailpit, not a real inbox. Google sign-in
stays switched off until a Google client id exists.

## Local URLs

| What | URL |
| --- | --- |
| Web app | http://localhost:3300 |
| Sign in | http://localhost:3300/signin |
| Owner portal | http://localhost:3300/app |
| Public page for the demo subdivision | http://localhost:3300/juniper-bench |
| Owner map editor | Owner portal → Juniper Bench → Map and lot shapes |
| Mailpit (all local email) | http://localhost:8025 |
| API | http://localhost:8000 |
| API docs (try requests here) | http://localhost:8000/docs |
| Public GraphQL explorer (GraphiQL) | http://localhost:8000/graphql |
| Postgres + PostGIS | `localhost:5434`, database `cornerpin` |
| Uploaded photos and documents | the `var/storage` folder in the repo (gitignored) |

## Accounts for smoke testing (dev database)

These exist in the dev database `cornerpin` after `uv run python -m cornerpin.seed`.

| Email | What it is | Can see |
| --- | --- | --- |
| `owner@demo.cornerpin.test` | Owner of **Demo Land Co.** | The owner portal for Demo Land Co. and its subdivision **Juniper Bench** (`/juniper-bench`) |
| Any new address, e.g. `you@example.test` | Created on first sign-in, as a buyer | No portal ("You don't manage any subdivisions") |

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

### Resetting the demo data

```bash
uv run python -m cornerpin.seed
```

This rebuilds Demo Land Co. and Juniper Bench from scratch: 25 lots, phase 1 published and
phase 2 not. Accounts you created stay, but everything attached to Demo Land Co. is removed:
lots and subdivisions you added, and owners you added with the SQL above (run it again).

## Accounts used only by automated tests

You don't need these for smoke testing, and they don't exist in the dev database. Signing in
with one on the dev site just creates a new buyer account with no portal.

**Playwright** (`pnpm e2e`) uses a separate database, `cornerpin_e2e`, rebuilt on every run:

| Email | Role |
| --- | --- |
| `owner+mobile@demo.cornerpin.test`, `owner+desktop@demo.cornerpin.test` | Owners of Demo Land Co.; the sign-in tests use them |
| `portal+mobile@demo.cornerpin.test`, `portal+desktop@demo.cornerpin.test` | Owners of Demo Land Co.; the portal tests use them |
| `owner@other.cornerpin.test` | Owner of **Other Land Co.** (tenant `1aca3c52-936f-5fd9-8a5b-aa1b6e00ae2e`); used to prove one owner can't open another's portal |
| `visitor+<project>-<time>@cornerpin.test` | Made up per run; a new buyer account |

Its uploads go to `var/e2e-storage`, emptied at the start of each run.

**pytest** (`uv run pytest`) uses another separate database, `cornerpin_test`, rebuilt on every
run, and a temporary folder for uploads. It has two tenants, `alpha` and `bravo`, each with `owner@<tenant>.test` and
`buyer@<tenant>.test`.

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
