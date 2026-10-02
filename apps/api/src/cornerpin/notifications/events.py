"""One event per recipient (ADR-029): a failed send retries for that person alone, and a
retry never repeats a send that already succeeded."""

from typing import ClassVar
from uuid import UUID

from cornerpin.core.outbox import Event
from cornerpin.listings.events import LotChanged


class OwnerInquiryEmail(Event):
    event_type: ClassVar[str] = "notifications.owner_inquiry_email"

    inquiry_id: UUID
    user_id: UUID


class OwnerHoldEmail(Event):
    event_type: ClassVar[str] = "notifications.owner_hold_email"

    hold_request_id: UUID
    user_id: UUID


class SavedLotEmail(Event):
    event_type: ClassVar[str] = "notifications.saved_lot_email"

    user_id: UUID
    change: LotChanged


class SavedLotPush(Event):
    event_type: ClassVar[str] = "notifications.saved_lot_push"

    subscription_id: UUID
    change: LotChanged
