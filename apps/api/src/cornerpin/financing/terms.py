"""The demo's financing terms (ADR-049): the rate it offers, the terms a buyer may pick, and
the income bands a buyer states. Synthetic, like everything in the module."""

from decimal import Decimal
from typing import Literal

from cornerpin.financing.amortization import monthly_payment

STANDARD_RATE = Decimal("0.075")
TERMS = (60, 120, 180, 240, 360)
IncomeBand = Literal["under_50k", "50k_100k", "100k_150k", "over_150k"]
# A band's midpoint stands for the buyer's income when the payment is compared with it.
INCOME_MIDPOINTS: dict[IncomeBand, Decimal] = {
    "under_50k": Decimal(40_000),
    "50k_100k": Decimal(75_000),
    "100k_150k": Decimal(125_000),
    "over_150k": Decimal(175_000),
}


def payment_to_income(amount: Decimal, term_months: int, band: IncomeBand) -> float:
    """The share of a month's stated income this loan's payment would take, at the standard
    rate: the one figure from the buyer's finances the score may see."""
    payment = monthly_payment(amount, STANDARD_RATE, term_months)
    return round(float(payment / (INCOME_MIDPOINTS[band] / 12)), 3)
