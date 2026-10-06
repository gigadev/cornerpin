"""Requesting and delivering outreach (P2-03, ADR-036).

`request_send` records the message as queued and queues its delivery in the same transaction,
so every message has a row whatever happens to it. `deliver` runs in the outbox handler, as
cornerpin_worker, and decides at that moment: consent for the channel (the latest row, so an
opt-out wins), quiet hours in the recipient's time zone (waiting for the window, not refusing),
then the daily caps. A refusal is recorded with its reason; both outcomes reach the timeline
through a trigger."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.orm import Session

from cornerpin.core.config import get_settings
from cornerpin.core.outbox import enqueue
from cornerpin.leads.schemas import Channel
from cornerpin.outreach import policy
from cornerpin.outreach.channels import ADAPTERS, Outbound
from cornerpin.outreach.events import OutreachSend
from cornerpin.outreach.replies import reply_address

MESSAGE = """
    SELECT m.id, m.tenant_id, m.lead_id, m.channel::text AS channel, m.status::text AS status,
           m.subject, m.body, l.user_id, l.email, l.phone, t.name AS tenant_name,
           u.time_zone AS user_time_zone
    FROM outreach_messages m
    JOIN leads l ON l.id = m.lead_id
    JOIN tenants t ON t.id = m.tenant_id
    LEFT JOIN users u ON u.id = l.user_id
    WHERE m.id = :id
"""

LATEST_CONSENT = """
    SELECT granted FROM contact_consents
    WHERE tenant_id = :tenant AND user_id = :user AND channel = CAST(:channel AS contact_channel)
    ORDER BY recorded_at DESC LIMIT 1
"""

# A buyer without a time zone of their own gets the subdivision's they last asked about.
LOT_TIME_ZONE = """
    SELECT s.time_zone FROM lead_events e
    JOIN lots l ON l.id = e.lot_id
    JOIN subdivisions s ON s.id = l.subdivision_id
    WHERE e.lead_id = :lead
    ORDER BY e.created_at DESC LIMIT 1
"""

SENT_SINCE = """
    SELECT count(*) FILTER (WHERE lead_id = :lead) AS lead_sent, count(*) AS tenant_sent
    FROM outreach_messages
    WHERE tenant_id = :tenant AND status = 'sent' AND sent_at > :since
"""

# Where replies go while Cornerpin doesn't receive email itself (ADR-037).
OWNER_EMAIL = """
    SELECT u.email FROM memberships m JOIN users u ON u.id = m.user_id
    WHERE m.tenant_id = :tenant AND m.role = 'owner'
    ORDER BY m.created_at, u.email LIMIT 1
"""


def request_send(
    session: Session,
    *,
    tenant_id: UUID,
    lead_id: UUID,
    channel: Channel,
    body: str,
    subject: str | None = None,
) -> UUID:
    """Queue a message to a lead. Nothing is checked yet: that happens when it goes."""
    message_id: UUID = session.execute(
        text(
            "INSERT INTO outreach_messages (tenant_id, lead_id, channel, direction, status,"
            " subject, body) VALUES (:tenant, :lead, CAST(:channel AS contact_channel),"
            " 'outbound', 'queued', :subject, :body) RETURNING id"
        ),
        {
            "tenant": tenant_id,
            "lead": lead_id,
            "channel": channel,
            "subject": subject,
            "body": body,
        },
    ).scalar_one()
    enqueue(session, OutreachSend(message_id=message_id))
    return message_id


def _refuse(session: Session, message_id: UUID, reason: policy.Refusal) -> None:
    session.execute(
        text(
            "UPDATE outreach_messages SET status = 'refused', refused_reason = :reason"
            " WHERE id = :id"
        ),
        {"id": message_id, "reason": reason},
    )


def _consent(session: Session, row: Row[Any]) -> bool | None:
    if row.user_id is None:  # an anonymous inquirer has given no consent
        return None
    latest: bool | None = session.execute(
        text(LATEST_CONSENT),
        {"tenant": row.tenant_id, "user": row.user_id, "channel": row.channel},
    ).scalar_one_or_none()
    return latest


def _time_zone(session: Session, row: Row[Any]) -> str | None:
    if row.user_time_zone:
        return str(row.user_time_zone)
    found: str | None = session.execute(
        text(LOT_TIME_ZONE), {"lead": row.lead_id}
    ).scalar_one_or_none()
    return found


def _reply_to(session: Session, row: Row[Any]) -> str | None:
    """A reply address that brings the answer back to this lead (ADR-037), or, until Cornerpin
    receives email, the owner's own address."""
    domain = get_settings().inbound_email_domain
    if domain:
        return reply_address(row.id, domain)
    owner: str | None = session.execute(
        text(OWNER_EMAIL), {"tenant": row.tenant_id}
    ).scalar_one_or_none()
    return owner


def deliver(session: Session, message_id: UUID, now: datetime) -> None:
    """Send a queued message if it may go now; wait for sending hours, or refuse."""
    row = session.execute(text(MESSAGE), {"id": message_id}).one_or_none()
    if row is None or row.status != "queued":
        return  # already decided: a retried event never sends twice

    refusal = policy.consent_refusal(_consent(session, row))
    if refusal is not None:
        _refuse(session, message_id, refusal)
        return

    opens = policy.next_window(now, policy.zone(_time_zone(session, row)))
    if opens is not None:
        enqueue(session, OutreachSend(message_id=message_id), available_at=opens)
        return

    counts = session.execute(
        text(SENT_SINCE),
        {"tenant": row.tenant_id, "lead": row.lead_id, "since": now - policy.CAP_WINDOW},
    ).one()
    refusal = policy.cap_refusal(counts.lead_sent, counts.tenant_sent)
    adapter = ADAPTERS.get(row.channel)
    if refusal is None and adapter is None:
        refusal = "channel_unavailable"
    if refusal is not None or adapter is None:
        _refuse(session, message_id, refusal or "channel_unavailable")
        return

    receipt = adapter.send(
        Outbound(
            tenant_id=row.tenant_id,
            tenant_name=row.tenant_name,
            user_id=row.user_id,
            to_email=row.email,
            to_phone=row.phone,
            subject=row.subject,
            body=row.body,
            reply_to=_reply_to(session, row),
        )
    )
    session.execute(
        text(
            "UPDATE outreach_messages SET status = 'sent', sent_at = :now, provider = :provider,"
            " provider_message_id = :provider_id WHERE id = :id"
        ),
        {
            "id": message_id,
            "now": now,
            "provider": receipt.provider,
            "provider_id": receipt.provider_message_id,
        },
    )
