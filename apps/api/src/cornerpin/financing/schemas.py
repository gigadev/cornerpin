"""What the financing routes return (ADR-049). Amounts are exact decimals, sent as strings with
two places ("1234.50"), so no float ever rounds a cent."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, PlainSerializer

from cornerpin.decisioning.decisions import LeadScore
from cornerpin.financing.terms import IncomeBand

Money = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json")]
ApplicationStatus = Literal["submitted", "approved", "declined", "withdrawn"]


class FinancingDecisionOut(BaseModel):
    kind: Literal["approved", "declined"]
    reason: str
    decided_at: datetime
    decided_by_email: str | None = Field(description="None for the synthetic seed's decisions")


class ApplicationOut(BaseModel):
    """A synthetic buyer's application to finance a lot through the owner (demo tenant only)."""

    id: UUID
    lot_id: UUID
    lot_number: str
    subdivision_name: str
    applicant_name: str
    applicant_email: str
    amount: Money = Field(description="The loan asked for")
    down_payment: Money
    term_months: int
    income_band: IncomeBand
    status: ApplicationStatus
    created_at: datetime
    score: LeadScore | None = Field(description="Risk of falling behind: advice, not a decision")
    decision: FinancingDecisionOut | None


class Installment(BaseModel):
    number: int
    due_on: date
    payment: Money
    principal: Money
    interest: Money
    balance: Money = Field(description="Still owed once this installment is paid")


class Payment(BaseModel):
    id: UUID
    paid_on: date
    amount: Money
    recorded_by_email: str | None = Field(description="None for the synthetic seed's payments")


class LoanSummary(BaseModel):
    id: UUID
    application_id: UUID
    applicant_name: str
    lot_number: str
    subdivision_name: str
    principal: Money
    annual_rate: Decimal = Field(description="0.075 is 7.5% a year")
    term_months: int
    monthly_payment: Money
    first_due_on: date
    paid_to_date: Money
    outstanding_balance: Money = Field(description="Principal still owed after the payments")
    past_due: Money = Field(description="Due by today but not yet paid")
    days_past_due: int = Field(description="Since the oldest unpaid installment fell due")
    next_due_on: date | None


class LoanDetail(LoanSummary):
    schedule: list[Installment]
    payments: list[Payment] = Field(description="Oldest first")
