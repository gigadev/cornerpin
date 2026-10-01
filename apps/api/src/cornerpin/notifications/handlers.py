"""Outbox handlers owned by the notifications module."""

from cornerpin.core.auth.events import MagicLinkRequested
from cornerpin.core.outbox import handler
from cornerpin.notifications.email import Email, get_email_sender


@handler(MagicLinkRequested, scrub=("url",))
def send_magic_link(event: MagicLinkRequested) -> None:
    get_email_sender().send(
        Email(
            to=event.email,
            subject="Your Cornerpin sign-in link",
            text=(
                "Use this link to sign in to Cornerpin:\n\n"
                f"{event.url}\n\n"
                f"It works once and expires in {event.minutes_valid} minutes. "
                "If you didn't ask for it, you can ignore this email.\n"
            ),
        )
    )
