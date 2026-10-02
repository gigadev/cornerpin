"""The words in notification emails and push messages. Plain text, no tracking."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from cornerpin.leads.notices import BuyerMessage
from cornerpin.listings.events import LotChanged
from cornerpin.listings.models import LotStatus
from cornerpin.listings.notices import LotNotice

STATUS_WORDS = {
    LotStatus.AVAILABLE: "available",
    LotStatus.ON_HOLD: "on hold",
    LotStatus.SOLD: "sold",
}


@dataclass(frozen=True)
class Message:
    subject: str
    text: str


def money(price: Decimal | None) -> str:
    return "no price" if price is None else f"${int(price):,}"


def _lot_name(lot: LotNotice) -> str:
    return f"Lot {lot.number} at {lot.subdivision_name}"


def lot_change_summary(lot: LotNotice, change: LotChanged) -> str:
    """One line: "Lot 7 at Juniper Bench is now on hold, $529,000 (was $549,000)"."""
    parts: list[str] = []
    if change.status_changed:
        parts.append(f"is now {STATUS_WORDS[change.to_status]}")
    if change.price_changed:
        price = f"{money(change.to_price)} (was {money(change.from_price)})"
        parts.append(price if parts else f"is now {price}")
    return f"{_lot_name(lot)} {', '.join(parts)}"


def lot_change_email(lot: LotNotice, change: LotChanged, web_origin: str) -> Message:
    lines = [f"{_lot_name(lot)} has changed."]
    if change.status_changed:
        lines.append(
            f"Status: {STATUS_WORDS[change.from_status]} → {STATUS_WORDS[change.to_status]}"
        )
    if change.price_changed:
        lines.append(f"Price: {money(change.from_price)} → {money(change.to_price)}")
    return Message(
        subject=lot_change_summary(lot, change),
        text="\n".join(lines)
        + f"\n\nSee the lot: {web_origin}{lot.path}\n\n"
        + "You get this email because you saved this lot. To stop these emails, turn off "
        + f"alerts on your account page: {web_origin}/account\n",
    )


def lot_change_push(lot: LotNotice, change: LotChanged, web_origin: str) -> dict[str, str]:
    body = lot_change_summary(lot, change).removeprefix(f"{_lot_name(lot)} ")
    return {
        "title": f"Lot {lot.number} · {lot.subdivision_name}",
        "body": body[:1].upper() + body[1:],
        "url": f"{web_origin}{lot.path}",
    }


def owner_email(
    kind: str, lot: LotNotice, buyer: BuyerMessage, tenant_id: UUID, web_origin: str
) -> Message:
    """`kind` is "inquiry" or "hold"."""
    subject = (
        f"Hold request for {_lot_name(lot)}"
        if kind == "hold"
        else f"New question about {_lot_name(lot)}"
    )
    contact = buyer.email + (f", {buyer.phone}" if buyer.phone else "")
    lines = [
        f"{buyer.name} ({contact}) "
        + ("asked you to hold" if kind == "hold" else "asked about")
        + f" {_lot_name(lot)}.",
        "",
        buyer.message or "(No message.)",
        "",
        f"Reply to this email to answer {buyer.name}.",
    ]
    if not buyer.signed_in:
        lines.append("They didn't sign in, so their email address hasn't been verified.")
    if kind == "hold":
        lines.append("Approve or decline the request in the owner portal.")
    lines += ["", f"Inquiries and holds: {web_origin}/app/{tenant_id}/inquiries"]
    return Message(subject=subject, text="\n".join(lines) + "\n")
