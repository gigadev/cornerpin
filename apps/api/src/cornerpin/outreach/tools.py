"""The outreach agent's tools (ADR-038): the only way it learns a fact or does anything. Each
reads or writes for one lead of one tenant, in the worker's session, and each call is on the
lead's timeline: lookups and notes as agent_action events, handoffs and tour requests as the
lead's handoff. Lot facts come only from published lots in published subdivisions."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from anthropic.types import ToolParam
from pydantic import BaseModel, StringConstraints, ValidationError
from sqlalchemy import Row, text
from sqlalchemy.orm import Session

from cornerpin.core.config import get_settings

AgentTool = Literal[
    "lookup_lot", "check_availability", "request_tour", "log_timeline", "handoff_to_human"
]
MAX_AVAILABLE = 25

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Said = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


@dataclass(frozen=True)
class Lead:
    id: UUID
    tenant_id: UUID
    tenant_name: str
    user_id: UUID | None
    email: str
    name: str
    stage: str
    handoff_at: datetime | None


@dataclass(frozen=True)
class Outcome:
    """What a tool returns to the model, and any prices it may now quote."""

    result: dict[str, Any]
    prices: frozenset[Decimal] = frozenset()
    is_error: bool = False


@dataclass
class Toolbox:
    """The tools for one turn with one lead. It remembers every price the tools returned."""

    session: Session
    lead: Lead
    prices: set[Decimal] = field(default_factory=lambda: set[Decimal]())
    calls: list[str] = field(default_factory=lambda: list[str]())

    def run(self, name: str, arguments: dict[str, Any]) -> Outcome:
        self.calls.append(name)
        tool = TOOLS.get(name)
        if tool is None:
            return Outcome({"error": f"There is no tool called {name}."}, is_error=True)
        try:
            outcome = tool.run(self, tool.arguments.model_validate(arguments))
        except ValidationError as exc:
            return Outcome({"error": exc.errors(include_url=False)}, is_error=True)
        self.prices |= outcome.prices
        return outcome

    # --- what the tools write --------------------------------------------------------------

    def log(
        self,
        tool: AgentTool,
        summary: str,
        *,
        lot_id: UUID | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> None:
        """An agent_action event. clock_timestamp() keeps a turn's calls in order."""
        self.session.execute(
            text(
                "INSERT INTO lead_events (tenant_id, lead_id, kind, lot_id, detail, created_at)"
                " VALUES (:tenant, :lead, 'agent_action', :lot, CAST(:detail AS jsonb),"
                " clock_timestamp())"
            ),
            {
                "tenant": self.lead.tenant_id,
                "lead": self.lead.id,
                "lot": lot_id,
                "detail": json.dumps({"tool": tool, "text": summary, "input": arguments or {}}),
            },
        )

    def hand_off(self, reason: str) -> bool:
        """Put the lead in the owner's "needs a person" inbox, unless it's already there.
        The handoff trigger records it on the timeline."""
        handed: UUID | None = self.session.execute(
            text(
                "UPDATE leads SET handoff_at = clock_timestamp(), handoff_reason = left(:r, 1000)"
                " WHERE id = :id AND handoff_at IS NULL RETURNING id"
            ),
            {"id": self.lead.id, "r": reason},
        ).scalar_one_or_none()
        return handed is not None


# --- lot facts -----------------------------------------------------------------------------

LOTS = """
    SELECT l.id, l.number, l.status::text AS status, l.price, l.acreage,
           l.listing_type::text AS listing_type, l.home_bedrooms, l.home_bathrooms,
           l.home_square_feet, l.home_description, s.name AS subdivision, s.slug,
           s.description AS subdivision_description
    FROM lots l JOIN subdivisions s ON s.id = l.subdivision_id
    WHERE l.tenant_id = :tenant AND l.published AND s.published
      AND (CAST(:subdivision AS text) IS NULL
           OR s.name ILIKE :subdivision OR s.slug = lower(:subdivision))
"""
STATUS_WORDS = {"available": "available", "on_hold": "on hold", "sold": "sold"}


def _status(row: Row[Any]) -> str:
    status: str = row.status
    return STATUS_WORDS.get(status, status)


def money(amount: Decimal) -> str:
    return f"${amount:,.0f}" if amount == amount.to_integral_value() else f"${amount:,.2f}"


def _facts(row: Row[Any], *, full: bool) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "lot": row.number,
        "subdivision": row.subdivision,
        "status": _status(row),
        "price": money(row.price) if row.price is not None else None,
        "acres": float(row.acreage) if row.acreage is not None else None,
        "listing": "lot and home" if row.listing_type == "lot_and_home" else "land only",
        "page": f"{get_settings().web_origin}/{row.slug}/lots/{row.number}",
    }
    if row.price is None:
        facts["price_note"] = "No published price: don't quote one; the owner will share it."
    if full and row.listing_type == "lot_and_home":
        facts["home"] = {
            "bedrooms": row.home_bedrooms,
            "bathrooms": float(row.home_bathrooms) if row.home_bathrooms is not None else None,
            "square_feet": row.home_square_feet,
            "description": row.home_description,
        }
    if full and row.subdivision_description:
        facts["subdivision_description"] = row.subdivision_description
    return {key: value for key, value in facts.items() if value is not None}


def _prices(rows: list[Row[Any]]) -> frozenset[Decimal]:
    return frozenset(row.price for row in rows if row.price is not None)


def _summary(row: Row[Any]) -> str:
    price = money(row.price) if row.price is not None else "no published price"
    return f"{_status(row).capitalize()}, {price}"


