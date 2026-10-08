"""P3-01: risk scores and decisions (ADR-013, ADR-045)."""

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
from cornerpin.decisioning.scoring import RulesBaseline

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
    assert set(LeadFeatures.model_fields) == ALLOWED_FEATURES
    assert [f for f in LeadFeatures.model_fields if looks_personal(f)] == []


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
    assert score.model_version == "rules-v1"
    assert set(score.inputs) == ALLOWED_FEATURES
    assert score.inputs["stage"] == "new"
    assert score.inputs["listing_type"] == "land_only"
    assert score.inputs["phase_release"] == "upcoming"
    assert score.inputs["days_since_buyer_activity"] == 0
    assert 0 < score.score < 1
    assert [r["code"] for r in score.reasons] == ["recent", "phase_upcoming"]
    assert score.reasons[0]["text"] == "Active in the last week"


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


def test_replying_and_asking_for_a_hold_scores_better_than_going_quiet() -> None:
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
