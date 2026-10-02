"""What other modules may read about a lot, for messages sent in the background (ADR-011).
Runs in the worker's session."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.listings.models import LotStatus


@dataclass(frozen=True)
class LotNotice:
    id: UUID
    tenant_id: UUID
    number: str
    status: LotStatus
    price: Decimal | None
    subdivision_name: str
    subdivision_slug: str
    public: bool  # published, in a published subdivision

    @property
    def path(self) -> str:
        """The lot's public page, relative to the web origin."""
        return f"/{self.subdivision_slug}/lots/{self.number}"


def lot_notice(session: Session, lot_id: UUID) -> LotNotice | None:
    row = session.execute(
        text(
            "SELECT l.id, l.tenant_id, l.number, l.status, l.price,"
            " l.published AND s.published AS public, s.name, s.slug"
            " FROM lots l JOIN subdivisions s ON s.id = l.subdivision_id WHERE l.id = :id"
        ),
        {"id": lot_id},
    ).one_or_none()
    if row is None:
        return None
    return LotNotice(
        id=row.id,
        tenant_id=row.tenant_id,
        number=row.number,
        status=LotStatus(row.status),
        price=row.price,
        subdivision_name=row.name,
        subdivision_slug=row.slug,
        public=row.public,
    )
