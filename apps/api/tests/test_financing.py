"""P3-05: the owner-financing demo's schema, seed, read routes and application scores (ADR-013,
ADR-049)."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from cornerpin.core.auth import service
from cornerpin.core.auth.deps import SESSION_COOKIE
from cornerpin.core.outbox import drain
from cornerpin.decisioning.features import ApplicationFeatures
from cornerpin.financing.amortization import add_months, monthly_payment, schedule
from cornerpin.financing.demo import APPLICANTS
from cornerpin.financing.standing import standing
from cornerpin.main import create_app
from cornerpin.seed import DEMO_OWNER_EMAIL, DEMO_TENANT_ID, seed

from .conftest import Databases, TenantData
from .test_decisioning import looks_personal

# What an application's score may look at (ADR-049): its terms, the share of stated income
# the payment would take, and the lot. Adding one means changing the ADR and this list.
ALLOWED_APPLICATION_FEATURES = {
    "down_payment_ratio",
    "term_months",
    "payment_to_income",
    "lot_price_band",
    "listing_type",
}
# Features the personal-word check flags but Scott approved on 2026-10-08: affordability, the
# loan's payment as a share of stated income, and nothing else about the buyer (ADR-049).
APPROVED_EXCEPTIONS = {"payment_to_income"}

# --- amortization, to the cent --------------------------------------------------------------


def test_the_level_payment_matches_the_textbook() -> None:
    assert monthly_payment(Decimal(100_000), Decimal("0.075"), 360) == Decimal("699.21")
    assert monthly_payment(Decimal(12_000), Decimal(0), 12) == Decimal("1000.00")


@pytest.mark.parametrize("principal", ["1.00", "88000.00", "431999.99", "629000.00"])
@pytest.mark.parametrize("rate", ["0", "0.0399", "0.075", "0.12"])
@pytest.mark.parametrize("months", [1, 60, 240, 360])
def test_every_schedule_balances_to_the_cent(principal: str, rate: str, months: int) -> None:
    rows = schedule(Decimal(principal), Decimal(rate), months, date(2026, 1, 31))
    assert len(rows) == months
    assert sum(row.principal for row in rows) == Decimal(principal)
    assert rows[-1].balance == Decimal("0.00")
    owed = Decimal(principal)
    for row in rows:
        assert row.payment == row.principal + row.interest
        owed -= row.principal
        assert row.balance == owed >= 0
        assert row.principal.as_tuple().exponent == -2


def test_due_dates_step_by_month_and_keep_to_the_month_end() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 1), 3) == date(2027, 2, 1)
    assert add_months(date(2026, 3, 1), -2) == date(2026, 1, 1)


# --- where a loan stands --------------------------------------------------------------------


def _rows() -> list[Any]:
    return schedule(Decimal(10_000), Decimal("0.075"), 12, date(2026, 1, 1))


def test_a_loan_paid_up_to_date_is_current() -> None:
    rows = _rows()
    paid = sum((row.payment for row in rows[:3]), Decimal(0))
    now = standing(Decimal(10_000), rows, paid, date(2026, 3, 15))
    assert (now.past_due, now.days_past_due) == (Decimal(0), 0)
    assert now.outstanding_balance == rows[2].balance
    assert now.next_due_on == date(2026, 4, 1)


def test_a_loan_two_payments_behind_is_late_from_the_oldest_unpaid() -> None:
    rows = _rows()
    paid = sum((row.payment for row in rows[:1]), Decimal(0))
    now = standing(Decimal(10_000), rows, paid, date(2026, 3, 15))
    assert now.past_due == rows[1].payment + rows[2].payment
    assert now.days_past_due == (date(2026, 3, 15) - date(2026, 2, 1)).days
    assert now.outstanding_balance == rows[0].balance


def test_a_part_payment_doesnt_count_as_an_installment() -> None:
    rows = _rows()
    now = standing(Decimal(10_000), rows, rows[0].payment - Decimal("0.01"), date(2026, 1, 5))
    assert now.outstanding_balance == Decimal(10_000)
    assert now.past_due == Decimal("0.01")
    assert now.days_past_due == 4


# --- the seeded demo ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def demo(db: Databases, tenants: tuple[TenantData, TenantData]) -> Iterator[None]:
    """The demo tenant, seeded as it is everywhere else, financing included."""
    with db.owner.begin() as conn:
        seed(conn)
    yield


@pytest.fixture
def demo_owner(demo: None) -> Iterator[TestClient]:
    with TestClient(create_app()) as client:
        signed_in = service.sign_in_verified_email(DEMO_OWNER_EMAIL, None, "/app", "pytest")
        client.cookies.set(SESSION_COOKIE, signed_in.session_token)
        yield client


BASE = f"/v1/tenants/{DEMO_TENANT_ID}/financing"


def test_the_seeded_schedules_balance_to_the_cent(db: Databases, demo: None) -> None:
    with db.owner.connect() as conn:
        loans = conn.execute(
            text(
                "SELECT l.id, l.principal, l.term_months, count(s.*) AS installments,"
                " sum(s.principal) AS principal_paid, bool_and(s.payment = s.principal"
                " + s.interest) AS parts_add_up,"
                " (SELECT balance FROM loan_schedules WHERE loan_id = l.id"
                "  ORDER BY number DESC LIMIT 1) AS last_balance"
                " FROM loans l JOIN loan_schedules s ON s.loan_id = l.id"
                " WHERE l.tenant_id = :t GROUP BY l.id"
            ),
            {"t": DEMO_TENANT_ID},
        ).all()
    assert len(loans) == sum(1 for a in APPLICANTS if a.outcome == "loan")
    for loan in loans:
        assert loan.installments == loan.term_months
        assert loan.principal_paid == loan.principal
        assert loan.last_balance == Decimal("0.00")
        assert loan.parts_add_up


def test_the_owner_sees_the_applications_with_their_decisions(demo_owner: TestClient) -> None:
    found = demo_owner.get(f"{BASE}/applications")
    assert found.status_code == 200
    applications = found.json()
    assert len(applications) == len(APPLICANTS)
    assert [a["status"] for a in applications[:3]] == ["submitted"] * 3
    assert all("(synthetic)" in a["applicant_name"] for a in applications)
    assert all(a["applicant_email"].endswith("@synthetic.example") for a in applications)
    declined = [a for a in applications if a["status"] == "declined"]
    assert declined and all(a["decision"]["kind"] == "declined" for a in declined)
    assert all(a["decision"]["decided_by_email"] is None for a in declined)
    one = demo_owner.get(f"{BASE}/applications/{applications[0]['id']}")
    assert one.json()["id"] == applications[0]["id"]
    assert isinstance(one.json()["amount"], str)


def test_the_owner_sees_loans_and_which_are_behind(demo_owner: TestClient) -> None:
    loans = demo_owner.get(f"{BASE}/loans").json()
    behind = {
        loan["applicant_name"]: loan["days_past_due"]
        for loan in loans
        if loan["past_due"] != "0.00"
    }
    late = {f"{a.name} (synthetic)" for a in APPLICANTS if a.outcome == "loan" and a.missed}
    assert set(behind) == late
    assert all(days > 0 for days in behind.values())

    detail = demo_owner.get(f"{BASE}/loans/{loans[0]['id']}").json()
    assert len(detail["schedule"]) == detail["term_months"]
    assert detail["schedule"][-1]["balance"] == "0.00"
    assert detail["payments"] and detail["payments"][0]["recorded_by_email"] is None
    paid = sum(Decimal(p["amount"]) for p in detail["payments"])
    assert Decimal(detail["paid_to_date"]) == paid


def test_a_tenant_without_the_switch_gets_404_on_every_financing_route(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData], demo: None
) -> None:
    alpha, _ = tenants
    some = UUID(int=1)
    for path in ("applications", f"applications/{some}", "loans", f"loans/{some}"):
        url = f"/v1/tenants/{alpha.tenant_id}/financing/{path}"
        assert alpha_owner.get(url).status_code == 404, url
    # Nor can a tenant without the switch reach the demo tenant's.
    assert alpha_owner.get(f"{BASE}/applications").status_code == 404


def test_only_a_demo_tenant_can_have_the_financing_demo(
    db: Databases, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    with pytest.raises(IntegrityError), db.owner.begin() as conn:
        conn.execute(
            text("UPDATE tenants SET financing_demo = true WHERE id = :t"),
            {"t": alpha.tenant_id},
        )


# --- application scores ---------------------------------------------------------------------


def test_an_application_score_sees_only_its_allowed_features() -> None:
    names = tuple(ApplicationFeatures.model_fields)
    assert set(names) == ALLOWED_APPLICATION_FEATURES
    assert {name for name in names if looks_personal(name)} == APPROVED_EXCEPTIONS


def test_the_service_takes_exactly_the_api_application_features() -> None:
    from cornerpin_decisioning.contract import ApplicationFeatures as Theirs
    from cornerpin_decisioning.model import CURRENT_APPLICATION, read_artifact

    ours, theirs = ApplicationFeatures.model_json_schema(), Theirs.model_json_schema()
    assert ours["properties"] == theirs["properties"]
    assert ours["required"] == theirs["required"]
    assert set(read_artifact(CURRENT_APPLICATION).metadata["features"]) == (
        ALLOWED_APPLICATION_FEATURES
    )


def test_waiting_applications_are_scored_with_reasons(
    db: Databases, demo_owner: TestClient
) -> None:
    drain()
    applications = demo_owner.get(f"{BASE}/applications").json()
    waiting = [a for a in applications if a["status"] == "submitted"]
    assert waiting
    for application in waiting:
        score = application["score"]
        assert score["model_version"] == "lgbm-application-v1"
        assert len(score["reasons"]) >= 3
    # Decided ones aren't scored: the question no longer applies.
    assert all(a["score"] is None for a in applications if a["status"] != "submitted")
    with db.owner.connect() as conn:
        inputs = conn.execute(
            text(
                "SELECT inputs FROM risk_scores WHERE financing_application_id = :a"
                " ORDER BY scored_at DESC LIMIT 1"
            ),
            {"a": waiting[0]["id"]},
        ).scalar_one()
    assert set(inputs) == ALLOWED_APPLICATION_FEATURES
