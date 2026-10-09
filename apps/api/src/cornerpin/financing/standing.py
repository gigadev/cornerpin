"""Where a loan stands on a given day, from its schedule and the payments made (ADR-049).

Payments fill installments in order. An installment counts as paid once the payments cover it
in full; what's due by today but not covered is past due, and the oldest uncovered installment
that has fallen due sets how many days past due the loan is."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


class Due(Protocol):
    @property
    def due_on(self) -> date: ...
    @property
    def payment(self) -> Decimal: ...
    @property
    def balance(self) -> Decimal: ...


@dataclass(frozen=True)
class Standing:
    paid_to_date: Decimal
    outstanding_balance: Decimal
    past_due: Decimal
    days_past_due: int
    next_due_on: date | None


def standing(principal: Decimal, schedule: Sequence[Due], paid: Decimal, today: date) -> Standing:
    covered, running = 0, Decimal(0)
    for row in schedule:
        if running + row.payment > paid:
            break
        running += row.payment
        covered += 1
    due_by_today = sum((row.payment for row in schedule if row.due_on <= today), Decimal(0))
    past_due = max(due_by_today - paid, Decimal(0))
    unpaid = schedule[covered] if covered < len(schedule) else None
    late = unpaid is not None and unpaid.due_on <= today and past_due > 0
    return Standing(
        paid_to_date=paid,
        outstanding_balance=schedule[covered - 1].balance if covered else principal,
        past_due=past_due,
        days_past_due=(today - unpaid.due_on).days if late and unpaid else 0,
        next_due_on=unpaid.due_on if unpaid else None,
    )
