"""Helpers for the outreach tests (P2-03, P2-04): a fake mailbox and clock, and shortcuts to a
lead with consent and a queued message. The fixtures that install them are in conftest.py."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import text

from cornerpin.core.db import worker_session
from cornerpin.notifications.email import Email
from cornerpin.outreach.service import request_send

from .conftest import Databases, Listing

BOISE = ZoneInfo("America/Boise")
AFTERNOON = datetime(2026, 10, 6, 15, 0, tzinfo=BOISE)  # within sending hours
# Any token passes the fake verifier.
TURNSTILE: dict[str, str] = {"turnstile_token": "t"}


@dataclass
class Mailbox:
    sent: list[Email] = field(default_factory=lambda: [])
    failing: bool = False

    def send(self, email: Email) -> str | None:
        if self.failing:
            raise ConnectionError("mail server down")
        self.sent.append(email)
        return f"msg-{uuid4().hex}"  # unique, as a provider's ids are

    def to(self, address: str) -> list[Email]:
        return [email for email in self.sent if email.to == address]


@dataclass
class Clock:
    now: datetime = AFTERNOON

    def __call__(self) -> datetime:
        return self.now


def inquire(client: TestClient, lot: Listing, *, allow_email: bool, **extra: Any) -> None:
    body: dict[str, Any] = {"name": "Pat Buyer", "message": "Is the well shared?", **extra}
    if allow_email:
        body["contact"] = {"email": True}
    sent = client.post(f"/v1/lots/{lot.available}/inquiries", json=body)
    assert sent.status_code == 201, sent.text


def lead_of(db: Databases, lot: Listing, email: str) -> UUID:
    with db.owner.connect() as conn:
        lead_id: UUID = conn.execute(
            text("SELECT id FROM leads WHERE tenant_id = :t AND email = :e"),
            {"t": lot.tenant.tenant_id, "e": email},
        ).scalar_one()
    return lead_id


def ask_to_send(db: Databases, lot: Listing, lead_id: UUID, body: str = "Hi Pat") -> UUID:
    with worker_session(engine=db.api) as session:
        return request_send(
            session,
            tenant_id=lot.tenant.tenant_id,
            lead_id=lead_id,
            channel="email",
            subject="Lot 1 at Buyers",
            body=body,
        )


def message(db: Databases, message_id: UUID) -> Any:
    with db.owner.connect() as conn:
        return conn.execute(
            text(
                "SELECT status::text AS status, refused_reason, provider, provider_message_id,"
                " sent_at FROM outreach_messages WHERE id = :id"
            ),
            {"id": message_id},
        ).one()


def timeline(db: Databases, lead_id: UUID) -> list[Any]:
    with db.owner.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT kind::text AS kind, detail FROM lead_events WHERE lead_id = :l"
                    " ORDER BY created_at, kind::text"
                ),
                {"l": lead_id},
            )
        )


def email_of(client: TestClient) -> str:
    address: str = client.get("/v1/me").json()["email"]
    return address


def token_in(email: Email) -> str:
    link = next(line for line in email.text.splitlines() if "/unsubscribe?token=" in line)
    return link.split("token=", 1)[1].strip()
