"""The integration adapter interface (ADR-012, ADR-040, ADR-041), and what adapters are given: a
tenant's connection, with its credentials unsealed, and lead activity and lots read in the
worker's session. Each activity is read when it's delivered, so it carries the lead's current
state, whatever order deliveries happen in."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Protocol, get_args
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.core.config import get_settings
from cornerpin.integrations.crypto import unseal

ActivityKind = Literal["inquiry", "hold_requested", "handoff", "stage_changed", "hold_approved"]
ACTIVITY_KINDS: tuple[str, ...] = get_args(ActivityKind)


@dataclass(frozen=True)
class Activity:
    """Something that happened to a lead, with what the integrations need to pass it on."""

    id: UUID
    tenant_id: UUID
    lead_id: UUID
    kind: ActivityKind
    new_lead: bool  # the lead's first event
    verified: bool  # False for an anonymous inquiry
    buyer: str  # the name, else the email
    message: str | None
    reason: str | None  # a handoff's
    lot: str | None  # "Lot 2-6, Juniper Bench"
    lot_url: str | None  # its public page, if public
    lead_url: str  # the lead in the owner portal
    # The lead as it is now.
    name: str
    email: str
    phone: str | None
    stage: str
    # An approved hold's.
    hold_request_id: UUID | None
    lot_price: Decimal | None
    decided_at: datetime | None


@dataclass(frozen=True)
class Lot:
    id: UUID
    tenant_id: UUID
    number: str
    subdivision: str
    slug: str
    status: str
    price: Decimal | None
    acreage: Decimal | None
    listing_type: str
    public: bool

    @property
    def name(self) -> str:
        return f"Lot {self.number}, {self.subdivision}"

    @property
    def url(self) -> str:
        return f"{get_settings().web_origin}/{self.slug}/lots/{self.number}"


@dataclass(frozen=True)
class Connection:
    id: UUID
    tenant_id: UUID
    provider: str
    settings: dict[str, Any]
    secret: dict[str, Any]


class Broken(Exception):
    """The integration refused the credentials or the data for good (revoked, gone, rejected):
    the connection is marked failed for an owner to see, and the delivery isn't retried."""


class Adapter(Protocol):
    provider: str

    def wants(self, activity: Activity) -> bool:
        """Whether this integration does anything with the activity."""
        ...

    def deliver(self, connection: Connection, activity: Activity) -> None:
        """Pass the activity on. Raise Broken for a dead connection; anything else retries."""
        ...


class LotAdapter(Protocol):
    provider: str

    def sync_lots(self, connection: Connection, changed: list[Lot]) -> None:
        """Bring the integration's copy of these lots up to date."""
        ...


ACTIVITY = """
    SELECT e.id, e.tenant_id, e.lead_id, e.kind::text AS kind, e.verified, e.detail,
           coalesce(nullif(l.name, ''), l.email) AS buyer, l.name, l.email, l.phone,
           l.stage::text AS stage, e.hold_request_id, h.decided_at,
           lot.number, lot.price AS lot_price, s.name AS subdivision, s.slug,
           lot.published AND s.published AS public,
           NOT EXISTS (SELECT FROM lead_events p
                       WHERE p.lead_id = e.lead_id AND p.created_at < e.created_at) AS new_lead
    FROM lead_events e
    JOIN leads l ON l.id = e.lead_id
    LEFT JOIN lots lot ON lot.id = e.lot_id
    LEFT JOIN subdivisions s ON s.id = lot.subdivision_id
    LEFT JOIN hold_requests h ON h.id = e.hold_request_id
    WHERE e.id = :id
"""


def activity(session: Session, lead_event_id: UUID) -> Activity | None:
    row = session.execute(text(ACTIVITY), {"id": lead_event_id}).one_or_none()
    if row is None or row.kind not in ACTIVITY_KINDS:
        return None
    origin = get_settings().web_origin
    detail: dict[str, Any] = row.detail
    return Activity(
        id=row.id,
        tenant_id=row.tenant_id,
        lead_id=row.lead_id,
        kind=row.kind,
        new_lead=row.new_lead,
        verified=row.verified,
        buyer=row.buyer,
        message=detail.get("message") or None,
        reason=detail.get("reason") or None,
        lot=f"Lot {row.number}, {row.subdivision}" if row.number else None,
        lot_url=f"{origin}/{row.slug}/lots/{row.number}" if row.number and row.public else None,
        lead_url=f"{origin}/app/{row.tenant_id}/leads/{row.lead_id}",
        name=row.name,
        email=row.email,
        phone=row.phone,
        stage=row.stage,
        hold_request_id=row.hold_request_id,
        lot_price=row.lot_price,
        decided_at=row.decided_at,
    )


LOTS = """
    SELECT l.id, l.tenant_id, l.number, s.name AS subdivision, s.slug, l.status::text AS status,
           l.price, l.acreage, l.listing_type::text AS listing_type,
           l.published AND s.published AS public
    FROM lots l JOIN subdivisions s ON s.id = l.subdivision_id
"""


def lots(
    session: Session, *, lot_id: UUID | None = None, tenant_id: UUID | None = None
) -> list[Lot]:
    """One lot, or all of a tenant's, published or not."""
    where = " WHERE l.id = :id" if lot_id else " WHERE l.tenant_id = :t ORDER BY s.name, l.number"
    rows = session.execute(text(LOTS + where), {"id": lot_id, "t": tenant_id})
    return [
        Lot(
            id=r.id,
            tenant_id=r.tenant_id,
            number=r.number,
            subdivision=r.subdivision,
            slug=r.slug,
            status=r.status,
            price=r.price,
            acreage=r.acreage,
            listing_type=r.listing_type,
            public=r.public,
        )
        for r in rows
    ]


def connections(session: Session, tenant_id: UUID) -> list[Connection]:
    """The tenant's connected, enabled integrations, credentials unsealed."""
    rows = session.execute(
        text(
            "SELECT id, tenant_id, provider::text AS provider, settings, secret"
            " FROM integration_connections"
            " WHERE tenant_id = :t AND enabled AND status = 'connected' AND secret IS NOT NULL"
        ),
        {"t": tenant_id},
    )
    return [
        Connection(
            id=row.id,
            tenant_id=row.tenant_id,
            provider=row.provider,
            settings=row.settings,
            secret=unseal(row.tenant_id, row.provider, bytes(row.secret)),
        )
        for row in rows
    ]


def mark_failed(session: Session, connection_id: UUID, error: str) -> None:
    session.execute(
        text(
            "UPDATE integration_connections SET status = 'failed', error = left(:e, 500)"
            " WHERE id = :id"
        ),
        {"id": connection_id, "e": error},
    )
