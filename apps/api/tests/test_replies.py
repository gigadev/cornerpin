"""P2-04: replies on the timeline (ADR-037). A signed webhook appends the reply to the right
lead; an unsigned or unknown one is rejected and logged; a reply hands the lead on (engaged,
and the agent in P2-05)."""

import base64
import hashlib
import hmac
import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cornerpin.core.config import get_settings
from cornerpin.core.outbox import drain
from cornerpin.outreach import handlers as outreach_handlers
from cornerpin.outreach.replies import html_to_text, message_for, reply_address, reply_text
from cornerpin.outreach.webhooks import verify_svix

from .conftest import Databases, Listing
from .outreach_support import Clock, Mailbox, ask_to_send, email_of, inquire, lead_of

DOMAIN = "reply.cornerpin.test"
SECRET = "whsec_" + base64.b64encode(b"test-webhook-signing-key-32bytes").decode()


@dataclass
class FakeInbox:
    texts: dict[str, str] = field(default_factory=lambda: {})

    def text_of(self, email_id: str) -> str:
        return self.texts[email_id]


@pytest.fixture
def inbound(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeInbox]:
    monkeypatch.setenv("INBOUND_EMAIL_DOMAIN", DOMAIN)
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    inbox = FakeInbox()
    monkeypatch.setattr(outreach_handlers, "get_inbox", lambda: inbox)
    yield inbox
    get_settings.cache_clear()


def signed(body: bytes, *, secret: str = SECRET, at: int | None = None) -> dict[str, str]:
    stamp = str(at if at is not None else int(time.time()))
    message_id = f"msg_{uuid4().hex}"
    key = base64.b64decode(secret.removeprefix("whsec_"))
    mac = hmac.new(key, f"{message_id}.{stamp}.".encode() + body, hashlib.sha256).digest()
    return {
        "svix-id": message_id,
        "svix-timestamp": stamp,
        "svix-signature": f"v1,{base64.b64encode(mac).decode()}",
    }


def received(to: str, sender: str, email_id: str) -> bytes:
    return json.dumps(
        {
            "type": "email.received",
            "created_at": "2026-10-06T21:00:00Z",
            "data": {
                "email_id": email_id,
                "from": f"Pat Buyer <{sender}>",
                "to": [to],
                "subject": "Re: Lot 1 at Buyers",
                "attachments": [],
            },
        }
    ).encode()


def sent_outreach(buyer: TestClient, listing: Listing, db: Databases) -> tuple[UUID, UUID, str]:
    """A buyer who allowed email, and an outreach email sent to them: (lead, message, buyer)."""
    inquire(buyer, listing, allow_email=True)
    email = email_of(buyer)
    lead_id = lead_of(db, listing, email)
    message_id = ask_to_send(db, listing, lead_id, "Would Saturday at 10 suit you?")
    drain()
    return lead_id, message_id, email


def inbound_rows(db: Databases, lead_id: UUID) -> list[Any]:
    with db.owner.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT body, subject, from_address::text AS from_address, provider,"
                    " status::text AS status FROM outreach_messages"
                    " WHERE lead_id = :l AND direction = 'inbound'"
                ),
                {"l": lead_id},
            )
        )


def latest_event(db: Databases, lead_id: UUID) -> Any:
    with db.owner.connect() as conn:
        return conn.execute(
            text(
                "SELECT kind::text AS kind, verified, detail FROM lead_events WHERE lead_id = :l"
                " AND kind = 'message_received' ORDER BY created_at DESC LIMIT 1"
            ),
            {"l": lead_id},
        ).one_or_none()


def stage(db: Databases, lead_id: UUID) -> str:
    with db.owner.connect() as conn:
        value: str = conn.execute(
            text("SELECT stage::text FROM leads WHERE id = :l"), {"l": lead_id}
        ).scalar_one()
    return value


# --- addresses and text, without a database -------------------------------------------------


