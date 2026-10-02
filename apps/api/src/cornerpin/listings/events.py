"""Events the listings module produces."""

from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from cornerpin.core.outbox import Event
from cornerpin.listings.models import LotStatus


class LotChanged(Event):
    """A lot's status or price changed. Queued by the `lots_queue_change` trigger (migration
    0008), never from Python, so the field names must match the trigger's payload."""

    event_type: ClassVar[str] = "listings.lot_changed"

    lot_id: UUID
    from_status: LotStatus
    to_status: LotStatus
    from_price: Decimal | None
    to_price: Decimal | None

    @property
    def status_changed(self) -> bool:
        return self.from_status != self.to_status

    @property
    def price_changed(self) -> bool:
        return self.from_price != self.to_price
