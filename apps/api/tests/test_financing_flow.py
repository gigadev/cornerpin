"""P3-06: buyers apply, owners decide, lend and record payments (ADR-049, ADR-050)."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import text

from cornerpin.core.outbox import drain
from cornerpin.seed import DEMO_OWNER_EMAIL, DEMO_TENANT_ID

from .conftest import Databases, TenantData
from .test_financing import BASE

Signer = Any  # conftest's client_for: an email in, a signed-in TestClient out


def _lot(db: Databases, number: str) -> str:
    with db.owner.connect() as conn:
        found: UUID = conn.execute(
            text("SELECT id FROM lots WHERE tenant_id = :t AND number = :n"),
            {"t": DEMO_TENANT_ID, "n": number},
        ).scalar_one()
    return str(found)


def _apply(buyer: TestClient, lot: str, **changes: Any) -> Any:
    body: dict[str, Any] = {
        "name": "Sky Buyer",
        "down_payment": 20_000,
        "term_months": 360,
        "income_band": "under_50k",
    }
    return buyer.post(f"/v1/lots/{lot}/financing-applications", json=body | changes)


def _application(owner: TestClient, application_id: str) -> dict[str, Any]:
    found: dict[str, Any] = owner.get(f"{BASE}/applications/{application_id}").json()
    return found


def test_an_available_lot_offers_the_demo_terms_and_others_dont(
    db: Databases, demo: None, anonymous: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    offer = anonymous.get(f"/v1/lots/{_lot(db, '3-3')}/financing")
    assert offer.status_code == 200
    body = offer.json()
    assert body["annual_rate"] == "0.075"
    assert body["terms"] == [60, 120, 180, 240, 360]
    assert Decimal(body["min_down"]) < Decimal(body["max_down"]) < Decimal(body["price"])
    assert anonymous.get(f"/v1/lots/{_lot(db, '2-9')}/financing").status_code == 404  # sold
    alpha, _ = tenants
    assert anonymous.get(f"/v1/lots/{alpha.lot_id}/financing").status_code == 404


def test_a_buyer_applies_once_and_within_the_down_payment_range(
    db: Databases, demo: None, client_for: Signer, anonymous: TestClient
) -> None:
    lot = _lot(db, "3-3")
    buyer = client_for("applicant-once@example.test")
    assert _apply(anonymous, lot).status_code == 401
    too_little = _apply(buyer, lot, down_payment=1)
    assert too_little.status_code == 422
    assert "between" in too_little.json()["detail"]
    assert _apply(buyer, lot).status_code == 201
    assert _apply(buyer, lot).status_code == 409
    [mine] = buyer.get("/v1/me/financing-applications").json()
    assert (mine["status"], mine["lot_number"], mine["decision"]) == ("submitted", "3-3", None)
    assert Decimal(mine["monthly_payment"]) > 0


def test_a_lot_of_a_tenant_without_the_demo_takes_no_application(
    client_for: Signer, tenants: tuple[TenantData, TenantData], demo: None
) -> None:
    alpha, _ = tenants
    buyer = client_for("applicant-alpha@example.test")
    assert _apply(buyer, str(alpha.lot_id)).status_code == 404


def test_a_decline_tells_the_buyer_why_and_logs_the_score_shown(
    db: Databases, client_for: Signer, demo_owner: TestClient
) -> None:
    buyer = client_for("applicant-declined@example.test")
    application_id = _apply(buyer, _lot(db, "3-3")).json()["id"]
    drain()
    shown = _application(demo_owner, application_id)["score"]
    url = f"{BASE}/applications/{application_id}/decision"

    assert demo_owner.post(url, json={"decision": "decline"}).status_code == 422  # no reason
    declined = demo_owner.post(
        url,
        json={"decision": "decline", "reason": "Too much of the income.", "score_id": shown["id"]},
    )
    assert declined.status_code == 200, declined.text
    decision = declined.json()["decision"]
    raised = [r["text"] for r in shown["reasons"] if r["weight"] > 0][:4]
    assert raised and decision["principal_reasons"] == raised
    assert decision["decided_by_email"] == DEMO_OWNER_EMAIL
    assert demo_owner.post(url, json={"decision": "approve"}).status_code == 409

    [mine] = buyer.get("/v1/me/financing-applications").json()
    assert mine["status"] == "declined"
    assert mine["decision"]["reason"] == "Too much of the income."
    assert mine["decision"]["principal_reasons"] == raised


def test_an_approval_opens_a_loan_whose_schedule_balances_and_takes_payments(
    db: Databases, client_for: Signer, demo_owner: TestClient
) -> None:
    buyer = client_for("applicant-approved@example.test")
    made = _apply(buyer, _lot(db, "3-3"), down_payment=40_000, income_band="over_150k")
    application_id = made.json()["id"]
    approved = demo_owner.post(
        f"{BASE}/applications/{application_id}/decision", json={"decision": "approve"}
    )
    assert approved.status_code == 200
    assert approved.json()["decision"]["principal_reasons"] == []

    loans = demo_owner.get(f"{BASE}/loans").json()
    [loan] = [loan for loan in loans if loan["application_id"] == application_id]
    detail = demo_owner.get(f"{BASE}/loans/{loan['id']}").json()
    assert len(detail["schedule"]) == 360
    assert detail["schedule"][-1]["balance"] == "0.00"
    principal = sum(Decimal(row["principal"]) for row in detail["schedule"])
    assert principal == Decimal(detail["principal"])
    first_due = date.fromisoformat(detail["first_due_on"])
    assert first_due.day == 1 and first_due > date.today()

    payments = f"{BASE}/loans/{loan['id']}/payments"
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    ahead = demo_owner.post(payments, json={"amount": "10.00", "paid_on": tomorrow})
    assert ahead.status_code == 422
    assert demo_owner.post(payments, json={"amount": "99999999.00"}).status_code == 422
    paid = demo_owner.post(payments, json={"amount": detail["monthly_payment"]})
    assert paid.status_code == 201, paid.text
    after = paid.json()
    assert after["paid_to_date"] == detail["monthly_payment"]
    assert after["outstanding_balance"] == detail["schedule"][0]["balance"]
    assert after["payments"][-1]["recorded_by_email"] == DEMO_OWNER_EMAIL

    [mine] = buyer.get("/v1/me/financing-applications").json()
    assert mine["status"] == "approved"


def test_a_score_from_another_application_is_refused(
    db: Databases, client_for: Signer, demo_owner: TestClient
) -> None:
    first = _apply(client_for("applicant-one@example.test"), _lot(db, "3-3")).json()["id"]
    second = _apply(client_for("applicant-two@example.test"), _lot(db, "3-3")).json()["id"]
    drain()
    other_score = _application(demo_owner, first)["score"]["id"]
    refused = demo_owner.post(
        f"{BASE}/applications/{second}/decision",
        json={"decision": "approve", "score_id": other_score},
    )
    assert refused.status_code == 422
    assert _application(demo_owner, second)["status"] == "submitted"


def test_buyers_see_only_their_own_and_cannot_decide(
    db: Databases, demo: None, client_for: Signer
) -> None:
    applicant = client_for("applicant-own@example.test")
    application_id = _apply(applicant, _lot(db, "3-3")).json()["id"]
    stranger = client_for("applicant-stranger@example.test")
    assert stranger.get("/v1/me/financing-applications").json() == []
    decide = applicant.post(
        f"{BASE}/applications/{application_id}/decision", json={"decision": "approve"}
    )
    assert decide.status_code == 404


def test_the_portal_knows_which_tenant_has_the_demo(
    demo_owner: TestClient, alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    assert demo_owner.get(f"/v1/tenants/{DEMO_TENANT_ID}").json()["financing_demo"] is True
    assert alpha_owner.get(f"/v1/tenants/{alpha.tenant_id}").json()["financing_demo"] is False
    some = UUID(int=1)
    deciding = {"decision": "approve"}
    url = f"/v1/tenants/{alpha.tenant_id}/financing"
    assert alpha_owner.post(f"{url}/applications/{some}/decision", json=deciding).status_code == 404
    paying = alpha_owner.post(f"{url}/loans/{some}/payments", json={"amount": "1.00"})
    assert paying.status_code == 404
