"""Contact consent (ADR-014, ADR-022). Rows are only ever added: the latest row per tenant, user
and channel is the current state. A form records a row only for a channel whose answer changed,
so the history reads as a list of real decisions."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.leads.schemas import Channel, ContactChoices

# The channels a form asks about; calls (voice) wait for Phase 4.
OFFERED: tuple[Channel, ...] = ("email", "sms")

LATEST = """
    SELECT DISTINCT ON (channel) channel::text AS channel, granted
    FROM contact_consents
    WHERE tenant_id = :tenant_id AND user_id = :user_id
    ORDER BY channel, recorded_at DESC
"""

# For owner lists: the channels a buyer currently allows, given rows aliased with tenant_id and
# user_id columns.
ALLOWED_CHANNELS_SQL = """
    coalesce((
      SELECT array_agg(latest.channel ORDER BY latest.channel)
      FROM (SELECT DISTINCT ON (c.channel) c.channel::text AS channel, c.granted
            FROM contact_consents c
            WHERE c.tenant_id = {alias}.tenant_id AND c.user_id = {alias}.user_id
            ORDER BY c.channel, c.recorded_at DESC) latest
      WHERE latest.granted
    ), ARRAY[]::text[])
"""


def allowed_channels_sql(alias: str) -> str:
    return ALLOWED_CHANNELS_SQL.format(alias=alias)


def current_choices(session: Session, tenant_id: UUID, user_id: UUID) -> ContactChoices:
    rows = session.execute(text(LATEST), {"tenant_id": tenant_id, "user_id": user_id}).all()
    granted = {row.channel: row.granted for row in rows}
    return ContactChoices(email=granted.get("email", False), sms=granted.get("sms", False))


def record(
    session: Session, tenant_id: UUID, user_id: UUID, channel: Channel, granted: bool, source: str
) -> None:
    """Rows from one transaction would share now(), so each takes the wall-clock time."""
    session.execute(
        text(
            "INSERT INTO contact_consents (tenant_id, user_id, channel, granted, source,"
            " recorded_at) VALUES (:tenant_id, :user_id, CAST(:channel AS contact_channel),"
            " :granted, :source, clock_timestamp())"
        ),
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "channel": channel,
            "granted": granted,
            "source": source,
        },
    )


def record_choices(
    session: Session, tenant_id: UUID, user_id: UUID, choices: ContactChoices, source: str
) -> None:
    """Add a row for each channel whose answer differs from the current state."""
    current = current_choices(session, tenant_id, user_id)
    for channel in OFFERED:
        wanted: bool = getattr(choices, channel)
        if wanted != getattr(current, channel):
            record(session, tenant_id, user_id, channel, wanted, source)
