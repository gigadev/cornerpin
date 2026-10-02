"""Events the leads module produces. They carry ids only: handlers read the record at send
time, so buyers' messages and contact details never sit in the outbox."""

from typing import ClassVar
from uuid import UUID

from cornerpin.core.outbox import Event


class InquiryReceived(Event):
    event_type: ClassVar[str] = "leads.inquiry_received"

    inquiry_id: UUID


class HoldRequested(Event):
    event_type: ClassVar[str] = "leads.hold_requested"

    hold_request_id: UUID
