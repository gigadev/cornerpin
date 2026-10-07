"""Channel adapters (ADR-036): one per way of reaching a buyer. Email is the only one until SMS
(P2-09); the service refuses a message on a channel with no adapter."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from cornerpin.core.config import get_settings
from cornerpin.leads.schemas import Channel
from cornerpin.notifications.email import Email, get_email_sender
from cornerpin.outreach.unsubscribe import one_click_url, unsubscribe_url


@dataclass(frozen=True)
class Outbound:
    tenant_id: UUID
    tenant_name: str
    user_id: UUID
    to_email: str
    to_phone: str | None
    subject: str | None
    body: str
    reply_to: str | None


@dataclass(frozen=True)
class Receipt:
    provider: str
    provider_message_id: str | None


class ChannelAdapter(Protocol):
    channel: Channel

    def send(self, message: Outbound) -> Receipt: ...


def email_text(message: Outbound, unsubscribe: str) -> str:
    """The body, then who is writing and why, and how to stop."""
    return (
        f"{message.body}\n\n"
        "--\n"
        f"You're getting this because you allowed {message.tenant_name} to email you about"
        " their lots on Cornerpin.\n"
        f"Stop these emails: {unsubscribe}\n"
    )


class EmailChannel:
    channel: Channel = "email"

    def send(self, message: Outbound) -> Receipt:
        url = unsubscribe_url(message.tenant_id, message.user_id, "email")
        one_click = one_click_url(message.tenant_id, message.user_id, "email")
        provider_id = get_email_sender().send(
            Email(
                to=message.to_email,
                subject=message.subject or f"About your interest in {message.tenant_name}'s lots",
                text=email_text(message, url),
                reply_to=message.reply_to,
                # One-click unsubscribe (RFC 8058), which Gmail and Yahoo expect.
                headers={
                    "List-Unsubscribe": f"<{one_click}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                },
            )
        )
        return Receipt(provider=get_settings().email_backend, provider_message_id=provider_id)


ADAPTERS: dict[Channel, ChannelAdapter] = {"email": EmailChannel()}
