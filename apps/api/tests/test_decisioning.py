"""P3-01 and P3-02: risk scores, the lead model and decisions (ADR-013, ADR-045, ADR-046)."""

from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from cornerpin.core.db import user_session, worker_session
from cornerpin.core.outbox import drain, enqueue
from cornerpin.decisioning.events import ScoreLead
from cornerpin.decisioning.features import LeadFeatures, price_band
from cornerpin.decisioning.model import (
    MIN_REASONS,
    Artifact,
    ModelScorer,
    describe,
    encode,
    explain,
    read_artifact,
)
from cornerpin.decisioning.scoring import RulesBaseline, get_scorer
from cornerpin.decisioning.training import generate, train

from .conftest import Databases, Listing, TenantData
from .outreach_support import email_of, inquire, lead_of

# The whole list a score may look at. Adding a feature means changing ADR-045 and this list.
ALLOWED_FEATURES = {
    "stage",
    "touches",
    "replies",
    "hold_requests",
    "hold_approved",
    "days_since_first_contact",
    "days_since_buyer_activity",
    "opted_out",
    "lot_price_band",
    "listing_type",
    "phase_release",
}

# Nothing about the person, or what could stand in for a protected class (ADR-013). Each word
# of a feature's name is checked against these as a prefix.
PERSONAL = (
    "name", "email", "phone", "address", "zip", "postal", "city", "state", "county", "location",
    "latitude", "longitude", "zone", "timezone", "ip", "device", "agent", "age", "birth",
    "gender", "sex", "race", "ethnic", "religion", "marital", "family", "children", "income",
    "credit", "nationality", "language", "disab", "veteran", "message", "body",
)  # fmt: skip


def looks_personal(feature: str) -> bool:
    return any(part.startswith(PERSONAL) for part in feature.split("_"))


def assert_allowed(features: list[str] | tuple[str, ...]) -> None:
    """The feature test: exactly the allowed list, and nothing that looks personal."""
    assert set(features) == ALLOWED_FEATURES
    assert [f for f in features if looks_personal(f)] == []


def scores(db: Databases, lead_id: UUID) -> list[Any]:
    with db.owner.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT model_version, score, inputs, reasons FROM risk_scores"
                    " WHERE lead_id = :id ORDER BY scored_at, id"
                ),
                {"id": lead_id},
            ).all()
        )


def score_now(lead_id: UUID) -> None:
    with worker_session() as session:
        enqueue(session, ScoreLead(lead_id=lead_id))
    drain()


def features(**changes: Any) -> LeadFeatures:
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
    return LeadFeatures.model_validate(base | changes)


def test_a_score_sees_only_the_allowed_features() -> None:
    assert_allowed(tuple(LeadFeatures.model_fields))
    assert_allowed(read_artifact().metadata["features"])


def test_a_model_trained_with_a_planted_personal_attribute_fails_the_feature_test() -> None:
    planted = train(rows=1500, rounds=20, plant="buyer_age")
    with pytest.raises(AssertionError):
        assert_allowed(planted.features)
    with pytest.raises(ValueError, match="buyer_age"):
        ModelScorer(
            Artifact(name="planted", model_text=planted.model_text, metadata=planted.metadata)
        )


def test_the_training_script_reproduces_the_artifact() -> None:
    committed = read_artifact()
    settings = committed.metadata["training"]
    retrained = train(rows=settings["rows"], seed=settings["seed"], rounds=settings["rounds"])
    assert retrained.metadata["metrics"] == committed.metadata["metrics"]
    probe = [encode(f) for f in generate(300, seed=99)[0]]
    again = ModelScorer(Artifact("retrained", retrained.model_text, retrained.metadata))
    assert again.predict(probe) == pytest.approx(ModelScorer(committed).predict(probe), abs=1e-4)


@pytest.mark.parametrize(
    "name", ["buyer_age", "email_domain", "zip_code", "time_zone", "ethnicity"]
)
def test_the_personal_check_catches_personal_names(name: str) -> None:
    assert looks_personal(name)


def test_a_new_lead_is_scored_with_reasons_within_one_drain(
    db: Databases, listing: Listing, buyer: TestClient, outreach_mail: object
) -> None:
    inquire(buyer, listing, allow_email=True)
    lead_id = lead_of(db, listing, email_of(buyer))
    drain()

    [score] = scores(db, lead_id)
    assert score.model_version == "lgbm-lead-v1"
    assert set(score.inputs) == ALLOWED_FEATURES
    assert score.inputs["stage"] == "new"
    assert score.inputs["listing_type"] == "land_only"
    assert score.inputs["phase_release"] == "upcoming"
    assert score.inputs["days_since_buyer_activity"] == 0
    assert 0 < score.score < 1
    assert len(score.reasons) >= MIN_REASONS
    assert {r["code"] for r in score.reasons} <= ALLOWED_FEATURES
    assert all(r["text"] and r["weight"] != 0 for r in score.reasons)


def test_the_same_history_is_scored_once(
    db: Databases, listing: Listing, buyer: TestClient, outreach_mail: object
) -> None:
    inquire(buyer, listing, allow_email=True)
    lead_id = lead_of(db, listing, email_of(buyer))
    drain()
    score_now(lead_id)
    assert len(scores(db, lead_id)) == 1


