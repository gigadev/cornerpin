"""P2-03: outreach (ADR-036). No send without consent; a send in quiet hours waits for the next
window; after an opt-out the next send is refused and logged; every send has a row."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cornerpin.core.db import worker_session
from cornerpin.core.outbox import drain
from cornerpin.outreach import policy
from cornerpin.outreach.service import deliver

from .conftest import Databases, Listing
from .outreach_support import (
    BOISE,
    TURNSTILE,
    Clock,
    Mailbox,
    ask_to_send,
    email_of,
    inquire,
    lead_of,
    message,
    timeline,
    token_in,
)

# --- the rules, without a database ----------------------------------------------------------


@pytest.mark.parametrize(
    ("local", "opens"),
    [
        (datetime(2026, 10, 6, 8, 59), datetime(2026, 10, 6, 9, 0)),
        (datetime(2026, 10, 6, 9, 0), None),
        (datetime(2026, 10, 6, 19, 59), None),
        (datetime(2026, 10, 6, 20, 0), datetime(2026, 10, 7, 9, 0)),
        (datetime(2026, 10, 6, 23, 30), datetime(2026, 10, 7, 9, 0)),
    ],
)
def test_sending_hours(local: datetime, opens: datetime | None) -> None:
    now = local.replace(tzinfo=BOISE).astimezone(UTC)
    expected = opens.replace(tzinfo=BOISE) if opens else None
    assert policy.next_window(now, BOISE) == expected


def test_unknown_time_zones_fall_back() -> None:
    assert policy.zone("Mars/Olympus") == BOISE
    assert policy.zone(None) == BOISE


# --- sending --------------------------------------------------------------------------------


def test_a_consented_email_is_sent_logged_and_says_how_to_stop(
    buyer: TestClient, listing: Listing, db: Databases, outreach_mail: Mailbox, clock: Clock
) -> None:
    inquire(buyer, listing, allow_email=True)
    email = email_of(buyer)
    lead_id = lead_of(db, listing, email)

    message_id = ask_to_send(db, listing, lead_id, "Happy to walk the lot with you Saturday.")
    assert message(db, message_id).status == "queued"  # a row before anything happens
    drain()

    sent = message(db, message_id)
    assert (sent.status, sent.provider) == ("sent", "smtp")
    assert sent.provider_message_id.startswith("msg-")
    assert sent.sent_at == clock.now
    [mail] = outreach_mail.to(email)
    assert mail.subject == "Lot 1 at Buyers"
    assert mail.text.startswith("Happy to walk the lot with you Saturday.")
    assert "because you allowed alpha to email you" in mail.text
    assert "/unsubscribe?token=" in mail.text
    assert mail.headers["List-Unsubscribe"].startswith("<http://localhost:3300/v1/unsubscribe?")
    assert mail.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert mail.reply_to == "owner@alpha.test"
    events = {event.kind: event.detail for event in timeline(db, lead_id)}
    assert events["message_sent"]["subject"] == "Lot 1 at Buyers"
    assert events["message_sent"]["message"] == "Happy to walk the lot with you Saturday."
    assert events["stage_changed"] == {"from": "new", "to": "contacted"}  # the first send

    # A retried event never sends twice.
    with worker_session(engine=db.api) as session:
        deliver(session, message_id, clock.now)
    assert len(outreach_mail.to(email)) == 1


def test_no_send_without_consent(
    buyer: TestClient,
    anonymous: TestClient,
    listing: Listing,
    db: Databases,
    outreach_mail: Mailbox,
    clock: Clock,
) -> None:
    # Signed in but never allowed email; and an anonymous inquirer, who can't consent.
    inquire(buyer, listing, allow_email=False)
    walk_in = "walk.in.outreach@example.test"
    inquire(anonymous, listing, allow_email=False, email=walk_in, **TURNSTILE)
    leads = [lead_of(db, listing, email_of(buyer)), lead_of(db, listing, walk_in)]

    sent = [ask_to_send(db, listing, lead_id) for lead_id in leads]
    drain()

    for message_id, lead_id in zip(sent, leads, strict=True):
        assert (message(db, message_id).status, message(db, message_id).refused_reason) == (
            "refused",
            "no_consent",
        )
        outcome = timeline(db, lead_id)[-1]
        assert (outcome.kind, outcome.detail["reason"]) == ("message_refused", "no_consent")
    assert outreach_mail.to(email_of(buyer)) == []
    assert outreach_mail.to(walk_in) == []


def test_a_send_in_quiet_hours_waits_for_the_morning(
    buyer: TestClient, listing: Listing, db: Databases, outreach_mail: Mailbox, clock: Clock
) -> None:
    inquire(buyer, listing, allow_email=True)
    email = email_of(buyer)
    clock.now = datetime(2026, 10, 6, 22, 30, tzinfo=BOISE)
    message_id = ask_to_send(db, listing, lead_of(db, listing, email))
    drain()

    assert message(db, message_id).status == "queued"
    assert outreach_mail.to(email) == []
    with db.owner.connect() as conn:
        waiting = conn.execute(
            text(
                "SELECT available_at FROM outbox WHERE processed_at IS NULL"
                " AND event_type = 'outreach.send' AND payload->>'message_id' = :id"
            ),
            {"id": str(message_id)},
        ).scalar_one()
    assert waiting == datetime(2026, 10, 7, 9, 0, tzinfo=BOISE)

    clock.now = datetime(2026, 10, 7, 9, 5, tzinfo=BOISE)
    with db.owner.begin() as conn:  # the morning has come
        conn.execute(
            text("UPDATE outbox SET available_at = now() WHERE payload->>'message_id' = :id"),
            {"id": str(message_id)},
        )
    drain()
    assert message(db, message_id).status == "sent"
    assert len(outreach_mail.to(email)) == 1


def test_quiet_hours_are_the_buyers_own_when_they_have_set_a_time_zone(
    buyer: TestClient, listing: Listing, db: Databases, outreach_mail: Mailbox, clock: Clock
) -> None:
    inquire(buyer, listing, allow_email=True)
    assert buyer.patch("/v1/me", json={"time_zone": "America/New_York"}).status_code == 200
    clock.now = datetime(2026, 10, 6, 19, 30, tzinfo=BOISE)  # 9:30 pm in New York
    message_id = ask_to_send(db, listing, lead_of(db, listing, email_of(buyer)))
    drain()
    assert message(db, message_id).status == "queued"


def test_after_an_opt_out_the_next_send_is_refused_and_logged(
    buyer: TestClient,
    anonymous: TestClient,
    listing: Listing,
    db: Databases,
    outreach_mail: Mailbox,
    clock: Clock,
) -> None:
    inquire(buyer, listing, allow_email=True)
    email = email_of(buyer)
    lead_id = lead_of(db, listing, email)
    ask_to_send(db, listing, lead_id)
    drain()
    token = token_in(outreach_mail.to(email)[0])

    # Opening the link changes nothing (mail scanners open links); the button does.
    page = anonymous.get("/v1/unsubscribe", params={"token": token})
    assert page.status_code == 200, page.text
    assert (page.json()["channel"], page.json()["allowed"]) == ("email", True)
    stopped = anonymous.post("/v1/unsubscribe", params={"token": token})
    assert stopped.json()["allowed"] is False
    again = anonymous.post("/v1/unsubscribe", params={"token": token})  # one-click, twice
    assert again.status_code == 200

    with db.owner.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT granted, source FROM contact_consents c JOIN users u ON u.id = c.user_id"
                " WHERE u.email = :e AND c.tenant_id = :t ORDER BY c.recorded_at"
            ),
            {"e": email, "t": listing.tenant.tenant_id},
        ).all()
    assert [tuple(row) for row in rows] == [(True, "inquiry"), (False, "unsubscribe")]

    refused = ask_to_send(db, listing, lead_id)
    drain()
    assert (message(db, refused).status, message(db, refused).refused_reason) == (
        "refused",
        "opted_out",
    )
    assert len(outreach_mail.to(email)) == 1
    kinds = [event.kind for event in timeline(db, lead_id)]
    assert kinds[-2:] == ["consent_changed", "message_refused"]


def test_a_bad_unsubscribe_link_is_refused(anonymous: TestClient) -> None:
    assert anonymous.get("/v1/unsubscribe", params={"token": "nope.nope"}).status_code == 400
    assert anonymous.post("/v1/unsubscribe", params={"token": "x"}).status_code == 400


def test_daily_caps(
    client_for: Callable[[str | None], TestClient],
    buyer: TestClient,
    listing: Listing,
    db: Databases,
    outreach_mail: Mailbox,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inquire(buyer, listing, allow_email=True)
    lead_id = lead_of(db, listing, email_of(buyer))
    sent = [ask_to_send(db, listing, lead_id) for _ in range(policy.LEAD_DAILY_CAP + 1)]
    drain()
    outcomes = [(message(db, m).status, message(db, m).refused_reason) for m in sent]
    assert outcomes == [("sent", None)] * policy.LEAD_DAILY_CAP + [("refused", "lead_daily_cap")]

    # A day later the lead may hear again; a full tenant still refuses.
    clock.now += timedelta(hours=25)
    monkeypatch.setattr(policy, "TENANT_DAILY_CAP", 0)
    capped = ask_to_send(db, listing, lead_id)
    drain()
    assert message(db, capped).refused_reason == "tenant_daily_cap"


def test_a_failed_send_is_retried_and_sent_once(
    buyer: TestClient, listing: Listing, db: Databases, outreach_mail: Mailbox, clock: Clock
) -> None:
    inquire(buyer, listing, allow_email=True)
    email = email_of(buyer)
    outreach_mail.failing = True
    message_id = ask_to_send(db, listing, lead_of(db, listing, email))
    drain()
    assert message(db, message_id).status == "queued"

    outreach_mail.failing = False
    with db.owner.begin() as conn:  # skip the back-off
        conn.execute(
            text("UPDATE outbox SET available_at = now() WHERE payload->>'message_id' = :id"),
            {"id": str(message_id)},
        )
    drain()
    assert message(db, message_id).status == "sent"
    assert len(outreach_mail.to(email)) == 1
