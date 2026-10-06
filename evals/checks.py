"""What must be true after a scenario: its own expectations, and the checks every scenario gets.
Facts are read from the database the run used, so a check compares the emails with the
listings, not with what the agent's tools said."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import Engine, text

from cornerpin.outreach.agent import quoted_amounts
from cornerpin.outreach.tools import money
from cornerpin.seed import DEMO_TENANT_ID

from .harness import BOISE, Outcome


@dataclass(frozen=True)
class LotFacts:
    price: Decimal | None
    acres: Decimal | None
    sqft: int | None


@dataclass(frozen=True)
class Listings:
    lots: dict[str, LotFacts]
    prices: frozenset[Decimal]  # every published price the agent could have read

    def variants(self, lot: str, fact: str) -> list[str]:
        """Ways an email may state a fact; the first is how the tools give it."""
        facts = self.lots[lot]
        match fact:
            case "price" if facts.price is not None:
                return [money(facts.price)]
            case "acres" if facts.acres is not None:
                return [f"{facts.acres.normalize()}"]
            case "sqft" if facts.sqft is not None:
                return [f"{facts.sqft:,}", str(facts.sqft)]
            case _:
                raise ValueError(f"lot {lot} has no {fact}")


def listings(owner: Engine) -> Listings:
    with owner.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT number, price, acreage, home_square_feet FROM lots"
                " WHERE tenant_id = :t AND published"
            ),
            {"t": DEMO_TENANT_ID},
        ).all()
    return Listings(
        lots={r.number: LotFacts(r.price, r.acreage, r.home_square_feet) for r in rows},
        prices=frozenset(r.price for r in rows if r.price is not None),
    )


def failures(outcome: Outcome, facts: Listings) -> list[str]:
    expect = outcome.scenario.expect
    said = "\n".join(email.text for email in outcome.emails)
    lowered = said.lower()
    found: list[str] = list(outcome.errors)

    # --- every scenario -------------------------------------------------------------------
    if outcome.model.exhausted:
        found.append("the recording ran out of replies: re-record with --live --record")
    if outcome.model.unused:
        found.append(f"{outcome.model.unused} recorded replies went unused: re-record")
    for turn in outcome.turns:
        if turn.stopped == "invented_price" and turn.draft:
            invented = [w for w, v in quoted_amounts(turn.draft) if v not in facts.prices]
            found.append(f"invented a price ({', '.join(invented)}); the guard held it back")
        if turn.stopped == "unfinished":
            found.append("a turn didn't finish (out of steps or tokens, or refused)")
    for email in outcome.emails:
        for written, value in quoted_amounts(email.text):
            if value not in facts.prices:
                found.append(f"emailed {written}, which no listing shows")

    # --- this scenario ------------------------------------------------------------------------
    if len(outcome.emails) != expect.emails:
        found.append(f"expected {expect.emails} email(s) to the buyer, got {len(outcome.emails)}")
    for quote in expect.quotes:
        lot, fact = quote.split(":")
        options = facts.variants(lot, fact)
        if not any(option.lower() in lowered for option in options):
            found.append(f"didn't state lot {lot}'s {fact} ({options[0]})")
    for alternatives in expect.says:
        if not any(phrase.lower() in lowered for phrase in alternatives):
            found.append(f"didn't say {' or '.join(repr(p) for p in alternatives)}")
    found += [f"said {p!r}" for p in expect.never_says if p.lower() in lowered]
    if expect.handoff is True and not outcome.handed_off:
        found.append("expected a handoff to a person; there was none")
    if expect.handoff is False and outcome.handed_off:
        found.append(f"handed off when it needn't have: {outcome.handoff_reason}")
    reason = outcome.handoff_reason or ""
    if expect.handoff_reason and not reason.startswith(expect.handoff_reason):
        found.append(f"handoff reason {reason!r} doesn't start {expect.handoff_reason!r}")
    called = {name for turn in outcome.turns for name in turn.tool_calls}
    found += [f"never called {tool}" for tool in expect.tools if tool not in called]
    if expect.waits_until:
        due = datetime.combine(
            outcome.asked_on + timedelta(days=1),
            datetime.strptime(expect.waits_until, "%H:%M").time(),
            BOISE,
        )
        if outcome.held_until is None or outcome.held_until != due:
            found.append(f"expected the email held until {due:%a %H:%M}, got {outcome.held_until}")
    return found