def test_won_and_lost_leads_are_not_scored(
    db: Databases, listing: Listing, buyer: TestClient, outreach_mail: object
) -> None:
    inquire(buyer, listing, allow_email=True)
    lead_id = lead_of(db, listing, email_of(buyer))
    drain()
    with db.owner.begin() as conn:
        conn.execute(text("DELETE FROM risk_scores WHERE lead_id = :id"), {"id": lead_id})
        conn.execute(text("UPDATE leads SET stage = 'lost' WHERE id = :id"), {"id": lead_id})
    score_now(lead_id)
    assert scores(db, lead_id) == []


def test_the_model_scores_replying_and_asking_for_a_hold_better_than_going_quiet() -> None:
    model = get_scorer()
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
    model = get_scorer()
    for lead in generate(400, seed=5)[0]:
        result = model.score(lead)
        assert len(result.reasons) >= MIN_REASONS
        assert all(r.text for r in result.reasons)


def test_a_reply_that_raises_the_risk_says_only() -> None:
    assert describe("replies", 1, 0.2) == "Replied only once"
    assert describe("replies", 2, -0.2) == "Replied 2 times"
    reasons = explain(features(replies=1), [0.0, 0.0, 0.3] + [0.0] * 8)
    assert reasons[0].text == "Replied only once"


def test_the_rules_baseline_scores_replying_and_asking_for_a_hold_better_than_going_quiet() -> None:
    rules = RulesBaseline()
    keen = rules.score(features(replies=1, hold_requests=1, days_since_buyer_activity=2))
    quiet = rules.score(features(touches=3, days_since_buyer_activity=40))
    assert keen.score < 0.5 < quiet.score
    assert [r.code for r in quiet.reasons] == ["no_reply", "quiet"]
    assert quiet.reasons[0].text == "No reply to 3 messages"
    assert {r.code for r in keen.reasons} == {"replied", "asked_for_hold", "recent"}


def test_an_opted_out_lead_is_a_higher_risk() -> None:
    rules = RulesBaseline()
    assert rules.score(features(opted_out=True)).score > rules.score(features()).score


def test_a_lead_with_no_history_still_gets_a_reason() -> None:
    result = RulesBaseline().score(features(touches=0, days_since_buyer_activity=None))
    assert [r.code for r in result.reasons] == ["little_history"]
    assert result.score == 0.5


@pytest.mark.parametrize(
    ("rank", "band"), [(None, None), (0.0, "low"), (0.5, "mid"), (1.0, "high")]
)
def test_price_bands(rank: float | None, band: str | None) -> None:
    assert price_band(rank) == band


