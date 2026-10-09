"""What the financing routes return (ADR-049). Amounts are exact decimals, sent as strings with
two places ("1234.50"), so no float ever rounds a cent."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, PlainSerializer, StringConstraints, model_validator

from cornerpin.decisioning.decisions import LeadScore
from cornerpin.financing.terms import IncomeBand
from cornerpin.leads.schemas import PersonName

Money = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json")]
ApplicationStatus = Literal["submitted", "approved", "declined", "withdrawn"]


Term = Literal[60, 120, 180, 240, 360]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class FinancingDecisionOut(BaseModel):
    kind: Literal["approved", "declined"]
    reason: str
    decided_at: datetime
    decided_by_email: str | None = Field(description="None for the synthetic seed's decisions")
    principal_reasons: list[str] = Field(
        description="What raised the risk most, as the buyer was told on a decline"
    )


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


# --- buyers (P3-06) ---------------------------------------------------------------------------


class FinancingOffer(BaseModel):
    """What the owner offers on an available lot, for the lot page's form. Synthetic terms."""

    lot_id: UUID
    price: Money
    annual_rate: Decimal = Field(description="0.075 is 7.5% a year")
    terms: list[Term]
    income_bands: list[IncomeBand]
    min_down: Money
    max_down: Money


class ApplicationCreate(BaseModel):
    """No SSN, no date of birth, no credit check: a demonstration (ADR-050)."""

    name: PersonName
    down_payment: int = Field(ge=0, description="Whole dollars")
    term_months: Term
    income_band: IncomeBand = Field(description="Stated by the buyer, never checked")


class BuyerDecision(BaseModel):
    kind: Literal["approved", "declined"]
    reason: str
    decided_at: datetime
    principal_reasons: list[str]


class MyApplication(BaseModel):
    id: UUID
    lot_id: UUID
    lot_number: str | None = Field(description="None if the lot is no longer public")
    subdivision_name: str | None
    subdivision_slug: str | None
    amount: Money
    down_payment: Money
    term_months: int
    annual_rate: Decimal
    monthly_payment: Money = Field(description="At the demo's rate, if approved as asked")
    status: ApplicationStatus
    created_at: datetime
    decision: BuyerDecision | None


# --- owners (P3-06) ---------------------------------------------------------------------------


class ApplicationDecision(BaseModel):
    decision: Literal["approve", "decline"]
    reason: Reason = Field(default="", description="Required to decline; shown to the buyer")
    score_id: UUID | None = Field(
        default=None, description="The score the owner saw when deciding, if one was shown"
    )

    @model_validator(mode="after")
    def _a_decline_says_why(self) -> Self:
        if self.decision == "decline" and not self.reason:
            raise ValueError("Say why you're declining; the buyer is told")
        return self


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    paid_on: date | None = Field(default=None, description="Defaults to today")
