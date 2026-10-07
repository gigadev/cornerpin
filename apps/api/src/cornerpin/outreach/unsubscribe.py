"""Unsubscribe links (ADR-036). A link names one tenant, one buyer and one channel, signed, so
it works without signing in. Following it shows a page; only a POST (the page's button, or a
mail provider's one-click request) records the opt-out, so mail scanners that open links never
unsubscribe anyone."""

from uuid import UUID

from cornerpin.core.auth.tokens import sign, unsign
from cornerpin.core.config import get_settings
from cornerpin.leads.schemas import Channel

# An opt-out is harmless to repeat, and old emails should keep working.
MAX_AGE_SECONDS = 5 * 365 * 24 * 3600
CHANNELS: tuple[Channel, ...] = ("email", "sms", "voice")


def unsubscribe_token(tenant_id: UUID, user_id: UUID, channel: Channel) -> str:
    return sign({"t": str(tenant_id), "u": str(user_id), "c": channel}, get_settings().secret_key)


def unsubscribe_url(tenant_id: UUID, user_id: UUID, channel: Channel) -> str:
    """The page a person opens from the email."""
    token = unsubscribe_token(tenant_id, user_id, channel)
    return f"{get_settings().web_origin}/unsubscribe?token={token}"


def one_click_url(tenant_id: UUID, user_id: UUID, channel: Channel) -> str:
    """Where a mail provider POSTs a one-click unsubscribe (RFC 8058): the API, through the
    web app's /v1 proxy."""
    token = unsubscribe_token(tenant_id, user_id, channel)
    return f"{get_settings().web_origin}/v1/unsubscribe?token={token}"


def read_token(token: str) -> tuple[UUID, UUID, Channel] | None:
    """(tenant, user, channel), or None if the link was altered or is malformed."""
    value = unsign(token, get_settings().secret_key, max_age_seconds=MAX_AGE_SECONDS)
    if value is None:
        return None
    channel: Channel | None = next((c for c in CHANNELS if c == value.get("c")), None)
    if channel is None:
        return None
    try:
        return UUID(value["t"]), UUID(value["u"]), channel
    except (KeyError, ValueError):
        return None
