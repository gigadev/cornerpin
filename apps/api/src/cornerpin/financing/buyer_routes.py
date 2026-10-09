"""Buyers and the financing demo (P3-06, ADR-050): what a lot offers, applying, and their own
applications with the decisions on them. Only a public, available lot of a tenant with the
demo on offers financing; anywhere else every route answers 404."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from psycopg import errors
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from cornerpin.core.auth.deps import SignedInUser
from cornerpin.core.db import public_session, user_session
from cornerpin.core.outbox import expect_events
from cornerpin.financing.amortization import monthly_payment
from cornerpin.financing.schemas import (
    ApplicationCreate,
    BuyerDecision,
    FinancingOffer,
    MyApplication,
)
from cornerpin.financing.terms import INCOME_MIDPOINTS, STANDARD_RATE, TERMS
from cornerpin.leads.schemas import Created

router = APIRouter(tags=["financing"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "No such lot, or it doesn't offer financing"}
}
# The down payment a buyer may offer, as a share of the price (ADR-050).
MIN_DOWN, MAX_DOWN = Decimal("0.05"), Decimal("0.50")


@dataclass(frozen=True)
class OfferedLot:
    id: UUID
    tenant_id: UUID
    price: Decimal

    @property
    def min_down(self) -> Decimal:
        return (self.price * MIN_DOWN).to_integral_value(rounding=ROUND_CEILING)

    @property
    def max_down(self) -> Decimal:
        return (self.price * MAX_DOWN).to_integral_value(rounding=ROUND_FLOOR)


def _offered_lot(lot_id: UUID) -> OfferedLot:
    """The lot, if the public can see it, it's available and priced, and its owner offers the
    financing demo; otherwise 404."""
    with public_session() as session:
        row = session.execute(
            text(
                "SELECT id, tenant_id, price, status::text AS status,"
                " app_tenant_offers_financing(tenant_id) AS offered FROM lots WHERE id = :id"
            ),
            {"id": lot_id},
        ).one_or_none()
    if row is None or not row.offered or row.status != "available" or row.price is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return OfferedLot(id=row.id, tenant_id=row.tenant_id, price=Decimal(row.price))


@contextmanager
def _still_offered() -> Generator[None]:
    """An insert the RLS check refused (the lot or the offer went away meanwhile) is a 404."""
    try:
        yield
    except ProgrammingError as exc:
        if isinstance(exc.orig, errors.InsufficientPrivilege):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None
        raise


@router.get("/lots/{lot_id}/financing", responses=NOT_FOUND)
def financing_offer(lot_id: UUID) -> FinancingOffer:
    """The demo's terms on this lot. Anyone may look; applying needs a sign-in."""
    lot = _offered_lot(lot_id)
    return FinancingOffer(
        lot_id=lot.id,
        price=lot.price,
        annual_rate=STANDARD_RATE,
        terms=list(TERMS),  # pyright: ignore[reportArgumentType] -- the Term values themselves
        income_bands=list(INCOME_MIDPOINTS),
        min_down=lot.min_down,
        max_down=lot.max_down,
    )


@router.post(
    "/lots/{lot_id}/financing-applications",
    status_code=status.HTTP_201_CREATED,
    responses={
        **NOT_FOUND,
        status.HTTP_409_CONFLICT: {"description": "Already applied for this lot"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Down payment out of range"},
    },
)
def apply(lot_id: UUID, body: ApplicationCreate, user: SignedInUser) -> Created:
    """Apply to finance this lot through its owner. The application is scored in the
    background, and the owner decides."""
    lot = _offered_lot(lot_id)
    down = Decimal(body.down_payment)
    if not lot.min_down <= down <= lot.max_down:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"The down payment must be between ${lot.min_down:,.0f} and ${lot.max_down:,.0f}",
        )
    application_id = uuid4()
    try:
        with user_session(user.id) as session, _still_offered():
            email = session.execute(
                text("SELECT email FROM users WHERE id = app_user_id()")
            ).scalar_one()
            session.execute(
                text(
                    "INSERT INTO financing_applications (id, tenant_id, lot_id, user_id,"
                    " applicant_name, applicant_email, amount, down_payment, term_months,"
                    " income_band) VALUES (:id, :t, :lot, app_user_id(), :name, :email, :amount,"
                    " :down, :term, CAST(:income AS income_band))"
                ),
                {
                    "id": application_id,
                    "t": lot.tenant_id,
                    "lot": lot.id,
                    "name": body.name,
                    "email": email,
                    "amount": lot.price - down,
                    "down": down,
                    "term": body.term_months,
                    "income": body.income_band,
                },
            )
            expect_events(session)  # a trigger queues the application's score (ADR-049)
    except IntegrityError as exc:
        if isinstance(exc.orig, errors.UniqueViolation):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "You've already applied to finance this lot"
            ) from None
        raise
    return Created(id=application_id)


MINE = """
    SELECT a.id, a.lot_id, a.amount, a.down_payment, a.term_months, a.status::text AS status,
           a.created_at,
           (SELECT jsonb_build_object('kind', d.kind, 'reason', d.reason,
                                      'decided_at', d.decided_at,
                                      'principal_reasons', d.principal_reasons)
            FROM financing_decisions d WHERE d.application_id = a.id
            ORDER BY d.decided_at DESC LIMIT 1) AS decision
    FROM financing_applications a
    WHERE a.user_id = app_user_id()
    ORDER BY a.created_at DESC
"""

LOTS = """
    SELECT l.id, l.number, s.name, s.slug FROM lots l
    JOIN subdivisions s ON s.id = l.subdivision_id WHERE l.id = ANY(:ids)
"""


@router.get("/me/financing-applications")
def my_applications(user: SignedInUser) -> list[MyApplication]:
    """The buyer's own applications, newest first, with any decision and its reasons."""
    with user_session(user.id) as session:
        rows = session.execute(text(MINE)).all()
    lots: dict[UUID, Any] = {}
    if rows:
        with public_session() as session:
            found = session.execute(text(LOTS), {"ids": [row.lot_id for row in rows]}).all()
            lots = {lot.id: lot for lot in found}
    return [
        MyApplication(
            id=row.id,
            lot_id=row.lot_id,
            lot_number=lots[row.lot_id].number if row.lot_id in lots else None,
            subdivision_name=lots[row.lot_id].name if row.lot_id in lots else None,
            subdivision_slug=lots[row.lot_id].slug if row.lot_id in lots else None,
            amount=row.amount,
            down_payment=row.down_payment,
            term_months=row.term_months,
            annual_rate=STANDARD_RATE,
            monthly_payment=monthly_payment(row.amount, STANDARD_RATE, row.term_months),
            status=row.status,
            created_at=row.created_at,
            decision=BuyerDecision.model_validate(row.decision) if row.decision else None,
        )
        for row in rows
    ]
