"""Helpers for the outreach tests (P2-03 to P2-05): a fake mailbox, clock and model, and
shortcuts to a lead with consent and a queued message. The fixtures that install them are in
conftest.py."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from anthropic.types import MessageParam, ToolParam
from fastapi.testclient import TestClient
from sqlalchemy import text

from cornerpin.core.db import worker_session
from cornerpin.notifications.email import Email
from cornerpin.outreach.model import ModelReply, ToolCall, Usage
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


Step = ModelReply | Callable[[list[MessageParam]], ModelReply]


@dataclass
class ScriptedModel:
    """Stands in for Claude (P2-05): each call takes the next step, a reply or a function of the
    conversation so far. Running out of steps fails the test's turn."""

    steps: list[Step] = field(default_factory=lambda: list[Step]())
    calls: list[tuple[str, list[MessageParam]]] = field(default_factory=lambda: [])
    name: str = "scripted"

    def reply(
        self, *, system: str, messages: list[MessageParam], tools: list[ToolParam]
    ) -> ModelReply:
        self.calls.append((system, list(messages)))
        if not self.steps:
            raise AssertionError("the model was called more often than scripted")
        step = self.steps.pop(0)
        return step(messages) if callable(step) else step


def use(name: str, **arguments: Any) -> ModelReply:
    """A reply that calls one tool."""
    return ModelReply(
        text="",
        tool_calls=(ToolCall(id=f"call_{uuid4().hex[:8]}", name=name, input=arguments),),
        stop_reason="tool_use",
    )


def write(body: str) -> ModelReply:
    return ModelReply(text=body, usage=Usage(input_tokens=1000, output_tokens=100))


def last_result(messages: list[MessageParam]) -> dict[str, Any]:
    """The JSON the last tool call returned."""
    content = messages[-1]["content"]
    assert not isinstance(content, str)
    block: Any = list(content)[-1]
    result: dict[str, Any] = json.loads(block["content"])
    return result


def email_of(client: TestClient) -> str:
    address: str = client.get("/v1/me").json()["email"]
    return address


def token_in(email: Email) -> str:
    link = next(line for line in email.text.splitlines() if "/unsubscribe?token=" in line)
    return link.split("token=", 1)[1].strip()