def test_reply_addresses_name_their_message_and_cant_be_forged() -> None:
    message_id = uuid4()
    address = reply_address(message_id, DOMAIN)
    assert len(address.split("@")[0]) <= 64
    assert message_for(address) == message_id
    assert message_for(address.upper()) == message_id  # mail systems may change case
    assert message_for(f"Demo Land Co. <{address}>".split(" ")[-1]) == message_id
    local, _, domain = address.partition("@")
    forged = f"{local[:-1]}{'0' if local[-1] != '0' else '1'}@{domain}"
    assert message_for(forged) is None
    assert message_for(f"reply+{uuid4().hex}{'0' * 16}@{DOMAIN}") is None
    assert message_for("owner@alpha.test") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Saturday works.\n\nOn Tue, Oct 6, 2026 at 3:00 PM Demo Land Co <reply+x@r.test>"
            " wrote:\n> Would Saturday suit you?",
            "Saturday works.",
        ),
        (
            "Yes please.\r\n\r\nOn Tue, Oct 6, 2026 at 3:00 PM Demo Land Co\r\nwrote:\r\n> Hi",
            "Yes please.",
        ),
        (
            "Can we do 11?\n\nFrom: Demo Land Co <reply+x@r.test>\nSent: Tuesday\nSubject: Lot",
            "Can we do 11?",
        ),
        ("See you then\n\nSent from my iPhone", "See you then"),
        (
            "Coming from the north.\nFrom: the highway, I mean.",
            "Coming from the north.\nFrom: the highway, I mean.",
        ),
        ("> only a quote", "> only a quote"),
        ("Fine\n-----Original Message-----\nFrom: x", "Fine"),
    ],
)
def test_reply_text_drops_the_quoted_history(raw: str, expected: str) -> None:
    assert reply_text(raw) == expected


def test_html_only_emails_still_read() -> None:
    assert html_to_text("<p>Saturday<br>works &amp; thanks</p><style>p{}</style>") == (
        "Saturday\nworks & thanks\n"
    )


def test_svix_signatures() -> None:
    body = b'{"type":"email.received"}'
    now = time.time()
    good = signed(body)
    assert verify_svix(SECRET, good, body, now)
    assert verify_svix(
        SECRET, {**good, "svix-signature": "v1,nope v1," + good["svix-signature"][3:]}, body, now
    )
    assert not verify_svix(SECRET, good, body + b" ", now)  # the body was changed
    assert not verify_svix(SECRET, signed(body, at=int(now) - 600), body, now)  # too old
    other = "whsec_" + base64.b64encode(b"someone-elses-key").decode()
    assert not verify_svix(SECRET, signed(body, secret=other), body, now)
    assert not verify_svix(SECRET, {}, body, now)
    assert not verify_svix(SECRET, {**good, "svix-timestamp": "soon"}, body, now)


# --- through the API and the outbox ---------------------------------------------------------


def test_outreach_replies_to_an_address_for_its_own_message(
    inbound: FakeInbox, buyer: TestClient, listing: Listing, db: Databases, outreach_mail: Mailbox,
    clock: Clock,
) -> None:  # fmt: skip
    _, message_id, email = sent_outreach(buyer, listing, db)
    [mail] = outreach_mail.to(email)
    assert mail.reply_to is not None and mail.reply_to.endswith(f"@{DOMAIN}")
    assert message_for(mail.reply_to) == message_id


def test_a_signed_webhook_puts_the_reply_on_the_right_lead(
    inbound: FakeInbox, anonymous: TestClient, buyer: TestClient, listing: Listing,
    db: Databases, outreach_mail: Mailbox, clock: Clock,
) -> None:  # fmt: skip
    lead_id, message_id, email = sent_outreach(buyer, listing, db)
    inbound.texts["em_1"] = (
        "Saturday at 10 is perfect.\n\nOn Tue, Oct 6 Demo wrote:\n> Would Saturday at 10 suit?"
    )
    body = received(reply_address(message_id, DOMAIN), email.upper(), "em_1")

    posted = anonymous.post("/v1/webhooks/resend", content=body, headers=signed(body))
    assert posted.status_code == 204, posted.text
    drain()

    [reply] = inbound_rows(db, lead_id)
    assert (reply.body, reply.subject, reply.from_address, reply.provider, reply.status) == (
        "Saturday at 10 is perfect.",
        "Re: Lot 1 at Buyers",
        email,
        "resend",
        "received",
    )
    event = latest_event(db, lead_id)
    assert (event.verified, event.detail["message"]) == (True, "Saturday at 10 is perfect.")
    assert stage(db, lead_id) == "engaged"
    with db.owner.connect() as conn:
        payload = conn.execute(
            text(
                "SELECT payload FROM outbox WHERE event_type = 'outreach.inbound_email'"
                " AND payload->>'provider_email_id' = 'em_1'"
            )
        ).scalar_one()
    assert {"text", "subject", "from_address"}.isdisjoint(payload)  # the words left the outbox

    # The provider retries: still one reply.
    again = anonymous.post("/v1/webhooks/resend", content=body, headers=signed(body))
    assert again.status_code == 204
    drain()
    assert len(inbound_rows(db, lead_id)) == 1


