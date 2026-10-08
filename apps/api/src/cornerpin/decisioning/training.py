"""Train the lead model on synthetic history (ADR-046).

    uv run python -m cornerpin.decisioning.training           retrain lead-v1 into models/

There is no real history to learn from yet, so leads are generated in the demo's shape and
their outcomes follow the stated rules in `fell_through_logit`, plus noise. A buyer's hidden
interest shapes how they behave (replies, holds, opting out) but never reaches the model; it
learns from behaviour alone, as it would from real leads. Training is deterministic, so the
artifact in models/ can be reproduced from its recorded settings."""

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from cornerpin.decisioning.features import LeadFeatures, PriceBand
from cornerpin.decisioning.model import (
    CATEGORIES,
    CURRENT,
    FEATURES,
    MODELS,
    MONOTONE,
    encode,
)

RULES_VERSION = "synthetic-v1"
DEFAULTS: dict[str, int] = {"rows": 6000, "seed": 7, "rounds": 80}
PARAMS: dict[str, Any] = {
    "objective": "binary",
    "num_leaves": 8,
    "learning_rate": 0.1,
    "min_data_in_leaf": 40,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 1,
    "verbose": -1,
}

type Rng = np.random.Generator
BANDS: tuple[PriceBand, ...] = ("low", "mid", "high")


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def fell_through_logit(f: LeadFeatures) -> float:
    """The stated rules: what makes a synthetic lead fall through, in log-odds."""
    quiet = f.days_since_buyer_activity
    if quiet is None:
        quiet = f.days_since_first_contact
    return (
        0.6
        - 0.6 * min(f.replies, 3)
        - 1.0 * (f.hold_requests > 0)
        - 1.2 * f.hold_approved
        + 0.35 * max(f.touches - f.replies, 0)
        + 0.025 * min(max(quiet - 14, 0), 90)
        + 1.5 * f.opted_out
        + 0.4 * (f.phase_release == "upcoming")
        + 0.3 * (f.lot_price_band == "high")
        - 0.1 * (f.lot_price_band == "low")
        - 0.3 * (f.listing_type == "lot_and_home")
    )


