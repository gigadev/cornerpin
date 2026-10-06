"""Runs one scenario end to end: its own database with the demo seed, the API in process, the
outbox drained after every step, email captured, and the clock set to the step's time in Boise.
Only the model is swapped (models.py); the agent, its tools and guardrails are the real ones."""

import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from cornerpin.core.auth import service
from cornerpin.core.auth.deps import SESSION_COOKIE
from cornerpin.core.config import get_settings
from cornerpin.core.db import api_engine
from cornerpin.core.outbox import drain
from cornerpin.devtools import recreate_database
from cornerpin.main import create_app
from cornerpin.notifications import handlers as notification_handlers
from cornerpin.notifications.email import Email
from cornerpin.outreach import agent, channels, policy
from cornerpin.outreach.agent import Turn
from cornerpin.outreach.model import AgentModel
from cornerpin.seed import DEMO_SLUG, DEMO_TENANT_ID, seed

from .models import EvalModel
from .scenarios import Ask, OptOut, Reply, Scenario

EVALS_DATABASE = "cornerpin_evals"
BOISE = ZoneInfo("America/Boise")
INBOUND_DOMAIN = "reply.cornerpin.test"


def prepare(*, live: bool) -> Engine:
    """Point everything at a fresh `cornerpin_evals` database with the demo seed. Without
    `live`, the agent is switched on with a placeholder key: the model is a recording."""
    dev = get_settings()
    owner_url = make_url(dev.database_url).set(database=EVALS_DATABASE)
    api_url = make_url(dev.api_database_url).set(database=EVALS_DATABASE)
    os.environ.update(
        DATABASE_URL=owner_url.render_as_string(hide_password=False),
        API_DATABASE_URL=api_url.render_as_string(hide_password=False),
        OUTBOX_RUNNER="off",
        INBOUND_EMAIL_DOMAIN=INBOUND_DOMAIN,
        AGENT_FOLLOW_UP_MINUTES="0",
        STORAGE_DIR=tempfile.mkdtemp(prefix="cornerpin-evals-storage-"),
    )
    if not live:
        os.environ["ANTHROPIC_API_KEY"] = "recorded-replies"
    get_settings.cache_clear()
    api_engine.cache_clear()
    recreate_database(owner_url)
    owner = create_engine(owner_url)
    with owner.begin() as conn:
        seed(conn)
    return owner


@dataclass
class Mailbox:
    sent: list[Email] = field(default_factory=lambda: list[Email]())

    def send(self, email: Email) -> str | None:
        self.sent.append(email)
        return f"eval-{uuid4().hex}"


@dataclass
class Clock:
    now: datetime = field(default_factory=lambda: datetime.now(BOISE))

    def __call__(self) -> datetime:
        return self.now


def today_at(hhmm: str) -> datetime:
    """Today's date in Boise, at a local time. Today, so that a message held for tomorrow
    morning is still in the future for the outbox."""
    return datetime.combine(datetime.now(BOISE).date(), time.fromisoformat(hhmm), BOISE)


@dataclass
class Outcome:
    scenario: Scenario
    buyer: str
    model: EvalModel
    emails: list[Email]
    turns: list[Turn]
    handed_off: bool
    handoff_reason: str | None
    held_until: datetime | None  # when a message held for sending hours goes
    asked_on: date
    errors: list[str]


