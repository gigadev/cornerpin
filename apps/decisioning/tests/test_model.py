"""The lead model (P3-02, ADR-046), now in the decisioning service (ADR-048)."""

from typing import Any

import pytest

from cornerpin_decisioning.contract import Features
from cornerpin_decisioning.model import (
    FEATURES,
    MIN_REASONS,
    Artifact,
    ModelScorer,
    current_scorer,
    describe,
    encode,
    explain,
    read_artifact,
)
from cornerpin_decisioning.training import generate, train


def features(**changes: Any) -> Features:
    base: dict[str, Any] = {
        "stage": "contacted",
        "touches": 1,
        "replies": 0,
        "hold_requests": 0,
        "hold_approved": False,
        "days_since_first_contact": 3,
        "days_since_buyer_activity": 3,
        "opted_out": False,
        "lot_price_band": "mid",
        "listing_type": "land_only",
        "phase_release": "released",
    }
    return Features.model_validate(base | changes)


def test_the_artifact_was_trained_on_the_contract_features() -> None:
    assert read_artifact().metadata["features"] == list(FEATURES)


def test_a_model_trained_with_a_planted_personal_attribute_is_refused() -> None:
    planted = train(rows=1500, rounds=20, plant="buyer_age")
    assert planted.features != list(FEATURES)
    with pytest.raises(ValueError, match="buyer_age"):
        ModelScorer(Artifact("planted", planted.model_text, planted.metadata))


def test_the_training_script_reproduces_the_artifact() -> None:
    committed = read_artifact()
    settings = committed.metadata["training"]
    retrained = train(rows=settings["rows"], seed=settings["seed"], rounds=settings["rounds"])
    assert retrained.metadata["metrics"] == committed.metadata["metrics"]
    probe = [encode(f) for f in generate(300, seed=99)[0]]
    again = ModelScorer(Artifact("retrained", retrained.model_text, retrained.metadata))
    assert again.predict(probe) == pytest.approx(ModelScorer(committed).predict(probe), abs=1e-4)


def test_replying_and_asking_for_a_hold_scores_better_than_going_quiet() -> None:
    model = current_scorer()
    keen = model.score(
        features(stage="engaged", replies=1, hold_requests=1, days_since_buyer_activity=2)
    )
    quiet = model.score(
        features(touches=3, days_since_buyer_activity=40, days_since_first_contact=45)
    )
    assert keen.score < 0.5 < quiet.score
    assert keen.reasons[0].text == "Asked to hold a lot"
    assert keen.reasons[0].weight < 0
    assert {"touches", "replies", "days_since_buyer_activity"} <= {r.code for r in quiet.reasons}
    assert all(r.weight > 0 for r in quiet.reasons[:3])


def test_every_synthetic_lead_gets_at_least_three_reasons_in_words() -> None:
    model = current_scorer()
    for lead in generate(400, seed=5)[0]:
        result = model.score(lead)
        assert len(result.reasons) >= MIN_REASONS
        assert all(r.text for r in result.reasons)


def test_a_reply_that_raises_the_risk_says_only() -> None:
    assert describe("replies", 1, 0.2) == "Replied only once"
    assert describe("replies", 2, -0.2) == "Replied 2 times"
    reasons = explain(features(replies=1), [0.0, 0.0, 0.3] + [0.0] * 8)
    assert reasons[0].text == "Replied only once"
