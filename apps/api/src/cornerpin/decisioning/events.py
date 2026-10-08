from typing import ClassVar
from uuid import UUID

from cornerpin.core.outbox import Event


class ScoreLead(Event):
    """Something that bears on a lead's score happened. Queued by a trigger on lead_events
    (migration 0018)."""

    event_type: ClassVar[str] = "decisioning.score_lead"

    lead_id: UUID
