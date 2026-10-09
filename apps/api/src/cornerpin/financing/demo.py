"""The financing demo's synthetic data (ADR-013, ADR-049), seeded with the demo tenant.

Twelve made-up applicants, every one marked synthetic, on Juniper Bench lots no browser test
uses: six approved into loans on sold lots (two of them behind on payments), three declined,
three waiting for a decision. Dates count back from the day it's seeded, so the loans are
always part-way through and the late ones always late. Emails use the reserved .example domain,
so nothing can ever be sent to them."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, text

from cornerpin.financing.amortization import add_months, schedule, to_cents
from cornerpin.financing.terms import STANDARD_RATE, IncomeBand


@dataclass(frozen=True)
class Applicant:
    name: str
    lot: str
    down: Decimal  # share of the lot's price
    term_months: int
    income: IncomeBand
    outcome: str  # "loan", "declined" or "submitted"
    months_in: int = 0  # for a loan: installments that have fallen due
    missed: int = 0  # for a loan: how many of the latest it hasn't paid
    reason: str = ""


APPLICANTS = (
    Applicant("Avery Brooks", "2-1", Decimal("0.20"), 180, "100k_150k", "loan", months_in=14),
    Applicant("Jordan Ellis", "2-2", Decimal("0.25"), 120, "over_150k", "loan", months_in=9),
    Applicant("Riley Moreno", "2-7", Decimal("0.10"), 360, "50k_100k", "loan", 20, missed=3),
    Applicant("Hayden Cole", "2-8", Decimal("0.15"), 240, "100k_150k", "loan", months_in=6),
    Applicant("Morgan Price", "4-1", Decimal("0.12"), 240, "50k_100k", "loan", 11, missed=1),
    Applicant("Taylor Reed", "4-2", Decimal("0.30"), 120, "over_150k", "loan", months_in=3),
    Applicant(
        "Quinn Harper", "2-11", Decimal("0.05"), 360, "under_50k", "declined",
        reason="The payment would take too much of the stated income.",
    ),
    Applicant(
        "Drew Bailey", "4-6", Decimal("0.08"), 360, "50k_100k", "declined",
        reason="Too little down for this term.",
    ),
    Applicant(
        "Sky Lambert", "3-16", Decimal("0.06"), 240, "under_50k", "declined",
        reason="The payment would take too much of the stated income.",
    ),
    Applicant("Rowan Fisher", "2-12", Decimal("0.20"), 180, "100k_150k", "submitted"),
    Applicant("Emerson Hale", "4-5", Decimal("0.10"), 240, "50k_100k", "submitted"),
    Applicant("Parker Quinn", "2-4", Decimal("0.35"), 120, "over_150k", "submitted"),
)  # fmt: skip

APPROVED = "Meets the demo's terms."


def _email(name: str) -> str:
    return name.lower().replace(" ", ".") + "@synthetic.example"


def seed_financing(conn: Connection, tenant_id: UUID, today: date | None = None) -> None:
    """Switch the financing demo on for `tenant_id` and add its synthetic applications and
    loans. The tenant's lots must already exist."""
    today = today or date.today()
    conn.execute(text("UPDATE tenants SET financing_demo = true WHERE id = :t"), {"t": tenant_id})
    lots = {
        row.number: row
        for row in conn.execute(
            text("SELECT id, number, price FROM lots WHERE tenant_id = :t"), {"t": tenant_id}
        )
    }
    for applicant in APPLICANTS:
        lot = lots[applicant.lot]
        price = Decimal(lot.price)
        down = to_cents(price * applicant.down)
        amount = price - down
        status = {"loan": "approved", "declined": "declined"}.get(applicant.outcome, "submitted")
        made = today - timedelta(days=30 * applicant.months_in + 21)
        application_id = conn.execute(
            text(
                "INSERT INTO financing_applications (tenant_id, lot_id, applicant_name,"
                " applicant_email, amount, down_payment, term_months, income_band, status,"
                " created_at) VALUES (:t, :lot, :name, :email, :amount, :down, :term,"
                " CAST(:income AS income_band), CAST(:status AS financing_status), :made)"
                " RETURNING id"
            ),
            {
                "t": tenant_id,
                "lot": lot.id,
                "name": f"{applicant.name} (synthetic)",
                "email": _email(applicant.name),
                "amount": amount,
                "down": down,
                "term": applicant.term_months,
                "income": applicant.income,
                "status": status,
                "made": made,
            },
        ).scalar_one()
        if applicant.outcome == "submitted":
            continue
        conn.execute(
            text(
                "INSERT INTO financing_decisions (tenant_id, application_id, kind, reason,"
                " decided_at) VALUES (:t, :a, CAST(:kind AS financing_decision_kind), :reason,"
                " :at)"
            ),
            {
                "t": tenant_id,
                "a": application_id,
                "kind": status,
                "reason": applicant.reason or APPROVED,
                "at": made + timedelta(days=7),
            },
        )
        if applicant.outcome == "loan":
            _loan(conn, tenant_id, application_id, amount, applicant, today)


def _loan(
    conn: Connection,
    tenant_id: UUID,
    application_id: UUID,
    amount: Decimal,
    applicant: Applicant,
    today: date,
) -> None:
    # The first installment fell due `months_in` months ago, on the 1st.
    first_due = add_months(today.replace(day=1), -(applicant.months_in - 1))
    rows = schedule(amount, STANDARD_RATE, applicant.term_months, first_due)
    loan_id = conn.execute(
        text(
            "INSERT INTO loans (tenant_id, application_id, principal, annual_rate, term_months,"
            " first_due_on) VALUES (:t, :a, :p, :r, :n, :first) RETURNING id"
        ),
        {
            "t": tenant_id,
            "a": application_id,
            "p": amount,
            "r": STANDARD_RATE,
            "n": applicant.term_months,
            "first": first_due,
        },
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO loan_schedules (tenant_id, loan_id, number, due_on, payment, principal,"
            " interest, balance) VALUES (:t, :l, :number, :due_on, :payment, :principal,"
            " :interest, :balance)"
        ),
        [{"t": tenant_id, "l": loan_id, **vars(row)} for row in rows],
    )
    due = [row for row in rows if row.due_on <= today]
    paid = due[: len(due) - applicant.missed]
    if paid:
        conn.execute(
            text(
                "INSERT INTO loan_payments (tenant_id, loan_id, paid_on, amount)"
                " VALUES (:t, :l, :paid_on, :amount)"
            ),
            [
                {"t": tenant_id, "l": loan_id, "paid_on": row.due_on, "amount": row.payment}
                for row in paid
            ],
        )
