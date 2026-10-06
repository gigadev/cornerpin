"""Outbox handlers for outreach (ADR-036, ADR-037, ADR-038). Importing this module registers
them."""

from email.utils import parseaddr
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.core.outbox import handler
from cornerpin.outreach import agent, policy
from cornerpin.outreach.events import (
    FollowUpDue,
    InboundEmailReceived,
    OutreachSend,
    ReplyReceived,
)
from cornerpin.outreach.inbound import Inbound, get_inbox, receive
from cornerpin.outreach.service import deliver


@handler(OutreachSend)
def send_outreach(event: OutreachSend, session: Session) -> None:
    deliver(session, event.message_id, policy.utcnow())


# The buyer's words leave the outbox once they're on the lead.
@handler(InboundEmailReceived, scrub=("text", "subject", "from_address"))
def receive_email(event: InboundEmailReceived, session: Session) -> None:
    body = event.text if event.text is not None else get_inbox().text_of(event.provider_email_id)
    receive(
        session,
        Inbound(
            provider=event.provider,
            provider_email_id=event.provider_email_id,
            to=event.to,
            from_address=parseaddr(event.from_address)[1].lower(),
            subject=event.subject,
            text=body,
        ),
    )


@handler(ReplyReceived)
def reply_received(event: ReplyReceived, session: Session) -> None:
    """A buyer who replies is engaged (ADR-035), and the agent answers (ADR-038)."""
    lead_id: UUID | None = session.execute(
        text("SELECT lead_id FROM outreach_messages WHERE id = :id"), {"id": event.message_id}
    ).scalar_one_or_none()
    if lead_id is None:
        return
    session.execute(
        text("UPDATE leads SET stage = 'engaged' WHERE id = :id AND stage IN ('new', 'contacted')"),
        {"id": lead_id},
    )
    agent.run_turn(session, lead_id, reply_id=event.message_id)


@handler(FollowUpDue)
def follow_up(event: FollowUpDue, session: Session) -> None:
    """The agent's first follow-up to a signed-in buyer's inquiry (ADR-038)."""
    lead_id: UUID | None = session.execute(
        text(
            "SELECT l.id FROM inquiries i"
            " JOIN leads l ON l.tenant_id = i.tenant_id AND l.user_id = i.user_id"
            " WHERE i.id = :id"
        ),
        {"id": event.inquiry_id},
    ).scalar_one_or_none()
    if lead_id is not None:
        agent.run_turn(session, lead_id)
