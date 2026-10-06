from typing import ClassVar
from uuid import UUID

from cornerpin.core.outbox import Event


class OutreachSend(Event):
    """Deliver one queued outreach message, if it may go now (ADR-036)."""

    event_type: ClassVar[str] = "outreach.send"

    message_id: UUID
