from typing import ClassVar
from uuid import UUID

from cornerpin.core.outbox import Event

Provider = str  # "slack"; "salesforce" with P2-08


class LeadActivity(Event):
    """A new lead, a hold request or a handoff, for a tenant with a connected integration.
    Queued by a trigger on lead_events (migration 0016)."""

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
