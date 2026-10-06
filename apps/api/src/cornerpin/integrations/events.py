from typing import ClassVar
from uuid import UUID

from cornerpin.core.outbox import Event

Provider = str  # "slack" or "salesforce"


class LeadActivity(Event):
    """A lead's inquiry, hold request or approved hold, handoff or stage change, for a tenant
    with a connected integration. Queued by a trigger on lead_events (migrations 0016, 0017)."""

    event_type: ClassVar[str] = "integrations.lead_activity"

    lead_event_id: UUID


class DeliverActivity(Event):
    """One integration's copy of a lead activity, so each retries on its own."""

    event_type: ClassVar[str] = "integrations.deliver_activity"

    provider: Provider
    lead_event_id: UUID


class SlackConnect(Event):
    """Finish connecting Slack: exchange the one-time code an owner's install returned."""

    event_type: ClassVar[str] = "integrations.slack_connect"

    tenant_id: UUID
    code: str


class SalesforceConnect(Event):
    """Finish connecting Salesforce with the credentials an owner typed in: sign in, set the
    org up, send the lots."""

    event_type: ClassVar[str] = "integrations.salesforce_connect"

    tenant_id: UUID


class LotChanged(Event):
    """A lot was added or changed, for a tenant with Salesforce connected. Queued by a trigger
    on lots (migration 0017)."""

    event_type: ClassVar[str] = "integrations.lot_changed"

    lot_id: UUID


class DeliverLot(Event):
    """One integration's copy of a lot change."""

    event_type: ClassVar[str] = "integrations.deliver_lot"

    provider: Provider
    lot_id: UUID
