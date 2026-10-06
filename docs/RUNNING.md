# Running Cornerpin locally

Four services, four commands, all run from the repo root (`C:\git\github\cornerpin`).

| Service | Command | Address | Keeps the terminal? |
| --- | --- | --- | --- |
| Database (Postgres + PostGIS) | `pnpm db` | localhost:5434 | No, runs in Docker |
| Mailpit (catches every email) | `pnpm mail` | http://localhost:8025 | No, runs in Docker |
| API (FastAPI) | `pnpm api` | http://localhost:8000 | Yes |
| Web app (Next.js) | `pnpm web` | http://localhost:3300 | Yes |

## Starting

Docker Desktop has to be running first. Then, in one terminal:

```bash
pnpm db
```

```bash
pnpm mail
```

Both start in the background and hand the terminal back; `pnpm db` waits until the database
accepts connections. Then open a terminal each for the API and the web app, which stay in the
foreground and print their logs:

```bash
pnpm api
```

```bash
pnpm web
```

Open http://localhost:3300/juniper-bench. Sign-in links arrive in Mailpit. The test accounts
are in [TEST_ACCOUNTS.md](TEST_ACCOUNTS.md).

The API and the web app reload themselves when you change their code. After installing
packages, stop the web app (Ctrl+C) and start it again.

## Stopping

Ctrl+C in the API and web app terminals. To stop the database and Mailpit:

```bash
pnpm stop
```

The data is kept. Docker Desktop also stops them when it quits.

## The first time

Before the first start, from the repo root: copy `.env.example` to `.env`, run `uv sync` and
`pnpm install`, then start the database and create the tables and the demo data:

```bash
uv run alembic upgrade head
```

```bash
uv run python -m cornerpin.seed
```

[WALKTHROUGH.md](WALKTHROUGH.md#first-time) has the details and the prerequisites.

## When something is off

| Symptom | Likely cause |
| --- | --- |
| `pnpm db` fails with "cannot connect to the Docker daemon" | Docker Desktop isn't running |
| Pages say they can't reach the API | `pnpm api` isn't running |
| "Port 3300 (or 8000) is already in use" | An earlier copy is still running; close its terminal, or find it with `Get-NetTCPConnection -LocalPort 3300` |
| No sign-in email | Check Mailpit at http://localhost:8025; `pnpm mail` starts it |
| Errors about missing tables after pulling new code | Run `uv run alembic upgrade head` |
| Demo data looks wrong | `uv run python -m cornerpin.seed` puts it back |
| pytest's evals test says a recording is "recorded under another prompt, tools or model" | The agent's prompt or tools changed: `uv run python -m evals --live --record` (about 16 cents) and commit `evals/recordings/` (ADR-039) |
