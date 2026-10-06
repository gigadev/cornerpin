"""Email delivery behind one interface (ADR-017): SMTP to Mailpit locally, Resend in the cloud.
Only outbox handlers send email."""

import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from email.utils import make_msgid
from functools import lru_cache
from typing import Protocol

import httpx

from cornerpin.core.config import get_settings


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str
    reply_to: str | None = None
    # Extra headers, e.g. List-Unsubscribe on outreach (ADR-036).
    headers: dict[str, str] = field(default_factory=dict[str, str])


class EmailSender(Protocol):
    def send(self, email: Email) -> str | None:
        """Send it; returns the provider's id for the message, when there is one."""
        ...


@dataclass(frozen=True)
class SmtpSender:
    host: str
    port: int
    sender: str

    def send(self, email: Email) -> str | None:
        message = MimeMessage()
        message["From"] = self.sender
        message["To"] = email.to
        message["Subject"] = email.subject
        message["Message-ID"] = make_msgid(domain="cornerpin.app")
        if email.reply_to:
            message["Reply-To"] = email.reply_to
        for name, value in email.headers.items():
            message[name] = value
        message.set_content(email.text)
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            smtp.send_message(message)
        return message["Message-ID"]


@dataclass(frozen=True)
class ResendSender:
    api_key: str
    sender: str

    def send(self, email: Email) -> str | None:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "from": self.sender,
                "to": [email.to],
                "subject": email.subject,
                "text": email.text,
                **({"reply_to": email.reply_to} if email.reply_to else {}),
                **({"headers": email.headers} if email.headers else {}),
            },
            timeout=10,
        )
        response.raise_for_status()
        sent: dict[str, object] = response.json()
        message_id = sent.get("id")
        return message_id if isinstance(message_id, str) else None


@lru_cache
def get_email_sender() -> EmailSender:
    settings = get_settings()
    if settings.email_backend == "resend" and settings.resend_api_key:
        return ResendSender(api_key=settings.resend_api_key, sender=settings.email_from)
    return SmtpSender(host=settings.smtp_host, port=settings.smtp_port, sender=settings.email_from)