def _lead(rng: Rng) -> LeadFeatures:
    interest = float(rng.normal())  # hidden: shapes behaviour, never a feature
    age = min(int(rng.exponential(30)), 180)
    touches = int(rng.integers(0, min(5, age // 3 + 1) + 1))
    replies = int(rng.binomial(touches, _sigmoid(-0.5 + 1.2 * interest)))
    hold_requests = int(rng.random() < _sigmoid(-2.2 + 1.5 * interest))
    hold_approved = hold_requests > 0 and rng.random() < 0.6
    opted_out = bool(rng.random() < _sigmoid(-3.2 - 1.0 * interest + 0.3 * touches))
    if rng.random() < 0.15:  # only an anonymous inquiry: nothing verified from the buyer
        buyer_activity = None
    else:
        recency = float(rng.beta(1.0, 2.0 + max(interest, -0.9)))  # keener: more recent
        buyer_activity = int(age * recency)
    has_lot = rng.random() > 0.05
    stage = (
        "holding" if hold_approved else "engaged" if replies else "contacted" if touches else "new"
    )
    return LeadFeatures(
        stage=stage,
        touches=touches,
        replies=replies,
        hold_requests=hold_requests,
        hold_approved=hold_approved,
        days_since_first_contact=age,
        days_since_buyer_activity=buyer_activity,
        opted_out=opted_out,
        lot_price_band=BANDS[int(rng.integers(0, 3))] if has_lot else None,
        listing_type=(
            ("lot_and_home" if rng.random() < 0.15 else "land_only") if has_lot else None
        ),
        phase_release=("upcoming" if rng.random() < 0.15 else "released") if has_lot else None,
    )


def generate(rows: int, seed: int) -> tuple[list[LeadFeatures], list[int]]:
    """Synthetic leads and whether each fell through (1) or closed (0)."""
    rng = np.random.default_rng(seed)
    leads = [_lead(rng) for _ in range(rows)]
    labels = [
        int(rng.random() < _sigmoid(fell_through_logit(f) + float(rng.normal(0, 0.8))))
        for f in leads
    ]
    return leads, labels


def auc(labels: list[int], predicted: list[float]) -> float:
    """Area under the ROC curve, by ranks (ties share their rank)."""
    order = np.argsort(predicted, kind="stable")
    ranks = np.empty(len(predicted))
    ranks[order] = np.arange(1, len(predicted) + 1)
    values = np.asarray(predicted)
    for v in np.unique(values):
        tied = values == v
        ranks[tied] = ranks[tied].mean()
    positives = np.asarray(labels) == 1
    n_pos, n_neg = int(positives.sum()), int((~positives).sum())
    return float((ranks[positives].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def log_loss(labels: list[int], predicted: list[float]) -> float:
    p = np.clip(np.asarray(predicted), 1e-9, 1 - 1e-9)
    y = np.asarray(labels)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


@dataclass(frozen=True)
class Trained:
    model_text: str
    metadata: dict[str, Any]

    @property
    def features(self) -> list[str]:
        names: list[str] = self.metadata["features"]
        return names


def train(
    *,
    rows: int = DEFAULTS["rows"],
    seed: int = DEFAULTS["seed"],
    rounds: int = DEFAULTS["rounds"],
    plant: str | None = None,
) -> Trained:
    """Train on 80% of a synthetic history and measure on the rest. `plant` adds a made-up
    personal column that predicts the outcome, to prove the feature test catches it."""
    import lightgbm as lgb

    leads, labels = generate(rows, seed)
    matrix = [encode(f) for f in leads]
    names = list(FEATURES)
    if plant is not None:
        rng = np.random.default_rng(seed + 1)
        names.append(plant)
        for row, label in zip(matrix, labels, strict=True):
            row.append(float(rng.normal(40 + 10 * label, 8)))
    cut = int(rows * 0.8)
    x, y = np.array(matrix, dtype=float), np.array(labels)
    dataset = lgb.Dataset(
        x[:cut],
        label=y[:cut],
        feature_name=names,
        categorical_feature=[names.index(n) for n in CATEGORIES],
        free_raw_data=False,
    )
    params = PARAMS | {
        "seed": seed,
        "monotone_constraints": [MONOTONE.get(n, 0) for n in names],
    }
    booster = lgb.train(params, dataset, num_boost_round=rounds)  # pyright: ignore[reportUnknownMemberType]
    held_out = [float(p) for p in np.asarray(booster.predict(x[cut:])).ravel()]  # pyright: ignore[reportUnknownMemberType]
    held_labels = [int(v) for v in y[cut:]]
    metadata: dict[str, Any] = {
        "features": names,
        "categories": {k: list(v) for k, v in CATEGORIES.items()},
        "monotone": MONOTONE,
        "params": {k: v for k, v in params.items() if k != "monotone_constraints"},
        "training": {"rows": rows, "seed": seed, "rounds": rounds, "rules": RULES_VERSION},
        "metrics": {
            "held_out_rows": rows - cut,
            "fell_through_rate": round(float(np.mean(held_labels)), 4),
            "auc": round(auc(held_labels, held_out), 4),
            "log_loss": round(log_loss(held_labels, held_out), 4),
        },
        "lightgbm": lgb.__version__,
        "data": "synthetic: generated by cornerpin.decisioning.training, not real buyers",
    }
    return Trained(model_text=booster.model_to_string(), metadata=metadata)  # pyright: ignore[reportUnknownMemberType]


def save(trained: Trained, name: str = CURRENT, folder: Path = MODELS) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.txt").write_text(trained.model_text, encoding="utf-8", newline="\n")
    (folder / f"{name}.json").write_text(
        json.dumps(trained.metadata, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=DEFAULTS["rows"])
    parser.add_argument("--seed", type=int, default=DEFAULTS["seed"])
    parser.add_argument("--rounds", type=int, default=DEFAULTS["rounds"])
    args = parser.parse_args()
    trained = train(rows=args.rows, seed=args.seed, rounds=args.rounds)
    save(trained)
    print(f"{CURRENT}: {json.dumps(trained.metadata['metrics'])}")


if __name__ == "__main__":
    main()
