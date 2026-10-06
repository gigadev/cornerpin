"""When outreach may go (ADR-036). Pure functions, so the rules are tested without a database."""

from datetime import UTC, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Sending hours in the recipient's time zone, on every channel.
SEND_FROM = time(9, 0)
SEND_UNTIL = time(20, 0)
DEFAULT_TIME_ZONE = "America/Boise"

# Sends per rolling 24 hours. The tenant cap stays well under the email provider's free daily
# limit, which sign-in links and alerts share.
LEAD_DAILY_CAP = 2
TENANT_DAILY_CAP = 40
CAP_WINDOW = timedelta(hours=24)

Refusal = Literal[
    "no_consent", "opted_out", "lead_daily_cap", "tenant_daily_cap", "channel_unavailable"
]


def zone(name: str | None) -> ZoneInfo:
    """The named zone, or the default when it's missing or unknown."""
    try:
        return ZoneInfo(name or DEFAULT_TIME_ZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIME_ZONE)


def next_window(now: datetime, tz: ZoneInfo) -> datetime | None:
    """None if `now` is within sending hours in `tz`; otherwise when they next open."""
    local = now.astimezone(tz)
    if SEND_FROM <= local.time() < SEND_UNTIL:
        return None
    day = local.date() if local.time() < SEND_FROM else local.date() + timedelta(days=1)
    return datetime.combine(day, SEND_FROM, tzinfo=tz)


def consent_refusal(latest: bool | None) -> Refusal | None:
    """The latest consent row decides: none means never asked, false means they opted out."""
    if latest is None:
        return "no_consent"
    return None if latest else "opted_out"


def cap_refusal(lead_sent: int, tenant_sent: int) -> Refusal | None:
    if lead_sent >= LEAD_DAILY_CAP:
        return "lead_daily_cap"
    if tenant_sent >= TENANT_DAILY_CAP:
        return "tenant_daily_cap"
    return None


def utcnow() -> datetime:
    return datetime.now(UTC)
