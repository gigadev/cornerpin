"""Outbox handlers for integrations (ADR-040). Importing this module registers them.

A lead activity fans out into one delivery per connected integration, so a failing one retries
alone. A connection whose credentials stopped working is marked failed for an owner to see, and
the delivery isn't retried."""

import logging

from sqlalchemy.orm import Session

from cornerpin.core.outbox import enqueue, handler
from cornerpin.integrations import slack
from cornerpin.integrations.base import Adapter, Broken, activity, connections, mark_failed
from cornerpin.integrations.events import DeliverActivity, LeadActivity, SlackConnect

logger = logging.getLogger(__name__)

ADAPTERS: dict[str, Adapter] = {slack.PROVIDER: slack.SlackAdapter()}


@handler(LeadActivity)
def fan_out(event: LeadActivity, session: Session) -> None:
    found = activity(session, event.lead_event_id)
    if found is None:
        return
    for connection in connections(session, found.tenant_id):
        if connection.provider in ADAPTERS:
            enqueue(
                session,
                DeliverActivity(provider=connection.provider, lead_event_id=event.lead_event_id),
            )


@handler(DeliverActivity)
def deliver(event: DeliverActivity, session: Session) -> None:
    found = activity(session, event.lead_event_id)
    adapter = ADAPTERS.get(event.provider)
    if found is None or adapter is None:
        return
    connection = next(
        (c for c in connections(session, found.tenant_id) if c.provider == event.provider), None
    )
    if connection is None:  # disconnected or switched off since
        return
    try:
        adapter.deliver(connection, found)
    except Broken as exc:
        logger.warning("%s connection %s failed: %s", event.provider, connection.id, exc)
        mark_failed(session, connection.id, str(exc))


# The one-time code leaves the outbox once it's used.
@handler(SlackConnect, scrub=("code",))
def slack_connect(event: SlackConnect, session: Session) -> None:
    slack.connect(session, event.tenant_id, event.code)
