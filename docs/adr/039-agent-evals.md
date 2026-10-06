# ADR-039: Agent evals: recorded on a live run, replayed on every push

- **Status:** Accepted
- **Date:** 2026-10-06
- **Applies from:** P2-06

## Context

ADR-014 says an eval suite of scripted conversations checks the outreach agent and runs in CI.
The plan asks for checks on lot facts, invented prices, opt-outs, handoffs and quiet hours, a
runner that reports cost, and a way to run in CI without paying for the model on every push.
A live run of the suite costs about 16 cents (13 scenarios on Claude Sonnet 5.5). Live runs also
vary: in three runs of the final suite, one scenario failed once.

## Decision

- **Scenarios are code** (`evals/scenarios.py`). Each scenario is a buyer's steps with the demo
  tenant: an inquiry, replies, an opt-out. Each says what must be true afterwards:
  - the emails sent, and the lot facts they state;
  - phrases they must and mustn't contain;
  - whether the lead goes to a person, and why;
  - the tools called;
  - for quiet hours, when the email is held until.
- **Every scenario also gets the same checks:**
  - every amount of money in an email is a published price;
  - no draft was held back for inventing one;
  - every turn finished.

  Facts come from the database the run used, not from the agent's tools.
- **Everything but the model is real.** The suite runs on:
  - its own `cornerpin_evals` database with the demo seed;
  - the API in process and the outbox drained after each step;
  - the real agent, tools and guardrails.

  Email is captured, and the clock is set to each step's time in Boise.
- **Two ways to supply the model:**
  - `--live` uses Claude and reports what each scenario cost, priced from usage. With
    `--record`, the replies of passing scenarios are saved to `evals/recordings/`, which are
    committed.
  - The default replays those recordings. It costs nothing and gives the same result every time.
- **A recording is tied to its prompt.** Each records a fingerprint of the model, the system
  prompt and the tool definitions. Replaying a recording whose fingerprint has changed fails the
  run. A prompt or tool change therefore can't pass CI until someone has run it live and
  re-recorded.
- **CI:**
  - **Every push replays the suite**, inside pytest, for free.
  - **The pytest run also plants a regression** (`--plant invented-price` raises every price
    the model writes) and requires the suite to fail.
  - **Live runs happen only when asked:** from the Actions tab, or by labelling a pull request
    `live-evals`. They need the `ANTHROPIC_API_KEY` repository secret and stop starting
    scenarios after $1.
- **Checks are deterministic.** They are string and number checks, with no model grading
  another model's output, so the checks themselves cost nothing and can't disagree with each
  other between runs.

## Consequences

- CI can't tell whether a change to the agent's code changes what the model would say. The
  replay only shows that the recorded conversation still passes through today's tools and
  checks. That is why prompt and tool changes force a live run.
- A change to the tools' output, such as a new field, changes what the model sees without
  changing the fingerprint. The replay still passes, so such changes should get a live run.
- Live runs are not deterministic. A live failure is read and judged, not retried until it
  passes. Recordings are made only from passing scenarios.
- Phrase checks are strict and may need loosening as the model's wording drifts.
- More scenarios cost about a cent each per live run.

## Related

ADR-014 (outreach agent), ADR-016 (free tiers first), ADR-036 (sending rules), ADR-038 (the
agent)
