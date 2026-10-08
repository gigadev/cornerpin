# ADR-048: The decisioning service: the model in its own Cloud Run service, called by the API

- **Status:** Accepted
- **Date:** 2026-10-08
- **Applies from:** P3-04

## Context

ADR-011 drew decisioning as its own service and said to split it out in Phase 3, once its ML
dependencies would bloat the API image. P3-02 put LightGBM, NumPy and SciPy in the API until
then. Four things needed deciding:
- what moves;
- how the two sides agree on the contract;
- how the API authenticates;
- how local development works without a second server.

## Decision

- **`apps/decisioning` is a second workspace package**, `cornerpin-decisioning`, with its own
  Dockerfile. It holds:
  - the model code;
  - training;
  - the `lead-v1` artifact;
  - the model's own tests;
  - two endpoints: `GET /health`, which loads the model so a cold start pays for it there, and
    `POST /v1/score`, which takes features and returns the score and its reasons.

  It reads no database and holds no secrets.
- **The API keeps what touches data:**
  - the feature builder;
  - storing scores;
  - the decision log;
  - the outbox handler.

  It sends a lead's features and stores what comes back. Its dependencies no longer include
  LightGBM, NumPy or SciPy; the image drops from 770 MB to 466 MB and loses `libgomp1`.
- **Each side has its own copy of the contract.** The API has `LeadFeatures`, `Reason` and
  `Score`; the service has `Features`, `Reason`, `Score` and `ScoreRequest`. Neither imports the
  other's package. A test in the API's suite compares the two feature schemas field for field,
  and the artifact's feature list with ADR-045's allowed list. The service also refuses anything
  outside its contract with 422.
- **Authentication is Cloud Run IAM.**
  - The service is private: only the API's service account has `roles/run.invoker`.
  - The API attaches a Google ID token, fetched from the metadata server, for the service's URL.
  - Cloud Run checks it before the request reaches the service. This is the same arrangement as
    the web app calling the private API.
  - The service's URL is Cloud Run's deterministic one, worked out in Terraform like the API's,
    so there's no reference loop.
- **`DECISIONING_URL` chooses the path:**
  - **set**, the API calls the service, with an ID token when the URL is `https`;
  - **empty**, locally, the API runs the service's code in-process from the dev environment,
    where the workspace's dev group installs it.

  Outside local the API refuses to start without it, so the API image can never try to load a
  model it doesn't have. To try the real HTTP path locally, run the service on port 8200 and set
  the URL.
- **Failures are retried by the outbox.** The handler stores a score only after the service
  answers. A timeout, a 5xx or a cold start that runs past 15 seconds raises, and the outbox
  retries with back-off (ADR-043). A score is never half-written, and the inputs check (ADR-045)
  stops a retry from adding a duplicate.
- **Deploys:**
  - The workflow builds the decisioning image and deploys it after migrations and before the
    API, whose new code calls it.
  - Terraform creates the service with the placeholder image, its service account, the invoker
    binding, and `DECISIONING_URL` on the API and the jobs.
  - The service scales from zero to two instances, with 512 MiB.

## Consequences

- The API image is lighter and starts faster. A model change ships as a new decisioning image
  without touching the API.
- The first score after a quiet spell waits for the service to start and load the model, a few
  seconds. That's acceptable because scoring runs in the background.
- Scoring now crosses the network. If the service is down, scores lag until it's back; nothing
  else in the API depends on them.
- Costs: Cloud Run stays in the free tier at this volume. The extra image may take Artifact
  Registry past its free 0.5 GB, at $0.10 per GB a month, so a few cents at most.

## Related

ADR-011 (service boundaries), ADR-032 (production), ADR-043, ADR-045, ADR-046
