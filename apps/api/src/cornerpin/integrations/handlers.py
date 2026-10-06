"""Outbox handlers for integrations (ADR-040, ADR-041). Importing this module registers them.

Lead activity and lot changes fan out into one delivery per connected integration that wants
them, so a failing one retries alone. A connection whose credentials or data were refused for
good is marked failed for an owner to see, and the delivery isn't retried."""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from cornerpin.core.outbox import enqueue, handler
from cornerpin.integrations import salesforce, slack
from cornerpin.integrations.base import (
    Adapter,
    Broken,
    Connection,
    LotAdapter,
    activity,
    connections,
    lots,
    mark_failed,
)
from cornerpin.integrations.events import (
    DeliverActivity,
    DeliverLot,
    LeadActivity,
    LotChanged,
    SalesforceConnect,
    SlackConnect,
)

logger = logging.getLogger(__name__)

ADAPTERS: dict[str, Adapter] = {
    slack.PROVIDER: slack.SlackAdapter(),
    salesforce.PROVIDER: salesforce.SalesforceAdapter(),
}
LOT_ADAPTERS: dict[str, LotAdapter] = {salesforce.PROVIDER: salesforce.SalesforceAdapter()}


def _connection(session: Session, tenant_id: UUID, provider: str) -> Connection | None:
    """The tenant's connection, if it's still connected and switched on."""
    return next((c for c in connections(session, tenant_id) if c.provider == provider), None)


def _broken(session: Session, connection: Connection, exc: Broken) -> None:
    logger.warning("%s connection %s failed: %s", connection.provider, connection.id, exc)
    mark_failed(session, connection.id, str(exc))


@handler(LeadActivity)
def fan_out(event: LeadActivity, session: Session) -> None:
    found = activity(session, event.lead_event_id)
    if found is None:
        return
    for connection in connections(session, found.tenant_id):
        adapter = ADAPTERS.get(connection.provider)
        if adapter is not None and adapter.wants(found):
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
    connection = _connection(session, found.tenant_id, event.provider)
    if connection is None:  # disconnected or switched off since
        return
    try:
        adapter.deliver(connection, found)
    except Broken as exc:
        _broken(session, connection, exc)


@handler(LotChanged)
def fan_out_lot(event: LotChanged, session: Session) -> None:
    [lot] = lots(session, lot_id=event.lot_id) or [None]
    if lot is None:
        return
    for connection in connections(session, lot.tenant_id):
        if connection.provider in LOT_ADAPTERS:
            enqueue(session, DeliverLot(provider=connection.provider, lot_id=lot.id))


@handler(DeliverLot)
def deliver_lot(event: DeliverLot, session: Session) -> None:
    [lot] = lots(session, lot_id=event.lot_id) or [None]
    adapter = LOT_ADAPTERS.get(event.provider)
    if lot is None or adapter is None:
        return
    connection = _connection(session, lot.tenant_id, event.provider)
    if connection is None:
        return
    try:
        adapter.sync_lots(connection, [lot])
    except Broken as exc:
        _broken(session, connection, exc)


# The one-time code leaves the outbox once it's used.
@handler(SlackConnect, scrub=("code",))
def slack_connect(event: SlackConnect, session: Session) -> None:
    slack.connect(session, event.tenant_id, event.code)


@handler(SalesforceConnect)
def salesforce_connect(event: SalesforceConnect, session: Session) -> None:
    salesforce.connect(session, event.tenant_id)
