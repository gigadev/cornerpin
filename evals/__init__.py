"""Evals for the outreach agent (P2-06, ADR-039).

Scripted conversations with the demo tenant, run through the real API, outbox, tools and
guardrails, with checks on what the buyer receives: lot facts, invented prices, opt-outs,
handoffs and quiet hours. The model is either Claude (`--live`, which costs money and can
`--record`) or the recorded replies of the last live run (the default, free, run by pytest on
every push).

    uv run python -m evals                    replay the recordings
    uv run python -m evals --live --record    the real model; keep its replies if they pass
    uv run python -m evals --plant invented-price    a regression the suite must catch
"""