def test_a_reply_from_another_address_is_kept_but_not_verified(
    inbound: FakeInbox, anonymous: TestClient, buyer: TestClient, listing: Listing,
    db: Databases, outreach_mail: Mailbox, clock: Clock,
) -> None:  # fmt: skip
    lead_id, message_id, _ = sent_outreach(buyer, listing, db)
    inbound.texts["em_2"] = "Forwarding this to my wife."
    body = received(reply_address(message_id, DOMAIN), "someone.else@example.test", "em_2")
    assert (
        anonymous.post("/v1/webhooks/resend", content=body, headers=signed(body)).status_code == 204
    )
    drain()
    assert latest_event(db, lead_id).verified is False


def test_unsigned_and_badly_signed_webhooks_are_rejected_and_logged(
    inbound: FakeInbox, anonymous: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    body = received(f"reply+{uuid4().hex}{'0' * 16}@{DOMAIN}", "x@example.test", "em_3")
    with caplog.at_level(logging.WARNING, logger="cornerpin.outreach.webhooks"):
        assert anonymous.post("/v1/webhooks/resend", content=body).status_code == 401
        forged = signed(body, secret="whsec_" + base64.b64encode(b"wrong").decode())
        assert (
            anonymous.post("/v1/webhooks/resend", content=body, headers=forged).status_code == 401
        )
    assert caplog.text.count("missing or bad signature") == 2


def test_a_reply_to_an_unknown_address_is_dropped_and_logged(
    inbound: FakeInbox, anonymous: TestClient, db: Databases, outreach_mail: Mailbox,
    caplog: pytest.LogCaptureFixture,
) -> None:  # fmt: skip
    inbound.texts["em_4"] = "hello?"
    body = received(f"reply+{uuid4().hex}{'0' * 16}@{DOMAIN}", "x@example.test", "em_4")
    assert (
        anonymous.post("/v1/webhooks/resend", content=body, headers=signed(body)).status_code == 204
    )
    with caplog.at_level(logging.WARNING, logger="cornerpin.outreach.inbound"):
        drain()
    assert "em_4 from resend dropped" in caplog.text
    with db.owner.connect() as conn:
        found = conn.execute(
            text("SELECT count(*) FROM outreach_messages WHERE provider_message_id = 'em_4'")
        ).scalar_one()
    assert found == 0


def test_the_webhook_is_dormant_until_configured(anonymous: TestClient) -> None:
    body = b"{}"
    assert (
        anonymous.post("/v1/webhooks/resend", content=body, headers=signed(body)).status_code == 404
    )


def test_locally_the_dev_route_plays_the_provider(
    inbound: FakeInbox, anonymous: TestClient, buyer: TestClient, listing: Listing,
    db: Databases, outreach_mail: Mailbox, clock: Clock,
) -> None:  # fmt: skip
    lead_id, message_id, email = sent_outreach(buyer, listing, db)
    posted = anonymous.post(
        "/v1/dev/inbound-email",
        json={"to": reply_address(message_id, DOMAIN), "from_address": email,
              "subject": "Re: hi", "text": "Works for me.\n\n> earlier"},
    )  # fmt: skip
    assert posted.status_code == 204, posted.text
    drain()
    assert [row.body for row in inbound_rows(db, lead_id)] == ["Works for me."]
