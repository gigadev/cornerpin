# ADR-046: The lead model: LightGBM on synthetic history, explained by its own contributions

- **Status:** Accepted
- **Date:** 2026-10-07
- **Applies from:** P3-02

## Context

ADR-013 chose gradient-boosted trees, and ADR-045 fixed what a score may look at. Cornerpin
has no history of leads that closed or fell through. Ricky's tenant is new and the demo's
buyers are made up. Scott chose synthetic training data on 2026-10-07, on the condition that
the portal says so. The model has to explain every score in words an owner understands, and
the artifact has to be reproducible so a reviewer can trust it.

## Decision

- **Synthetic history in the demo's shape.** `cornerpin.decisioning.training` generates leads
  with a hidden "interest" that shapes how each buyer behaves: replies, holds, opting out,
  recency. Interest never reaches the model, which learns from behaviour alone. Whether a lead
  fell through follows the stated rules in `fell_through_logit`, plus noise:
  - replies and holds lower the risk; an approved hold lowers it most;
  - unanswered messages, going quiet past two weeks and opting out raise it;
  - an unreleased phase and a higher-priced lot raise it a little;
  - a lot with a home lowers it a little.

  The rules are versioned (`synthetic-v1`). Every artifact's metadata says the data is
  synthetic, and the portal will too (P3-03).
- **LightGBM, small and deterministic.** It trains on 6,000 leads (80% for training, 20% held
  out) with 80 rounds of 8-leaf trees, one thread and a fixed seed. Categorical features are
  coded in a fixed order.
- **Monotone constraints** make the model agree with common sense whatever the data says:
  - more replies, a hold request and an approved hold can only lower the risk;
  - more days since the buyer was last heard from, and opting out, can only raise it.
- **The artifact lives in the repo:** `models/lead-v1.txt` (about 84 KB) and `lead-v1.json`,
  which holds:
  - the features, categories and constraints;
  - the parameters;
  - the training settings;
  - the held-out metrics (AUC 0.786, log loss 0.537);
  - the LightGBM version.

  There are no timestamps, so retraining with the same settings rewrites identical files. A
  test retrains and compares predictions on 300 unseen leads.
- **The model version is `lgbm-` plus the artifact name**, so `lgbm-lead-v1`. The scorer
  refuses an artifact trained on any feature list but `LeadFeatures`.
- **Reasons come from LightGBM's own per-feature contributions** (`pred_contrib`, TreeSHAP),
  in log-odds, measured against the average lead:
  - the three features that moved the risk most are always shown, and up to five if the
    others moved it by at least 0.1;
  - each reason states the lead's own fact in the owner's words, such as "No replies yet" or
    "Last heard from 40 days ago";
  - its signed weight says whether it raised or lowered the risk;
  - a reply that still raised the risk, because most leads reply more, reads "Replied only
    once".
- **The rules baseline (`rules-v1`) stays as the reference** the model is compared with. New
  scores come from the model.
- **A planted attribute** proves the feature test works: `train(plant="buyer_age")` adds a
  made-up personal column that predicts the outcome. The test asserts that the feature check
  fails on it and the scorer refuses it.
- **LightGBM is an API dependency until P3-04**, which moves it to the decisioning service.
  - It brings NumPy and SciPy, and the image adds `libgomp1`, the OpenMP runtime.
  - It's imported only when the first score is made, so the API starts as fast as before.
  - It's free.
  - Existing leads keep their `rules-v1` score until their next event. If P3-01 and P3-02
    deploy together, migration 0018's backfill is scored by the model directly.

## Consequences

- Scores are honest about what they are: a model of stated rules, not of Ricky's buyers. When
  real outcomes exist (won and lost leads), the same pipeline can train on them. That needs a
  new rules version, an ADR on how real labels are drawn, and the same feature test.
- The held-out AUC measures how well the model recovers the synthetic rules, not real-world
  accuracy. It's recorded so changes to the generator or parameters are visible.
- Changing the generator, the parameters or LightGBM's version means retraining, committing the
  new artifact, and the reproduction test passing on CI's Linux as well as Windows.

## Related

ADR-011 (decisioning service), ADR-013, ADR-017 (LightGBM), ADR-045
