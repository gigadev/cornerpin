# ADR-032: Production deployment on Google Cloud and Neon

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-12

## Context

ADR-009 puts production on Cloud Run, Neon and Cloud Storage at cornerpin.app, built locally
first. P1-12 has to choose a region and how the domain reaches Cloud Run, decide how services
authenticate to each other, where secrets live, how migrations run, and how deploys happen,
within ADR-016's free-tiers-first rule.

## Decision

- **Region.** Google Cloud us-west1 (Oregon) and Neon aws-us-west-2 (Oregon): closest to
  Idaho, a few milliseconds apart, and us-west1 is an Always Free Cloud Storage region. Scott
  chose this on 2026-10-01.
- **The domain goes through Firebase Hosting**, which rewrites every path to the web service on
  Cloud Run, with a Google-managed certificate, free at this traffic. The alternatives were a
  global load balancer (about $18–20 a month) and Cloud Run domain mapping (preview, and Google
  calls it not production-ready). Scott chose this on 2026-10-01. Firebase Hosting forwards
  exactly one cookie, `__session`, so the session cookie is now called that. Google sign-in's
  short-lived state cookie (`cp_oauth`) is not forwarded either; before Google sign-in is
  switched on in production, that state must move into `__session` or the URL.
  `www.cornerpin.app` redirects to the apex.
- **Two Cloud Run services, scale to zero.** `web` is public (Hosting calls it). `api` is
  private: only the web app's service account and the tasks account may invoke it. The web
  server adds a Google ID token from the metadata server to every API call (`API_AUDIENCE`);
  locally nothing changes. The browser still only talks to the web origin (ADR-023).
- **A service account per job.** `api`, `web`, `tasks` (Cloud Tasks and Scheduler calling the
  API), `ops` (migrations and ops commands) and `deployer` (GitHub Actions). The running API
  can't read the database owner's credentials; only `ops` can.
- **Secrets** live in Secret Manager. Terraform creates the containers; `scripts/set-secrets.sh`
  fills them, prompting for account secrets and generating the rest, so no secret value is in
  Terraform state, the repo or a chat. The API's database role gets a generated password that
  the migrate job applies.
- **Neon** is used through its direct endpoint, not the pooler, because transactions set a role
  and settings per transaction (ADR-021). The free plan's owner role is neither superuser nor
  BYPASSRLS, so ops commands that write tenant rows lift forced RLS inside their own
  transaction only (`cornerpin.ops`), and migration 0007 grants the one permission a non-superuser
  needs to hand a function to `cornerpin_public`. Both are tested against a non-superuser owner.
- **Migrations and ops commands are Cloud Run jobs** from the API image: `migrate` runs on every
  deploy before the new API starts; `ops` runs one-off commands such as `seed-demo` and
  `create-tenant`.
- **Deploys** run in GitHub Actions after CI passes on `main` (or by hand), signed in through
  Workload Identity Federation limited to this repository's `main`: build and push both images,
  migrate, deploy the API, deploy the web app, smoke-check the live site. Terraform owns each
  service's configuration and ignores which image runs.
- **Infrastructure is Terraform** in `infra/`, with state in a versioned bucket created once by
  `scripts/bootstrap.sh`.
- **The outbox drain is hourly, not every minute.** Each drain wakes Neon's compute, and the free
  plan has 100 CU-hours a month; waking it every minute would use about 186. Events are still
  dispatched as soon as their transaction commits, now including the lot changes a database
  trigger queues (the routes that change status or price say so).
- **Budget.** A $5 monthly budget alerts the billing account's admins at 50, 90 and 100 percent.
  Scott approved this on 2026-10-01.

## Expected cost

| Service | Monthly |
| --- | --- |
| Cloud Run (2 services, 2 jobs, scale to zero) | $0, inside the free tier |
| Firebase Hosting | $0, inside 10 GB storage and 360 MB/day transfer |
| Cloud Storage (uploads, Terraform state) | $0, Always Free in us-west1 |
| Cloud Tasks, Cloud Scheduler (2 jobs) | $0 |
| Artifact Registry (cleanup keeps it small) | under $1 |
| Secret Manager (6 secrets) | $0, inside the 6 free active versions |
| Neon free plan | $0 |
| Resend free plan, Cloudflare Turnstile | $0 |

## Consequences

- Sessions signed in before the cookie rename end; people sign in again.
- A request that wakes both scaled-to-zero services and Neon can take a few seconds.
- Moving off Firebase Hosting later means renaming the cookie back or keeping `__session`.

## Related

ADR-009 (Cloud Run, Neon), ADR-010 and ADR-029 (outbox), ADR-016 (cost), ADR-021 (roles),
ADR-023 (sessions and the /v1 proxy), ADR-030 (offline)
