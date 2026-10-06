"""The integration adapter interface (ADR-012, ADR-040), and what adapters are given: a tenant's
connection, with its credentials unsealed, and lead activity read in the worker's session."""

from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.core.config import get_settings
from cornerpin.integrations.crypto import unseal

ActivityKind = Literal["inquiry", "hold_requested", "handoff"]


@dataclass(frozen=True)
class Activity:
    """Something an owner wants to hear about, in the words an alert needs."""

    id: UUID
    tenant_id: UUID
    lead_id: UUID
    kind: ActivityKind
    new_lead: bool  # the lead's first event
    verified: bool  # False for an anonymous inquiry
    buyer: str
    message: str | None
    reason: str | None  # a handoff's
    lot: str | None  # "Lot 2-6, Juniper Bench"
    lot_url: str | None  # its public page, if public
    lead_url: str  # the lead in the owner portal


@dataclass(frozen=True)
class Connection:
    id: UUID
    tenant_id: UUID
    provider: str
    settings: dict[str, Any]
    secret: dict[str, Any]


class Broken(Exception):
    """The integration refused the credentials for good (revoked, channel gone): the
    connection is marked failed for an owner to reconnect, and the delivery isn't retried."""


class Adapter(Protocol):
    provider: str

    def deliver(self, connection: Connection, activity: Activity) -> None:
        """Pass the activity on. Raise Broken for a dead connection; anything else retries."""
        ...


ACTIVITY = """
    SELECT e.id, e.tenant_id, e.lead_id, e.kind::text AS kind, e.verified, e.detail,
           coalesce(nullif(l.name, ''), l.email) AS buyer, lot.number, s.name AS subdivision,
           s.slug, lot.published AND s.published AS public,
           NOT EXISTS (SELECT FROM lead_events p
                       WHERE p.lead_id = e.lead_id AND p.created_at < e.created_at) AS new_lead
    FROM lead_events e
    JOIN leads l ON l.id = e.lead_id
    LEFT JOIN lots lot ON lot.id = e.lot_id
    LEFT JOIN subdivisions s ON s.id = lot.subdivision_id
    WHERE e.id = :id
"""


def activity(session: Session, lead_event_id: UUID) -> Activity | None:
    row = session.execute(text(ACTIVITY), {"id": lead_event_id}).one_or_none()
    if row is None or row.kind not in ("inquiry", "hold_requested", "handoff"):
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
    )


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
