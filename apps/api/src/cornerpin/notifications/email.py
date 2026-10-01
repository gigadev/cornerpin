"""Email delivery behind one interface (ADR-017): SMTP to Mailpit locally, Resend in the cloud.
Only outbox handlers send email."""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from functools import lru_cache
from typing import Protocol

import httpx

from cornerpin.core.config import get_settings


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str


class EmailSender(Protocol):
    def send(self, email: Email) -> None: ...


@dataclass(frozen=True)
class SmtpSender:
    host: str
    port: int
    sender: str

    def send(self, email: Email) -> None:
        message = MimeMessage()
        message["From"] = self.sender
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.text)
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            smtp.send_message(message)


@dataclass(frozen=True)
class ResendSender:
    api_key: str
    sender: str

    def send(self, email: Email) -> None:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "from": self.sender,
                "to": [email.to],
                "subject": email.subject,
                "text": email.text,
            },
            timeout=10,
        )
        response.raise_for_status()


@lru_cache
def get_email_sender() -> EmailSender:
    settings = get_settings()
    if settings.email_backend == "resend" and settings.resend_api_key:
        return ResendSender(api_key=settings.resend_api_key, sender=settings.email_from)
    return SmtpSender(host=settings.smtp_host, port=settings.smtp_port, sender=settings.email_from)
