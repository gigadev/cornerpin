from typing import ClassVar

from cornerpin.core.outbox import Event


class MagicLinkRequested(Event):
    """Send a sign-in link. `url` carries the raw token and is scrubbed after sending."""

    event_type: ClassVar[str] = "auth.magic_link_requested"

    email: str
    url: str
    minutes_valid: int
