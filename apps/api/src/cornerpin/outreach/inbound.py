"""Receiving replies (P2-04, ADR-037). The provider tells us an email arrived; the handler fetches
its text, finds the outreach message it answers from the reply address, and records it on that
lead. Anything else is logged and dropped."""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.core.config import get_settings
from cornerpin.core.outbox import enqueue
from cornerpin.outreach.events import ReplyReceived
from cornerpin.outreach.replies import html_to_text, message_for, reply_text

logger = logging.getLogger(__name__)


class InboxReader(Protocol):
    def text_of(self, email_id: str) -> str:
        """The email's plain text (from its HTML if it has no text part)."""
        ...


@dataclass(frozen=True)
class ResendInbox:
    api_key: str

    def text_of(self, email_id: str) -> str:
        response = httpx.get(
            f"https://api.resend.com/emails/receiving/{email_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=10,
        )
        response.raise_for_status()
        email: dict[str, object] = response.json()
        body = email.get("text")
        if isinstance(body, str) and body.strip():
            return body
        markup = email.get("html")
        return html_to_text(markup) if isinstance(markup, str) else ""


@lru_cache
def get_inbox() -> InboxReader:
    api_key = get_settings().resend_api_key
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is needed to read received email")
    return ResendInbox(api_key=api_key)


@dataclass(frozen=True)
class Inbound:
    provider: str
    provider_email_id: str
    to: list[str]
    from_address: str
    subject: str | None
    text: str


def receive(session: Session, email: Inbound) -> UUID | None:
    """Record a reply on its lead and hand it to the agent; returns the new message's id, or
    None when it isn't for us or was already recorded (a provider's retry)."""
    answered = next((m for m in map(message_for, email.to) if m is not None), None)
    original = (
        session.execute(
            text(
                "SELECT tenant_id, lead_id, channel::text AS channel FROM outreach_messages"
                " WHERE id = :id AND direction = 'outbound'"
            ),
            {"id": answered},
        ).one_or_none()
        if answered
        else None
    )
    if original is None:
        logger.warning(
            "inbound email %s from %s dropped: not a reply address of ours",
            email.provider_email_id,
            email.provider,
        )
        return None

    message_id: UUID | None = session.execute(
        text(
            "INSERT INTO outreach_messages (tenant_id, lead_id, channel, direction, status,"
            " subject, body, provider, provider_message_id, from_address)"
            " VALUES (:tenant, :lead, CAST(:channel AS contact_channel), 'inbound', 'received',"
            " :subject, :body, :provider, :provider_id, :from_address)"
            " ON CONFLICT (provider, provider_message_id) DO NOTHING RETURNING id"
        ),
        {
            "tenant": original.tenant_id,
            "lead": original.lead_id,
            "channel": original.channel,
            "subject": email.subject,
            "body": reply_text(email.text),
            "provider": email.provider,
            "provider_id": email.provider_email_id,
            "from_address": email.from_address,
        },
    ).scalar_one_or_none()
    if message_id is not None:
        enqueue(session, ReplyReceived(message_id=message_id))
    return message_id