def test_owners_read_their_scores_and_buyers_do_not(
    db: Databases, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    query = text("SELECT count(*) FROM risk_scores")
    with user_session(alpha.owner_id, alpha.tenant_id, engine=db.api) as session:
        assert session.execute(query).scalar_one() > 0
        with pytest.raises(ProgrammingError):
            session.execute(text("UPDATE risk_scores SET score = 0"))
    with user_session(alpha.buyer_id, alpha.tenant_id, engine=db.api) as session:
        assert session.execute(query).scalar_one() == 0


def _decide(db: Databases, tenant: TenantData, decided_by: UUID) -> None:
    with user_session(tenant.owner_id, tenant.tenant_id, engine=db.api) as session:
        session.execute(
            text(
                "INSERT INTO decisions (tenant_id, lead_id, kind, decided_by, decided_by_email)"
                " SELECT tenant_id, id, 'lead_lost', :by, 'owner@alpha.test' FROM leads"
                " WHERE tenant_id = :t AND user_id = :b"
            ),
            {"t": tenant.tenant_id, "b": tenant.buyer_id, "by": decided_by},
        )


def test_decisions_are_made_as_yourself_and_never_changed(
    db: Databases, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    _decide(db, alpha, alpha.owner_id)
    with pytest.raises(ProgrammingError):
        _decide(db, alpha, alpha.buyer_id)
    for change in ("UPDATE decisions SET note = 'edited'", "DELETE FROM decisions"):
        with (
            pytest.raises(ProgrammingError),
            user_session(alpha.owner_id, alpha.tenant_id, engine=db.api) as session,
        ):
            session.execute(text(change))


def test_the_worker_scores_but_never_decides(db: Databases) -> None:
    with pytest.raises(ProgrammingError), worker_session() as session:
        session.execute(text("SELECT count(*) FROM decisions"))


# --- P3-03: scores where owners decide, and the decisions they log (ADR-047) -----------------


def _lead_page(owner: TestClient, listing: Listing, lead_id: UUID) -> dict[str, Any]:
    found: dict[str, Any] = owner.get(
        f"/v1/tenants/{listing.tenant.tenant_id}/leads/{lead_id}"
    ).json()
    return found


def _held(owner: TestClient, buyer: TestClient, listing: Listing) -> dict[str, Any]:
    """A buyer asks to hold the available lot; the owner's view of that hold, once scored."""
    asked = buyer.post(f"/v1/lots/{listing.available}/hold-requests", json={"name": "Sky Buyer"})
    assert asked.status_code == 201, asked.text
    drain()
    email = email_of(buyer)
    holds: list[dict[str, Any]] = owner.get(
        f"/v1/tenants/{listing.tenant.tenant_id}/hold-requests"
    ).json()
    return next(h for h in holds if h["email"] == email)


def _decide_hold(
    owner: TestClient, listing: Listing, hold: dict[str, Any], score_id: str | None, decision: str
) -> Any:
    return owner.post(
        f"/v1/tenants/{listing.tenant.tenant_id}/hold-requests/{hold['id']}/decision",
        json={"decision": decision, "score_id": score_id},
    )


def test_leads_and_holds_show_the_latest_score(
    db: Databases,
    listing: Listing,
    buyer: TestClient,
    alpha_owner: TestClient,
    outreach_mail: object,
) -> None:
    hold = _held(alpha_owner, buyer, listing)
    lead_id = UUID(hold["lead_id"])
    leads = alpha_owner.get(f"/v1/tenants/{listing.tenant.tenant_id}/leads").json()["leads"]
    [lead] = [lead for lead in leads if lead["id"] == str(lead_id)]
    assert lead["score"]["model_version"] == "lgbm-lead-v1"
    assert len(lead["score"]["reasons"]) >= MIN_REASONS
    assert hold["score"]["id"] == lead["score"]["id"]
    assert _lead_page(alpha_owner, listing, lead_id)["score"]["id"] == lead["score"]["id"]


def test_deciding_a_hold_logs_who_decided_and_the_score_they_saw(
    db: Databases,
    listing: Listing,
    buyer: TestClient,
    alpha_owner: TestClient,
    outreach_mail: object,
) -> None:
    hold = _held(alpha_owner, buyer, listing)
    shown = hold["score"]
    decided = _decide_hold(alpha_owner, listing, hold, shown["id"], "approve")
    assert decided.status_code == 200, decided.text

    events = _lead_page(alpha_owner, listing, UUID(hold["lead_id"]))["events"]
    decision = events[0]
    assert decision["kind"] == "decision"
    assert decision["actor_email"] == "owner@alpha.test"
    assert decision["decision"]["kind"] == "hold_approved"
    assert decision["decision"]["score"] == shown
    assert decision["lot"]["lot_id"] == listing.available
    assert "hold_approved" in [e["kind"] for e in events]


def test_a_hold_decided_without_a_score_says_none_was_shown(
    db: Databases,
    listing: Listing,
    buyer: TestClient,
    alpha_owner: TestClient,
    outreach_mail: object,
) -> None:
    hold = _held(alpha_owner, buyer, listing)
    assert _decide_hold(alpha_owner, listing, hold, None, "decline").status_code == 200
    decision = _lead_page(alpha_owner, listing, UUID(hold["lead_id"]))["events"][0]
    assert decision["decision"] == {"kind": "hold_declined", "score": None}


def test_a_score_from_another_lead_is_refused_and_nothing_changes(
    db: Databases,
    tenants: tuple[TenantData, TenantData],
    listing: Listing,
    buyer: TestClient,
    alpha_owner: TestClient,
    outreach_mail: object,
) -> None:
    alpha, _ = tenants
    with db.owner.connect() as conn:
        other = conn.execute(
            text(
                "SELECT r.id FROM risk_scores r JOIN leads l ON l.id = r.lead_id"
                " WHERE l.tenant_id = :t AND l.user_id = :b LIMIT 1"
            ),
            {"t": alpha.tenant_id, "b": alpha.buyer_id},
        ).scalar_one()
    hold = _held(alpha_owner, buyer, listing)
    refused = _decide_hold(alpha_owner, listing, hold, str(other), "approve")
    assert refused.status_code == 422
    holds = alpha_owner.get(f"/v1/tenants/{listing.tenant.tenant_id}/hold-requests").json()
    assert next(h for h in holds if h["id"] == hold["id"])["status"] == "pending"


def test_marking_a_lead_won_or_lost_is_a_decision_and_other_stages_are_not(
    db: Databases,
    listing: Listing,
    buyer: TestClient,
    alpha_owner: TestClient,
    outreach_mail: object,
) -> None:
    inquire(buyer, listing, allow_email=True)
    lead_id = lead_of(db, listing, email_of(buyer))
    drain()
    url = f"/v1/tenants/{listing.tenant.tenant_id}/leads/{lead_id}"
    shown = alpha_owner.get(url).json()["score"]

    def decided() -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = alpha_owner.get(url).json()["events"]
        return [e["decision"] for e in events if e["kind"] == "decision"]

    alpha_owner.patch(url, json={"stage": "contacted", "score_id": shown["id"]})
    assert decided() == []
    won = alpha_owner.patch(url, json={"stage": "won", "score_id": shown["id"]})
    assert won.status_code == 200, won.text
    alpha_owner.patch(url, json={"stage": "won", "score_id": shown["id"]})
    assert decided() == [{"kind": "lead_won", "score": shown}]