class Harness:
    def __init__(self, owner: Engine) -> None:
        self.owner = owner
        self.mail = Mailbox()
        self.clock = Clock()
        self.turns: list[Turn] = []
        self.model: AgentModel | None = None
        run_turn: Callable[..., Turn] = agent.run_turn

        def capture(*args: Any, **kwargs: Any) -> Turn:
            turn = run_turn(*args, **kwargs)
            self.turns.append(turn)
            return turn

        # The seams: email out, the clock, the model, and a record of each turn.
        setattr(channels, "get_email_sender", lambda: self.mail)  # noqa: B010
        setattr(notification_handlers, "get_email_sender", lambda: self.mail)  # noqa: B010
        setattr(policy, "utcnow", self.clock)  # noqa: B010
        setattr(agent, "get_model", lambda: self.model)  # noqa: B010
        setattr(agent, "run_turn", capture)  # noqa: B010

    def _one(self, sql: str, **params: object) -> Any:
        with self.owner.connect() as conn:
            return conn.execute(text(sql), params).one_or_none()

    def run(
        self,
        scenario: Scenario,
        model: EvalModel,
        plant: Callable[[AgentModel], AgentModel] | None = None,
    ) -> Outcome:
        """Play the scenario's steps. The agent gets `model`, wrapped in `plant` if given."""
        self.model = plant(model) if plant else model
        self.mail.sent.clear()
        self.turns.clear()
        buyer = f"{scenario.name.replace('_', '-')}-{uuid4().hex[:6]}@buyers.cornerpin.test"
        first_event: int = self._one("SELECT coalesce(max(id), 0) AS id FROM outbox").id
        errors: list[str] = []
        asked_on = datetime.now(BOISE).date()

        with TestClient(create_app()) as client:
            signed_in = service.sign_in_verified_email(buyer, None, "/", "evals")
            client.cookies.set(SESSION_COOKIE, signed_in.session_token)
            for step in scenario.steps:
                match step:
                    case Ask():
                        self.clock.now = today_at(step.at)
                        asked_on = self.clock.now.date()
                        lot = self._one(
                            "SELECT l.id FROM lots l JOIN subdivisions s"
                            " ON s.id = l.subdivision_id WHERE s.slug = :slug AND l.number = :n",
                            slug=DEMO_SLUG,
                            n=step.lot,
                        )
                        response = client.post(
                            f"/v1/lots/{lot.id}/inquiries",
                            json={
                                "name": "Casey Rivera",
                                "message": step.message,
                                "contact": {"email": step.allow_email},
                            },
                        )
                    case Reply():
                        self.clock.now += timedelta(minutes=10)
                        latest = next((m for m in reversed(self.mail.sent) if m.to == buyer), None)
                        if latest is None or latest.reply_to is None:
                            errors.append(f"nothing to reply to before {step.text!r}")
                            break
                        response = client.post(
                            "/v1/dev/inbound-email",
                            json={
                                "to": latest.reply_to,
                                "from_address": buyer,
                                "subject": f"Re: {latest.subject}",
                                "text": step.text,
                            },
                        )
                    case OptOut():
                        response = client.post(
                            "/v1/me/consents",
                            json={
                                "tenant_id": str(DEMO_TENANT_ID),
                                "channel": "email",
                                "granted": False,
                            },
                        )
                if not response.is_success:
                    errors.append(f"{step}: {response.status_code} {response.text}")
                    break
                drain()

        lead = self._one(
            "SELECT id, handoff_at IS NOT NULL AS handed_off, handoff_reason FROM leads"
            " WHERE tenant_id = :t AND email = :e",
            t=DEMO_TENANT_ID,
            e=buyer,
        )
        lead_id: UUID | None = lead.id if lead else None
        held = self._one(
            "SELECT o.available_at FROM outbox o"
            " JOIN outreach_messages m ON m.id = CAST(o.payload->>'message_id' AS uuid)"
            " WHERE o.event_type = 'outreach.send' AND o.processed_at IS NULL AND m.lead_id = :l"
            " ORDER BY o.available_at DESC LIMIT 1",
            l=lead_id,
        )
        with self.owner.connect() as conn:
            failed = conn.execute(
                text(
                    "SELECT event_type, last_error FROM outbox"
                    " WHERE id > :first AND last_error IS NOT NULL"
                ),
                {"first": first_event},
            ).all()
        errors += [f"{row.event_type} failed: {row.last_error}" for row in failed]
        # A failed turn would retry during a later scenario, with that scenario's model.
        with self.owner.begin() as conn:
            conn.execute(
                text(
                    "UPDATE outbox SET processed_at = now() WHERE id > :first"
                    " AND processed_at IS NULL"
                    " AND event_type IN ('outreach.follow_up_due', 'outreach.reply_received')"
                ),
                {"first": first_event},
            )

        return Outcome(
            scenario=scenario,
            buyer=buyer,
            model=model,
            emails=[m for m in self.mail.sent if m.to == buyer],
            turns=[t for t in self.turns if t.lead_id == lead_id],
            handed_off=bool(lead and lead.handed_off),
            handoff_reason=lead.handoff_reason if lead else None,
            held_until=held.available_at if held else None,
            asked_on=asked_on,
            errors=errors,
        )
