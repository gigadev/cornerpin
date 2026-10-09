"""Owner financing in the owner portal (P3-05, ADR-049): applications and loans, read-only for
now (P3-06 adds applying, deciding and payments). Every route answers 404 unless the tenant
has the financing demo switched on, which only a demo tenant can."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import Row, text
from sqlalchemy.orm import Session

from cornerpin.core.auth.deps import CurrentUser, SignedInUser
from cornerpin.core.tenancy import tenant_session
from cornerpin.decisioning.decisions import latest_application_score_sql
from cornerpin.financing.amortization import monthly_payment
from cornerpin.financing.schemas import (
    ApplicationOut,
    Installment,
    LoanDetail,
    LoanSummary,
    Payment,
)
from cornerpin.financing.standing import standing

router = APIRouter(prefix="/tenants/{tenant_id}/financing", tags=["financing"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {
        "description": "Not found, not your tenant, or the tenant has no financing demo"
    }
}
LIST_LIMIT = 200

APPLICATIONS = f"""
    SELECT a.id, a.lot_id, lot.number AS lot_number, s.name AS subdivision_name,
           a.applicant_name, a.applicant_email, a.amount, a.down_payment, a.term_months,
           a.income_band::text AS income_band, a.status::text AS status, a.created_at,
           {latest_application_score_sql("a.id")} AS score,
           (SELECT jsonb_build_object('kind', d.kind, 'reason', d.reason,
                                      'decided_at', d.decided_at,
                                      'decided_by_email', d.decided_by_email)
            FROM financing_decisions d WHERE d.application_id = a.id
            ORDER BY d.decided_at DESC LIMIT 1) AS decision
    FROM financing_applications a
    JOIN lots lot ON lot.id = a.lot_id
    JOIN subdivisions s ON s.id = lot.subdivision_id
    WHERE a.tenant_id = app_tenant_id() AND (CAST(:id AS uuid) IS NULL OR a.id = :id)
    ORDER BY a.status = 'submitted' DESC, a.created_at DESC
    LIMIT :limit
"""  # noqa: S608 -- interpolates a fixed SQL fragment

LOANS = """
    SELECT l.id, l.application_id, a.applicant_name, lot.number AS lot_number,
           s.name AS subdivision_name, l.principal, l.annual_rate, l.term_months,
           l.first_due_on,
           coalesce((SELECT sum(p.amount) FROM loan_payments p WHERE p.loan_id = l.id), 0)
             AS paid
    FROM loans l
    JOIN financing_applications a ON a.id = l.application_id
    JOIN lots lot ON lot.id = a.lot_id
    JOIN subdivisions s ON s.id = lot.subdivision_id
    WHERE l.tenant_id = app_tenant_id() AND (CAST(:id AS uuid) IS NULL OR l.id = :id)
    ORDER BY l.first_due_on, l.id
    LIMIT :limit
"""

SCHEDULE = """
    SELECT loan_id, number, due_on, payment, principal, interest, balance
    FROM loan_schedules WHERE loan_id = ANY(:ids) ORDER BY loan_id, number
"""


@contextmanager
def financing_session(user: CurrentUser, tenant_id: UUID) -> Generator[Session]:
    """A tenant session that exists only for a tenant with the financing demo on."""
    with tenant_session(user, tenant_id) as session:
        on = session.execute(
            text("SELECT financing_demo FROM tenants WHERE id = app_tenant_id()")
        ).scalar_one_or_none()
        if not on:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        yield session


def _applications(session: Session, application_id: UUID | None = None) -> list[ApplicationOut]:
    rows = session.execute(text(APPLICATIONS), {"id": application_id, "limit": LIST_LIMIT}).all()
    return [ApplicationOut.model_validate(row, from_attributes=True) for row in rows]


def _loans(session: Session, loan_id: UUID | None = None) -> list[LoanDetail]:
    loans = session.execute(text(LOANS), {"id": loan_id, "limit": LIST_LIMIT}).all()
    schedules: dict[UUID, list[Installment]] = {loan.id: [] for loan in loans}
    if loans:
        for row in session.execute(text(SCHEDULE), {"ids": list(schedules)}):
            schedules[row.loan_id].append(Installment.model_validate(row, from_attributes=True))
    payments: dict[UUID, list[Payment]] = {loan.id: [] for loan in loans}
    if loan_id is not None and loans:
        for row in session.execute(
            text(
                "SELECT id, paid_on, amount, recorded_by_email FROM loan_payments"
                " WHERE loan_id = :id ORDER BY paid_on, created_at"
            ),
            {"id": loan_id},
        ):
            payments[loan_id].append(Payment.model_validate(row, from_attributes=True))
    return [_loan(loan, schedules[loan.id], payments[loan.id]) for loan in loans]


def _loan(loan: Row[Any], schedule: list[Installment], payments: list[Payment]) -> LoanDetail:
    principal: Decimal = loan.principal
    now = standing(principal, schedule, loan.paid, date.today())
    return LoanDetail(
        id=loan.id,
        application_id=loan.application_id,
        applicant_name=loan.applicant_name,
        lot_number=loan.lot_number,
        subdivision_name=loan.subdivision_name,
        principal=principal,
        annual_rate=loan.annual_rate,
        term_months=loan.term_months,
        monthly_payment=monthly_payment(principal, loan.annual_rate, loan.term_months),
        first_due_on=loan.first_due_on,
        paid_to_date=now.paid_to_date,
        outstanding_balance=now.outstanding_balance,
        past_due=now.past_due,
        days_past_due=now.days_past_due,
        next_due_on=now.next_due_on,
        schedule=schedule,
        payments=payments,
    )


@router.get("/applications", responses=NOT_FOUND)
def list_applications(tenant_id: UUID, user: SignedInUser) -> list[ApplicationOut]:
    """Waiting for a decision first, then newest first."""
    with financing_session(user, tenant_id) as session:
        return _applications(session)


@router.get("/applications/{application_id}", responses=NOT_FOUND)
def get_application(tenant_id: UUID, application_id: UUID, user: SignedInUser) -> ApplicationOut:
    with financing_session(user, tenant_id) as session:
        found = _applications(session, application_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return found[0]


@router.get("/loans", responses=NOT_FOUND)
def list_loans(tenant_id: UUID, user: SignedInUser) -> list[LoanSummary]:
    """Every loan with where it stands today."""
    with financing_session(user, tenant_id) as session:
        loans = _loans(session)
    return [LoanSummary.model_validate(loan.model_dump()) for loan in loans]


@router.get("/loans/{loan_id}", responses=NOT_FOUND)
def get_loan(tenant_id: UUID, loan_id: UUID, user: SignedInUser) -> LoanDetail:
    """A loan with its whole schedule and every payment."""
    with financing_session(user, tenant_id) as session:
        found = _loans(session, loan_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return found[0]
