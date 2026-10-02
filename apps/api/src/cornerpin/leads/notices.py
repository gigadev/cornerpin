"""What other modules may read about buyer activity, for messages sent in the background
(ADR-011). Runs in the worker's session."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class BuyerMessage:
    """An inquiry or a hold request, as the owner's email shows it."""

    id: UUID
    tenant_id: UUID
    lot_id: UUID
    name: str
    email: str
    phone: str | None
    message: str
    signed_in: bool


_COLUMNS = "id, tenant_id, lot_id, name, email, phone, message, user_id IS NOT NULL AS signed_in"


def _message(session: Session, table: str, id_: UUID) -> BuyerMessage | None:
    row = session.execute(
        text(f"SELECT {_COLUMNS} FROM {table} WHERE id = :id"),  # noqa: S608 -- fixed names
        {"id": id_},
    ).one_or_none()
    if row is None:
        return None
    return BuyerMessage(
        id=row.id,
        tenant_id=row.tenant_id,
        lot_id=row.lot_id,
        name=row.name,
        email=row.email,
        phone=row.phone,
        message=row.message,
        signed_in=row.signed_in,
    )


def inquiry(session: Session, inquiry_id: UUID) -> BuyerMessage | None:
    return _message(session, "inquiries", inquiry_id)


def hold_request(session: Session, hold_request_id: UUID) -> BuyerMessage | None:
    return _message(session, "hold_requests", hold_request_id)


def savers(session: Session, lot_id: UUID) -> list[UUID]:
    """Users who have saved the lot."""
    return list(
        session.execute(
            text("SELECT user_id FROM saved_lots WHERE lot_id = :id ORDER BY created_at"),
            {"id": lot_id},
        ).scalars()
    )
