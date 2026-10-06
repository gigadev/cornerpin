from typing import ClassVar
from uuid import UUID

from cornerpin.core.outbox import Event


class OutreachSend(Event):
    """Deliver one queued outreach message, if it may go now (ADR-036)."""

    event_type: ClassVar[str] = "outreach.send"

    message_id: UUID


class InboundEmailReceived(Event):
    """A provider reports an email to one of our reply addresses (ADR-037). The body is fetched
    in the handler, unless a local test sent it along."""

    event_type: ClassVar[str] = "outreach.inbound_email"

    provider: str
    provider_email_id: str
    to: list[str]
    from_address: str
    subject: str | None = None
    text: str | None = None


class ReplyReceived(Event):
    """A buyer replied to outreach; the agent answers it (P2-05)."""

    event_type: ClassVar[str] = "outreach.reply_received"

    message_id: UUID
