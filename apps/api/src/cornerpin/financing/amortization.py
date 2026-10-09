"""Fixed-rate monthly amortization, to the cent (ADR-049).

Each month's interest is the balance times the monthly rate, rounded to the cent; the rest of
the payment goes to principal. The last installment takes whatever principal is left, so the
principal portions add up to exactly the amount borrowed and the balance ends at 0.00."""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_cents(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def monthly_payment(principal: Decimal, annual_rate: Decimal, months: int) -> Decimal:
    """The level payment that repays `principal` over `months` at `annual_rate` (0.075 = 7.5%)."""
    if months <= 0:
        raise ValueError("a loan needs at least one month")
    rate = annual_rate / 12
    if rate == 0:
        return to_cents(principal / months)
    factor = (1 + rate) ** months
    return to_cents(principal * rate * factor / (factor - 1))


def add_months(start: date, months: int) -> date:
    month = start.month - 1 + months
    year, month = start.year + month // 12, month % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


@dataclass(frozen=True)
class Installment:
    number: int
    due_on: date
    payment: Decimal
    principal: Decimal
    interest: Decimal
    balance: Decimal
    """What's still owed once this installment is paid."""


def schedule(
    principal: Decimal, annual_rate: Decimal, months: int, first_due: date
) -> list[Installment]:
    payment = monthly_payment(principal, annual_rate, months)
    rate = annual_rate / 12
    balance = to_cents(principal)
    rows: list[Installment] = []
    for number in range(1, months + 1):
        interest = to_cents(balance * rate)
        part = balance if number == months else min(payment - interest, balance)
        balance -= part
        rows.append(
            Installment(
                number=number,
                due_on=add_months(first_due, number - 1),
                payment=part + interest,
                principal=part,
                interest=interest,
                balance=balance,
            )
        )
    return rows