def find_lots(
    session: Session, tenant_id: UUID, number: str, subdivision: str | None
) -> list[Row[Any]]:
    return list(
        session.execute(
            text(LOTS + " AND lower(l.number) = lower(:number) ORDER BY s.name LIMIT 5"),
            {"tenant": tenant_id, "number": number, "subdivision": subdivision},
        )
    )


class LookupLot(BaseModel):
    number: Short
    subdivision: Short | None = None


def lookup_lot(box: Toolbox, args: LookupLot) -> Outcome:
    rows = find_lots(box.session, box.lead.tenant_id, args.number, args.subdivision)
    arguments = args.model_dump(exclude_none=True)
    if not rows:
        box.log("lookup_lot", f"No listed lot {args.number}", arguments=arguments)
        return Outcome(
            {
                "found": False,
                "note": "No listed lot has that number. Don't describe it; check_availability"
                " lists the lots for sale.",
            }
        )
    for row in rows:
        box.log("lookup_lot", _summary(row), lot_id=row.id, arguments=arguments)
    return Outcome({"found": True, "lots": [_facts(r, full=True) for r in rows]}, _prices(rows))


class CheckAvailability(BaseModel):
    subdivision: Short | None = None


def check_availability(box: Toolbox, args: CheckAvailability) -> Outcome:
    rows = list(
        box.session.execute(
            text(
                LOTS + " AND l.status = 'available'"
                " ORDER BY s.name, l.number COLLATE lot_number LIMIT :limit"
            ),
            {
                "tenant": box.lead.tenant_id,
                "subdivision": args.subdivision,
                "limit": MAX_AVAILABLE + 1,
            },
        )
    )
    more = len(rows) > MAX_AVAILABLE
    rows = rows[:MAX_AVAILABLE]
    where = f" in {args.subdivision}" if args.subdivision else ""
    box.log(
        "check_availability",
        f"{len(rows)}{'+' if more else ''} available{where}",
        arguments=args.model_dump(exclude_none=True),
    )
    result: dict[str, Any] = {"available": [_facts(r, full=False) for r in rows]}
    if more:
        result["note"] = f"Only the first {MAX_AVAILABLE} are listed."
    return Outcome(result, _prices(rows))


# --- actions -------------------------------------------------------------------------------


class RequestTour(BaseModel):
    preferred_times: Said
    lot_number: Short | None = None
    subdivision: Short | None = None


def request_tour(box: Toolbox, args: RequestTour) -> Outcome:
    """Logs the request and hands off: a person arranges it until tours are booked (Phase 4)."""
    lot = ""
    if args.lot_number:
        rows = find_lots(box.session, box.lead.tenant_id, args.lot_number, args.subdivision)
        lot = f" of Lot {rows[0].number}, {rows[0].subdivision}" if rows else ""
    reason = f"Wants a tour{lot}: {args.preferred_times}"
    if not box.hand_off(reason):  # already with a person: keep the request anyway
        box.log("request_tour", reason, arguments=args.model_dump(exclude_none=True))
    return Outcome(
        {
            "ok": True,
            "note": f"{box.lead.tenant_name} has been asked to arrange it and will reply"
            " personally. Don't suggest or confirm a time.",
        }
    )


class LogTimeline(BaseModel):
    note: Said


def log_timeline(box: Toolbox, args: LogTimeline) -> Outcome:
    box.log("log_timeline", args.note)
    return Outcome({"ok": True})


class HandoffToHuman(BaseModel):
    reason: Said


def handoff_to_human(box: Toolbox, args: HandoffToHuman) -> Outcome:
    if not box.hand_off(args.reason):
        box.log("handoff_to_human", args.reason)
    return Outcome(
        {
            "ok": True,
            "note": f"A person at {box.lead.tenant_name} will take it from here. Say so"
            " briefly without answering what you handed off, or reply NO_EMAIL if they asked"
            " not to be emailed.",
        }
    )


# --- the contract the model sees ------------------------------------------------------------


@dataclass(frozen=True)
class Tool[A: BaseModel]:
    description: str
    arguments: type[A]
    run: Callable[[Toolbox, A], Outcome]


TOOLS: dict[str, Tool[Any]] = {
    "lookup_lot": Tool(
        "Everything listed about one lot: status, price, size, home details and its page. Use"
        " it before you say anything about a lot.",
        LookupLot,
        lookup_lot,
    ),
    "check_availability": Tool(
        "The lots for sale now, with their prices, optionally in one subdivision.",
        CheckAvailability,
        check_availability,
    ),
    "request_tour": Tool(
        "Ask the owner to arrange a visit or a call. Pass what the buyer said about timing."
        " The owner replies personally.",
        RequestTour,
        request_tour,
    ),
    "log_timeline": Tool(
        "Leave a note on the buyer's timeline for the owner: a budget, a timeline, a"
        " preference, or anything else they should know.",
        LogTimeline,
        log_timeline,
    ),
    "handoff_to_human": Tool(
        "Pass the conversation to a person: a question your tools can't answer, anything you're"
        " unsure of, a complaint, or a request to stop. Give a one-line reason.",
        HandoffToHuman,
        handoff_to_human,
    ),
}


def tool_params() -> list[ToolParam]:
    params: list[ToolParam] = []
    for name, tool in TOOLS.items():
        schema = tool.arguments.model_json_schema()
        params.append(
            {
                "name": name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": schema.get("properties", {}),
                    "required": schema.get("required", []),
                },
            }
        )
    return params
