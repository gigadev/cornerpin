"""The trained lead model (ADR-046): how features become the model's inputs, and how its
per-feature contributions become reasons in plain words.

Runs in the decisioning service (ADR-048); LightGBM is imported when the model is loaded."""

import json
import math
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np

from cornerpin_decisioning.contract import Features, Reason, Score

MODELS = Path(__file__).parent / "models"
CURRENT = "lead-v1"

FEATURES: tuple[str, ...] = tuple(Features.model_fields)
# Categorical features, coded by their position here; missing values stay missing.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "stage": ("new", "contacted", "engaged", "holding"),
    "lot_price_band": ("low", "mid", "high"),
    "listing_type": ("land_only", "lot_and_home"),
    "phase_release": ("upcoming", "released"),
}
# Replies and holds may only lower the risk; going quiet and opting out may only raise it.
MONOTONE: dict[str, int] = {
    "replies": -1,
    "hold_requests": -1,
    "hold_approved": -1,
    "days_since_buyer_activity": 1,
    "opted_out": 1,
}
MIN_REASONS = 3
MAX_REASONS = 5
NOTABLE = 0.1  # log-odds; a reason past the first three must move the risk at least this much


def encode(features: Features) -> list[float]:
    row: list[float] = []
    for name in FEATURES:
        value = getattr(features, name)
        if value is None:
            row.append(math.nan)
        elif name in CATEGORIES:
            row.append(float(CATEGORIES[name].index(value)))
        else:
            row.append(float(value))
    return row


def _times(n: int, one: str, many: str) -> str:
    return one if n == 1 else many.format(n=n)


def _days(n: int) -> str:
    return "today" if n == 0 else _times(n, "1 day ago", "{n} days ago")


def describe(name: str, value: Any, weight: float = 0.0) -> str:
    """The fact behind a reason, in the owner's words. Whether it raised or lowered the risk is
    the reason's weight. Contributions are measured against the average lead, so a reply can
    still raise the risk when most leads reply more; the words say so."""
    if name == "replies" and value and weight > 0:
        return _times(value, "Replied only once", "Only {n} replies")
    match name, value:
        case "stage", stage:
            return {
                "new": "Still a new lead",
                "contacted": "Contacted, no conversation yet",
                "engaged": "In conversation",
                "holding": "Holding a lot",
            }[stage]
        case "touches", 0:
            return "No messages sent yet"
        case "touches", n:
            return _times(n, "1 message sent", "{n} messages sent")
        case "replies", 0:
            return "No replies yet"
        case "replies", n:
            return _times(n, "Replied once", "Replied {n} times")
        case "hold_requests", 0:
            return "Hasn't asked to hold a lot"
        case "hold_requests", n:
            return _times(n, "Asked to hold a lot", "Asked to hold lots {n} times")
        case "hold_approved", approved:
            return "Has an approved hold" if approved else "No approved hold"
        case "days_since_first_contact", n:
            return f"First contact {_days(n)}"
        case "days_since_buyer_activity", None:
            return "Nothing from the buyer themselves yet"
        case "days_since_buyer_activity", n:
            return f"Last heard from {_days(n)}"
        case "opted_out", opted_out:
            return "Asked not to be emailed" if opted_out else "Open to email"
        case "lot_price_band", None:
            return "The lot has no price"
        case "lot_price_band", band:
            return {
                "low": "One of the lower-priced lots",
                "mid": "A mid-priced lot",
                "high": "One of the higher-priced lots",
            }[band]
        case "listing_type", None:
            return "Not tied to a lot"
        case "listing_type", kind:
            return "Land only" if kind == "land_only" else "A lot with a home"
        case "phase_release", None:
            return "Not tied to a lot"
        case "phase_release", release:
            return (
                "The lot's phase is released"
                if release == "released"
                else "The lot's phase isn't released yet"
            )
        case _:
            raise ValueError(f"no wording for feature {name}")


def explain(features: Features, contributions: list[float]) -> list[Reason]:
    """The features that moved the risk most: always three, up to five if they matter."""
    ranked = sorted(
        zip(FEATURES, contributions, strict=True), key=lambda pair: abs(pair[1]), reverse=True
    )
    chosen = [
        (name, weight)
        for i, (name, weight) in enumerate(ranked[:MAX_REASONS])
        if i < MIN_REASONS or abs(weight) >= NOTABLE
    ]
    return [
        Reason(
            code=name,
            text=describe(name, getattr(features, name), weight),
            weight=round(weight, 3),
        )
        for name, weight in chosen
    ]


@dataclass(frozen=True)
class Artifact:
    name: str
    model_text: str
    metadata: dict[str, Any]

    @property
    def version(self) -> str:
        return f"lgbm-{self.name}"


def read_artifact(name: str = CURRENT, folder: Path = MODELS) -> Artifact:
    return Artifact(
        name=name,
        model_text=(folder / f"{name}.txt").read_text(encoding="utf-8"),
        metadata=json.loads((folder / f"{name}.json").read_text(encoding="utf-8")),
    )


class ModelScorer:
    """Scores with a trained LightGBM model. Refuses a model trained on any other features."""

    def __init__(self, artifact: Artifact) -> None:
        import lightgbm as lgb

        if tuple(artifact.metadata["features"]) != FEATURES:
            raise ValueError(
                f"{artifact.name} was trained on {artifact.metadata['features']}, not {FEATURES}"
            )
        self.version = artifact.version
        self._booster = lgb.Booster(model_str=artifact.model_text)

    def predict(self, rows: list[list[float]]) -> list[float]:
        found = self._booster.predict(np.array(rows, dtype=float))  # pyright: ignore[reportUnknownMemberType]
        return [float(p) for p in np.asarray(found).ravel()]

    def score(self, features: Features) -> Score:
        row = np.array([encode(features)], dtype=float)
        risk = self.predict([encode(features)])[0]
        contrib = self._booster.predict(row, pred_contrib=True)  # pyright: ignore[reportUnknownMemberType]
        # One column per feature, then the model's baseline.
        per_feature = [float(c) for c in np.asarray(contrib)[0][: len(FEATURES)]]
        return Score(
            model_version=self.version,
            score=round(risk, 3),
            reasons=explain(features, per_feature),
        )


@cache
def current_scorer() -> ModelScorer:
    return ModelScorer(read_artifact())
