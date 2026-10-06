"""Outbox handlers for outreach (ADR-036, ADR-037). Importing this module registers them."""

from email.utils import parseaddr

from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.core.outbox import handler
from cornerpin.outreach import policy
from cornerpin.outreach.events import InboundEmailReceived, OutreachSend, ReplyReceived
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
    """A buyer who replies is engaged (ADR-035). The agent's answer comes with P2-05."""
    session.execute(
        text(
            "UPDATE leads SET stage = 'engaged' FROM outreach_messages m"
            " WHERE m.id = :id AND leads.id = m.lead_id AND leads.stage IN ('new', 'contacted')"
        ),
        {"id": event.message_id},
    )
