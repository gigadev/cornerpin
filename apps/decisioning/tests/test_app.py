"""The decisioning service's endpoint (ADR-048)."""

from fastapi.testclient import TestClient

from cornerpin_decisioning.app import app

client = TestClient(app)

FEATURES = {
    "stage": "engaged",
    "touches": 2,
    "replies": 1,
    "hold_requests": 1,
    "hold_approved": False,
    "days_since_first_contact": 9,
    "days_since_buyer_activity": 2,
    "opted_out": False,
    "lot_price_band": "mid",
    "listing_type": "land_only",
    "phase_release": "released",
}


def test_health_names_the_model() -> None:
    assert client.get("/health").json() == {"status": "ok", "model_version": "lgbm-lead-v1"}


def test_a_score_comes_back_with_its_reasons() -> None:
    found = client.post("/v1/score", json={"features": FEATURES})
    assert found.status_code == 200
    body = found.json()
    assert body["model_version"] == "lgbm-lead-v1"
    assert 0 < body["score"] < 1
    assert len(body["reasons"]) >= 3
    assert {"code", "text", "weight"} == set(body["reasons"][0])


def test_anything_beyond_the_contract_is_refused() -> None:
    planted = client.post("/v1/score", json={"features": FEATURES | {"buyer_age": 40}})
    assert planted.status_code == 422
    missing = {k: v for k, v in FEATURES.items() if k != "replies"}
    assert client.post("/v1/score", json={"features": missing}).status_code == 422
